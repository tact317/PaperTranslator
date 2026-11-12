from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m
from backend import phase43_region_finisher as p43
from backend import phase45_source_aligned_finisher as p45
from backend import phase50_terminal_band_finisher as p50
from backend import phase51_exact_residue_finisher as p51
from backend import phase52_all_layer_residue_finisher as p52


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest_document_id() -> str:
    candidates: list[tuple[float, str]] = []
    for path in m.LAYOUT_TRANSLATION_CACHE_DIR.iterdir():
        if not path.is_dir():
            continue
        mono = path / "translated-mono.pdf"
        qa = path / "qa.json"
        if mono.exists() and qa.exists():
            candidates.append((max(mono.stat().st_mtime, qa.stat().st_mtime), path.name))
    if not candidates:
        raise RuntimeError("translated full-paper cache was not found")
    return max(candidates)[1]


def _root(document_id: str) -> Path:
    path = m._layout_dir(document_id) / "phase53_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 53, "updated_at": _utc_now(), **payload})


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "")


def _norm_token(value: str) -> str:
    return p51._norm_token(_nfkc(value))


def _anchor_tokens(anchor: str) -> list[str]:
    text = _nfkc(anchor)
    return [token for token in (_norm_token(x) for x in p51._TOKEN_RE.findall(text)) if token]


def _raw_records(page: fitz.Page) -> list[dict]:
    records: list[dict] = []
    for raw in page.get_text("words", sort=True):
        if len(raw) < 8:
            continue
        x0, y0, x1, y1, word, block_no, line_no, word_no = raw[:8]
        rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        normalized_word = _nfkc(str(word))
        for match in p51._TOKEN_RE.finditer(normalized_word):
            token = _norm_token(match.group(0))
            if token:
                records.append({
                    "token": token,
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "block": int(block_no),
                    "line": int(line_no),
                    "word": int(word_no),
                    "raw": str(word),
                })
    return records


def _overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    return inter / max(1e-6, min(a.get_area(), b.get_area()))


def _dedupe_visual_records(records: list[dict]) -> list[dict]:
    """Collapse hidden duplicate glyph runs without depending on PDF block ids."""
    out: list[dict] = []
    for item in records:
        rect = fitz.Rect(item["bbox"])
        duplicate = False
        for existing in out[-18:]:
            if existing["token"] != item["token"]:
                continue
            other = fitz.Rect(existing["bbox"])
            if _overlap_ratio(rect, other) >= 0.55 or (
                abs((rect.y0 + rect.y1) - (other.y0 + other.y1)) <= 2.6
                and abs((rect.x0 + rect.x1) - (other.x0 + other.x1)) <= 3.2
            ):
                # Keep the envelope so a later redaction covers every near-coincident layer.
                merged = other | rect
                existing["bbox"] = [merged.x0, merged.y0, merged.x1, merged.y1]
                duplicate = True
                break
        if not duplicate:
            out.append(dict(item))
    return out


def _cluster_lines(records: list[dict]) -> list[list[dict]]:
    if not records:
        return []
    heights = [fitz.Rect(item["bbox"]).height for item in records]
    tol = max(2.2, statistics.median(heights) * 0.52)
    lines: list[list[dict]] = []
    for item in sorted(records, key=lambda r: ((r["bbox"][1] + r["bbox"][3]) / 2.0, r["bbox"][0])):
        cy = (item["bbox"][1] + item["bbox"][3]) / 2.0
        placed = False
        for line in reversed(lines[-3:]):
            lcy = statistics.median((r["bbox"][1] + r["bbox"][3]) / 2.0 for r in line)
            if abs(cy - lcy) <= tol:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])
    for line in lines:
        line.sort(key=lambda r: r["bbox"][0])
    return lines


def _line_sequence_match(lines: list[list[dict]], tokens: list[str]) -> list[list[dict]]:
    """Find the anchor across visual lines, allowing unrelated PDF objects between words."""
    flat: list[tuple[int, dict]] = []
    for line_idx, line in enumerate(lines):
        for item in line:
            flat.append((line_idx, item))
    matches: list[list[dict]] = []
    for start, (line_idx, item) in enumerate(flat):
        if not tokens:
            break
        first_ok = item["token"] == tokens[0]
        if not first_ok and len(tokens[0]) <= 4 and item["token"].endswith(tokens[0]):
            first_ok = True
        if not first_ok:
            continue
        chosen = [item]
        next_token = 1
        last_line = line_idx
        last_x = item["bbox"][0]
        for candidate_line, candidate in flat[start + 1:]:
            if next_token >= len(tokens):
                break
            if candidate_line < last_line or candidate_line > last_line + 2:
                if candidate_line > last_line + 2:
                    break
                continue
            # On the same visual line, preserve left-to-right reading order.  On the next
            # line x may reset to the column start.
            if candidate_line == last_line and candidate["bbox"][0] + 1.0 < last_x:
                continue
            if candidate["token"] == tokens[next_token]:
                chosen.append(candidate)
                next_token += 1
                last_line = candidate_line
                last_x = candidate["bbox"][0]
        if next_token == len(tokens):
            matches.append(chosen)
    return matches


def _rare_token_band_matches(page: fitz.Page, anchor: str) -> list[list[dict]]:
    """Last geometric fallback for a residue whose exact PDF sequence is fragmented.

    Use the longest lexical anchors, then collect all anchor words in the same one/two
    visual lines.  This avoids relying on block ids or serialization order.
    """
    tokens = _anchor_tokens(anchor)
    if not tokens:
        return []
    counts = Counter(tokens)
    rare = sorted({t for t in tokens if len(t) >= 6}, key=lambda t: (-len(t), t))[:4]
    if len(rare) < 2:
        rare = sorted(set(tokens), key=lambda t: (-len(t), t))[:3]
    records = _dedupe_visual_records(_raw_records(page))
    lines = _cluster_lines(records)
    token_set = set(tokens)
    candidates: list[tuple[int, int, int]] = []
    for i, line in enumerate(lines):
        present = {item["token"] for item in line}
        score = sum(1 for token in rare if token in present)
        if i + 1 < len(lines):
            present2 = present | {item["token"] for item in lines[i + 1]}
            score2 = sum(1 for token in rare if token in present2)
            if score2 >= score:
                candidates.append((score2, i, i + 1))
        candidates.append((score, i, i))
    if not candidates:
        return []
    score, begin, end = max(candidates, key=lambda row: row[0])
    if score < min(2, len(rare)):
        return []
    selected: list[dict] = []
    needed = counts.copy()
    for idx in range(begin, end + 1):
        for item in lines[idx]:
            if item["token"] in token_set and needed[item["token"]] > 0:
                selected.append(item)
                needed[item["token"]] -= 1
    # Require substantial anchor coverage so a common-word line cannot be erased.
    if len(selected) < max(3, int(len(tokens) * 0.65)):
        return []
    return [selected]


def _geometric_residue_matches(page: fitz.Page, anchor: str) -> tuple[list[list[dict]], dict]:
    tokens = _anchor_tokens(anchor)
    if not tokens:
        return [], {"reason": "anchor_tokens_missing"}

    # Fast native search first.  PyMuPDF can match across line wraps in many PDFs.
    native = page.search_for(_nfkc(anchor), quads=False)
    if native:
        matches: list[list[dict]] = []
        for rect in native:
            matches.append([{"token": "__native__", "bbox": [rect.x0, rect.y0, rect.x1, rect.y1], "block": -1, "line": -1, "word": -1, "raw": anchor}])
        return matches, {"reason": "", "mode": "native_search", "copies": len(matches)}

    records = _dedupe_visual_records(_raw_records(page))
    lines = _cluster_lines(records)
    matches = _line_sequence_match(lines, tokens)
    if matches:
        return matches, {"reason": "", "mode": "visual_sequence", "copies": len(matches)}

    matches = _rare_token_band_matches(page, anchor)
    if matches:
        return matches, {"reason": "", "mode": "rare_token_band", "copies": len(matches)}
    return [], {"reason": "geometric_residue_not_found", "anchor_tokens": tokens}


def _rects_for_match(match: list[dict], page: fitz.Page) -> list[fitz.Rect]:
    # Native search already returns one exact envelope.
    if match and match[0].get("token") == "__native__":
        rect = fitz.Rect(match[0]["bbox"])
        return [fitz.Rect(
            max(page.rect.x0 + 0.5, rect.x0 - 1.8),
            max(page.rect.y0 + 0.5, rect.y0 - 1.0),
            min(page.rect.x1 - 0.5, rect.x1 + 1.8),
            min(page.rect.y1 - 0.5, rect.y1 + 1.0),
        )]

    lines = _cluster_lines(match)
    rects: list[fitz.Rect] = []
    for line in lines:
        rect = fitz.Rect(line[0]["bbox"])
        for item in line[1:]:
            rect |= fitz.Rect(item["bbox"])
        rects.append(fitz.Rect(
            max(page.rect.x0 + 0.5, rect.x0 - 2.0),
            max(page.rect.y0 + 0.5, rect.y0 - 1.2),
            min(page.rect.x1 - 0.5, rect.x1 + 2.0),
            min(page.rect.y1 - 0.5, rect.y1 + 1.2),
        ))
    return rects


def _anchor_still_visible(pdf_path: Path, page_number: int, anchor: str) -> bool:
    text = m._extract_pdf_page_texts(pdf_path)[page_number - 1]
    normalized_anchor = re.sub(r"\s+", " ", _nfkc(anchor)).strip().lower()
    normalized_text = re.sub(r"\s+", " ", _nfkc(text)).strip().lower()
    if normalized_anchor and normalized_anchor in normalized_text:
        return True
    anchor_tokens = _anchor_tokens(anchor)
    if not anchor_tokens:
        return False
    for run in m._long_english_runs(text):
        run_tokens = _anchor_tokens(run)
        if len(set(anchor_tokens) & set(run_tokens)) >= max(3, int(len(set(anchor_tokens)) * 0.65)):
            return True
    return False


def _erase_residue_layers(pdf_path: Path, page_number: int, anchor: str, root: Path) -> tuple[Path | None, list[fitz.Rect], dict]:
    """Iteratively erase every discoverable copy of the exact residue.

    Saving and reopening between passes is intentional: some PDFs expose hidden text
    objects only after the top duplicate has been removed.
    """
    working = root / "phase53-erased.tmp.pdf"
    shutil.copy2(pdf_path, working)
    first_rects: list[fitz.Rect] = []
    history: list[dict] = []
    for round_idx in range(1, 5):
        doc = fitz.open(working)
        next_path = root / f"phase53-erased-{round_idx}.tmp.pdf"
        try:
            page = doc[page_number - 1]
            matches, meta = _geometric_residue_matches(page, anchor)
            if not matches:
                history.append({"round": round_idx, "status": "not_found", **meta})
                break
            rects: list[fitz.Rect] = []
            for match in matches:
                rects.extend(_rects_for_match(match, page))
            rects = p52._dedupe_rects(rects)
            if not rects:
                history.append({"round": round_idx, "status": "no_rects", **meta})
                break
            if not first_rects:
                first_rects = [fitz.Rect(r) for r in rects]
            for rect in rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            doc.save(next_path, garbage=4, clean=True, deflate=True)
            history.append({
                "round": round_idx,
                "status": "redacted",
                "mode": meta.get("mode"),
                "rects": [[r.x0, r.y0, r.x1, r.y1] for r in rects],
            })
        finally:
            doc.close()
        next_path.replace(working)
        if not _anchor_still_visible(working, page_number, anchor):
            return working, first_rects, {"reason": "", "rounds": history}
    if not _anchor_still_visible(working, page_number, anchor) and first_rects:
        return working, first_rects, {"reason": "", "rounds": history}
    return None, first_rects, {"reason": "residue_survived_geometric_erasure", "rounds": history}


def _fit_and_insert(pdf_path: Path, page_number: int, rects: list[fitz.Rect], translated: str, client) -> tuple[bool, dict]:
    if not rects:
        return False, {"reason": "no_insertion_rect"}
    doc = fitz.open(pdf_path)
    tmp = pdf_path.with_suffix(".phase53-insert.tmp.pdf")
    try:
        page = doc[page_number - 1]
        insertion = fitz.Rect(rects[0])
        for rect in rects[1:]:
            insertion |= rect
        insertion = fitz.Rect(
            insertion.x0,
            max(page.rect.y0 + 0.5, insertion.y0 - 0.8),
            insertion.x1,
            min(page.rect.y1 - 0.5, insertion.y1 + 1.6),
        )
        preferred = max(5.0, min(8.0, statistics.median(r.height for r in rects) * 0.72))
        final_text, fontsize, fit_meta = p52._fit_translation(insertion, translated, preferred, client)
        if final_text is None or fontsize is None:
            return False, {"reason": "layout_fit_failed", "fit": fit_meta}
        inserted = page.insert_textbox(
            insertion,
            final_text,
            fontsize=fontsize,
            fontname="japan",
            lineheight=1.0,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
            overlay=True,
        )
        if inserted < 0:
            return False, {"reason": "insert_failed", "fit": fit_meta}
        doc.save(tmp, garbage=4, clean=True, deflate=True)
    finally:
        doc.close()
    tmp.replace(pdf_path)
    return True, {
        "reason": "",
        "insert_bbox": [insertion.x0, insertion.y0, insertion.x1, insertion.y1],
        "fontsize": fontsize,
        "fit": fit_meta,
        "translation": final_text,
    }


def _repair_anchor(document_id: str, target_pdf: Path, page_number: int, anchor: str, client, root: Path) -> dict:
    before_text = m._extract_pdf_page_texts(target_pdf)[page_number - 1]
    before_science = p43._science_fingerprint(before_text)
    before_burden = p50._page_burden(target_pdf, page_number)

    # The QA residue is itself a faithful English source fragment.  Translating it
    # directly avoids a final coordinate-alignment dependency at this terminal stage.
    focus = p45._prepare_source_text(anchor)

    def on_progress(info: dict) -> None:
        payload = dict(info)
        payload.update({"status": "running", "page": page_number, "stage": str(info.get("stage") or "translating")})
        _progress(root, **payload)
        parts = ["  residue", str(info.get("stage") or "working")]
        if info.get("batch") is not None:
            parts.append(f"batch {info.get('batch')}/{info.get('batches')}")
        if info.get("attempt") is not None:
            parts.append(f"attempt {info.get('attempt')}/{info.get('max_attempts') or 2}")
        if info.get("reason"):
            parts.append(f"reason={info.get('reason')}")
        print(" | ".join(parts), flush=True)

    translated, rewrite_meta = p45._translate_source_region(document_id, focus, client, progress_callback=on_progress)
    if translated is None:
        return {"status": "failed", "reason": rewrite_meta.get("reason", "translation_failed"), "rewrite": rewrite_meta}

    erased_pdf, insertion_rects, erase_meta = _erase_residue_layers(target_pdf, page_number, anchor, root)
    if erased_pdf is None:
        return {"status": "failed", "reason": erase_meta.get("reason"), "rewrite": rewrite_meta, "erase": erase_meta}
    ok, insert_meta = _fit_and_insert(erased_pdf, page_number, insertion_rects, translated, client)
    if not ok:
        erased_pdf.unlink(missing_ok=True)
        return {"status": "failed", "reason": insert_meta.get("reason"), "rewrite": rewrite_meta, "erase": erase_meta, "insert": insert_meta}

    after_text = m._extract_pdf_page_texts(erased_pdf)[page_number - 1]
    after_science = p43._science_fingerprint(after_text)
    after_burden = p50._page_burden(erased_pdf, page_number)
    if not p43._science_equal(before_science, after_science):
        erased_pdf.unlink(missing_ok=True)
        return {"status": "failed", "reason": "page_science_changed", "before_burden": before_burden, "after_burden": after_burden, "erase": erase_meta, "insert": insert_meta}
    if _anchor_still_visible(erased_pdf, page_number, anchor):
        erased_pdf.unlink(missing_ok=True)
        return {"status": "failed", "reason": "anchor_still_visible", "before_burden": before_burden, "after_burden": after_burden, "erase": erase_meta, "insert": insert_meta}
    if not after_burden < before_burden:
        erased_pdf.unlink(missing_ok=True)
        return {"status": "failed", "reason": "no_visible_improvement", "before_burden": before_burden, "after_burden": after_burden, "erase": erase_meta, "insert": insert_meta}

    erased_pdf.replace(target_pdf)
    return {
        "status": "patched",
        "reason": "",
        "anchor": anchor,
        "focus": focus,
        "rewrite": rewrite_meta,
        "erase": erase_meta,
        "insert": insert_meta,
        "before_burden": before_burden,
        "after_burden": after_burden,
    }


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    input_qa = _load_json(qa_path)
    page_anchors = p50._critical_long_anchors(input_qa)
    pages = sorted(page_anchors)

    backup_pdf = root / "translated-mono.before-phase53.pdf"
    backup_qa = root / "qa.before-phase53.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)
    shutil.copy2(backup_pdf, target_pdf)

    manifest = {
        "phase": 53,
        "mode": "geometric-iterative-exact-residue-eradication",
        "started_at": _utc_now(),
        "document_id": document_id,
        "baseline": str(backup_pdf),
        "selected_pages": pages,
        "anchors": {str(page): page_anchors[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)
    _progress(root, status="starting", stage="starting", selected_pages=pages)

    print("===== PHASE53 GEOMETRIC RESIDUE ERADICATION =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : exact QA phrase -> native/visual/rare-token geometry -> iterative layer removal -> one Japanese insertion.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for pos, page_number in enumerate(pages, start=1):
        anchors = page_anchors[page_number]
        print(f"[page {page_number}] page {pos}/{len(pages)}", flush=True)
        page_detail = {"page": page_number, "anchors": [], "patched_residues": 0}
        for anchor in anchors:
            if not p45._shared_page_visible_defects(target_pdf, page_number).get("long_english_run"):
                break
            print(f"  residue: {anchor[:140]}", flush=True)
            detail = _repair_anchor(document_id, target_pdf, page_number, anchor, client, root)
            page_detail["anchors"].append(detail)
            if detail.get("status") == "patched":
                page_detail["patched_residues"] += 1
                print("  PATCHED", flush=True)
            else:
                print(f"  FAILED reason={detail.get('reason')}", flush=True)

        visible = p45._shared_page_visible_defects(target_pdf, page_number)
        page_detail["visible_after"] = visible
        if not any(visible.values()):
            accepted.append(page_number)
            print(f"  ACCEPTED: patched_residues={page_detail['patched_residues']}", flush=True)
        else:
            rejected.append(page_number)
            remaining = sum(len(v) for v in visible.values() if isinstance(v, list))
            print(f"  REJECTED: patched_residues={page_detail['patched_residues']} remaining_defects={remaining}", flush=True)
        manifest["pages"].append(page_detail)
        manifest["accepted_pages"] = accepted
        manifest["rejected_pages"] = rejected
        _write_json(root / "manifest.json", manifest)

    author_restoration = m.restore_primary_author_band(source_pdf, target_pdf)
    reference_restoration = m.restore_reference_section(source_pdf, target_pdf)
    m.build_alternating_dual(source_pdf, target_pdf, m._layout_dual_path(document_id))

    print("\nRunning final Postflight...", flush=True)
    _progress(root, status="running", stage="postflight", accepted_pages=accepted, rejected_pages=rejected)
    final_qa = m._run_layout_qa(
        document_id,
        source_pdf,
        target_pdf,
        author_restoration=author_restoration,
        reference_restoration=reference_restoration,
    )
    final_qa["phase53_repair"] = manifest
    _write_json(qa_path, final_qa)

    manifest["finished_at"] = _utc_now()
    manifest["final_quality_gate"] = final_qa.get("quality_gate")
    manifest["final_critical_count"] = final_qa.get("critical_count")
    manifest["final_high_count"] = final_qa.get("high_count")
    _write_json(root / "manifest.json", manifest)
    _progress(
        root,
        status="completed" if final_qa.get("quality_gate") == "pass" else "failed",
        stage="done",
        accepted_pages=accepted,
        rejected_pages=rejected,
        quality_gate=final_qa.get("quality_gate"),
        critical_count=final_qa.get("critical_count"),
        high_count=final_qa.get("high_count"),
    )

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    mono_out = downloads / "PeperTranslator_full_ja_PHASE53.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE53.pdf"
    qa_out = downloads / ("PeperTranslator_full_QA_PHASE53.json" if final_qa.get("quality_gate") == "pass" else "PeperTranslator_full_QA_PHASE53_FAILED.json")
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [item for item in (final_qa.get("warnings") or []) if isinstance(item, dict) and item.get("severity") in {"critical", "high"}]
    print("\n===== PHASE53 FINAL SUMMARY =====")
    print(f"QualityGate : {final_qa.get('quality_gate')}")
    print(f"Critical    : {final_qa.get('critical_count')}")
    print(f"High        : {final_qa.get('high_count')}")
    print(f"Selected    : {pages}")
    print(f"Repaired    : {accepted}")
    print(f"Rejected    : {rejected}")
    if severe:
        print("Remaining blocking warnings:")
        for item in severe[:18]:
            print(f"  p.{item.get('page')} {item.get('code')}: {item.get('message')}")
    print(f"MONO        : {mono_out}")
    print(f"DUAL        : {dual_out}")
    print(f"QA          : {qa_out}")
    return 0 if final_qa.get("quality_gate") == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Geometric exact QA residue repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

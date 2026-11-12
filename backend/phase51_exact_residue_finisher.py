from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m
from backend import phase43_region_finisher as p43
from backend import phase45_source_aligned_finisher as p45
from backend import phase46_line_window_finisher as p46
from backend import phase48_residual_container_finisher as p48
from backend import phase50_terminal_band_finisher as p50


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’.-]*")


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
    path = m._layout_dir(document_id) / "phase51_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 51, "updated_at": _utc_now(), **payload})


def _norm_token(value: str) -> str:
    return (value or "").replace("’", "'").lower().strip(".-")


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    return [(_norm_token(match.group(0)), match.start(), match.end()) for match in _TOKEN_RE.finditer(text or "")]


def _word_token_records(page: fitz.Page) -> list[dict]:
    """Return deduplicated Latin word tokens in rendered reading order.

    MuPDF can expose duplicate hidden text layers at nearly identical coordinates.
    Those duplicates made the earlier sequence/band repair miss the literal QA residue.
    Collapse only same-token, near-identical boxes; keep legitimate repeated words.
    """
    records: list[dict] = []
    for raw in page.get_text("words", sort=True):
        if len(raw) < 8:
            continue
        x0, y0, x1, y1, word, block_no, line_no, word_no = raw[:8]
        rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        for token, _start, _end in _token_spans(str(word)):
            if not token:
                continue
            candidate = {
                "token": token,
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                "block": int(block_no),
                "line": int(line_no),
                "word": int(word_no),
                "raw": str(word),
            }
            duplicate = False
            for existing in records[-8:]:
                if existing["token"] != token:
                    continue
                other = fitz.Rect(existing["bbox"])
                cx = abs(((other.x0 + other.x1) - (rect.x0 + rect.x1)) / 2.0)
                cy = abs(((other.y0 + other.y1) - (rect.y0 + rect.y1)) / 2.0)
                if cx <= 1.2 and cy <= 1.2:
                    duplicate = True
                    break
            if not duplicate:
                records.append(candidate)
    return records


def _find_residue_words(page: fitz.Page, anchor: str) -> tuple[list[dict] | None, dict]:
    anchor_tokens = [_norm_token(item) for item in _TOKEN_RE.findall(anchor or "")]
    anchor_tokens = [item for item in anchor_tokens if item]
    words = _word_token_records(page)
    if not anchor_tokens or not words:
        return None, {"reason": "anchor_tokens_missing", "anchor_tokens": anchor_tokens}

    values = [item["token"] for item in words]
    width = len(anchor_tokens)
    for start in range(0, len(values) - width + 1):
        if values[start:start + width] == anchor_tokens:
            matched = words[start:start + width]
            return matched, {
                "reason": "",
                "mode": "exact_word_sequence",
                "anchor_tokens": anchor_tokens,
                "matched_tokens": [item["token"] for item in matched],
            }

    # Final-residue anchors are sometimes clipped at the first glyph run (for
    # example ``ting`` from a longer ``...ting`` word).  Allow suffix matching only
    # on the first token; every later token must still match exactly.
    for start in range(0, len(values) - width + 1):
        window = values[start:start + width]
        if not window:
            continue
        first_ok = window[0] == anchor_tokens[0]
        if not first_ok and len(anchor_tokens[0]) <= 4 and len(window[0]) > len(anchor_tokens[0]):
            first_ok = window[0].endswith(anchor_tokens[0])
        if first_ok and window[1:] == anchor_tokens[1:]:
            matched = words[start:start + width]
            return matched, {
                "reason": "",
                "mode": "first_token_suffix_word_sequence",
                "anchor_tokens": anchor_tokens,
                "matched_tokens": [item["token"] for item in matched],
            }

    return None, {
        "reason": "target_residue_sequence_not_found",
        "anchor_tokens": anchor_tokens,
        "nearby": values[:80],
    }


def _rects_for_words(words: list[dict], page: fitz.Page) -> list[fitz.Rect]:
    grouped: dict[tuple[int, int], list[fitz.Rect]] = defaultdict(list)
    for item in words:
        grouped[(int(item["block"]), int(item["line"]))].append(fitz.Rect(item["bbox"]))
    rects: list[fitz.Rect] = []
    for _key, items in sorted(grouped.items(), key=lambda pair: min(rect.y0 for rect in pair[1])):
        rect = fitz.Rect(items[0])
        for item in items[1:]:
            rect |= item
        pad_x = 1.25
        pad_y = max(0.7, rect.height * 0.10)
        rects.append(fitz.Rect(
            max(page.rect.x0 + 0.5, rect.x0 - pad_x),
            max(page.rect.y0 + 0.5, rect.y0 - pad_y),
            min(page.rect.x1 - 0.5, rect.x1 + pad_x),
            min(page.rect.y1 - 0.5, rect.y1 + pad_y),
        ))
    return rects


def _source_context_lines(source_page: fitz.Page, target_seed: dict) -> tuple[list[dict], dict]:
    source_lines = p46._line_records(source_page)
    source_anchor, meta = p48._best_source_anchor(source_lines, target_seed, source_page.rect)
    if source_anchor is None:
        return [], meta
    column = p48._column_lines(source_lines, source_anchor, float(source_page.rect.width))
    if not column:
        return [source_anchor], meta
    try:
        idx = next(i for i, item in enumerate(column) if int(item["id"]) == int(source_anchor["id"]))
    except StopIteration:
        return [source_anchor], meta
    return column[max(0, idx - 1):min(len(column), idx + 2)], meta


def _focus_from_source(anchor: str, source_lines: list[dict]) -> tuple[str, dict]:
    """Recover the unclipped source phrase corresponding to the visible residue."""
    anchor_tokens = [_norm_token(item) for item in _TOKEN_RE.findall(anchor or "")]
    anchor_tokens = [item for item in anchor_tokens if item]
    context = " ".join(str(item.get("text") or "") for item in source_lines)
    spans = _token_spans(context)
    source_tokens = [item[0] for item in spans]
    if anchor_tokens and source_tokens and len(source_tokens) >= len(anchor_tokens):
        width = len(anchor_tokens)
        for start in range(0, len(source_tokens) - width + 1):
            window = source_tokens[start:start + width]
            first_ok = window[0] == anchor_tokens[0]
            clipped = False
            if not first_ok and len(anchor_tokens[0]) <= 4 and len(window[0]) > len(anchor_tokens[0]):
                first_ok = window[0].endswith(anchor_tokens[0])
                clipped = first_ok
            if first_ok and window[1:] == anchor_tokens[1:]:
                begin = spans[start][1]
                end = spans[start + width - 1][2]
                phrase = p45._prepare_source_text(context[begin:end])
                return phrase, {
                    "mode": "source_token_sequence",
                    "clipped_first_token_recovered": clipped,
                    "source_preview": re.sub(r"\s+", " ", phrase)[:240],
                }

    # The visible residue itself is still a faithful source fragment.  Remove only a
    # clearly clipped ``-ing`` tail when the complete source token could not be found.
    fallback = p45._prepare_source_text(anchor)
    first = _TOKEN_RE.match(fallback)
    clipped_removed = False
    if first:
        token = first.group(0)
        if len(token) <= 4 and token.lower().endswith("ing") and token.lower() not in {"ring", "sing", "wing", "king"}:
            fallback = fallback[first.end():].lstrip(" ,;:-")
            clipped_removed = True
    return fallback, {
        "mode": "anchor_fallback",
        "clipped_first_token_removed": clipped_removed,
        "source_preview": re.sub(r"\s+", " ", fallback)[:240],
    }


def _fit_exact_rect(rect: fitz.Rect, text: str, preferred: float) -> float | None:
    start = min(max(5.2, preferred), 9.0)
    size = start
    while size >= 4.2:
        probe = fitz.open()
        try:
            page = probe.new_page(width=max(5.0, rect.width), height=max(5.0, rect.height))
            result = page.insert_textbox(
                fitz.Rect(0, 0, rect.width, rect.height),
                text,
                fontsize=round(size, 2),
                fontname="japan",
                lineheight=1.0,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if result >= 0:
                return round(size, 2)
        finally:
            probe.close()
        size -= 0.2
    return None


def _page_burden(pdf_path: Path, page_number: int) -> tuple[int, int, int, int]:
    return p50._page_burden(pdf_path, page_number)


def _apply_exact_residue_patch(
    target_pdf: Path,
    page_number: int,
    matched_words: list[dict],
    translated: str,
) -> tuple[bool, dict]:
    before_text = m._extract_pdf_page_texts(target_pdf)[page_number - 1]
    before_science = p43._science_fingerprint(before_text)
    before_burden = _page_burden(target_pdf, page_number)

    doc = fitz.open(target_pdf)
    tmp = target_pdf.with_suffix(".phase51-candidate.tmp.pdf")
    try:
        page = doc[page_number - 1]
        rects = _rects_for_words(matched_words, page)
        if not rects:
            return False, {"reason": "no_residue_rects"}
        insertion = fitz.Rect(rects[0])
        for rect in rects[1:]:
            insertion |= rect
        # Give the replacement only a tiny extra vertical allowance.  Unlike
        # Phase50, never widen to the entire column and therefore never delete
        # neighboring formulas/measurements just to remove one English residue.
        insertion = fitz.Rect(
            insertion.x0,
            max(page.rect.y0 + 0.5, insertion.y0 - 0.8),
            insertion.x1,
            min(page.rect.y1 - 0.5, insertion.y1 + 0.8),
        )
        preferred = statistics.median(max(5.0, fitz.Rect(item["bbox"]).height * 0.78) for item in matched_words)
        fontsize = _fit_exact_rect(insertion, translated, preferred)
        if fontsize is None:
            return False, {
                "reason": "layout_fit_failed",
                "bbox": [insertion.x0, insertion.y0, insertion.x1, insertion.y1],
                "translation_preview": translated[:220],
            }

        for rect in rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
        inserted = page.insert_textbox(
            insertion,
            translated,
            fontsize=fontsize,
            fontname="japan",
            lineheight=1.0,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
            overlay=True,
        )
        if inserted < 0:
            return False, {"reason": "insert_failed"}
        doc.save(tmp, garbage=4, clean=True, deflate=True)
    finally:
        doc.close()

    after_text = m._extract_pdf_page_texts(tmp)[page_number - 1]
    after_science = p43._science_fingerprint(after_text)
    after_burden = _page_burden(tmp, page_number)
    if not p43._science_equal(before_science, after_science):
        tmp.unlink(missing_ok=True)
        return False, {"reason": "page_science_changed", "before_burden": before_burden, "after_burden": after_burden}
    if not after_burden < before_burden:
        tmp.unlink(missing_ok=True)
        return False, {"reason": "no_visible_improvement", "before_burden": before_burden, "after_burden": after_burden}
    tmp.replace(target_pdf)
    return True, {
        "reason": "",
        "rects": [[r.x0, r.y0, r.x1, r.y1] for r in rects],
        "insert_bbox": [insertion.x0, insertion.y0, insertion.x1, insertion.y1],
        "fontsize": fontsize,
        "before_burden": before_burden,
        "after_burden": after_burden,
    }


def _repair_anchor(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    anchor: str,
    client,
    root: Path,
    index: int,
    total: int,
) -> dict:
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    try:
        target_page = target_doc[page_number - 1]
        matched_words, match_meta = _find_residue_words(target_page, anchor)
        if not matched_words:
            return {"status": "failed", "reason": match_meta.get("reason"), "target_match": match_meta}

        # Use the rendered target line as a geometric hint only.  The actual repair
        # span is the exact word sequence above.
        seed, seed_meta = p50._best_target_seed(target_page, anchor)
        source_lines: list[dict] = []
        source_meta: dict = {"reason": "target_seed_missing"}
        if seed is not None:
            source_lines, source_meta = _source_context_lines(source_doc[page_number - 1], seed)
        focus, focus_meta = _focus_from_source(anchor, source_lines)
        if not focus:
            return {
                "status": "failed",
                "reason": "empty_focus",
                "target_match": match_meta,
                "source_anchor": source_meta,
                "focus": focus_meta,
            }
    finally:
        source_doc.close()
        target_doc.close()

    def on_progress(info: dict) -> None:
        payload = dict(info)
        payload.update({
            "status": "running",
            "page": page_number,
            "anchor": index,
            "anchors": total,
            "stage": str(info.get("stage") or "translating_residue"),
        })
        _progress(root, **payload)
        parts = [f"  residue {index}/{total}", str(info.get("stage") or "working")]
        if info.get("batch") is not None:
            parts.append(f"batch {info.get('batch')}/{info.get('batches')}")
        if info.get("attempt") is not None:
            parts.append(f"attempt {info.get('attempt')}/{info.get('max_attempts') or 2}")
        if info.get("reason"):
            parts.append(f"reason={info.get('reason')}")
        print(" | ".join(parts), flush=True)

    translated, rewrite_meta = p45._translate_source_region(
        document_id,
        focus,
        client,
        progress_callback=on_progress,
    )
    if translated is None:
        return {
            "status": "failed",
            "reason": rewrite_meta.get("reason", "translation_failed"),
            "target_match": match_meta,
            "target_seed": seed_meta,
            "source_anchor": source_meta,
            "focus": focus_meta,
            "rewrite": rewrite_meta,
        }

    ok, patch_meta = _apply_exact_residue_patch(target_pdf, page_number, matched_words, translated)
    return {
        "status": "patched" if ok else "failed",
        "reason": "" if ok else patch_meta.get("reason", "patch_failed"),
        "anchor": anchor,
        "target_match": match_meta,
        "target_seed": seed_meta,
        "source_anchor": source_meta,
        "focus": focus_meta,
        "rewrite": rewrite_meta,
        "translation_preview": re.sub(r"\s+", " ", translated)[:260],
        **patch_meta,
    }


def _baseline_pdf(document_id: str, target_pdf: Path) -> tuple[Path, str]:
    phase50_before = m._layout_dir(document_id) / "phase50_repair" / "translated-mono.before-phase50.pdf"
    if phase50_before.exists():
        return phase50_before, "phase50_before"
    return target_pdf, "current_target"


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

    source_baseline, baseline_mode = _baseline_pdf(document_id, target_pdf)
    backup_pdf = root / "translated-mono.before-phase51.pdf"
    backup_qa = root / "qa.before-phase51.json"
    if not backup_pdf.exists():
        shutil.copy2(source_baseline, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)
    shutil.copy2(backup_pdf, target_pdf)

    manifest: dict = {
        "phase": 51,
        "mode": "exact-qa-residue-word-span-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "baseline": str(backup_pdf),
        "baseline_mode": baseline_mode,
        "selected_pages": pages,
        "anchors": {str(page): page_anchors[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)
    _progress(root, status="starting", stage="starting", selected_pages=pages)

    print("===== PHASE51 EXACT QA RESIDUE SPAN REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : translate only the exact Postflight English residue and redact only its matched word boxes.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for page_pos, page_number in enumerate(pages, start=1):
        anchors = page_anchors[page_number]
        print(f"[page {page_number}] page {page_pos}/{len(pages)}", flush=True)
        page_detail = {"page": page_number, "anchors": [], "patched_residues": 0}
        for index, anchor in enumerate(anchors, start=1):
            current = p45._shared_page_visible_defects(target_pdf, page_number)
            if not current.get("long_english_run"):
                break
            _progress(root, status="running", stage="anchor_start", page=page_number, anchor=index, anchors=len(anchors))
            print(f"  residue {index}/{len(anchors)}: {anchor[:100]}", flush=True)
            detail = _repair_anchor(
                document_id,
                source_pdf,
                target_pdf,
                page_number,
                anchor,
                client,
                root,
                index,
                len(anchors),
            )
            page_detail["anchors"].append(detail)
            if detail.get("status") == "patched":
                page_detail["patched_residues"] += 1
                print("  PATCHED exact residue span", flush=True)
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
    final_qa["phase51_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE51.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE51.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE51.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE51_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE51 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Exact QA residue span repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

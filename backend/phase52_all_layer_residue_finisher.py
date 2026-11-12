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
from backend import phase50_terminal_band_finisher as p50
from backend import phase51_exact_residue_finisher as p51


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
    path = m._layout_dir(document_id) / "phase52_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 52, "updated_at": _utc_now(), **payload})


def _norm_token(value: str) -> str:
    return p51._norm_token(value)


def _anchor_tokens(anchor: str) -> list[str]:
    return [token for token in (_norm_token(x) for x in p51._TOKEN_RE.findall(anchor or "")) if token]


def _raw_word_records(page: fitz.Page) -> list[dict]:
    records: list[dict] = []
    for raw in page.get_text("words", sort=False):
        if len(raw) < 8:
            continue
        x0, y0, x1, y1, word, block_no, line_no, word_no = raw[:8]
        rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        for token, _start, _end in p51._token_spans(str(word)):
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


def _matches_anchor(window: list[str], tokens: list[str]) -> bool:
    if len(window) != len(tokens) or not tokens:
        return False
    first_ok = window[0] == tokens[0]
    if not first_ok and len(tokens[0]) <= 4 and len(window[0]) > len(tokens[0]):
        first_ok = window[0].endswith(tokens[0])
    return first_ok and window[1:] == tokens[1:]


def _all_layer_residue_matches(page: fitz.Page, anchor: str) -> tuple[list[list[dict]], dict]:
    """Find every text-layer occurrence of the QA residue.

    Phase51 deliberately deduplicated near-identical words before sequence matching.
    That was useful for locating a residue, but it meant only one copy of a duplicated
    hidden text layer could be redacted.  Here we retain raw layer/block identities and
    search each rendered block independently, returning every matching occurrence.
    """
    tokens = _anchor_tokens(anchor)
    records = _raw_word_records(page)
    if not tokens or not records:
        return [], {"reason": "anchor_tokens_missing", "anchor_tokens": tokens}

    by_block: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        by_block[int(record["block"])].append(record)

    matches: list[list[dict]] = []
    for _block_no, items in by_block.items():
        items.sort(key=lambda item: (int(item["line"]), int(item["word"]), float(item["bbox"][0])))
        values = [item["token"] for item in items]
        width = len(tokens)
        for start in range(0, len(values) - width + 1):
            if _matches_anchor(values[start:start + width], tokens):
                matches.append(items[start:start + width])

    # Some PDFs split one logical line into adjacent blocks.  If per-block search found
    # nothing, fall back to Phase51's rendered-order exact matcher for the primary copy.
    if not matches:
        primary, meta = p51._find_residue_words(page, anchor)
        if primary:
            matches = [primary]
            return matches, {"reason": "", "mode": "rendered_order_fallback", "copies": 1, **meta}
        return [], {"reason": "target_residue_sequence_not_found", "anchor_tokens": tokens}

    return matches, {
        "reason": "",
        "mode": "all_text_layers",
        "copies": len(matches),
        "anchor_tokens": tokens,
    }


def _rects_for_match(match: list[dict], page: fitz.Page) -> list[fitz.Rect]:
    grouped: dict[tuple[int, int], list[fitz.Rect]] = defaultdict(list)
    for item in match:
        grouped[(int(item["block"]), int(item["line"]))].append(fitz.Rect(item["bbox"]))
    out: list[fitz.Rect] = []
    for _key, items in sorted(grouped.items(), key=lambda pair: min(r.y0 for r in pair[1])):
        rect = fitz.Rect(items[0])
        for item in items[1:]:
            rect |= item
        pad_x = 1.5
        pad_y = max(0.9, rect.height * 0.12)
        out.append(fitz.Rect(
            max(page.rect.x0 + 0.5, rect.x0 - pad_x),
            max(page.rect.y0 + 0.5, rect.y0 - pad_y),
            min(page.rect.x1 - 0.5, rect.x1 + pad_x),
            min(page.rect.y1 - 0.5, rect.y1 + pad_y),
        ))
    return out


def _dedupe_rects(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    result: list[fitz.Rect] = []
    for rect in rects:
        duplicate = False
        for existing in result:
            ix0 = max(rect.x0, existing.x0)
            iy0 = max(rect.y0, existing.y0)
            ix1 = min(rect.x1, existing.x1)
            iy1 = min(rect.y1, existing.y1)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            smaller = max(1e-6, min(rect.get_area(), existing.get_area()))
            if inter / smaller >= 0.92:
                # Keep the larger box so all glyph runs of duplicate layers are covered.
                if rect.get_area() > existing.get_area():
                    existing.x0, existing.y0, existing.x1, existing.y1 = rect.x0, rect.y0, rect.x1, rect.y1
                duplicate = True
                break
        if not duplicate:
            result.append(fitz.Rect(rect))
    return result


def _compact_japanese(client, text: str, max_chars: int) -> str | None:
    """Ask for a shorter equivalent only when the normal translation cannot fit."""
    model = m._preferred_translation_model()
    prompt = (
        "次の日本語訳を、意味を変えず、情報を足さず、専門用語を保ったまま短くしてください。\n"
        f"目安は{max(8, max_chars)}文字以内です。説明・引用符・前置きは禁止。短い日本語本文だけ返してください。\n\n"
        f"日本語訳: {text}"
    )
    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        candidate = str(((response or {}).get("message") or {}).get("content") or "").strip()
    except Exception:
        return None
    candidate = re.sub(r"^```(?:text)?\s*|\s*```$", "", candidate, flags=re.I | re.S).strip()
    candidate = candidate.strip('"“”「」')
    if not candidate or m._japanese_char_count(candidate) < 2:
        return None
    if p43._has_defect(candidate):
        return None
    return candidate


def _fit_translation(rect: fitz.Rect, translated: str, preferred: float, client) -> tuple[str | None, float | None, dict]:
    fontsize = p51._fit_exact_rect(rect, translated, preferred)
    if fontsize is not None:
        return translated, fontsize, {"mode": "normal"}

    # Estimate a conservative Japanese character budget from the available area.
    base_size = min(max(4.0, preferred), 7.0)
    columns = max(8, int(rect.width / max(3.8, base_size)))
    lines = max(1, int(rect.height / max(4.4, base_size * 1.05)))
    max_chars = max(8, int(columns * lines * 0.9))
    compact = _compact_japanese(client, translated, max_chars)
    if compact:
        fontsize = p51._fit_exact_rect(rect, compact, preferred)
        if fontsize is not None:
            return compact, fontsize, {"mode": "compact", "max_chars": max_chars}

    # Terminal fallback: go slightly below Phase51's 4.2 pt floor, but never below
    # 3.4 pt.  This is only for the final one-line residue and avoids erasing adjacent
    # text merely to gain space.
    size = min(max(5.0, preferred), 8.0)
    while size >= 3.4:
        probe = fitz.open()
        try:
            page = probe.new_page(width=max(5.0, rect.width), height=max(5.0, rect.height))
            result = page.insert_textbox(
                fitz.Rect(0, 0, rect.width, rect.height),
                compact or translated,
                fontsize=round(size, 2),
                fontname="japan",
                lineheight=1.0,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if result >= 0:
                return compact or translated, round(size, 2), {
                    "mode": "small_font",
                    "compact": bool(compact),
                    "max_chars": max_chars,
                }
        finally:
            probe.close()
        size -= 0.2
    return None, None, {"mode": "failed", "max_chars": max_chars}


def _apply_all_layer_patch(
    target_pdf: Path,
    page_number: int,
    matches: list[list[dict]],
    translated: str,
    client,
) -> tuple[bool, dict]:
    before_text = m._extract_pdf_page_texts(target_pdf)[page_number - 1]
    before_science = p43._science_fingerprint(before_text)
    before_burden = p50._page_burden(target_pdf, page_number)

    doc = fitz.open(target_pdf)
    tmp = target_pdf.with_suffix(".phase52-candidate.tmp.pdf")
    try:
        page = doc[page_number - 1]
        all_rects: list[fitz.Rect] = []
        for match in matches:
            all_rects.extend(_rects_for_match(match, page))
        all_rects = _dedupe_rects(all_rects)
        if not all_rects:
            return False, {"reason": "no_residue_rects"}

        # Use the first visible occurrence as the insertion slot.  Every duplicate
        # layer is removed, but the Japanese replacement is inserted only once.
        primary = fitz.Rect(all_rects[0])
        # Include any near-coincident duplicate rect in the insertion envelope.
        for rect in all_rects[1:]:
            if abs(rect.y0 - primary.y0) <= max(2.5, primary.height * 0.4):
                primary |= rect
        insertion = fitz.Rect(
            primary.x0,
            max(page.rect.y0 + 0.5, primary.y0 - 1.0),
            primary.x1,
            min(page.rect.y1 - 0.5, primary.y1 + 1.0),
        )
        preferred = statistics.median(
            max(5.0, fitz.Rect(item["bbox"]).height * 0.78)
            for item in matches[0]
        )
        final_text, fontsize, fit_meta = _fit_translation(insertion, translated, preferred, client)
        if final_text is None or fontsize is None:
            return False, {
                "reason": "layout_fit_failed",
                "bbox": [insertion.x0, insertion.y0, insertion.x1, insertion.y1],
                "translation_preview": translated[:220],
                "fit": fit_meta,
            }

        for rect in all_rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
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

    after_text = m._extract_pdf_page_texts(tmp)[page_number - 1]
    after_science = p43._science_fingerprint(after_text)
    after_burden = p50._page_burden(tmp, page_number)
    if not p43._science_equal(before_science, after_science):
        tmp.unlink(missing_ok=True)
        return False, {"reason": "page_science_changed", "before_burden": before_burden, "after_burden": after_burden}
    if not after_burden < before_burden:
        tmp.unlink(missing_ok=True)
        return False, {
            "reason": "no_visible_improvement",
            "before_burden": before_burden,
            "after_burden": after_burden,
            "copies_redacted": len(matches),
        }
    tmp.replace(target_pdf)
    return True, {
        "reason": "",
        "copies_redacted": len(matches),
        "redact_rects": [[r.x0, r.y0, r.x1, r.y1] for r in all_rects],
        "insert_bbox": [insertion.x0, insertion.y0, insertion.x1, insertion.y1],
        "fontsize": fontsize,
        "fit": fit_meta,
        "before_burden": before_burden,
        "after_burden": after_burden,
    }


def _repair_anchor(document_id: str, source_pdf: Path, target_pdf: Path, page_number: int, anchor: str, client, root: Path) -> dict:
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    try:
        target_page = target_doc[page_number - 1]
        matches, match_meta = _all_layer_residue_matches(target_page, anchor)
        if not matches:
            return {"status": "failed", "reason": match_meta.get("reason"), "target_match": match_meta}
        seed, seed_meta = p50._best_target_seed(target_page, anchor)
        source_lines: list[dict] = []
        source_meta: dict = {"reason": "target_seed_missing"}
        if seed is not None:
            source_lines, source_meta = p51._source_context_lines(source_doc[page_number - 1], seed)
        focus, focus_meta = p51._focus_from_source(anchor, source_lines)
        if not focus:
            focus = p45._prepare_source_text(anchor)
            focus_meta = {"mode": "anchor_fallback", "source_preview": focus[:240]}
    finally:
        source_doc.close()
        target_doc.close()

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
        return {
            "status": "failed",
            "reason": rewrite_meta.get("reason", "translation_failed"),
            "target_match": match_meta,
            "target_seed": seed_meta,
            "source_anchor": source_meta,
            "focus": focus_meta,
            "rewrite": rewrite_meta,
        }

    ok, patch_meta = _apply_all_layer_patch(target_pdf, page_number, matches, translated, client)
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

    # Phase51 already repaired p.8 successfully.  Preserve the current PDF and touch
    # only pages still reported by current QA (normally only p.4).
    backup_pdf = root / "translated-mono.before-phase52.pdf"
    backup_qa = root / "qa.before-phase52.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)
    shutil.copy2(backup_pdf, target_pdf)

    manifest = {
        "phase": 52,
        "mode": "all-text-layer-exact-residue-eradication",
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

    print("===== PHASE52 ALL-LAYER EXACT RESIDUE REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : remove every duplicate text-layer copy of the exact QA residue; insert Japanese once.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for pos, page_number in enumerate(pages, start=1):
        anchors = page_anchors[page_number]
        print(f"[page {page_number}] page {pos}/{len(pages)}", flush=True)
        page_detail = {"page": page_number, "anchors": [], "patched_residues": 0}
        for anchor in anchors:
            current = p45._shared_page_visible_defects(target_pdf, page_number)
            if not current.get("long_english_run"):
                break
            print(f"  residue: {anchor[:120]}", flush=True)
            detail = _repair_anchor(document_id, source_pdf, target_pdf, page_number, anchor, client, root)
            page_detail["anchors"].append(detail)
            if detail.get("status") == "patched":
                page_detail["patched_residues"] += 1
                print(f"  PATCHED copies_redacted={detail.get('copies_redacted')}", flush=True)
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
    final_qa["phase52_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE52.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE52.pdf"
    qa_out = downloads / ("PeperTranslator_full_QA_PHASE52.json" if final_qa.get("quality_gate") == "pass" else "PeperTranslator_full_QA_PHASE52_FAILED.json")
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [item for item in (final_qa.get("warnings") or []) if isinstance(item, dict) and item.get("severity") in {"critical", "high"}]
    print("\n===== PHASE52 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="All-layer exact QA residue repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

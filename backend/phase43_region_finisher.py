from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m


VISIBLE_CODES = {
    "long_english_run",
    "short_english_artifact",
    "residual_english_prose",
    "bad_term",
    "scientific_surface_corruption",
}

FUNCTION_WORDS = {
    "by", "the", "of", "and", "to", "in", "for", "with", "from", "as", "at", "on",
    "is", "are", "was", "were", "be", "been", "being",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    path = m._layout_dir(document_id) / "phase43_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clean(text: str) -> str:
    value = (text or "").replace("\x00", " ")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _defects(text: str) -> dict[str, list[str]]:
    value = _clean(text)
    bad_terms = [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in value.lower()]
    return {
        "long_english_run": m._long_english_runs(value),
        "short_english_artifact": m._short_english_artifact_hits(value),
        "residual_english_prose": m._residual_english_prose_hits(value),
        "bad_term": bad_terms,
        "scientific_surface_corruption": m._scientific_surface_artifact_hits(value),
    }


def _has_defect(text: str) -> bool:
    return any(_defects(text).values())


def _region_needs_rewrite(text: str) -> bool:
    value = _clean(text)
    if _has_defect(value) or _orphan_function_word(value):
        return True
    words = [word.lower() for word in re.findall(r"\b[a-z]{2,}\b", value)]
    has_japanese = bool(re.search(r"[ぁ-んァ-ヶ一-龯]", value))
    if has_japanese and any(word in FUNCTION_WORDS for word in words):
        return True
    if has_japanese and len(words) >= 4:
        return True
    return len(words) >= 7


def _orphan_function_word(text: str) -> bool:
    token = re.sub(r"[^A-Za-z]", "", text or "").lower()
    return token in FUNCTION_WORDS and len((text or "").strip()) <= 12


def _extract_blocks(page: fitz.Page) -> list[dict]:
    payload = page.get_text("dict", sort=False)
    records: list[dict] = []
    for block_index, block in enumerate(payload.get("blocks", [])):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        sizes: list[float] = []
        for line_index, line in enumerate(block.get("lines", [])):
            parts: list[str] = []
            for span in line.get("spans", []):
                text = str(span.get("text") or "")
                if text:
                    parts.append(text)
                try:
                    size = float(span.get("size") or 0)
                except Exception:
                    size = 0
                if size > 0:
                    sizes.append(size)
            line_text = "".join(parts).strip()
            if line_text:
                lines.append(line_text)
        text = _clean("\n".join(lines))
        if not text:
            continue
        rect = fitz.Rect(block.get("bbox"))
        if rect.is_empty or rect.width < 1 or rect.height < 2:
            continue
        records.append({
            "id": len(records),
            "block_index": block_index,
            "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
            "text": text,
            "font_size": statistics.median(sizes) if sizes else 9.0,
            "defects": _defects(text),
        })
    return records


def _rect(record: dict) -> fitz.Rect:
    return fitz.Rect(record["bbox"])


def _vertical_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    return overlap / max(1.0, min(a.height, b.height))


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    return overlap / max(1.0, min(a.width, b.width))


def _horizontal_gap(a: fitz.Rect, b: fitz.Rect) -> float:
    if a.x1 < b.x0:
        return b.x0 - a.x1
    if b.x1 < a.x0:
        return a.x0 - b.x1
    return 0.0


def _vertical_gap(a: fitz.Rect, b: fitz.Rect) -> float:
    if a.y1 < b.y0:
        return b.y0 - a.y1
    if b.y1 < a.y0:
        return a.y0 - b.y1
    return 0.0


def _same_column(a: fitz.Rect, b: fitz.Rect, page_width: float) -> bool:
    if _horizontal_overlap(a, b) >= 0.18:
        return True
    ca = (a.x0 + a.x1) / 2
    cb = (b.x0 + b.x1) / 2
    return abs(ca - cb) <= page_width * 0.20


def _adjacent(a: dict, b: dict, page_width: float) -> bool:
    ra, rb = _rect(a), _rect(b)
    if _vertical_overlap(ra, rb) >= 0.35 and _horizontal_gap(ra, rb) <= 24:
        return True
    if _same_column(ra, rb, page_width) and _vertical_gap(ra, rb) <= 15:
        return True
    return False


def _ordered(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: (round(_rect(r).y0, 1), _rect(r).x0))


def _region_text(records: list[dict]) -> str:
    parts: list[str] = []
    for record in _ordered(records):
        text = _clean(record["text"])
        if text:
            parts.append(text)
    return _clean("\n".join(parts))


def _record_is_nonbody_metadata(record: dict, page: fitz.Page) -> bool:
    """Apply the same narrow metadata exemption used by final geometry-aware QA."""
    return m._fragment_is_nonbody_english_metadata(
        {
            "text": str(record.get("text") or ""),
            "bbox": record.get("bbox") or (0.0, 0.0, 0.0, 0.0),
            "dir": (1.0, 0.0),
        },
        page,
    )


def _candidate_components(page: fitz.Page) -> list[list[dict]]:
    records = _extract_blocks(page)
    if not records:
        return []
    page_width = float(page.rect.width)
    body_records = [record for record in records if not _record_is_nonbody_metadata(record, page)]
    marked: set[int] = set()

    # Direct block-level evidence. Keep publication/license/affiliation metadata out
    # of a repair component even when the same page contains a real body defect.
    for record in body_records:
        if any(record["defects"].values()):
            marked.add(record["id"])

    # A two-character orphan such as ``by`` often lives in its own tiny PDF block.
    # It is invisible to a Japanese-context detector until joined with its neighbor.
    for record in body_records:
        if not _orphan_function_word(record["text"]):
            continue
        neighbors = [other for other in body_records if other["id"] != record["id"] and _adjacent(record, other, page_width)]
        if any(re.search(r"[ぁ-んァ-ヶ一-龯]", other["text"]) for other in neighbors):
            marked.add(record["id"])
            for other in sorted(neighbors, key=lambda item: (_vertical_gap(_rect(record), _rect(item)), _horizontal_gap(_rect(record), _rect(item))))[:2]:
                marked.add(other["id"])

    # Long English debris can be split across multiple PDF blocks.  Scan small
    # visual windows so the page-level defect becomes attributable to a repair region.
    ordered = _ordered(body_records)
    for start in range(len(ordered)):
        window = [ordered[start]]
        for stop in range(start + 1, min(len(ordered), start + 5)):
            candidate = ordered[stop]
            if not _adjacent(window[-1], candidate, page_width):
                break
            window.append(candidate)
            text = _region_text(window)
            if _has_defect(text):
                marked.update(item["id"] for item in window)

    if not marked:
        return []

    # Merge marked blocks that belong to the same visual neighborhood.  This is the
    # root fix over Phase 42: repair the rendered region, not an arbitrary PDF block.
    remaining = {record["id"]: record for record in body_records if record["id"] in marked}
    components: list[list[dict]] = []
    while remaining:
        seed_id = next(iter(remaining))
        component = [remaining.pop(seed_id)]
        changed = True
        while changed:
            changed = False
            for rid, record in list(remaining.items()):
                if any(_adjacent(record, item, page_width) for item in component):
                    component.append(remaining.pop(rid))
                    changed = True
        components.append(_ordered(component))
    return components


def _science_fingerprint(text: str) -> dict:
    normalized = m._repair_scientific_surface_artifacts(_clean(text))
    return {
        "numbers": Counter(m._number_counter(normalized)),
        "measurements": Counter(m._measurement_tokens(normalized)),
        "dimensions": Counter(m._dimension_expressions(normalized)),
        "relations": set(m.formula_relation_tokens(normalized)),
    }


def _science_equal(before: dict, after: dict) -> bool:
    return (
        before["numbers"] == after["numbers"]
        and before["measurements"] == after["measurements"]
        and before["dimensions"] == after["dimensions"]
        and before["relations"] == after["relations"]
    )


def _rewrite_region(document_id: str, text: str, client) -> tuple[str | None, dict]:
    original = _clean(text)
    deterministic = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(original))
    if not _region_needs_rewrite(deterministic):
        return deterministic, {"mode": "deterministic", "attempts": 0}

    science_before = _science_fingerprint(deterministic)
    terms = m._guard_terms_for_document(document_id)
    protected, mapping = m.protect_translation_segment(deterministic, terms)
    model = m._preferred_translation_model()
    system = (
        m._load_translation_prompt(model)
        + "\n\nYou are repairing one bounded visual region of an already translated scientific PDF. "
        "Rewrite all prose in this region as natural Japanese without adding, deleting, or reversing meaning. "
        "The region may contain orphan English fragments created by PDF segmentation. Never leave standalone English "
        "function words such as by, the, of, and, to, in, for, with, or from in Japanese prose. Proper nouns, variable "
        "names, standard abbreviations, and journal/publisher names may remain Latin. Every __PTG_[A-Z]+__ token is "
        "immutable and must appear exactly once. Keep citations and equation references. Return only the repaired region."
    )
    last_reason = "model_output"
    last_preview = ""
    for attempt in range(6):
        extra = ""
        if attempt >= 3:
            extra = (
                "\n\nPrevious attempts left English debris. Be especially strict: translate or remove only the grammatical "
                "role of stray lowercase English function words while preserving all protected scientific tokens."
            )
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system + extra},
                {"role": "user", "content": protected},
            ],
            options={"temperature": 0},
        )
        output = m._ollama_message_content(response).strip()
        last_preview = re.sub(r"\s+", " ", output)[:260]
        if m._prompt_leak_hits(output):
            last_reason = "prompt_leak"
            continue
        restored, ok, problems = m.restore_translation_placeholders(output, mapping)
        if not ok:
            last_reason = "placeholder_integrity:" + ",".join(problems[:3])
            continue
        restored = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(restored))
        if m._simplified_chinese_hits(restored) or m._foreign_language_hits(restored):
            last_reason = "language_leak"
            continue
        if _region_needs_rewrite(restored):
            last_reason = "visible_defect_remains"
            continue
        if not _science_equal(science_before, _science_fingerprint(restored)):
            last_reason = "local_science_changed"
            continue
        if m._japanese_char_count(restored) < max(2, min(18, m._latin_char_count(original) // 28)):
            last_reason = "not_japanese_enough"
            continue
        return restored, {
            "mode": "qwen_region_rewrite",
            "attempts": attempt + 1,
            "protected": len(mapping),
            "source_preview": re.sub(r"\s+", " ", original)[:240],
            "target_preview": re.sub(r"\s+", " ", restored)[:240],
        }
    return None, {
        "mode": "qwen_region_rewrite",
        "attempts": 6,
        "protected": len(mapping),
        "reason": last_reason,
        "target_preview": last_preview,
    }


def _union_rect(records: list[dict]) -> fitz.Rect:
    rect = _rect(records[0])
    for record in records[1:]:
        rect |= _rect(record)
    return rect


def _safe_expand_rect(page: fitz.Page, rect: fitz.Rect, all_blocks: list[dict], region_ids: set[int]) -> fitz.Rect:
    result = fitz.Rect(rect)
    max_extra = max(12.0, rect.height * 0.45)
    bottom_limit = min(float(page.rect.y1) - 8, rect.y1 + max_extra)
    top_limit = max(float(page.rect.y0) + 8, rect.y0 - min(8.0, rect.height * 0.15))
    for block in all_blocks:
        if block["id"] in region_ids:
            continue
        other = _rect(block)
        if _horizontal_overlap(rect, other) < 0.15:
            continue
        if other.y0 >= rect.y1 and other.y0 < bottom_limit:
            bottom_limit = max(rect.y1, other.y0 - 1.5)
        if other.y1 <= rect.y0 and other.y1 > top_limit:
            top_limit = min(rect.y0, other.y1 + 1.5)
    return fitz.Rect(max(page.rect.x0 + 2, rect.x0 - 1), top_limit, min(page.rect.x1 - 2, rect.x1 + 1), bottom_limit)


def _fit_font(rect: fitz.Rect, text: str, preferred: float) -> float | None:
    width = max(4.0, rect.width)
    height = max(4.0, rect.height)
    start = max(6.0, min(10.5, preferred * 0.96))
    sizes: list[float] = []
    size = start
    while size >= 4.6:
        sizes.append(round(size, 2))
        size -= 0.3
    for fontsize in sizes:
        probe_doc = fitz.open()
        try:
            probe = probe_doc.new_page(width=width, height=height)
            result = probe.insert_textbox(
                fitz.Rect(0, 0, width, height),
                text,
                fontsize=fontsize,
                fontname="japan",
                lineheight=1.02,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if result >= 0:
                return fontsize
        finally:
            probe_doc.close()
    return None


def _page_visible_defects(page: fitz.Page) -> dict:
    """Mirror final QA's visual-fragment reading order for repair acceptance."""
    text = _clean(page.get_text("text", sort=True))
    long_hits: list[str] = []
    short_hits: list[str] = []
    residual_hits: list[str] = []
    for fragment in m._pdf_visual_fragments(page):
        if not m._fragment_is_nonbody_english_metadata(fragment, page):
            for hit in m._long_english_runs(fragment.get("text") or ""):
                if hit not in long_hits:
                    long_hits.append(hit)
        if m._fragment_is_horizontal(fragment):
            for hit in m._short_english_artifact_hits(fragment.get("text") or ""):
                if hit not in short_hits:
                    short_hits.append(hit)
            for hit in m._residual_english_prose_hits(fragment.get("text") or ""):
                if hit not in residual_hits:
                    residual_hits.append(hit)
    return {
        "long_english_run": long_hits[:8],
        "short_english_artifact": short_hits[:12],
        "residual_english_prose": residual_hits[:12],
        "bad_term": [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in text.lower()],
        "scientific_surface_corruption": m._scientific_surface_artifact_hits(text),
    }


def _patch_page(document_id: str, pdf_path: Path, page_number: int, client) -> dict:
    doc = fitz.open(pdf_path)
    tmp: Path | None = None
    try:
        page = doc[page_number - 1]
        all_blocks = _extract_blocks(page)
        components = _candidate_components(page)
        result = {
            "page": page_number,
            "candidate_regions": len(components),
            "patched_regions": 0,
            "failed_regions": [],
            "regions": [],
        }
        if not components:
            result["visible_after"] = _page_visible_defects(page)
            return result

        patches: list[dict] = []
        for index, component in enumerate(components):
            source_text = _region_text(component)
            rewritten, meta = _rewrite_region(document_id, source_text, client)
            region = {
                "index": index,
                "source_text": source_text,
                "block_ids": [item["id"] for item in component],
                "rewrite": meta,
            }
            if rewritten is None:
                region["status"] = "rewrite_failed"
                result["failed_regions"].append(region)
                result["regions"].append(region)
                continue
            base = _union_rect(component)
            expanded = _safe_expand_rect(page, base, all_blocks, set(region["block_ids"]))
            preferred = statistics.median(float(item["font_size"]) for item in component)
            fontsize = _fit_font(base, rewritten, preferred)
            use_rect = base
            if fontsize is None:
                fontsize = _fit_font(expanded, rewritten, preferred)
                use_rect = expanded
            if fontsize is None:
                region["status"] = "layout_fit_failed"
                region["bbox"] = [base.x0, base.y0, base.x1, base.y1]
                result["failed_regions"].append(region)
                result["regions"].append(region)
                continue
            region.update({
                "status": "ready",
                "bbox": [use_rect.x0, use_rect.y0, use_rect.x1, use_rect.y1],
                "fontsize": fontsize,
                "text": rewritten,
            })
            patches.append(region)
            result["regions"].append(region)

        if patches:
            for patch in patches:
                page.add_redact_annot(fitz.Rect(patch["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            for patch in patches:
                insert_result = page.insert_textbox(
                    fitz.Rect(patch["bbox"]),
                    patch["text"],
                    fontsize=patch["fontsize"],
                    fontname="japan",
                    lineheight=1.02,
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                    overlay=True,
                )
                if insert_result < 0:
                    raise RuntimeError(f"page {page_number} region {patch['index']} failed after fit probe")
                patch["status"] = "patched"
                result["patched_regions"] += 1

            tmp = pdf_path.with_suffix(".phase43.tmp.pdf")
            doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()
    if tmp is not None and tmp.exists():
        tmp.replace(pdf_path)

    check_doc = fitz.open(pdf_path)
    try:
        result["visible_after"] = _page_visible_defects(check_doc[page_number - 1])
    finally:
        check_doc.close()
    return result


def _selected_pages(qa: dict, target_pdf: Path, source_pdf: Path) -> tuple[list[int], dict[int, list[str]]]:
    source_pages = m._extract_pdf_page_texts(source_pdf)
    ref_page = m._reference_start_page_from_pdf(source_pdf)
    body_end = (ref_page - 1) if ref_page else len(source_pages)
    reasons: dict[int, set[str]] = {}
    for item in qa.get("warnings") or []:
        if not isinstance(item, dict):
            continue
        page = item.get("page")
        code = str(item.get("code") or "")
        severity = str(item.get("severity") or "")
        if isinstance(page, int) and 1 <= page <= body_end and severity in {"critical", "high"} and code in VISIBLE_CODES:
            reasons.setdefault(page, set()).add(code)

    target_pages = m._extract_pdf_page_texts(target_pdf)
    long_pages = m._pdf_long_english_run_hits_by_page(target_pdf)
    short_pages = m._pdf_short_english_artifact_hits_by_page(target_pdf)
    residual_pages = m._pdf_residual_english_prose_hits_by_page(target_pdf)
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(target_pdf)
    for page in range(1, min(body_end, len(target_pages)) + 1):
        text = target_pages[page - 1]
        if page - 1 < len(long_pages) and long_pages[page - 1]:
            reasons.setdefault(page, set()).add("long_english_run")
        if page - 1 < len(short_pages) and short_pages[page - 1]:
            reasons.setdefault(page, set()).add("short_english_artifact")
        if page - 1 < len(residual_pages) and residual_pages[page - 1]:
            reasons.setdefault(page, set()).add("residual_english_prose")
        if any(bad.lower() in text.lower() for bad, _ in m._LAYOUT_BAD_TERMS):
            reasons.setdefault(page, set()).add("bad_term")
        if page - 1 < len(surface_pages) and surface_pages[page - 1]:
            reasons.setdefault(page, set()).add("scientific_surface_corruption")
    return sorted(reasons), {page: sorted(values) for page, values in reasons.items()}


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("Phase 42 translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase43.pdf"
    backup_qa = root / "qa.before-phase43.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = _selected_pages(source_qa, target_pdf, source_pdf)
    manifest: dict = {
        "phase": 43,
        "mode": "visual-region-fragment-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "selected_pages": pages,
        "reasons": {str(page): reasons[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)

    print("===== PHASE43 VISUAL REGION REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : current Phase 42 PDF; repair only visual regions containing split/orphan debris.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for page_number in pages:
        print(f"[page {page_number}] {', '.join(reasons[page_number])}", flush=True)
        detail = _patch_page(document_id, target_pdf, page_number, client)
        visible_after = detail.get("visible_after") or {}
        page_ok = not any(visible_after.values()) and not detail.get("failed_regions")
        if page_ok:
            accepted.append(page_number)
            print(f"  ACCEPTED: patched_regions={detail['patched_regions']}", flush=True)
        else:
            rejected.append(page_number)
            print(
                f"  REJECTED: patched_regions={detail['patched_regions']} failed_regions={len(detail.get('failed_regions') or [])}",
                flush=True,
            )
        manifest["pages"].append(detail)
        manifest["accepted_pages"] = accepted
        manifest["rejected_pages"] = rejected
        _write_json(root / "manifest.json", manifest)

    author_restoration = m.restore_primary_author_band(source_pdf, target_pdf)
    reference_restoration = m.restore_reference_section(source_pdf, target_pdf)
    m.build_alternating_dual(source_pdf, target_pdf, m._layout_dual_path(document_id))

    print("\nRunning final Postflight...", flush=True)
    final_qa = m._run_layout_qa(
        document_id,
        source_pdf,
        target_pdf,
        author_restoration=author_restoration,
        reference_restoration=reference_restoration,
    )
    final_qa["phase43_repair"] = manifest
    _write_json(qa_path, final_qa)

    manifest["finished_at"] = _utc_now()
    manifest["final_quality_gate"] = final_qa.get("quality_gate")
    manifest["final_critical_count"] = final_qa.get("critical_count")
    manifest["final_high_count"] = final_qa.get("high_count")
    _write_json(root / "manifest.json", manifest)

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    mono_out = downloads / "PeperTranslator_full_ja_PHASE43.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE43.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE43.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE43_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE43 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Repair split/orphan visible text regions in the current PaperTranslator artifact")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

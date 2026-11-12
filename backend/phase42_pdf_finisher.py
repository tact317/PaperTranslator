from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m


VISIBLE_BLOCKING_CODES = {
    "long_english_run",
    "short_english_artifact",
    "bad_term",
    "scientific_surface_corruption",
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
    path = m._layout_dir(document_id) / "phase42_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clean_pdf_text(text: str) -> str:
    value = (text or "").replace("\x00", " ")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _block_defects(text: str) -> dict[str, list[str]]:
    value = _clean_pdf_text(text)
    bad_terms = [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in value.lower()]
    return {
        "long_english_run": m._long_english_runs(value),
        "short_english_artifact": m._short_english_artifact_hits(value),
        "bad_term": bad_terms,
        "scientific_surface_corruption": m._scientific_surface_artifact_hits(value),
    }


def _has_blocking_defect(text: str) -> bool:
    return any(_block_defects(text).values())


def _extract_text_blocks(page: fitz.Page) -> list[dict]:
    payload = page.get_text("dict", sort=False)
    records: list[dict] = []
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        sizes: list[float] = []
        for line in block.get("lines", []):
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
        text = _clean_pdf_text("\n".join(lines))
        if not text:
            continue
        rect = fitz.Rect(block.get("bbox"))
        if rect.is_empty or rect.width < 8 or rect.height < 4:
            continue
        records.append({
            "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
            "text": text,
            "font_size": statistics.median(sizes) if sizes else 9.0,
            "defects": _block_defects(text),
        })
    return records


def _rewrite_mixed_block(document_id: str, text: str, client=None) -> tuple[str | None, dict]:
    """Rewrite one already-translated PDF text block, never a whole page.

    Scientific literals and formulas are hidden behind opaque placeholders before
    Qwen sees the block.  This finisher is deliberately bounded: it is only called
    for blocks with a visible English/surface defect in the existing Phase 41 PDF.
    """
    original = _clean_pdf_text(text)
    deterministic = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(original))
    if not _has_blocking_defect(deterministic):
        return deterministic, {"mode": "deterministic", "attempts": 0, "mapping": 0}

    terms = m._guard_terms_for_document(document_id)
    protected, mapping = m.protect_translation_segment(deterministic, terms)
    if client is None:
        client = m.ollama.Client(host=m.OLLAMA_HOST)
    model = m._preferred_translation_model()
    system = (
        m._load_translation_prompt(model)
        + "\n\nYou are a final PDF block finisher. The input is a partially translated scientific-paper "
        "text block containing Japanese and English debris. Rewrite the whole block as natural Japanese "
        "without adding or deleting meaning. Proper nouns, variable names and standard abbreviations may "
        "remain Latin. Every __PTG_[A-Z]+__ token is immutable and must appear exactly once. "
        "Return only the rewritten block, with no commentary."
    )
    last_reason = "model_output"
    last_preview = ""
    for attempt in range(4):
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": protected},
            ],
            options={"temperature": 0},
        )
        output = m._ollama_message_content(response).strip()
        last_preview = re.sub(r"\s+", " ", output)[:220]
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
        defects = _block_defects(restored)
        if any(defects.values()):
            last_reason = "visible_defect_remains"
            continue
        if m._japanese_char_count(restored) < max(2, min(16, m._latin_char_count(original) // 24)):
            last_reason = "not_japanese_enough"
            continue
        return restored, {
            "mode": "qwen_block_rewrite",
            "attempts": attempt + 1,
            "mapping": len(mapping),
            "source_preview": re.sub(r"\s+", " ", original)[:220],
            "target_preview": re.sub(r"\s+", " ", restored)[:220],
        }
    return None, {
        "mode": "qwen_block_rewrite",
        "attempts": 4,
        "mapping": len(mapping),
        "reason": last_reason,
        "target_preview": last_preview,
    }


def _fit_textbox_size(rect: fitz.Rect, text: str, preferred: float) -> float | None:
    width = max(4.0, rect.width)
    height = max(4.0, rect.height)
    probe_doc = fitz.open()
    try:
        probe = probe_doc.new_page(width=width, height=height)
        probe_rect = fitz.Rect(0, 0, width, height)
        start = max(6.0, min(10.0, preferred * 0.96))
        candidates = []
        size = start
        while size >= 5.4:
            candidates.append(round(size, 2))
            size -= 0.35
        for fontsize in candidates:
            result = probe.insert_textbox(
                probe_rect,
                text,
                fontsize=fontsize,
                fontname="japan",
                lineheight=1.08,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            # Each probe attempt leaves text behind. Create a fresh page for the next
            # size so the return value is not affected by prior insertions.
            if result >= 0:
                return fontsize
            probe_doc.delete_page(-1)
            probe = probe_doc.new_page(width=width, height=height)
            probe_rect = fitz.Rect(0, 0, width, height)
    finally:
        probe_doc.close()
    return None


def _patch_page_blocks(document_id: str, pdf_path: Path, page_number: int, client=None) -> dict:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number - 1]
        records = [record for record in _extract_text_blocks(page) if any(record["defects"].values())]
        result: dict = {
            "page": page_number,
            "candidate_blocks": len(records),
            "patched_blocks": 0,
            "failed_blocks": [],
            "blocks": [],
        }
        if not records:
            return result

        patches: list[dict] = []
        for index, record in enumerate(records):
            rewritten, meta = _rewrite_mixed_block(document_id, record["text"], client=client)
            item = {"index": index, "bbox": record["bbox"], "defects": record["defects"], "rewrite": meta}
            if rewritten is None:
                item["status"] = "rewrite_failed"
                result["failed_blocks"].append(item)
                result["blocks"].append(item)
                continue
            rect = fitz.Rect(record["bbox"])
            fontsize = _fit_textbox_size(rect, rewritten, float(record["font_size"]))
            if fontsize is None:
                item["status"] = "layout_fit_failed"
                result["failed_blocks"].append(item)
                result["blocks"].append(item)
                continue
            item.update({"status": "ready", "fontsize": fontsize, "text": rewritten})
            patches.append(item)
            result["blocks"].append(item)

        if not patches:
            return result

        # Redact all selected text blocks in one pass so later redactions cannot erase
        # text inserted by an earlier patch. Keep images and vector graphics untouched.
        for item in patches:
            page.add_redact_annot(fitz.Rect(item["bbox"]), fill=(1, 1, 1))
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
        for item in patches:
            rect = fitz.Rect(item["bbox"])
            insert_result = page.insert_textbox(
                rect,
                item["text"],
                fontsize=item["fontsize"],
                fontname="japan",
                lineheight=1.08,
                color=(0, 0, 0),
                align=fitz.TEXT_ALIGN_LEFT,
                overlay=True,
            )
            if insert_result < 0:
                raise RuntimeError(f"page {page_number} block {item['index']} unexpectedly failed to fit")
            item["status"] = "patched"
            result["patched_blocks"] += 1

        tmp = pdf_path.with_suffix(".phase42.tmp.pdf")
        doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()
    if 'tmp' in locals() and tmp.exists():
        tmp.replace(pdf_path)
    return result


def _page_validation(document_id: str, page_number: int, source_pdf: Path, target_pdf: Path, root: Path) -> dict:
    source_page = root / f"page-{page_number}-source.pdf"
    target_page = root / f"page-{page_number}-target.pdf"
    m._write_single_page_pdf(source_pdf, source_page, page_number)
    m._write_single_page_pdf(target_pdf, target_page, page_number)
    source_text = m._extract_pdf_page_texts(source_page)[0]
    target_text = m._extract_pdf_page_texts(target_page)[0]
    source_measurements = m._pdf_measurement_tokens_by_page(source_page)[0]
    target_measurements = m._pdf_measurement_tokens_by_page(target_page)[0]
    source_dimensions = m._pdf_dimension_tokens_by_page(source_page)[0]
    target_dimensions = m._pdf_dimension_tokens_by_page(target_page)[0]
    numeric = m._preflight_scientific_numeric_details(
        source_text,
        target_text,
        source_measurements=source_measurements,
        target_measurements=target_measurements,
        source_dimensions=source_dimensions,
        target_dimensions=target_dimensions,
    )
    numeric_gate = m._scientific_numeric_gate_decision(numeric, guard_clean=True)
    source_rel = set(m.formula_relation_tokens(source_text))
    target_rel = set(m.formula_relation_tokens(m._repair_scientific_surface_artifacts(target_text)))
    formula = m._formula_relation_gate_decision(source_rel, target_rel, guard_clean=True)
    visible = {
        "long_english_runs": m._long_english_runs(target_text),
        "short_english_artifacts": m._short_english_artifact_hits(target_text),
        "bad_terms": [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in target_text.lower()],
        "surface_artifacts": m._pdf_scientific_surface_artifact_hits_by_page(target_page)[0],
    }
    ok = bool(
        numeric_gate.get("hard_ok")
        and not numeric_gate.get("conflicting_measurements")
        and not numeric_gate.get("conflicting_dimensions")
        and not formula.get("conflicting")
        and not any(visible.values())
    )
    return {
        "ok": ok,
        "numeric_gate": numeric_gate,
        "formula_gate": formula,
        "visible": visible,
        "source_measurements": numeric.get("source_measurements", []),
        "target_measurements": numeric.get("target_measurements", []),
        "source_dimensions": numeric.get("source_dimensions", []),
        "target_dimensions": numeric.get("target_dimensions", []),
    }


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
        if isinstance(page, int) and 1 <= page <= body_end and severity in {"critical", "high"} and code in VISIBLE_BLOCKING_CODES:
            reasons.setdefault(page, set()).add(code)

    target_pages = m._extract_pdf_page_texts(target_pdf)
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(target_pdf)
    for page in range(1, min(body_end, len(target_pages)) + 1):
        text = target_pages[page - 1]
        if m._long_english_runs(text):
            reasons.setdefault(page, set()).add("long_english_run")
        if m._short_english_artifact_hits(text):
            reasons.setdefault(page, set()).add("short_english_artifact")
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
        raise RuntimeError("Phase 41 translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase42.pdf"
    backup_qa = root / "qa.before-phase42.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Deterministic rerun from the same Phase 41 artifact.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = _selected_pages(source_qa, target_pdf, source_pdf)
    manifest: dict = {
        "phase": 42,
        "mode": "bounded-pdf-block-finisher",
        "started_at": _utc_now(),
        "document_id": document_id,
        "selected_pages": pages,
        "reasons": {str(p): reasons[p] for p in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)

    print("===== PHASE42 BOUNDED PDF FINISHER =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : existing Phase 41 PDF; only defective text blocks are rewritten.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for page in pages:
        print(f"[page {page}] {', '.join(reasons[page])}", flush=True)
        detail = _patch_page_blocks(document_id, target_pdf, page, client=client)
        validation = _page_validation(document_id, page, source_pdf, target_pdf, root)
        detail["validation"] = validation
        if validation["ok"]:
            accepted.append(page)
            print(f"  ACCEPTED: patched_blocks={detail['patched_blocks']}", flush=True)
        else:
            rejected.append(page)
            print(f"  REJECTED: visible/science validation remains", flush=True)
        manifest["pages"].append(detail)
        manifest["accepted_pages"] = accepted
        manifest["rejected_pages"] = rejected
        _write_json(root / "manifest.json", manifest)

    # Pages with no visible defect may still have historical Guard attribution.  Do
    # not mark them repaired here; Phase 42 only certifies pages it actually validated.
    # The postflight relation gate itself now distinguishes a real contradictory
    # relation from a PDF-text-layer miss.
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
    final_qa["phase42_repair"] = manifest
    final_qa["author_restoration"] = author_restoration
    final_qa["reference_restoration"] = reference_restoration
    _write_json(qa_path, final_qa)

    manifest["finished_at"] = _utc_now()
    manifest["final_quality_gate"] = final_qa.get("quality_gate")
    manifest["final_critical_count"] = final_qa.get("critical_count")
    manifest["final_high_count"] = final_qa.get("high_count")
    _write_json(root / "manifest.json", manifest)

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    mono_out = downloads / "PeperTranslator_full_ja_PHASE42.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE42.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE42.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE42_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE42 FINAL SUMMARY =====")
    print(f"QualityGate : {final_qa.get('quality_gate')}")
    print(f"Critical    : {final_qa.get('critical_count')}")
    print(f"High        : {final_qa.get('high_count')}")
    print(f"Selected    : {pages}")
    print(f"Repaired    : {accepted}")
    print(f"Rejected    : {rejected}")
    if severe:
        print("Remaining blocking warnings:")
        for item in severe[:16]:
            print(f"  p.{item.get('page')} {item.get('code')}: {item.get('message')}")
    print(f"MONO        : {mono_out}")
    print(f"DUAL        : {dual_out}")
    print(f"QA          : {qa_out}")
    return 0 if final_qa.get("quality_gate") == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Finish the current PaperTranslator artifact by rewriting only visibly defective PDF text blocks")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

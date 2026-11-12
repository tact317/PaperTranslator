from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m
from backend import phase43_region_finisher as p43


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
    path = m._layout_dir(document_id) / "phase44_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _phase43_clean_baseline(document_id: str) -> Path | None:
    """Return the PDF from before Phase 43 partial page edits when available."""
    candidate = m._layout_dir(document_id) / "phase43_repair" / "translated-mono.before-phase43.pdf"
    return candidate if candidate.exists() else None


def _progress(root: Path, **payload) -> None:
    data = {"phase": 44, "updated_at": _utc_now(), **payload}
    _write_json(root / "progress.json", data)


def _rewrite_region(document_id: str, text: str, client, progress_callback=None) -> tuple[str | None, dict]:
    original = p43._clean(text)
    deterministic = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(original))
    if not p43._region_needs_rewrite(deterministic):
        return deterministic, {
            "mode": "deterministic",
            "attempts": 0,
            "model_saw_protected_tokens": False,
        }

    science_before = p43._science_fingerprint(deterministic)
    terms = m._guard_terms_for_document(document_id)
    protected, mapping = m.protect_translation_segment(deterministic, terms)
    model = m._preferred_translation_model()
    system = m._load_translation_prompt(model)

    restored, _protected_output, ok, rescue = m._translate_repair_last_mile(
        client,
        model,
        system,
        protected,
        mapping,
        progress_callback=progress_callback,
    )
    meta = {
        "mode": "placeholder_free_prose_slots",
        **(rescue or {}),
        "protected": len(mapping),
        "model_saw_protected_tokens": False,
        "source_preview": re.sub(r"\s+", " ", original)[:240],
    }
    if not ok:
        return None, meta

    restored = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(restored))
    meta["target_preview"] = re.sub(r"\s+", " ", restored)[:240]
    if m._simplified_chinese_hits(restored) or m._foreign_language_hits(restored):
        meta["reason"] = "language_leak"
        return None, meta
    if p43._has_defect(restored):
        meta["reason"] = "visible_defect_remains"
        return None, meta
    if not p43._science_equal(science_before, p43._science_fingerprint(restored)):
        meta["reason"] = "local_science_changed"
        return None, meta
    if m._japanese_char_count(restored) < max(2, min(18, m._latin_char_count(original) // 28)):
        meta["reason"] = "not_japanese_enough"
        return None, meta
    return restored, meta


def _patch_page(document_id: str, pdf_path: Path, page_number: int, client, root: Path) -> dict:
    doc = fitz.open(pdf_path)
    tmp: Path | None = None
    try:
        page = doc[page_number - 1]
        all_blocks = p43._extract_blocks(page)
        components = p43._candidate_components(page)
        result = {
            "page": page_number,
            "candidate_regions": len(components),
            "patched_regions": 0,
            "failed_regions": [],
            "regions": [],
        }
        if not components:
            result["visible_after"] = p43._page_visible_defects(page)
            return result

        patches: list[dict] = []
        total_regions = len(components)
        for index, component in enumerate(components):
            region_no = index + 1
            print(f"  region {region_no}/{total_regions}: preparing", flush=True)
            _progress(
                root,
                status="running",
                page=page_number,
                region=region_no,
                regions=total_regions,
                stage="preparing",
            )

            def on_progress(info: dict) -> None:
                stage = str(info.get("stage") or "working")
                batch = info.get("batch")
                batches = info.get("batches")
                attempt = info.get("attempt")
                max_attempts = info.get("max_attempts")
                fragments = info.get("fragments")
                parts = [f"  region {region_no}/{total_regions}", stage]
                if batch is not None and batches is not None:
                    parts.append(f"batch {batch}/{batches}")
                if attempt is not None:
                    parts.append(f"attempt {attempt}/{max_attempts or 4}")
                if fragments is not None:
                    parts.append(f"fragments={fragments}")
                if info.get("reason"):
                    parts.append(f"reason={info['reason']}")
                print(" | ".join(parts), flush=True)
                _progress(
                    root,
                    status="running",
                    page=page_number,
                    region=region_no,
                    regions=total_regions,
                    **info,
                )

            source_text = p43._region_text(component)
            rewritten, meta = _rewrite_region(document_id, source_text, client, progress_callback=on_progress)
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
                print(f"  region {region_no}/{total_regions}: REWRITE FAILED ({meta.get('reason')})", flush=True)
                continue

            base = p43._union_rect(component)
            expanded = p43._safe_expand_rect(page, base, all_blocks, set(region["block_ids"]))
            preferred = statistics.median(float(item["font_size"]) for item in component)
            fontsize = p43._fit_font(base, rewritten, preferred)
            use_rect = base
            if fontsize is None:
                fontsize = p43._fit_font(expanded, rewritten, preferred)
                use_rect = expanded
            if fontsize is None:
                region["status"] = "layout_fit_failed"
                region["bbox"] = [base.x0, base.y0, base.x1, base.y1]
                result["failed_regions"].append(region)
                result["regions"].append(region)
                print(f"  region {region_no}/{total_regions}: LAYOUT FIT FAILED", flush=True)
                continue

            region.update({
                "status": "ready",
                "bbox": [use_rect.x0, use_rect.y0, use_rect.x1, use_rect.y1],
                "fontsize": fontsize,
                "text": rewritten,
            })
            patches.append(region)
            result["regions"].append(region)
            print(f"  region {region_no}/{total_regions}: ready", flush=True)

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
            tmp = pdf_path.with_suffix(".phase44.tmp.pdf")
            doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()

    if tmp is not None and tmp.exists():
        tmp.replace(pdf_path)

    check_doc = fitz.open(pdf_path)
    try:
        result["visible_after"] = p43._page_visible_defects(check_doc[page_number - 1])
    finally:
        check_doc.close()
    return result


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase44.pdf"
    backup_qa = root / "qa.before-phase44.json"
    baseline = _phase43_clean_baseline(document_id) or target_pdf
    if not backup_pdf.exists():
        shutil.copy2(baseline, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Always restart Phase 44 from the clean pre-Phase43 artifact. Phase 43 could
    # patch one region on a page and later reject the page, so its current PDF is
    # not a safe repair baseline.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = p43._selected_pages(source_qa, target_pdf, source_pdf)

    manifest: dict = {
        "phase": 44,
        "mode": "placeholder-free-prose-slot-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "baseline": str(baseline),
        "selected_pages": pages,
        "reasons": {str(page): reasons[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)
    _progress(root, status="starting", selected_pages=pages)

    print("===== PHASE44 PLACEHOLDER-FREE FRAGMENT REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : Qwen receives prose slots only; Python owns every scientific token.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    total_pages = len(pages)
    for page_pos, page_number in enumerate(pages, start=1):
        print(f"[page {page_number}] page {page_pos}/{total_pages} | {', '.join(reasons[page_number])}", flush=True)
        _progress(
            root,
            status="running",
            page=page_number,
            page_index=page_pos,
            pages=total_pages,
            stage="page_start",
        )
        detail = _patch_page(document_id, target_pdf, page_number, client, root)
        visible_after = detail.get("visible_after") or {}
        page_ok = not any(visible_after.values()) and not detail.get("failed_regions")
        if page_ok:
            accepted.append(page_number)
            print(f"  ACCEPTED: patched_regions={detail['patched_regions']}", flush=True)
        else:
            rejected.append(page_number)
            print(
                f"  REJECTED: patched_regions={detail['patched_regions']} "
                f"failed_regions={len(detail.get('failed_regions') or [])}",
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
    _progress(root, status="running", stage="postflight", accepted_pages=accepted, rejected_pages=rejected)
    final_qa = m._run_layout_qa(
        document_id,
        source_pdf,
        target_pdf,
        author_restoration=author_restoration,
        reference_restoration=reference_restoration,
    )
    final_qa["phase44_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE44.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE44.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE44.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE44_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE44 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Finish current PaperTranslator PDF without exposing protected tokens to Qwen")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

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
from backend import phase45_source_aligned_finisher as p45
from backend import phase46_line_window_finisher as p46


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
    path = m._layout_dir(document_id) / "phase47_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 47, "updated_at": _utc_now(), **payload})


def _visible_defects(pdf_path: Path, page_number: int) -> dict[str, list[str]]:
    pages = m._extract_pdf_page_texts(pdf_path)
    text = pages[page_number - 1] if 0 < page_number <= len(pages) else ""
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(pdf_path)
    surface = surface_pages[page_number - 1] if 0 < page_number <= len(surface_pages) else []
    return {
        "long_english_run": m._long_english_runs(text),
        "short_english_artifact": m._short_english_artifact_hits(text),
        "bad_term": [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in text.lower()],
        "scientific_surface_corruption": list(surface),
    }


def _latin_words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'’.-]{1,}", text or "")]


def _source_text_for_window(source_page: fitz.Page, window: list[dict]) -> tuple[str, fitz.Rect, str]:
    """Map the still-visible target line window back to the pristine source PDF.

    Phase46 translated the already-damaged target text.  For the three stubborn long
    English pages we instead use the exact rendered line rectangle as a spatial key
    into the source PDF.  A tiny expansion is tried only when it improves lexical
    overlap / Latin evidence; this avoids pulling a neighboring column into the repair.
    """
    base = p46._union_rect(window)
    page_rect = source_page.rect
    probes: list[tuple[str, fitz.Rect]] = [("base", fitz.Rect(base))]
    for pad_y in (1.5, 3.0):
        rect = fitz.Rect(
            max(page_rect.x0, base.x0 - 1.0),
            max(page_rect.y0, base.y0 - pad_y),
            min(page_rect.x1, base.x1 + 1.0),
            min(page_rect.y1, base.y1 + pad_y),
        )
        probes.append((f"expand_y_{pad_y:g}", rect))

    target_text = p45._prepare_source_text(p46._line_text(window))
    target_words = set(_latin_words(target_text))
    best: tuple[float, str, fitz.Rect, str] = (-1.0, "", fitz.Rect(base), "none")
    for mode, rect in probes:
        raw = source_page.get_text("text", clip=rect, sort=True)
        prepared = p45._prepare_source_text(raw)
        if not prepared:
            continue
        words = _latin_words(prepared)
        latin = m._latin_char_count(prepared)
        if not words and latin == 0:
            continue
        overlap = 0.0
        if target_words:
            overlap = len(target_words & set(words)) / max(1, len(target_words))
        # Prefer lexical overlap first.  Use Latin count only as a weak tie breaker;
        # otherwise an expanded rectangle can win merely by swallowing nearby prose.
        score = overlap * 1000.0 + min(latin, 500) / 1000.0
        if score > best[0]:
            best = (score, prepared, fitz.Rect(rect), mode)
    return best[1], best[2], best[3]


def _translate_source_text(document_id: str, source_text: str, client, progress_callback=None) -> tuple[str | None, dict]:
    translated, meta = p45._translate_source_region(
        document_id,
        source_text,
        client,
        progress_callback=progress_callback,
    )
    if translated is None:
        return None, meta
    translated = p46._cleanup_tiny_by_artifact(translated)
    meta = dict(meta)
    meta["mode"] = "source_aligned_adaptive_line_window"
    meta["target_preview"] = re.sub(r"\s+", " ", translated)[:260]
    if p43._has_defect(translated):
        meta["reason"] = "visible_defect_remains"
        return None, meta
    return translated, meta


def _fit_patch(target_page: fitz.Page, all_lines: list[dict], window: list[dict], text: str) -> tuple[fitz.Rect, float] | None:
    base = p46._union_rect(window)
    ids = {int(item["id"]) for item in window}
    expanded = p43._safe_expand_rect(target_page, base, all_lines, ids)
    preferred = statistics.median(float(item.get("font_size") or 8.0) for item in window)
    fontsize = p43._fit_font(base, text, preferred)
    use_rect = base
    if fontsize is None:
        fontsize = p43._fit_font(expanded, text, preferred)
        use_rect = expanded
    if fontsize is None:
        return None
    return use_rect, fontsize


def _split_window(window: list[dict]) -> tuple[list[dict], list[dict]]:
    mid = max(1, len(window) // 2)
    return window[:mid], window[mid:]


def _adaptive_window_patches(
    document_id: str,
    source_page: fitz.Page,
    target_page: fitz.Page,
    all_lines: list[dict],
    window: list[dict],
    client,
    root: Path,
    page_number: int,
    pass_number: int,
    window_number: int,
    window_total: int,
    depth: int = 0,
) -> tuple[list[dict], list[dict]]:
    """Translate a visual window; recursively split only when the bounded repair fails.

    This is the root change over Phase46.  A 6-9 line scientific paragraph no longer
    becomes an all-or-nothing candidate: if translation validation or layout fitting
    fails, the same source-aligned region is bisected until an atomic line can be
    repaired.  Already-good neighboring lines are never touched.
    """
    target_text = p46._line_text(window)
    source_text, source_rect, mapping_mode = _source_text_for_window(source_page, window)
    label = f"window {window_number}/{window_total}" + (f" split-depth={depth}" if depth else "")

    record_base = {
        "line_ids": [int(item["id"]) for item in window],
        "target_preview": re.sub(r"\s+", " ", target_text)[:260],
        "source_preview": re.sub(r"\s+", " ", source_text)[:260],
        "source_mapping": mapping_mode,
        "source_bbox": [source_rect.x0, source_rect.y0, source_rect.x1, source_rect.y1],
        "depth": depth,
    }

    if source_text and m._latin_char_count(source_text) > 0:
        def on_progress(info: dict) -> None:
            parts = [f"  pass {pass_number}", label, str(info.get("stage") or "working")]
            if info.get("batch") is not None and info.get("batches") is not None:
                parts.append(f"batch {info['batch']}/{info['batches']}")
            if info.get("attempt") is not None:
                parts.append(f"attempt {info['attempt']}/{info.get('max_attempts') or 4}")
            if info.get("fragments") is not None:
                parts.append(f"fragments={info['fragments']}")
            if info.get("reason"):
                parts.append(f"reason={info['reason']}")
            print(" | ".join(parts), flush=True)
            _progress(
                root,
                status="running",
                page=page_number,
                pass_number=pass_number,
                window=window_number,
                windows=window_total,
                split_depth=depth,
                **info,
            )

        translated, meta = _translate_source_text(
            document_id,
            source_text,
            client,
            progress_callback=on_progress,
        )
        if translated is not None:
            fit = _fit_patch(target_page, all_lines, window, translated)
            if fit is not None:
                rect, fontsize = fit
                ready = {
                    **record_base,
                    "status": "ready",
                    "rewrite": meta,
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "fontsize": fontsize,
                    "text": translated,
                }
                return [ready], []
            record_base["rewrite"] = meta
            record_base["reason"] = "layout_fit_failed"
        else:
            record_base["rewrite"] = meta
            record_base["reason"] = meta.get("reason") or "rewrite_failed"
    else:
        record_base["reason"] = "source_mapping_failed"

    # Do not keep retrying the exact same oversized candidate.  Split the visual
    # window and let each child map independently to the clean source PDF.
    if len(window) > 1:
        left, right = _split_window(window)
        print(f"  pass {pass_number} | {label}: split {len(window)} -> {len(left)} + {len(right)}", flush=True)
        patches: list[dict] = []
        failures: list[dict] = []
        for child in (left, right):
            child_patches, child_failures = _adaptive_window_patches(
                document_id,
                source_page,
                target_page,
                all_lines,
                child,
                client,
                root,
                page_number,
                pass_number,
                window_number,
                window_total,
                depth + 1,
            )
            patches.extend(child_patches)
            failures.extend(child_failures)
        return patches, failures

    # Last deterministic fallback is only for a one-line Japanese sentence with a
    # trivial lower-case by residue.  Never delete/replace words in a real English
    # sentence here; source-aligned translation must handle those.
    deterministic = p46._cleanup_tiny_by_artifact(target_text)
    if deterministic != target_text and not p43._has_defect(deterministic):
        if p43._science_equal(p43._science_fingerprint(target_text), p43._science_fingerprint(deterministic)):
            fit = _fit_patch(target_page, all_lines, window, deterministic)
            if fit is not None:
                rect, fontsize = fit
                ready = {
                    **record_base,
                    "status": "ready",
                    "rewrite": {"mode": "deterministic_tiny_by_fallback", "attempts": 0},
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "fontsize": fontsize,
                    "text": deterministic,
                }
                return [ready], []

    failed = {**record_base, "status": "failed"}
    return [], [failed]


def _repair_page_pass(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    client,
    root: Path,
    pass_number: int,
) -> dict:
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    tmp: Path | None = None
    try:
        source_page = source_doc[page_number - 1]
        target_page = target_doc[page_number - 1]
        all_lines = p46._line_records(target_page)
        windows = p46._candidate_line_windows(target_page)
        # Keep windows small enough that their source clip cannot span unrelated
        # paragraphs.  Adaptive recursion handles any residual difficult candidate.
        bounded: list[list[dict]] = []
        for window in windows:
            bounded.extend(p46._split_group(window, max_lines=5, max_chars=900))
        windows = bounded

        result = {
            "pass": pass_number,
            "candidate_windows": len(windows),
            "patched_windows": 0,
            "failed_windows": [],
            "windows": [],
        }
        if not windows:
            return result

        patches: list[dict] = []
        failures: list[dict] = []
        total = len(windows)
        for index, window in enumerate(windows, start=1):
            print(f"  pass {pass_number} | window {index}/{total}: source-align", flush=True)
            _progress(
                root,
                status="running",
                page=page_number,
                pass_number=pass_number,
                window=index,
                windows=total,
                stage="source_align",
            )
            child_patches, child_failures = _adaptive_window_patches(
                document_id,
                source_page,
                target_page,
                all_lines,
                window,
                client,
                root,
                page_number,
                pass_number,
                index,
                total,
            )
            patches.extend(child_patches)
            failures.extend(child_failures)

        # All rectangles originate from disjoint line windows.  Redact first, then
        # reinsert translated text so old English cannot remain under the overlay.
        if patches:
            for patch in patches:
                target_page.add_redact_annot(fitz.Rect(patch["bbox"]), fill=(1, 1, 1))
            target_page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            for patch in patches:
                inserted = target_page.insert_textbox(
                    fitz.Rect(patch["bbox"]),
                    patch["text"],
                    fontsize=patch["fontsize"],
                    fontname="japan",
                    lineheight=1.02,
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                    overlay=True,
                )
                if inserted < 0:
                    raise RuntimeError(
                        f"page {page_number} pass {pass_number} adaptive line patch failed after fit probe"
                    )
                patch["status"] = "patched"
                result["patched_windows"] += 1
                result["windows"].append(patch)
            tmp = target_pdf.with_suffix(f".phase47-pass{pass_number}.tmp.pdf")
            target_doc.save(tmp, garbage=3, deflate=True)

        result["failed_windows"] = failures
        result["windows"].extend(failures)
    finally:
        source_doc.close()
        target_doc.close()

    if tmp is not None and tmp.exists():
        tmp.replace(target_pdf)
    return result


def _repair_page(document_id: str, source_pdf: Path, target_pdf: Path, page_number: int, client, root: Path) -> dict:
    page_result = {"page": page_number, "passes": [], "patched_windows": 0}
    # Three bounded passes are enough to consume partial improvements without
    # turning this into another open-ended page retranslation loop.
    for pass_number in (1, 2, 3):
        before = _visible_defects(target_pdf, page_number)
        if not any(before.values()):
            break
        detail = _repair_page_pass(
            document_id,
            source_pdf,
            target_pdf,
            page_number,
            client,
            root,
            pass_number,
        )
        page_result["passes"].append(detail)
        page_result["patched_windows"] += int(detail.get("patched_windows", 0) or 0)
        after = _visible_defects(target_pdf, page_number)
        detail["visible_after"] = after
        if not any(after.values()):
            break
        if int(detail.get("patched_windows", 0) or 0) == 0:
            break
    page_result["visible_after"] = _visible_defects(target_pdf, page_number)
    return page_result


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase47.pdf"
    backup_qa = root / "qa.before-phase47.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Preserve Phase45/46 accepted repairs.  Rerunning Phase47 always starts from
    # this exact pre-Phase47 artifact, so the operation is deterministic/idempotent.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = p43._selected_pages(source_qa, target_pdf, source_pdf)

    manifest: dict = {
        "phase": 47,
        "mode": "adaptive-source-aligned-line-window-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "baseline": str(backup_pdf),
        "selected_pages": pages,
        "reasons": {str(page): reasons[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
    }
    _write_json(root / "manifest.json", manifest)
    _progress(root, status="starting", selected_pages=pages, stage="starting")

    print("===== PHASE47 ADAPTIVE SOURCE-LINE REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : map each visible defect line-window to source PDF; split failed windows recursively.\n")

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
        detail = _repair_page(document_id, source_pdf, target_pdf, page_number, client, root)
        visible_after = detail.get("visible_after") or {}
        page_ok = not any(visible_after.values())
        if page_ok:
            accepted.append(page_number)
            print(f"  ACCEPTED: patched_windows={detail['patched_windows']}", flush=True)
        else:
            rejected.append(page_number)
            remaining = sum(len(v) for v in visible_after.values() if isinstance(v, list))
            print(f"  REJECTED: patched_windows={detail['patched_windows']} remaining_defects={remaining}", flush=True)
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
    final_qa["phase47_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE47.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE47.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE47.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE47_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE47 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Adaptive source-aligned line-window repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

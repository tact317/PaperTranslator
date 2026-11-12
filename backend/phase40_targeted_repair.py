from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz

from backend import main as m


REPAIRABLE_WARNING_CODES = {
    "long_english_run",
    "semantic_relation_changed",
    "bad_term",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        raise RuntimeError("failed full-paper translation cache was not found")
    return max(candidates)[1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _repair_root(document_id: str) -> Path:
    root = m._layout_dir(document_id) / "phase40_repair"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _select_repair_pages(document_id: str, qa: dict) -> tuple[list[int], dict[int, list[str]]]:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    source_pages = m._extract_pdf_page_texts(source_pdf)
    target_pages = m._extract_pdf_page_texts(target_pdf)
    ref_page = m._reference_start_page_from_pdf(source_pdf)
    body_end = (ref_page - 1) if ref_page else len(source_pages)

    reasons: dict[int, set[str]] = {}
    for warning in qa.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        page = warning.get("page")
        code = str(warning.get("code") or "")
        severity = str(warning.get("severity") or "")
        if not isinstance(page, int) or page < 1 or page > body_end:
            continue
        if severity in {"critical", "high"} and code in REPAIRABLE_WARNING_CODES:
            reasons.setdefault(page, set()).add(code)

    # Attribute the original full-run Guard fallbacks to source pages.  Every
    # attributable fallback page is repaired, even if the English fragment is too
    # short to trigger the visible long-run detector.
    guard_events: list[dict] = []
    guard_path = m._layout_guard_log_path(document_id)
    if guard_path.exists():
        for line in guard_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except Exception:
                continue
            if isinstance(event, dict):
                guard_events.append(event)
    fallback_attribution = m._attribute_guard_fallback_pages(guard_events, source_pages)
    for page in fallback_attribution.get("pages") or []:
        if 1 <= int(page) <= body_end:
            reasons.setdefault(int(page), set()).add("translation_guard_fallback")

    # Recompute visible English runs from the current artifact.  This catches any
    # stale QA report and makes the repair plan depend on what is actually visible.
    for page, text in enumerate(target_pages[:body_end], start=1):
        if page >= 3 and m._long_english_runs(text):
            reasons.setdefault(page, set()).add("long_english_run")

    # Surface corruption is a real visible scientific defect.  The old report was
    # global, so locate the exact body pages now and repair only those pages.
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(target_pdf)
    for page, hits in enumerate(surface_pages[:body_end], start=1):
        if hits:
            reasons.setdefault(page, set()).add("scientific_surface_corruption")

    return sorted(reasons), {page: sorted(values) for page, values in reasons.items()}


def _page_visible_checks(path: Path, *, semantic_required: bool, source_path: Path | None = None) -> dict:
    text = m._extract_pdf_page_texts(path)[0]
    long_runs = m._long_english_runs(text)
    bad_terms = [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in text.lower()]
    surface = m._pdf_scientific_surface_artifact_hits_by_page(path)[0]
    semantic_warnings: list[dict] = []
    semantic_meta: dict = {"enabled": False, "calls": 0}
    if semantic_required and source_path is not None:
        source_text = m._extract_pdf_page_texts(source_path)[0]
        semantic_warnings, semantic_meta = m._run_semantic_layout_qa([source_text], [text], None)
    return {
        "long_english_runs": long_runs[:4],
        "bad_terms": bad_terms,
        "surface_artifacts": surface,
        "semantic_warnings": semantic_warnings,
        "semantic_meta": semantic_meta,
        "ok": not long_runs and not bad_terms and not surface and not semantic_warnings,
    }


def _archived_preflight_candidate(document_id: str, page: int, *, semantic_required: bool) -> tuple[Path, dict] | None:
    page_dir = m._layout_preflight_dir(document_id) / "pages" / f"page-{page}"
    source = page_dir / "source.pdf"
    target = page_dir / "translated.pdf"
    qa_path = page_dir / "qa.json"
    if not source.exists() or not target.exists() or not qa_path.exists():
        return None
    try:
        qa = _load_json(qa_path)
    except Exception:
        return None
    if qa.get("status") != "pass" or float(qa.get("eligible_chunk_coverage_percent", 0) or 0) < 100.0:
        return None
    visible = _page_visible_checks(target, semantic_required=semantic_required, source_path=source)
    if not visible["ok"]:
        return None
    return target, {"qa": qa, "visible": visible, "source": "archived_preflight"}


def _copy_diagnostics(document_id: str, page_dir: Path) -> None:
    for source, name in (
        (m._layout_guard_log_path(document_id), "translation_guard.jsonl"),
        (m._layout_proxy_log_path(document_id), "proxy_requests.jsonl"),
    ):
        if source.exists():
            shutil.copy2(source, page_dir / name)


def _translate_repair_page(document_id: str, page: int, *, semantic_required: bool) -> tuple[Path | None, dict]:
    command, work_dir, source_page = m._layout_translation_command(document_id, repair_page=page)
    page_dir = _repair_root(document_id) / f"page-{page}"
    print(f"  translating page {page} with repair mode (min-text-length=1)", flush=True)
    log_lines, mono, _ = m._run_pdf2zh_process(
        command,
        work_dir,
        lambda progress: print(f"    page {page}: {progress}%", flush=True) if progress in {25, 50, 75, 90, 96} else None,
    )
    target = page_dir / "translated.pdf"
    shutil.copy2(mono, target)
    _copy_diagnostics(document_id, page_dir)
    (page_dir / "worker.log").write_text("\n".join(log_lines), encoding="utf-8", errors="replace")

    qa = m._run_layout_preflight_qa(
        document_id,
        source_page,
        target,
        page,
        proxy_log_path=page_dir / "proxy_requests.jsonl",
        guard_log_path=page_dir / "translation_guard.jsonl",
    )
    _write_json(page_dir / "qa.json", qa)
    visible = _page_visible_checks(target, semantic_required=semantic_required, source_path=source_page)
    accepted = qa.get("status") == "pass" and visible["ok"]
    result = {
        "source": "fresh_targeted_repair",
        "qa": qa,
        "visible": visible,
        "accepted": accepted,
    }
    return (target if accepted else None), result


def _replace_pdf_page(target_path: Path, replacement_path: Path, page_number: int) -> None:
    source_doc = fitz.open(target_path)
    replacement_doc = fitz.open(replacement_path)
    out = fitz.open()
    try:
        if len(replacement_doc) != 1:
            raise RuntimeError(f"replacement page {page_number} must contain exactly one page")
        if page_number < 1 or page_number > len(source_doc):
            raise RuntimeError(f"page {page_number} is outside target PDF")
        metadata = source_doc.metadata or {}
        for index in range(len(source_doc)):
            if index == page_number - 1:
                out.insert_pdf(replacement_doc, from_page=0, to_page=0)
            else:
                out.insert_pdf(source_doc, from_page=index, to_page=index)
        if metadata:
            try:
                out.set_metadata(metadata)
            except Exception:
                pass
        temp = target_path.with_suffix(f".phase40-page-{page_number}.tmp.pdf")
        out.save(temp, garbage=4, deflate=True)
    finally:
        out.close()
        replacement_doc.close()
        source_doc.close()
    temp.replace(target_path)


def _backup_file(source: Path, destination: Path) -> None:
    if source.exists() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _restore_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("failed full-paper translated PDF / QA report was not found")

    repair_root = _repair_root(document_id)
    original_target_backup = repair_root / "translated-mono.before-phase40.pdf"
    original_guard_backup = repair_root / "full-run-translation_guard.jsonl"
    original_proxy_backup = repair_root / "full-run-proxy_requests.jsonl"
    original_qa_backup = repair_root / "qa.before-phase40.json"

    _backup_file(target_pdf, original_target_backup)
    _backup_file(m._layout_guard_log_path(document_id), original_guard_backup)
    _backup_file(m._layout_proxy_log_path(document_id), original_proxy_backup)
    _backup_file(qa_path, original_qa_backup)

    # Reruns are deterministic: always start from the failed full-paper artifact,
    # not from a partially repaired previous attempt.
    shutil.copy2(original_target_backup, target_pdf)
    source_qa = _load_json(original_qa_backup)
    pages, reasons = _select_repair_pages(document_id, source_qa)
    semantic_pages = {
        int(item["page"])
        for item in source_qa.get("warnings") or []
        if isinstance(item, dict)
        and item.get("code") == "semantic_relation_changed"
        and isinstance(item.get("page"), int)
    }

    manifest: dict = {
        "phase": 40,
        "mode": "targeted-page-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "source_quality_gate": source_qa.get("quality_gate"),
        "selected_pages": pages,
        "reasons": {str(page): reasons[page] for page in pages},
        "pages": [],
    }
    _write_json(repair_root / "manifest.json", manifest)

    print("===== PHASE40 TARGETED REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Full 16-page translation will NOT be rerun.\n")

    accepted_pages: list[int] = []
    rejected_pages: list[int] = []
    for page in pages:
        print(f"[page {page}] reasons: {', '.join(reasons[page])}")
        semantic_required = page in semantic_pages
        candidate = _archived_preflight_candidate(document_id, page, semantic_required=semantic_required)
        if candidate is not None:
            replacement, detail = candidate
            detail["accepted"] = True
            print("  reuse: archived PASS page")
        else:
            try:
                replacement, detail = _translate_repair_page(
                    document_id, page, semantic_required=semantic_required
                )
            except Exception as exc:
                replacement = None
                detail = {"source": "fresh_targeted_repair", "accepted": False, "error": str(exc)}

        if replacement is not None:
            _replace_pdf_page(target_pdf, replacement, page)
            accepted_pages.append(page)
            print("  result: ACCEPTED + spliced\n")
        else:
            rejected_pages.append(page)
            print("  result: REJECTED (original full-paper page kept)\n")

        manifest["pages"].append({
            "page": page,
            "reasons": reasons[page],
            **detail,
        })
        manifest["accepted_pages"] = accepted_pages
        manifest["rejected_pages"] = rejected_pages
        _write_json(repair_root / "manifest.json", manifest)

    # The full-run Guard/proxy logs are historical evidence.  Page-repair jobs use
    # the same proxy files, so restore the originals before final postflight.
    _restore_if_exists(original_guard_backup, m._layout_guard_log_path(document_id))
    _restore_if_exists(original_proxy_backup, m._layout_proxy_log_path(document_id))

    author_restoration = m.restore_primary_author_band(source_pdf, target_pdf)
    reference_restoration = m.restore_reference_section(source_pdf, target_pdf)
    m.build_alternating_dual(source_pdf, target_pdf, m._layout_dual_path(document_id))

    print("Running final Postflight against repaired PDF...", flush=True)
    final_qa = m._run_layout_qa(
        document_id,
        source_pdf,
        target_pdf,
        author_restoration=author_restoration,
        reference_restoration=reference_restoration,
    )
    final_qa["author_restoration"] = author_restoration
    final_qa["reference_restoration"] = reference_restoration
    final_qa["targeted_repair"] = manifest
    _write_json(qa_path, final_qa)

    manifest["finished_at"] = _utc_now()
    manifest["final_quality_gate"] = final_qa.get("quality_gate")
    manifest["final_critical_count"] = final_qa.get("critical_count")
    manifest["final_high_count"] = final_qa.get("high_count")
    _write_json(repair_root / "manifest.json", manifest)

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    mono_out = downloads / "PeperTranslator_full_ja_PHASE40.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE40.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE40.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE40_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE40 FINAL SUMMARY =====")
    print(f"QualityGate : {final_qa.get('quality_gate')}")
    print(f"Critical    : {final_qa.get('critical_count')}")
    print(f"High        : {final_qa.get('high_count')}")
    print(f"Repaired    : {accepted_pages}")
    print(f"Rejected    : {rejected_pages}")
    if severe:
        print("Remaining severe warnings:")
        for item in severe[:12]:
            print(f"  p.{item.get('page')} {item.get('code')}: {item.get('message')}")
    print(f"MONO        : {mono_out}")
    print(f"DUAL        : {dual_out}")
    print(f"QA          : {qa_out}")
    return 0 if final_qa.get("quality_gate") == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair only severe pages in an existing full PaperTranslator PDF")
    parser.add_argument("--document-id", default="", help="64-char cached document id; newest failed full translation is used when omitted")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

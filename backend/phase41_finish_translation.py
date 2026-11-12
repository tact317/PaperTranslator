from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import main as m
from backend import phase40_targeted_repair as p40


HARD_REPAIR_CODES = {
    "long_english_run",
    "bad_term",
    "formula_relation_changed",
    "short_english_artifact",
    "residual_english_prose",
    "simplified_chinese_leak",
    "internal_placeholder_leak",
    "scientific_surface_corruption",
    "translation_coverage_too_low",
    "mostly_untranslated_pages",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
    path = m._layout_dir(document_id) / "phase41_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _capture_baseline(source: Path, destination: Path, *, refresh: bool = False) -> None:
    """Capture the artifact that this Phase41 run is allowed to roll back to.

    Historical Phase41 directories survive across application upgrades because the
    document cache key is based on the source PDF.  Reusing a months-old
    ``before-phase41`` file after a fresh full translation silently discarded all
    newer translation/QA improvements.  Production therefore refreshes the
    baseline on every new full-run repair attempt; standalone reruns retain the
    previous idempotent behavior by default.
    """
    if refresh and destination.exists():
        destination.unlink()
    if source.exists() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _restore_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


def _copy_diagnostics(document_id: str, page_dir: Path) -> None:
    for source, name in (
        (m._layout_guard_log_path(document_id), "translation_guard.jsonl"),
        (m._layout_proxy_log_path(document_id), "proxy_requests.jsonl"),
    ):
        if source.exists():
            shutil.copy2(source, page_dir / name)


def _page_visible_checks(
    path: Path,
    *,
    source_path: Path | None = None,
    original_page_number: int | None = None,
) -> dict:
    text = m._extract_pdf_page_texts(path)[0]
    # Keep repair acceptance consistent with full Postflight: page 1-2 may contain
    # legitimate all-English author/affiliation metadata, while page 3+ uses the
    # same geometry-aware long-English detector as production QA.
    if original_page_number is not None and original_page_number < 3:
        long_runs = []
    else:
        pages = m._pdf_long_english_run_hits_by_page(path)
        long_runs = pages[0] if pages else []
    bad_terms = [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in text.lower()]
    short_artifacts = m._pdf_short_english_artifact_hits_by_page(path)[0]
    residual_english = m._pdf_residual_english_prose_hits_by_page(path)[0]
    simplified_chinese = m._simplified_chinese_hits(text)
    internal_markers = m._visible_internal_marker_hits(text)
    surface = m._pdf_scientific_surface_artifact_hits_by_page(path)[0]
    formula_conflicts: list[str] = []
    formula_missing: list[str] = []
    if source_path is not None:
        source_text = m._extract_pdf_page_texts(source_path)[0]
        source_relations = set(m.formula_relation_tokens(source_text))
        target_relations = set(m.formula_relation_tokens(m._repair_scientific_surface_artifacts(text)))
        relation = m._formula_relation_gate_decision(source_relations, target_relations, guard_clean=True)
        formula_conflicts = list(relation.get("conflicting") or [])
        formula_missing = list(relation.get("missing") or [])
    return {
        "long_english_runs": long_runs[:4],
        "bad_terms": bad_terms,
        "short_english_artifacts": short_artifacts,
        "residual_english_prose": residual_english,
        "simplified_chinese_hits": simplified_chinese,
        "internal_placeholder_hits": internal_markers,
        "surface_artifacts": surface,
        "formula_conflicts": formula_conflicts,
        "formula_missing_diagnostic": formula_missing,
        "ok": not any((
            long_runs, bad_terms, short_artifacts, residual_english, simplified_chinese,
            internal_markers, surface, formula_conflicts,
        )),
    }


def _select_pages(document_id: str, qa: dict) -> tuple[list[int], dict[int, list[str]]]:
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
        if isinstance(page, int) and 1 <= page <= body_end and severity in {"critical", "high"} and code in HARD_REPAIR_CODES:
            reasons.setdefault(page, set()).add(code)

    # Phase73: a document-global coverage failure previously had no page number, so
    # Phase41 was invoked but selected zero pages.  Route only clearly untranslated
    # body pages into the existing isolated repair path.  We intentionally require a
    # prose-rich English source and a strongly Latin target; scientific/metadata-only
    # pages are left alone.  Replacement still requires the normal page preflight and
    # scientific-value checks before it can be spliced into the full PDF.
    coverage_warning = any(
        isinstance(item, dict)
        and item.get("severity") in {"critical", "high"}
        and str(item.get("code") or "") in {"translation_coverage_too_low", "mostly_untranslated_pages"}
        for item in (qa.get("warnings") or [])
    )
    if coverage_warning:
        for page, (source_text, target_text) in enumerate(
            zip(source_pages[:body_end], target_pages[:body_end]), start=1
        ):
            source_latin = m._latin_char_count(source_text)
            target_japanese = m._japanese_char_count(target_text)
            target_latin = m._latin_char_count(target_text)
            target_ratio = target_japanese / max(1, target_japanese + target_latin)
            source_is_prose_rich = source_latin >= 180
            target_is_clearly_untranslated = (
                target_latin >= 120
                and (target_ratio < 0.25 or target_japanese < 40)
            )
            if source_is_prose_rich and target_is_clearly_untranslated:
                reasons.setdefault(page, set()).add("translation_coverage_too_low")

    # Historical Guard fallbacks are useful routing evidence.  They are not a
    # document-wide failure anymore, but an unresolved page should get one isolated
    # repair attempt before the artifact is considered final.
    for page in ((qa.get("translation_guard") or {}).get("unresolved_fallback_pages") or []):
        try:
            page = int(page)
        except Exception:
            continue
        if 1 <= page <= body_end:
            reasons.setdefault(page, set()).add("translation_guard_fallback")

    # Recompute actual visible defects from the current Phase 40 artifact.  This
    # avoids relying on stale warning lists and locates the global surface warning.
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(target_pdf)
    for page, hits in enumerate(surface_pages[:body_end], start=1):
        if hits:
            reasons.setdefault(page, set()).add("scientific_surface_corruption")

    try:
        long_pages = m._pdf_long_english_run_hits_by_page(target_pdf)
        short_pages = m._pdf_short_english_artifact_hits_by_page(target_pdf)
        residual_pages = m._pdf_residual_english_prose_hits_by_page(target_pdf)
    except Exception:
        # Test doubles / recovery paths may provide text without a materialized PDF.
        long_pages = [m._long_english_runs(text) for text in target_pages]
        short_pages = [m._short_english_artifact_hits(text) for text in target_pages]
        residual_pages = [m._residual_english_prose_hits(text) for text in target_pages]
    for page, text in enumerate(target_pages[:body_end], start=1):
        if page >= 3 and page - 1 < len(long_pages) and long_pages[page - 1]:
            reasons.setdefault(page, set()).add("long_english_run")
        if page - 1 < len(short_pages) and short_pages[page - 1]:
            reasons.setdefault(page, set()).add("short_english_artifact")
        if page - 1 < len(residual_pages) and residual_pages[page - 1]:
            reasons.setdefault(page, set()).add("residual_english_prose")
        if m._simplified_chinese_hits(text):
            reasons.setdefault(page, set()).add("simplified_chinese_leak")
        if m._visible_internal_marker_hits(text):
            reasons.setdefault(page, set()).add("internal_placeholder_leak")

    return sorted(reasons), {page: sorted(values) for page, values in reasons.items()}


def _recheck_candidate(document_id: str, page: int, candidate_dir: Path, *, label: str) -> tuple[Path, dict] | None:
    source = candidate_dir / "source.pdf"
    target = candidate_dir / "translated.pdf"
    guard = candidate_dir / "translation_guard.jsonl"
    proxy = candidate_dir / "proxy_requests.jsonl"
    if not source.exists() or not target.exists() or not guard.exists() or not proxy.exists():
        return None
    try:
        qa = m._run_layout_preflight_qa(
            document_id,
            source,
            target,
            page,
            proxy_log_path=proxy,
            guard_log_path=guard,
        )
    except Exception as exc:
        return None
    visible = _page_visible_checks(target, source_path=source, original_page_number=page)
    detail = {
        "source": label,
        "qa": qa,
        "visible": visible,
        "accepted": qa.get("status") == "pass" and visible["ok"],
    }
    _write_json(candidate_dir / "phase41_recheck.json", detail)
    return (target, detail) if detail["accepted"] else None


def _existing_candidate(document_id: str, page: int) -> tuple[Path, dict] | None:
    # First re-evaluate the Phase 40 page that may have been rejected only because
    # semantic LLM review was previously a hard acceptance criterion.
    phase40 = m._layout_dir(document_id) / "phase40_repair" / f"page-{page}"
    candidate = _recheck_candidate(document_id, page, phase40, label="phase40_candidate_rechecked")
    if candidate is not None:
        return candidate

    archived = m._layout_preflight_dir(document_id) / "pages" / f"page-{page}"
    return _recheck_candidate(document_id, page, archived, label="archived_preflight_rechecked")


def _translate_page(document_id: str, page: int) -> tuple[Path | None, dict]:
    command, work_dir, source_page = m._layout_translation_command(
        document_id,
        repair_page=page,
        repair_namespace="phase41_repair",
        repair_proxy=True,
    )
    page_dir = _root(document_id) / f"page-{page}"
    print(f"  fresh repair: page {page} (last-mile Guard enabled)", flush=True)
    log_lines, mono, _ = m._run_pdf2zh_process(
        command,
        work_dir,
        lambda progress: print(f"    page {page}: {progress}%", flush=True)
        if progress in {25, 50, 75, 90, 96}
        else None,
    )
    target = page_dir / "translated.pdf"
    shutil.copy2(mono, target)
    from backend.phase60_postrender_normalizer import normalize_pdf as _phase60_normalize_pdf
    normalization = _phase60_normalize_pdf(source_page, target)
    _write_json(page_dir / "postrender_normalization.json", normalization)
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
    visible = _page_visible_checks(target, source_path=source_page, original_page_number=page)
    accepted = qa.get("status") == "pass" and visible["ok"]
    detail = {
        "source": "fresh_phase41_last_mile_repair",
        "qa": qa,
        "visible": visible,
        "postrender_normalization": normalization,
        "accepted": accepted,
    }
    _write_json(page_dir / "qa.json", qa)
    _write_json(page_dir / "acceptance.json", detail)
    return (target if accepted else None), detail


def run(
    document_id: str,
    *,
    export_downloads: bool = True,
    refresh_baseline: bool = False,
    reuse_existing_candidates: bool = True,
) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("Phase 40 translated PDF / QA report was not found")

    root = _root(document_id)
    target_backup = root / "translated-mono.before-phase41.pdf"
    qa_backup = root / "qa.before-phase41.json"
    guard_backup = root / "translation_guard.before-phase41.jsonl"
    proxy_backup = root / "proxy_requests.before-phase41.jsonl"
    _capture_baseline(target_pdf, target_backup, refresh=refresh_baseline)
    _capture_baseline(qa_path, qa_backup, refresh=refresh_baseline)
    _capture_baseline(m._layout_guard_log_path(document_id), guard_backup, refresh=refresh_baseline)
    _capture_baseline(m._layout_proxy_log_path(document_id), proxy_backup, refresh=refresh_baseline)

    # Deterministic rerun: restart from this run's captured pre-Phase41 artifact,
    # preserving accepted page repairs without accumulating partial attempts.
    shutil.copy2(target_backup, target_pdf)
    source_qa = _load_json(qa_backup)
    pages, reasons = _select_pages(document_id, source_qa)

    manifest: dict = {
        "phase": 41,
        "mode": "last-mile-targeted-repair",
        "started_at": _utc_now(),
        "document_id": document_id,
        "source_quality_gate": source_qa.get("quality_gate"),
        "selected_pages": pages,
        "reasons": {str(page): reasons[page] for page in pages},
        "pages": [],
        "accepted_pages": [],
        "rejected_pages": [],
        "reuse_existing_candidates": bool(reuse_existing_candidates),
    }
    _write_json(root / "manifest.json", manifest)

    print("===== PHASE41 LAST-MILE REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Base    : current Phase 40 PDF; full paper will NOT be translated again.\n")

    accepted: list[int] = []
    rejected: list[int] = []
    reused: list[int] = []
    fresh: list[int] = []
    for page in pages:
        print(f"[page {page}] reasons: {', '.join(reasons[page])}")
        candidate = _existing_candidate(document_id, page) if reuse_existing_candidates else None
        if candidate is not None:
            replacement, detail = candidate
            reused.append(page)
            print(f"  reuse: {detail['source']}")
        else:
            try:
                if not reuse_existing_candidates:
                    shutil.rmtree(_root(document_id) / f"page-{page}", ignore_errors=True)
                replacement, detail = _translate_page(document_id, page)
                fresh.append(page)
            except Exception as exc:
                replacement = None
                detail = {
                    "source": "fresh_phase41_last_mile_repair",
                    "accepted": False,
                    "error": str(exc),
                }

        if replacement is not None:
            p40._replace_pdf_page(target_pdf, replacement, page)
            accepted.append(page)
            print("  result: ACCEPTED + spliced\n")
        else:
            rejected.append(page)
            print("  result: REJECTED; previous Phase 40 page kept\n")

        manifest["pages"].append({"page": page, "reasons": reasons[page], **detail})
        manifest["accepted_pages"] = accepted
        manifest["rejected_pages"] = rejected
        manifest["reused_pages"] = reused
        manifest["freshly_translated_pages"] = fresh
        _write_json(root / "manifest.json", manifest)

    # Restore full-run historical logs; the per-page repair logs are preserved in
    # phase41_repair/page-N and the accepted manifest marks those pages clean.
    _restore_if_exists(guard_backup, m._layout_guard_log_path(document_id))
    _restore_if_exists(proxy_backup, m._layout_proxy_log_path(document_id))

    author_restoration = m.restore_primary_author_band(source_pdf, target_pdf)
    reference_restoration = m.restore_reference_section(source_pdf, target_pdf)
    m.build_alternating_dual(source_pdf, target_pdf, m._layout_dual_path(document_id))

    print("Running final Postflight...", flush=True)
    final_qa = m._run_layout_qa(
        document_id,
        source_pdf,
        target_pdf,
        author_restoration=author_restoration,
        reference_restoration=reference_restoration,
    )
    final_qa["author_restoration"] = author_restoration
    final_qa["reference_restoration"] = reference_restoration
    final_qa["phase41_repair"] = manifest
    _write_json(qa_path, final_qa)

    manifest["finished_at"] = _utc_now()
    manifest["final_quality_gate"] = final_qa.get("quality_gate")
    manifest["final_critical_count"] = final_qa.get("critical_count")
    manifest["final_high_count"] = final_qa.get("high_count")
    _write_json(root / "manifest.json", manifest)

    mono_out = dual_out = qa_out = None
    if export_downloads:
        downloads = Path.home() / "Downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        mono_out = downloads / "PeperTranslator_full_ja_PHASE41.pdf"
        dual_out = downloads / "PeperTranslator_full_en-ja_PHASE41.pdf"
        qa_out = downloads / (
            "PeperTranslator_full_QA_PHASE41.json"
            if final_qa.get("quality_gate") == "pass"
            else "PeperTranslator_full_QA_PHASE41_FAILED.json"
        )
        shutil.copy2(target_pdf, mono_out)
        if m._layout_dual_path(document_id).exists():
            shutil.copy2(m._layout_dual_path(document_id), dual_out)
        _write_json(qa_out, final_qa)

    severe = [
        item
        for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    reviews = [
        item
        for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("code") == "semantic_relation_review"
    ]
    print("\n===== PHASE41 FINAL SUMMARY =====")
    print(f"QualityGate : {final_qa.get('quality_gate')}")
    print(f"Critical    : {final_qa.get('critical_count')}")
    print(f"High        : {final_qa.get('high_count')}")
    print(f"Selected    : {pages}")
    print(f"Reused      : {reused}")
    print(f"Fresh       : {fresh}")
    print(f"Repaired    : {accepted}")
    print(f"Rejected    : {rejected}")
    print(f"Semantic review-only warnings: {len(reviews)}")
    if severe:
        print("Remaining blocking warnings:")
        for item in severe[:12]:
            print(f"  p.{item.get('page')} {item.get('code')}: {item.get('message')}")
    if export_downloads:
        print(f"MONO        : {mono_out}")
        print(f"DUAL        : {dual_out}")
        print(f"QA          : {qa_out}")
    return 0 if final_qa.get("quality_gate") == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Finish the current PaperTranslator artifact with isolated last-mile page repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

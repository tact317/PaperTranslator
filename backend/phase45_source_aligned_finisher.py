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
from backend import phase60_postrender_normalizer as p60


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
    path = m._layout_dir(document_id) / "phase45_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 45, "updated_at": _utc_now(), **payload})


def _prepare_source_text(text: str) -> str:
    """Normalize source-PDF prose before a bounded repair translation.

    Journal PDFs commonly encode line-wrap hyphenation as ``formula-\ntion``.  That
    break is layout, not semantics, so remove it before asking the model to translate.
    Scientific punctuation, numbers, equations, and citations are otherwise untouched
    and are subsequently hidden by the shared Translation Guard.
    """
    value = p43._clean(text).replace("\u00ad", "")
    value = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", value)
    value = re.sub(r"[ \t]*\n[ \t]*", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _shared_page_visible_defects(pdf_path: Path, page_number: int) -> dict[str, list[str]]:
    """Use the same geometry-aware detectors as final Postflight acceptance."""
    pages = m._extract_pdf_page_texts(pdf_path)
    text = pages[page_number - 1] if 0 < page_number <= len(pages) else ""
    long_pages = m._pdf_long_english_run_hits_by_page(pdf_path)
    short_pages = m._pdf_short_english_artifact_hits_by_page(pdf_path)
    residual_pages = m._pdf_residual_english_prose_hits_by_page(pdf_path)
    surface_pages = m._pdf_scientific_surface_artifact_hits_by_page(pdf_path)

    def page_hits(values: list[list[str]]) -> list[str]:
        return list(values[page_number - 1]) if 0 < page_number <= len(values) else []

    return {
        "long_english_run": page_hits(long_pages),
        "short_english_artifact": page_hits(short_pages),
        "residual_english_prose": page_hits(residual_pages),
        "bad_term": [bad for bad, _ in m._LAYOUT_BAD_TERMS if bad.lower() in text.lower()],
        "scientific_surface_corruption": page_hits(surface_pages),
    }


def _needs_atomic_repair(record: dict, component_has_long_english: bool) -> bool:
    if any((record.get("defects") or {}).values()):
        return True
    text = str(record.get("text") or "")
    if p43._orphan_function_word(text):
        return True
    # When a long English paragraph was split into several PDF blocks, some lines
    # individually contain fewer than six words and therefore do not trip the
    # long-run regex.  Repair those Latin-heavy siblings as part of the same visual
    # component without dragging already-Japanese blocks into the rewrite.
    return component_has_long_english and m._latin_char_count(text) >= 6


def _atomic_groups(page: fitz.Page) -> list[list[dict]]:
    components = []
    for component in p43._candidate_components(page):
        body = [record for record in component if not p43._record_is_nonbody_metadata(record, page)]
        if body:
            components.append(body)
    if not components:
        return []
    page_width = float(page.rect.width)
    groups: list[list[dict]] = []
    used: set[int] = set()

    for component in components:
        component_long = bool(m._long_english_runs(p43._region_text(component)))
        for record in p43._ordered(component):
            rid = int(record["id"])
            if rid in used or not _needs_atomic_repair(record, component_long):
                continue

            group = [record]
            # A standalone ``by``/``of`` block is too narrow for a readable Japanese
            # replacement.  Pair it with the nearest visual neighbor and retranslate
            # the corresponding clean source-PDF area instead.
            if p43._orphan_function_word(record.get("text", "")):
                neighbors = [
                    other for other in component
                    if int(other["id"]) not in used
                    and int(other["id"]) != rid
                    and p43._adjacent(record, other, page_width)
                ]
                neighbors.sort(
                    key=lambda item: (
                        p43._vertical_gap(p43._rect(record), p43._rect(item)),
                        p43._horizontal_gap(p43._rect(record), p43._rect(item)),
                    )
                )
                if neighbors:
                    group.append(neighbors[0])

            ordered = p43._ordered(group)
            groups.append(ordered)
            used.update(int(item["id"]) for item in ordered)

    return groups


def _source_text_for_group(
    source_page: fitz.Page,
    target_page: fitz.Page,
    group: list[dict],
    all_target_blocks: list[dict],
) -> tuple[str, fitz.Rect, str]:
    base = p43._union_rect(group)
    ids = {int(item["id"]) for item in group}
    expanded = p43._safe_expand_rect(target_page, base, all_target_blocks, ids)
    target_latin = m._latin_char_count(p43._region_text(group))

    probes: list[tuple[str, fitz.Rect]] = [("base", base)]
    if expanded != base:
        probes.append(("expanded", expanded))

    best: tuple[str, fitz.Rect, str] = ("", base, "none")
    best_latin = -1
    for mode, rect in probes:
        raw = source_page.get_text("text", clip=rect, sort=True)
        prepared = _prepare_source_text(raw)
        latin = m._latin_char_count(prepared)
        if latin > best_latin:
            best = (prepared, fitz.Rect(rect), mode)
            best_latin = latin
        if target_latin <= 3 and latin >= 1:
            return prepared, fitz.Rect(rect), mode
        if latin >= max(8, int(target_latin * 0.45)):
            return prepared, fitz.Rect(rect), mode
    return best


def _deterministic_target_region_repair(source_text: str, target_text: str) -> tuple[str | None, dict]:
    original = p43._clean(target_text)
    if not original:
        return None, {"mode": "deterministic-target-lexical", "reason": "empty_target"}
    repaired = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(original))
    repaired = m._repair_mixed_script_source_names(source_text, repaired)
    if repaired == original:
        return None, {"mode": "deterministic-target-lexical", "reason": "no_change"}
    if p43._has_defect(repaired):
        return None, {"mode": "deterministic-target-lexical", "reason": "visible_defect_remains", "target_preview": re.sub(r"\s+", " ", repaired)[:260]}
    if not p43._science_equal(p43._science_fingerprint(original), p43._science_fingerprint(repaired)):
        return None, {"mode": "deterministic-target-lexical", "reason": "target_science_changed"}
    return repaired, {"mode": "deterministic-target-lexical", "reason": "", "target_preview": re.sub(r"\s+", " ", repaired)[:260]}


def _translate_source_region(
    document_id: str,
    source_text: str,
    client,
    progress_callback=None,
) -> tuple[str | None, dict]:
    source = _prepare_source_text(source_text)
    if not source:
        return None, {"reason": "source_mapping_empty", "attempts": 0}

    terms = list(m._guard_terms_for_document(document_id))
    # Preserve mixed alphanumeric identifiers that the generic standalone-number
    # rule intentionally does not match (for example ANSYS 2020R1, Solid236, 3D).
    # These are source literals, not prose, and should never be regenerated by Qwen.
    mixed_identifiers = re.findall(
        r"\b(?=[A-Za-z0-9.-]*[A-Za-z])(?=[A-Za-z0-9.-]*\d)[A-Za-z0-9][A-Za-z0-9.-]*\b",
        source,
    )
    for item in mixed_identifiers:
        if item not in terms:
            terms.append(item)
    protected, mapping = m.protect_translation_segment(source, terms)
    model = m._preferred_translation_model()
    system = m._load_translation_prompt(model)
    glossary = m._glossary_prompt_text()
    if glossary:
        system += "\n\nRequired terminology:\n" + glossary
    restored, _protected_out, ok, rescue = m._translate_repair_last_mile(
        client,
        model,
        system,
        protected,
        mapping,
        progress_callback=progress_callback,
    )
    meta = {
        "mode": "source_aligned_placeholder_free",
        **(rescue or {}),
        "protected": len(mapping),
        "source_preview": re.sub(r"\s+", " ", source)[:260],
    }
    if not ok:
        return None, meta

    restored = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(restored))
    restored = m._repair_mixed_script_source_names(source, restored)
    meta["target_preview"] = re.sub(r"\s+", " ", restored)[:260]
    if m._simplified_chinese_hits(restored) or m._foreign_language_hits(restored):
        meta["reason"] = "language_leak"
        return None, meta
    if p43._has_defect(restored):
        meta["reason"] = "visible_defect_remains"
        return None, meta
    source_science = p43._science_fingerprint(source)
    target_science = p43._science_fingerprint(restored)
    if not p43._science_equal(source_science, target_science):
        meta["reason"] = "source_science_changed"
        return None, meta
    if m._latin_char_count(source) >= 20 and m._japanese_char_count(restored) < 2:
        meta["reason"] = "not_japanese_enough"
        return None, meta
    return restored, meta


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
        all_blocks = p43._extract_blocks(target_page)
        groups = _atomic_groups(target_page)
        repair_font = p60.resolve_proportional_repair_font()
        result = {
            "pass": pass_number,
            "candidate_regions": len(groups),
            "patched_regions": 0,
            "failed_regions": [],
            "regions": [],
            "repair_font": p60._repair_font_name(repair_font),
        }
        if not groups:
            return result
        if repair_font is None:
            result["failed_regions"].append({
                "status": "proportional_repair_font_unavailable",
                "reason": "Phase45 refuses to redraw mixed scientific/Japanese text with CJK full-width Latin metrics.",
            })
            return result

        patches: list[dict] = []
        total = len(groups)
        for index, group in enumerate(groups, start=1):
            print(f"  pass {pass_number} | region {index}/{total}: source-align", flush=True)
            _progress(
                root,
                status="running",
                page=page_number,
                pass_number=pass_number,
                region=index,
                regions=total,
                stage="source_align",
            )
            source_text, source_rect, mapping_mode = _source_text_for_group(
                source_page, target_page, group, all_blocks
            )
            target_text = p43._region_text(group)
            region = {
                "index": index - 1,
                "block_ids": [int(item["id"]) for item in group],
                "target_preview": re.sub(r"\s+", " ", target_text)[:240],
                "source_mapping": mapping_mode,
                "source_bbox": [source_rect.x0, source_rect.y0, source_rect.x1, source_rect.y1],
            }
            if not source_text or m._latin_char_count(source_text) == 0:
                region["status"] = "source_mapping_failed"
                region["reason"] = "source_has_no_latin"
                result["failed_regions"].append(region)
                result["regions"].append(region)
                print(f"  pass {pass_number} | region {index}/{total}: SOURCE MAPPING FAILED", flush=True)
                continue

            def on_progress(info: dict) -> None:
                parts = [f"  pass {pass_number}", f"region {index}/{total}", str(info.get("stage") or "working")]
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
                    region=index,
                    regions=total,
                    **info,
                )

            rewritten, meta = _deterministic_target_region_repair(source_text, target_text)
            if rewritten is None:
                rewritten, meta = _translate_source_region(
                    document_id, source_text, client, progress_callback=on_progress
                )
            region["rewrite"] = meta
            if rewritten is None:
                region["status"] = "rewrite_failed"
                result["failed_regions"].append(region)
                result["regions"].append(region)
                print(
                    f"  pass {pass_number} | region {index}/{total}: REWRITE FAILED ({meta.get('reason')})",
                    flush=True,
                )
                continue

            base = p43._union_rect(group)
            expanded = p43._safe_expand_rect(
                target_page, base, all_blocks, {int(item["id"]) for item in group}
            )
            preferred = statistics.median(float(item["font_size"]) for item in group)
            fontsize = p60._fit_font(base, rewritten, preferred, repair_font)
            use_rect = base
            if fontsize is None:
                fontsize = p60._fit_font(expanded, rewritten, preferred, repair_font)
                use_rect = expanded
            if fontsize is None:
                region["status"] = "layout_fit_failed"
                region["bbox"] = [base.x0, base.y0, base.x1, base.y1]
                result["failed_regions"].append(region)
                result["regions"].append(region)
                print(f"  pass {pass_number} | region {index}/{total}: LAYOUT FIT FAILED", flush=True)
                continue

            region.update({
                "status": "ready",
                "bbox": [use_rect.x0, use_rect.y0, use_rect.x1, use_rect.y1],
                "fontsize": fontsize,
                "text": rewritten,
            })
            patches.append(region)
            result["regions"].append(region)
            print(f"  pass {pass_number} | region {index}/{total}: ready", flush=True)

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
                    fontname=p60._REPAIR_FONT_ALIAS,
                    fontfile=str(repair_font),
                    lineheight=1.0,
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                    overlay=True,
                )
                if inserted < 0:
                    raise RuntimeError(
                        f"page {page_number} pass {pass_number} region {patch['index']} failed after fit probe"
                    )
                patch["status"] = "patched"
                result["patched_regions"] += 1
            tmp = target_pdf.with_suffix(f".phase45-pass{pass_number}.tmp.pdf")
            target_doc.save(tmp, garbage=3, deflate=True)
    finally:
        source_doc.close()
        target_doc.close()

    if tmp is not None and tmp.exists():
        tmp.replace(target_pdf)
    return result


def _repair_page(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    client,
    root: Path,
) -> dict:
    page_result = {"page": page_number, "passes": [], "patched_regions": 0}
    for pass_number in (1, 2):
        before = _shared_page_visible_defects(target_pdf, page_number)
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
        page_result["patched_regions"] += int(detail.get("patched_regions", 0) or 0)
        after = _shared_page_visible_defects(target_pdf, page_number)
        detail["visible_after"] = after
        if not any(after.values()):
            break
        if int(detail.get("patched_regions", 0) or 0) == 0:
            break
    page_result["visible_after"] = _shared_page_visible_defects(target_pdf, page_number)
    return page_result


def run(
    document_id: str,
    *,
    export_downloads: bool = True,
    refresh_baseline: bool = False,
) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase45.pdf"
    backup_qa = root / "qa.before-phase45.json"
    if refresh_baseline or not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if refresh_baseline or not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Idempotent retry: restart from the captured baseline.  Production can refresh
    # it explicitly so an old manual Phase45 run can never overwrite a newer full run.
    # before the first Phase45 run, never from a half-patched previous attempt.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = p43._selected_pages(source_qa, target_pdf, source_pdf)

    manifest: dict = {
        "phase": 45,
        "mode": "source-aligned-atomic-defect-repair",
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

    print("===== PHASE45 SOURCE-ALIGNED ATOMIC REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : translate clean source-PDF text at each broken target block; no mixed target rewrite.\n")

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
            print(f"  ACCEPTED: patched_regions={detail['patched_regions']}", flush=True)
        else:
            rejected.append(page_number)
            remaining = sum(len(v) for v in visible_after.values() if isinstance(v, list))
            print(
                f"  REJECTED: patched_regions={detail['patched_regions']} remaining_defects={remaining}",
                flush=True,
            )
        manifest["pages"].append(detail)
        manifest["accepted_pages"] = accepted
        manifest["rejected_pages"] = rejected
        _write_json(root / "manifest.json", manifest)

    author_restoration = m.restore_primary_author_band(source_pdf, target_pdf)
    reference_restoration = m.restore_reference_section(source_pdf, target_pdf)
    postrender_normalization = p60.normalize_pdf(source_pdf, target_pdf)
    _write_json(root / "postrender_normalization.json", postrender_normalization)
    _write_json(m._layout_dir(document_id) / "postrender_normalization.json", postrender_normalization)
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
    final_qa["author_restoration"] = author_restoration
    final_qa["reference_restoration"] = reference_restoration
    final_qa["postrender_normalization"] = postrender_normalization
    if postrender_normalization.get("unresolved"):
        first = (postrender_normalization.get("unresolved") or [{}])[0]
        final_qa.setdefault("warnings", []).insert(0, m._warning(
            "high",
            int(first.get("page") or 0) or None,
            "postrender_normalization_incomplete",
            "Phase45後のPDF描画補正を完全修復できませんでした。",
            "phase45_repair/postrender_normalization.json の unresolved を確認してください。",
        ))
        final_qa["warning_count"] = int(final_qa.get("warning_count", 0) or 0) + 1
        final_qa["high_count"] = int(final_qa.get("high_count", 0) or 0) + 1
        final_qa["quality_gate"] = "fail"
        if final_qa.get("status") == "ok":
            final_qa["status"] = "warning"
    final_qa["phase45_repair"] = manifest
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

    mono_out: Path | None = None
    dual_out: Path | None = None
    qa_out: Path | None = None
    if export_downloads:
        downloads = Path.home() / "Downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        mono_out = downloads / "PeperTranslator_full_ja_PHASE45.pdf"
        dual_out = downloads / "PeperTranslator_full_en-ja_PHASE45.pdf"
        qa_out = downloads / (
            "PeperTranslator_full_QA_PHASE45.json"
            if final_qa.get("quality_gate") == "pass"
            else "PeperTranslator_full_QA_PHASE45_FAILED.json"
        )
        shutil.copy2(target_pdf, mono_out)
        if m._layout_dual_path(document_id).exists():
            shutil.copy2(m._layout_dual_path(document_id), dual_out)
        _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE45 FINAL SUMMARY =====")
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
    if export_downloads:
        print(f"MONO        : {mono_out}")
        print(f"DUAL        : {dual_out}")
        print(f"QA          : {qa_out}")
    else:
        print("EXPORT      : skipped (production-internal repair)")
    return 0 if final_qa.get("quality_gate") == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair remaining English debris from clean source-PDF geometry")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

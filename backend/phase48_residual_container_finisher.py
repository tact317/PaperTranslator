from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
import unicodedata
from collections import Counter
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
    path = m._layout_dir(document_id) / "phase48_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 48, "updated_at": _utc_now(), **payload})


def _visible_defects(pdf_path: Path, page_number: int) -> dict[str, list[str]]:
    return p45._shared_page_visible_defects(pdf_path, page_number)


def _ascii_fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    return value.encode("ascii", "ignore").decode("ascii")


def _latin_tokens(text: str) -> list[str]:
    value = _ascii_fold(text).lower()
    return [token for token in re.findall(r"[a-z][a-z'’-]*", value) if len(token) >= 2]


def _token_overlap(target: list[str], source: list[str]) -> tuple[float, float]:
    if not target or not source:
        return 0.0, 0.0
    tc = Counter(target)
    sc = Counter(source)
    common = sum((tc & sc).values())
    return common / max(1, len(target)), common / max(1, len(source))


def _same_column_record(a: dict, b: dict, page_width: float) -> bool:
    return p46._same_column(a, b, page_width)


def _best_source_anchor(source_lines: list[dict], target_line: dict, page_rect: fitz.Rect) -> tuple[dict | None, dict]:
    """Find the pristine source line by lexical evidence first, geometry second.

    Phase47 still used the target rectangle as the primary source lookup. After several
    successful local rewrites, line wrapping can move inside that rectangle, so the clip
    may contain a neighboring source line. The remaining failures are literal English
    source fragments, which are stronger anchors than geometry. Match those words first.
    """
    target_text = str(target_line.get("text") or "")
    target_tokens = _latin_tokens(target_text)
    target_rect = p46._line_rect(target_line)
    target_seq = " ".join(target_tokens)
    best: tuple[float, dict | None, dict] = (-1e9, None, {})

    for source_line in source_lines:
        source_text = str(source_line.get("text") or "")
        source_tokens = _latin_tokens(source_text)
        if not source_tokens:
            continue
        coverage, precision = _token_overlap(target_tokens, source_tokens)
        source_seq = " ".join(source_tokens)
        substring = bool(target_seq and (target_seq in source_seq or source_seq in target_seq))
        source_rect = p46._line_rect(source_line)
        same_col = _same_column_record(target_line, source_line, float(page_rect.width))
        y_distance = abs(((target_rect.y0 + target_rect.y1) / 2) - ((source_rect.y0 + source_rect.y1) / 2))
        y_score = max(0.0, 1.0 - y_distance / max(24.0, float(page_rect.height) * 0.08))
        x_distance = abs(((target_rect.x0 + target_rect.x1) / 2) - ((source_rect.x0 + source_rect.x1) / 2))
        x_score = max(0.0, 1.0 - x_distance / max(40.0, float(page_rect.width) * 0.18))

        if target_tokens:
            score = coverage * 7.0 + precision * 1.5 + (3.0 if substring else 0.0)
            score += (1.0 if same_col else 0.0) + y_score * 0.7 + x_score * 0.4
        else:
            score = (2.0 if same_col else 0.0) + y_score * 1.5 + x_score

        meta = {
            "score": round(score, 4),
            "coverage": round(coverage, 4),
            "precision": round(precision, 4),
            "substring": substring,
            "same_column": same_col,
            "y_distance": round(y_distance, 2),
            "source_preview": re.sub(r"\s+", " ", source_text)[:220],
        }
        if score > best[0]:
            best = (score, source_line, meta)

    line = best[1]
    meta = best[2]
    if line is None:
        return None, {"reason": "no_source_line"}

    # A long English residue must have lexical support. Mixed Japanese/English repair
    # lines can fall back to close geometry because only one or two English words may
    # remain after earlier phases.
    latin, japanese, words, ratio = p46._line_metrics(target_text)
    if latin >= 18 and words >= 3 and ratio >= 0.5:
        if float(meta.get("coverage", 0.0)) < 0.45:
            return None, {**meta, "reason": "weak_lexical_anchor"}
    elif not bool(meta.get("same_column")) and float(meta.get("y_distance", 9999)) > 18:
        return None, {**meta, "reason": "weak_geometric_anchor"}
    return line, meta


def _column_lines(lines: list[dict], anchor: dict, page_width: float) -> list[dict]:
    anchor_rect = p46._line_rect(anchor)
    preferred = float(anchor.get("font_size") or 8.0)
    candidates: list[dict] = []
    for line in lines:
        if not _same_column_record(anchor, line, page_width):
            continue
        size = float(line.get("font_size") or preferred)
        if preferred > 0 and not (preferred * 0.65 <= size <= preferred * 1.45):
            continue
        rect = p46._line_rect(line)
        # Same-column overlap is more reliable than line-center distance here: a
        # Japanese line is often much shorter than the English line above it even
        # though both start at the same paragraph margin.
        if abs(rect.x0 - anchor_rect.x0) > page_width * 0.12 and p43._horizontal_overlap(rect, anchor_rect) < 0.2:
            continue
        candidates.append(line)
    return sorted(candidates, key=lambda item: (p46._line_rect(item).y0, p46._line_rect(item).x0))


def _container_variant(lines: list[dict], seed: dict, radius: int, page_width: float) -> tuple[list[dict], int, int]:
    column = _column_lines(lines, seed, page_width)
    if not column:
        return [seed], 0, 0
    try:
        index = next(i for i, item in enumerate(column) if int(item["id"]) == int(seed["id"]))
    except StopIteration:
        return [seed], 0, 0

    start = index
    stop = index
    remaining_before = radius
    remaining_after = radius
    while remaining_before > 0 and start > 0:
        prev = column[start - 1]
        cur = column[start]
        if p46._vertical_gap(prev, cur) > 5.8:
            break
        start -= 1
        remaining_before -= 1
    while remaining_after > 0 and stop + 1 < len(column):
        cur = column[stop]
        nxt = column[stop + 1]
        if p46._vertical_gap(cur, nxt) > 5.8:
            break
        stop += 1
        remaining_after -= 1
    group = column[start:stop + 1]
    before_count = index - start
    after_count = stop - index
    return group, before_count, after_count


def _source_container(source_lines: list[dict], anchor: dict, before_count: int, after_count: int, page_width: float) -> list[dict]:
    column = _column_lines(source_lines, anchor, page_width)
    if not column:
        return [anchor]
    try:
        index = next(i for i, item in enumerate(column) if int(item["id"]) == int(anchor["id"]))
    except StopIteration:
        return [anchor]
    start = max(0, index - before_count)
    stop = min(len(column), index + after_count + 1)
    return column[start:stop]


def _fit_font_relaxed(rect: fitz.Rect, text: str, preferred: float) -> float | None:
    fitted = p43._fit_font(rect, text, preferred)
    if fitted is not None:
        return fitted
    width = max(4.0, rect.width)
    height = max(4.0, rect.height)
    size = 4.4
    while size >= 4.0:
        probe_doc = fitz.open()
        try:
            page = probe_doc.new_page(width=width, height=height)
            result = page.insert_textbox(
                fitz.Rect(0, 0, width, height),
                text,
                fontsize=round(size, 2),
                fontname="japan",
                lineheight=1.0,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if result >= 0:
                return round(size, 2)
        finally:
            probe_doc.close()
        size -= 0.2
    return None


def _defect_burden(pdf_path: Path, page_number: int) -> dict:
    defects = _visible_defects(pdf_path, page_number)
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number - 1]
        lines = p46._line_records(page)
        page_has_long = bool(defects.get("long_english_run"))
        latin = 0
        for line in lines:
            text = str(line.get("text") or "")
            if p46._direct_line_defect(text) or (page_has_long and (p46._latin_heavy_line(text) or p46._english_continuation_line(text))):
                latin += m._latin_char_count(text)
    finally:
        doc.close()
    return {
        "long": len(defects.get("long_english_run") or []),
        "short": len(defects.get("short_english_artifact") or []),
        "bad": len(defects.get("bad_term") or []),
        "surface": len(defects.get("scientific_surface_corruption") or []),
        "latin": latin,
    }


def _burden_key(value: dict) -> tuple[int, int, int, int, int]:
    return (
        int(value.get("surface", 0)),
        int(value.get("long", 0)),
        int(value.get("short", 0)) + int(value.get("bad", 0)),
        int(value.get("latin", 0)),
        int(value.get("bad", 0)),
    )


def _candidate_seeds(page: fitz.Page) -> list[dict]:
    lines = p46._line_records(page)
    page_text = p43._clean(page.get_text("text", sort=True))
    page_has_long = bool(m._long_english_runs(page_text))
    seeds: list[dict] = []
    for line in lines:
        text = str(line.get("text") or "")
        if p46._direct_line_defect(text):
            seeds.append(line)
        elif page_has_long and p46._latin_heavy_line(text):
            seeds.append(line)
    # Long English first; then exact short artifacts. This makes the source lexical
    # anchor strongest while the literal English source is still present.
    return sorted(
        seeds,
        key=lambda item: (
            0 if p46._latin_heavy_line(str(item.get("text") or "")) else 1,
            p46._line_rect(item).y0,
            p46._line_rect(item).x0,
        ),
    )


def _translate_container(document_id: str, source_text: str, client, progress_callback=None) -> tuple[str | None, dict]:
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
    meta["mode"] = "lexical-anchor-residual-container"
    meta["target_preview"] = re.sub(r"\s+", " ", translated)[:260]
    if p43._has_defect(translated):
        meta["reason"] = "visible_defect_remains"
        return None, meta
    return translated, meta


def _apply_candidate_patch(
    target_pdf: Path,
    page_number: int,
    target_group: list[dict],
    translated: str,
    preferred_font: float,
) -> tuple[bool, dict]:
    before_text = m._extract_pdf_page_texts(target_pdf)[page_number - 1]
    before_science = p43._science_fingerprint(before_text)
    before_burden = _defect_burden(target_pdf, page_number)

    doc = fitz.open(target_pdf)
    tmp = target_pdf.with_suffix(".phase48-candidate.tmp.pdf")
    try:
        page = doc[page_number - 1]
        all_lines = p46._line_records(page)
        ids = {int(item["id"]) for item in target_group}
        base = p46._union_rect(target_group)
        expanded = p43._safe_expand_rect(page, base, all_lines, ids)
        use_rect = base
        fontsize = _fit_font_relaxed(base, translated, preferred_font)
        if fontsize is None:
            fontsize = _fit_font_relaxed(expanded, translated, preferred_font)
            use_rect = expanded
        if fontsize is None:
            return False, {"reason": "layout_fit_failed"}

        page.add_redact_annot(use_rect, fill=(1, 1, 1))
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
        inserted = page.insert_textbox(
            use_rect,
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
        doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()

    after_text = m._extract_pdf_page_texts(tmp)[page_number - 1]
    after_science = p43._science_fingerprint(after_text)
    after_burden = _defect_burden(tmp, page_number)
    if not p43._science_equal(before_science, after_science):
        tmp.unlink(missing_ok=True)
        return False, {
            "reason": "page_science_changed",
            "before_burden": before_burden,
            "after_burden": after_burden,
        }
    if _burden_key(after_burden) >= _burden_key(before_burden):
        tmp.unlink(missing_ok=True)
        return False, {
            "reason": "no_visible_improvement",
            "before_burden": before_burden,
            "after_burden": after_burden,
        }
    tmp.replace(target_pdf)
    return True, {
        "reason": "",
        "bbox": [use_rect.x0, use_rect.y0, use_rect.x1, use_rect.y1],
        "fontsize": fontsize,
        "before_burden": before_burden,
        "after_burden": after_burden,
    }


def _repair_one_seed(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    seed_id: int,
    client,
    root: Path,
    pass_number: int,
    seed_number: int,
    seed_total: int,
    progress_func=None,
) -> dict:
    if progress_func is None:
        progress_func = _progress
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    try:
        source_page = source_doc[page_number - 1]
        target_page = target_doc[page_number - 1]
        source_lines = p46._line_records(source_page)
        target_lines = p46._line_records(target_page)
        seed = next((item for item in target_lines if int(item["id"]) == int(seed_id)), None)
        if seed is None:
            return {"status": "failed", "reason": "seed_disappeared", "seed_id": seed_id}
        anchor, anchor_meta = _best_source_anchor(source_lines, seed, source_page.rect)
        if anchor is None:
            return {"status": "failed", "reason": anchor_meta.get("reason", "source_anchor_failed"), "anchor": anchor_meta, "seed_id": seed_id}
        seed_text = str(seed.get("text") or "")
        pure_english = p46._latin_heavy_line(seed_text) and m._japanese_char_count(seed_text) <= 2
        radii = (1, 2, 0) if pure_english else (0, 1, 2)
        attempts: list[dict] = []

        for variant_index, radius in enumerate(radii, start=1):
            target_group, before_count, after_count = _container_variant(
                target_lines, seed, radius, float(target_page.rect.width)
            )
            source_group = _source_container(
                source_lines, anchor, before_count, after_count, float(source_page.rect.width)
            )
            source_text = p45._prepare_source_text(p46._line_text(source_group))
            if not source_text:
                attempts.append({"radius": radius, "reason": "empty_source_container"})
                continue

            def on_progress(info: dict) -> None:
                parts = [
                    f"  pass {pass_number}",
                    f"seed {seed_number}/{seed_total}",
                    f"container {variant_index}/{len(radii)}",
                    str(info.get("stage") or "working"),
                ]
                if info.get("batch") is not None and info.get("batches") is not None:
                    parts.append(f"batch {info['batch']}/{info['batches']}")
                if info.get("attempt") is not None:
                    parts.append(f"attempt {info['attempt']}/{info.get('max_attempts') or 4}")
                if info.get("reason"):
                    parts.append(f"reason={info['reason']}")
                print(" | ".join(parts), flush=True)
                progress_payload = dict(info)
                progress_payload.update({
                    "status": "running",
                    "stage": str(info.get("stage") or "working"),
                    "page": page_number,
                    "pass_number": pass_number,
                    "seed": seed_number,
                    "seeds": seed_total,
                    "container": variant_index,
                    "containers": len(radii),
                    "radius": radius,
                })
                progress_func(root, **progress_payload)

            translated, meta = _translate_container(
                document_id,
                source_text,
                client,
                progress_callback=on_progress,
            )
            if translated is None:
                attempts.append({
                    "radius": radius,
                    "target_line_ids": [int(item["id"]) for item in target_group],
                    "source_line_ids": [int(item["id"]) for item in source_group],
                    "rewrite": meta,
                    "reason": meta.get("reason") or "rewrite_failed",
                })
                continue

            preferred = statistics.median(float(item.get("font_size") or 8.0) for item in target_group)
            target_doc.close()
            source_doc.close()
            ok, patch_meta = _apply_candidate_patch(
                target_pdf,
                page_number,
                target_group,
                translated,
                preferred,
            )
            if ok:
                return {
                    "status": "patched",
                    "seed_id": seed_id,
                    "seed_preview": re.sub(r"\s+", " ", seed_text)[:220],
                    "anchor": anchor_meta,
                    "radius": radius,
                    "target_line_ids": [int(item["id"]) for item in target_group],
                    "source_line_ids": [int(item["id"]) for item in source_group],
                    "source_preview": re.sub(r"\s+", " ", source_text)[:260],
                    "rewrite": meta,
                    **patch_meta,
                }
            attempts.append({
                "radius": radius,
                "target_line_ids": [int(item["id"]) for item in target_group],
                "source_line_ids": [int(item["id"]) for item in source_group],
                "rewrite": meta,
                **patch_meta,
            })
            # Re-open for another variant because _apply_candidate_patch works on its
            # own candidate copy and closes all handles before returning.
            source_doc = fitz.open(source_pdf)
            target_doc = fitz.open(target_pdf)
            source_page = source_doc[page_number - 1]
            target_page = target_doc[page_number - 1]
            source_lines = p46._line_records(source_page)
            target_lines = p46._line_records(target_page)
            seed = next((item for item in target_lines if int(item["id"]) == int(seed_id)), seed)
            anchor, anchor_meta = _best_source_anchor(source_lines, seed, source_page.rect)
            if anchor is None:
                break

        return {
            "status": "failed",
            "seed_id": seed_id,
            "seed_preview": re.sub(r"\s+", " ", seed_text)[:220],
            "anchor": anchor_meta,
            "attempts": attempts,
            "reason": attempts[-1].get("reason", "repair_failed") if attempts else "repair_failed",
        }
    finally:
        try:
            source_doc.close()
        except Exception:
            pass
        try:
            target_doc.close()
        except Exception:
            pass


def _repair_page(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    client,
    root: Path,
    progress_func=None,
) -> dict:
    if progress_func is None:
        progress_func = _progress
    result = {"page": page_number, "passes": [], "patched_containers": 0}
    for pass_number in range(1, 9):
        failed_signatures: set[str] = set()
        before = _visible_defects(target_pdf, page_number)
        if not any(before.values()):
            break
        doc = fitz.open(target_pdf)
        try:
            seeds = _candidate_seeds(doc[page_number - 1])
        finally:
            doc.close()
        pass_detail = {"pass": pass_number, "seed_count": len(seeds), "seeds": []}
        result["passes"].append(pass_detail)
        if not seeds:
            break

        patched_this_pass = 0
        for seed_number, seed in enumerate(seeds, start=1):
            signature = re.sub(r"\s+", " ", str(seed.get("text") or "")).strip().lower()
            if signature in failed_signatures:
                continue
            print(f"  pass {pass_number} | seed {seed_number}/{len(seeds)}: lexical source anchor", flush=True)
            progress_func(
                root,
                status="running",
                stage="source_anchor",
                page=page_number,
                pass_number=pass_number,
                seed=seed_number,
                seeds=len(seeds),
            )
            detail = _repair_one_seed(
                document_id,
                source_pdf,
                target_pdf,
                page_number,
                int(seed["id"]),
                client,
                root,
                pass_number,
                seed_number,
                len(seeds),
                progress_func=progress_func,
            )
            pass_detail["seeds"].append(detail)
            if detail.get("status") == "patched":
                patched_this_pass += 1
                result["patched_containers"] += 1
                # Geometry / line IDs may change after an accepted patch. Restart from
                # a fresh line extraction instead of applying stale seed IDs.
                break
            failed_signatures.add(signature)

        pass_detail["patched_containers"] = patched_this_pass
        pass_detail["visible_after"] = _visible_defects(target_pdf, page_number)
        if not any(pass_detail["visible_after"].values()):
            break
        if patched_this_pass == 0:
            break

    result["visible_after"] = _visible_defects(target_pdf, page_number)
    return result


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase48.pdf"
    backup_qa = root / "qa.before-phase48.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Preserve every accepted / partial improvement through Phase47. Reruns are
    # idempotent from the exact pre-Phase48 artifact, not from an older phase.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = p43._selected_pages(source_qa, target_pdf, source_pdf)

    manifest: dict = {
        "phase": 48,
        "mode": "lexical-anchor-residual-container-repair",
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

    print("===== PHASE48 LEXICAL-ANCHOR RESIDUAL CONTAINER REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : match each remaining English line to the pristine source by words, then rewrite a 1/3/5-line container.\n")

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
            print(f"  ACCEPTED: patched_containers={detail['patched_containers']}", flush=True)
        else:
            rejected.append(page_number)
            remaining = sum(len(v) for v in visible_after.values() if isinstance(v, list))
            print(f"  REJECTED: patched_containers={detail['patched_containers']} remaining_defects={remaining}", flush=True)
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
    final_qa["phase48_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE48.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE48.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE48.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE48_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE48 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Lexical-anchor residual container repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

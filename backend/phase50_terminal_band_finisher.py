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
from backend import phase48_residual_container_finisher as p48


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
    path = m._layout_dir(document_id) / "phase50_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 50, "updated_at": _utc_now(), **payload})


def _visible_defects(pdf_path: Path, page_number: int) -> dict[str, list[str]]:
    return p45._shared_page_visible_defects(pdf_path, page_number)


def _warning_anchor(item: dict) -> str:
    message = str(item.get("message") or "")
    if "残っています:" in message:
        return message.split("残っています:", 1)[1].strip()
    if ":" in message:
        return message.rsplit(":", 1)[-1].strip()
    return message.strip()


def _critical_long_anchors(qa: dict) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for item in qa.get("warnings") or []:
        if not isinstance(item, dict):
            continue
        if item.get("severity") != "critical" or item.get("code") != "long_english_run":
            continue
        page = item.get("page")
        if not isinstance(page, int) or page < 1:
            continue
        anchor = _warning_anchor(item)
        if anchor:
            result.setdefault(page, []).append(anchor)
    return result


def _anchor_score(anchor: str, line_text: str) -> float:
    a = p48._latin_tokens(anchor)
    b = p48._latin_tokens(line_text)
    if not a or not b:
        return 0.0
    coverage, precision = p48._token_overlap(a, b)
    aseq = " ".join(a)
    bseq = " ".join(b)
    substring = bool(aseq and (aseq in bseq or bseq in aseq))
    return coverage * 8.0 + precision * 2.0 + (4.0 if substring else 0.0)


def _best_target_seed(page: fitz.Page, anchor: str) -> tuple[dict | None, dict]:
    lines = p46._line_records(page)
    best_score = 0.0
    best: dict | None = None
    for line in lines:
        score = _anchor_score(anchor, str(line.get("text") or ""))
        if score > best_score:
            best_score = score
            best = line
    if best is None or best_score < 3.5:
        return None, {"reason": "target_anchor_not_found", "score": round(best_score, 4), "anchor": anchor[:220]}
    return best, {
        "score": round(best_score, 4),
        "anchor": anchor[:220],
        "target_preview": re.sub(r"\s+", " ", str(best.get("text") or ""))[:220],
    }


def _full_column_band(page: fitz.Page, group: list[dict], seed: dict) -> fitz.Rect:
    lines = p46._line_records(page)
    column = p48._column_lines(lines, seed, float(page.rect.width))
    base = p46._union_rect(group)
    if column:
        x0 = min(p46._line_rect(item).x0 for item in column)
        x1 = max(p46._line_rect(item).x1 for item in column)
    else:
        x0, x1 = base.x0, base.x1
    # Keep the repair strictly inside the page and only widen the horizontal band.
    # A little vertical padding scrubs duplicate/overlapping text-layer spans that
    # can survive a line-tight redaction even after the visible text was replaced.
    pad_y = max(1.2, statistics.median(float(item.get("font_size") or 8.0) for item in group) * 0.16)
    return fitz.Rect(
        max(page.rect.x0 + 1.0, x0 - 1.5),
        max(page.rect.y0 + 1.0, base.y0 - pad_y),
        min(page.rect.x1 - 1.0, x1 + 1.5),
        min(page.rect.y1 - 1.0, base.y1 + pad_y),
    )


def _fit_in_band(rect: fitz.Rect, text: str, preferred: float) -> float | None:
    # Start from the original font and allow a modest reduction.  The band variants
    # grow vertically before we ever go below a readable 4 pt floor.
    size = min(float(preferred), 9.0)
    while size >= 4.0:
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
    defects = _visible_defects(pdf_path, page_number)
    pages = m._extract_pdf_page_texts(pdf_path)
    text = pages[page_number - 1] if 0 < page_number <= len(pages) else ""
    return (
        len(defects.get("scientific_surface_corruption") or []),
        len(defects.get("long_english_run") or []),
        len(defects.get("short_english_artifact") or []) + len(defects.get("bad_term") or []),
        m._latin_char_count(text),
    )


def _apply_band_candidate(
    target_pdf: Path,
    page_number: int,
    target_group: list[dict],
    seed: dict,
    translated: str,
    preferred: float,
) -> tuple[bool, dict]:
    before_text = m._extract_pdf_page_texts(target_pdf)[page_number - 1]
    before_science = p43._science_fingerprint(before_text)
    before_burden = _page_burden(target_pdf, page_number)

    doc = fitz.open(target_pdf)
    tmp = target_pdf.with_suffix(".phase50-candidate.tmp.pdf")
    try:
        page = doc[page_number - 1]
        band = _full_column_band(page, target_group, seed)
        fontsize = _fit_in_band(band, translated, preferred)
        if fontsize is None:
            return False, {"reason": "layout_fit_failed", "bbox": [band.x0, band.y0, band.x1, band.y1]}
        page.add_redact_annot(band, fill=(1, 1, 1))
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
        inserted = page.insert_textbox(
            band,
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
    if after_burden >= before_burden:
        tmp.unlink(missing_ok=True)
        return False, {"reason": "no_visible_improvement", "before_burden": before_burden, "after_burden": after_burden}
    tmp.replace(target_pdf)
    return True, {
        "reason": "",
        "bbox": [band.x0, band.y0, band.x1, band.y1],
        "fontsize": fontsize,
        "before_burden": before_burden,
        "after_burden": after_burden,
    }


def _repair_anchor(
    document_id: str,
    source_pdf: Path,
    target_pdf: Path,
    page_number: int,
    anchor_text: str,
    client,
    root: Path,
    anchor_index: int,
    anchor_total: int,
) -> dict:
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    try:
        source_page = source_doc[page_number - 1]
        target_page = target_doc[page_number - 1]
        seed, seed_meta = _best_target_seed(target_page, anchor_text)
        if seed is None:
            return {"status": "failed", "reason": seed_meta.get("reason"), "anchor": seed_meta}
        source_lines = p46._line_records(source_page)
        target_lines = p46._line_records(target_page)
        source_anchor, source_meta = p48._best_source_anchor(source_lines, seed, source_page.rect)
        if source_anchor is None:
            return {"status": "failed", "reason": source_meta.get("reason", "source_anchor_failed"), "anchor": seed_meta, "source_anchor": source_meta}

        # Phase48 already tried 1/3/5-line boxes.  The terminal fallback deliberately
        # takes over a wider paragraph band (3/5/7/9 lines) and wipes the full text
        # column across that y-range, which also removes duplicate hidden text spans.
        radii = (1, 2, 3, 4)
        attempts: list[dict] = []
        for variant_index, radius in enumerate(radii, start=1):
            target_group, before_count, after_count = p48._container_variant(
                target_lines, seed, radius, float(target_page.rect.width)
            )
            source_group = p48._source_container(
                source_lines, source_anchor, before_count, after_count, float(source_page.rect.width)
            )
            source_text = p45._prepare_source_text(p46._line_text(source_group))
            if not source_text:
                attempts.append({"radius": radius, "reason": "empty_source_container"})
                continue

            def on_progress(info: dict) -> None:
                payload = dict(info)
                payload.update({
                    "status": "running",
                    "stage": str(info.get("stage") or "working"),
                    "page": page_number,
                    "anchor": anchor_index,
                    "anchors": anchor_total,
                    "container": variant_index,
                    "containers": len(radii),
                    "radius": radius,
                })
                _progress(root, **payload)
                parts = [
                    f"  anchor {anchor_index}/{anchor_total}",
                    f"container {variant_index}/{len(radii)}",
                    str(info.get("stage") or "working"),
                ]
                if info.get("batch") is not None and info.get("batches") is not None:
                    parts.append(f"batch {info['batch']}/{info['batches']}")
                if info.get("attempt") is not None:
                    parts.append(f"attempt {info['attempt']}/{info.get('max_attempts') or 2}")
                if info.get("reason"):
                    parts.append(f"reason={info['reason']}")
                print(" | ".join(parts), flush=True)

            translated, rewrite_meta = p45._translate_source_region(
                document_id,
                source_text,
                client,
                progress_callback=on_progress,
            )
            if translated is None:
                attempts.append({"radius": radius, "reason": rewrite_meta.get("reason", "rewrite_failed"), "rewrite": rewrite_meta})
                continue

            preferred = statistics.median(float(item.get("font_size") or 8.0) for item in target_group)
            source_doc.close()
            target_doc.close()
            ok, patch_meta = _apply_band_candidate(
                target_pdf,
                page_number,
                target_group,
                seed,
                translated,
                preferred,
            )
            if ok:
                return {
                    "status": "patched",
                    "anchor_text": anchor_text,
                    "target_anchor": seed_meta,
                    "source_anchor": source_meta,
                    "radius": radius,
                    "source_preview": re.sub(r"\s+", " ", source_text)[:320],
                    "rewrite": rewrite_meta,
                    **patch_meta,
                }
            attempts.append({"radius": radius, "reason": patch_meta.get("reason", "patch_failed"), "rewrite": rewrite_meta, **patch_meta})

            source_doc = fitz.open(source_pdf)
            target_doc = fitz.open(target_pdf)
            source_page = source_doc[page_number - 1]
            target_page = target_doc[page_number - 1]
            source_lines = p46._line_records(source_page)
            target_lines = p46._line_records(target_page)
            seed, seed_meta = _best_target_seed(target_page, anchor_text)
            if seed is None:
                break
            source_anchor, source_meta = p48._best_source_anchor(source_lines, seed, source_page.rect)
            if source_anchor is None:
                break

        return {
            "status": "failed",
            "anchor_text": anchor_text,
            "target_anchor": seed_meta,
            "source_anchor": source_meta,
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
    anchors: list[str],
    client,
    root: Path,
) -> dict:
    result = {"page": page_number, "anchors": [], "patched_bands": 0}
    # Re-evaluate after every accepted patch because the exact warning line may move
    # or disappear when a full-column band is regenerated.
    for index, anchor in enumerate(anchors, start=1):
        before = _visible_defects(target_pdf, page_number)
        if not before.get("long_english_run"):
            break
        print(f"  terminal anchor {index}/{len(anchors)}: {anchor[:90]}", flush=True)
        _progress(root, status="running", stage="anchor_start", page=page_number, anchor=index, anchors=len(anchors))
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
        result["anchors"].append(detail)
        if detail.get("status") == "patched":
            result["patched_bands"] += 1
    result["visible_after"] = _visible_defects(target_pdf, page_number)
    return result


def run(document_id: str) -> int:
    source_pdf = m._cached_pdf_path(document_id)
    target_pdf = m._layout_mono_path(document_id)
    qa_path = m._layout_qa_path(document_id)
    if not target_pdf.exists() or not qa_path.exists():
        raise RuntimeError("translated PDF / QA report was not found")

    root = _root(document_id)
    backup_pdf = root / "translated-mono.before-phase50.pdf"
    backup_qa = root / "qa.before-phase50.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    page_anchors = _critical_long_anchors(source_qa)
    pages = sorted(page_anchors)

    manifest: dict = {
        "phase": 50,
        "mode": "qa-anchored-full-column-terminal-band-repair",
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

    print("===== PHASE50 QA-ANCHORED TERMINAL BAND REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : use the exact remaining Postflight line as an anchor, then replace a wider full-column source-aligned band.\n")

    client = m.ollama.Client(host=m.OLLAMA_HOST)
    accepted: list[int] = []
    rejected: list[int] = []
    for page_pos, page_number in enumerate(pages, start=1):
        print(f"[page {page_number}] page {page_pos}/{len(pages)}", flush=True)
        _progress(root, status="running", stage="page_start", page=page_number, page_index=page_pos, pages=len(pages))
        detail = _repair_page(document_id, source_pdf, target_pdf, page_number, page_anchors[page_number], client, root)
        visible = detail.get("visible_after") or {}
        page_ok = not any(visible.values())
        if page_ok:
            accepted.append(page_number)
            print(f"  ACCEPTED: patched_bands={detail['patched_bands']}", flush=True)
        else:
            rejected.append(page_number)
            remaining = sum(len(v) for v in visible.values() if isinstance(v, list))
            print(f"  REJECTED: patched_bands={detail['patched_bands']} remaining_defects={remaining}", flush=True)
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
    final_qa["phase50_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE50.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE50.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE50.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE50_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE50 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="QA-anchored full-column terminal band repair")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

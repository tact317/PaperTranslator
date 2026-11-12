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
    path = m._layout_dir(document_id) / "phase46_repair"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _progress(root: Path, **payload) -> None:
    _write_json(root / "progress.json", {"phase": 46, "updated_at": _utc_now(), **payload})


def _line_records(page: fitz.Page) -> list[dict]:
    """Extract rendered text lines instead of coarse PDF blocks.

    Phase45 still repaired whole blocks.  On the real paper, a single PDF block can
    contain both valid Japanese and dozens of untranslated English lines.  The final
    QA is line/text driven, so Phase46 works at the same visual granularity.
    """
    payload = page.get_text("dict", sort=True)
    records: list[dict] = []
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            text = p43._clean(text)
            if not text:
                continue
            rect = fitz.Rect(line.get("bbox"))
            if rect.is_empty or rect.width < 1 or rect.height < 1:
                continue
            sizes: list[float] = []
            for span in spans:
                try:
                    size = float(span.get("size") or 0)
                except Exception:
                    size = 0
                if size > 0:
                    sizes.append(size)
            records.append({
                "id": len(records),
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                "text": text,
                "font_size": statistics.median(sizes) if sizes else 8.0,
            })
    return sorted(records, key=lambda item: (round(fitz.Rect(item["bbox"]).y0, 1), fitz.Rect(item["bbox"]).x0))


def _line_rect(record: dict) -> fitz.Rect:
    return fitz.Rect(record["bbox"])


def _line_metrics(text: str) -> tuple[int, int, int, float]:
    latin = m._latin_char_count(text)
    japanese = m._japanese_char_count(text)
    words = len(re.findall(r"\b[A-Za-z][A-Za-z'’.-]*\b", text or ""))
    ratio = latin / max(1, latin + japanese)
    return latin, japanese, words, ratio


def _latin_heavy_line(text: str) -> bool:
    latin, _jp, words, ratio = _line_metrics(text)
    return latin >= 18 and words >= 3 and ratio >= 0.50


def _english_continuation_line(text: str) -> bool:
    """Include short wrap tails such as ``was constrained.`` in a long repair."""
    latin, japanese, words, ratio = _line_metrics(text)
    return latin >= 5 and words >= 1 and japanese <= 1 and ratio >= 0.70


def _direct_line_defect(text: str) -> bool:
    if m._long_english_runs(text) or m._short_english_artifact_hits(text):
        return True
    if any(bad.lower() in (text or "").lower() for bad, _ in m._LAYOUT_BAD_TERMS):
        return True
    return bool(m._scientific_surface_artifact_hits(text))


def _same_column(a: dict, b: dict, page_width: float) -> bool:
    ra, rb = _line_rect(a), _line_rect(b)
    overlap = max(0.0, min(ra.x1, rb.x1) - max(ra.x0, rb.x0))
    overlap_ratio = overlap / max(1.0, min(ra.width, rb.width))
    if overlap_ratio >= 0.25:
        return True
    ca = (ra.x0 + ra.x1) / 2
    cb = (rb.x0 + rb.x1) / 2
    return abs(ca - cb) <= page_width * 0.13


def _vertical_gap(a: dict, b: dict) -> float:
    ra, rb = _line_rect(a), _line_rect(b)
    if ra.y1 < rb.y0:
        return rb.y0 - ra.y1
    if rb.y1 < ra.y0:
        return ra.y0 - rb.y1
    return 0.0


def _line_text(records: list[dict]) -> str:
    return "\n".join(str(item.get("text") or "") for item in records).strip()


def _split_group(records: list[dict], max_lines: int = 9, max_chars: int = 1800) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    chars = 0
    for record in records:
        length = len(str(record.get("text") or ""))
        if current and (len(current) >= max_lines or chars + length > max_chars):
            groups.append(current)
            current = []
            chars = 0
        current.append(record)
        chars += length
    if current:
        groups.append(current)
    return groups


def _candidate_line_windows(page: fitz.Page) -> list[list[dict]]:
    lines = _line_records(page)
    if not lines:
        return []

    page_text = p43._clean(page.get_text("text", sort=True))
    page_has_long = bool(m._long_english_runs(page_text))
    page_width = float(page.rect.width)

    long_ids: set[int] = set()
    if page_has_long:
        # Seed with clearly English-looking lines.  Grow only through similarly
        # Latin-heavy lines in the same column; Japanese lines are never pulled into
        # a long-English repair window just because they are nearby.
        seeds = [line for line in lines if _latin_heavy_line(line["text"])]
        for seed in seeds:
            component = [seed]
            changed = True
            while changed:
                changed = False
                for other in lines:
                    if other["id"] in {item["id"] for item in component}:
                        continue
                    if not (_latin_heavy_line(other["text"]) or _english_continuation_line(other["text"])):
                        continue
                    if any(_same_column(other, item, page_width) and _vertical_gap(other, item) <= 5.5 for item in component):
                        component.append(other)
                        changed = True
            component = sorted(component, key=lambda item: (_line_rect(item).y0, _line_rect(item).x0))
            component_text = _line_text(component)
            if m._long_english_runs(component_text):
                long_ids.update(int(item["id"]) for item in component)

    windows: list[list[dict]] = []
    used: set[int] = set()

    # Turn long English components into bounded visual windows.  This keeps source
    # order/context while avoiding another page/block-sized rewrite.
    remaining = {int(item["id"]): item for item in lines if int(item["id"]) in long_ids}
    while remaining:
        seed_id = next(iter(remaining))
        component = [remaining.pop(seed_id)]
        changed = True
        while changed:
            changed = False
            for rid, other in list(remaining.items()):
                if any(_same_column(other, item, page_width) and _vertical_gap(other, item) <= 5.5 for item in component):
                    component.append(remaining.pop(rid))
                    changed = True
        component = sorted(component, key=lambda item: (_line_rect(item).y0, _line_rect(item).x0))
        for chunk in _split_group(component):
            windows.append(chunk)
            used.update(int(item["id"]) for item in chunk)

    # Add exact short-artifact/bad-term lines not already covered by a long window.
    # A single mixed Japanese line is small enough to rewrite safely and is exactly
    # the granularity final Postflight later evaluates.
    for line in lines:
        rid = int(line["id"])
        if rid in used:
            continue
        if _direct_line_defect(line["text"]):
            windows.append([line])
            used.add(rid)

    return sorted(windows, key=lambda group: (_line_rect(group[0]).y0, _line_rect(group[0]).x0))


def _union_rect(records: list[dict]) -> fitz.Rect:
    rect = fitz.Rect(records[0]["bbox"])
    for record in records[1:]:
        rect |= fitz.Rect(record["bbox"])
    return rect


def _cleanup_tiny_by_artifact(text: str) -> str:
    """Remove only the trivial lower-case ``by`` residue in already-Japanese lines.

    This is deliberately not used on English phrases such as ``discussed by Badia``;
    those contain several Latin words and must be translated by the model as a whole.
    """
    value = text or ""
    if not re.search(r"[ぁ-んァ-ヶ一-龯]", value):
        return value
    english_words = re.findall(r"\b[A-Za-z][A-Za-z'’.-]*\b", value)
    lower_words = [word.lower() for word in english_words]
    if lower_words.count("by") != 1 or len(english_words) > 2:
        return value
    value = re.sub(r"([（(])\s*by\s*(?=\[\d)", r"\1", value)
    value = re.sub(r"(?<![A-Za-z])by\s+(?=(?:方程式|式)\b)", "", value)
    value = re.sub(r"(?<![A-Za-z])by(?![A-Za-z])", "により", value)
    return re.sub(r"\s+([、。）」】])", r"\1", value)


def _translate_window(document_id: str, text: str, client, progress_callback=None) -> tuple[str | None, dict]:
    source = p43._clean(text)
    if not source:
        return None, {"reason": "empty_window", "attempts": 0}

    # Cheap deterministic cleanup solves isolated citation/connector debris without
    # asking Qwen to rewrite an otherwise-good Japanese line.
    deterministic = _cleanup_tiny_by_artifact(source)
    if deterministic != source and not p43._has_defect(deterministic):
        if p43._science_equal(p43._science_fingerprint(source), p43._science_fingerprint(deterministic)):
            return deterministic, {
                "mode": "deterministic_tiny_artifact_cleanup",
                "attempts": 0,
                "source_preview": re.sub(r"\s+", " ", source)[:240],
                "target_preview": re.sub(r"\s+", " ", deterministic)[:240],
            }

    terms = list(m._guard_terms_for_document(document_id))
    protected, mapping = m.protect_translation_segment(source, terms)
    model = m._preferred_translation_model()
    system = m._load_translation_prompt(model)
    restored, _protected_out, ok, rescue = m._translate_repair_last_mile(
        client,
        model,
        system,
        protected,
        mapping,
        progress_callback=progress_callback,
    )
    meta = {
        "mode": "target_line_window_placeholder_free",
        **(rescue or {}),
        "protected": len(mapping),
        "source_preview": re.sub(r"\s+", " ", source)[:240],
    }
    if not ok:
        return None, meta

    restored = m._repair_known_translation_terms(m._repair_scientific_surface_artifacts(restored))
    restored = _cleanup_tiny_by_artifact(restored)
    meta["target_preview"] = re.sub(r"\s+", " ", restored)[:240]

    if m._simplified_chinese_hits(restored) or m._foreign_language_hits(restored):
        meta["reason"] = "language_leak"
        return None, meta
    if p43._has_defect(restored):
        meta["reason"] = "visible_defect_remains"
        return None, meta
    if not p43._science_equal(p43._science_fingerprint(source), p43._science_fingerprint(restored)):
        meta["reason"] = "science_changed"
        return None, meta
    if m._latin_char_count(source) >= 20 and m._japanese_char_count(restored) < 2:
        meta["reason"] = "not_japanese_enough"
        return None, meta
    return restored, meta


def _repair_page_pass(
    document_id: str,
    target_pdf: Path,
    page_number: int,
    client,
    root: Path,
    pass_number: int,
) -> dict:
    doc = fitz.open(target_pdf)
    tmp: Path | None = None
    try:
        page = doc[page_number - 1]
        all_lines = _line_records(page)
        windows = _candidate_line_windows(page)
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
        total = len(windows)
        for index, window in enumerate(windows, start=1):
            text = _line_text(window)
            print(f"  pass {pass_number} | window {index}/{total}: prepare", flush=True)
            _progress(
                root,
                status="running",
                page=page_number,
                pass_number=pass_number,
                window=index,
                windows=total,
                stage="prepare",
            )

            def on_progress(info: dict) -> None:
                parts = [f"  pass {pass_number}", f"window {index}/{total}", str(info.get("stage") or "working")]
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
                    window=index,
                    windows=total,
                    **info,
                )

            rewritten, meta = _translate_window(document_id, text, client, progress_callback=on_progress)
            record = {
                "index": index - 1,
                "line_ids": [int(item["id"]) for item in window],
                "source_preview": re.sub(r"\s+", " ", text)[:260],
                "rewrite": meta,
            }
            if rewritten is None:
                record["status"] = "rewrite_failed"
                result["failed_windows"].append(record)
                result["windows"].append(record)
                print(f"  pass {pass_number} | window {index}/{total}: REWRITE FAILED ({meta.get('reason')})", flush=True)
                continue

            base = _union_rect(window)
            ids = {int(item["id"]) for item in window}
            expanded = p43._safe_expand_rect(page, base, all_lines, ids)
            preferred = statistics.median(float(item.get("font_size") or 8.0) for item in window)
            fontsize = p43._fit_font(base, rewritten, preferred)
            use_rect = base
            if fontsize is None:
                fontsize = p43._fit_font(expanded, rewritten, preferred)
                use_rect = expanded
            if fontsize is None:
                record["status"] = "layout_fit_failed"
                record["bbox"] = [base.x0, base.y0, base.x1, base.y1]
                result["failed_windows"].append(record)
                result["windows"].append(record)
                print(f"  pass {pass_number} | window {index}/{total}: LAYOUT FIT FAILED", flush=True)
                continue

            record.update({
                "status": "ready",
                "bbox": [use_rect.x0, use_rect.y0, use_rect.x1, use_rect.y1],
                "fontsize": fontsize,
                "text": rewritten,
            })
            patches.append(record)
            result["windows"].append(record)
            print(f"  pass {pass_number} | window {index}/{total}: ready", flush=True)

        if patches:
            for patch in patches:
                page.add_redact_annot(fitz.Rect(patch["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            for patch in patches:
                inserted = page.insert_textbox(
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
                        f"page {page_number} pass {pass_number} window {patch['index']} failed after fit probe"
                    )
                patch["status"] = "patched"
                result["patched_windows"] += 1
            tmp = target_pdf.with_suffix(f".phase46-pass{pass_number}.tmp.pdf")
            doc.save(tmp, garbage=3, deflate=True)
    finally:
        doc.close()

    if tmp is not None and tmp.exists():
        tmp.replace(target_pdf)
    return result


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


def _repair_page(document_id: str, target_pdf: Path, page_number: int, client, root: Path) -> dict:
    page_result = {"page": page_number, "passes": [], "patched_windows": 0}
    for pass_number in (1, 2):
        before = _visible_defects(target_pdf, page_number)
        if not any(before.values()):
            break
        detail = _repair_page_pass(document_id, target_pdf, page_number, client, root, pass_number)
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
    backup_pdf = root / "translated-mono.before-phase46.pdf"
    backup_qa = root / "qa.before-phase46.json"
    if not backup_pdf.exists():
        shutil.copy2(target_pdf, backup_pdf)
    if not backup_qa.exists():
        shutil.copy2(qa_path, backup_qa)

    # Phase46 intentionally starts from the Phase45 artifact so the already accepted
    # p.2/p.12 repairs are preserved.  Reruns are idempotent from this snapshot.
    shutil.copy2(backup_pdf, target_pdf)
    source_qa = _load_json(backup_qa)
    pages, reasons = p43._selected_pages(source_qa, target_pdf, source_pdf)

    manifest: dict = {
        "phase": 46,
        "mode": "target-line-window-repair",
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

    print("===== PHASE46 DEFECT-LINE WINDOW REPAIR =====")
    print(f"DOCUMENT: {document_id}")
    print("PAGES   : " + (", ".join(map(str, pages)) if pages else "none"))
    print("Mode    : repair only final-QA-visible lines/windows; no whole page or block retranslation.\n")

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
        detail = _repair_page(document_id, target_pdf, page_number, client, root)
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
    final_qa["phase46_repair"] = manifest
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
    mono_out = downloads / "PeperTranslator_full_ja_PHASE46.pdf"
    dual_out = downloads / "PeperTranslator_full_en-ja_PHASE46.pdf"
    qa_out = downloads / (
        "PeperTranslator_full_QA_PHASE46.json"
        if final_qa.get("quality_gate") == "pass"
        else "PeperTranslator_full_QA_PHASE46_FAILED.json"
    )
    shutil.copy2(target_pdf, mono_out)
    if m._layout_dual_path(document_id).exists():
        shutil.copy2(m._layout_dual_path(document_id), dual_out)
    _write_json(qa_out, final_qa)

    severe = [
        item for item in (final_qa.get("warnings") or [])
        if isinstance(item, dict) and item.get("severity") in {"critical", "high"}
    ]
    print("\n===== PHASE46 FINAL SUMMARY =====")
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
    parser = argparse.ArgumentParser(description="Repair only final-QA-visible PDF line windows")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    document_id = args.document_id.strip() or _latest_document_id()
    return run(document_id)


if __name__ == "__main__":
    sys.exit(main())

"""Best-effort Japanese reading translation using the installed translation engine.

The strict layout translation quality gate is intentionally separate and unchanged.
This module does not accept a blank/English-only translation as successful Japanese.
"""
import re

_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def _valid_translation(source, translation):
    value = str(translation or "").strip()
    return bool(value and _JAPANESE.search(value) and value != str(source).strip())


def translate_batch_best_effort(batch, translate):
    """Translate a batch; retry only missing/invalid items individually.

    Return (ordered_segments, issues). An unresolved item remains visible, marked
    with original English rather than silently omitted or falsely claimed translated.
    """
    received = {}
    issues = []
    try:
        returned = translate(batch)
        if not isinstance(returned, list):
            raise ValueError("Batch translation did not return a list")
        for item in returned:
            if isinstance(item, dict) and "id" in item:
                received[item["id"]] = item
    except Exception as exc:
        issues.append({"kind": "batch_retry", "segment_ids": [s["id"] for s in batch],
                       "error": f"{type(exc).__name__}: {str(exc)[:350]}"})

    output = []
    for source in batch:
        sid = source["id"]
        candidate = received.get(sid)
        target = str((candidate or {}).get("translation") or "").strip()
        if not _valid_translation(source["sourceText"], target):
            try:
                single = translate([source])
                if not isinstance(single, list):
                    raise ValueError("Single-segment translation is not a list")
                candidate = next((x for x in single if isinstance(x, dict) and x.get("id") == sid), None)
                target = str((candidate or {}).get("translation") or "").strip()
                if not _valid_translation(source["sourceText"], target):
                    raise ValueError("No usable Japanese text for the segment")
            except Exception as exc:
                issues.append({"kind": "untranslated_segment", "segment_id": sid,
                               "page": source["pageRef"], "source": source["sourceText"],
                               "error": f"{type(exc).__name__}: {str(exc)[:350]}"})
                target = "\u3010\u672a\u7ffb\u8a33\u30fb\u8981\u78ba\u8a8d\u3011 " + source["sourceText"]
                output.append({**source, "translation": target, "needs_review": True})
                continue
        output.append({**source, "translation": target, "needs_review": False})
    return output, issues

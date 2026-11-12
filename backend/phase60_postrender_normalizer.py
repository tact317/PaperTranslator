from __future__ import annotations

import os
import re
import shutil
import statistics
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

# Longest-first so ``mm`` is not consumed as ``m``.
_UNIT_RE = r"keV|MeV|GeV|Hz|mm|cm|µm|μm|um|nm|T|K|A|G|m|h|s|°|%"
_MEASUREMENT_RE = re.compile(
    rf"(?<![A-Za-z0-9.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*({_UNIT_RE})(?![A-Za-z])"
)
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))(?![A-Za-z0-9.])")
_JP_RE = re.compile(r"[ぁ-んァ-ヶ一-龯]")

_REPAIR_FONT_ENV = "PEPERTRANSLATOR_REPAIR_FONT_FILE"
_REPAIR_FONT_ALIAS = "PTRepairSerif"


def _font_has_repair_glyphs(path: Path) -> bool:
    """Return True only for a real Unicode font usable for mixed JP/science text."""
    try:
        font = fitz.Font(fontfile=str(path))
    except Exception:
        return False
    try:
        # Japanese body text plus the scientific glyphs that Phase60-64 may insert.
        if not all(font.has_glyph(ord(ch)) for ch in "日RMS10µ°"):
            return False
        # Reject CJK-monospace / full-width Latin metrics. The exact bug this phase
        # fixes is visually wide ASCII inside an otherwise Japanese repair line.
        advances = [float(font.glyph_advance(ord(ch))) for ch in "RMS10"]
        return max(advances) - min(advances) >= 0.08 and sum(advances) / len(advances) < 0.9
    except Exception:
        return False


def _repair_font_candidates() -> list[Path]:
    """Return local proportional Japanese font candidates without bundling a font."""
    candidates: list[Path] = []
    override = (os.getenv(_REPAIR_FONT_ENV) or "").strip()
    if override:
        candidates.append(Path(override))

    windir = Path(os.getenv("WINDIR") or "C:/Windows")
    win_fonts = windir / "Fonts"
    for name in (
        "yumin.ttf",
        "yuminl.ttf",
        "yumindb.ttf",
        "meiryo.ttc",
        "meiryoB.ttc",
        "msmincho.ttc",
        "YuGothR.ttc",
        "YuGothM.ttc",
    ):
        candidates.append(win_fonts / name)
    for pattern in (
        "yumin*.ttf", "*YuMincho*.ttf", "*YuMincho*.ttc",
        "meiryo*.ttc", "msmincho*.ttc", "YuGoth*.ttc",
    ):
        try:
            candidates.extend(sorted(win_fonts.glob(pattern)))
        except Exception:
            pass

    local_app = (os.getenv("LOCALAPPDATA") or "").strip()
    if local_app:
        user_fonts = Path(local_app) / "Microsoft" / "Windows" / "Fonts"
        for pattern in (
            "*NotoSerifCJK*.otf", "*NotoSerifCJK*.ttc", "*NotoSerifCJK*.ttf",
            "*SourceHanSerif*.otf", "*SourceHanSerif*.ttc", "*SourceHanSerif*.ttf",
            "*YuMincho*.ttf", "*YuMincho*.ttc",
        ):
            try:
                candidates.extend(sorted(user_fonts.glob(pattern)))
            except Exception:
                pass

    # Development / non-Windows fallbacks. These are only referenced when already
    # installed on the host; no font binaries are shipped in the package.
    candidates.extend([
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ])
    return candidates


def resolve_proportional_repair_font() -> Path | None:
    """Find a local proportional Unicode font for post-render line replacement.

    PyMuPDF's built-in ``japan`` font is reliable for glyph coverage but uses CJK
    fallback metrics for Latin digits and symbols. Re-rendered mixed scientific
    lines can therefore show ``R M S``, ``1 0 µm`` or ``6 . 1°`` even when the
    extracted text is correct. Prefer an installed proportional Japanese font and
    fail the repair rather than silently shipping that visual corruption.
    """
    seen: set[str] = set()
    for candidate in _repair_font_candidates():
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file() and _font_has_repair_glyphs(candidate):
                return candidate
        except Exception:
            continue
    return None


def _repair_font_name(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(fitz.Font(fontfile=str(path)).name)
    except Exception:
        return path.name



def normalize_pdf_inline_separators(text: str) -> str:
    """Map non-semantic PDF control/format separators to ordinary spaces.

    BabelDOC/PyMuPDF can expose span boundaries as control characters such as
    ``\x01``.  For scientific-token detection those separators are layout
    metadata, not content: ``1\x01T`` is the same visible measurement as
    ``1 T``. Flat-string detectors use this helper; span-aware re-rendering uses
    :func:`visible_pdf_span_text` so true symbol-font glyphs such as ``°`` are
    not mistaken for separators.
    """
    value = text or ""
    return "".join(
        " " if unicodedata.category(ch) in {"Cc", "Cf"} else ch
        for ch in value
    )


def visible_pdf_span_text(span: dict) -> str:
    """Return the text that a PDF span is intended to show on the page.

    Two different things can be serialized as control characters in the PDFs
    handled by this project:

    * BabelDOC span separators such as ``\x01``. They are layout metadata and
      should become an ordinary space when a line is re-rendered.
    * Publisher symbol-font glyphs. In the IHEP paper ``AdvMT_SY`` exposes the
      rendered degree sign as ``\x06``. That glyph is semantic content and must
      become ``°`` rather than being erased as a generic control character.

    Keep this conversion span-aware. A flat string alone cannot distinguish the
    two cases safely.
    """
    raw = str(span.get("text") or "")
    font = str(span.get("font") or "")
    if re.search(r"(?:^|[-_])MT[-_]?SY(?:$|[-_])|AdvMT_SY", font, re.IGNORECASE):
        raw = raw.replace("\x06", "°")
    return "".join(
        " " if unicodedata.category(ch) in {"Cc", "Cf"} else ch
        for ch in raw
    )


def _page_visible_text(page: fitz.Page) -> str:
    """Flatten one PDF page using span-aware visible character semantics."""
    payload = page.get_text("dict", sort=True)
    lines: list[str] = []
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(visible_pdf_span_text(span) for span in line.get("spans", []))
            if text.strip():
                lines.append(text)
    return "\n".join(lines)


def scalar_duplicate_unit_artifact_hits(text: str) -> list[str]:
    """Return impossible repeated scalar-unit artifacts after separator folding."""
    normalized = normalize_pdf_inline_separators(text)
    number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
    hits: list[str] = []
    for unit in ("T", "A", "G", "K", "°", "%"):
        pattern = rf"(?<![A-Za-z0-9.]){number}\s*{re.escape(unit)}\s*{re.escape(unit)}(?![A-Za-z])"
        if re.search(pattern, normalized):
            hits.append(f"duplicate_scalar_unit_{unit}")
    return hits




def _source_visual_unit_overrides(page: fitz.Page) -> list[dict]:
    """Detect source text-layer unit mappings contradicted by the rendered glyph font.

    Some publisher PDFs use a symbol font for the micro sign but declare the font as
    WinAnsi without a ToUnicode map. PyMuPDF then extracts the symbol glyph as ``m``.
    A rendered ``10 µm`` therefore becomes text-layer ``10 mm``.  Do not guess from
    the letters alone: require a very specific structural witness inside one source
    line -- a symbol/Pi-font span extracted as ``m`` immediately followed by a normal
    ``m`` span, with a scalar directly before it.  This is evidence that the first
    extracted ``m`` is a non-text symbol glyph, not a real metre prefix.
    """
    payload = page.get_text("dict", sort=False)
    overrides: list[dict] = []
    number_re = re.compile(r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$")
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if str(span.get("text") or "")]
            if len(spans) < 2:
                continue
            for index, span in enumerate(spans):
                raw = str(span.get("text") or "")
                font = str(span.get("font") or "")
                # The faulty extraction is seen in symbol/Pi fonts, e.g. AdvPi1.
                if raw.strip() != "m" or not re.search(r"(?:pi|symbol)", font, re.IGNORECASE):
                    continue
                previous_text = "".join(str(item.get("text") or "") for item in spans[:index])
                following_text = "".join(str(item.get("text") or "") for item in spans[index + 1:])
                if not re.match(r"^m(?![A-Za-z])", following_text.lstrip()):
                    continue
                number_match = number_re.search(previous_text)
                if not number_match:
                    continue
                bbox = line.get("bbox") or span.get("bbox") or ()
                if len(bbox) != 4:
                    continue
                overrides.append({
                    "number": _normalize_number(number_match.group(1)),
                    "text_layer_unit": "mm",
                    "visual_unit": "µm",
                    "bbox": [float(value) for value in bbox],
                    "source_font": font,
                    "evidence": "symbol_font_m_plus_regular_m",
                })
    return overrides


def _replace_measurement_unit_once(text: str, number: str, old_unit: str, new_unit: str) -> tuple[str, bool]:
    """Replace one exact scalar unit while preserving PDF separator characters."""
    raw_number = re.escape(number)
    separators = r"[\s\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u206f]*"
    pattern = re.compile(
        rf"(?<![\d.])({raw_number})({separators})({re.escape(old_unit)})(?![A-Za-z])"
    )
    match = pattern.search(text or "")
    if not match:
        return text or "", False
    repaired = (text or "")[:match.start(3)] + new_unit + (text or "")[match.end(3):]
    return repaired, True


def _apply_source_visual_unit_overrides(lines: list[dict], overrides: list[dict]) -> dict[int, list[dict]]:
    """Bind source visual/text mismatches to the geometrically nearest target line."""
    applied: dict[int, list[dict]] = {}
    used_lines: set[tuple[int, str, str]] = set()
    for override in overrides:
        number = str(override.get("number") or "")
        old_unit = str(override.get("text_layer_unit") or "")
        new_unit = str(override.get("visual_unit") or "")
        if not number or not old_unit or not new_unit:
            continue
        sx0, sy0, sx1, sy1 = [float(v) for v in override.get("bbox", [0, 0, 0, 0])]
        candidates: list[tuple[float, int, str]] = []
        for line_index, line in enumerate(lines):
            before = str(line.get("text") or "")
            _, found = _replace_measurement_unit_once(before, number, old_unit, new_unit)
            if not found or (line_index, number, old_unit) in used_lines:
                continue
            tx0, ty0, tx1, ty1 = [float(v) for v in line.get("bbox", [0, 0, 0, 0])]
            # Layout translation largely preserves columns and vertical placement.
            # Favor same-column candidates, then nearest baseline.
            source_cx = (sx0 + sx1) / 2.0
            target_cx = (tx0 + tx1) / 2.0
            score = abs(ty0 - sy0) + 0.18 * abs(target_cx - source_cx)
            candidates.append((score, line_index, before))
        if not candidates:
            continue
        _, line_index, before = min(candidates, key=lambda item: item[0])
        after, found = _replace_measurement_unit_once(before, number, old_unit, new_unit)
        if not found:
            continue
        lines[line_index].setdefault("original_text", before)
        lines[line_index]["text"] = after
        used_lines.add((line_index, number, old_unit))
        applied.setdefault(line_index, []).append({
            "reason": "source_visual_unit_override",
            "number": number,
            "text_layer_unit": old_unit,
            "visual_unit": new_unit,
            "source_font": override.get("source_font"),
            "evidence": override.get("evidence"),
        })
    return applied

def _normalize_number(value: str) -> str:
    value = (value or "").strip().replace("−", "-").replace("–", "-")
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return str(int(number))
    return (f"{number:.12f}").rstrip("0").rstrip(".")


def _normalize_unit(unit: str) -> str:
    if unit in {"μm", "um"}:
        return "µm"
    return unit


def _measurement_counter(text: str) -> Counter[tuple[str, str]]:
    out: Counter[tuple[str, str]] = Counter()
    normalized = normalize_pdf_inline_separators(text)
    for match in _MEASUREMENT_RE.finditer(normalized):
        out[(_normalize_number(match.group(1)), _normalize_unit(match.group(2)))] += 1
    return out


def _repair_known_lexical_residue(text: str) -> tuple[str, list[str]]:
    repaired = text or ""
    reasons: list[str] = []
    rules = (
        (r"クイ\s*ENCH", "クエンチ", "mixed_quench"),
        (r"ス\s*ledge", "スレッド", "mixed_sledge"),
        (r"ス\s*led(?![A-Za-z])", "スレッド", "mixed_sled"),
    )
    for pattern, replacement, reason in rules:
        updated = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)
        if updated != repaired:
            repaired = updated
            reasons.append(reason)

    # Raw English forms are deterministic only inside an otherwise Japanese line.
    if _JP_RE.search(repaired):
        updated = re.sub(r"(?<![A-Za-z])quench(?:es|ed|ing)?(?![A-Za-z])", "クエンチ", repaired, flags=re.IGNORECASE)
        if updated != repaired:
            repaired = updated
            reasons.append("raw_quench_in_japanese")
        updated = re.sub(r"(?<![A-Za-z])sledge(?![A-Za-z])", "スレッド", repaired, flags=re.IGNORECASE)
        if updated != repaired:
            repaired = updated
            reasons.append("raw_sledge_in_japanese")
    return repaired, reasons


def _repair_duplicate_unit_names(text: str) -> tuple[str, list[str]]:
    repaired = text or ""
    reasons: list[str] = []
    for pattern, replacement, reason in (
        (r"(?<![A-Za-z])((?:\d+(?:\.\d+)?|\.\d+)\s*A)\s*アンペア", r"\1", "duplicate_ampere"),
        (r"(?<![A-Za-z])((?:\d+(?:\.\d+)?|\.\d+)\s*m)\s*メートル", r"\1", "duplicate_meter"),
        (r"(?<![A-Za-z])((?:\d+(?:\.\d+)?|\.\d+)\s*mm)\s*ミリメートル", r"\1", "duplicate_millimeter"),
    ):
        updated = re.sub(pattern, replacement, repaired)
        if updated != repaired:
            repaired = updated
            reasons.append(reason)
    return repaired, reasons


def _repair_impossible_surface_duplicates(text: str) -> tuple[str, list[str]]:
    """Collapse duplicate scientific typography without changing values.

    Postflight already treats serial scalar units and duplicated length-unit glyphs
    as impossible surface corruption.  Phase72 could detect these but the Phase60
    materialized-PDF normalizer did not repair the same grammar, so an isolated
    Phase41 retry could reproduce the defect and be rejected forever.  Keep one
    canonical repair path here, where the visible line is redrawn and re-verified.
    """
    # Preserve PDF internal separators unless a proven duplicate is actually
    # collapsed.  Phase62 deliberately treats characters such as ``\x01`` as
    # non-visible adjacency for QA, but materializing them as spaces here would
    # mutate otherwise-correct measurements such as ``1\x01T``.
    repaired = text or ""
    reasons: list[str] = []
    sep = r"[\s\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u2060\ufeff]*"

    for unit in ("mm", "cm", "nm", "um", "µm", "μm"):
        patterns = (
            rf"(?i)(?<![A-Za-z])(?:{re.escape(unit)}{sep}){{2,}}(?![A-Za-z])",
            rf"(?i)\b({re.escape(unit)}){sep}\1\b",
        )
        for pattern in patterns:
            updated, count = re.subn(pattern, lambda m, u=unit: u, repaired)
            if count:
                repaired = updated
                reasons.extend([f"duplicate_surface_unit_{unit}"] * count)

    number = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
    for unit in ("T", "A", "G", "K", "°", "%"):
        pattern = rf"(?<![A-Za-z0-9.])({number}){sep}{re.escape(unit)}{sep}{re.escape(unit)}(?![A-Za-z])"
        updated, count = re.subn(pattern, lambda m, u=unit: f"{m.group(1)} {u}", repaired)
        if count:
            repaired = updated
            reasons.extend([f"duplicate_scalar_unit_{unit}"] * count)

    for pattern, replacement, reason in (
        (r"([×xX])\s*\1+", r"\1", "duplicate_multiply"),
        (r"(?<![<>=!])=\s*=(?![=])", "=", "duplicate_equal"),
        (r"≈\s*=", "≈", "duplicate_approx_equal"),
    ):
        updated, count = re.subn(pattern, replacement, repaired)
        if count:
            repaired = updated
            reasons.extend([reason] * count)
    return repaired, reasons


def _repair_ordinal_unit_leak(text: str) -> tuple[str, list[str]]:
    """Remove a measurement unit inserted after a Japanese ordinal.

    A Phase59 per-chunk repair could see source ``1 T`` and target ``第1`` in the
    same chunk and incorrectly create ``第1 Tおよび第2磁場積分``.  Restrict the
    cleanup to unmistakable ordinal syntax: another ordinal follows, or the token is
    immediately followed by an ordinal noun such as ``積分``/``溝``/``章``.
    """
    repaired = text or ""
    reasons: list[str] = []
    pattern = re.compile(
        rf"第\s*(\d+(?:\.\d+)?)\s*({_UNIT_RE})\s*(?=(?:および|及び|ならびに|または|と)\s*第|(?:磁場)?積分|溝|コイル|章|節|項)"
    )
    updated, count = pattern.subn(lambda m: f"第{m.group(1)}", repaired)
    if count:
        repaired = updated
        reasons.extend(["ordinal_unit_leak"] * count)
    return repaired, reasons


def _preceding_context(text: str, start: int, width: int = 28) -> str:
    return (text or "")[max(0, start - width):start]


def _following_context(text: str, end: int, width: int = 22) -> str:
    return (text or "")[end:min(len(text or ""), end + width)]


def _ordinal_or_label_context(text: str, start: int) -> bool:
    prefix = _preceding_context(text, start, 12)
    if re.search(r"(?:第|図|表|式|節|章|項|No\.?|Fig\.?|Table)\s*$", prefix, re.IGNORECASE):
        return True
    return False


def _unit_context_compatible(unit: str, text: str, start: int, end: int) -> bool:
    context = (_preceding_context(text, start, 34) + " " + _following_context(text, end, 26)).lower()
    unit = _normalize_unit(unit)
    if unit in {"T", "G"}:
        return bool(re.search(r"磁場|ピーク|field|tesla|gauss", context, re.IGNORECASE))
    if unit == "A":
        return bool(re.search(r"電流|current", context, re.IGNORECASE))
    if unit == "K":
        return bool(re.search(r"温度|冷却|液体ヘリウム|ヘリウム|temperature|cool|helium", context, re.IGNORECASE))
    if unit in {"m", "mm", "cm", "µm", "nm"}:
        return bool(re.search(r"長さ|長|幅|高さ|厚|径|直径|ギャップ|距離|間隔|ステップ|残差|誤差|rms|length|width|height|gap|distance|step|residual|error", context, re.IGNORECASE))
    if unit == "°":
        return bool(re.search(r"角|位相|誤差|phase|roll|angle", context, re.IGNORECASE))
    if unit == "%":
        return bool(re.search(r"割合|パーセント|偏差|percentage|deviation|percent", context, re.IGNORECASE))
    if unit in {"Hz", "keV", "MeV", "GeV"}:
        return True
    return False


def _missing_measurement_deficits(source_text: str, target_text: str) -> Counter[tuple[str, str]]:
    source = _measurement_counter(source_text)
    target = _measurement_counter(target_text)
    return source - target


def _repair_missing_units(text: str, deficits: Counter[tuple[str, str]]) -> tuple[str, list[dict]]:
    """Restore only context-supported, source-backed missing units in one visible line."""
    value = text or ""
    if not deficits:
        return value, []
    replacements: list[tuple[int, int, str, dict]] = []
    for match in _NUMBER_RE.finditer(value):
        number = _normalize_number(match.group(1))
        if _ordinal_or_label_context(value, match.start()):
            continue
        tail = normalize_pdf_inline_separators(value[match.end():match.end() + 18])
        if re.match(rf"\s*(?:{_UNIT_RE})(?![A-Za-z])", tail):
            continue
        candidates = [unit for (n, unit), count in deficits.items() if n == number and count > 0]
        candidates = sorted(set(candidates))
        if len(candidates) != 1:
            continue
        unit = candidates[0]
        # Post-render unit restoration must stay extremely conservative.
        # Length units (m/mm/cm/um/nm) frequently appear in table headers,
        # axis labels and separately positioned spans.  Global source/target
        # deficits cannot reliably prove that a visually bare number is
        # missing its unit, and Phase60 could therefore turn an existing
        # ``15 mm`` into ``15 mm mm``.  Only restore scalar units whose
        # surrounding Japanese context provides a strong semantic binding.
        if unit not in {"T", "A", "G", "K", "°", "%"}:
            continue
        if not _unit_context_compatible(unit, value, match.start(), match.end()):
            continue
        replacements.append((match.start(), match.end(), f"{match.group(1)} {unit}", {
            "reason": "missing_unit_restored",
            "number": number,
            "unit": unit,
        }))
        deficits[(number, unit)] -= 1

    if not replacements:
        return value, []
    repaired = value
    details: list[dict] = []
    for start, end, replacement, detail in reversed(replacements):
        repaired = repaired[:start] + replacement + repaired[end:]
        details.append(detail)
    details.reverse()
    return repaired, details


def normalize_visible_line(text: str, deficits: Counter[tuple[str, str]] | None = None) -> tuple[str, list[dict]]:
    repaired = text or ""
    details: list[dict] = []

    repaired2, reasons = _repair_known_lexical_residue(repaired)
    if repaired2 != repaired:
        details.extend({"reason": reason} for reason in reasons)
        repaired = repaired2

    repaired2, reasons = _repair_duplicate_unit_names(repaired)
    if repaired2 != repaired:
        details.extend({"reason": reason} for reason in reasons)
        repaired = repaired2

    repaired2, reasons = _repair_impossible_surface_duplicates(repaired)
    if repaired2 != repaired:
        details.extend({"reason": reason} for reason in reasons)
        repaired = repaired2

    repaired2, reasons = _repair_ordinal_unit_leak(repaired)
    if repaired2 != repaired:
        details.extend({"reason": reason} for reason in reasons)
        repaired = repaired2

    if deficits is not None:
        repaired2, unit_details = _repair_missing_units(repaired, deficits)
        if repaired2 != repaired:
            details.extend(unit_details)
            repaired = repaired2

    return repaired, details


def _line_records(page: fitz.Page) -> list[dict]:
    payload = page.get_text("dict", sort=True)
    records: list[dict] = []
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(visible_pdf_span_text(span) for span in spans).strip()
            if not text:
                continue
            rect = fitz.Rect(line.get("bbox"))
            if rect.is_empty or rect.width < 1 or rect.height < 1:
                continue
            sizes = []
            for span in spans:
                try:
                    size = float(span.get("size") or 0)
                except Exception:
                    size = 0.0
                if size > 0:
                    sizes.append(size)
            records.append({
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                "text": text,
                "font_size": statistics.median(sizes) if sizes else 8.0,
            })
    return sorted(records, key=lambda item: (round(item["bbox"][1], 1), item["bbox"][0]))


def _fit_font(rect: fitz.Rect, text: str, preferred: float, fontfile: Path) -> float | None:
    size = min(max(4.6, preferred), 10.5)
    while size >= 3.8:
        probe = fitz.open()
        try:
            page = probe.new_page(width=max(8.0, rect.width), height=max(8.0, rect.height))
            result = page.insert_textbox(
                fitz.Rect(0, 0, rect.width, rect.height),
                text,
                fontsize=round(size, 2),
                fontname=_REPAIR_FONT_ALIAS,
                fontfile=str(fontfile),
                lineheight=1.0,
                align=fitz.TEXT_ALIGN_LEFT,
            )
            if result >= 0:
                return round(size, 2)
        finally:
            probe.close()
        size -= 0.2
    return None


def _normalized_target_text_for_deficits(lines: list[dict]) -> str:
    normalized: list[str] = []
    for item in lines:
        text, _ = _repair_ordinal_unit_leak(str(item.get("text") or ""))
        text, _ = _repair_duplicate_unit_names(text)
        normalized.append(text)
    return "\n".join(normalized)


def _measurement_occurrences(text: str, unit_filter: str | None = None) -> list[tuple[str, str]]:
    """Return normalized scalar/unit pairs in textual order."""
    normalized = normalize_pdf_inline_separators(text)
    result: list[tuple[str, str]] = []
    for match in _MEASUREMENT_RE.finditer(normalized):
        number = _normalize_number(match.group(1))
        unit = _normalize_unit(match.group(2))
        if unit_filter is None or unit == unit_filter:
            result.append((number, unit))
    return result


def _repair_detached_decimal_degree_tails(lines: list[dict], source_text: str) -> dict[int, list[dict]]:
    """Repair a decimal degree value split into integer prose + orphan tail glyph.

    BabelDOC can place a style placeholder *inside* a decimal scalar. A source
    ``6.1°`` may then reconstruct as Japanese prose containing bare ``6`` plus a
    detached styled ``1°`` later on the next visual line. This pass is deliberately
    narrow: it activates only when source evidence, bare integer candidates and
    orphan fractional degree tails form the same ordered one-to-one mapping.

    It therefore does not invent scientific values and does not rewrite ordinary
    integer degree measurements.
    """
    source_degrees = [
        number for number, unit in _measurement_occurrences(source_text, "°")
        if "." in number
    ]
    if not source_degrees:
        return {}

    target_text = "\n".join(str(item.get("text") or "") for item in lines)
    target_degrees = Counter(number for number, unit in _measurement_occurrences(target_text, "°"))
    source_counter = Counter(source_degrees)
    missing: list[str] = []
    remaining = source_counter - target_degrees
    for number in source_degrees:
        if remaining[number] > 0:
            missing.append(number)
            remaining[number] -= 1
    if not missing:
        return {}

    bare_candidates: list[tuple[int, re.Match[str]]] = []
    for line_index, line in enumerate(lines):
        text = str(line.get("text") or "")
        context = text
        if line_index > 0:
            context = str(lines[line_index - 1].get("text") or "") + " " + context
        if not re.search(r"位相|角|phase|angle|error", context, re.IGNORECASE):
            continue
        for match in re.finditer(r"(?<![A-Za-z0-9.])(\d+)(?![A-Za-z0-9.])", text):
            if _ordinal_or_label_context(text, match.start()):
                continue
            tail = text[match.end():match.end() + 4]
            if re.match(r"\s*°", tail):
                continue
            bare_candidates.append((line_index, match))

    orphan_tails: list[tuple[int, re.Match[str]]] = []
    tail_pattern = re.compile(r"(?<![\d.])(\d+)\s*°(?![A-Za-z])")
    for line_index, line in enumerate(lines):
        text = str(line.get("text") or "")
        for match in tail_pattern.finditer(text):
            orphan_tails.append((line_index, match))

    pairs: list[tuple[str, tuple[int, re.Match[str]], tuple[int, re.Match[str]]]] = []
    used_bare: set[int] = set()
    used_tail: set[int] = set()
    for source_number in missing:
        whole, fraction = source_number.split(".", 1)
        bare_choice = None
        for index, candidate in enumerate(bare_candidates):
            if index in used_bare:
                continue
            if candidate[1].group(1) == whole:
                bare_choice = (index, candidate)
                break
        if bare_choice is None:
            return {}
        bare_pos, bare = bare_choice

        tail_choice = None
        for index, candidate in enumerate(orphan_tails):
            if index in used_tail:
                continue
            if candidate[1].group(1) != fraction:
                continue
            bare_line = lines[bare[0]]
            tail_line = lines[candidate[0]]
            bx0, by0, bx1, by1 = [float(v) for v in bare_line.get("bbox", [0, 0, 0, 0])]
            tx0, ty0, tx1, ty1 = [float(v) for v in tail_line.get("bbox", [0, 0, 0, 0])]
            line_height = max(1.0, by1 - by0, ty1 - ty0)
            if candidate[0] < bare[0] or ty0 - by0 > 2.2 * line_height:
                continue
            if abs(tx0 - bx0) > 42.0 and candidate[0] != bare[0]:
                continue
            tail_choice = (index, candidate)
            break
        if tail_choice is None:
            return {}

        tail_pos, tail = tail_choice
        used_bare.add(bare_pos)
        used_tail.add(tail_pos)
        pairs.append((source_number, bare, tail))

    if len(pairs) != len(missing):
        return {}

    # Apply replacements from right to left per line so match offsets remain valid.
    replacements: dict[int, list[tuple[int, int, str, dict]]] = {}
    for source_number, (bare_line_index, bare_match), (tail_line_index, tail_match) in pairs:
        replacements.setdefault(bare_line_index, []).append((
            bare_match.start(1),
            bare_match.end(1),
            f"{source_number}°",
            {
                "reason": "detached_decimal_degree_restored",
                "number": source_number,
                "unit": "°",
            },
        ))
        replacements.setdefault(tail_line_index, []).append((
            tail_match.start(),
            tail_match.end(),
            "",
            {
                "reason": "detached_decimal_degree_tail_removed",
                "number": source_number,
                "unit": "°",
            },
        ))

    details_by_line: dict[int, list[dict]] = {}
    for line_index, items in replacements.items():
        before = str(lines[line_index].get("text") or "")
        after = before
        details: list[dict] = []
        for start, end, replacement, detail in sorted(items, key=lambda row: row[0], reverse=True):
            after = after[:start] + replacement + after[end:]
            details.append(detail)
        # Removing orphan tails may leave doubled/trailing spaces after punctuation.
        after = re.sub(r"(?<=[。．.!?])\s+$", "", after)
        after = re.sub(r" {2,}", " ", after)
        if after != before:
            lines[line_index].setdefault("original_text", before)
            lines[line_index]["text"] = after
            details_by_line[line_index] = list(reversed(details))
    return details_by_line


def normalize_pdf(source_pdf: Path, target_pdf: Path) -> dict:
    """Apply deterministic cleanup after BabelDOC has materialized the PDF.

    The crucial distinction from Phase59 is timing: mixed-script residues can be
    created only after separately translated/styled PDF spans are reassembled.  A
    pre-render string normalizer cannot see them.  This pass works on the actual
    rendered text lines that Postflight will inspect.
    """
    source_pdf = Path(source_pdf)
    target_pdf = Path(target_pdf)
    repair_font = resolve_proportional_repair_font()
    report: dict = {
        "mode": "phase65-proportional-postrender-typography",
        "repair_font": {
            "available": repair_font is not None,
            "name": _repair_font_name(repair_font),
            "file": repair_font.name if repair_font is not None else None,
            "source": "local-system-font",
        },
        "source_visual_text_consistency": [],
        "patched_pages": [],
        "patches": [],
        "unresolved": [],
    }
    source_doc = fitz.open(source_pdf)
    target_doc = fitz.open(target_pdf)
    tmp = target_pdf.with_suffix(".phase60-normalized.tmp.pdf")
    try:
        page_count = min(len(source_doc), len(target_doc))
        for page_index in range(page_count):
            source_page = source_doc[page_index]
            page = target_doc[page_index]
            source_text = _page_visible_text(source_page)
            lines = _line_records(page)
            if not lines:
                continue
            source_visual_overrides = _source_visual_unit_overrides(source_page)
            if source_visual_overrides:
                report["source_visual_text_consistency"].extend(
                    {"page": page_index + 1, **item} for item in source_visual_overrides
                )
            visual_line_details = _apply_source_visual_unit_overrides(lines, source_visual_overrides)
            detached_degree_details = _repair_detached_decimal_degree_tails(lines, source_text)
            target_for_deficits = _normalized_target_text_for_deficits(lines)
            deficits = _missing_measurement_deficits(source_text, target_for_deficits)
            page_patches: list[dict] = []
            for line_index, line in enumerate(lines):
                before_original = str(line.get("original_text") or line.get("text") or "")
                before = str(line.get("text") or "")
                after, details = normalize_visible_line(before, deficits)
                if line_index in visual_line_details:
                    details = list(visual_line_details[line_index]) + details
                if line_index in detached_degree_details:
                    details = list(detached_degree_details[line_index]) + details
                if after == before_original:
                    continue
                rect = fitz.Rect(line["bbox"])
                # A tiny horizontal allowance avoids needless font shrink when a unit
                # such as ``T``/``A`` is restored. Never invade another column.
                rect = fitz.Rect(
                    max(page.rect.x0 + 0.5, rect.x0 - 0.3),
                    max(page.rect.y0 + 0.5, rect.y0 - 0.45),
                    min(page.rect.x1 - 0.5, rect.x1 + 3.0),
                    min(page.rect.y1 - 0.5, rect.y1 + 0.45),
                )
                if repair_font is None:
                    report["unresolved"].append({
                        "page": page_index + 1,
                        "reason": "proportional_repair_font_unavailable",
                        "before": before,
                        "after": after,
                        "details": details,
                        "environment_override": _REPAIR_FONT_ENV,
                    })
                    continue
                fontsize = _fit_font(rect, after, float(line.get("font_size") or 8.0), repair_font)
                if fontsize is None:
                    report["unresolved"].append({
                        "page": page_index + 1,
                        "reason": "layout_fit_failed",
                        "before": before,
                        "after": after,
                        "details": details,
                    })
                    continue
                page_patches.append({
                    "page": page_index + 1,
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "before": before_original,
                    "after": after,
                    "font_size": fontsize,
                    "render_font": _repair_font_name(repair_font),
                    "render_font_file": repair_font.name if repair_font is not None else None,
                    "details": details,
                })

            if not page_patches:
                continue
            for patch in page_patches:
                page.add_redact_annot(fitz.Rect(patch["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            for patch in page_patches:
                inserted = page.insert_textbox(
                    fitz.Rect(patch["bbox"]),
                    patch["after"],
                    fontsize=float(patch["font_size"]),
                    fontname=_REPAIR_FONT_ALIAS,
                    fontfile=str(repair_font),
                    lineheight=1.0,
                    color=(0, 0, 0),
                    align=fitz.TEXT_ALIGN_LEFT,
                    overlay=True,
                )
                if inserted < 0:
                    report["unresolved"].append({
                        **patch,
                        "reason": "insert_failed",
                    })
                    continue
                report["patches"].append(patch)
            report["patched_pages"].append(page_index + 1)

        target_doc.save(tmp, garbage=4, clean=True, deflate=True)
    finally:
        source_doc.close()
        target_doc.close()

    if tmp.exists():
        tmp.replace(target_pdf)

    # Re-read the real output and record remaining deterministic defects.  QA still
    # makes the final pass/fail decision; this report is diagnostic evidence only.
    verify = fitz.open(target_pdf)
    try:
        patches_by_page: dict[int, list[dict]] = {}
        for patch in report.get("patches", []):
            patches_by_page.setdefault(int(patch.get("page") or 0), []).append(patch)
        for page_index, page in enumerate(verify, start=1):
            # Verify the actual font materialized in every Phase65 replacement
            # region. A silent fallback to PyMuPDF's built-in ``Gothic`` would
            # recreate the wide Latin/scientific glyphs that this phase fixes.
            if page_index in patches_by_page:
                payload = page.get_text("dict", sort=False)
                for patch in patches_by_page[page_index]:
                    patch_rect = fitz.Rect(patch.get("bbox") or (0, 0, 0, 0))
                    fonts: set[str] = set()
                    for block in payload.get("blocks", []):
                        if block.get("type") != 0:
                            continue
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                bbox = span.get("bbox")
                                if not bbox:
                                    continue
                                span_rect = fitz.Rect(bbox)
                                if patch_rect.intersects(span_rect):
                                    font = str(span.get("font") or "")
                                    if font:
                                        fonts.add(font)
                    patch["verified_render_fonts"] = sorted(fonts)
                    if any(font.lower() == "gothic" for font in fonts):
                        report["unresolved"].append({
                            "page": page_index,
                            "reason": "non_proportional_patch_font_materialized",
                            "fonts": sorted(fonts),
                            "text": patch.get("after"),
                        })

            for line in _line_records(page):
                text = str(line.get("text") or "")
                lexical, _ = _repair_known_lexical_residue(text)
                ordinal, _ = _repair_ordinal_unit_leak(text)
                duplicate, _ = _repair_duplicate_unit_names(text)
                scalar_duplicates = scalar_duplicate_unit_artifact_hits(text)
                if lexical != text:
                    report["unresolved"].append({"page": page_index, "reason": "lexical_residue_remains", "text": text})
                if ordinal != text:
                    report["unresolved"].append({"page": page_index, "reason": "ordinal_unit_leak_remains", "text": text})
                if duplicate != text:
                    report["unresolved"].append({"page": page_index, "reason": "duplicate_unit_name_remains", "text": text})
                if scalar_duplicates:
                    report["unresolved"].append({
                        "page": page_index,
                        "reason": "duplicate_scalar_unit_remains",
                        "artifacts": scalar_duplicates,
                        "text": text,
                    })
    finally:
        verify.close()

    report["patched_pages"] = sorted(set(report["patched_pages"]))
    return report

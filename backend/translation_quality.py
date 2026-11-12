from __future__ import annotations

import csv
import re
from pathlib import Path

import fitz


REFERENCE_HEADINGS = ("References", "REFERENCES")
TARGET_REFERENCE_HEADINGS = ("参考文献", "References", "REFERENCES")
_PLACEHOLDER_PATTERN = re.compile(r"__PTG_[A-Z]+__")
_REFERENCE_NUMBERED_PREFIX_RE = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*)|(?:[IVXLC]+))[.)]?\s+",
    re.IGNORECASE,
)


def extract_page_texts(path: Path) -> list[str]:
    doc = fitz.open(path)
    try:
        return [page.get_text("text") for page in doc]
    finally:
        doc.close()


def _reference_heading_line_matches(text: str, candidates: tuple[str, ...]) -> bool:
    """Return True only for a heading-like References line.

    A flattened substring search mistakes table-of-contents rows such as
    ``References ........ 9`` or ordinary prose like ``references to Fig. 2`` for
    the bibliography boundary.  This helper accepts only a standalone heading
    (optionally numbered, e.g. ``6. References``), so TOC entries cannot truncate
    the translation source.
    """
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return False
    line = _REFERENCE_NUMBERED_PREFIX_RE.sub("", line, count=1).strip()
    if line.endswith(":"):
        line = line[:-1].strip()
    lowered = line.casefold()
    return any(lowered == candidate.casefold() for candidate in candidates)


def reference_start_page_from_texts(pages: list[str]) -> int | None:
    """Shared text-only boundary detector using complete logical lines."""
    for index, text in enumerate(pages, start=1):
        for line in (text or "").splitlines():
            if _reference_heading_line_matches(line, TARGET_REFERENCE_HEADINGS):
                return index
    return None


def _heading_rect(page: fitz.Page, candidates: tuple[str, ...]) -> fitz.Rect | None:
    """Find the first *standalone* bibliography heading on a page.

    Geometry is taken from the PDF line itself rather than from ``search_for`` so
    that TOC rows containing the word References are not accepted as headings.
    """
    hits: list[fitz.Rect] = []
    try:
        payload = page.get_text("dict")
    except Exception:
        payload = {"blocks": []}
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(str(span.get("text", "")) for span in spans)
            if not _reference_heading_line_matches(line_text, candidates):
                continue
            bbox = line.get("bbox")
            if bbox and len(bbox) == 4:
                hits.append(fitz.Rect(*bbox))
            elif spans:
                rects = [fitz.Rect(*span["bbox"]) for span in spans if span.get("bbox")]
                if rects:
                    rect = rects[0]
                    for other in rects[1:]:
                        rect |= other
                    hits.append(rect)
    if not hits:
        return None
    return min(hits, key=lambda rect: (rect.y0, rect.x0))


def reference_heading_rect_on_page(page: fitz.Page) -> fitz.Rect | None:
    return _heading_rect(page, TARGET_REFERENCE_HEADINGS)


def _reference_start_page_in_doc(doc: fitz.Document) -> int | None:
    for index, page in enumerate(doc, start=1):
        if _heading_rect(page, REFERENCE_HEADINGS) is not None:
            return index
    return None


def _heading_y(page: fitz.Page, candidates: tuple[str, ...]) -> float | None:
    rect = _heading_rect(page, candidates)
    return rect.y0 if rect is not None else None


def _footer_top(page: fitz.Page) -> float:
    """Keep journal footer/page number outside raster replacement regions."""
    return max(0.0, page.rect.height - 68.0)



def prepare_translation_source(original_path: Path, output_path: Path) -> dict:
    """Create a translation source that excludes bibliography-only tail pages.

    Earlier versions rasterized every page after ``References`` so that
    PDFMathTranslate could not translate bibliographic metadata.  BabelDOC's scan
    detector can legitimately interpret those intentionally image-only tail pages
    as evidence that the *whole* input is a scanned PDF and abort an otherwise
    searchable article.

    Phase71 keeps only pages that actually need translation:

    * if References begins in the right column of a mixed body page, rasterize only
      that right-column bibliography region and omit all later reference-only pages;
    * if References begins full-width, omit that page and every later bibliography
      page from the translation input entirely.

    ``restore_reference_section`` appends the untouched source bibliography after
    translation, so no citation page needs to enter the LLM/BabelDOC path.
    """
    source_doc = fitz.open(original_path)
    work_doc = fitz.open(original_path)
    try:
        ref_page_1 = _reference_start_page_in_doc(source_doc)
        if ref_page_1 is None:
            work_doc.save(output_path, garbage=4, deflate=True)
            return {
                "prepared": True,
                "references_rasterized": False,
                "reference_tail_omitted": False,
                "reason": "references_not_found",
            }

        ref_index = ref_page_1 - 1
        source_page = source_doc[ref_index]
        heading = _heading_rect(source_page, REFERENCE_HEADINGS)
        if heading is None:
            work_doc.save(output_path, garbage=4, deflate=True)
            return {
                "prepared": True,
                "references_rasterized": False,
                "reference_tail_omitted": False,
                "reason": "reference_heading_not_found",
            }

        midpoint = source_page.rect.width / 2.0
        mixed_right_column = heading.x0 >= midpoint * 0.90
        rasterized_pages: list[int] = []
        omitted_pages: list[int] = []

        # A full-width References heading can still share a page with the end of
        # the article body (Conclusion/Acknowledgements above, bibliography below).
        # Phase71 treated every full-width heading as a bibliography-only page and
        # could therefore delete real body text or turn a one-page preflight into an
        # image-only PDF that BabelDOC reports as "document contains no paragraphs".
        # Detect actual body text above the heading before deciding whether the page
        # itself can be omitted.
        body_above = source_page.get_text(
            "text",
            clip=fitz.Rect(0.0, 0.0, source_page.rect.width, max(0.0, heading.y0 - 4.0)),
        )
        body_above_chars = len(re.findall(r"[A-Za-zぁ-んァ-ヶ一-龯]", body_above or ""))
        full_width_mixed = (not mixed_right_column) and body_above_chars >= 80

        if mixed_right_column or full_width_mixed:
            # Keep the body part of the mixed page but make only the bibliography
            # region image-only.  Later bibliography-only pages are omitted from
            # BabelDOC and restored verbatim after translation.
            work_page = work_doc[ref_index]
            x0 = midpoint if mixed_right_column else 0.0
            first_region = fitz.Rect(
                x0,
                max(0.0, heading.y0 - 3.0),
                source_page.rect.width,
                source_page.rect.height,
            )
            first_pix = source_page.get_pixmap(
                matrix=fitz.Matrix(2.0, 2.0), clip=first_region, alpha=False
            )
            work_page.add_redact_annot(first_region, fill=(1, 1, 1))
            work_page.apply_redactions()
            work_page.insert_image(
                first_region,
                stream=first_pix.tobytes("png"),
                keep_proportion=False,
                overlay=True,
            )
            rasterized_pages.append(ref_page_1)

            if len(work_doc) > ref_index + 1:
                omitted_pages = list(range(ref_page_1 + 1, len(source_doc) + 1))
                work_doc.delete_pages(ref_index + 1, len(work_doc) - 1)
            mode = "right-column" if mixed_right_column else "full-width-mixed"
        else:
            # A genuinely bibliography-only full-width page and every following
            # page can be omitted from BabelDOC.  A PDF cannot have zero pages, so
            # a references-only one-page document keeps an image-only fallback.
            if ref_index > 0:
                omitted_pages = list(range(ref_page_1, len(source_doc) + 1))
                work_doc.delete_pages(ref_index, len(work_doc) - 1)
                mode = "full-width-omitted"
            else:
                work_page = work_doc[0]
                rect = source_page.rect
                pix = source_page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
                work_page.add_redact_annot(rect, fill=(1, 1, 1))
                work_page.apply_redactions()
                work_page.insert_image(rect, stream=pix.tobytes("png"), keep_proportion=False, overlay=True)
                rasterized_pages.append(1)
                if len(work_doc) > 1:
                    omitted_pages = list(range(2, len(source_doc) + 1))
                    work_doc.delete_pages(1, len(work_doc) - 1)
                mode = "references-only-fallback"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        work_doc.save(output_path, garbage=4, deflate=True)
        return {
            "prepared": True,
            "references_rasterized": bool(rasterized_pages),
            "reference_page": ref_page_1,
            "mode": mode,
            "rasterized_pages": rasterized_pages,
            "reference_tail_omitted": bool(omitted_pages),
            "omitted_reference_pages": omitted_pages,
            "translation_input_pages": len(work_doc),
            "source_pages": len(source_doc),
            "body_chars_before_reference": body_above_chars,
        }
    finally:
        source_doc.close()
        work_doc.close()

def restore_reference_section(original_path: Path, translated_path: Path) -> dict:
    """Restore bibliography without overwriting translated body text.

    On the first mixed body/References page only the bibliography column below the
    heading is replaced. The replacement is rasterized deliberately: unlike
    ``show_pdf_page(..., clip=...)`` it does not import an entire hidden source-page
    text layer, which previously made PDF extraction return English body text under
    visibly Japanese content. All following bibliography-only pages are copied from
    the source PDF verbatim and therefore remain searchable/selectable.
    """
    source_doc = fitz.open(original_path)
    target_doc = fitz.open(translated_path)
    try:
        ref_page_1 = _reference_start_page_in_doc(source_doc)
        if ref_page_1 is None:
            return {"patched": False, "reason": "references_not_found"}
        ref_index = ref_page_1 - 1
        if ref_index > len(target_doc):
            return {"patched": False, "reason": "target_missing_pages_before_reference"}

        source_page = source_doc[ref_index]

        # Phase71 may omit a full-width References tail from the BabelDOC input.
        # When the translated artifact ends exactly before that page, simply append
        # the untouched source bibliography.  No rasterized page needs to pass
        # through BabelDOC and the final PDF regains the original page count.
        if ref_index == len(target_doc):
            source_heading = _heading_rect(source_page, REFERENCE_HEADINGS)
            if source_heading is None:
                return {"patched": False, "reason": "source_reference_heading_not_found"}
            midpoint = source_page.rect.width / 2.0
            if source_heading.x0 >= midpoint * 0.90:
                # A mixed right-column page should have remained in the translation
                # input; reaching this branch would otherwise discard its left body.
                return {"patched": False, "reason": "mixed_reference_page_missing_from_target"}
            appended_reference_pages = len(source_doc) - ref_index
            target_doc.insert_pdf(source_doc, from_page=ref_index, to_page=len(source_doc) - 1)
            temp_path = translated_path.with_suffix(".references-fixed.tmp.pdf")
            target_doc.save(temp_path, garbage=4, deflate=True)
            target_doc.close()
            source_doc.close()
            temp_path.replace(translated_path)
            return {
                "patched": True,
                "reference_page": ref_page_1,
                "mode": "full-width-appended",
                "source_x": 0.0,
                "source_y": round(source_heading.y0, 2),
                "target_x": 0.0,
                "target_y": round(source_heading.y0, 2),
                "first_reference_page_rasterized": False,
                "following_reference_pages_verbatim": True,
                "appended_reference_pages": appended_reference_pages,
            }

        target_page = target_doc[ref_index]
        source_heading = _heading_rect(source_page, REFERENCE_HEADINGS)
        target_heading = _heading_rect(target_page, TARGET_REFERENCE_HEADINGS)
        if source_heading is None:
            return {"patched": False, "reason": "source_reference_heading_not_found"}
        if target_heading is None:
            target_heading = fitz.Rect(
                source_heading.x0,
                source_heading.y0,
                source_heading.x1,
                source_heading.y1,
            )

        width = target_page.rect.width
        midpoint = width / 2.0
        source_footer = _footer_top(source_page)
        target_footer = _footer_top(target_page)

        # Scientific journals commonly start References in the right column of the
        # final body page. Detect that from the source heading instead of assuming a
        # full-width region; this prevents Conclusion/Acknowledgements on the left
        # column from being overwritten.
        if source_heading.x0 >= midpoint * 0.90:
            source_x0 = midpoint
            target_x0 = midpoint
            column_mode = "right-column"
        else:
            source_x0 = 0.0
            target_x0 = 0.0
            column_mode = "full-width"

        source_clip = fitz.Rect(
            source_x0,
            max(0.0, source_heading.y0 - 3.0),
            source_page.rect.width,
            source_footer,
        )
        target_region = fitz.Rect(
            target_x0,
            max(0.0, target_heading.y0 - 3.0),
            target_page.rect.width,
            target_footer,
        )

        if source_clip.height > 0 and target_region.height > 0:
            # Redaction removes translated bibliography objects and text layer before
            # inserting the source rendering. This avoids hidden duplicate text.
            target_page.add_redact_annot(target_region, fill=(1, 1, 1))
            target_page.apply_redactions()
            pix = source_page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=source_clip, alpha=False)
            target_page.insert_image(
                target_region,
                stream=pix.tobytes("png"),
                keep_proportion=False,
                overlay=True,
            )

        # Pages after the mixed page are bibliography-only in the source. Replace
        # them with the original vector/text pages rather than translating them.
        if len(target_doc) > ref_index + 1:
            target_doc.delete_pages(ref_index + 1, len(target_doc) - 1)
        if len(source_doc) > ref_index + 1:
            target_doc.insert_pdf(source_doc, from_page=ref_index + 1, to_page=len(source_doc) - 1)

        temp_path = translated_path.with_suffix(".references-fixed.tmp.pdf")
        target_doc.save(temp_path, garbage=4, deflate=True)
        target_doc.close()
        source_doc.close()
        temp_path.replace(translated_path)
        return {
            "patched": True,
            "reference_page": ref_page_1,
            "mode": column_mode,
            "source_x": round(source_x0, 2),
            "source_y": round(source_heading.y0, 2),
            "target_x": round(target_x0, 2),
            "target_y": round(target_heading.y0, 2),
            "first_reference_page_rasterized": True,
            "following_reference_pages_verbatim": True,
        }
    finally:
        try:
            if not source_doc.is_closed:
                source_doc.close()
        except Exception:
            pass
        try:
            if not target_doc.is_closed:
                target_doc.close()
        except Exception:
            pass


def _extract_orcid_names(text: str) -> list[str]:
    names: list[str] = []
    pattern = re.compile(
        r"([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){1,3})\s*(?:\s*)?https?://orcid\.org/",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        if name.startswith("Ds "):
            name = name[3:].strip()
        if name and name not in names:
            names.append(name)
    return names


def extract_primary_author_names(original_path: Path) -> list[str]:
    doc = fitz.open(original_path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()
    return _extract_orcid_names(text)


def restore_primary_author_band(original_path: Path, translated_path: Path) -> dict:
    """Fallback author repair using redaction + raster band.

    Phase 11 normally preserves names before the LLM call, so this is only used when
    the output still loses an author name. The old clipped-page composition imported
    a hidden full English text layer; this implementation does not.
    """
    source = fitz.open(original_path)
    target = fitz.open(translated_path)
    try:
        all_source_text = "\n".join(page.get_text("text") for page in source)
        names = _extract_orcid_names(all_source_text)
        if not names:
            return {"patched": False, "reason": "author_names_not_found"}

        target_head = "\n".join(target[i].get_text("text") for i in range(min(4, len(target))))
        if all(name in target_head for name in names):
            return {"patched": False, "reason": "already_preserved", "names": names}

        best_page = None
        best_rects: list[fitz.Rect] = []
        best_score: tuple[float, int] | None = None
        for page_index in range(min(4, len(source))):
            rects: list[fitz.Rect] = []
            for name in names:
                rects.extend(source[page_index].search_for(name))
            if len(rects) < 2:
                continue
            vertical_span = max(rect.y1 for rect in rects) - min(rect.y0 for rect in rects)
            score = (-vertical_span, len(rects))
            if best_score is None or score > best_score:
                best_score = score
                best_page = page_index
                best_rects = rects
        if best_page is None or best_page >= len(target):
            return {"patched": False, "reason": "author_line_not_located", "names": names}

        y0 = max(0.0, min(rect.y0 for rect in best_rects) - 3.0)
        y1 = min(source[best_page].rect.height, max(rect.y1 for rect in best_rects) + 3.0)
        region = fitz.Rect(0, y0, target[best_page].rect.width, y1)
        clip = fitz.Rect(0, y0, source[best_page].rect.width, y1)

        target_page = target[best_page]
        target_page.add_redact_annot(region, fill=(1, 1, 1))
        target_page.apply_redactions()
        pix = source[best_page].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip, alpha=False)
        target_page.insert_image(region, stream=pix.tobytes("png"), keep_proportion=False, overlay=True)

        temp_path = translated_path.with_suffix(".authors-fixed.tmp.pdf")
        target.save(temp_path, garbage=4, deflate=True)
        target.close()
        source.close()
        temp_path.replace(translated_path)
        return {
            "patched": True,
            "page": best_page + 1,
            "y0": round(y0, 2),
            "y1": round(y1, 2),
            "names": names,
            "mode": "redact-raster-band",
        }
    finally:
        try:
            if not source.is_closed:
                source.close()
        except Exception:
            pass
        try:
            if not target.is_closed:
                target.close()
        except Exception:
            pass


def build_alternating_dual(original_path: Path, translated_path: Path, output_path: Path) -> None:
    """Build a deterministic English/Japanese alternating-page PDF."""
    source = fitz.open(original_path)
    target = fitz.open(translated_path)
    out = fitz.open()
    try:
        count = min(len(source), len(target))
        for index in range(count):
            out.insert_pdf(source, from_page=index, to_page=index)
            out.insert_pdf(target, from_page=index, to_page=index)
        temp_path = output_path.with_suffix(".dual.tmp.pdf")
        out.save(temp_path, garbage=4, deflate=True)
        temp_path.replace(output_path)
    finally:
        out.close()
        source.close()
        target.close()


def protected_terms(original_path: Path) -> list[str]:
    """Collect document-specific exact strings that must not be rewritten."""
    doc = fitz.open(original_path)
    try:
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()

    terms: set[str] = set()
    terms.update(_extract_orcid_names(text))

    patterns = (
        r"https?://[^\s)>]+",
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        r"\b10\.\d{4,9}/[^\s)>]+",
        r"\[(?:\d+)(?:\s*[-–,]\s*\d+)*\]",
        r"\b(?:BHTSU|HTS|FEM|DOFs?|MEMEP|MEM|RAA|FFT|FC|ANSYS|COMSOL|ORCID|PSI|SLS|I-TOMCAT)\b",
        r"\b(?:Re-Ba-Cu-O|Gd-Ba-Cu-O|Y-Ba-Cu-O)\b",
        r"\b(?:Jc|Js|Jx|Jy|Jz|Bz|By|B0|Hx|Hy|Hz|AZ)(?:\([^\n)]{1,24}\))?\b",
        r"\|\s*[A-Za-z][A-Za-z0-9,]*\s*\|",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = re.sub(r"\s+", " ", match.group(0)).strip().rstrip(".,;")
            if 1 < len(value) <= 180:
                terms.add(value)

    # Units are protected together with their numeric value at segment time.
    # Do not add standalone one-letter units such as T/K here: raw substring
    # matching would split ordinary prose words (e.g. the T in "The").
    return sorted(terms, key=lambda value: (-len(value), value))[:800]


def write_protected_glossary(original_path: Path, output_path: Path) -> int:
    """Legacy helper retained for diagnostics; Phase 11 no longer relies on it."""
    terms = protected_terms(original_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "target", "tgt_lng"])
        for term in terms:
            writer.writerow([term, term, "ja"])
    return len(terms)


def _alpha_code(index: int) -> str:
    index += 1
    chars: list[str] = []
    while index:
        index, rem = divmod(index - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars)).rjust(4, "A")


def _placeholder(index: int) -> str:
    return f"__PTG_{_alpha_code(index)}__"


def _candidate_spans(text: str, document_terms: list[str] | tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    # BabelDOC style placeholders can split *inside* a decimal scalar, not only
    # between a complete number and its unit. For example a visually atomic
    # ``6.1°`` may reach the translation proxy as ``6{v3}.1{v4}°``. The older
    # measurement pattern protected ``6`` and ``1°`` separately, which allowed
    # the model/layout round-trip to reconstruct ``6 ... 1°``. Treat the whole
    # styled scalar + unit as one opaque object before the generic numeric rules.
    style_gap = r"(?:\s*\{\s*v\s*\d+\s*\}\s*)*"
    styled_digits = rf"\d(?:{style_gap}\d)*"
    styled_number = rf"{styled_digits}(?:{style_gap}\.{style_gap}{styled_digits})?"
    styled_measurement = (
        rf"(?<!\w){styled_number}{style_gap}\s*"
        rf"(?:keV|MeV|GeV|mm|cm|m|µm|μm|um|nm|T|K|A|G|Hz|h|s|°|%)"
        rf"(?!\w)"
    )

    # Existing BabelDOC placeholders must survive exactly so BabelDOC can restore
    # formula/style objects after our proxy returns the translation.
    regexes = (
        r"\{\s*v\s*\d+\s*\}",
        r"<\s*/?\s*style\b[^>]*>",
        r"https?://[^\s)>]+",
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        r"\b10\.\d{4,9}/[^\s)>]+",
        r"\[(?:\d+)(?:\s*[-–,]\s*\d+)*\]",
        # Multi-dimensional measurements first, before individual numbers.
        # BabelDOC may interleave style placeholders such as {v3} between a value,
        # unit and multiplication sign.  Treat the complete expression as one
        # immutable span even in that representation.
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:mm|cm|m|µm|μm|um|nm)?(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*[×xX](?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:mm|cm|m|µm|μm|um|nm)?(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*[×xX](?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:mm|cm|m|µm|μm|um|nm)(?!\w)",
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)\s*(?:mm|cm|m|µm|μm|um|nm)?\s*[×xX]\s*(?:\d+(?:\.\d+)?|\.\d+)\s*(?:mm|cm|m|µm|μm|um|nm)?\s*[×xX]\s*(?:\d+(?:\.\d+)?|\.\d+)\s*(?:mm|cm|m|µm|μm|um|nm)(?!\w)",
        # Scientific notation with optional physical unit tail.
        # Keep BabelDOC style placeholders inside the immutable span as well.
        # Without this variant, expressions such as ``1{v3} × {v4}10^-3`` were
        # split around the multiplication sign and could reconstruct as ``× ×``.
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*[×xX](?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*10(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:\^\s*)?[−-]?\d+(?:\s*[A-Za-zµμΩ]+(?:\s*[A-Za-z]+)?(?:[−-]?\d+)?)?",
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)\s*[×xX]\s*10\s*(?:\^\s*)?[−-]?\d+(?:\s*[A-Za-zµμΩ]+(?:\s*[A-Za-z]+)?(?:[−-]?\d+)?)?",
        # Compact relation tokens such as y > x, x = 0 mm, Jc = 6e9.
        # BabelDOC may insert {vN} style placeholders between the variable,
        # operator and value. Protect the complete styled relation atomically;
        # otherwise the model can emit a second '=' around a protected style run.
        r"(?<!\w)(?:\|\s*[A-Za-z][A-Za-z0-9]*(?:,[A-Za-z0-9]+)*\s*\||[A-Za-zµμφρΔ][A-Za-z0-9µμφρΔ_]*(?:,[A-Za-z0-9µμφρΔ_]+)*(?:\([^\n)]{0,40}\))?)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:=|<|>|≤|≥|⩽|⩾|≠)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:[-+±]?\s*(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*(?:\s*(?:mm|cm|m|µm|um|nm|T|K|s|h|Hz|A\s*m[−-]?2))?|[A-Za-zµμφρΔ][A-Za-z0-9µμφρΔ_]*(?:,[A-Za-z0-9µμφρΔ_]+)*(?:\([^\n)]{0,40}\))?)",
        r"(?<!\w)(?:\|\s*[A-Za-z][A-Za-z0-9]*(?:,[A-Za-z0-9]+)*\s*\||[A-Za-zµμφρΔ][A-Za-z0-9µμφρΔ_]*(?:,[A-Za-z0-9µμφρΔ_]+)*(?:\([^\n)]{0,40}\))?)\s*(?:=|<|>|≤|≥|⩽|⩾|≠)\s*(?:[-+±]?\s*(?:\d+(?:\.\d+)?|\.\d+)(?:\s*(?:mm|cm|m|µm|um|nm|T|K|s|h|Hz|A\s*m[−-]?2))?|[A-Za-zµμφρΔ][A-Za-z0-9µμφρΔ_]*(?:,[A-Za-z0-9µμφρΔ_]+)*(?:\([^\n)]{0,40}\))?)",
        # Number + unit. BabelDOC may inject {vN} style placeholders between
        # the numeric value and its unit.  Protect the complete styled measurement
        # atomically; otherwise the number is hidden but the bare unit (for example
        # ``T`` in ``10{v8} T``) reaches the LLM and can be translated/dropped.
        styled_measurement,
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:A(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*m(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*[−-]?2|T(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*s(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*[−-]?1|Tm2)(?!\w)",
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)(?:\s*\{\s*v\s*\d+\s*\}\s*)*\s*(?:keV|MeV|GeV|mm|cm|m|µm|μm|um|nm|T|K|A|G|Hz|h|s|°|%)(?!\w)",
        r"(?<!\w)(?:\d+(?:\.\d+)?|\.\d+)\s*(?:keV|MeV|GeV|mm|cm|m|µm|μm|um|nm|T|K|A|G|Hz|h|s|°|%|A\s*m[−-]?2|T\s*s[−-]?1|T\s*(?:·\s*)?mm(?:2|²)|Tm2)(?!\w)",
        # Technical product / solver identifiers such as OPERA-3D.  Keep the
        # identifier immutable so a model cannot turn it into OPERATO-3D while
        # translating the surrounding prose.
        r"(?<![A-Za-z0-9])(?:[A-Z]{2,}[A-Z0-9]*)(?:-[A-Z0-9]+)+(?![A-Za-z0-9])",
        # Formula/physics variable names that should not be transliterated.
        r"(?<!\w)(?:Jc|Js|Jx|Jy|Jz|Bz|By|B0|Hx|Hy|Hz|AZ)(?:\([^\n)]{1,24}\))?(?!\w)",
        r"\b(?:BHTSU|HTS|FEM|DOFs?|MEMEP|MEM|RAA|FFT|FC|ANSYS|COMSOL|ORCID|PSI|SLS|I-TOMCAT)\b",
        r"\b(?:Re-Ba-Cu-O|Gd-Ba-Cu-O|Y-Ba-Cu-O)\b",
        # Preserve publication dates as one immutable object.  Translating the
        # surrounding labels is fine, but rearranging the day/month/year produced
        # invalid strings such as "8年2021月" in the Phase 14 preflight.
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        # Preserve surnames used in prose citations (Tanaka et al., Kinjo et al.).
        r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?=\s+et\s+al\.?)",
        # Finally protect every standalone numeric token. This is the decisive Phase
        # 11 change: the LLM never sees 14/10/6/0.85/etc as mutable text.
        r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?|\.\d+)(?![A-Za-z0-9])",
    )
    # Scientific identifiers and SI units are case-sensitive.  In particular,
    # magnetic-field component ``By`` must be protected while grammatical lower-case
    # ``by`` must remain visible to the translator.  A global IGNORECASE flag made
    # every English ``by`` immutable and was the root cause of the Phase 41/42 debris.
    for pattern in regexes:
        for match in re.finditer(pattern, text):
            start, end = match.start(), match.end()
            while end > start and text[end - 1] in ",;.":
                end -= 1
            if end > start:
                spans.append((start, end))

    for term in document_terms:
        if not term or len(term) < 2:
            continue
        # Document terms include names, identifiers and acronyms. Match them as
        # lexical tokens when they begin/end in an alphanumeric character; raw
        # substring matching can otherwise protect pieces inside unrelated words.
        left = r"(?<![A-Za-z0-9])" if term[0].isalnum() else ""
        right = r"(?![A-Za-z0-9])" if term[-1].isalnum() else ""
        pattern = left + re.escape(term) + right
        for match in re.finditer(pattern, text):
            spans.append((match.start(), match.end()))

    return spans


def protect_translation_segment(
    text: str,
    document_terms: list[str] | tuple[str, ...] = (),
) -> tuple[str, dict[str, str]]:
    """Replace immutable scientific tokens with opaque per-request placeholders.

    Overlap resolution prefers the longest span, so ``14 mm × 14 mm × 4 mm`` is one
    protected object rather than three separately mutable numbers.
    """
    candidates = _candidate_spans(text, document_terms)
    if not candidates:
        return text, {}

    # Longest first prevents a short token from blocking a complete relation/dimension.
    selected: list[tuple[int, int]] = []
    occupied: list[tuple[int, int]] = []
    for start, end in sorted(set(candidates), key=lambda item: (-(item[1] - item[0]), item[0])):
        if end <= start:
            continue
        if any(not (end <= a or start >= b) for a, b in occupied):
            continue
        selected.append((start, end))
        occupied.append((start, end))
    selected.sort()

    parts: list[str] = []
    mapping: dict[str, str] = {}
    cursor = 0
    for index, (start, end) in enumerate(selected):
        token = _placeholder(index)
        parts.append(text[cursor:start])
        parts.append(token)
        mapping[token] = text[start:end]
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), mapping


def restore_translation_placeholders(
    translated_text: str,
    mapping: dict[str, str],
) -> tuple[str, bool, list[str]]:
    """Restore placeholders only when every protected token survived exactly once."""
    problems: list[str] = []
    for token in mapping:
        count = translated_text.count(token)
        if count != 1:
            problems.append(f"{token}:count={count}")

    foreign = sorted(set(_PLACEHOLDER_PATTERN.findall(translated_text)) - set(mapping))
    problems.extend(f"foreign:{token}" for token in foreign)
    if problems:
        return translated_text, False, problems

    restored = translated_text
    for token, original in mapping.items():
        restored = restored.replace(token, original)
    if _PLACEHOLDER_PATTERN.search(restored):
        return restored, False, ["placeholder_remained_after_restore"]
    return restored, True, []


def formula_relation_tokens(text: str) -> list[str]:
    """Extract compact mathematical relations that should remain semantically stable."""
    compact = re.sub(r"\s+", " ", text)
    atom = r"(?:\|\s*[A-Za-z][A-Za-z0-9]*(?:,[A-Za-z0-9]+)*\s*\||[A-Za-z][A-Za-z0-9_]*(?:,[A-Za-z0-9_]+)*(?:\([^)]{1,24}\))?)"
    op = r"(?:=|<|>|≤|≥|⩽|⩾|≠)"
    results = []
    for match in re.finditer(rf"{atom}\s*{op}\s*(?:[-+]?\d+(?:\.\d+)?|{atom})", compact):
        value = re.sub(r"\s+", "", match.group(0))
        if value not in results:
            results.append(value)
    return results



def hard_semantic_guard_problems(source_text: str, translated_text: str) -> list[str]:
    """Catch a small set of high-confidence polarity reversals before PDF output.

    This is intentionally narrow. Broad semantic equivalence remains the post-PDF
    LLM QA job; these rules only block contradictions that can be recognized with
    high precision and that have already occurred in the regression corpus.
    """
    source = re.sub(r"\s+", " ", source_text).strip().lower()
    target = re.sub(r"\s+", " ", translated_text).strip()
    problems: list[str] = []

    if re.search(r"(?<!not )\bnecessarily\b", source) and not re.search(r"\bnot\s+necessarily\b", source):
        if re.search(r"必ずしも.{0,90}(?:ない|ません|ず|とは限らない)", target):
            problems.append("necessarily_reversed_to_not_necessarily")

    if "faster than" in source and "slower than" not in source:
        if re.search(r"より.{0,40}(?:遅い|遅く|低速)", target):
            problems.append("faster_reversed_to_slower")
    if "slower than" in source and "faster than" not in source:
        if re.search(r"より.{0,40}(?:速い|速く|高速)", target):
            problems.append("slower_reversed_to_faster")

    source_has_increase = bool(re.search(r"\bincreas(?:e|es|ed|ing)\b", source))
    source_has_decrease = bool(re.search(r"\bdecreas(?:e|es|ed|ing)\b", source))
    if source_has_increase and not source_has_decrease and "減少" in target and "増加" not in target:
        problems.append("increase_reversed_to_decrease")
    if source_has_decrease and not source_has_increase and "増加" in target and "減少" not in target:
        problems.append("decrease_reversed_to_increase")

    return problems

def semantic_risk_sentences(text: str) -> list[str]:
    markers = re.compile(
        r"\b(?:not|no|never|neither|without|cannot|can't|necessarily|must|only|impossible|"
        r"more than|less than|greater than|lower than|higher than|faster|slower|increase|decrease|"
        r"above|below|exceed|under|over|equal|same|different|minimum|maximum|finite|infinite)\b",
        re.IGNORECASE,
    )
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text))
    result: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if 45 <= len(sentence) <= 900 and markers.search(sentence):
            result.append(sentence)
    return result

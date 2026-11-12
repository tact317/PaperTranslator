#!/usr/bin/env python3
"""Conservative, non-raster Type1 font Unicode-map recovery.

This tool does not OCR, does not translate, and does not assert scientific
semantic correctness. It only adds basic text extraction mappings to
single-byte Type1 fonts missing a ToUnicode entry. Original input is never
modified, and page pixels must remain byte-for-byte identical at test DPI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path
import fitz


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def _basic_to_unicode_cmap() -> bytes:
    # Covers ASCII and Windows-1252 only. Do not guess PDF symbolic glyphs.
    pairs = []
    for code in range(32, 256):
        if code == 127:
            continue
        try:
            scalar = ord(bytes([code]).decode('cp1252'))
        except UnicodeDecodeError:
            continue
        pairs.append(f'<{code:02X}> <{scalar:04X}>')
    lines = [
        '/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
        '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
        '/CMapName /PeperTranslator-Latin def', '/CMapType 2 def',
        '1 begincodespacerange', '<00> <FF>', 'endcodespacerange',
    ]
    for i in range(0, len(pairs), 100):
        block = pairs[i:i + 100]
        lines.extend([f'{len(block)} beginbfchar', *block, 'endbfchar'])
    lines.extend([
        'endcmap', 'CMapName currentdict /CMap defineresource pop',
        'end', 'end',
    ])
    return '\n'.join(lines).encode('ascii')


def _short_staging_path(dst: Path) -> Path:
    """Use short, atomic sibling staging names on legacy Windows MAX_PATH.

    Repeating the full output stem plus another UUID previously produced a
    269-character temporary path in the user's per-document layout cache.
    PyMuPDF then raised `code=2: cannot open file` during its CID retry.
    A short sibling filename preserves atomic replacement on the same volume.
    """
    return dst.with_name(f".ptcid-{uuid.uuid4().hex}.tmp.pdf")


def normalize(src: Path, dst: Path, dpi: int = 72) -> dict:
    src, dst = src.resolve(), dst.resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    if src == dst:
        raise ValueError('Input and output must be different: original is read-only')
    if dst.exists():
        raise FileExistsError('Output already exists; refusing to overwrite: ' + str(dst))
    before_digest = _digest(src)
    tmp = _short_staging_path(dst)
    try:
        return _normalize_impl(src, dst, tmp, before_digest, dpi)
    finally:
        tmp.unlink(missing_ok=True)


def _normalize_impl(src, dst, tmp, before_digest, dpi):
    with fitz.open(src) as doc:
        if doc.needs_pass:
            raise ValueError('Encrypted PDF is not supported')
        fonts = {}
        for page in doc:
            for entry in page.get_fonts(full=True):
                xref = entry[0]
                subtype = doc.xref_get_key(xref, 'Subtype')[1]
                to_unicode = doc.xref_get_key(xref, 'ToUnicode')[0]
                fonts[xref] = (subtype, to_unicode)
        eligible = sorted(
            x for x, (subtype, mapping) in fonts.items()
            if subtype == '/Type1' and mapping == 'null'
        )
        unsupported = sorted(
            x for x, (subtype, mapping) in fonts.items()
            if subtype != '/Type1' and mapping == 'null'
        )
        if unsupported:
            raise ValueError(
                f'Unsupported unmapped font types at xrefs {unsupported}; '
                'do not add a single-byte map to composite fonts.'
            )
        if not eligible:
            raise ValueError('No eligible unmapped Type1 fonts; do not rewrite PDF')
        cmap = _basic_to_unicode_cmap()
        for xref in eligible:
            cmap_xref = doc.get_new_xref()
            doc.update_object(cmap_xref, '<<>>')
            doc.update_stream(cmap_xref, cmap, compress=True)
            doc.xref_set_key(xref, 'ToUnicode', f'{cmap_xref} 0 R')
        page_count = len(doc)
        doc.save(tmp, garbage=4, deflate=True)
    with fitz.open(src) as before, fitz.open(tmp) as after:
        if len(before) != len(after):
            raise RuntimeError('Page count changed')
        for i in range(len(before)):
            if before[i].rect != after[i].rect:
                raise RuntimeError('Page geometry changed')
            # Render equality means no visual content/figures were changed.
            a = before[i].get_pixmap(dpi=dpi, alpha=False).samples
            b = after[i].get_pixmap(dpi=dpi, alpha=False).samples
            if a != b:
                raise RuntimeError(f'Visual regression on page {i+1}; output rejected')
    if _digest(src) != before_digest:
        raise RuntimeError('Source unexpectedly changed')
    if dst.exists():
        raise FileExistsError('Refusing to overwrite output')
    os.replace(tmp, dst)
    return {
        'source': str(src), 'output': str(dst), 'source_sha256': before_digest,
        'output_sha256': _digest(dst), 'pages': page_count,
        'mapped_Type1_font_count': len(eligible),
        'font_xrefs': eligible, 'render_identical_at_dpi': dpi,
        'tested_pdf2zh_next': False,
        'warning': 'Visible PDF matches; semantic accuracy of scientific glyphs is not guaranteed.'
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--dpi', type=int, default=72)
    a = p.parse_args()
    print(json.dumps(normalize(a.input, a.output, a.dpi), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

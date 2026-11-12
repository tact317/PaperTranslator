"""Phase97 portable, network-free offline reading pack generator.

This module has no mutation path into Library, cache, vocabulary or translation jobs.
Only explicitly selected SHA-256 document IDs are exported.  All PDF names within
ZIPs are generated from IDs and never taken from source filenames.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
from typing import Any
import zipfile

DOCUMENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENTS = 10
MAX_ARCHIVE_INPUT_BYTES = 300 * 1024 * 1024
MAX_PDF_BYTES = 160 * 1024 * 1024
MAX_VOCABULARY_CARDS = 10000


def _validate_id(document_id: str) -> None:
    if not isinstance(document_id, str) or not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("不正な文書IDです。")


def _safe_text(value: Any, cap: int) -> str:
    return str(value or "").strip()[:cap]


def _read_template() -> str:
    template_path = Path(__file__).with_name("phase97_mobile_reader.html")
    return template_path.read_text(encoding="utf-8")


def _js_safe_json(value: dict) -> str:
    """Do not let user data inject closing script tags or HTML into the reader."""
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _cards_for_offline(vocabulary: dict) -> list[dict]:
    raw = vocabulary.get("cards", []) if isinstance(vocabulary, dict) else []
    if not isinstance(raw, list) or len(raw) > MAX_VOCABULARY_CARDS:
        raise ValueError("語彙カードの件数が出力上限を超えています。")
    result = []
    seen = set()
    for card in raw:
        if not isinstance(card, dict):
            continue
        source = _safe_text(card.get("source"), 1000)
        target = _safe_text(card.get("translation"), 1000)
        if not source or not target:
            continue
        key = _safe_text(card.get("card_id") or card.get("cardId"), 100)
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            key = hashlib.sha256(f"{source.casefold()}\0{target}".encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        contexts = card.get("contexts")
        example = _safe_text(contexts[0], 600) if isinstance(contexts, list) and contexts else ""
        result.append({
            "id": key, "source": source, "translation": target,
            "kind": _safe_text(card.get("kind") or "term", 20),
            "example": example,
        })
    return result


def _pdf_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def build_offline_zip(
    *, document_ids: list[str], cache_root: Path, library_index: dict,
    vocabulary: dict, include_vocabulary: bool = True,
) -> bytes:
    """Return a ZIP in memory; never write into cache or Library.

    Deliberately caps input size before reading PDFs.  Package contains no CDN,
    remote scripts, service worker, or network-required resources.
    """
    if not isinstance(document_ids, list) or not (1 <= len(document_ids) <= MAX_DOCUMENTS):
        raise ValueError("1〜10件の論文を指定してください。")
    for doc_id in document_ids:
        _validate_id(doc_id)
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("論文IDが重複しています。")

    library_docs = library_index.get("documents", {}) if isinstance(library_index, dict) else {}
    if not isinstance(library_docs, dict):
        library_docs = {}
    documents = []
    files: list[tuple[Path, str]] = []
    total_bytes = 0
    for doc_id in document_ids:
        original = cache_root / (doc_id + ".pdf")
        if not _pdf_ok(original):
            raise ValueError(f"原文PDFが見つからないか破損しています: {doc_id[:12]}")
        # Guard document identity when a stale or manually replaced cache file exists.
        # Streaming hash avoids loading even a large PDF into RAM just for validation.
        h = hashlib.sha256()
        with original.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        if h.hexdigest() != doc_id:
            raise ValueError(f"原文PDFのIDとハッシュが一致しません: {doc_id[:12]}")
        record = library_docs.get(doc_id, {})
        if not isinstance(record, dict):
            record = {}
        title = _safe_text(record.get("title"), 500) or doc_id[:12]
        qa_path = cache_root / "layout_translations" / doc_id / "qa.json"
        qa = None
        if qa_path.is_file():
            try:
                data = json.loads(qa_path.read_text(encoding="utf-8"))
                qa = data if isinstance(data, dict) else None
            except (OSError, ValueError):
                pass
        quality_gate = _safe_text((qa or {}).get("quality_gate"), 20) if qa else "unknown"
        item = {
            "id": doc_id, "title": title,
            "doi": _safe_text(record.get("doi"), 200),
            "quality_gate": quality_gate,
            "files": [],
        }
        base = f"pdfs/{doc_id[:16]}"
        variants = [
            (original, f"{base}-original.pdf", "英語原文", "original"),
            (cache_root / "translations" / (doc_id + ".ja-reading.pdf"),
             f"{base}-reading-ja.pdf", "本文日本語訳", "reading"),
            (cache_root / "layout_translations" / doc_id / "translated-mono.pdf",
             f"{base}-layout-ja.pdf", "レイアウト日本語訳", "layout"),
            (cache_root / "layout_translations" / doc_id / "translated-dual.pdf",
             f"{base}-dual.pdf", "英日対訳", "dual"),
        ]
        for src, relative, label, kind in variants:
            if not _pdf_ok(src):
                if kind == "original":
                    raise ValueError("原文PDFを読み込めません。")
                continue
            length = src.stat().st_size
            if length > MAX_PDF_BYTES:
                raise ValueError(f"PDFが1ファイルの出力上限160MiBを超えています: {doc_id[:12]}")
            total_bytes += length
            if total_bytes > MAX_ARCHIVE_INPUT_BYTES:
                raise ValueError("PDF合計が持ち出し上限300MiBを超えています。件数を減らしてください。")
            files.append((src, relative))
            item["files"].append({"path": relative, "label": label, "kind": kind})
        if qa is not None:
            # Quality decision, not claims of correctness.  Full QA JSON itself is
            # not necessary for the phone viewer and may contain sensitive excerpts.
            item["qa_status"] = "要確認" if quality_gate == "fail" else ("合格" if quality_gate == "pass" else "未判定")
        documents.append(item)

    cards = _cards_for_offline(vocabulary) if include_vocabulary else []
    payload = {"schema": "pepertranslator-offline-v1", "documents": documents, "cards": cards}
    reader = _read_template()
    token = "/*__PT_OFFLINE_JSON__*/"
    if reader.count(token) != 1:
        raise RuntimeError("オフライン閲覧テンプレートの埋め込み位置が不正です。")
    reader = reader.replace(token, _js_safe_json(payload))
    manifest = {"schema": payload["schema"], "documents": documents, "vocabulary_count": len(cards),
                "offline": True, "remote_sync": False, "translation_engine": False}
    explanation = (
        "PeperTranslator オフライン持ち出し\n\n"
        "1. ZIPを展開し、PDFは pdfs フォルダから直接開けます。\n"
        "2. index.html をブラウザーで開ける環境なら、論文一覧と語彙カードを利用できます。\n"
        "3. iOS/Androidのファイルアプリ・ブラウザーによっては、ローカルHTMLのJavaScriptが制限されます。\n"
        "   その場合、PDFは端末標準のPDFビューアーで開き、単語は vocabulary.tsv を利用してください。\n"
        "4. スマホ単体では翻訳しません。復習履歴はPCの語彙データへ自動同期されません。\n"
        "5. このZIPには選択した論文の本文と語彙が含まれます。共有先に注意してください。\n"
        "6. 品質ゲートFAILの日本語訳は確認用です。科学値や数式は原文と照合してください。\n"
        "7. オフライン利用時にPC・Ollama・インターネット接続は不要です。\n"
    )
    vocab_tsv = "source\ttranslation\tkind\n"
    for c in cards:
        vocab_tsv += "\t".join(str(c[field]).replace("\t", " ").replace("\r", " ").replace("\n", " ") for field in ("source", "translation", "kind")) + "\n"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5,
                         allowZip64=True) as archive:
        for path, name in files:
            archive.write(path, arcname=name)
        archive.writestr("index.html", reader.encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr("vocabulary.tsv", ("\ufeff" + vocab_tsv).encode("utf-8"))
        archive.writestr("README_JA.txt", explanation.encode("utf-8"))
    return output.getvalue()

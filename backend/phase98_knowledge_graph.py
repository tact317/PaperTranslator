"""Phase98: explicit, evidence-anchored research graph for PeperTranslator.

No model-generated links, PDF mutation, or writes to Library/vocabulary/cache.
Facts and manually authored links live in a separate SQLite database. Deletions
are soft, and JSON export includes archived records for recovery.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Callable, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DOCUMENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
FACT_ID_RE = re.compile(r"^fact_[0-9a-f]{32}$")
LINK_ID_RE = re.compile(r"^link_[0-9a-f]{32}$")
KINDS = {"term", "measurement", "figure", "note"}
RELATIONS = {"cites", "compares", "supports", "contradicts", "uses", "related_to"}


class FactInput(BaseModel):
    document_id: str = Field(min_length=64, max_length=64)
    kind: str = Field(min_length=3, max_length=24)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=3000)
    page_number: int | None = Field(default=None, ge=1)
    figure_label: str = Field(default="", max_length=100)
    value_text: str = Field(default="", max_length=120)
    unit: str = Field(default="", max_length=80)
    source_quote: str = Field(default="", max_length=1000)


class LinkInput(BaseModel):
    from_id: str = Field(min_length=1, max_length=72)
    to_id: str = Field(min_length=1, max_length=72)
    relation: str = Field(min_length=2, max_length=24)
    note: str = Field(default="", max_length=2000)
    evidence_document_id: str | None = Field(default=None, max_length=64)
    evidence_page_number: int | None = Field(default=None, ge=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    return str(text).strip()


def _docs(raw: Any) -> dict[str, dict]:
    """Library is the only source of paper-node identity/metadata."""
    if not isinstance(raw, dict):
        return {}
    source = raw.get("documents", raw)
    if not isinstance(source, dict):
        return {}
    return {
        key: value for key, value in source.items()
        if DOCUMENT_ID_RE.fullmatch(key) and isinstance(value, dict)
    }


def _paper_id(document_id: str) -> str:
    return "paper_" + document_id


def _document(docs: dict[str, dict], document_id: str, page: int | None = None) -> dict:
    if not DOCUMENT_ID_RE.fullmatch(str(document_id)) or document_id not in docs:
        raise HTTPException(status_code=422, detail="Libraryに登録された論文IDを指定してください。")
    row = docs[document_id]
    if page is not None:
        count = int(row.get("page_count") or 0)
        if page < 1 or (count > 0 and page > count):
            raise HTTPException(status_code=422, detail=f"根拠ページは1～{count or '最終ページ'}で指定してください。")
    return row


def _require_fact_input(value: FactInput, docs: dict[str, dict]) -> dict:
    _document(docs, value.document_id, value.page_number)
    kind, title = _clean(value.kind), _clean(value.title)
    if kind not in KINDS or not title:
        raise HTTPException(status_code=422, detail="種別または名称が不正です。")
    return {
        "document_id": value.document_id,
        "kind": kind, "title": title,
        "body": _clean(value.body), "page_number": value.page_number,
        "figure_label": _clean(value.figure_label), "value_text": _clean(value.value_text),
        "unit": _clean(value.unit), "source_quote": _clean(value.source_quote),
    }


def _query_all(db: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(x) for x in db.execute(sql, args).fetchall()]


def create_graph_router(*, app_data_root: Path, library_loader: Callable[[], dict],
                        quality_loader: Callable[[str], dict] | None = None) -> APIRouter:
    """Attach once after the existing Library API. Database is created lazily."""
    router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])
    path = Path(app_data_root) / "knowledge_graph" / "graph_v1.sqlite3"

    @contextmanager
    def db_session():
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=15.0)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL, kind TEXT NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL, page_number INTEGER,
                figure_label TEXT NOT NULL, value_text TEXT NOT NULL, unit TEXT NOT NULL,
                source_quote TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, deleted_at TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS links (
                id TEXT PRIMARY KEY, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
                relation TEXT NOT NULL, note TEXT NOT NULL,
                evidence_document_id TEXT, evidence_page_number INTEGER,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pt98_facts_document ON facts(document_id, deleted_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pt98_links_source ON links(from_id, to_id, deleted_at)")
            db.commit()
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def known_docs() -> dict[str, dict]:
        return _docs(library_loader())

    def require_node(db: sqlite3.Connection, docs: dict[str, dict], node_id: str) -> None:
        if node_id.startswith("paper_") and DOCUMENT_ID_RE.fullmatch(node_id[6:]):
            _document(docs, node_id[6:])
            return
        if FACT_ID_RE.fullmatch(node_id):
            row = db.execute("SELECT document_id FROM facts WHERE id=? AND deleted_at IS NULL", (node_id,)).fetchone()
            if row and row[0] in docs:
                return
        raise HTTPException(status_code=422, detail="リンク先が存在しないか、アーカイブ済みです。")

    def require_link_input(db: sqlite3.Connection, value: LinkInput, docs: dict[str, dict]) -> dict:
        a, b = _clean(value.from_id), _clean(value.to_id)
        if a == b:
            raise HTTPException(status_code=422, detail="自分自身にはリンクできません。")
        require_node(db, docs, a)
        require_node(db, docs, b)
        relation = _clean(value.relation)
        if relation not in RELATIONS:
            raise HTTPException(status_code=422, detail="関係の種類が不正です。")
        evidence_id = value.evidence_document_id or None
        if evidence_id:
            _document(docs, evidence_id, value.evidence_page_number)
        elif value.evidence_page_number is not None:
            raise HTTPException(status_code=422, detail="根拠ページには論文IDも指定してください。")
        note = _clean(value.note)
        if relation == "cites" and (not a.startswith("paper_") or not b.startswith("paper_")):
            raise HTTPException(status_code=422, detail="引用関係は論文間で登録してください。")
        if relation == "cites" and not note and value.evidence_page_number is None:
            raise HTTPException(status_code=422, detail="引用関係には根拠ページまたはメモを記載してください。")
        return {"from_id": a, "to_id": b, "relation": relation, "note": note,
                "evidence_document_id": evidence_id, "evidence_page_number": value.evidence_page_number}

    @router.get("")
    def read_graph():
        docs = known_docs()
        paper_nodes = []
        for doc_id, row in sorted(docs.items(), key=lambda it: str(it[1].get("title") or it[0]).lower()):
            quality = quality_loader(doc_id) if quality_loader is not None else {}
            paper_nodes.append({
                "id": _paper_id(doc_id), "kind": "paper", "document_id": doc_id,
                "title": str(row.get("title") or (row.get("filenames") or [doc_id[:12]])[-1]),
                "page_count": int(row.get("page_count") or 0), "doi": row.get("doi"),
                "notes": str(row.get("notes") or ""), "paper_key": str(row.get("paper_key") or ""),
                "origin": "library", "quality_gate": quality.get("quality_gate"),
                "mono_ready": bool(quality.get("mono_ready")),
            })
        with db_session() as db:
            facts = _query_all(db, "SELECT * FROM facts WHERE deleted_at IS NULL ORDER BY created_at, id")
            # Orphaned annotations are preserved on disk, but not displayed as sourced facts.
            facts = [f for f in facts if f["document_id"] in docs]
            fact_ids = {f["id"] for f in facts}
            visible = {_paper_id(d) for d in docs} | fact_ids
            manual_links = [v for v in _query_all(db, "SELECT * FROM links WHERE deleted_at IS NULL ORDER BY created_at, id")
                            if v["from_id"] in visible and v["to_id"] in visible]
        source_links = [{"id": "anchor_" + f["id"], "from_id": _paper_id(f["document_id"]),
                         "to_id": f["id"], "relation": "source_of", "origin": "derived",
                         "note": "登録された原文論文", "evidence_document_id": f["document_id"],
                         "evidence_page_number": f["page_number"]} for f in facts]
        return {"version": 1, "papers": paper_nodes,
                "facts": [dict(f, origin="manual") for f in facts],
                "links": source_links + [dict(v, origin="manual") for v in manual_links],
                "manual_facts": len(facts), "manual_links": len(manual_links),
                "metadata": {"relationships_auto_inferred": False, "source_quotes_verified": False}}

    @router.post("/facts", status_code=201)
    def add_fact(value: FactInput):
        data = _require_fact_input(value, known_docs())
        now, fid = _now(), "fact_" + uuid4().hex
        with db_session() as db:
            db.execute("""INSERT INTO facts
                (id, document_id, kind, title, body, page_number, figure_label, value_text,
                 unit, source_quote, created_at, updated_at, deleted_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (fid, *(data[k] for k in ("document_id","kind","title","body","page_number",
                    "figure_label","value_text","unit","source_quote")), now, now))
        return {"status": "created", "id": fid}

    @router.put("/facts/{fact_id}")
    def update_fact(fact_id: str, value: FactInput):
        data = _require_fact_input(value, known_docs())
        if not FACT_ID_RE.fullmatch(fact_id):
            raise HTTPException(status_code=404, detail="項目が見つかりません。")
        with db_session() as db:
            exists = db.execute("SELECT id FROM facts WHERE id=? AND deleted_at IS NULL", (fact_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="項目が見つかりません。")
            db.execute("""UPDATE facts SET document_id=?,kind=?,title=?,body=?,page_number=?,
                figure_label=?,value_text=?,unit=?,source_quote=?,updated_at=? WHERE id=?""",
                (*[data[k] for k in ("document_id","kind","title","body","page_number",
                    "figure_label","value_text","unit","source_quote")], _now(), fact_id))
        return {"status": "updated", "id": fact_id}

    @router.delete("/facts/{fact_id}")
    def archive_fact(fact_id: str):
        if not FACT_ID_RE.fullmatch(fact_id):
            raise HTTPException(status_code=404, detail="項目が見つかりません。")
        with db_session() as db:
            result = db.execute("UPDATE facts SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                                (_now(), _now(), fact_id))
            if result.rowcount != 1:
                raise HTTPException(status_code=404, detail="項目が見つかりません。")
        return {"status": "archived", "id": fact_id, "recoverable": True}

    @router.post("/facts/{fact_id}/restore")
    def restore_fact(fact_id: str):
        if not FACT_ID_RE.fullmatch(fact_id):
            raise HTTPException(status_code=404, detail="項目が見つかりません。")
        with db_session() as db:
            row = db.execute("SELECT document_id FROM facts WHERE id=? AND deleted_at IS NOT NULL", (fact_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="アーカイブが見つかりません。")
            _document(known_docs(), row[0])
            db.execute("UPDATE facts SET deleted_at=NULL,updated_at=? WHERE id=?", (_now(), fact_id))
        return {"status": "restored", "id": fact_id}

    @router.post("/links", status_code=201)
    def add_link(value: LinkInput):
        docs = known_docs()
        with db_session() as db:
            data = require_link_input(db, value, docs)
            link_id, now = "link_" + uuid4().hex, _now()
            db.execute("""INSERT INTO links (id,from_id,to_id,relation,note,evidence_document_id,
                evidence_page_number,created_at,updated_at,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,NULL)""",
                (link_id, *[data[k] for k in ("from_id","to_id","relation","note",
                    "evidence_document_id","evidence_page_number")], now, now))
        return {"status": "created", "id": link_id}

    @router.put("/links/{link_id}")
    def update_link(link_id: str, value: LinkInput):
        if not LINK_ID_RE.fullmatch(link_id):
            raise HTTPException(status_code=404, detail="関係が見つかりません。")
        with db_session() as db:
            exists = db.execute("SELECT id FROM links WHERE id=? AND deleted_at IS NULL", (link_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="関係が見つかりません。")
            data = require_link_input(db, value, known_docs())
            db.execute("""UPDATE links SET from_id=?,to_id=?,relation=?,note=?,
                evidence_document_id=?,evidence_page_number=?,updated_at=? WHERE id=?""",
                (*[data[k] for k in ("from_id","to_id","relation","note",
                    "evidence_document_id","evidence_page_number")], _now(), link_id))
        return {"status": "updated", "id": link_id}

    @router.delete("/links/{link_id}")
    def archive_link(link_id: str):
        if not LINK_ID_RE.fullmatch(link_id):
            raise HTTPException(status_code=404, detail="関係が見つかりません。")
        with db_session() as db:
            result = db.execute("UPDATE links SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
                                (_now(), _now(), link_id))
            if result.rowcount != 1:
                raise HTTPException(status_code=404, detail="関係が見つかりません。")
        return {"status": "archived", "id": link_id, "recoverable": True}

    @router.post("/links/{link_id}/restore")
    def restore_link(link_id: str):
        if not LINK_ID_RE.fullmatch(link_id):
            raise HTTPException(status_code=404, detail="関係が見つかりません。")
        with db_session() as db:
            row = db.execute("SELECT * FROM links WHERE id=? AND deleted_at IS NOT NULL", (link_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="アーカイブが見つかりません。")
            docs = known_docs()
            require_node(db, docs, row["from_id"])
            require_node(db, docs, row["to_id"])
            db.execute("UPDATE links SET deleted_at=NULL,updated_at=? WHERE id=?", (_now(), link_id))
        return {"status": "restored", "id": link_id}

    @router.get("/archives")
    def list_archives():
        """Recent soft-deleted entries for in-app restore; no destructive purge."""
        with db_session() as db:
            facts = _query_all(db, "SELECT * FROM facts WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT 30")
            links = _query_all(db, "SELECT * FROM links WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT 30")
        return {"facts": facts, "links": links}

    @router.get("/export")
    def export_graph_backup():
        with db_session() as db:
            facts = _query_all(db, "SELECT * FROM facts ORDER BY created_at,id")
            links = _query_all(db, "SELECT * FROM links ORDER BY created_at,id")
        data = {"schema_version": 1, "generated_at": _now(), "storage": "manual_graph_only",
                "all_facts_including_archived": facts, "all_links_including_archived": links,
                "paper_reference_ids": sorted(known_docs()),
                "notice": "研究メモ・リンクはユーザー登録値であり、原文との照合は自動実施していません。"}
        return JSONResponse(data, headers={
            "Content-Disposition": "attachment; filename=PeperTranslator_KnowledgeGraph_Backup.json",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    return router

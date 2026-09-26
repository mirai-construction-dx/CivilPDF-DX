"""Full-text and semantic document search API (Phase 7 P2)."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database import get_db
from models.document import Document
from models.user import User, UserRole
from services import ai_settings as ai_settings_service
from services.access_control import visible_documents_query

router = APIRouter(prefix="/search", tags=["Search"])

# ── Schemas ───────────────────────────────────────────────────────────────────


class SearchHit(BaseModel):
    document_id: str
    title: str
    document_type: str
    status: str
    project_id: str
    snippet: str  # matched text fragment
    score: float
    tags: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: str  # "keyword" | "semantic"
    expanded_terms: list[str]  # terms actually used in FTS query
    total: int
    hits: list[SearchHit]


# ── FTS5 helpers ──────────────────────────────────────────────────────────────

_FTS_CREATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    document_id UNINDEXED,
    title,
    ocr_text,
    tags_text,
    tokenize='unicode61'
)
"""

_FTS_INDEX_DOC = """
INSERT INTO documents_fts(document_id, title, ocr_text, tags_text)
VALUES (:doc_id, :title, :ocr_text, :tags_text)
"""

_FTS_SEARCH = """
SELECT
    d.id AS document_id,
    d.title,
    d.document_type,
    d.status,
    d.project_id,
    d.tags,
    snippet(documents_fts, 2, '**', '**', '...', 16) AS snippet,
    bm25(documents_fts) AS score
FROM documents_fts
JOIN documents d ON d.id = documents_fts.document_id
WHERE documents_fts MATCH :query
ORDER BY score
LIMIT :limit
"""

_PG_SEARCH_SQL = """
SELECT
    d.id AS document_id,
    d.title,
    d.document_type,
    d.status,
    d.project_id,
    d.tags,
    ts_headline('simple', coalesce(d.ocr_text, ''), plainto_tsquery('simple', :query), 'MaxWords=24, MinWords=6') AS snippet,
    ts_rank(d.search_vector, plainto_tsquery('simple', :query)) AS score
FROM documents d
WHERE d.search_vector @@ plainto_tsquery('simple', :query)
ORDER BY score DESC
LIMIT :limit
"""

_PG_SYNC_SQL = """
UPDATE documents
SET search_vector = to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(ocr_text, '') || ' ' || coalesce(:tags_text, ''))
WHERE id = :doc_id
"""

_PG_ENSURE_SQL = """
ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector
"""

_PG_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_documents_search_vector
ON documents USING GIN (search_vector)
"""


def _ensure_fts_table(db: Session) -> None:
    """Create FTS5 virtual table if it does not exist."""
    if db.bind.dialect.name == "postgresql":
        db.execute(text(_PG_ENSURE_SQL))
        db.execute(text(_PG_INDEX_SQL))
        db.commit()
        return
    db.execute(text(_FTS_CREATE))
    db.commit()


def _sync_document_to_fts(db: Session, doc: Document) -> None:
    """Insert or replace a document in the FTS index."""
    tags_text = " ".join(doc.tags or [])
    ocr = (doc.ocr_text or "")[:10000]
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text(_PG_SYNC_SQL),
            {"doc_id": doc.id, "tags_text": tags_text},
        )
        db.commit()
        return
    db.execute(
        text("DELETE FROM documents_fts WHERE document_id = :doc_id"),
        {"doc_id": doc.id},
    )
    db.execute(
        text(_FTS_INDEX_DOC),
        {"doc_id": doc.id, "title": doc.title, "ocr_text": ocr, "tags_text": tags_text},
    )
    db.commit()


def _rebuild_fts_index(db: Session) -> int:
    """Sync all documents into FTS index. Returns count of indexed documents."""
    _ensure_fts_table(db)
    if db.bind.dialect.name == "postgresql":
        docs = db.query(Document).all()
        for doc in docs:
            _sync_document_to_fts(db, doc)
        return len(docs)
    db.execute(text("DELETE FROM documents_fts"))
    docs = db.query(
        Document
    ).all()  # Index all documents including those without physical files
    for doc in docs:
        tags_text = " ".join(doc.tags or [])
        ocr = (doc.ocr_text or "")[:10000]
        db.execute(
            text(_FTS_INDEX_DOC),
            {
                "doc_id": doc.id,
                "title": doc.title,
                "ocr_text": ocr,
                "tags_text": tags_text,
            },
        )
    db.commit()
    return len(docs)


def _fts_search(db: Session, fts_query: str, limit: int) -> list[dict]:
    """Execute FTS5 MATCH query and return raw rows."""
    try:
        if db.bind.dialect.name == "postgresql":
            rows = (
                db.execute(
                    text(_PG_SEARCH_SQL),
                    {"query": fts_query, "limit": limit},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]
        rows = (
            db.execute(
                text(_FTS_SEARCH),
                {"query": fts_query, "limit": limit},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]
    except Exception:
        # FTS5 syntax error or empty index — return empty
        return []


# ── Semantic query expansion via Claude ───────────────────────────────────────

_EXPAND_SYSTEM = """あなたは建設業の文書検索エキスパートです。
ユーザーのクエリを受け取り、全文検索エンジンで使う関連キーワードを5〜8個生成してください。
建設業・土木・建築の専門用語も含め、同義語・関連語を考慮してください。
必ずJSON配列で返してください: ["term1", "term2", ...]"""


def _expand_query_with_claude(query: str, db: Session) -> list[str]:
    """Use Claude to expand search query into related terms. Falls back to original on error.

    Honours the same admin kill switch, key and model settings as the AI API
    (services.ai_settings) instead of reading the environment directly.
    """
    if not ai_settings_service.is_ai_enabled(db):
        return [query]
    api_key = ai_settings_service.get_api_key(db)
    if not api_key:
        return [query]

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            # Query expansion runs on every semantic search: keep the small,
            # cheap model regardless of the (possibly larger) admin setting.
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": f"クエリ: {query}"}],
        )
        raw = message.content[0].text
        terms = json.loads(raw)
        if isinstance(terms, list) and terms:
            return [str(t) for t in terms[:8]]
    except Exception:
        pass

    return [query]


def _escape_fts_term(term: str) -> str:
    """Escape a term for FTS5 and append prefix wildcard."""
    # Remove FTS5 special chars that would cause syntax errors
    clean = re.sub(r'["\(\)\{\}\[\]\*\:,\.\-]', " ", term).strip()
    if not clean:
        return '""'
    # Use prefix wildcard (*) so "構造" matches "構造図", "構造計算", etc.
    return f'"{clean}"*'


def _build_fts_query(terms: list[str], mode: str) -> str:
    """Build FTS5 query string from terms.

    keyword mode: prefix match on the original query
    semantic mode: OR of all expanded terms with prefix matching
    """
    if mode == "keyword" or len(terms) == 1:
        return _escape_fts_term(terms[0])

    # Semantic: OR search across all expanded terms
    return " OR ".join(_escape_fts_term(t) for t in terms)


# ── Access filter helper ───────────────────────────────────────────────────────


def _accessible_document_ids(
    db: Session, document_ids: list[str], current_user: User
) -> set[str]:
    """Return which of these documents the caller may read.

    Uses the same canonical RBAC filter as every other document read
    (``visible_documents_query``) but resolves all hits in **one** query. The
    previous implementation called ``document_visible`` once per hit, which
    issued up to ``limit`` (≤100) extra SELECTs on a hot read path.

    Hits whose document row no longer exists are excluded: the full-text index
    can outlive a document, and returning a hit for a document the caller cannot
    load is not useful (the old per-hit helper treated a missing row as visible).
    """
    if not document_ids:
        return set()
    rows = (
        visible_documents_query(db, current_user)
        .filter(Document.id.in_(document_ids))
        .with_entities(Document.id)
        .all()
    )
    return {row[0] for row in rows}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/documents", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, max_length=200, description="検索クエリ"),
    mode: str = Query("keyword", pattern="^(keyword|semantic)$"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """Search documents using full-text search (keyword) or AI-expanded semantic search."""
    _ensure_fts_table(db)

    # Auto-sync: rebuild if FTS count differs from documents count
    if db.bind.dialect.name == "postgresql":
        fts_count = (
            db.execute(
                text("SELECT COUNT(*) FROM documents WHERE search_vector IS NOT NULL")
            ).scalar()
            or 0
        )
    else:
        fts_count = db.execute(text("SELECT COUNT(*) FROM documents_fts")).scalar() or 0
    doc_count = db.query(Document).count()
    if fts_count != doc_count:
        _rebuild_fts_index(db)

    if mode == "semantic":
        expanded_terms = _expand_query_with_claude(q, db)
    else:
        expanded_terms = [q]

    fts_query = _build_fts_query(expanded_terms, mode)
    rows = _fts_search(db, fts_query, limit)

    def _parse_tags(raw) -> list[str]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    accessible_ids = _accessible_document_ids(
        db, [r["document_id"] for r in rows], current_user
    )
    hits = [
        SearchHit(
            document_id=r["document_id"],
            title=r["title"],
            document_type=r["document_type"],
            status=r["status"],
            project_id=r["project_id"],
            snippet=r.get("snippet") or "",
            score=abs(float(r.get("score") or 0)),
            tags=_parse_tags(r.get("tags")),
        )
        for r in rows
        if r["document_id"] in accessible_ids
    ]

    return SearchResponse(
        query=q,
        mode=mode,
        expanded_terms=expanded_terms,
        total=len(hits),
        hits=hits,
    )


@router.post("/documents/reindex", status_code=status.HTTP_200_OK)
def reindex_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Rebuild the full-text search index (admin/manager only)."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )
    count = _rebuild_fts_index(db)
    return {"indexed": count, "status": "ok"}


@router.get("/documents/suggest", response_model=list[str])
def suggest_terms(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """Return AI-expanded search terms for a query (used by frontend autocomplete)."""
    return _expand_query_with_claude(q, db)

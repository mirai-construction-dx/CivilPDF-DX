"""AI-powered document analysis API endpoints (Phase 7)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database import get_db
from models.document import Document
from models.user import User
from services import ai_settings as ai_settings_service
from services.access_control import document_visible
from services.audit_chain_service import create_chained_audit_log

router = APIRouter(prefix="/ai", tags=["AI"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ClassifyResponse(BaseModel):
    document_id: str
    drawing_type: Optional[str]  # 図面種別
    project_type: Optional[str]  # プロジェクト種別
    confidence: float  # 0.0–1.0
    tags: list[str]
    classified_at: str
    model: str


class ExtractResponse(BaseModel):
    document_id: str
    extracted_at: str
    model: str
    data: dict  # 抽出された構造化データ


class SummaryResponse(BaseModel):
    document_id: str
    summary: str
    summarized_at: str
    model: str


# ── Helpers ───────────────────────────────────────────────────────────────────

_CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # Cost-efficient for classification


def _check_document_access(doc: Document, current_user: User) -> None:
    """Raise 404 if the user is not allowed to access this document."""
    if not document_visible(doc, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )


def _get_document_text(doc: Document) -> str:
    """Return OCR text if available, otherwise extract via pypdf."""
    if doc.ocr_text:
        return doc.ocr_text

    if not doc.file_path or not Path(doc.file_path).exists():
        return ""

    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(doc.file_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        return "\n".join(pages)
    except Exception:
        return ""


def _ensure_ai_enabled(db: Session) -> None:
    """Kill switch gate — checked before any document text is extracted."""
    if not ai_settings_service.is_ai_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 機能は無効化されています（設定画面で有効化してください）",
        )


def _get_anthropic_client(db: Session):
    """Return Anthropic client; checks DB first, then env var fallback."""
    try:
        import anthropic
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="anthropic package not installed",
        ) from exc

    _ensure_ai_enabled(db)
    api_key = ai_settings_service.get_api_key(db)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )
    return anthropic.Anthropic(api_key=api_key)


def _get_model_name(db: Session) -> str:
    """Return model name from DB settings, fallback to compile-time default."""
    return ai_settings_service.get_model_name(db, _CLAUDE_MODEL)


# ── Classification ─────────────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """あなたは建設業の文書分類AIです。与えられた文書テキストを分析し、以下のカテゴリに分類してください。

図面種別 (drawing_type):
- "平面図" — 平面レイアウト・間取り図
- "立面図" — 建物外観・ファサード図
- "断面図" — 断面・剖面図
- "構造図" — 構造計算・配筋図・鉄骨図
- "設備図" — 電気・機械・給排水設備図
- "その他図面" — 上記に該当しない図面
- null — 図面ではない文書

プロジェクト種別 (project_type):
- "土木" — 土木工事・インフラ
- "建築" — 建築物・建屋
- "設備" — 設備工事単体
- "道路" — 道路・舗装
- "橋梁" — 橋・高架
- "その他" — 上記以外
- null — 判断不能

必ずJSON形式で回答してください。
{"drawing_type": "...", "project_type": "...", "confidence": 0.9, "reasoning": "..."}"""


@router.post("/documents/{document_id}/classify", response_model=ClassifyResponse)
def classify_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClassifyResponse:
    """Classify a document using Claude AI into drawing type and project type."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    _check_document_access(doc, current_user)
    _ensure_ai_enabled(db)

    text = _get_document_text(doc)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text found in document — run OCR first",
        )

    client = _get_anthropic_client(db)
    model_name = _get_model_name(db)

    prompt = f"以下の文書を分類してください:\n\n文書名: {doc.title}\n\nテキスト（最初の3000字）:\n{text[:3000]}"

    message = client.messages.create(
        model=model_name,
        max_tokens=256,
        system=_CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: parse only what we can
        result = {
            "drawing_type": None,
            "project_type": None,
            "confidence": 0.0,
            "reasoning": raw,
        }

    drawing_type = result.get("drawing_type")
    project_type = result.get("project_type")
    confidence = float(result.get("confidence", 0.8))

    # Build tag list
    tags: list[str] = []
    if drawing_type:
        tags.append(f"図面:{drawing_type}")
    if project_type:
        tags.append(f"種別:{project_type}")
    tags.append("ai分類済")

    # Merge tags into document (preserve existing)
    existing_tags = list(doc.tags or [])
    merged_tags = list({*existing_tags, *tags})
    doc.tags = merged_tags

    classified_at = datetime.now(timezone.utc).isoformat()
    extra = dict(doc.extra_data or {})
    extra["ai_classification"] = {
        "drawing_type": drawing_type,
        "project_type": project_type,
        "confidence": confidence,
        "reasoning": result.get("reasoning", ""),
        "classified_at": classified_at,
        "model": model_name,
    }
    doc.extra_data = extra
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="ai.document_classified",
        resource_type="document",
        resource_id=document_id,
        detail=json.dumps(
            {
                "drawing_type": drawing_type,
                "project_type": project_type,
                "confidence": confidence,
                "model": model_name,
            },
            ensure_ascii=False,
        ),
        ip_address=None,
    )

    return ClassifyResponse(
        document_id=document_id,
        drawing_type=drawing_type,
        project_type=project_type,
        confidence=confidence,
        tags=merged_tags,
        classified_at=classified_at,
        model=model_name,
    )


# ── Structured Data Extraction ─────────────────────────────────────────────────

_EXTRACT_SYSTEM = """あなたは建設業の文書データ抽出AIです。文書から以下の情報を抽出し、JSON形式で返してください。

抽出項目:
- construction_name: 工事名・案件名
- contractor: 施工会社・元請け
- site_location: 現場住所・場所
- amount: 金額（数値とおよその単位）
- start_date: 工期開始日（YYYY-MM-DD形式または null）
- end_date: 工期終了日（YYYY-MM-DD形式または null）
- responsible_person: 担当者名
- checklist_items: 承認チェックリスト（配列）

見つからない項目は null にしてください。"""


@router.post("/documents/{document_id}/extract", response_model=ExtractResponse)
def extract_document_data(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExtractResponse:
    """Extract structured data (dates, amounts, names) from a document using Claude AI."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    _check_document_access(doc, current_user)
    _ensure_ai_enabled(db)

    text = _get_document_text(doc)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text found in document — run OCR first",
        )

    client = _get_anthropic_client(db)
    model_name = _get_model_name(db)

    prompt = f"文書名: {doc.title}\n\nテキスト:\n{text[:4000]}"

    message = client.messages.create(
        model=model_name,
        max_tokens=512,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        extracted = {"raw_response": raw}

    extracted_at = datetime.now(timezone.utc).isoformat()

    # Persist extracted data
    extra = dict(doc.extra_data or {})
    extra["ai_extraction"] = {
        "data": extracted,
        "extracted_at": extracted_at,
        "model": model_name,
    }
    doc.extra_data = extra
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="ai.document_extracted",
        resource_type="document",
        resource_id=document_id,
        detail=json.dumps({"model": model_name}, ensure_ascii=False),
        ip_address=None,
    )

    return ExtractResponse(
        document_id=document_id,
        extracted_at=extracted_at,
        model=model_name,
        data=extracted,
    )


# ── AI Summary ─────────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM = """あなたは建設業の文書要約AIです。
与えられた文書を3〜5行の簡潔な日本語で要約してください。
承認者が内容を素早く把握できるよう、工事内容・目的・重要事項を含めてください。"""


@router.get("/documents/{document_id}/summary", response_model=SummaryResponse)
def get_document_summary(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SummaryResponse:
    """Generate a brief AI summary of a document for approvers."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    _check_document_access(doc, current_user)
    _ensure_ai_enabled(db)

    text = _get_document_text(doc)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text found in document — run OCR first",
        )

    client = _get_anthropic_client(db)
    model_name = _get_model_name(db)

    prompt = f"文書名: {doc.title}\n\nテキスト:\n{text[:5000]}"

    message = client.messages.create(
        model=model_name,
        max_tokens=256,
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = message.content[0].text.strip()
    summarized_at = datetime.now(timezone.utc).isoformat()

    # Cache summary in extra_data
    extra = dict(doc.extra_data or {})
    extra["ai_summary"] = {
        "summary": summary,
        "summarized_at": summarized_at,
        "model": model_name,
    }
    doc.extra_data = extra
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="ai.document_summarized",
        resource_type="document",
        resource_id=document_id,
        detail=json.dumps({"model": model_name}, ensure_ascii=False),
        ip_address=None,
    )

    return SummaryResponse(
        document_id=document_id,
        summary=summary,
        summarized_at=summarized_at,
        model=model_name,
    )

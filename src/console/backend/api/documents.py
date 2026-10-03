import io
import json
import math
import re
import uuid
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Query,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, contains_eager
from typing import List, Optional
import aiofiles

from database import get_db
from models.user import User, Project
from models.document import Document, DocumentStatus, DocumentType
from auth.dependencies import get_current_user
from datetime import datetime, timezone

from api.schemas import (
    DocumentResponse,
    DocumentUpdate,
    TimestampResponse,
    TimestampVerifyResponse,
)
from api.csv_export import (
    DEFAULT_CHUNK_ROWS,
    csv_stream_response,
    ensure_export_within_limit,
)
from config import settings
from services import timestamp_service
from services.pdfa_validator import validate_pdfa
from services.retention_service import apply_retention_policy
from services.audit_chain_service import create_chained_audit_log
from services.access_control import (
    assert_document_visible,
    assert_project_visible,
    can_delete_document,
    can_write_documents,
    visible_documents_query,
)

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_MIME_TYPES = {"application/pdf"}
MAX_FILE_BYTES = settings.max_file_size_mb * 1024 * 1024
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f\"\\]")


def _safe_filename(filename: str) -> str:
    """Sanitize a filename for use inside Content-Disposition header values."""
    cleaned = _CONTROL_CHARS.sub("_", filename or "download")
    return cleaned.strip() or "download"


def _ensure_pdf_content(first_chunk: bytes) -> bool:
    """Return True when the uploaded content looks like a PDF (magic bytes)."""
    return first_chunk.startswith(b"%PDF-")


# extra_data keys used to restore the pre-deletion state (WEB-DOC-005 C-1).
_STATUS_BEFORE_DELETION = "status_before_deletion"
_ARCHIVED_BEFORE_DELETION = "is_archived_before_deletion"


def _assert_not_trashed(doc: Document) -> Document:
    """AT-DOC-006: soft-deleted documents are 404 on direct-URL reads.

    The trash list and the restore endpoint are the only ways to reach a
    document that is in the trash.
    """
    if doc.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return doc


def _assert_can_delete(doc: Document, user: User) -> None:
    """§5.2 文書削除 / ※3 復元: admin=全て, manager/engineer=自分, viewer=不可."""
    if not can_delete_document(doc, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )


@router.get("/", response_model=None)
def list_documents(
    project_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    document_type: Optional[DocumentType] = Query(None),
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_meta: bool = Query(False, description="paginated response metadata"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = visible_documents_query(db, current_user)
    q = q.filter(Document.deletion_requested_at.is_(None))
    if project_id:
        q = q.filter(Document.project_id == project_id)
    if organization_id:
        q = q.join(Project, Document.project_id == Project.id).filter(
            Project.organization_id == organization_id
        )
    if document_type:
        q = q.filter(Document.document_type == document_type)
    if status_filter:
        q = q.filter(Document.status == status_filter)

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    if include_meta:
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if total else 0,
        }
    return items


@router.get("/trash", response_model=List[DocumentResponse])
def list_trash(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return soft-deleted documents visible to the user (ごみ箱)."""
    q = visible_documents_query(db, current_user)
    q = q.filter(Document.deletion_requested_at.is_not(None))
    return q.order_by(Document.deletion_requested_at.desc()).all()


@router.get("/export.csv")
def export_documents(
    project_id: Optional[str] = Query(None),
    document_type: Optional[DocumentType] = Query(None),
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export the visible document list as CSV (RBAC-scoped, Excel-safe).

    The result set is streamed in bounded batches and capped at
    ``MAX_EXPORT_ROWS``. ``contains_eager`` reuses the explicit joins below so
    the per-row ``doc.project`` / ``doc.owner`` access does not emit one query
    per document (N+1).
    """
    q = (
        visible_documents_query(db, current_user)
        .filter(Document.deletion_requested_at.is_(None))
        .join(Project, Document.project_id == Project.id)
        .join(User, Document.owner_id == User.id)
        .options(
            contains_eager(Document.project),
            contains_eager(Document.owner),
        )
    )
    if project_id:
        q = q.filter(Document.project_id == project_id)
    if document_type:
        q = q.filter(Document.document_type == document_type)
    if status_filter:
        q = q.filter(Document.status == status_filter)

    row_count = q.order_by(None).count()
    ensure_export_within_limit(row_count, label="文書")

    docs = q.order_by(Document.created_at.desc()).yield_per(DEFAULT_CHUNK_ROWS)
    headers = [
        "id",
        "title",
        "document_type",
        "status",
        "revision",
        "project_code",
        "project_name",
        "owner_email",
        "owner_name",
        "file_size_bytes",
        "page_count",
        "tags",
        "is_pdfa",
        "created_at",
        "updated_at",
        "retention_expires_at",
    ]

    def rows():
        for doc in docs:

            def _iso(value):
                if not value:
                    return ""
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.isoformat()

            tags = doc.tags or []
            if isinstance(tags, list):
                tags_text = " ".join(str(t) for t in tags)
            else:
                tags_text = str(tags)
            yield [
                doc.id,
                doc.title,
                doc.document_type.value
                if hasattr(doc.document_type, "value")
                else str(doc.document_type),
                doc.status.value if hasattr(doc.status, "value") else str(doc.status),
                doc.revision,
                doc.project.code,
                doc.project.name,
                doc.owner.email,
                doc.owner.full_name,
                doc.file_size,
                doc.page_count,
                tags_text,
                "yes" if doc.is_pdfa else "no",
                _iso(doc.created_at),
                _iso(doc.updated_at),
                _iso(doc.retention_expires_at),
            ]

    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.exported",
        resource_type="document",
        resource_id=None,
        detail=f"document list CSV export ({row_count} rows)",
        ip_address=None,
    )
    return csv_stream_response(
        headers,
        rows(),
        f"documents-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv",
    )


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: str = Form(...),
    title: str = Form(...),
    document_type: DocumentType = Form(DocumentType.OTHER),
    file: UploadFile = File(...),
    # ISO 19650 metadata fields
    iso19650_originator: Optional[str] = Form(None),
    iso19650_functional_breakdown: Optional[str] = Form(None),
    iso19650_form: Optional[str] = Form(None),
    iso19650_discipline: Optional[str] = Form(None),
    iso19650_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    assert_project_visible(project, current_user)
    if not can_write_documents(current_user):
        # §5.2 文書アップロード: viewer は不可
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are allowed",
        )

    # Save file
    upload_dir = Path(settings.upload_dir) / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = upload_dir / f"{file_id}.pdf"

    first_chunk = await file.read(4096)
    if not _ensure_pdf_content(first_chunk):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content is not a valid PDF",
        )

    total_size = len(first_chunk)
    if total_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {settings.max_file_size_mb}MB limit",
        )
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(first_chunk)
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_BYTES:
                await f.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds {settings.max_file_size_mb}MB limit",
                )
            await f.write(chunk)

    content = Path(file_path).read_bytes()

    doc = Document(
        title=title,
        document_type=document_type,
        filename=file.filename or "upload.pdf",
        file_path=str(file_path),
        file_size=len(content),
        mime_type="application/pdf",
        project_id=project_id,
        owner_id=current_user.id,
        iso19650_originator=iso19650_originator,
        iso19650_functional_breakdown=iso19650_functional_breakdown,
        iso19650_form=iso19650_form,
        iso19650_discipline=iso19650_discipline,
        iso19650_number=iso19650_number,
    )
    db.add(doc)
    db.flush()  # get doc.id and doc.created_at assigned

    # PDF/A-3 validation (ISO 14289 — 電子帳簿保存法・e-文書法要件)
    try:
        pdfa_result = validate_pdfa(content, str(file_path))
        doc.is_pdfa = pdfa_result["is_pdfa"]
        doc.pdfa_version = pdfa_result.get("pdfa_version")
        doc.pdfa_validation_result = pdfa_result
    except Exception:
        pass  # validation failure is non-fatal

    # Apply retention policy based on document type
    apply_retention_policy(db, doc)

    # Generate timestamp (電子帳簿保存法・e-文書法)
    try:
        ts = timestamp_service.generate_timestamp(
            content, file.filename or "upload.pdf"
        )
        doc.timestamp_hash = ts["file_hash"]
        doc.timestamp_token = ts["token_b64"]
        doc.timestamp_tsa_url = ts["tsa_url"]
        doc.timestamp_verified_at = datetime.now(timezone.utc)
    except Exception:
        pass  # timestamp failure is non-fatal; log but continue

    db.commit()
    db.refresh(doc)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.uploaded",
        resource_type="document",
        resource_id=doc.id,
        detail=json.dumps(
            {
                "project_id": project_id,
                "title": title,
                "file_size": total_size,
                "document_type": (
                    document_type.value
                    if hasattr(document_type, "value")
                    else str(document_type)
                ),
                # Initial content hash, so the chain holds the original even if
                # the file is later changed and re-stamped (decision D-1).
                "file_hash": doc.timestamp_hash,
            },
            ensure_ascii=False,
        ),
        ip_address=None,
    )
    return doc


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_not_trashed(doc)
    # D-3b (2026-10-03): record document views (READ) in the tamper-evident
    # chain. Only successful views are recorded; the client IP comes from the
    # request context. Downloads are recorded separately as document.downloaded.
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.viewed",
        resource_type="document",
        resource_id=doc.id,
        detail=None,
        ip_address=None,
    )
    db.refresh(doc)
    return doc


@router.patch("/{doc_id}", response_model=DocumentResponse)
def update_document(
    doc_id: str,
    body: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_not_trashed(doc)
    if doc.owner_id != current_user.id and current_user.role.value not in (
        "admin",
        "manager",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.updated",
        resource_type="document",
        resource_id=doc.id,
        detail=json.dumps(body.model_dump(exclude_none=True), ensure_ascii=False),
        ip_address=None,
    )
    return doc


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_not_trashed(doc)
    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk"
        )
    # Embed the DX document id into the PDF Info dict (/CivilPdfDxDocId) so the
    # CivilPDF-Editor can read it back and target the right document when syncing
    # a ReviewSidecar. Existing metadata is preserved; falls back to the raw file
    # if embedding fails (e.g. encrypted/corrupt PDF).
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(doc.file_path)
        writer = PdfWriter()
        writer.append(reader)
        metadata = dict(reader.metadata or {})
        metadata["/CivilPdfDxDocId"] = doc.id
        writer.add_metadata(metadata)
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        create_chained_audit_log(
            db,
            user_id=current_user.id,
            action="document.downloaded",
            resource_type="document",
            resource_id=doc.id,
            detail=json.dumps({"filename": _safe_filename(doc.filename)}),
            ip_address=None,
        )
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{_safe_filename(doc.filename)}"'
                )
            },
        )
    except Exception:
        create_chained_audit_log(
            db,
            user_id=current_user.id,
            action="document.downloaded",
            resource_type="document",
            resource_id=doc.id,
            detail=json.dumps({"filename": _safe_filename(doc.filename)}),
            ip_address=None,
        )
        return FileResponse(
            path=doc.file_path,
            filename=_safe_filename(doc.filename),
            media_type="application/pdf",
        )


@router.post("/{doc_id}/timestamp", response_model=TimestampResponse)
async def apply_timestamp(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply RFC 3161 timestamp to an existing document (電子帳簿保存法・e-文書法)."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_not_trashed(doc)
    if doc.owner_id != current_user.id and current_user.role.value not in (
        "admin",
        "manager",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk"
        )

    file_content = Path(doc.file_path).read_bytes()
    ts = timestamp_service.generate_timestamp(file_content, doc.filename)

    # Re-stamping overwrites the single timestamp field on the document. Keep
    # the superseded hash in the tamper-evident audit chain so a re-stamp after
    # the file changed stays traceable (requirements v1.1.0, decision D-1).
    previous_hash = doc.timestamp_hash
    previous_verified_at = doc.timestamp_verified_at

    doc.timestamp_hash = ts["file_hash"]
    doc.timestamp_token = ts["token_b64"]
    doc.timestamp_tsa_url = ts["tsa_url"]
    doc.timestamp_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.timestamped",
        resource_type="document",
        resource_id=doc.id,
        detail=json.dumps(
            {
                "token_type": ts["token_type"],
                "tsa_url": ts["tsa_url"],
                "file_hash": ts["file_hash"],
                "previous_file_hash": previous_hash,
                "previous_verified_at": (
                    previous_verified_at.isoformat() if previous_verified_at else None
                ),
                "hash_changed": bool(previous_hash)
                and previous_hash != ts["file_hash"],
            }
        ),
        ip_address=None,
    )

    return TimestampResponse(
        document_id=doc.id,
        file_hash=ts["file_hash"],
        token_type=ts["token_type"],
        tsa_url=ts["tsa_url"],
        verified_at=doc.timestamp_verified_at,
        token_present=bool(doc.timestamp_token),
    )


@router.get("/{doc_id}/timestamp/verify", response_model=TimestampVerifyResponse)
def verify_timestamp(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify that the stored timestamp matches the current file content."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_not_trashed(doc)

    if not doc.timestamp_hash or not doc.timestamp_token:
        return TimestampVerifyResponse(
            document_id=doc.id,
            valid=False,
            message="No timestamp recorded for this document",
        )

    if not doc.file_path or not Path(doc.file_path).exists():
        return TimestampVerifyResponse(
            document_id=doc.id,
            valid=False,
            message="File not found on disk — cannot verify integrity",
        )

    file_content = Path(doc.file_path).read_bytes()
    is_valid = timestamp_service.verify_file_against_timestamp(
        file_content, doc.timestamp_hash, doc.timestamp_token
    )

    return TimestampVerifyResponse(
        document_id=doc.id,
        valid=is_valid,
        message="Timestamp valid — file integrity confirmed"
        if is_valid
        else "Timestamp mismatch — file may have been modified",
        file_hash=doc.timestamp_hash,
        verified_at=doc.timestamp_verified_at,
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_can_delete(doc, current_user)

    if doc.deletion_requested_at is not None:
        # B-4: idempotent. Keep the first deletion request time (the 30-day
        # grace period starts from it) and do not log a second deletion.
        return

    # Soft delete: retention/GDPR requires a grace period before physical
    # removal. The background deletion job performs the physical erasure.
    now = datetime.now(timezone.utc)
    # C-1: remember the pre-deletion state so restore can bring it back
    # (no dedicated column; stored in the existing extra_data JSON).
    status_value = doc.status.value if hasattr(doc.status, "value") else doc.status
    doc.extra_data = {
        **(doc.extra_data or {}),
        _STATUS_BEFORE_DELETION: status_value,
        _ARCHIVED_BEFORE_DELETION: bool(doc.is_archived),
    }
    doc.deletion_requested_at = now
    doc.is_archived = True
    doc.status = DocumentStatus.ARCHIVED
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.soft_deleted",
        resource_type="document",
        resource_id=doc.id,
        detail=json.dumps({"deletion_requested_at": now.isoformat()}),
        ip_address=None,
    )


@router.post("/{doc_id}/restore", response_model=DocumentResponse)
def restore_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore a soft-deleted document (ごみ箱から復元)."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    _assert_can_delete(doc, current_user)
    if doc.deletion_requested_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not in the trash",
        )
    if not doc.file_path:
        # The deletion job already erased the file (services/deletion_job.py
        # nulls file_path); there is nothing left to restore.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has already been physically deleted",
        )
    # C-1: restore the pre-deletion status. Legacy rows deleted before the
    # state was recorded fall back to DRAFT. Approval workflows are untouched.
    extra = dict(doc.extra_data or {})
    saved_status = extra.pop(_STATUS_BEFORE_DELETION, None)
    saved_archived = extra.pop(_ARCHIVED_BEFORE_DELETION, False)
    if saved_status:
        try:
            restored_status = DocumentStatus(saved_status)
        except ValueError:
            restored_status = DocumentStatus.DRAFT
        restored_archived = bool(saved_archived)
    elif doc.status != DocumentStatus.ARCHIVED:
        # Trashed by a path that does not record the prior state (e.g. the
        # GDPR deletion request in api/privacy.py only sets
        # deletion_requested_at). The status was never changed, so keep it.
        restored_status = doc.status
        restored_archived = bool(doc.is_archived)
    else:
        restored_status = DocumentStatus.DRAFT
        restored_archived = False
    doc.extra_data = extra
    doc.deletion_requested_at = None
    doc.is_archived = restored_archived
    doc.status = restored_status
    db.commit()
    db.refresh(doc)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.restored",
        resource_type="document",
        resource_id=doc.id,
        detail=json.dumps({"restored_at": datetime.now(timezone.utc).isoformat()}),
        ip_address=None,
    )
    return doc

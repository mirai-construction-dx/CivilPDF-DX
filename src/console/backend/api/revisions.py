import json
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.schemas import RevisionResponse
from config import settings
from auth.dependencies import get_current_user
from database import get_db
from models.document import Document, DocumentVersion
from models.user import User, UserRole
from services.audit_chain_service import create_chained_audit_log
from services.access_control import assert_document_visible

router = APIRouter(prefix="/documents", tags=["Revisions"])


def _require_manager(user: User) -> None:
    if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Manager or Admin required")


@router.post("/{doc_id}/revisions", status_code=201, response_model=RevisionResponse)
async def upload_revision(
    doc_id: str,
    file: UploadFile = File(...),
    revision: Optional[str] = Form(None),
    revision_note: Optional[str] = Form(None),
    is_from_editor: bool = Form(False),
    editor_session_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RevisionResponse:
    _require_manager(current_user)
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    content = await file.read()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File content is not a valid PDF")
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds {settings.max_file_size_mb}MB limit",
        )
    file_size = len(content)
    max_version = (
        db.query(func.max(DocumentVersion.version_number))
        .filter(DocumentVersion.document_id == doc_id)
        .scalar()
    )
    next_version = (max_version or 0) + 1

    # Persist the revision bytes. Without them a "version" is metadata only and
    # the old revision can never be retrieved (WEB-DOC-003 旧版参照).
    version_dir = Path(settings.upload_dir) / doc_id / "revisions"
    version_dir.mkdir(parents=True, exist_ok=True)
    version_path = version_dir / f"v{next_version:04d}-{uuid.uuid4().hex[:8]}.pdf"
    version_path.write_bytes(content)

    version = DocumentVersion(
        document_id=doc_id,
        version_number=next_version,
        filename=file.filename,
        file_path=str(version_path),
        file_size=file_size,
        created_by=current_user.id,
        revision=revision,
        revision_note=revision_note,
        is_from_editor=is_from_editor,
        editor_session_id=editor_session_id,
    )
    db.add(version)
    db.flush()
    db.refresh(version)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.revision.uploaded",
        resource_type="document",
        resource_id=doc_id,
        detail=json.dumps({"version_number": next_version, "revision": revision}),
        ip_address=None,
    )
    db.refresh(version)
    return RevisionResponse.model_validate(version)


@router.get("/{doc_id}/revisions", response_model=List[RevisionResponse])
def list_revisions(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[RevisionResponse]:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version_number.asc())
        .all()
    )
    return [RevisionResponse.model_validate(v) for v in versions]


@router.get("/{doc_id}/revisions/{version_number}/download")
def download_revision(
    doc_id: str,
    version_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the stored bytes of one revision (旧版参照).

    Revisions written before the bytes started being persisted have no
    ``file_path``; those respond 410 so the caller can tell "never stored"
    apart from "not found".
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert_document_visible(doc, current_user)
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc_id,
            DocumentVersion.version_number == version_number,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Revision not found")
    if not version.file_path or not Path(version.file_path).exists():
        raise HTTPException(
            status_code=410,
            detail="Revision content was not stored for this version",
        )
    return FileResponse(
        version.file_path,
        media_type="application/pdf",
        filename=version.filename or f"revision-{version_number}.pdf",
    )

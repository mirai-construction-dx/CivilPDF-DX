import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas import (
    EditorEventItem,
    EditorEventsResponse,
    FlattenCheckResponse,
    ReviewSidecarGetResponse,
    ReviewSidecarImportResponse,
    ReviewSidecarPayload,
    WorkflowStatusResponse,
)
from auth.dependencies import get_current_user
from database import get_db
from models.document import Document, DocumentStatus
from models.user import User, UserRole
from services.audit_chain_service import create_chained_audit_log
from services.editor_service import determine_editor_status
from services.access_control import assert_document_visible

# Aligned with CivilPDF-Editor v1.12.3 (MAX_SIDECAR_BYTES).
# 8 MiB supports review sidecars with several image stamps while still
# bounding abuse. If photo-grade stamp images become common, move to
# client-side compression instead of raising this further (Issue #92).
_MAX_SIDECAR_BYTES = 8 * 1024 * 1024  # 8 MiB

router = APIRouter(prefix="/documents", tags=["Editor Integration"])


def _require_manager(user: User) -> None:
    if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Manager or Admin required")


def _require_engineer(user: User) -> None:
    if user.role not in (UserRole.ENGINEER, UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Engineer or higher required")


def _get_doc_or_404(doc_id: str, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{doc_id}/review-sidecar", response_model=ReviewSidecarImportResponse)
def import_review_sidecar(
    doc_id: str,
    payload: ReviewSidecarPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewSidecarImportResponse:
    _require_manager(current_user)
    sidecar_dict = payload.model_dump()
    if (
        len(json.dumps(sidecar_dict, ensure_ascii=False).encode("utf-8"))
        > _MAX_SIDECAR_BYTES
    ):
        raise HTTPException(
            status_code=413, detail="Review sidecar payload is too large"
        )
    doc = _get_doc_or_404(doc_id, db)
    assert_document_visible(doc, current_user)
    # An approved document is evidence: importing a sidecar must not rewrite its
    # status back to EDITOR_DRAFT/EDITOR_REVIEWED. The reviewer has to go through
    # the workflow again (差戻し→再申請) so the approval record and the document
    # state cannot drift apart.
    if doc.status in (DocumentStatus.APPROVED, DocumentStatus.FINALIZED):
        raise HTTPException(
            status_code=409,
            detail=(
                "Document is approved/finalized; return it through the approval "
                "workflow before importing review content"
            ),
        )
    doc.review_sidecar = sidecar_dict
    doc.review_sidecar_imported_at = datetime.now(timezone.utc)
    doc.status = determine_editor_status(sidecar_dict)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="review_sidecar.imported",
        resource_type="document",
        resource_id=doc_id,
        detail=json.dumps({"schema": sidecar_dict.get("review_schema")}),
        ip_address=None,
    )
    db.refresh(doc)
    return ReviewSidecarImportResponse(
        id=doc.id,
        status=doc.status,
        review_sidecar=doc.review_sidecar,
        review_sidecar_imported_at=doc.review_sidecar_imported_at,
    )


@router.get("/{doc_id}/review-sidecar", response_model=ReviewSidecarGetResponse)
def get_review_sidecar(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewSidecarGetResponse:
    _require_engineer(current_user)
    doc = _get_doc_or_404(doc_id, db)
    assert_document_visible(doc, current_user)
    return ReviewSidecarGetResponse(
        review_sidecar=doc.review_sidecar,
        review_sidecar_imported_at=doc.review_sidecar_imported_at,
    )


@router.post("/{doc_id}/flatten-check", response_model=FlattenCheckResponse)
def flatten_check(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlattenCheckResponse:
    _require_manager(current_user)
    doc = _get_doc_or_404(doc_id, db)
    assert_document_visible(doc, current_user)
    if doc.file_path is None:
        raise HTTPException(status_code=422, detail="Document file path is not set")
    try:
        import hashlib

        from pypdf import PdfReader

        PdfReader(doc.file_path)
        with open(doc.file_path, "rb") as f:
            raw = f.read()
        flattened_hash = hashlib.sha256(raw).hexdigest()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Flatten check failed: {str(e)}")
    doc.status = DocumentStatus.FINALIZED
    doc.is_flattened = True
    doc.flattened_verified_at = datetime.now(timezone.utc)
    doc.flattened_hash = flattened_hash
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="document.flatten.verified",
        resource_type="document",
        resource_id=doc_id,
        detail=json.dumps({"flattened_hash": flattened_hash}),
        ip_address=None,
    )
    db.refresh(doc)
    return FlattenCheckResponse(
        is_flattened=True,
        flattened_hash=flattened_hash,
        status=doc.status,
    )


@router.post("/{doc_id}/editor-events", response_model=EditorEventsResponse)
def post_editor_events(
    doc_id: str,
    events: List[EditorEventItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EditorEventsResponse:
    _require_engineer(current_user)
    doc = _get_doc_or_404(doc_id, db)
    assert_document_visible(doc, current_user)
    count = 0
    for event in events:
        create_chained_audit_log(
            db,
            user_id=current_user.id,
            action=event.event_type,
            resource_type="document",
            resource_id=doc_id,
            detail=json.dumps(event.detail) if event.detail is not None else None,
            ip_address=None,
        )
        count += 1
    return EditorEventsResponse(created=count)


@router.get("/{doc_id}/workflow-status", response_model=WorkflowStatusResponse)
def get_workflow_status(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowStatusResponse:
    _require_engineer(current_user)
    doc = _get_doc_or_404(doc_id, db)
    assert_document_visible(doc, current_user)
    workflow = doc.workflow
    if workflow:
        status_str = workflow.status
        updated_at = workflow.completed_at or workflow.created_at
        steps = [
            {
                "approver_id": s.approver_id,
                "order": s.order,
                "status": s.status,
                "comment": s.comment,
                "decided_at": s.decided_at.isoformat() if s.decided_at else None,
            }
            for s in (workflow.steps or [])
        ]
    else:
        status_str = doc.status.value
        updated_at = doc.updated_at or doc.created_at
        steps = []
    editor_sync = {
        "workflow_status": status_str,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.extra_data = {**(doc.extra_data or {}), "editor_sync": editor_sync}
    db.commit()
    db.refresh(doc)
    return WorkflowStatusResponse(
        status=status_str,
        updated_at=updated_at,
        steps=steps,
        editor_sync=editor_sync,
    )

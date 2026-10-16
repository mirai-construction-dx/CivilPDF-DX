"""Electronic delivery (電子納品) ZIP generation API.

Provides:
  GET  /projects/{project_id}/electronic-delivery/check   — readiness check
  POST /projects/{project_id}/electronic-delivery         — generate & download ZIP
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.schemas import ElectronicDeliveryCheckResponse
from auth.dependencies import get_current_user, require_manager
from database import get_db
from models.user import Project, User
from services import electronic_delivery_service
from services.access_control import assert_project_visible
from services.audit_chain_service import create_chained_audit_log

router = APIRouter(prefix="/projects", tags=["ElectronicDelivery"])


def _get_project_or_404(project_id: str, db: Session, user: User) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    return assert_project_visible(project, user)


@router.get(
    "/{project_id}/electronic-delivery/check",
    response_model=ElectronicDeliveryCheckResponse,
)
def check_delivery_readiness(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return readiness status for electronic delivery packaging."""
    project = _get_project_or_404(project_id, db, current_user)
    documents = electronic_delivery_service.deliverable_documents(db, project_id)
    result = electronic_delivery_service.check_delivery_readiness(project, documents)
    return result


@router.post("/{project_id}/electronic-delivery", status_code=status.HTTP_200_OK)
def generate_delivery_zip(
    project_id: str,
    allow_partial: bool = Query(
        False,
        description=(
            "true の場合、ファイルを読み取れない文書を除外した「読み取れる分のみ」の"
            "パッケージを生成する（既定は安全側で 409 を返す）"
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Generate and stream a MLIT-conformant electronic delivery ZIP package.

    Refuses (409) when the project has no deliverable document — an
    INDEX.XML-only package is not a deliverable, and allow_partial cannot
    produce one either.

    Also refuses (409) when a deliverable document's file cannot be read: packaging it
    would put a 0-byte PDF into an official MLIT deliverable, which is rejected
    on receipt. The failure is explicit and lists the offending documents so they
    can be restored, rather than shipping a package that looks complete.

    Pass ``allow_partial=true`` to deliberately deliver only the readable
    documents. Unreadable ones are excluded from both the ZIP and INDEX.XML — so
    the package stays internally consistent — and are reported in the readiness
    check, the audit chain and the ``X-CivilPDF-Omitted-Documents`` header.
    """
    project = _get_project_or_404(project_id, db, current_user)
    # Soft-deleted documents are excluded (see deliverable_documents).
    documents = electronic_delivery_service.deliverable_documents(db, project_id)
    if not documents:
        # A package with only INDEX.XML is not a deliverable. 409 (not 422): the
        # request is well-formed; the project's current state cannot be packaged,
        # the same class of refusal as the unreadable-file 409 below, and it
        # matches the readiness check (ready=false for 0 documents).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "納品対象の文書が1件もないため、電子納品パッケージを生成できません。"
                "文書を登録してから再実行してください。"
            ),
        )
    unreadable = electronic_delivery_service.find_unreadable_documents(documents)

    if unreadable and not allow_partial:
        sample = "、".join(f"{d['title']}（{d['reason']}）" for d in unreadable[:5])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"ファイルを読み取れない文書が {len(unreadable)} 件あるため、"
                f"電子納品パッケージを生成できません: {sample}"
                + (" ほか" if len(unreadable) > 5 else "")
                + "。ファイルを復元するか、読み取れる分のみ納品する場合は"
                " allow_partial=true を指定してください。"
            ),
        )

    omitted_ids = {d["id"] for d in unreadable}
    packaged = [doc for doc in documents if doc.id not in omitted_ids]
    if not packaged:
        # allow_partial cannot turn "nothing readable" into an empty deliverable.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"読み取れる文書が1件もないため（読み取れない文書 {len(unreadable)} 件）、"
                "allow_partial=true でも電子納品パッケージを生成できません。"
            ),
        )

    zip_bytes = electronic_delivery_service.generate_delivery_zip(project, packaged)

    # Generating an official deliverable is a compliance-relevant action, so it
    # is recorded in the tamper-evident audit chain, including any document that
    # was deliberately left out of the package.
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="electronic_delivery.generated",
        resource_type="project",
        resource_id=project_id,
        detail=json.dumps(
            {
                "document_count": len(packaged),
                "omitted_count": len(unreadable),
                "omitted_document_ids": sorted(omitted_ids),
                "allow_partial": allow_partial,
                "package_bytes": len(zip_bytes),
            }
        ),
        ip_address=None,
    )

    filename = electronic_delivery_service.package_filename(project)

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Makes a partial package visible at the protocol level, not only in
            # the log, so an automated client cannot mistake it for a complete one.
            "X-CivilPDF-Omitted-Documents": str(len(unreadable)),
        },
    )

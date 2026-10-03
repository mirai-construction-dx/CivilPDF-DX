from fastapi import APIRouter, Depends, HTTPException, status
import json
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db
from models.user import User
from models.document import Document, DocumentStatus, ApprovalWorkflow, ApprovalStep
from auth.dependencies import get_current_user
from api.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowListItem,
    ApprovalDecision,
)
from services.audit_chain_service import create_chained_audit_log
from services.access_control import (
    assert_document_visible,
    can_be_approver,
    can_write_documents,
    document_visible,
)
from services.notification_service import create_notification

router = APIRouter(prefix="/workflows", tags=["Approval Workflows"])


def _assert_not_in_trash(doc: Document) -> None:
    """C-2: documents in the trash cannot enter or progress an approval flow."""
    if doc.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document is in the trash; workflows cannot be created or "
                "decided until it is restored"
            ),
        )


@router.get("/", response_model=list[WorkflowListItem])
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflows = (
        db.query(ApprovalWorkflow).order_by(ApprovalWorkflow.created_at.desc()).all()
    )
    result = []
    for wf in workflows:
        if not document_visible(wf.document, current_user):
            continue
        all_steps = wf.steps
        pending = sum(1 for s in all_steps if s.status == "pending")
        result.append(
            WorkflowListItem(
                id=wf.id,
                document_id=wf.document_id,
                document_title=wf.document.title if wf.document else "",
                status=wf.status,
                created_at=wf.created_at,
                completed_at=wf.completed_at,
                step_count=len(all_steps),
                pending_step_count=pending,
            )
        )
    return result


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    body: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == body.document_id).first()
    assert_document_visible(doc, current_user)
    if not can_write_documents(current_user):
        # §5.2 ワークフロー作成: viewer は不可
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )
    _assert_not_in_trash(doc)

    if (
        db.query(ApprovalWorkflow)
        .filter(ApprovalWorkflow.document_id == body.document_id)
        .first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow already exists for this document",
        )

    if not body.approver_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one approver is required",
        )

    # Validate every approver before writing anything so a rejected request
    # leaves no partial workflow behind.
    for approver_id in body.approver_ids:
        approver = db.query(User).filter(User.id == approver_id).first()
        if not approver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approver {approver_id} not found",
            )
        if not can_be_approver(doc, approver):
            # §5.2 ※1 (A-3): approvers must be able to view the document and
            # viewers can never approve.
            raise HTTPException(
                status_code=422,  # Unprocessable Content
                detail=(
                    f"Approver {approver_id} cannot be assigned: approvers must "
                    "be able to view the document and must not be viewers"
                ),
            )

    workflow = ApprovalWorkflow(document_id=body.document_id, status="in_progress")
    db.add(workflow)
    db.flush()

    for i, approver_id in enumerate(body.approver_ids):
        step = ApprovalStep(
            workflow_id=workflow.id,
            approver_id=approver_id,
            order=i + 1,
            status="pending" if i > 0 else "pending",
        )
        db.add(step)

    doc.status = DocumentStatus.PENDING_REVIEW
    first_approver_id = body.approver_ids[0]
    db.commit()
    db.refresh(workflow)
    create_notification(
        db,
        user_id=first_approver_id,
        notification_type="workflow.assigned",
        title="承認依頼が届いています",
        body=f"文書「{doc.title}」の承認が依頼されました",
        resource_type="workflow",
        resource_id=workflow.id,
    )
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="workflow.created",
        resource_type="workflow",
        resource_id=workflow.id,
        detail=json.dumps({"document_id": doc.id, "approver_ids": body.approver_ids}),
        ip_address=None,
    )
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = (
        db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    )
    assert_document_visible(workflow.document if workflow else None, current_user)
    return workflow


@router.post("/{workflow_id}/steps/{step_id}/decide", response_model=WorkflowResponse)
def decide_step(
    workflow_id: str,
    step_id: str,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    step = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.id == step_id,
            ApprovalStep.workflow_id == workflow_id,
        )
        .first()
    )
    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Step not found"
        )
    # A-3 / D-3: a user who cannot view the document cannot see the workflow
    # either, so the step is reported as missing rather than forbidden.
    if not document_visible(step.workflow.document, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Step not found"
        )
    if step.approver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the approver for this step",
        )
    # A-3 / §5.2: re-check the approver conditions at decision time, so a
    # user demoted to viewer after being assigned cannot approve.
    if not can_be_approver(step.workflow.document, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role can no longer approve this step",
        )
    if step.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Step already decided"
        )
    _assert_not_in_trash(step.workflow.document)

    # Enforce approval order: all previous steps must be approved first.
    previous_steps = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.workflow_id == workflow_id,
            ApprovalStep.order < step.order,
        )
        .all()
    )
    if any(s.status != "approved" for s in previous_steps):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Previous approval steps must be approved first",
        )

    # normalize: "approve" -> "approved", "reject" -> "rejected"
    step.status = "approved" if body.decision == "approve" else "rejected"
    step.comment = body.comment
    step.decided_at = datetime.now(timezone.utc)

    workflow = step.workflow
    document = workflow.document

    if body.decision == "reject":
        workflow.status = "rejected"
        workflow.completed_at = datetime.now(timezone.utc)
        document.status = DocumentStatus.REJECTED
        create_notification(
            db,
            user_id=document.owner_id,
            notification_type="workflow.decided",
            title="承認が却下されました",
            body=f"文書「{document.title}」が却下されました",
            resource_type="workflow",
            resource_id=workflow.id,
        )
    else:
        # Check if all steps approved
        all_steps = (
            db.query(ApprovalStep).filter(ApprovalStep.workflow_id == workflow_id).all()
        )
        if all(s.status == "approved" for s in all_steps):
            workflow.status = "approved"
            workflow.completed_at = datetime.now(timezone.utc)
            document.status = DocumentStatus.APPROVED
            create_notification(
                db,
                user_id=document.owner_id,
                notification_type="workflow.decided",
                title="承認が完了しました",
                body=f"文書「{document.title}」の承認が完了しました",
                resource_type="workflow",
                resource_id=workflow.id,
            )
        else:
            # Activate next step
            next_step = (
                db.query(ApprovalStep)
                .filter(
                    ApprovalStep.workflow_id == workflow_id,
                    ApprovalStep.order == step.order + 1,
                )
                .first()
            )
            if next_step:
                next_step.status = "pending"
                create_notification(
                    db,
                    user_id=next_step.approver_id,
                    notification_type="workflow.assigned",
                    title="承認依頼が届いています",
                    body=f"文書「{document.title}」の承認が依頼されました",
                    resource_type="workflow",
                    resource_id=workflow.id,
                )

    db.commit()
    db.refresh(workflow)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="workflow.step.decided",
        resource_type="workflow",
        resource_id=workflow.id,
        detail=json.dumps(
            {
                "step_id": step.id,
                "decision": body.decision,
                "step_order": step.order,
            },
            ensure_ascii=False,
        ),
        ip_address=None,
    )
    return workflow

from fastapi import APIRouter, Depends, HTTPException, status
import json
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db
from models.user import User, UserRole
from models.document import Document, DocumentStatus, ApprovalWorkflow, ApprovalStep
from auth.dependencies import get_current_user
from api.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowListItem,
    ApprovalDecision,
)
from services.audit_chain_service import create_chained_audit_log
from services.access_control import assert_document_visible, document_visible
from services.notification_service import create_notification

router = APIRouter(prefix="/workflows", tags=["Approval Workflows"])

# WEB-WF-005: 差戻し（return）と再申請（resubmit）。
# 新しい DB enum 値を追加しないため、文書は再編集可能な "draft" に戻す
# （PostgreSQL の documentstatus enum は本番 migration が必要になるため）。
_STEP_STATUS_BY_DECISION = {
    "approve": "approved",
    "reject": "rejected",
    "return": "returned",
}
# 差戻しは新しいアクション名で記録する。approve / reject は従来どおり
# workflow.step.decided のまま（既存の監査運用・フィルタを変えないため）。
_AUDIT_ACTION_BY_DECISION = {
    "approve": "workflow.step.decided",
    "reject": "workflow.step.decided",
    "return": "workflow.step.returned",
}


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

    workflow = ApprovalWorkflow(document_id=body.document_id, status="in_progress")
    db.add(workflow)
    db.flush()

    for i, approver_id in enumerate(body.approver_ids):
        approver = db.query(User).filter(User.id == approver_id).first()
        if not approver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approver {approver_id} not found",
            )
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


@router.post("/{workflow_id}/resubmit", response_model=WorkflowResponse)
def resubmit_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """WEB-WF-005 再申請: 差戻しされた承認依頼を同じ承認フローで再開する。

    権限: 文書の起票者（owner）本人、または admin。
    状態: workflow.status == "returned" のときだけ許可する。
    """
    workflow = (
        db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    document = workflow.document
    assert_document_visible(document, current_user)

    if document.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner or an admin can resubmit",
        )
    if workflow.status != "returned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a returned workflow can be resubmitted",
        )

    steps = (
        db.query(ApprovalStep)
        .filter(ApprovalStep.workflow_id == workflow_id)
        .order_by(ApprovalStep.order)
        .all()
    )
    if not steps:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow has no approval steps",
        )

    now = datetime.now(timezone.utc)
    for step in steps:
        step.status = "pending"
        step.comment = None
        step.decided_at = None

    workflow.status = "in_progress"
    workflow.completed_at = None
    document.status = DocumentStatus.PENDING_REVIEW

    first_approver_id = steps[0].approver_id
    db.commit()
    db.refresh(workflow)
    create_notification(
        db,
        user_id=first_approver_id,
        notification_type="workflow.assigned",
        title="承認依頼が届いています",
        body=f"文書「{document.title}」の承認が再申請されました",
        resource_type="workflow",
        resource_id=workflow.id,
    )
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="workflow.resubmitted",
        resource_type="workflow",
        resource_id=workflow.id,
        detail=json.dumps(
            {
                "document_id": document.id,
                "step_count": len(steps),
                "resubmitted_at": now.isoformat(),
            },
            ensure_ascii=False,
        ),
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
    if step.approver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the approver for this step",
        )
    if step.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Step already decided"
        )

    # 差戻し後は再申請（resubmit）まで承認・却下・再差戻しを受け付けない。
    # ここを許すと、差戻しされた依頼が resubmit を経ずに承認完了へ進み、
    # 差戻しの統制が無効化される（設計 D2「差戻し後は先頭から再開する」）。
    if step.workflow.status == "returned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow was returned; resubmit it before deciding steps",
        )

    # Enforce approval order: all previous steps must be approved first.
    # 差戻し（WEB-WF-005）は承認と同じ順序規則を適用しない。順序規則は
    # 「承認済みの先行ステップがあると後続を決定できない」ためのもので、
    # 未承認の先行がある差戻し（下の return ガードで認める）は妨げない。
    previous_steps = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.workflow_id == workflow_id,
            ApprovalStep.order < step.order,
        )
        .all()
    )
    approved_previous = [s for s in previous_steps if s.status == "approved"]
    if body.decision != "return" and any(
        s.status != "approved" for s in previous_steps
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Previous approval steps must be approved first",
        )
    if body.decision == "return" and approved_previous:
        # 承認済みの上流ステップを巻き戻す仕様は未定義のため許可しない（設計 D2）。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot return a step after a previous step was approved",
        )

    # normalize: "approve" -> "approved", "reject" -> "rejected",
    #            "return" -> "returned"
    step.status = _STEP_STATUS_BY_DECISION[body.decision]
    step.comment = body.comment
    step.decided_at = datetime.now(timezone.utc)

    workflow = step.workflow
    document = workflow.document

    if body.decision == "return":
        # WEB-WF-005 差戻し: 起票者が修正して再申請できる状態にする。
        workflow.status = "returned"
        workflow.completed_at = None
        document.status = DocumentStatus.DRAFT
        reason = body.comment or "（理由の記載なし）"
        create_notification(
            db,
            user_id=document.owner_id,
            notification_type="workflow.decided",
            title="承認依頼が差戻されました",
            body=f"文書「{document.title}」が差戻されました。理由: {reason}",
            resource_type="workflow",
            resource_id=workflow.id,
        )
    elif body.decision == "reject":
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
        action=_AUDIT_ACTION_BY_DECISION[body.decision],
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

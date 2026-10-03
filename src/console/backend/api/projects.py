from fastapi import APIRouter, Depends, HTTPException, Query, status
import json
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models.user import User, Project
from auth.dependencies import get_current_user, require_manager
from api.schemas import ProjectCreate, ProjectResponse
from services.audit_chain_service import create_chained_audit_log
from services.access_control import assert_project_visible, can_access_all

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/", response_model=List[ProjectResponse])
def list_projects(
    organization_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if can_access_all(current_user):
        # §5.2 プロジェクト参照: admin / manager は全案件 (A-1)
        q = db.query(Project)
        if organization_id:
            q = q.filter(Project.organization_id == organization_id)
        return q.all()

    projects = current_user.projects
    if organization_id:
        projects = [p for p in projects if p.organization_id == organization_id]
    return projects


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    if db.query(Project).filter(Project.code == body.code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Project code already exists"
        )

    project = Project(
        name=body.name,
        code=body.code,
        description=body.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        detail=json.dumps({"name": body.name, "code": body.code}),
        ip_address=None,
    )
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    return assert_project_visible(project, current_user)


@router.post("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if user not in project.members:
        project.members.append(user)
        db.commit()
        create_chained_audit_log(
            db,
            user_id=current_user.id,
            action="project.member.added",
            resource_type="project",
            resource_id=project.id,
            detail=json.dumps({"user_id": user_id}),
            ip_address=None,
        )


@router.delete(
    "/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user and user in project.members:
        project.members.remove(user)
        db.commit()
        create_chained_audit_log(
            db,
            user_id=current_user.id,
            action="project.member.removed",
            resource_type="project",
            resource_id=project.id,
            detail=json.dumps({"user_id": user_id}),
            ip_address=None,
        )

"""Authorization helpers shared across API routers.

Rule summary (single source of truth):
- ADMIN / MANAGER: full read access to all documents, projects and workflows.
- ENGINEER / VIEWER: only documents they own or that belong to projects they
  are members of. Workflows/editor/revision data are gated by the underlying
  document visibility.
- Unauthorized resources are reported as 404 (not 403) to avoid leaking the
  existence of documents, projects or workflows to users outside their scope.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models.document import Document
from models.user import Project, User, UserRole


def can_access_all(user: User) -> bool:
    """Admin and manager can access every document/project in the system."""
    return user.role in (UserRole.ADMIN, UserRole.MANAGER)


def user_project_ids(user: User) -> set[str]:
    """Return the set of project ids the user is a member of."""
    return {p.id for p in user.projects}


def document_visible(doc: Optional[Document], user: User) -> bool:
    """Return True when the user may read the document (or it does not exist)."""
    if doc is None:
        return True  # caller decides 404 semantics
    if can_access_all(user):
        return True
    if doc.owner_id == user.id:
        return True
    return doc.project_id in user_project_ids(user)


def project_visible(project: Optional[Project], user: User) -> bool:
    """Return True when the user may read the project (or it does not exist)."""
    if project is None:
        return True
    if can_access_all(user):
        return True
    return project.id in user_project_ids(user)


def visible_documents_query(db: Session, user: User):
    """Return a query restricted to documents visible to the user."""
    q = db.query(Document)
    if can_access_all(user):
        return q
    member_ids = user_project_ids(user)
    return q.filter(
        (Document.owner_id == user.id) | (Document.project_id.in_(member_ids))
    )


def assert_document_visible(doc: Optional[Document], user: User) -> Document:
    """Raise 404 when the document is missing or not visible to the user."""
    from fastapi import HTTPException, status

    if doc is None or not document_visible(doc, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return doc


def assert_project_visible(project: Optional[Project], user: User) -> Project:
    """Raise 404 when the project is missing or not visible to the user."""
    from fastapi import HTTPException, status

    if project is None or not project_visible(project, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


def can_write_documents(user: User) -> bool:
    """§5.2: 文書アップロード・ワークフロー作成は viewer 以外に許可する."""
    return user.role in (UserRole.ADMIN, UserRole.MANAGER, UserRole.ENGINEER)


def can_delete_document(doc: Document, user: User) -> bool:
    """§5.2 文書削除 (※3 ごみ箱からの復元も同じ権限).

    admin は全文書、manager / engineer は自分の文書のみ、viewer は不可。
    文書の可視性 (404 秘匿) は呼び出し側で先に確認すること。
    """
    if user.role == UserRole.ADMIN:
        return True
    if user.role in (UserRole.MANAGER, UserRole.ENGINEER):
        return doc.owner_id == user.id
    return False


def can_be_approver(doc: Document, user: User) -> bool:
    """§5.2 ※1: 承認者は文書を閲覧できるユーザーに限り、viewer は不可 (A-3).

    admin は承認者に指定できる (2026-10-03 決定)。
    """
    if user.role == UserRole.VIEWER:
        return False
    return document_visible(doc, user)


def project_ids_for_filter(user: User) -> Optional[Iterable[str]]:
    """Return project ids used for SQL filtering, or None for full access."""
    if can_access_all(user):
        return None
    return user_project_ids(user)

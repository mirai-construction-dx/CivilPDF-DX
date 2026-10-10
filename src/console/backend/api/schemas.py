from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime
from models.organization import OrgType
from models.user import UserRole, UserStatus
from models.document import DocumentStatus, DocumentType


def _password_classes(password: str) -> int:
    """Count character classes present in a password (lower/upper/digit/symbol)."""
    classes = 0
    if any(c.islower() for c in password):
        classes += 1
    if any(c.isupper() for c in password):
        classes += 1
    if any(c.isdigit() for c in password):
        classes += 1
    if any(not c.isalnum() for c in password):
        classes += 1
    return classes


# ─── Organization ───
class OrganizationCreate(BaseModel):
    name: str
    code: str
    org_type: OrgType = OrgType.SITE_OFFICE
    parent_id: Optional[str] = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    code: str
    org_type: OrgType
    parent_id: Optional[str] = None
    path: str
    is_active: bool
    created_at: datetime
    children: List["OrganizationResponse"] = []

    model_config = {"from_attributes": True}


OrganizationResponse.model_rebuild()


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Auth ───
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


# ─── User ───
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    password: str
    role: UserRole = UserRole.ENGINEER

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8 or _password_classes(v) < 2:
            raise ValueError(
                "Password must be at least 8 characters and contain at least "
                "two of: lowercase, uppercase, digits, symbols"
            )
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    unlock: Optional[bool] = None


class AdminPasswordResetRequest(BaseModel):
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Project ───
class ProjectCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Document ───
class DocumentResponse(BaseModel):
    id: str
    title: str
    document_type: DocumentType
    status: DocumentStatus
    filename: str
    file_size: int
    page_count: Optional[int]
    is_pdfa: bool
    pdfa_version: Optional[str] = None
    tags: List[str] = []
    project_id: str
    owner_id: str
    created_at: datetime
    updated_at: Optional[datetime]
    # Timestamp fields (電子帳簿保存法)
    timestamp_verified_at: Optional[datetime] = None
    timestamp_hash: Optional[str] = None
    timestamp_tsa_url: Optional[str] = None
    # Retention (電子帳簿保存法/公共工事品確法)
    retention_expires_at: Optional[datetime] = None
    is_archived: bool = False
    archived_at: Optional[datetime] = None
    deletion_requested_at: Optional[datetime] = None
    # ISO 19650 metadata
    iso19650_originator: Optional[str] = None
    iso19650_functional_breakdown: Optional[str] = None
    iso19650_form: Optional[str] = None
    iso19650_discipline: Optional[str] = None
    iso19650_number: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    document_type: Optional[DocumentType] = None
    tags: Optional[List[str]] = None


# ─── Timestamp ───
class TimestampResponse(BaseModel):
    document_id: str
    file_hash: str
    token_type: str  # "rfc3161" | "local_hmac"
    tsa_url: str
    verified_at: datetime
    token_present: bool

    model_config = {"from_attributes": True}


class TimestampVerifyResponse(BaseModel):
    document_id: str
    valid: bool
    message: str
    file_hash: Optional[str] = None
    verified_at: Optional[datetime] = None


# ─── Workflow ───
class WorkflowCreate(BaseModel):
    document_id: str
    approver_ids: List[str]


class ApprovalStepResponse(BaseModel):
    id: str
    order: int
    approver_id: str
    status: str
    comment: Optional[str]
    decided_at: Optional[datetime]
    approver: UserResponse

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: str
    document_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    steps: List[ApprovalStepResponse]

    model_config = {"from_attributes": True}


class WorkflowListItem(BaseModel):
    id: str
    document_id: str
    document_title: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    step_count: int
    pending_step_count: int

    model_config = {"from_attributes": False}


class ApprovalDecision(BaseModel):
    # "approve" ... ステップ承認
    # "reject"  ... 却下（ワークフロー終端。従来どおり）
    # "return"  ... 差戻し（WEB-WF-005。起票者が修正して再申請できる。終端しない）
    decision: str
    comment: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in ("approve", "reject", "return"):
            raise ValueError("decision must be 'approve', 'reject' or 'return'")
        return v


# ─── Audit Log ───
class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    detail: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    sequence_number: Optional[int] = None
    record_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    user: Optional[UserResponse] = None

    model_config = {"from_attributes": True}


# ─── Electronic Delivery ───
class NonPdfaDocumentInfo(BaseModel):
    id: str
    title: str
    filename: str


class UnreadableDocumentInfo(BaseModel):
    id: str
    title: str
    filename: str
    reason: str


class ElectronicDeliveryCheckResponse(BaseModel):
    ready: bool
    document_count: int
    pdfa_compliant_count: int
    non_pdfa_documents: List[NonPdfaDocumentInfo]
    # Documents whose stored file cannot be read: they would be packaged as
    # 0-byte PDFs, so they are reported separately and make ready=false.
    unreadable_documents: List[UnreadableDocumentInfo] = []
    warnings: List[str]


# ─── Pagination ───
class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    per_page: int
    pages: int


# ─── Editor Integration ───
class ReviewSidecarPayload(BaseModel):
    # Matches the CivilPDF-Editor `civilpdf.review/v1` contract (lib/review/schema.ts).
    # A mode="before" validator folds the Editor keys (schema/savedAt) and the
    # legacy keys (version/exported_at) onto canonical snake_case fields so the
    # non-destructive review round-trip is loss-free and backward compatible.
    # extra="allow" preserves any forward-compatible keys the Editor may add.
    review_schema: Optional[str] = None
    generator: Optional[str] = None
    saved_at: Optional[str] = None
    stamps: List[Any] = []
    annotations: List[Any] = []
    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _fold_editor_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            schema_val = data.pop("schema", None)
            version_val = data.pop("version", None)
            saved_val = data.pop("savedAt", None)
            exported_val = data.pop("exported_at", None)
            data.setdefault("review_schema", schema_val or version_val)
            data.setdefault("saved_at", saved_val or exported_val)
        return data


class ReviewSidecarImportResponse(BaseModel):
    id: str
    status: DocumentStatus
    review_sidecar: Optional[Any] = None
    review_sidecar_imported_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ReviewSidecarGetResponse(BaseModel):
    review_sidecar: Optional[Any] = None
    review_sidecar_imported_at: Optional[datetime] = None


class FlattenCheckResponse(BaseModel):
    is_flattened: bool
    flattened_hash: Optional[str] = None
    status: DocumentStatus


class EditorEventItem(BaseModel):
    event_type: str
    detail: Optional[Any] = None
    occurred_at: datetime

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        allowed = {"stamp.placed", "stamp.removed", "annotation.added", "comment.added"}
        if v not in allowed:
            raise ValueError(f"event_type must be one of: {sorted(allowed)}")
        return v


class EditorEventsResponse(BaseModel):
    created: int


class WorkflowStatusResponse(BaseModel):
    status: str
    updated_at: Optional[datetime] = None
    steps: List[Any] = []
    editor_sync: Optional[Any] = None


# ─── Revisions ───
class RevisionResponse(BaseModel):
    id: str
    document_id: str
    version_number: int
    filename: str
    file_size: int
    revision: Optional[str] = None
    revision_note: Optional[str] = None
    is_from_editor: bool = False
    editor_session_id: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}

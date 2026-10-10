from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from database import Base


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    # Editor integration states
    EDITOR_DRAFT = "editor_draft"
    EDITOR_REVIEWED = "editor_reviewed"
    FINALIZED = "finalized"


class DocumentType(str, enum.Enum):
    DRAWING = "drawing"  # 図面
    PHOTO = "photo"  # 写真台帳
    INSPECTION = "inspection"  # 検査記録
    SAFETY = "safety"  # 安全書類
    CONTRACT = "contract"  # 契約書
    REPORT = "report"  # 報告書
    CORRECTION = "correction"  # 是正指示書
    OTHER = "other"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    document_type = Column(Enum(DocumentType), default=DocumentType.OTHER)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.DRAFT, index=True)

    # File info
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)  # nullable for GDPR physical deletion
    file_size = Column(BigInteger, nullable=False)
    page_count = Column(Integer, nullable=True)
    mime_type = Column(String, default="application/pdf")

    # PDF/A compliance
    is_pdfa = Column(Boolean, default=False)
    pdfa_version = Column(String, nullable=True)  # "PDF/A-1b", "PDF/A-2b", etc.
    pdfa_validation_result = Column(JSON, nullable=True)  # veraPDF detailed result

    # RFC 3161 timestamp (電子帳簿保存法・e-文書法)
    timestamp_verified_at = Column(DateTime(timezone=True), nullable=True)
    timestamp_hash = Column(String, nullable=True)  # SHA-256 of file at timestamp
    timestamp_token = Column(Text, nullable=True)  # base64-encoded TSA token
    timestamp_tsa_url = Column(String, nullable=True)  # TSA endpoint used

    # Retention policy (電子帳簿保存法・公共工事品確法)
    retention_policy_id = Column(
        String, ForeignKey("retention_policies.id"), nullable=True
    )
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    is_archived = Column(Boolean, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)  # GDPR削除権

    # ISO 19650 metadata (BIM情報管理)
    iso19650_originator = Column(String, nullable=True)  # 作成者コード (例: ABC)
    iso19650_functional_breakdown = Column(String, nullable=True)  # 機能分類 (例: 00)
    iso19650_form = Column(String, nullable=True)  # 情報形式 (例: DR=図面)
    iso19650_discipline = Column(String, nullable=True)  # 分野コード (例: ST=構造)
    iso19650_number = Column(String, nullable=True)  # 連番 (例: 0001)

    # OCR
    ocr_text = Column(Text, nullable=True)
    ocr_processed = Column(Boolean, default=False)

    # Custom metadata (avoiding SQLAlchemy reserved name)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)

    # Editor integration: ReviewSidecar (feature #1)
    review_sidecar = Column(JSON, nullable=True)
    review_sidecar_imported_at = Column(DateTime(timezone=True), nullable=True)

    # Revision management (feature #2)
    revision = Column(String, nullable=True)
    revision_note = Column(String, nullable=True)

    # Flatten gate (feature #3)
    is_flattened = Column(Boolean, default=False)
    flattened_verified_at = Column(DateTime(timezone=True), nullable=True)
    flattened_hash = Column(String, nullable=True)

    # Relations (indexed: list_documents/export_documents filter on all three)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    project = relationship("Project", back_populates="documents")
    owner = relationship("User", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")
    workflow = relationship(
        "ApprovalWorkflow", back_populates="document", uselist=False
    )
    retention_policy = relationship(
        "RetentionPolicy", foreign_keys=[retention_policy_id]
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    # Version numbers are allocated with max()+1; without a constraint two
    # concurrent uploads can both pick the same number and the audit trail then
    # carries two different revisions under one version.
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_number"
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)  # nullable for GDPR physical deletion
    file_size = Column(BigInteger, nullable=False)
    change_note = Column(String, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Editor integration (feature #2)
    revision = Column(String, nullable=True)
    revision_note = Column(String, nullable=True)
    is_from_editor = Column(Boolean, default=False)
    editor_session_id = Column(String, nullable=True)

    document = relationship("Document", back_populates="versions")


class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String, ForeignKey("documents.id"), unique=True, nullable=False
    )
    status = Column(
        String, default="pending"
    )  # pending, in_progress, approved, rejected, returned
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="workflow")
    steps = relationship(
        "ApprovalStep", back_populates="workflow", order_by="ApprovalStep.order"
    )


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    job_type = Column(String, nullable=False)  # pdf_to_pdfa, flatten, etc.
    status = Column(String, default="pending")  # pending|running|done|failed
    output_path = Column(String, nullable=True)
    output_size = Column(BigInteger, nullable=True)
    error_message = Column(Text, nullable=True)
    requested_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document")
    requester = relationship("User")


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("approval_workflows.id"), nullable=False)
    approver_id = Column(String, ForeignKey("users.id"), nullable=False)
    order = Column(Integer, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected, returned
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    workflow = relationship("ApprovalWorkflow", back_populates="steps")
    approver = relationship("User", back_populates="approvals")

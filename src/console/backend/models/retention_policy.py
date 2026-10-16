"""Retention policy model — stores legal document retention rules per document type."""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.sql import func
import uuid
import enum

from database import Base


class RetentionCategory(str, enum.Enum):
    """Legal retention categories mapped to Japanese regulations."""

    TAX_RECORDS = "tax_records"  # 国税関係書類 (電子帳簿保存法) — 7年
    CONSTRUCTION_GENERAL = "construction_general"  # 建設業法一般書類 — 5年
    CONSTRUCTION_MAJOR = "construction_major"  # 土木一式・建築一式 — 15年
    PUBLIC_WORKS = "public_works"  # 公共工事品確法 — 10年
    ELECTRONIC_SUBMISSION = "electronic_submission"  # 電子納品 — 永続
    PERSONAL_DATA = "personal_data"  # 個人情報保護法 — 目的達成後速やかに削除
    SAFETY = "safety"  # 安全書類 — 3年
    CONTRACT = "contract"  # 契約書類 — 10年
    CUSTOM = "custom"  # カスタム定義


class RetentionPolicy(Base):
    """Document retention policy by document type.

    Implements requirements from:
    - 電子帳簿保存法 (Electronic Bookkeeping Act)
    - 建設業法 (Construction Business Act)
    - 公共工事品確法 (Public Works Quality Assurance Act)
    - 国交省電子納品要領 (MLIT Electronic Submission Guidelines)
    """

    __tablename__ = "retention_policies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False, default=RetentionCategory.CUSTOM.value)
    document_type = Column(String, nullable=True)  # maps to DocumentType enum value

    # Retention period: -1 = permanent (永続), 0 = destroy immediately after purpose
    retention_years = Column(Integer, nullable=False, default=7)
    is_permanent = Column(Boolean, default=False)

    # Auto-archive expired documents (set ARCHIVED status, keep file)
    auto_archive = Column(Boolean, default=True)
    # Auto-delete expired documents (physical file removal after archive_grace_days)
    auto_delete = Column(Boolean, default=False)
    archive_grace_days = Column(Integer, default=30)

    legal_basis = Column(Text, nullable=True)  # 法的根拠テキスト
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Default policies seeded at migration time
DEFAULT_POLICIES = [
    {
        "name": "国税関係書類（電子帳簿保存法）",
        "category": RetentionCategory.TAX_RECORDS.value,
        "document_type": "contract",
        # 2026-10-03 decision B-2: contracts are kept 7 years, counted from the
        # upload date (requirements.md §3.2.4).
        "retention_years": 7,
        "is_permanent": False,
        "auto_archive": True,
        "auto_delete": False,
        "legal_basis": "社内決定 B-2（2026-10-03・契約書は7年、アップロード日起算）",
    },
    {
        "name": "公共工事書類（品確法）",
        "category": RetentionCategory.PUBLIC_WORKS.value,
        "document_type": "inspection",
        "retention_years": 10,
        "is_permanent": False,
        "auto_archive": True,
        "auto_delete": False,
        "legal_basis": "公共工事の品質確保の促進に関する法律 第17条",
    },
    {
        "name": "電子納品書類（国交省）",
        "category": RetentionCategory.ELECTRONIC_SUBMISSION.value,
        "document_type": "drawing",
        # 2026-10-03 decision B-2: drawings are kept 10 years, counted from the
        # upload date (requirements.md §3.2.4). Previously permanent.
        "retention_years": 10,
        "is_permanent": False,
        "auto_archive": False,
        "auto_delete": False,
        "legal_basis": "社内決定 B-2（2026-10-03・図面は10年、アップロード日起算）",
    },
    {
        "name": "建設業法主要書類",
        "category": RetentionCategory.CONSTRUCTION_MAJOR.value,
        "document_type": "report",
        "retention_years": 15,
        "is_permanent": False,
        "auto_archive": True,
        "auto_delete": False,
        "legal_basis": "建設業法 第40条の3、建設工事の請負契約に関する規則",
    },
    {
        "name": "安全書類（労安法）",
        "category": RetentionCategory.SAFETY.value,
        "document_type": "safety",
        "retention_years": 3,
        "is_permanent": False,
        "auto_archive": True,
        "auto_delete": False,
        "legal_basis": "労働安全衛生法 第59条、同規則 第38条",
    },
    {
        "name": "個人情報含む書類（個人情報保護法）",
        "category": RetentionCategory.PERSONAL_DATA.value,
        "document_type": "other",
        "retention_years": 0,
        "is_permanent": False,
        "auto_archive": False,
        "auto_delete": True,
        "archive_grace_days": 90,
        "legal_basis": "個人情報の保護に関する法律 第19条（不必要な個人情報の消去）",
    },
]

"""PostgreSQL enum parity between Alembic migrations and the ORM models.

``Column(Enum(PyEnum))`` persists the enum member **names** unless
``values_callable`` is supplied. PostgreSQL enforces enum labels, while SQLite
stores ``Enum`` columns as plain VARCHAR and silently accepts any string.

That asymmetry let a real defect reach production undetected: migration
``f2b3c4d5e6f7`` added the editor-integration document statuses using their
lowercase *values* (``editor_draft`` …) while the ORM emits the uppercase
*names* (``EDITOR_DRAFT`` …), so every write of those statuses on PostgreSQL
failed with ``invalid input value for enum documentstatus``. The whole CI suite
ran on SQLite and stayed green.

This test only has something to verify on PostgreSQL, so it is skipped
elsewhere; CI runs it in the "Backend Migrations (fresh DB)" job right after
``alembic upgrade head`` has built the schema on a real PostgreSQL service.
"""

import sys

import pytest
from sqlalchemy import Enum as SAEnum
from sqlalchemy import text

from database import Base, engine
import models  # noqa: F401  (populates Base.metadata)


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="SQLite stores Enum columns as VARCHAR; enum labels only exist on PostgreSQL",
)


def _postgres_enum_labels() -> dict[str, set[str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.typname, e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON e.enumtypid = t.oid"
            )
        ).fetchall()
    labels: dict[str, set[str]] = {}
    for typname, label in rows:
        labels.setdefault(typname, set()).add(label)
    return labels


def _enum_columns():
    for table, tbl in Base.metadata.tables.items():
        for col in tbl.columns:
            if isinstance(col.type, SAEnum) and col.type.enums:
                yield table, col


def test_model_enum_members_exist_as_postgresql_labels():
    """Every name the ORM can emit must be a label of the PostgreSQL enum."""
    labels = _postgres_enum_labels()

    problems: dict[str, object] = {}
    for table, col in _enum_columns():
        typname = col.type.name or f"{table}_{col.name}"
        known = labels.get(typname)
        if known is None:
            problems[f"{table}.{col.name}"] = f"PostgreSQL enum {typname} not found"
            continue
        missing = sorted(set(col.type.enums) - known)
        if missing:
            problems[f"{table}.{col.name}"] = missing

    assert not problems, (
        "PostgreSQL enum labels are missing names the ORM emits "
        f"(writes will fail with InvalidTextRepresentation): {problems}"
    )


def test_enum_parity_check_covers_every_enum_column():
    """Guard the guard: the parity test must not silently check zero columns."""
    columns = list(_enum_columns())
    assert (
        columns
    ), "no Enum columns discovered — the parity check is not testing anything"

    labels = _postgres_enum_labels()
    assert labels, "no PostgreSQL enum labels found — is the schema migrated?"


def test_document_status_editor_labels_present():
    """Pin the specific regression that motivated this module."""
    labels = _postgres_enum_labels()
    for label in ("EDITOR_DRAFT", "EDITOR_REVIEWED", "FINALIZED"):
        assert label in labels.get("documentstatus", set()), (
            f"documentstatus is missing {label}; ORM writes of "
            "DocumentStatus.{label} would fail on PostgreSQL"
        )


def test_parity_check_rejects_the_pre_fix_label_set(monkeypatch):
    """Negative test: the guard must fail on the schema that caused the incident.

    Replays the exact pre-``n4o5p6q7r8s9`` label set (migration
    ``f2b3c4d5e6f7`` added lowercase values while the ORM emits uppercase
    names). If this passes, the parity check above is not actually sensitive
    to the regression it exists to catch.
    """
    pre_fix = {
        "documentstatus": {
            "DRAFT",
            "PENDING_REVIEW",
            "APPROVED",
            "REJECTED",
            "ARCHIVED",
            "editor_draft",
            "editor_reviewed",
            "finalized",
        }
    }
    monkeypatch.setattr(sys.modules[__name__], "_postgres_enum_labels", lambda: pre_fix)

    with pytest.raises(AssertionError) as excinfo:
        test_model_enum_members_exist_as_postgresql_labels()

    assert "documents.status" in str(excinfo.value)
    for label in ("EDITOR_DRAFT", "EDITOR_REVIEWED", "FINALIZED"):
        assert label in str(excinfo.value)

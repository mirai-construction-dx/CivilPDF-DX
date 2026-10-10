"""Make (document_id, version_number) unique on document_versions.

Version numbers are allocated with ``max(version_number) + 1`` in
``api/revisions.py``. Without a database constraint two concurrent uploads can
read the same maximum and insert two different revisions under the same
version number, so the audit trail records one revision number twice and the
"which revision is this" question has no answer.

Existing duplicates (if any) are resolved before the constraint is created by
keeping the earliest row per ``(document_id, version_number)`` and renumbering
the later ones above the current maximum, preserving their relative order.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "uq_document_versions_number"


def upgrade() -> None:
    conn = op.get_bind()

    # Renumber duplicates above the current maximum, oldest first.
    duplicates = conn.execute(
        sa.text(
            """
            SELECT document_id, version_number, COUNT(*) AS n
            FROM document_versions
            GROUP BY document_id, version_number
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    for document_id, version_number, _count in duplicates:
        rows = conn.execute(
            sa.text(
                """
                SELECT id FROM document_versions
                WHERE document_id = :doc AND version_number = :ver
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"doc": document_id, "ver": version_number},
        ).fetchall()
        max_version = (
            conn.execute(
                sa.text(
                    "SELECT MAX(version_number) FROM document_versions "
                    "WHERE document_id = :doc"
                ),
                {"doc": document_id},
            ).scalar()
            or 0
        )
        for (row_id,) in rows[1:]:
            max_version += 1
            conn.execute(
                sa.text(
                    "UPDATE document_versions SET version_number = :ver WHERE id = :id"
                ),
                {"ver": max_version, "id": row_id},
            )

    with op.batch_alter_table("document_versions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            _CONSTRAINT, ["document_id", "version_number"]
        )


def downgrade() -> None:
    with op.batch_alter_table("document_versions", schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="unique")

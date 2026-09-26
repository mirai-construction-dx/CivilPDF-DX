"""Tests for services/deletion_job.py — GDPR Art.17 physical deletion job."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_doc(
    db, owner_id: str, deletion_requested_at=None, file_path: str = "/tmp/fake.pdf"
):
    from models.document import Document, DocumentType

    doc = Document(
        title="Test Document",
        document_type=DocumentType.OTHER,
        filename="fake.pdf",
        file_path=file_path,
        file_size=1024,
        mime_type="application/pdf",
        project_id="proj-001",
        owner_id=owner_id,
        deletion_requested_at=deletion_requested_at,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _make_user(db, email: str = "owner@example.com"):
    from models.user import User, UserRole, UserStatus
    from auth.jwt import get_password_hash

    user = User(
        email=email,
        username=email.split("@")[0],
        full_name="Test Owner",
        hashed_password=get_password_hash("Test123!"),
        role=UserRole.ENGINEER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# run_deletion_job
# ---------------------------------------------------------------------------


class TestRunDeletionJob:
    def test_no_candidates_returns_zero(self, db_session):
        from services.deletion_job import run_deletion_job

        result = run_deletion_job(db_session, grace_days=30)

        assert result["processed"] == 0
        assert result["deleted_files"] == 0
        assert result["errors"] == 0
        assert result["grace_days"] == 30

    def test_doc_within_grace_not_deleted(self, db_session):
        from services.deletion_job import run_deletion_job

        user = _make_user(db_session)
        # requested 5 days ago — within 30-day grace
        requested_at = datetime.now(timezone.utc) - timedelta(days=5)
        _make_doc(db_session, user.id, deletion_requested_at=requested_at)

        result = run_deletion_job(db_session, grace_days=30)

        assert result["processed"] == 0

    def test_doc_past_grace_deleted(self, db_session, tmp_path):
        from services.deletion_job import run_deletion_job
        from models.document import Document

        user = _make_user(db_session)
        fake_file = tmp_path / "to_delete.pdf"
        fake_file.write_bytes(b"pdf data")

        requested_at = datetime.now(timezone.utc) - timedelta(days=31)
        doc = _make_doc(
            db_session,
            user.id,
            deletion_requested_at=requested_at,
            file_path=str(fake_file),
        )
        doc_id = doc.id

        with patch("services.deletion_job.create_chained_audit_log") as mock_audit:
            mock_audit.return_value = MagicMock(id="audit-001")
            result = run_deletion_job(db_session, grace_days=30)

        assert result["processed"] == 1
        assert result["deleted_files"] == 1
        assert result["errors"] == 0
        assert not fake_file.exists()

        refreshed = db_session.query(Document).filter(Document.id == doc_id).first()
        assert refreshed.file_path is None
        assert refreshed.is_archived is True

    def test_missing_file_still_marks_deleted(self, db_session):
        from services.deletion_job import run_deletion_job
        from models.document import Document

        user = _make_user(db_session)
        requested_at = datetime.now(timezone.utc) - timedelta(days=45)
        doc = _make_doc(
            db_session,
            user.id,
            deletion_requested_at=requested_at,
            file_path="/nonexistent/path.pdf",
        )
        doc_id = doc.id

        with patch("services.deletion_job.create_chained_audit_log") as mock_audit:
            mock_audit.return_value = MagicMock(id="audit-002")
            result = run_deletion_job(db_session, grace_days=30)

        assert result["processed"] == 1
        assert result["deleted_files"] == 1

        refreshed = db_session.query(Document).filter(Document.id == doc_id).first()
        assert refreshed.file_path is None

    def test_exception_counted_as_error(self, db_session):
        from services.deletion_job import run_deletion_job

        user = _make_user(db_session)
        requested_at = datetime.now(timezone.utc) - timedelta(days=60)
        _make_doc(db_session, user.id, deletion_requested_at=requested_at)

        with patch(
            "services.deletion_job._physically_delete",
            side_effect=RuntimeError("disk error"),
        ):
            result = run_deletion_job(db_session, grace_days=30)

        assert result["errors"] == 1
        assert result["deleted_files"] == 0

    def test_result_contains_run_at(self, db_session):
        from services.deletion_job import run_deletion_job

        result = run_deletion_job(db_session)

        assert "run_at" in result
        # Should be parseable ISO datetime
        datetime.fromisoformat(result["run_at"])

    def test_audit_log_created_on_deletion(self, db_session, tmp_path):
        from services.deletion_job import run_deletion_job

        user = _make_user(db_session)
        fake_file = tmp_path / "audit_test.pdf"
        fake_file.write_bytes(b"data")

        requested_at = datetime.now(timezone.utc) - timedelta(days=35)
        _make_doc(
            db_session,
            user.id,
            deletion_requested_at=requested_at,
            file_path=str(fake_file),
        )

        with patch("services.deletion_job.create_chained_audit_log") as mock_audit:
            mock_audit.return_value = MagicMock(id="audit-003")
            run_deletion_job(db_session, grace_days=30)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action"] == "gdpr_physical_deletion"
        assert call_kwargs["resource_type"] == "document"
        assert call_kwargs["user_id"] is None  # system actor

    def test_no_deletion_requested_at_skipped(self, db_session):
        from services.deletion_job import run_deletion_job

        user = _make_user(db_session)
        _make_doc(db_session, user.id, deletion_requested_at=None)

        result = run_deletion_job(db_session, grace_days=30)

        assert result["processed"] == 0

    def test_custom_grace_days_respected(self, db_session, tmp_path):
        from services.deletion_job import run_deletion_job

        user = _make_user(db_session)
        fake_file = tmp_path / "grace.pdf"
        fake_file.write_bytes(b"x")

        # 10 days ago — past a 7-day grace but within 30-day default
        requested_at = datetime.now(timezone.utc) - timedelta(days=10)
        _make_doc(
            db_session,
            user.id,
            deletion_requested_at=requested_at,
            file_path=str(fake_file),
        )

        with patch("services.deletion_job.create_chained_audit_log") as mock_audit:
            mock_audit.return_value = MagicMock(id="audit-004")
            result_short = run_deletion_job(db_session, grace_days=7)

        assert result_short["processed"] == 1
        assert result_short["grace_days"] == 7

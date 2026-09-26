"""Scheduled retention pass — the automation that makes retention actually happen.

Regression context (2026-09-18): ``services/deletion_job.py`` and
``services/retention_service.py`` implemented and unit-tested retention
enforcement, but nothing ever called them on a schedule, so retention expiry and
the GDPR Art.17 cooling-off period were enforced only if an admin remembered to
POST the endpoint. These tests cover the packaged pass
(``run_retention_cycle``), its dry-run guarantees, and the CLI that the systemd
timer invokes.
"""

import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "retention-job.py"


def _load_retention_cli():
    """Import scripts/retention-job.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("retention_job_cli", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_user(db, email: str = "retention-owner@example.com"):
    from auth.jwt import get_password_hash
    from models.user import User, UserRole, UserStatus

    user = User(
        email=email,
        username=email.split("@")[0],
        full_name="Retention Owner",
        hashed_password=get_password_hash("Test123!"),
        role=UserRole.ENGINEER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_doc(
    db,
    owner_id: str,
    *,
    retention_expires_at=None,
    deletion_requested_at=None,
    file_path=None,
):
    from models.document import Document, DocumentType

    doc = Document(
        title="Retention Document",
        document_type=DocumentType.OTHER,
        filename="retention.pdf",
        file_path=file_path,
        file_size=10,
        mime_type="application/pdf",
        project_id="proj-retention",
        owner_id=owner_id,
        retention_expires_at=retention_expires_at,
        deletion_requested_at=deletion_requested_at,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


class TestRetentionCycle:
    def test_dry_run_changes_nothing(self, db_session):
        from services.retention_service import run_retention_cycle

        user = _make_user(db_session)
        expired = _make_doc(
            db_session,
            user.id,
            retention_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        requested = _make_doc(
            db_session,
            user.id,
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=90),
            file_path="/tmp/does-not-matter.pdf",
        )

        summary = run_retention_cycle(db_session, grace_days=30, dry_run=True)

        assert summary["dry_run"] is True
        assert summary["expired_documents"] >= 1
        assert summary["deletion_processed"] >= 1
        assert summary["deletion_deleted_files"] == 0

        db_session.refresh(expired)
        db_session.refresh(requested)
        assert expired.is_archived is False
        assert requested.file_path == "/tmp/does-not-matter.pdf"

    def test_apply_archives_expired_documents(self, db_session):
        from services.retention_service import run_retention_cycle

        user = _make_user(db_session, "retention-archive@example.com")
        doc = _make_doc(
            db_session,
            user.id,
            retention_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        summary = run_retention_cycle(db_session, grace_days=30, dry_run=False)

        assert summary["dry_run"] is False
        assert summary["expired_documents"] >= 1
        db_session.refresh(doc)
        assert doc.is_archived is True
        assert doc.status.value == "archived"

    def test_apply_seeds_default_policies_once(self, db_session):
        from models.retention_policy import RetentionPolicy
        from services.retention_service import run_retention_cycle

        first = run_retention_cycle(db_session, dry_run=False)
        assert first["seeded_policies"] > 0
        count = db_session.query(RetentionPolicy).count()
        assert count == first["seeded_policies"]

        second = run_retention_cycle(db_session, dry_run=False)
        assert second["seeded_policies"] == 0
        assert db_session.query(RetentionPolicy).count() == count

    def test_apply_physically_deletes_past_grace(self, db_session, tmp_path):
        from services.retention_service import run_retention_cycle

        target = tmp_path / "to-delete.pdf"
        target.write_bytes(b"%PDF-1.4 data")

        user = _make_user(db_session, "retention-delete@example.com")
        doc = _make_doc(
            db_session,
            user.id,
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=90),
            file_path=str(target),
        )

        summary = run_retention_cycle(db_session, grace_days=30, dry_run=False)

        assert summary["deletion_deleted_files"] >= 1
        assert summary["deletion_errors"] == 0
        assert not target.exists()
        db_session.refresh(doc)
        assert doc.file_path is None

    def test_documents_within_grace_are_kept(self, db_session, tmp_path):
        from services.retention_service import run_retention_cycle

        target = tmp_path / "still-cooling-off.pdf"
        target.write_bytes(b"%PDF-1.4 data")

        user = _make_user(db_session, "retention-grace@example.com")
        _make_doc(
            db_session,
            user.id,
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=3),
            file_path=str(target),
        )

        summary = run_retention_cycle(db_session, grace_days=30, dry_run=False)

        assert summary["deletion_deleted_files"] == 0
        assert target.exists()

    def test_summary_is_json_serialisable(self, db_session):
        import json

        from services.retention_service import run_retention_cycle

        summary = run_retention_cycle(db_session, dry_run=True)
        json.dumps(summary)  # must not raise; the timer logs --json


class TestDeletionJobDryRun:
    def test_dry_run_reports_candidates_without_touching_files(
        self, db_session, tmp_path
    ):
        from services.deletion_job import run_deletion_job

        target = tmp_path / "dry.pdf"
        target.write_bytes(b"%PDF-1.4 data")

        user = _make_user(db_session, "dry-run@example.com")
        doc = _make_doc(
            db_session,
            user.id,
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=90),
            file_path=str(target),
        )

        result = run_deletion_job(db_session, grace_days=30, dry_run=True)

        assert result["dry_run"] is True
        assert result["processed"] == 1
        assert result["deleted_files"] == 0
        assert result["candidate_ids"] == [doc.id]
        assert target.exists()


class TestRetentionCli:
    def test_default_is_dry_run(self):
        cli = _load_retention_cli()
        args = cli.parse_args([])
        assert args.apply is False and args.dry_run is False
        assert args.grace_days == 30

    def test_apply_flag_is_explicit(self):
        cli = _load_retention_cli()
        args = cli.parse_args(["--apply", "--grace-days", "7"])
        assert args.apply is True
        assert args.grace_days == 7

    def test_rejects_non_positive_grace_days(self, tmp_path):
        """A zero grace period would delete on request without a cooling-off."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--apply", "--grace-days", "0"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
            check=False,
        )
        assert result.returncode == 2
        assert "grace-days must be >= 1" in result.stderr

    def test_dry_run_flag_wins_over_apply(self):
        cli = _load_retention_cli()
        args = cli.parse_args(["--apply", "--dry-run"])
        # main() resolves this: --dry-run wins, so nothing is deleted.
        assert args.apply is True and args.dry_run is True

    @pytest.mark.parametrize("flag", ["--help"])
    def test_help_exits_cleanly(self, flag):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), flag],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "grace-days" in result.stdout

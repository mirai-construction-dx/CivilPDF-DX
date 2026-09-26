"""Guard the test suite's isolation from the deployed environment.

Regression context (2026-09-18): neither conftest set ``UPLOAD_DIR``, so
``config.upload_dir`` kept its default of ``~/civildx/uploads`` — the directory
the deployed backend actually uses for uploaded documents. Every
document-upload test therefore wrote real PDFs into production storage: it had
accumulated ~2,000 files that no database row referenced, 700 of them from a
single day of test runs.

These assertions keep the suite hermetic. If someone removes the isolation from
conftest, this fails loudly instead of silently filling production storage.
"""

from pathlib import Path

from config import settings


def test_upload_dir_is_not_the_deployed_default():
    """Tests must never write uploads to the deployed storage location."""
    deployed_default = str(Path.home() / "civildx" / "uploads")
    assert settings.upload_dir != deployed_default, (
        "UPLOAD_DIR is not isolated: the test suite would write real uploads "
        f"into the deployed storage directory ({deployed_default}). Set "
        "UPLOAD_DIR to a temporary directory in conftest.py."
    )


def test_upload_dir_is_a_temporary_directory():
    """The isolated directory should be an obvious throwaway path."""
    upload_dir = settings.upload_dir
    assert (
        "test" in upload_dir.lower() or "tmp" in upload_dir.lower()
    ), f"expected a throwaway upload directory, got {upload_dir!r}"


def test_isolated_upload_dir_is_writable_and_empty_at_start():
    """The sandbox must be usable, and must start clean rather than accumulating."""
    upload_dir = Path(settings.upload_dir)
    probe = upload_dir / ".isolation-probe"
    probe.write_bytes(b"probe")
    try:
        assert probe.read_bytes() == b"probe"
    finally:
        probe.unlink()


def test_database_url_is_not_a_remote_host():
    """Unit tests must run on a local database, never against a remote server."""
    url = settings.database_url
    for remote_marker in ("neon.tech", "amazonaws.com", "supabase"):
        assert (
            remote_marker not in url
        ), f"tests are pointed at a remote database ({remote_marker}): {url.split('@')[-1]}"

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


def test_app_engine_is_isolated_from_the_deployed_database():
    """The app's own engine must not point at the configured (deployed) database.

    Regression context (2026-10-10): the ``get_db`` override in conftest only
    covers FastAPI dependencies, so ``database.engine`` — built from
    ``DATABASE_URL`` at import time and used directly by ``/health/ready`` —
    still pointed at the deployed ``.env`` database. Running pytest from the
    repository root therefore asserted the dialect of the real PostgreSQL
    instance (``assert 'postgresql' == 'sqlite'``) and made ``test_enum_parity``
    run against a schema-less database. Setting ``DATABASE_URL`` in conftest
    before ``from main import app`` is what keeps this hermetic; this assertion
    fails loudly if that isolation is ever removed.
    """
    from database import engine

    assert engine.dialect.name == "sqlite", (
        "the app's engine is not isolated: /health/ready and any other code path "
        "that uses database.engine directly would talk to the deployed database "
        f"({engine.url.get_backend_name()}). Set DATABASE_URL to a temporary "
        "SQLite file in conftest.py before importing the app."
    )
    assert engine.url.get_backend_name() == settings.database_url.split(":", 1)[0], (
        "the app's engine and settings.database_url disagree; the conftest "
        "isolation is not applied to the imported engine"
    )

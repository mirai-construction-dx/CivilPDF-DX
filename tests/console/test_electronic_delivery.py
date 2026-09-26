"""Tests for electronic delivery ZIP generation (Phase 8 P3 / Phase 9 P1).

Covers:
- Readiness check API (GET .../check)
- ZIP generation API (POST .../electronic-delivery)
- ZIP content validation (folder structure, INDEX.XML)
- Auth / permission guards
- Real file inclusion (Phase 9 P1: file_path set → actual bytes in ZIP)
- Missing file fallback (Phase 9 P1: file_path missing → empty placeholder)
- Package integrity vs INDEX.XML, soft-deletion exclusion, deterministic numbering
  (2026-09-18: the package used to contradict its own manifest and to deliver
  documents the user had deleted)
"""

import io
import sys
import os
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src/console/backend"))

import pytest
from fastapi.testclient import TestClient

from models.document import Document, DocumentStatus, DocumentType
from models.user import Project, User


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _create_project(db, code: str = "TEST001", name: str = "テスト工事") -> Project:
    proj = Project(name=name, code=code, description="テスト工事")
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


_CREATED_FILES: list[str] = []


@pytest.fixture(autouse=True, scope="module")
def _cleanup_created_files():
    yield
    for path in _CREATED_FILES:
        try:
            os.unlink(path)
        except OSError:
            pass
    _CREATED_FILES.clear()


def _create_document(
    db,
    project_id: str,
    owner_id: str,
    title: str = "テスト図面",
    doc_type: DocumentType = DocumentType.DRAWING,
    filename: str = "test.pdf",
    is_pdfa: bool = True,
    with_file: bool = True,
) -> Document:
    """Create a document, by default with a real on-disk file.

    Readiness now means "this can be packaged as-is", and generation refuses
    (409) when a deliverable file cannot be read, so the default fixture must be
    genuinely packagable. Pass ``with_file=False`` for the missing-file cases.
    """
    file_path = None
    file_size = 1024
    if with_file:
        fd, file_path = tempfile.mkstemp(suffix=".pdf", prefix="civilpdf-delivery-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"%PDF-1.4 packaged test file")
        _CREATED_FILES.append(file_path)
        file_size = os.path.getsize(file_path)

    doc = Document(
        title=title,
        document_type=doc_type,
        status=DocumentStatus.APPROVED,
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        is_pdfa=is_pdfa,
        project_id=project_id,
        owner_id=owner_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ─── Check endpoint ───────────────────────────────────────────────────────────


def test_check_delivery_empty_project(client: TestClient, admin_token: str, db_session):
    proj = _create_project(db_session)
    resp = client.get(
        f"/api/v1/projects/{proj.id}/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False
    assert data["document_count"] == 0
    assert data["pdfa_compliant_count"] == 0
    assert data["non_pdfa_documents"] == []
    assert any("文書が1件もありません" in w for w in data["warnings"])


def test_check_delivery_with_pdfa_documents(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, is_pdfa=True)
    _create_document(db_session, proj.id, admin_user.id, title="図面2", is_pdfa=True)

    resp = client.get(
        f"/api/v1/projects/{proj.id}/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["document_count"] == 2
    assert data["pdfa_compliant_count"] == 2
    assert data["non_pdfa_documents"] == []
    assert data["unreadable_documents"] == []
    assert data["warnings"] == []


def test_check_delivery_non_pdfa_warning(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    proj = _create_project(db_session)
    _create_document(
        db_session, proj.id, admin_user.id, is_pdfa=False, filename="bad.pdf"
    )

    resp = client.get(
        f"/api/v1/projects/{proj.id}/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["pdfa_compliant_count"] == 0
    assert len(data["non_pdfa_documents"]) == 1
    assert any("PDF/A" in w for w in data["warnings"])


def test_check_delivery_project_not_found(client: TestClient, admin_token: str):
    resp = client.get(
        "/api/v1/projects/nonexistent-id/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_check_delivery_requires_auth(client: TestClient, db_session):
    proj = _create_project(db_session)
    resp = client.get(f"/api/v1/projects/{proj.id}/electronic-delivery/check")
    assert resp.status_code == 401


# ─── ZIP generation endpoint ──────────────────────────────────────────────────


def test_generate_zip_empty_project(client: TestClient, admin_token: str, db_session):
    proj = _create_project(db_session)
    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert ".zip" in resp.headers["content-disposition"]


def test_generate_zip_with_drawing(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, doc_type=DocumentType.DRAWING)

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("INDEX.XML" in n for n in names)
    assert any("DRAWINGS/DRAW_0001.PDF" in n for n in names)


def test_generate_zip_folder_structure(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, doc_type=DocumentType.DRAWING)
    _create_document(
        db_session, proj.id, admin_user.id, title="写真1", doc_type=DocumentType.PHOTO
    )
    _create_document(
        db_session,
        proj.id,
        admin_user.id,
        title="検査1",
        doc_type=DocumentType.INSPECTION,
    )

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("DRAWINGS/DRAW_0001.PDF" in n for n in names)
    assert any("PHOTO/PHOT_0001.PDF" in n for n in names)
    assert any("INSPECTION/INSP_0001.PDF" in n for n in names)


def test_generate_zip_contains_index_xml(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    proj = _create_project(db_session, code="SITE-007", name="国道7号改良工事")
    _create_document(db_session, proj.id, admin_user.id)

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_entries = [n for n in zf.namelist() if n.endswith("INDEX.XML")]
    assert len(xml_entries) == 1


def test_generate_zip_index_xml_content(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    proj = _create_project(db_session, code="PROJ-A1", name="河川改修工事")
    _create_document(db_session, proj.id, admin_user.id, title="平面図")

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_entry = next(n for n in zf.namelist() if n.endswith("INDEX.XML"))
    xml_content = zf.read(xml_entry).decode("utf-8")

    assert "工事管理情報" in xml_content
    assert "PROJ-A1" in xml_content
    assert "河川改修工事" in xml_content
    assert "CivilPDF-DX" in xml_content
    assert "平面図" in xml_content


def test_generate_zip_filename_sanitized(
    client: TestClient, admin_token: str, db_session
):
    proj = _create_project(db_session, code="工事/001", name="テスト")
    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    # Sanitized code must not contain slash or non-ASCII
    filename_part = disposition.split("filename=")[1].strip('"')
    assert "/" not in filename_part
    assert filename_part.isascii()


def test_generate_zip_multiple_docs_same_type(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    proj = _create_project(db_session)
    for i in range(3):
        _create_document(
            db_session,
            proj.id,
            admin_user.id,
            title=f"図面{i + 1}",
            doc_type=DocumentType.DRAWING,
        )

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    drawing_files = [n for n in zf.namelist() if "DRAWINGS/DRAW_" in n]
    assert len(drawing_files) == 3
    assert any("DRAW_0001.PDF" in n for n in drawing_files)
    assert any("DRAW_0002.PDF" in n for n in drawing_files)
    assert any("DRAW_0003.PDF" in n for n in drawing_files)


def test_generate_zip_project_not_found(client: TestClient, admin_token: str):
    resp = client.post(
        "/api/v1/projects/nonexistent-id/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_generate_zip_requires_auth(client: TestClient, db_session):
    proj = _create_project(db_session)
    resp = client.post(f"/api/v1/projects/{proj.id}/electronic-delivery")
    assert resp.status_code == 401


def test_generate_zip_forbidden_for_viewer(
    client: TestClient, viewer_token: str, db_session
):
    proj = _create_project(db_session)
    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


def test_generate_zip_response_headers(
    client: TestClient, admin_token: str, db_session
):
    proj = _create_project(db_session)
    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/zip"
    assert "content-disposition" in resp.headers
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment")


# ─── Phase 9 P1: Real file inclusion tests ───────────────────────────────────


def test_generate_zip_with_real_file(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    """ZIP must contain actual file bytes when doc.file_path points to a real file."""
    proj = _create_project(db_session, code="REAL001", name="実ファイルテスト工事")

    # Write known content to a temp file
    pdf_content = b"%PDF-1.4 fake pdf content for testing real file inclusion"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_content)
        tmp_path = tmp.name

    try:
        doc = Document(
            title="実ファイル図面",
            document_type=DocumentType.DRAWING,
            status=DocumentStatus.APPROVED,
            filename="real.pdf",
            file_path=tmp_path,
            file_size=len(pdf_content),
            is_pdfa=True,
            project_id=proj.id,
            owner_id=admin_user.id,
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.post(
            f"/api/v1/projects/{proj.id}/electronic-delivery",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        drawing_entries = [n for n in zf.namelist() if "DRAWINGS/DRAW_" in n]
        assert len(drawing_entries) == 1

        # Actual PDF bytes must be present inside the ZIP entry
        stored_bytes = zf.read(drawing_entries[0])
        assert stored_bytes == pdf_content
    finally:
        os.unlink(tmp_path)


def test_generate_zip_allow_partial_omits_unreadable_documents(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    """allow_partial=true delivers the readable subset — never 0-byte placeholders.

    A 0-byte PDF inside an official MLIT package is rejected on receipt, so the
    unreadable document is excluded from both the ZIP and INDEX.XML instead of
    being shipped as an empty file. Its omission is reported explicitly.
    """
    proj = _create_project(db_session, code="MISS001", name="欠損ファイルテスト工事")
    good = _create_document(db_session, proj.id, admin_user.id, title="正常図面")

    doc = Document(
        title="欠損ファイル図面",
        document_type=DocumentType.DRAWING,
        status=DocumentStatus.APPROVED,
        filename="missing.pdf",
        file_path="/nonexistent/path/that/does/not/exist.pdf",
        file_size=2048,
        is_pdfa=True,
        project_id=proj.id,
        owner_id=admin_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery?allow_partial=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["x-civilpdf-omitted-documents"] == "1"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    payload = [n for n in zf.namelist() if not n.endswith("INDEX.XML")]
    assert len(payload) == 1, f"only the readable document may be packaged: {payload}"
    assert all(zf.getinfo(n).file_size > 0 for n in payload), "no 0-byte PDFs allowed"

    index = zf.read(next(n for n in zf.namelist() if n.endswith("INDEX.XML"))).decode()
    assert "正常図面" in index
    assert "欠損ファイル図面" not in index
    assert good.id  # keep the readable document referenced


# ─── Package integrity against the INDEX.XML manifest ────────────────────────
# Regression context (2026-09-18): the delivery package silently contradicted
# its own manifest. A document whose file was gone was packed as a 0-byte entry
# while INDEX.XML still declared the original size, the readiness check reported
# ready=true, and soft-deleted documents were delivered to MLIT.


def test_generate_zip_refuses_to_package_unreadable_documents_by_default(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    """Never hand MLIT a knowingly-invalid deliverable: fail closed instead."""
    proj = _create_project(db_session)
    _create_document(
        db_session, proj.id, admin_user.id, title="欠損図面", with_file=False
    )

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409, resp.text[:200]
    detail = resp.json()["detail"]
    assert "読み取れない" in detail
    assert "欠損図面" in detail
    assert "allow_partial=true" in detail


def test_readiness_flags_unreadable_documents_and_is_not_ready(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, title="正常図面")
    _create_document(
        db_session, proj.id, admin_user.id, title="欠損図面", with_file=False
    )

    resp = client.get(
        f"/api/v1/projects/{proj.id}/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False, "a document that cannot be packaged must not be 'ready'"
    assert data["document_count"] == 2
    assert len(data["unreadable_documents"]) == 1
    assert data["unreadable_documents"][0]["title"] == "欠損図面"
    assert any("読み取れない" in w for w in data["warnings"])


def test_readiness_excludes_soft_deleted_documents(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    from datetime import datetime, timezone

    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, title="納品対象")
    trashed = _create_document(
        db_session, proj.id, admin_user.id, title="誤アップロード"
    )
    trashed.deletion_requested_at = datetime.now(timezone.utc)
    db_session.commit()

    resp = client.get(
        f"/api/v1/projects/{proj.id}/electronic-delivery/check",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["document_count"] == 1, "deletion-requested documents must not be delivered"
    assert data["ready"] is True


def test_zip_excludes_soft_deleted_documents(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    from datetime import datetime, timezone

    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, title="納品対象")
    trashed = _create_document(
        db_session, proj.id, admin_user.id, title="誤アップロード"
    )
    trashed.deletion_requested_at = datetime.now(timezone.utc)
    db_session.commit()

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    payload_entries = [n for n in zf.namelist() if not n.endswith("INDEX.XML")]
    assert len(payload_entries) == 1, f"trashed document leaked into the package: {payload_entries}"

    index = zf.read(next(n for n in zf.namelist() if n.endswith("INDEX.XML"))).decode()
    assert "誤アップロード" not in index
    assert "納品対象" in index


def test_index_xml_never_declares_a_size_the_package_does_not_have(
    client: TestClient, admin_token: str, admin_user: User, db_session
):
    """The manifest must describe the artefact, never the stale DB size."""
    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id, title="正常図面")
    _create_document(
        db_session, proj.id, admin_user.id, title="欠損図面", with_file=False
    )

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery?allow_partial=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    entries = [n for n in zf.namelist() if not n.endswith("INDEX.XML")]
    assert len(entries) == 1
    assert zf.getinfo(entries[0]).file_size > 0

    from xml.etree import ElementTree as ET

    root = ET.fromstring(
        zf.read(next(n for n in zf.namelist() if n.endswith("INDEX.XML"))).decode()
    )
    file_info = root.find(".//ファイル情報")
    assert file_info is not None
    declared_size = file_info.findtext("ファイルサイズ")
    actual_size = zf.getinfo(entries[0]).file_size
    assert declared_size == str(actual_size), (
        f"INDEX.XML declares {declared_size} bytes but the package holds "
        f"{actual_size}; the deliverable would contradict its own manifest"
    )


def test_index_xml_declares_the_current_software_version(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    """INDEX.XML used to hardcode 'v0.7.0' while the app version moved on."""
    from config import settings

    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id)

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    from xml.etree import ElementTree as ET

    root = ET.fromstring(
        zf.read(next(n for n in zf.namelist() if n.endswith("INDEX.XML"))).decode()
    )
    declared = root.findtext("./基本情報/ソフトウェアバージョン")
    assert declared == f"v{settings.app_version.lstrip('v')}"


def test_generation_is_recorded_in_the_audit_chain(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    """Producing an official deliverable is an auditable compliance action."""
    from models.audit_log import AuditLog

    proj = _create_project(db_session)
    _create_document(db_session, proj.id, admin_user.id)
    _create_document(
        db_session, proj.id, admin_user.id, title="欠損図面", with_file=False
    )

    resp = client.post(
        f"/api/v1/projects/{proj.id}/electronic-delivery?allow_partial=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "electronic_delivery.generated")
        .one()
    )
    import json as _json

    detail = _json.loads(entry.detail)
    assert detail["document_count"] == 1, "only the readable document is packaged"
    assert detail["omitted_count"] == 1
    assert detail["allow_partial"] is True
    assert detail["package_bytes"] > 0


def test_package_numbering_is_deterministic(
    client: TestClient, admin_token: str, admin_user: User, db_session, tmp_path
):
    """Explicit ordering keeps DRAW_0001/DRAW_0002 stable between runs."""
    proj = _create_project(db_session)
    for title in ("あ図面", "い図面", "う図面"):
        _create_document(db_session, proj.id, admin_user.id, title=title)

    def names():
        resp = client.post(
            f"/api/v1/projects/{proj.id}/electronic-delivery",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        index = zf.read(next(n for n in zf.namelist() if n.endswith("INDEX.XML"))).decode()
        from xml.etree import ElementTree as ET

        root = ET.fromstring(index)
        return [
            (fi.findtext("ファイル名"), fi.findtext("タイトル"))
            for fi in root.iter("ファイル情報")
        ]

    first = names()
    second = names()
    assert first == second, "package numbering must be reproducible between runs"
    assert {t for _, t in first} == {"あ図面", "い図面", "う図面"}
    assert [n for n, _ in first] == ["DRAW_0001.PDF", "DRAW_0002.PDF", "DRAW_0003.PDF"]

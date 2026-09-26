"""OCR / text-extraction API tests.

Scope:
  * authorization — access follows document visibility (the endpoints used to
    have no visibility check at all, so any authenticated user could read any
    document's text by id)
  * persistence — jobs live in the database, not a per-worker dict
  * contract — the response reports the real engine and never presents a
    placeholder sentence as extracted text
"""

import io

import pytest

from models.ocr_job import OCR_ENGINE_TEXT_LAYER, OcrJob


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _make_blank_pdf_bytes() -> bytes:
    """A valid one-page PDF with no text layer (the image-only-drawing case)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _make_text_pdf_bytes(text: str = "Runtime OCR text layer") -> bytes:
    """Build a one-page PDF whose text layer contains ``text``.

    A blank page has no text, so the page needs a font resource and a content
    stream for ``extract_text()`` to return anything.
    """
    from pypdf import PdfWriter
    from pypdf.generic import (
        DictionaryObject,
        NameObject,
        StreamObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    content = StreamObject()
    content.set_data(f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = content

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class TestOcrApi:
    def _create_project(self, client, token, code="OCR-001") -> str:
        return client.post(
            "/api/v1/projects/",
            json={"name": "OCR Project", "code": code},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["id"]

    def _create_document(
        self, client, token, project_id=None, pdf=None, code="OCR-001"
    ) -> str:
        project_id = project_id or self._create_project(client, token, code=code)
        doc = client.post(
            "/api/v1/documents/",
            data={
                "project_id": project_id,
                "title": "OCR Test",
                "document_type": "drawing",
            },
            files={
                "file": (
                    "test.pdf",
                    io.BytesIO(pdf or _make_pdf_bytes()),
                    "application/pdf",
                )
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert doc.status_code == 201, doc.text[:200]
        return doc.json()["id"]

    # ── happy path ───────────────────────────────────────────────────────
    def test_start_ocr_job(self, client, admin_token):
        doc_id = self._create_document(client, admin_token)
        resp = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["document_id"] == doc_id
        assert data["engine"] == OCR_ENGINE_TEXT_LAYER
        assert data["language"] == "jpn"
        assert data["enable_vertical"] is True
        assert "job_id" in data

    def test_get_ocr_job_status(self, client, admin_token):
        doc_id = self._create_document(client, admin_token)
        job_id = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()["job_id"]

        resp = client.get(
            f"/api/v1/ocr/jobs/{job_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("completed", "unsupported", "failed")

    def test_unknown_document_is_404(self, client, admin_token):
        resp = client.post(
            "/api/v1/ocr/process",
            json={"document_id": "00000000-0000-0000-0000-000000000000"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_unknown_job_is_404(self, client, admin_token):
        resp = client.get(
            "/api/v1/ocr/jobs/nonexistent-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        assert (
            client.post("/api/v1/ocr/process", json={"document_id": "x"}).status_code
            == 401
        )

    # ── contract honesty ────────────────────────────────────────────────
    def test_pdf_without_text_layer_is_reported_as_unsupported(
        self, client, admin_token
    ):
        """A missing text layer must be explicit, never a fake page of text."""
        doc_id = self._create_document(
            client, admin_token, pdf=_make_blank_pdf_bytes(), code="OCR-NOTEXT"
        )
        start = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert start["status"] == "unsupported", start
        assert start["page_count"] == 0
        assert start["engine"] == OCR_ENGINE_TEXT_LAYER
        assert "OCR" in (start["error"] or "")

        result = client.get(
            f"/api/v1/ocr/jobs/{start['job_id']}/result",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert result.status_code == 200
        assert result.json()["pages"] == [], "placeholder text must not be returned"
        assert result.json()["status"] == "unsupported"

    def test_unparseable_pdf_is_reported_as_failed(self, client, admin_token):
        """A broken PDF is a failure, not "no text" — the caller must be able to tell."""
        doc_id = self._create_document(client, admin_token, code="OCR-BROKEN")
        data = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert data["status"] == "failed", data
        assert data["pages"] if "pages" in data else True
        assert data["error"]

    def test_pdf_with_text_layer_returns_the_text(self, client, admin_token):
        doc_id = self._create_document(
            client,
            admin_token,
            pdf=_make_text_pdf_bytes("Bridge repair plan S=1/100"),
            code="OCR-TEXT",
        )
        start = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert start["status"] == "completed", start
        result = client.get(
            f"/api/v1/ocr/jobs/{start['job_id']}/result",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert result["pages"], "expected at least one extracted page"
        assert "Bridge repair plan" in result["pages"][0]["text"]

    def test_request_options_are_echoed_back(self, client, admin_token):
        doc_id = self._create_document(client, admin_token)
        data = client.post(
            "/api/v1/ocr/process",
            json={
                "document_id": doc_id,
                "language": "eng",
                "enable_vertical": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert data["language"] == "eng"
        assert data["enable_vertical"] is False

    # ── persistence (multi-worker / restart) ─────────────────────────────
    def test_job_is_persisted_not_held_in_process_memory(
        self, client, admin_token, db_session
    ):
        """Jobs must be readable by another process, not a per-worker dict.

        Simulates a poll served by a different uvicorn worker: the job row has to
        exist in the database for the second request to find it.
        """
        doc_id = self._create_document(client, admin_token, code="OCR-PERSIST")
        job_id = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()["job_id"]

        row = db_session.query(OcrJob).filter(OcrJob.id == job_id).one()
        assert row.document_id == doc_id
        assert row.engine == OCR_ENGINE_TEXT_LAYER
        # A fresh session (as another worker would use) can still read it.
        db_session.expunge_all()
        assert db_session.query(OcrJob).filter(OcrJob.id == job_id).count() == 1

    # ── authorization ───────────────────────────────────────────────────
    def test_viewer_cannot_extract_text_from_an_invisible_project(
        self, client, admin_token, viewer_token, db_session
    ):
        """Regression: /ocr/process had no visibility check at all.

        A viewer who is not a member of the document's project must not be able
        to read its text — that leaked another organization's documents.
        """
        doc_id = self._create_document(client, admin_token, code="OCR-SECRET")

        resp = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert (
            resp.status_code == 404
        ), "viewer without project membership must not reach the document"

    def test_viewer_cannot_read_another_users_job(
        self, client, admin_token, viewer_token
    ):
        doc_id = self._create_document(client, admin_token, code="OCR-JOB-SECRET")
        job_id = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()["job_id"]

        for path in (f"/api/v1/ocr/jobs/{job_id}", f"/api/v1/ocr/jobs/{job_id}/result"):
            resp = client.get(path, headers={"Authorization": f"Bearer {viewer_token}"})
            assert resp.status_code == 404, f"{path} leaked another user's job"

    def test_admin_can_extract_text_from_any_visible_document(
        self, client, admin_token, viewer_token
    ):
        """The owner of the document keeps access (no over-blocking)."""
        doc_id = self._create_document(client, admin_token, code="OCR-OWNER")
        job_id = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()["job_id"]
        assert (
            client.get(
                f"/api/v1/ocr/jobs/{job_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            ).status_code
            == 200
        )

    def test_gdpr_erased_document_is_gone(self, client, admin_token, db_session):
        from models.document import Document

        doc_id = self._create_document(client, admin_token, code="OCR-ERASED")
        doc = db_session.query(Document).filter(Document.id == doc_id).one()
        doc.file_path = None  # what the GDPR deletion job does
        db_session.commit()

        resp = client.post(
            "/api/v1/ocr/process",
            json={"document_id": doc_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 410


@pytest.mark.parametrize("status_value", ["completed", "unsupported", "failed"])
def test_status_constants_are_stable(status_value):
    """The API contract documents these values; keep them from drifting."""
    from models.ocr_job import (
        OCR_STATUS_COMPLETED,
        OCR_STATUS_FAILED,
        OCR_STATUS_UNSUPPORTED,
    )

    assert status_value in {
        OCR_STATUS_COMPLETED,
        OCR_STATUS_UNSUPPORTED,
        OCR_STATUS_FAILED,
    }

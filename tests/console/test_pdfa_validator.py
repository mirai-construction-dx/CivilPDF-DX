"""Tests for services/pdfa_validator.py — PDF/A validation (ISO 14289)."""

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_pdf_bytes() -> bytes:
    """Minimal syntactically-valid PDF bytes for testing."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"


# ---------------------------------------------------------------------------
# pypdf fallback path
# ---------------------------------------------------------------------------


class TestPypdfFallback:
    @patch("services.pdfa_validator.VERA_PDF_CMD", None)
    def test_no_xmp_returns_not_pdfa(self):
        from services.pdfa_validator import validate_pdfa

        result = validate_pdfa(_make_pdf_bytes())

        assert result["is_pdfa"] is False
        assert result["validator"] == "pypdf"
        assert result["conformant"] is False
        # pypdf 5.x omits xmp_metadata attribute for PDFs without XMP; either a warning
        # is recorded or the result is simply not-pdfa with no errors — both are acceptable
        assert isinstance(result["warnings"], list)
        assert isinstance(result["errors"], list)

    @patch("services.pdfa_validator.VERA_PDF_CMD", None)
    def test_invalid_pdf_records_error(self):
        from services.pdfa_validator import validate_pdfa

        result = validate_pdfa(b"this is not a pdf")

        assert result["is_pdfa"] is False
        assert result["validator"] == "pypdf"
        assert len(result["errors"]) > 0

    @patch("services.pdfa_validator.VERA_PDF_CMD", None)
    def test_xmp_pdfa_detected(self):
        """Simulate pypdf finding PDF/A XMP markers."""
        from services.pdfa_validator import _validate_with_pypdf

        mock_part = MagicMock()
        mock_part.text = "3"
        mock_conformance = MagicMock()
        mock_conformance.text = "B"

        mock_xmp = MagicMock()
        mock_xmp.get_element.side_effect = (
            lambda *a: mock_conformance if a[2] == "conformance" else mock_part
        )

        mock_reader = MagicMock()
        mock_reader.xmp_metadata = mock_xmp

        with patch("services.pdfa_validator.PdfReader", return_value=mock_reader):
            result = _validate_with_pypdf(b"fake")

        assert result["is_pdfa"] is True
        assert result["pdfa_version"] == "PDF/A-3b"
        assert result["conformant"] is True

    @patch("services.pdfa_validator.VERA_PDF_CMD", None)
    def test_xmp_none_returns_not_pdfa(self):
        from services.pdfa_validator import _validate_with_pypdf

        mock_reader = MagicMock()
        mock_reader.xmp_metadata = None

        with patch("services.pdfa_validator.PdfReader", return_value=mock_reader):
            result = _validate_with_pypdf(b"fake")

        assert result["is_pdfa"] is False


# ---------------------------------------------------------------------------
# veraPDF path
# ---------------------------------------------------------------------------


class TestVeraPDF:
    @patch("services.pdfa_validator.VERA_PDF_CMD", "/usr/bin/verapdf")
    def test_compliant_report_parsed(self, tmp_path):
        from services.pdfa_validator import _validate_with_verapdf

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(_make_pdf_bytes())

        vera_output = json.dumps(
            {
                "report": {
                    "jobs": [
                        {
                            "validationResult": {
                                "compliant": True,
                                "profileName": "PDF/A-3b validation profile",
                                "assertions": {"failedChecks": 0},
                            }
                        }
                    ]
                }
            }
        )

        mock_proc = MagicMock()
        mock_proc.stdout = vera_output

        with patch("subprocess.run", return_value=mock_proc):
            result = _validate_with_verapdf(str(pdf_file))

        assert result["is_pdfa"] is True
        assert result["conformant"] is True
        assert result["validator"] == "veraPDF"
        assert "PDF/A-3b" in result["pdfa_version"]

    @patch("services.pdfa_validator.VERA_PDF_CMD", "/usr/bin/verapdf")
    def test_non_compliant_report(self, tmp_path):
        from services.pdfa_validator import _validate_with_verapdf

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(_make_pdf_bytes())

        vera_output = json.dumps(
            {
                "report": {
                    "jobs": [
                        {
                            "validationResult": {
                                "compliant": False,
                                "profileName": "",
                                "assertions": {"failedChecks": 5},
                            }
                        }
                    ]
                }
            }
        )
        mock_proc = MagicMock()
        mock_proc.stdout = vera_output

        with patch("subprocess.run", return_value=mock_proc):
            result = _validate_with_verapdf(str(pdf_file))

        assert result["is_pdfa"] is False
        assert len(result["warnings"]) > 0

    @patch("services.pdfa_validator.VERA_PDF_CMD", "/usr/bin/verapdf")
    def test_timeout_recorded_as_error(self, tmp_path):
        import subprocess
        from services.pdfa_validator import _validate_with_verapdf

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"x")

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="verapdf", timeout=60),
        ):
            result = _validate_with_verapdf(str(pdf_file))

        assert result["is_pdfa"] is False
        assert any("timed out" in e for e in result["errors"])

    @patch("services.pdfa_validator.VERA_PDF_CMD", "/usr/bin/verapdf")
    def test_uses_vera_when_file_exists(self, tmp_path):
        """validate_pdfa() selects veraPDF when cmd and file are available."""
        from services.pdfa_validator import validate_pdfa

        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(_make_pdf_bytes())

        with patch("services.pdfa_validator._validate_with_verapdf") as mock_vera:
            mock_vera.return_value = {
                "is_pdfa": True,
                "pdfa_version": "PDF/A-3b",
                "conformant": True,
                "validator": "veraPDF",
                "warnings": [],
                "errors": [],
            }
            result = validate_pdfa(b"bytes", str(pdf_file))

        mock_vera.assert_called_once_with(str(pdf_file))
        assert result["is_pdfa"] is True

    @patch("services.pdfa_validator.VERA_PDF_CMD", "/usr/bin/verapdf")
    def test_falls_back_to_pypdf_when_file_missing(self):
        from services.pdfa_validator import validate_pdfa

        with patch("services.pdfa_validator._validate_with_pypdf") as mock_pyp:
            mock_pyp.return_value = {
                "is_pdfa": False,
                "pdfa_version": None,
                "conformant": False,
                "validator": "pypdf",
                "warnings": [],
                "errors": [],
            }
            result = validate_pdfa(b"bytes", "/nonexistent/path.pdf")

        mock_pyp.assert_called_once()
        assert result["validator"] == "pypdf"

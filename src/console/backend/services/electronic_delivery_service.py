"""Electronic delivery (電子納品) ZIP package generator.

Conforms to the MLIT (国土交通省) CALS/EC electronic delivery standard.
Generates a ZIP with folder structure, PDF files, and INDEX.XML metadata.
"""

import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from config import settings
from models.document import Document, DocumentType
from models.user import Project

# Maps DocumentType → (folder_name, file_prefix)
_FOLDER_MAP: dict[DocumentType, tuple[str, str]] = {
    DocumentType.DRAWING: ("DRAWINGS", "DRAW"),
    DocumentType.PHOTO: ("PHOTO", "PHOT"),
    DocumentType.INSPECTION: ("INSPECTION", "INSP"),
    DocumentType.SAFETY: ("SAFETY", "SAFE"),
    DocumentType.CONTRACT: ("CONTRACT", "CONT"),
    DocumentType.REPORT: ("REPORT", "REPO"),
    DocumentType.CORRECTION: ("CORRECTION", "CORR"),
    DocumentType.OTHER: ("OTHER", "OTHE"),
}


def _sanitize_code(code: str) -> str:
    """Convert project code to uppercase alphanumeric + underscore (max 16 chars)."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", code).upper()
    return sanitized[:16]


def package_filename(project: Project, generated_at: datetime | None = None) -> str:
    """Return the download filename for a delivery package."""
    generated = generated_at or datetime.now(timezone.utc)
    return f"{_sanitize_code(project.code)}_{generated:%Y%m%d}.zip"


def deliverable_documents(db: Session, project_id: str) -> list[Document]:
    """Return the documents eligible to be packaged for electronic delivery.

    Soft-deleted documents are excluded. A document whose deletion a user has
    requested (ごみ箱 / GDPR Art.17, including ones already physically erased)
    must never be handed to a third party as part of an official deliverable —
    previously the package and INDEX.XML both included them, so a document the
    user had deleted was still delivered to MLIT.

    Ordering is explicit (``created_at``, then ``id``) so the DRAW_0001 /
    PHOT_0001 numbering in INDEX.XML and in the ZIP is reproducible across runs.
    """
    return (
        db.query(Document)
        .filter(
            Document.project_id == project_id,
            Document.deletion_requested_at.is_(None),
        )
        .order_by(Document.created_at.asc(), Document.id.asc())
        .all()
    )


def find_unreadable_documents(documents: list[Document]) -> list[dict[str, str]]:
    """Return documents whose stored file cannot be packaged.

    An aborted upload, a manually removed upload directory or a half-finished
    restore leaves ``file_path`` set while the file is gone. Packaging such a
    document silently produced a 0-byte PDF that INDEX.XML still described with
    the original size, so the deliverable contradicted its own manifest.
    """
    unreadable: list[dict[str, str]] = []
    for doc in documents:
        if not doc.file_path:
            unreadable.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "filename": doc.filename,
                    "reason": "ファイルの保存先が登録されていません",
                }
            )
            continue
        try:
            path = Path(doc.file_path)
            if not path.is_file():
                reason = "ファイルが存在しません"
            elif path.stat().st_size == 0:
                reason = "ファイルが空です"
            else:
                continue
        except OSError as exc:
            reason = f"ファイルを読み取れません ({exc.__class__.__name__})"
        unreadable.append(
            {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "reason": reason,
            }
        )
    return unreadable


def _sub(parent: ET.Element, tag: str, text: str) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = text
    return el


def _build_index_xml(
    project: Project,
    by_folder: dict[str, list[Document]],
    generated_at: datetime,
    packaged_size: dict[str, int],
) -> bytes:
    """Build INDEX.XML per MLIT electronic delivery standard.

    ``packaged_size`` maps document id -> bytes actually written into the ZIP so
    the manifest always describes the artefact rather than the stale value in
    the database.
    """
    root = ET.Element("工事管理情報")

    basic = ET.SubElement(root, "基本情報")
    _sub(basic, "工事番号", project.code)
    _sub(basic, "工事名称", project.name)
    _sub(basic, "作成日", generated_at.strftime("%Y%m%d"))
    _sub(basic, "ソフトウェア名", "CivilPDF-DX")
    _sub(basic, "ソフトウェアバージョン", f"v{settings.app_version.lstrip('v')}")

    outcomes = ET.SubElement(root, "成果品情報")
    for folder_name, docs in sorted(by_folder.items()):
        _, prefix = _FOLDER_MAP.get(docs[0].document_type, ("OTHER", "OTHE"))
        folder_el = ET.SubElement(
            outcomes,
            "フォルダ情報",
            attrib={"フォルダ名": folder_name, "ファイル数": str(len(docs))},
        )
        for i, doc in enumerate(docs, start=1):
            file_el = ET.SubElement(folder_el, "ファイル情報")
            _sub(file_el, "ファイル名", f"{prefix}_{i:04d}.PDF")
            _sub(file_el, "タイトル", doc.title)
            _sub(file_el, "ファイルサイズ", str(packaged_size.get(doc.id, 0)))
            _sub(file_el, "PDF_A準拠", "1" if doc.is_pdfa else "0")

    declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_body = ET.tostring(root, encoding="unicode")
    return (declaration + xml_body).encode("utf-8")


def _group_by_folder(documents: list[Document]) -> dict[str, list[Document]]:
    by_folder: dict[str, list[Document]] = defaultdict(list)
    for doc in documents:
        folder_name, _ = _FOLDER_MAP.get(doc.document_type, ("OTHER", "OTHE"))
        by_folder[folder_name].append(doc)
    return by_folder


def check_delivery_readiness(
    project: Project, documents: list[Document]
) -> dict[str, Any]:
    """Return readiness status for electronic delivery packaging."""
    pdfa_count = sum(1 for d in documents if d.is_pdfa)
    non_pdfa = [
        {"id": d.id, "title": d.title, "filename": d.filename}
        for d in documents
        if not d.is_pdfa
    ]
    unreadable = find_unreadable_documents(documents)
    warnings: list[str] = []
    if not documents:
        warnings.append("プロジェクトに文書が1件もありません")
    if non_pdfa:
        warnings.append(f"PDF/A 非準拠ファイルが {len(non_pdfa)} 件あります")
    if unreadable:
        warnings.append(
            f"ファイルを読み取れない文書が {len(unreadable)} 件あります"
            "（そのままでは納品パッケージを生成できません）"
        )

    return {
        # "ready" means "this can be packaged as-is": a document whose file is
        # missing blocks packaging (409) unless a partial package is requested.
        "ready": len(documents) > 0 and not unreadable,
        "document_count": len(documents),
        "pdfa_compliant_count": pdfa_count,
        "non_pdfa_documents": non_pdfa,
        "unreadable_documents": unreadable,
        "warnings": warnings,
    }


def generate_delivery_zip(
    project: Project,
    documents: list[Document],
    generated_at: datetime | None = None,
) -> bytes:
    """Build in-memory ZIP conforming to MLIT electronic delivery layout.

    Layout:
        {CODE}_{YYYYMMDD}/
        ├── INDEX.XML
        ├── DRAWINGS/DRAW_0001.PDF …
        ├── PHOTO/PHOT_0001.PDF …
        └── …

    ``generated_at`` pins the package date (root folder name and the INDEX.XML
    作成日) so a delivery can be regenerated and verified later. ZIP entry
    timestamps are pinned to that same instant instead of ``time.localtime``,
    which otherwise made the bytes depend on the calling host's clock and
    timezone. With both pinned, the same input produces byte-identical output.
    """
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        # A naive datetime would be interpreted in the host timezone; treat it
        # as UTC so the package never depends on the calling environment.
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    date_str = generated_at.strftime("%Y%m%d")
    proj_code = _sanitize_code(project.code)
    root_dir = f"{proj_code}_{date_str}"
    zip_date_time = generated_at.astimezone(timezone.utc).timetuple()[:6]

    by_folder = _group_by_folder(documents)
    # Read each file exactly once: the INDEX.XML size entry and the packaged
    # bytes then come from the same read, so a file that changes between a
    # stat() and a read() can no longer make the manifest disagree with the
    # payload.
    payload: dict[str, bytes] = {}
    packaged_size: dict[str, int] = {}
    for docs in by_folder.values():
        for doc in docs:
            data = _read_file(doc)
            payload[doc.id] = data
            packaged_size[doc.id] = len(data)

    def _write(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
        info = zipfile.ZipInfo(filename=name, date_time=zip_date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        # Normalise the external attributes so the bytes do not depend on the
        # platform that produced the package.
        info.external_attr = 0o600 << 16
        zf.writestr(info, data)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        index_xml = _build_index_xml(project, by_folder, generated_at, packaged_size)
        _write(zf, f"{root_dir}/INDEX.XML", index_xml)

        for folder_name, docs in sorted(by_folder.items()):
            _, prefix = _FOLDER_MAP.get(docs[0].document_type, ("OTHER", "OTHE"))
            for i, doc in enumerate(docs, start=1):
                dest_name = f"{prefix}_{i:04d}.PDF"
                dest_path = f"{root_dir}/{folder_name}/{dest_name}"
                _write(zf, dest_path, payload[doc.id])

    return buf.getvalue()


def _read_file(doc: Document) -> bytes:
    """Read document bytes; return empty placeholder if file is missing."""
    if doc.file_path:
        try:
            return Path(doc.file_path).read_bytes()
        except OSError:
            pass
    return b""

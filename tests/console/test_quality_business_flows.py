"""Spec-based quality tests for the main construction-document business flows.

Scope (selected from the flows this repository actually implements — see
``docs/requirements.md`` §3.2): document lifecycle → approval, electronic
delivery (CALS/EC packaging), retention, audit trail, role/tenant isolation and
the AI/human confirmation boundary.  Flows this repository does not implement
(数量・原価・工程・BIM/CIM・GIS・点群・現場計測) are deliberately out of scope.

The tests assert *invariants that the existing suite does not cover*:

* a document cannot be re-typed (種別) by a non-manager after it was approved
* deleting a document does not silently cancel or alter an in-flight approval
* electronic-delivery output is reproducible for a fixed ``generated_at``
* retention expiry arithmetic is the documented ``365 days × years`` rule
* the audit chain holds for the approval flow and for delivery generation
* the AI classification path never writes approval-bearing fields
  (``document_type`` / ``status``) and never approves a document
* project members are gated by *membership*, not by "the request 404s because
  the user is a stranger" (the coverage illusion called out by
  ``tests/console/test_route_authorization.py``)

All fixtures are synthetic: documents are tiny generated PDFs, users are
created through the API, and no external provider is contacted (the AI client
is replaced with a local stub).
"""

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models.document import DocumentStatus
from services import retention_service
from services.electronic_delivery_service import generate_delivery_zip


# ── helpers ───────────────────────────────────────────────────────────────────


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _parseable_pdf() -> bytes:
    """Minimal PDF with a valid xref table so pypdf can open it."""
    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    obj2 = b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    obj3 = b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    body = header + obj1 + obj2 + obj3
    offsets = [
        0,
        len(header),
        len(header) + len(obj1),
        len(header) + len(obj1) + len(obj2),
    ]
    xref_offset = len(body)
    xref = b"xref\n0 4\n0000000000 65535 f \n" + b"".join(
        f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]
    )
    trailer = (
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return body + xref + trailer


def _create_project(client, admin_token, code: str | None = None) -> str:
    resp = client.post(
        "/api/v1/projects/",
        json={"name": "QA Project", "code": code or f"QA-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_user(client, admin_token, role: str = "engineer") -> tuple[str, str]:
    """Create a synthetic user via the API; return (user_id, token)."""
    suffix = uuid.uuid4().hex[:8]
    email = f"qa-{suffix}@example.com"
    password = "Quality123!"
    resp = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "username": f"qa-{suffix}",
            "full_name": f"QA {suffix}",
            "password": password,
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    token = client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    ).json()["access_token"]
    return resp.json()["id"], token


def _add_member(client, admin_token, project_id: str, user_id: str) -> None:
    resp = client.post(
        f"/api/v1/projects/{project_id}/members/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204, resp.text


def _upload(client, token: str, project_id: str, title: str = "QA Doc") -> str:
    resp = client.post(
        "/api/v1/documents/",
        data={"project_id": project_id, "title": title},
        files={"file": ("qa.pdf", io.BytesIO(_pdf()), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _status(client, token: str, doc_id: str) -> str:
    resp = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


def _approve_fully(client, admin_token: str, doc_id: str) -> str:
    """Create a single-step workflow and approve it; return the workflow id."""
    resp = client.post(
        "/api/v1/workflows/",
        json={"document_id": doc_id, "approver_ids": [_admin_id(client, admin_token)]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    workflow = resp.json()
    step_id = workflow["steps"][0]["id"]
    decided = client.post(
        f"/api/v1/workflows/{workflow['id']}/steps/{step_id}/decide",
        json={"decision": "approve", "comment": "QA"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert decided.status_code == 200, decided.text
    return workflow["id"]


def _admin_id(client, admin_token: str) -> str:
    resp = client.get(
        "/api/v1/users/", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, resp.text
    for user in resp.json():
        if user["email"] == "admin@example.com":
            return user["id"]
    raise AssertionError("admin user not found")


# ── 1. 文書 → 承認フローの品質不変条件 ────────────────────────────────────────


class TestDocumentApprovalLifecycle:
    """docs/requirements.md §3.2.4 WEB-DOC-002/005, §3.2.5 WEB-WF-002/003."""

    def test_approval_marks_document_and_blocks_role_change_by_non_manager(
        self, client, admin_token
    ):
        """承認後に非管理者が種別を書き換えられない（品質記録の固定）。

        文書種別は電子納品のフォルダ振り分け（INDEX.XML の構成）を決めるため、
        承認後に変更できると「承認済みの内容」と「納品物」が乖離する。
        """
        project_id = _create_project(client, admin_token)
        engineer_id, engineer_token = _create_user(client, admin_token, "engineer")
        _add_member(client, admin_token, project_id, engineer_id)
        doc_id = _upload(client, engineer_token, project_id, "承認対象図面")

        _approve_fully(client, admin_token, doc_id)
        assert _status(client, engineer_token, doc_id) == "approved"

        # 承認後は所有者でも種別を変えられない（納品フォルダが変わるため）。
        resp = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"document_type": "photo"},
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 409, resp.text

        # 所有者による title の訂正は承認後も可能（承認状態は変わらない）。
        resp = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"title": "承認対象図面（改題）"},
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == "承認対象図面（改題）"
        assert resp.json()["status"] == "approved"

    def test_non_owner_member_cannot_retype_someone_elses_document(
        self, client, admin_token
    ):
        """所有者でも manager でもないプロジェクトメンバーは種別を変更できない。"""
        project_id = _create_project(client, admin_token)
        outsider_id, outsider_token = _create_user(client, admin_token, "engineer")
        _add_member(client, admin_token, project_id, outsider_id)
        doc_id = _upload(client, admin_token, project_id, "他人の図面")

        resp = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"document_type": "photo"},
            headers={"Authorization": f"Bearer {outsider_token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_soft_delete_does_not_cancel_the_approval_flow(self, client, admin_token):
        """ごみ箱化しても承認フローは自動では終端しない（監査証跡の意味を保つ）。

        WEB-DOC-005 は論理削除（ごみ箱）と 30 日後の物理削除を分けている。
        削除がワークフローを暗黙に却下/承認すると、監査時に「誰が承認したか」と
        「なぜ消えたか」が混ざる。実装がどちらを採るかを明示的に固定する。
        """
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "削除と承認")
        workflow_id = _approve_fully(client, admin_token, doc_id)

        deleted = client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert deleted.status_code == 204, deleted.text

        workflow = client.get(
            f"/api/v1/workflows/{workflow_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert workflow.status_code == 200, workflow.text
        # The workflow keeps its own terminal state; deletion does not rewrite it.
        assert workflow.json()["status"] == "approved"

        restored = client.post(
            f"/api/v1/documents/{doc_id}/restore",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert restored.status_code == 200, restored.text
        # C-1: restore returns the document to its pre-deletion status. It was
        # approved before deletion, so it comes back as approved; the workflow
        # record stays approved either way.
        assert restored.json()["status"] == "approved"
        assert (
            client.get(
                f"/api/v1/workflows/{workflow_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            ).json()["status"]
            == "approved"
        )

    def test_one_document_has_at_most_one_workflow(self, client, admin_token):
        """同一文書に承認フローを二重作成できない（多重承認の防止）。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "二重フロー")
        _approve_fully(client, admin_token, doc_id)

        resp = client.post(
            "/api/v1/workflows/",
            json={
                "document_id": doc_id,
                "approver_ids": [_admin_id(client, admin_token)],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409, resp.text


# ── 2. 電子納品の再現性 ───────────────────────────────────────────────────────


class TestElectronicDeliveryReproducibility:
    """docs/requirements.md §3.2.7 電子納品（国交省 CALS/EC 要領準拠 ZIP）。"""

    def test_delivery_package_accepts_a_fixed_generated_at(
        self, db_session, admin_user
    ):
        """生成時刻を固定すると、同一入力の納品 ZIP はバイト同一になる。

        ``package_filename`` と同じく ``generated_at`` を受け取り、ZIP エントリの
        時刻もその瞬間に固定する。以前は内部で ``datetime.now`` を呼び、エントリ
        時刻も ``time.localtime`` 由来だったため、再納品・再検査で同じ成果品を
        再現できなかった（発注者側のハッシュ照合に耐えない）。
        """
        from models.user import Project

        project = Project(name="QA納品", code=f"QA-DEL-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        documents = self._documents(project.id, admin_user.id)
        for doc in documents:
            db_session.add(doc)
        db_session.commit()

        fixed = datetime(2026, 10, 10, 4, 5, 6, tzinfo=timezone.utc)
        first = generate_delivery_zip(project, documents, generated_at=fixed)
        second = generate_delivery_zip(project, documents, generated_at=fixed)

        assert first == second, "生成時刻を固定しても ZIP がバイト同一にならない"
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            infos = archive.infolist()
        # ルートフォルダ名と INDEX の作成日が固定時刻に従う
        assert infos[0].filename.endswith("_20261010/INDEX.XML"), infos[0].filename
        # ZIP エントリの時刻が固定されている（ホストの時計・TZ に依存しない）
        assert {info.date_time for info in infos} == {(2026, 10, 10, 4, 5, 6)}, [
            info.date_time for info in infos
        ]

    def test_package_filename_is_deterministic_for_a_fixed_date(self):
        """ファイル名は同じ日付なら決定的（再現性の基準側）。"""
        from models.user import Project

        from services.electronic_delivery_service import package_filename

        project = Project(name="QA納品", code=f"QA-DEL-{uuid.uuid4().hex[:6]}")
        fixed = datetime(2026, 10, 10, tzinfo=timezone.utc)
        assert package_filename(project, fixed) == package_filename(project, fixed)
        assert package_filename(project, fixed).endswith("_20261010.zip")

    def test_zip_entries_are_reproducible_for_the_same_input(
        self, db_session, admin_user
    ):
        """同一入力の INDEX.XML（名称・件数・並び）は再生成しても同一である。

        生成時刻は固定せずに呼び出し、その範囲で決定的な部分（エントリ名の並び・
        ルートフォルダ名・INDEX.XML の中身）が再現することを固定する。生成時刻を
        固定した場合のバイト同一性は
        ``test_delivery_package_accepts_a_fixed_generated_at`` が検証する。
        """
        from models.user import Project
        from services.electronic_delivery_service import _sanitize_code

        project = Project(name="QA納品2", code=f"QA-DEL-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        documents = self._documents(project.id, admin_user.id)
        for doc in documents:
            db_session.add(doc)
        db_session.commit()

        def package_names() -> tuple[list[str], str]:
            payload = generate_delivery_zip(project, documents)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                index_entry = next(n for n in names if n.endswith("INDEX.XML"))
                return names, archive.read(index_entry).decode("utf-8")

        first_names, first_index = package_names()
        second_names, second_index = package_names()

        assert first_names == second_names, "ZIP のエントリ名・並びが再現しない"
        assert first_names[0].endswith("INDEX.XML"), first_names
        assert first_index == second_index, "INDEX.XML の内容が再現しない"

        expected_root = _sanitize_code(project.code)
        assert all(
            name.startswith(f"{expected_root}_") for name in first_names
        ), first_names
        assert any(name.endswith(".PDF") for name in first_names), first_names

    def _documents(self, project_id: str, owner_id: str) -> list:
        """Synthetic drawings/reports used by the delivery tests."""
        from models.document import Document, DocumentType

        return [
            Document(
                title="平面図",
                filename="plan.pdf",
                file_size=len(_pdf()),
                document_type=DocumentType.DRAWING,
                status=DocumentStatus.PENDING_REVIEW,
                project_id=project_id,
                owner_id=owner_id,
                tags=[],
                extra_data={},
            ),
            Document(
                title="報告書",
                filename="report.pdf",
                file_size=len(_pdf()),
                document_type=DocumentType.REPORT,
                status=DocumentStatus.PENDING_REVIEW,
                project_id=project_id,
                owner_id=owner_id,
                tags=[],
                extra_data={},
            ),
        ]

    def test_filenames_are_0018_padded_and_folder_scoped(self, db_session, admin_user):
        """連番は 4 桁ゼロ詰めで、フォルダごとに振られる（PHOT_0001 形式）。"""
        from models.user import Project

        project = Project(name="QA納品3", code=f"QA-DEL-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        documents = self._documents(project.id, admin_user.id)
        for doc in documents:
            db_session.add(doc)
        db_session.commit()

        payload = generate_delivery_zip(project, documents)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
        drawing_names = [n for n in names if "DRAW_" in n]
        assert drawing_names, names
        assert drawing_names[0].endswith("DRAW_0001.PDF"), drawing_names

    def test_index_xml_file_count_matches_the_packaged_files(
        self, db_session, admin_user
    ):
        """INDEX.XML のファイル数が、実際に同梱された PDF 数と一致する。"""
        from models.user import Project

        project = Project(name="QA納品4", code=f"QA-DEL-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        documents = self._documents(project.id, admin_user.id)
        for doc in documents:
            db_session.add(doc)
        db_session.commit()

        payload = generate_delivery_zip(project, documents)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            index_entry = next(n for n in names if n.endswith("INDEX.XML"))
            index_xml = archive.read(index_entry).decode("utf-8")
            payload_entries = [n for n in names if not n.endswith("INDEX.XML")]

        counts = [
            int(m) for m in __import__("re").findall(r'ファイル数="(\d+)"', index_xml)
        ]
        assert counts, f"INDEX.XML にファイル数が無い: {index_xml[:200]}"
        assert sum(counts) == len(payload_entries), (counts, payload_entries)


# ── 3. 保持期限の決定性（計算再現性） ─────────────────────────────────────────


class TestRetentionArithmetic:
    """docs/requirements.md §3.2.6 WEB-AUDIT-005 / 電子帳簿保存法の区分別保持。"""

    def test_expiry_is_counted_in_calendar_years(self):
        """保持期限は暦年（同じ月日）で計算される（保有日数を1日も短くしない）。

        以前は「作成日 + 365日 × 年数」で、うるう日を跨ぐごとに期限が1日ずつ
        短くなっていた（7年で最大2日）。B-2 の決定と整合させるため暦年に統一した。
        """
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert retention_service.calculate_expiry(created, 7) == created.replace(
            year=2033
        )
        assert retention_service.calculate_expiry(created, 10) == created.replace(
            year=2036
        )

    def test_permanent_and_immediate_policies(self):
        """永続（-1）は期限なし、目的達成後速やか（0）は作成時刻で失効する。"""
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert retention_service.calculate_expiry(created, -1) is None
        assert retention_service.calculate_expiry(created, 7, is_permanent=True) is None
        assert retention_service.calculate_expiry(created, 0) == created

    def test_leap_day_start_moves_forward_not_backward(self):
        """2/29 起点で対象年がうるう年でない場合は 3/1 へ進める（短くしない）。

        2028-02-29 + 1年 は 2029-02-29 が存在しないため 2029-03-01 とする。
        365日後（2029-02-28）より後ろになり、暦年を下回らないことを固定する。
        """
        leap_start = datetime(2028, 2, 29, tzinfo=timezone.utc)
        expiry = retention_service.calculate_expiry(leap_start, 1)
        assert expiry == leap_start.replace(year=2029, month=3, day=1)
        assert expiry.date().isoformat() == "2029-03-01"
        assert (expiry - leap_start) >= timedelta(days=365)


# ── 4. 監査証跡（承認と納品） ────────────────────────────────────────────────


class TestAuditTrailOfBusinessActions:
    """docs/requirements.md §3.2.6 WEB-AUDIT-001/006（追記 + SHA-256 チェーン）。"""

    def test_approval_and_delivery_are_recorded_and_chain_verifies(
        self, client, admin_token
    ):
        """承認・納品の操作が監査ログに載り、ハッシュチェーンが検証できる。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "証跡確認")
        _approve_fully(client, admin_token, doc_id)

        generated = client.post(
            f"/api/v1/projects/{project_id}/electronic-delivery",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert generated.status_code == 200, generated.text

        actions = {
            entry["action"]
            for entry in client.get(
                "/api/v1/audit-logs/",
                params={"per_page": 200},
                headers={"Authorization": f"Bearer {admin_token}"},
            ).json()["items"]
        }
        assert "workflow.created" in actions
        assert "workflow.step.decided" in actions
        assert "electronic_delivery.generated" in actions

        verified = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["chain_valid"] is True

    def test_audit_chain_detects_a_modified_record(
        self, client, admin_token, db_session
    ):
        """監査レコードを書き換えるとチェーン検証が失敗する（改竄検知）。"""
        from models.audit_log import AuditLog

        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "改竄検知")
        _approve_fully(client, admin_token, doc_id)

        target = (
            db_session.query(AuditLog)
            .filter(AuditLog.sequence_number.isnot(None))
            .order_by(AuditLog.sequence_number.asc())
            .first()
        )
        assert target is not None, "チェーン対象の監査ログが無い"
        target.detail = json.dumps({"tampered": True})
        db_session.commit()

        verified = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["chain_valid"] is False
        assert verified.json()["first_broken_sequence"] is not None


# ── 5. 権限境界（メンバーシップで守られているか） ────────────────────────────


class TestRoleBoundariesAreEnforcedByMembership:
    """docs/requirements.md §3.2.4 WEB-DOC-010（プロジェクトメンバー以外は 404 秘匿）."""

    def test_project_member_engineer_can_read_but_not_delete_others_document(
        self, client, admin_token
    ):
        """可視性はメンバーシップで与えられ、削除権限はそれとは別に制限される。

        「非メンバーだから 404」は権限チェックの証明にならない（可視性の
        副作用）。メンバーである第三者に対して、読み取りは許可・削除は拒否と
        いう境界を明示的に検証する。
        """
        project_id = _create_project(client, admin_token)
        engineer_id, engineer_token = _create_user(client, admin_token, "engineer")
        _add_member(client, admin_token, project_id, engineer_id)
        doc_id = _upload(client, admin_token, project_id, "他人の文書")

        readable = client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert readable.status_code == 200, readable.text

        # 所有者でも manager/admin でもないメンバーは削除できない（403）。
        deleted = client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert deleted.status_code == 403, deleted.text
        # 権限の無い操作で状態が変わっていないこと（アップロード直後は draft）。
        assert _status_raw(client, admin_token, doc_id) == "draft"

        # 同じメンバーは復元もできない（削除と同じ判定）。
        restored = client.post(
            f"/api/v1/documents/{doc_id}/restore",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert restored.status_code == 403, restored.text

    def test_owner_and_manager_can_delete_and_restore(self, client, admin_token):
        """所有者本人と manager は削除・復元できる（正当な操作は妨げない）。"""
        project_id = _create_project(client, admin_token)
        engineer_id, engineer_token = _create_user(client, admin_token, "engineer")
        _add_member(client, admin_token, project_id, engineer_id)

        # 所有者本人が自分の文書を削除 → 復元
        own_doc = _upload(client, engineer_token, project_id, "自分の文書")
        deleted = client.delete(
            f"/api/v1/documents/{own_doc}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert deleted.status_code == 204, deleted.text
        assert _status_raw(client, admin_token, own_doc) == "archived"
        restored = client.post(
            f"/api/v1/documents/{own_doc}/restore",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert restored.status_code == 200, restored.text

        # manager は自分の文書を削除・復元できる（§5.2 文書削除: admin=全て,
        # manager/engineer=自分）。他者の文書の削除・復元は §5.2 でも不可
        # （test_qa_authz_workflow.py::test_cannot_delete_others_document を参照）。
        manager_id, manager_token = _create_user(client, admin_token, "manager")
        manager_doc = _upload(client, manager_token, project_id, "managerの文書")
        deleted = client.delete(
            f"/api/v1/documents/{manager_doc}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert deleted.status_code == 204, deleted.text
        restored = client.post(
            f"/api/v1/documents/{manager_doc}/restore",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert restored.status_code == 200, restored.text
        assert manager_id  # 参照保持


def _status_raw(client, token: str, doc_id: str) -> str:
    """Return the document status whether it is active or in the trash."""
    resp = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 200:
        return resp.json()["status"]
    resp = client.get(
        "/api/v1/documents/trash",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    for entry in resp.json():
        if entry["id"] == doc_id:
            return entry["status"]
    raise AssertionError(f"document {doc_id} found in neither active nor trash")

    def test_non_member_cannot_even_see_the_document(self, client, admin_token):
        """プロジェクト外の利用者には 404（存在を秘匿する）。"""
        project_id = _create_project(client, admin_token)
        _outsider_id, outsider_token = _create_user(client, admin_token, "engineer")
        doc_id = _upload(client, admin_token, project_id, "部外秘")

        resp = client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {outsider_token}"},
        )
        assert resp.status_code == 404, resp.text


# ── 6. AI 利用時の人確認境界 ─────────────────────────────────────────────────


@pytest.fixture
def _ai_enabled(db_session):
    """This class exercises AI behaviour, so the admin kill switch is on."""
    from services import ai_settings as ai_settings_service

    ai_settings_service.update_ai_setting(db_session, enabled=True)


class TestAiStaysAdvisory:
    """docs/requirements.md §6.4 AI利用ポリシー — AI は候補提示までで確定しない。"""

    def _document_with_text(self, db_session, admin_user, project_id: str) -> str:
        from models.document import Document, DocumentType

        doc = Document(
            title="QA平面図.pdf",
            filename="qa_plan.pdf",
            file_size=len(_pdf()),
            document_type=DocumentType.OTHER,
            status=DocumentStatus.DRAFT,
            project_id=project_id,
            owner_id=admin_user.id,
            ocr_text="平面図 1:100 建物配置図 工事名: QAテスト工事",
            tags=[],
            extra_data={},
        )
        db_session.add(doc)
        db_session.commit()
        return doc.id

    def test_classification_is_advisory_and_never_writes_type_or_status(
        self, client, admin_token, admin_user, db_session, _ai_enabled
    ):
        """AI 分類はタグと extra_data に候補を残すだけで、種別・状態を変えない。

        種別は電子納品の構成、状態は承認可否を決める。AI が直接書けると
        「人の確認を通らない確定処理」になるため、ここを固定する。
        """
        from models.document import Document

        project_id = _create_project(client, admin_token)
        doc_id = self._document_with_text(db_session, admin_user, project_id)
        before_type = db_session.get(Document, doc_id).document_type

        message = MagicMock()
        message.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "drawing_type": "平面図",
                        "project_type": "土木",
                        "confidence": 0.91,
                        "reasoning": "QAスタブ",
                    }
                )
            )
        ]
        with patch("api.ai._get_anthropic_client") as client_fn:
            stub = MagicMock()
            stub.messages.create.return_value = message
            client_fn.return_value = stub
            resp = client.post(
                f"/api/v1/ai/documents/{doc_id}/classify",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        doc = db_session.get(Document, doc_id)
        # 種別は人間が確定するまで変わらない。
        assert doc.document_type == before_type
        # 承認状態も変わらない（AI は承認しない）。
        assert doc.status == DocumentStatus.DRAFT
        # 候補はタグと構造化データに残る（人が確認できる形）。
        assert "ai分類済" in (doc.tags or [])
        assert any(str(tag).startswith("図面:") for tag in (doc.tags or []))
        stored = (doc.extra_data or {}).get("ai_classification")
        assert stored is not None
        assert stored["drawing_type"] == "平面図"
        assert stored["confidence"] == pytest.approx(0.91)
        assert stored["model"]

    def test_ai_cannot_approve_a_document(
        self, client, admin_token, admin_user, db_session, _ai_enabled
    ):
        """AI 経路ではワークフローが作られず、文書も承認されない。"""
        from models.document import Document
        from models.document import ApprovalWorkflow

        project_id = _create_project(client, admin_token)
        doc_id = self._document_with_text(db_session, admin_user, project_id)

        message = MagicMock()
        message.content = [MagicMock(text=json.dumps({"drawing_type": "平面図"}))]
        with patch("api.ai._get_anthropic_client") as client_fn:
            stub = MagicMock()
            stub.messages.create.return_value = message
            client_fn.return_value = stub
            for method, path in (
                ("post", "classify"),
                ("post", "extract"),
                ("get", "summary"),
            ):
                resp = getattr(client, method)(
                    f"/api/v1/ai/documents/{doc_id}/{path}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert resp.status_code == 200, (path, resp.text)

        db_session.expire_all()
        assert db_session.get(Document, doc_id).status == DocumentStatus.DRAFT
        assert (
            db_session.query(ApprovalWorkflow)
            .filter(ApprovalWorkflow.document_id == doc_id)
            .count()
            == 0
        )


# ── 7. 追加で欠落していた境界（Agent の棚卸し結果より） ──────────────────────


class TestRejectionAndResubmissionEvidence:
    """WEB-WF-002（却下）／WEB-WF-005（再申請）の証跡と状態遷移。"""

    def test_rejection_sets_both_workflow_and_document_status(
        self, client, admin_token
    ):
        """却下はワークフローと文書の双方を rejected にし、終端させる。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "却下対象")
        created = client.post(
            "/api/v1/workflows/",
            json={
                "document_id": doc_id,
                "approver_ids": [_admin_id(client, admin_token)],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 201, created.text
        step_id = created.json()["steps"][0]["id"]

        rejected = client.post(
            f"/api/v1/workflows/{created.json()['id']}/steps/{step_id}/decide",
            json={"decision": "reject", "comment": "数量表の根拠が不足"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"
        assert rejected.json()["completed_at"] is not None
        assert _status(client, admin_token, doc_id) == "rejected"

        # 却下は終端であり、再申請（resubmit）は returned 以外を受け付けない。
        resubmit = client.post(
            f"/api/v1/workflows/{created.json()['id']}/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resubmit.status_code == 409, resubmit.text

    def test_resubmission_is_recorded_under_its_own_audit_action(
        self, client, admin_token
    ):
        """再申請は workflow.resubmitted として監査に残る（差戻し→再申請の往復）。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "再申請の証跡")
        created = client.post(
            "/api/v1/workflows/",
            json={
                "document_id": doc_id,
                "approver_ids": [_admin_id(client, admin_token)],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = created.json()["id"]
        step_id = created.json()["steps"][0]["id"]
        auth = {"Authorization": f"Bearer {admin_token}"}

        returned = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "図面番号を修正"},
            headers=auth,
        )
        assert returned.status_code == 200, returned.text
        resumed = client.post(f"/api/v1/workflows/{workflow_id}/resubmit", headers=auth)
        assert resumed.status_code == 200, resumed.text

        actions = [
            entry["action"]
            for entry in client.get(
                "/api/v1/audit-logs/",
                params={"action": "workflow.resubmitted"},
                headers=auth,
            ).json()["items"]
        ]
        assert actions, "workflow.resubmitted が監査ログに記録されていない"


class TestManagerCrossProjectVisibility:
    """access_control.can_access_all は manager を含む（§3.2.4 WEB-DOC-010 の境界）。"""

    def test_manager_sees_documents_of_a_project_they_do_not_belong_to(
        self, client, admin_token
    ):
        """manager は非メンバーのプロジェクト文書も閲覧できる（A-1 の仕様）。

        §5.2「プロジェクト参照」「文書参照」は manager を「全て」と定める。以前は
        文書側だけが全件で、一覧（`api/projects.py`）は admin のみ全件という非対称が
        あったが、A-1（2026-10-03 決定）で一覧も manager に全件を返すように統一した。
        """
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "他部署の図面")
        manager_id, manager_token = _create_user(client, admin_token, "manager")

        # メンバーではない manager でも文書は読める
        readable = client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert readable.status_code == 200, readable.text

        # プロジェクト一覧にも出る（A-1: admin / manager は全案件）
        listing = client.get(
            "/api/v1/projects/", headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert listing.status_code == 200, listing.text
        assert project_id in {entry["id"] for entry in listing.json()}
        assert manager_id  # 参照保持（未使用警告の回避）


class TestRevisionEvidence:
    """WEB-DOC-003（版管理: 版数管理・旧版参照・変更メモ）の証跡境界。"""

    def _upload_revision(self, client, token, doc_id, note: str):
        return client.post(
            f"/api/v1/documents/{doc_id}/revisions",
            data={"revision": "A", "revision_note": note},
            files={"file": ("rev.pdf", io.BytesIO(_pdf()), "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_revision_metadata_is_recorded_in_order(self, client, admin_token):
        """版は連番で記録され、変更メモが参照できる（メタデータの証跡）。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "版管理対象")

        first = self._upload_revision(client, admin_token, doc_id, "初版")
        second = self._upload_revision(client, admin_token, doc_id, "修正版")
        assert first.status_code in (200, 201), first.text
        assert second.status_code in (200, 201), second.text

        listing = client.get(
            f"/api/v1/documents/{doc_id}/revisions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert listing.status_code == 200, listing.text
        versions = listing.json()
        numbers = [entry["version_number"] for entry in versions]
        assert numbers == sorted(numbers), numbers
        assert len(set(numbers)) == len(
            numbers
        ), "同一文書内で版番号が重複した（採番が max+1 のため UNIQUE 制約が無い）"
        assert any(entry.get("revision_note") == "修正版" for entry in versions)

    def test_revision_bytes_are_persisted_and_retrievable(
        self, client, admin_token, db_session
    ):
        """版の PDF 実体が保存され、版番号を指定して取得できる（旧版参照）。

        `api/revisions.py` は以前ファイル内容を検証するだけで書き出さず、
        `DocumentVersion.file_path` も設定していなかった。監査ログには版番号が
        残るのに実体が存在しない状態だったため、ここで実体の永続化と取得を固定する。
        """
        from models.document import DocumentVersion

        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "版の実体")
        uploaded = self._upload_revision(client, admin_token, doc_id, "実体確認")
        assert uploaded.status_code in (200, 201), uploaded.text

        db_session.expire_all()
        version = (
            db_session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        assert version is not None
        assert version.file_path, "リビジョンの実体パスが記録されていない"
        stored = __import__("pathlib").Path(version.file_path)
        assert stored.exists(), f"リビジョンの実体が保存されていない: {stored}"
        assert stored.read_bytes() == _pdf()

        fetched = client.get(
            f"/api/v1/documents/{doc_id}/revisions/{version.version_number}/download",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.content == _pdf(), "取得した旧版の内容が一致しない"

    def test_unknown_revision_download_is_404(self, client, admin_token):
        """存在しない版番号の取得は 404。"""
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "版なし")
        resp = client.get(
            f"/api/v1/documents/{doc_id}/revisions/99/download",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404, resp.text


class TestVersionNumberUniqueness:
    """版番号の一意性（DB 制約）— WEB-DOC-003 の前提。"""

    def test_same_version_number_cannot_be_inserted_twice(
        self, client, admin_token, db_session
    ):
        """同一文書・同一版番号の重複挿入は DB 制約で拒否される。

        採番は ``max(version_number) + 1`` のため、同時アップロードでは同じ番号を
        2 行に書けてしまう。監査ログには版番号が残るので、重複すると
        「どの版がどれか」を証明できなくなる。
        """
        from sqlalchemy.exc import IntegrityError

        from models.document import DocumentVersion

        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "版番号の一意性")
        resp = self._upload_revision(client, admin_token, doc_id, "初版")
        assert resp.status_code in (200, 201), resp.text

        db_session.expire_all()
        existing = (
            db_session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .first()
        )
        assert existing is not None
        duplicate = DocumentVersion(
            document_id=doc_id,
            version_number=existing.version_number,
            filename="dup.pdf",
            file_size=1,
            created_by=existing.created_by,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def _upload_revision(self, client, token, doc_id, note: str):
        return client.post(
            f"/api/v1/documents/{doc_id}/revisions",
            data={"revision": "A", "revision_note": note},
            files={"file": ("rev.pdf", io.BytesIO(_pdf()), "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )


# ── 8. 承認後の変更統制（第2バッチ） ─────────────────────────────────────────


_SIDECAR = {
    "schema": "civilpdf.review/v1",
    "generator": "CivilPDF-Editor",
    "savedAt": "2026-06-21T10:05:00Z",
    "stamps": [{"id": "s1", "page": 1, "status": "approved"}],
    "annotations": [],
}


class TestApprovedDocumentImmutability:
    """承認済み文書は納品物と承認記録の基準になるため、後から書き換えられない。"""

    def test_document_type_is_fixed_after_approval(self, client, admin_token):
        """承認後に種別を変えようとすると 409（納品フォルダが変わるため）。

        `_FOLDER_MAP` が DocumentType から納品先フォルダと接頭辞を決めるので、
        承認後の種別変更は「過去に納品した中身」を書き換えるのと同じ意味を持つ。
        """
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "承認済み図面")
        _approve_fully(client, admin_token, doc_id)

        blocked = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"document_type": "photo"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert blocked.status_code == 409, blocked.text
        # 種別が変わっていないこと
        assert (
            client.get(
                f"/api/v1/documents/{doc_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            ).json()["document_type"]
            != "photo"
        )

        # 承認後でも title の訂正（誤字等）は妨げない
        renamed = client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"title": "承認済み図面（改題）"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert renamed.status_code == 200, renamed.text

    def test_review_sidecar_import_is_blocked_after_approval(
        self, client, admin_token, db_session, admin_user
    ):
        """承認済み文書への sidecar 取込は 409（status を巻き戻させない）。

        `api/editor.py` は sidecar 取込で `doc.status` を EDITOR_DRAFT /
        EDITOR_REVIEWED に上書きする。承認済み文書でこれを許すと、承認記録は
        approved のまま文書だけが下書きに戻る不整合が生じる。
        """
        from models.document import Document
        from models.user import Project

        project = Project(name="QA承認後", code=f"QA-APR-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        doc = Document(
            title="承認済み（sidecar）",
            filename="approved.pdf",
            file_size=len(_pdf()),
            status=DocumentStatus.APPROVED,
            project_id=project.id,
            owner_id=admin_user.id,
            tags=[],
            extra_data={},
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=_SIDECAR,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409, resp.text
        db_session.expire_all()
        assert (
            db_session.query(Document).filter(Document.id == doc.id).first().status
            == DocumentStatus.APPROVED
        )

    def test_review_sidecar_still_works_before_approval(
        self, client, admin_token, db_session, admin_user
    ):
        """未承認（draft）の文書では sidecar 取込は従来どおり動く。"""
        from models.document import Document
        from models.user import Project

        project = Project(name="QA下書き", code=f"QA-DRF-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        doc = Document(
            title="下書き（sidecar）",
            filename="draft.pdf",
            file_size=len(_pdf()),
            status=DocumentStatus.DRAFT,
            project_id=project.id,
            owner_id=admin_user.id,
            tags=[],
            extra_data={},
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=_SIDECAR,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (200, 201), resp.text


class TestSuspendedAccount:
    """WEB-USER-003: suspended は inactive と同様に認証・操作を拒否する。"""

    def test_suspended_user_cannot_authenticate(self, client, admin_token, db_session):
        from auth.jwt import get_password_hash
        from models.user import User, UserRole, UserStatus

        user = User(
            email=f"susp-{uuid.uuid4().hex[:8]}@example.com",
            username=f"susp-{uuid.uuid4().hex[:8]}",
            full_name="Suspended QA",
            hashed_password=get_password_hash("Suspended123!"),
            role=UserRole.ENGINEER,
            status=UserStatus.SUSPENDED,
        )
        db_session.add(user)
        db_session.commit()

        resp = client.post(
            "/api/v1/auth/token",
            data={"username": user.email, "password": "Suspended123!"},
        )
        assert resp.status_code in (401, 403), resp.text

    def test_suspended_user_token_is_rejected(self, client, admin_token, db_session):
        """既に発行済みのトークンでも、停止後は 403 になる。"""
        from auth.jwt import create_access_token, get_password_hash
        from models.user import User, UserRole, UserStatus

        user = User(
            email=f"susp2-{uuid.uuid4().hex[:8]}@example.com",
            username=f"susp2-{uuid.uuid4().hex[:8]}",
            full_name="Suspended QA 2",
            hashed_password=get_password_hash("Suspended123!"),
            role=UserRole.ENGINEER,
            status=UserStatus.ACTIVE,
        )
        db_session.add(user)
        db_session.commit()

        token = create_access_token(
            {"sub": user.id, "email": user.email, "role": user.role.value}
        )
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )

        user.status = UserStatus.SUSPENDED
        db_session.commit()
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403, resp.text


class TestDuplicateApproverIsAcceptedAsConfigured:
    """WEB-WF-001: 同一人物を複数ステップに指定できる（現行仕様の記録）。"""

    def test_same_user_can_hold_two_steps(self, client, admin_token):
        """現在は重複を検査しない。多段統制の実効性は運用側の判断事項。

        実装は `approver_ids` の重複を弾かないため、1 人で全ステップを承認でき
        多段承認が形骸化し得る。ここでは現状を固定し、仕様判断が必要な点として
        残す（禁止にするなら 400 を返す実装変更が必要）。
        """
        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "多重ステップ")
        admin = _admin_id(client, admin_token)
        created = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin, admin]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 201, created.text
        steps = created.json()["steps"]
        assert len(steps) == 2
        assert len({step["approver_id"] for step in steps}) == 1, (
            "重複が拒否されるようになった場合は実装が変わったので、このテストを"
            "409/400 の期待へ更新すること"
        )


class TestFlattenReachesFinalized:
    """Editor 連携: flatten チェック成功で FINALIZED に到達する（確定状態）。"""

    def test_successful_flatten_marks_document_finalized(
        self, client, admin_token, db_session, admin_user
    ):
        from models.document import Document
        from models.user import Project

        project = Project(name="QA確定", code=f"QA-FIN-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        pdf_path = (
            __import__("pathlib").Path(
                __import__("tempfile").mkdtemp(prefix="qa-flatten-")
            )
            / "flat.pdf"
        )
        pdf_path.write_bytes(_parseable_pdf())
        doc = Document(
            title="平坦化対象",
            filename="flat.pdf",
            file_path=str(pdf_path),
            file_size=len(_parseable_pdf()),
            status=DocumentStatus.EDITOR_REVIEWED,
            project_id=project.id,
            owner_id=admin_user.id,
            tags=[],
            extra_data={},
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.post(
            f"/api/v1/documents/{doc.id}/flatten-check",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        refreshed = db_session.query(Document).filter(Document.id == doc.id).first()
        assert refreshed.status == DocumentStatus.FINALIZED
        assert refreshed.is_flattened is True
        assert refreshed.flattened_hash


class TestRevisionNumberingUnderRace:
    """版番号の採番は競合しても一意な番号に収束する（(document_id, version_number) 一意）。"""

    def test_upload_recovers_when_a_concurrent_insert_takes_the_number(
        self, client, admin_token, db_session
    ):
        """SELECT と INSERT の間に他者が同じ番号を取った場合、再採番して成功する。"""
        from models.document import DocumentVersion

        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "採番競合")

        # A concurrent upload already committed version 1. The API's max()+1 still
        # reads 1, so its insert hits uq_document_versions_number.
        db_session.add(
            DocumentVersion(
                document_id=doc_id,
                version_number=1,
                filename="concurrent.pdf",
                file_size=1,
                created_by=_admin_id(client, admin_token),
            )
        )
        db_session.commit()

        resp = client.post(
            f"/api/v1/documents/{doc_id}/revisions",
            data={"revision": "A", "revision_note": "競合テスト"},
            files={"file": ("rev.pdf", io.BytesIO(_pdf()), "application/pdf")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (200, 201), resp.text

        db_session.expire_all()
        rows = (
            db_session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.asc())
            .all()
        )
        numbers = [v.version_number for v in rows]
        assert numbers == [1, 2], numbers
        # The retried row must point at stored bytes.
        assert rows[1].file_path, "再採番された版の実体が保存されていない"


class TestIndexXmlCarriesRevisionAndIso19650:
    """INDEX.XML が版と ISO 19650 メタデータを成果品情報に含める。"""

    def _documents(self, project_id: str, owner_id: str) -> list:
        from models.document import Document, DocumentType

        return [
            Document(
                title="平面図",
                filename="plan.pdf",
                file_size=len(_pdf()),
                document_type=DocumentType.DRAWING,
                status=DocumentStatus.APPROVED,
                project_id=project_id,
                owner_id=owner_id,
                revision="A3",
                revision_note="数量表修正",
                iso19650_originator="ABC",
                iso19650_functional_breakdown="00",
                iso19650_form="DR",
                iso19650_discipline="ST",
                iso19650_number="0001",
                tags=[],
                extra_data={},
            )
        ]

    def test_index_xml_includes_revision_and_iso_fields(self, db_session, admin_user):
        from models.user import Project

        project = Project(name="QA納品版", code=f"QA-IDX-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        documents = self._documents(project.id, admin_user.id)
        for doc in documents:
            db_session.add(doc)
        db_session.commit()

        payload = generate_delivery_zip(
            project,
            documents,
            generated_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            index_entry = next(n for n in archive.namelist() if n.endswith("INDEX.XML"))
            index_xml = archive.read(index_entry).decode("utf-8")

        assert "<版>A3</版>" in index_xml, index_xml
        assert "平面図（A3）" in index_xml, index_xml
        assert "<ISO19650情報>" in index_xml, index_xml
        assert "<作成者コード>ABC</作成者コード>" in index_xml
        assert "<分野コード>ST</分野コード>" in index_xml
        assert "<連番>0001</連番>" in index_xml

    def test_index_xml_stays_unchanged_without_iso_metadata(
        self, db_session, admin_user
    ):
        """ISO 19650 情報が無い文書では ISO19650情報 要素を作らない。"""
        from models.document import Document, DocumentType
        from models.user import Project

        project = Project(name="QA納品素", code=f"QA-IDX-{uuid.uuid4().hex[:6]}")
        db_session.add(project)
        db_session.flush()
        doc = Document(
            title="報告書",
            filename="report.pdf",
            file_size=len(_pdf()),
            document_type=DocumentType.REPORT,
            status=DocumentStatus.APPROVED,
            project_id=project.id,
            owner_id=admin_user.id,
            tags=[],
            extra_data={},
        )
        db_session.add(doc)
        db_session.commit()

        payload = generate_delivery_zip(
            project,
            [doc],
            generated_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            index_entry = next(n for n in archive.namelist() if n.endswith("INDEX.XML"))
            index_xml = archive.read(index_entry).decode("utf-8")

        assert "<ISO19650情報>" not in index_xml, index_xml
        assert "<版 />" in index_xml, index_xml
        assert "報告書" in index_xml


class TestCriticalConfigChangesAreAudited:
    """設定変更（AI 有効化・API キー・M365 資格情報）が改ざん検知対象に残る。"""

    def test_ai_config_update_is_chained_and_never_records_the_key(
        self, client, admin_token, db_session
    ):
        from models.audit_log import AuditLog

        secret = "sk-ant-qa-should-never-be-logged"
        resp = client.put(
            "/api/v1/ai-config",
            json={"enabled": True, "model_name": "claude-qa", "api_key": secret},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "ai.config.updated")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert entry is not None, "AI 設定変更が監査に記録されていない"
        assert entry.sequence_number is not None, "未連鎖の行として記録されている"
        detail = entry.detail or ""
        assert secret not in detail, "API キーの値が監査ログに記録されている"
        assert '"api_key_changed": true' in detail, detail
        assert '"enabled": true' in detail, detail

    def test_m365_config_update_is_chained_and_never_records_the_secret(
        self, client, admin_token, db_session
    ):
        from models.audit_log import AuditLog

        secret = "qa-client-secret-never-logged"
        resp = client.put(
            "/api/v1/m365/config",
            json={
                "tenant_id": "qa-tenant",
                "client_id": "qa-client",
                "client_secret": secret,
                "enabled": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "m365.config.updated")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert entry is not None, "M365 設定変更が監査に記録されていない"
        assert entry.sequence_number is not None, "未連鎖の行として記録されている"
        detail = entry.detail or ""
        assert (
            secret not in detail
        ), "クライアントシークレットが監査ログに記録されている"
        assert '"client_secret_changed": true' in detail, detail


class TestAuditChainReportsUnchainedRows:
    """verify_chain は「連鎖していない行」を隠さず件数で返す。"""

    def test_unchained_rows_are_counted(self, client, admin_token, db_session):
        from models.audit_log import AuditLog

        project_id = _create_project(client, admin_token)
        doc_id = _upload(client, admin_token, project_id, "未連鎖の検出")
        _approve_fully(client, admin_token, doc_id)

        before = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert before["chain_valid"] is True
        assert before["unchained_records"] == 0, before

        # A row that never entered the chain (legacy shape) must be visible.
        db_session.add(
            AuditLog(
                user_id=None,
                action="legacy.unlinked",
                resource_type="auth",
                detail="{}",
                ip_address=None,
            )
        )
        db_session.commit()

        after = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert after["chain_valid"] is True, "連鎖行そのものは壊れていない"
        assert after["unchained_records"] == 1, after


class TestSsoLoginsEnterTheHashChain:
    """SSO（M365/OIDC）の認証行がハッシュチェーンに入る。"""

    def test_m365_login_failure_is_chained(self, client, admin_token, db_session):
        from models.audit_log import AuditLog

        resp = client.post(
            "/api/v1/auth/m365/login",
            json={"email": "qa-chain@example.com"},
        )
        # The bridge is deny-by-default for networks it cannot verify; either way
        # the attempt is recorded (409/403/503 are all "not logged in").
        assert resp.status_code != 200, resp.text

        db_session.expire_all()
        rows = db_session.query(AuditLog).filter(AuditLog.action.like("m365_%")).all()
        assert rows, "M365 ログイン試行が監査に記録されていない"
        assert all(
            row.sequence_number is not None for row in rows
        ), "M365 認証行が未連鎖のまま記録されている"

        verified = client.get(
            "/api/v1/audit-logs/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert verified["chain_valid"] is True, verified

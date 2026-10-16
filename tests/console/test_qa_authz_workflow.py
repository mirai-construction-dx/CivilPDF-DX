"""QA: 案件境界・RBAC・承認ワークフロー・削除/復元の仕様適合テスト.

仕様の根拠は docs/requirements.md (v1.1.0。テスト中の「行xx」は v1.0.0 時点の
行番号で、v1.1.0 では節の名前で参照すること):
- §3.2.4 WEB-DOC-005 / WEB-DOC-010
- §3.2.5 承認ワークフロー
- §5.2 RBAC 権限マトリクス
- §9.2 AT-DOC-005 / AT-DOC-006
- §9.3 AT-WF-001〜007
- src/console/backend/services/access_control.py 冒頭コメント
  (権限外リソースは 403 ではなく 404 で秘匿する)

仕様と実装が食い違う箇所は、期待値を仕様どおりに書いたうえで
``xfail(strict=True)`` を付けている (修正されると XPASS で失敗し気づける)。
2026-10-03 のユーザー決定 (requirements.md §5.2 注記 A-1/A-2/A-3, ※1〜※3,
WEB-DOC-005 決定事項 B-4/C-1/C-2, AT-DOC-005 D-3) で確定した点は、確定
仕様を期待する通常テストにしている。admin を承認者にできる点も 2026-10-03 に
決定済み (§5.2 ※2)。このファイルに xfail は残っていない。
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from auth.jwt import get_password_hash
from models.audit_log import AuditLog
from models.document import Document
from models.user import User, UserRole, UserStatus

API = "/api/v1"


# ─── helpers ──────────────────────────────────────────────────────────────


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _new_user(db_session, client, role: UserRole, name: str) -> tuple[str, str]:
    """Create an extra active user directly in the DB and log in.

    Returns (user_id, access_token).
    """
    password = f"Qa{name.capitalize()}Pass123"
    user = User(
        email=f"{name}@qa.example.com",
        username=name,
        full_name=f"QA {name}",
        hashed_password=get_password_hash(password),
        role=role,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    resp = client.post(
        f"{API}/auth/token",
        data={"username": user.email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return user.id, resp.json()["access_token"]


def _create_project(client, admin_token: str, name: str = "QA案件") -> str:
    resp = client.post(
        f"{API}/projects/",
        json={"name": name, "code": f"QA-{uuid.uuid4().hex[:8].upper()}"},
        headers=_h(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_member(client, admin_token: str, project_id: str, user_id: str) -> None:
    resp = client.post(
        f"{API}/projects/{project_id}/members/{user_id}", headers=_h(admin_token)
    )
    assert resp.status_code == 204, resp.text


def _upload(client, token: str, project_id: str, title: str = "図面"):
    return client.post(
        f"{API}/documents/",
        data={"project_id": project_id, "title": title},
        files={"file": (f"{title}.pdf", io.BytesIO(_pdf()), "application/pdf")},
        headers=_h(token),
    )


def _upload_ok(client, token: str, project_id: str, title: str = "図面") -> str:
    resp = _upload(client, token, project_id, title)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_wf(client, token: str, doc_id: str, approver_ids: list[str]):
    return client.post(
        f"{API}/workflows/",
        json={"document_id": doc_id, "approver_ids": approver_ids},
        headers=_h(token),
    )


def _decide(client, token, wf_id, step_id, decision="approve", comment=None):
    body = {"decision": decision}
    if comment is not None:
        body["comment"] = comment
    return client.post(
        f"{API}/workflows/{wf_id}/steps/{step_id}/decide",
        json=body,
        headers=_h(token),
    )


def _doc_ids(client, token: str, **params) -> set[str]:
    resp = client.get(f"{API}/documents/", params=params, headers=_h(token))
    assert resp.status_code == 200, resp.text
    return {d["id"] for d in resp.json()}


def _trash_ids(client, token: str) -> set[str]:
    resp = client.get(f"{API}/documents/trash", headers=_h(token))
    assert resp.status_code == 200, resp.text
    return {d["id"] for d in resp.json()}


def _doc_status(client, admin_token: str, doc_id: str) -> str:
    resp = client.get(f"{API}/documents/{doc_id}", headers=_h(admin_token))
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


@pytest.fixture
def two_projects(client, admin_token, engineer_user, viewer_user, manager_user):
    """案件A (engineer/viewer がメンバー) と案件B (メンバーなし) を用意する.

    案件Bには admin がアップロードした文書とワークフローを置く。
    承認者は案件Bの文書を閲覧できる manager (A-1: 全案件閲覧可, A-3)。
    """
    pa = _create_project(client, admin_token, "案件A")
    pb = _create_project(client, admin_token, "案件B")
    _add_member(client, admin_token, pa, engineer_user.id)
    _add_member(client, admin_token, pa, viewer_user.id)
    doc_a = _upload_ok(client, admin_token, pa, "案件A図面")
    doc_b = _upload_ok(client, admin_token, pb, "案件B機密図面")
    wf = _create_wf(client, admin_token, doc_b, [manager_user.id])
    assert wf.status_code == 201, wf.text
    return {
        "pa": pa,
        "pb": pb,
        "doc_a": doc_a,
        "doc_b": doc_b,
        "wf_b": wf.json()["id"],
    }


# ─── A. 案件境界とデータ分離 ───────────────────────────────────────────────


class TestProjectBoundary:
    @pytest.mark.parametrize("role", ["engineer", "viewer"])
    def test_member_of_a_cannot_reach_project_b_resources(
        self, request, client, two_projects, role
    ):
        """WEB-DOC-010 / §5.2「文書参照（所属PJ）」/ access_control.py 404秘匿.

        期待: 案件Aメンバー (engineer/viewer) から案件Bの文書は一覧に出ず、
        詳細・ダウンロード・版一覧・ワークフロー取得・案件取得は全て 404。
        案件Aの文書は見える (陽性対照)。
        根拠: requirements.md 行272, 行436, access_control.py 行8-9。
        """
        token = request.getfixturevalue(f"{role}_token")
        p = two_projects
        doc_b = p["doc_b"]

        # 陽性対照: 自案件の文書は見える
        assert p["doc_a"] in _doc_ids(client, token)
        ok = client.get(f"{API}/documents/{p['doc_a']}", headers=_h(token))
        assert ok.status_code == 200

        # 一覧 (全件 / 案件B指定) に出ない
        assert doc_b not in _doc_ids(client, token)
        assert _doc_ids(client, token, project_id=p["pb"]) == set()

        for path in (
            f"/documents/{doc_b}",
            f"/documents/{doc_b}/download",
            f"/documents/{doc_b}/revisions",
            f"/workflows/{p['wf_b']}",
            f"/projects/{p['pb']}",
        ):
            resp = client.get(f"{API}{path}", headers=_h(token))
            assert resp.status_code == 404, (path, resp.status_code)

        wfs = client.get(f"{API}/workflows/", headers=_h(token))
        assert wfs.status_code == 200
        assert p["wf_b"] not in {w["id"] for w in wfs.json()}

        projects = client.get(f"{API}/projects/", headers=_h(token))
        assert p["pb"] not in {x["id"] for x in projects.json()}

    def test_cross_project_access_status_is_404(
        self, client, two_projects, engineer_token
    ):
        """AT-DOC-005 (requirements.md v1.1.0, 決定 D-3) / WEB-DOC-010.

        期待: 他案件の文書は 404 (存在を秘匿)。存在しない ID と同じ応答。
        """
        resp = client.get(
            f"{API}/documents/{two_projects['doc_b']}", headers=_h(engineer_token)
        )
        assert resp.status_code == 404
        # 実在しない ID と同一の応答であること (存在の秘匿)
        missing = client.get(
            f"{API}/documents/{uuid.uuid4()}", headers=_h(engineer_token)
        )
        assert resp.status_code == missing.status_code
        assert resp.json() == missing.json()

    def test_non_member_cannot_upload_to_project_b(
        self, client, two_projects, admin_token, engineer_token
    ):
        """WEB-DOC-010 / §5.2 文書アップロードは所属案件に限る.

        期待: 案件Bの非メンバー engineer のアップロードは 404 (秘匿, D-3)、
        案件Bに文書が増えない。
        """
        before = _doc_ids(client, admin_token, project_id=two_projects["pb"])
        resp = _upload(client, engineer_token, two_projects["pb"], "侵入")
        assert resp.status_code == 404
        after = _doc_ids(client, admin_token, project_id=two_projects["pb"])
        assert after == before

    def test_non_member_cannot_mutate_project_b_document(
        self, client, two_projects, admin_token, engineer_token
    ):
        """WEB-DOC-010: 非メンバーは案件Bの文書を更新・削除・復元・
        ワークフロー作成・版追加できない (404 秘匿).

        根拠: requirements.md 行272, access_control.py 行8-9。
        """
        doc_b = two_projects["doc_b"]
        h = _h(engineer_token)
        assert (
            client.patch(
                f"{API}/documents/{doc_b}", json={"title": "改ざん"}, headers=h
            ).status_code
            == 404
        )
        assert client.delete(f"{API}/documents/{doc_b}", headers=h).status_code == 404
        assert (
            client.post(f"{API}/documents/{doc_b}/restore", headers=h).status_code
            == 404
        )
        doc_b2 = _upload_ok(client, admin_token, two_projects["pb"], "案件B図面2")
        assert _create_wf(client, engineer_token, doc_b2, []).status_code == 404
        # 何も変わっていない
        got = client.get(f"{API}/documents/{doc_b}", headers=_h(admin_token)).json()
        assert got["title"] == "案件B機密図面"
        assert got["deletion_requested_at"] is None

    def test_admin_sees_both_projects(self, client, two_projects, admin_token):
        """§5.2「文書参照 admin ✅（全て）」「プロジェクト参照 admin ✅（全て）」.

        根拠: requirements.md 行433, 行436。
        """
        p = two_projects
        ids = _doc_ids(client, admin_token)
        assert {p["doc_a"], p["doc_b"]} <= ids
        for path in (
            f"/documents/{p['doc_b']}",
            f"/documents/{p['doc_b']}/download",
            f"/documents/{p['doc_b']}/revisions",
            f"/workflows/{p['wf_b']}",
            f"/projects/{p['pb']}",
        ):
            assert client.get(f"{API}{path}", headers=_h(admin_token)).status_code == (
                200
            ), path

    def test_manager_non_member_sees_all_projects(
        self, client, two_projects, manager_token
    ):
        """A-1 (2026-10-03 決定) / §5.2 プロジェクト参照・文書参照 manager
        「✅（全て）」.

        旧 DEFECT-09 は §5.2 の旧版 (manager は所属のみ) に基づくもので、
        A-1 で「manager は所属に関係なく全案件・全文書を閲覧できる」に
        確定した。
        期待: 案件Bに所属しない manager でも、案件Bの文書は一覧・詳細・
        ダウンロード・ワークフロー取得・案件詳細とも 200 で、案件一覧
        (GET /projects/) にも案件A・Bの両方が出る (一覧と詳細の挙動が一致)。
        """
        p = two_projects
        assert {p["doc_a"], p["doc_b"]} <= _doc_ids(client, manager_token)
        for path in (
            f"/documents/{p['doc_b']}",
            f"/documents/{p['doc_b']}/download",
            f"/workflows/{p['wf_b']}",
            f"/projects/{p['pb']}",
        ):
            resp = client.get(f"{API}{path}", headers=_h(manager_token))
            assert resp.status_code == 200, (path, resp.status_code)
        projects = client.get(f"{API}/projects/", headers=_h(manager_token))
        assert projects.status_code == 200
        assert {p["pa"], p["pb"]} <= {x["id"] for x in projects.json()}


# ─── B. RBAC (§5.2) ──────────────────────────────────────────────────────


@pytest.fixture
def member_project(client, admin_token, engineer_user, viewer_user, manager_user):
    """engineer / viewer / manager が全員メンバーの案件と、admin 所有の文書."""
    pid = _create_project(client, admin_token, "RBAC案件")
    for uid in (engineer_user.id, viewer_user.id, manager_user.id):
        _add_member(client, admin_token, pid, uid)
    doc = _upload_ok(client, admin_token, pid, "admin所有図面")
    return {"pid": pid, "admin_doc": doc}


class TestRbacMatrix:
    def test_viewer_member_cannot_upload(
        self, client, member_project, viewer_token, admin_token
    ):
        """旧 DEFECT-01. §5.2 文書アップロード viewer「-」.

        期待: 案件メンバーであっても viewer のアップロードは 403。
        """
        before = _doc_ids(client, admin_token, project_id=member_project["pid"])
        resp = _upload(client, viewer_token, member_project["pid"], "viewer投稿")
        assert resp.status_code == 403
        after = _doc_ids(client, admin_token, project_id=member_project["pid"])
        assert after == before

    @pytest.mark.parametrize("role", ["engineer", "manager"])
    def test_engineer_and_manager_member_can_upload(
        self, request, client, member_project, role
    ):
        """§5.2 文書アップロード manager/engineer「✅」(行435). 陽性対照."""
        token = request.getfixturevalue(f"{role}_token")
        assert _upload(client, token, member_project["pid"], role).status_code == 201

    def test_viewer_member_cannot_delete(
        self, client, member_project, viewer_token, admin_token
    ):
        """旧 DEFECT-02. §5.2 文書削除 viewer「-」.

        期待: viewer の削除は 403 で、文書はごみ箱に入らない。
        """
        doc = member_project["admin_doc"]
        resp = client.delete(f"{API}/documents/{doc}", headers=_h(viewer_token))
        assert resp.status_code == 403
        assert doc in _doc_ids(client, admin_token)

    @pytest.mark.parametrize("role", ["engineer", "manager"])
    def test_owner_can_delete_own_document(self, request, client, member_project, role):
        """§5.2 文書削除 manager/engineer「✅（自分）」(行437). 陽性対照.

        期待: 自分がアップロードした文書は削除 204、一覧から消える。
        """
        token = request.getfixturevalue(f"{role}_token")
        doc = _upload_ok(client, token, member_project["pid"], f"{role}自分の図面")
        assert client.delete(
            f"{API}/documents/{doc}", headers=_h(token)
        ).status_code == (204)
        assert doc not in _doc_ids(client, token)

    @pytest.mark.parametrize("role", ["engineer", "manager"])
    def test_cannot_delete_others_document(
        self, request, client, db_session, member_project, admin_token, role
    ):
        """旧 DEFECT-03. §5.2 文書削除 manager/engineer「✅（自分）」.

        期待: 同じ案件の別 engineer が所有する文書の削除は 403 で、文書は残る。
        """
        token = request.getfixturevalue(f"{role}_token")
        other_id, other_token = _new_user(
            db_session, client, UserRole.ENGINEER, "engineer2"
        )
        _add_member(client, admin_token, member_project["pid"], other_id)
        doc = _upload_ok(client, other_token, member_project["pid"], "他人の図面")

        resp = client.delete(f"{API}/documents/{doc}", headers=_h(token))
        assert resp.status_code == 403
        assert doc in _doc_ids(client, other_token)

    def test_admin_can_delete_others_document(
        self, client, member_project, engineer_token, admin_token
    ):
        """§5.2 文書削除 admin「✅」(行437). 陽性対照."""
        doc = _upload_ok(client, engineer_token, member_project["pid"], "e図面")
        resp = client.delete(f"{API}/documents/{doc}", headers=_h(admin_token))
        assert resp.status_code == 204

    def test_owner_can_restore_own_document(
        self, client, member_project, engineer_token
    ):
        """WEB-DOC-005 ごみ箱・復元 (行267) + §5.2 文書削除「✅（自分）」. 陽性対照."""
        doc = _upload_ok(client, engineer_token, member_project["pid"], "復元対象")
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        resp = client.post(f"{API}/documents/{doc}/restore", headers=_h(engineer_token))
        assert resp.status_code == 200
        assert doc in _doc_ids(client, engineer_token)

    def test_admin_can_restore_others_document(
        self, client, member_project, engineer_token, admin_token
    ):
        """§5.2 ※3 復元は削除と同じ権限 — admin は他人の文書も復元可. 陽性対照."""
        doc = _upload_ok(client, engineer_token, member_project["pid"], "e削除済")
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        resp = client.post(f"{API}/documents/{doc}/restore", headers=_h(admin_token))
        assert resp.status_code == 200
        assert doc in _doc_ids(client, engineer_token)

    @pytest.mark.parametrize("role", ["viewer", "engineer", "manager"])
    def test_cannot_restore_others_document(
        self, request, client, db_session, member_project, admin_token, role
    ):
        """旧 DEFECT-04. WEB-DOC-005 復元 / §5.2 ※3「ごみ箱からの復元も、
        文書削除と同じ権限で行う（決定）」(admin=全て, manager/engineer=自分,
        viewer=不可)。
        期待: 他人がごみ箱に入れた文書の復元は 403 で、ごみ箱に残る。
        """
        token = request.getfixturevalue(f"{role}_token")
        other_id, other_token = _new_user(
            db_session, client, UserRole.ENGINEER, "engineer2"
        )
        _add_member(client, admin_token, member_project["pid"], other_id)
        doc = _upload_ok(client, other_token, member_project["pid"], "他人の削除済")
        assert (
            client.delete(f"{API}/documents/{doc}", headers=_h(other_token)).status_code
            == 204
        )

        resp = client.post(f"{API}/documents/{doc}/restore", headers=_h(token))
        assert resp.status_code == 403
        assert doc in _trash_ids(client, other_token)

    def test_viewer_member_cannot_create_workflow(
        self, client, member_project, viewer_token, manager_user, admin_token
    ):
        """旧 DEFECT-05. §5.2 ワークフロー作成 viewer「-」.

        期待: 403 で、文書ステータスは draft のまま。
        """
        doc = member_project["admin_doc"]
        resp = _create_wf(client, viewer_token, doc, [manager_user.id])
        assert resp.status_code == 403
        assert _doc_status(client, admin_token, doc) == "draft"

    @pytest.mark.parametrize("role", ["engineer", "manager"])
    def test_engineer_and_manager_can_create_workflow(
        self, request, client, member_project, manager_user, role
    ):
        """§5.2 ワークフロー作成 manager/engineer「✅」(行438). 陽性対照."""
        token = request.getfixturevalue(f"{role}_token")
        doc = _upload_ok(client, token, member_project["pid"], f"{role}起案")
        assert _create_wf(client, token, doc, [manager_user.id]).status_code == 201


# ─── C. 承認ワークフロー ──────────────────────────────────────────────────


@pytest.fixture
def wf_env(
    client, db_session, admin_token, engineer_user, engineer_token, manager_user
):
    """起案者 engineer と、承認者 3 名 (manager / engineer2 / manager2) の案件."""
    pid = _create_project(client, admin_token, "WF案件")
    e2_id, e2_token = _new_user(db_session, client, UserRole.ENGINEER, "engineer2")
    m2_id, m2_token = _new_user(db_session, client, UserRole.MANAGER, "manager2")
    for uid in (engineer_user.id, manager_user.id, e2_id, m2_id):
        _add_member(client, admin_token, pid, uid)
    doc = _upload_ok(client, engineer_token, pid, "承認対象図面")
    return {
        "pid": pid,
        "doc": doc,
        "approvers": [manager_user.id, e2_id, m2_id],
        "e2_token": e2_token,
        "m2_token": m2_token,
    }


def _three_step(client, engineer_token, wf_env):
    resp = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
    assert resp.status_code == 201, resp.text
    wf = resp.json()
    steps = sorted(wf["steps"], key=lambda s: s["order"])
    return wf["id"], [s["id"] for s in steps]


class TestApprovalWorkflow:
    def test_three_step_sequential_approval_reaches_approved(
        self, client, wf_env, engineer_token, manager_token, admin_token
    ):
        """AT-WF-001 / AT-WF-002 / AT-WF-003 (requirements.md 行711-713),
        WEB-WF-001/002/003 (行278-280).

        期待: 3ステップ作成 (順序1..3・全 pending・文書 pending_review)。
        Step1 承認前に Step2 は決定できない (409)。順次承認で各ステップが
        approved に遷移し、全承認でワークフロー/文書とも approved。
        承認後の GET でも状態・決定日時が保持される。
        """
        wf_id, (s1, s2, s3) = _three_step(client, engineer_token, wf_env)
        wf = client.get(f"{API}/workflows/{wf_id}", headers=_h(engineer_token)).json()
        assert wf["status"] == "in_progress"
        assert [s["order"] for s in wf["steps"]] == [1, 2, 3]
        assert [s["approver_id"] for s in wf["steps"]] == wf_env["approvers"]
        assert all(s["status"] == "pending" for s in wf["steps"])
        assert _doc_status(client, admin_token, wf_env["doc"]) == "pending_review"

        # 順次性: Step1 未承認で Step2 は決定不可
        early = _decide(client, wf_env["e2_token"], wf_id, s2)
        assert early.status_code == 409

        r1 = _decide(client, manager_token, wf_id, s1)
        assert r1.status_code == 200
        st = {s["id"]: s["status"] for s in r1.json()["steps"]}
        assert st == {s1: "approved", s2: "pending", s3: "pending"}
        assert r1.json()["status"] == "in_progress"
        assert _doc_status(client, admin_token, wf_env["doc"]) == "pending_review"

        assert _decide(client, wf_env["e2_token"], wf_id, s2).status_code == 200
        r3 = _decide(client, wf_env["m2_token"], wf_id, s3)
        assert r3.status_code == 200
        assert r3.json()["status"] == "approved"
        assert r3.json()["completed_at"] is not None
        assert _doc_status(client, admin_token, wf_env["doc"]) == "approved"

        # 永続化: 改めて取得しても状態が保持されている
        again = client.get(f"{API}/workflows/{wf_id}", headers=_h(engineer_token))
        assert again.status_code == 200
        body = again.json()
        assert body["status"] == "approved"
        assert all(s["status"] == "approved" for s in body["steps"])
        assert all(s["decided_at"] is not None for s in body["steps"])
        listed = client.get(f"{API}/workflows/", headers=_h(engineer_token)).json()
        item = next(w for w in listed if w["id"] == wf_id)
        assert item["status"] == "approved"
        assert item["pending_step_count"] == 0

    def test_reject_midway_marks_workflow_rejected(
        self, client, wf_env, engineer_token, manager_token, admin_token
    ):
        """AT-WF-004 (requirements.md 行714).

        期待: Step2 で却下するとワークフローも文書も rejected。
        後続の Step3 は pending のまま決定不可 (409)。
        """
        wf_id, (s1, s2, s3) = _three_step(client, engineer_token, wf_env)
        assert _decide(client, manager_token, wf_id, s1).status_code == 200
        rej = _decide(client, wf_env["e2_token"], wf_id, s2, "reject", "寸法誤り")
        assert rej.status_code == 200
        assert rej.json()["status"] == "rejected"
        assert rej.json()["completed_at"] is not None
        st = {s["id"]: s["status"] for s in rej.json()["steps"]}
        assert st == {s1: "approved", s2: "rejected", s3: "pending"}
        assert _doc_status(client, admin_token, wf_env["doc"]) == "rejected"

        late = _decide(client, wf_env["m2_token"], wf_id, s3)
        assert late.status_code == 409
        got = client.get(f"{API}/workflows/{wf_id}", headers=_h(engineer_token))
        assert got.json()["status"] == "rejected"

    def test_non_assignee_cannot_decide(
        self, client, wf_env, engineer_token, manager_token, admin_token
    ):
        """AT-WF-005 (行715) / §5.2 承認・却下「✅（担当のみ）」(行439).

        期待: 担当外 (起案者 engineer・Step2 の担当者・admin) が Step1 を
        承認/却下すると 403 で、状態は変わらない。
        """
        wf_id, (s1, _s2, _s3) = _three_step(client, engineer_token, wf_env)
        for token in (engineer_token, wf_env["e2_token"], admin_token):
            for decision in ("approve", "reject"):
                resp = _decide(client, token, wf_id, s1, decision)
                assert resp.status_code == 403, (decision, resp.status_code)
        wf = client.get(f"{API}/workflows/{wf_id}", headers=_h(admin_token)).json()
        assert wf["status"] == "in_progress"
        assert all(s["status"] == "pending" for s in wf["steps"])

    def test_duplicate_workflow_conflict(
        self, client, wf_env, engineer_token, manager_token
    ):
        """AT-WF-006 (requirements.md 行716).

        期待: 同一文書へ2つ目のワークフロー作成は 409 (起案者が別でも同じ)。
        """
        _three_step(client, engineer_token, wf_env)
        dup = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        assert dup.status_code == 409
        dup2 = _create_wf(client, manager_token, wf_env["doc"], wf_env["approvers"])
        assert dup2.status_code == 409

    def test_comments_are_saved_and_readable(
        self, client, wf_env, engineer_token, manager_token
    ):
        """AT-WF-007 (requirements.md 行717) / WEB-WF-002 (行279).

        期待: 承認時・却下時のコメントが保存され、ワークフロー取得で参照できる。
        """
        wf_id, (s1, s2, _s3) = _three_step(client, engineer_token, wf_env)
        approve_comment = "配筋確認済み。問題なし。"
        reject_comment = "かぶり厚さ不足 (図面 S-12)\n再提出してください"
        _decide(client, manager_token, wf_id, s1, "approve", approve_comment)
        _decide(client, wf_env["e2_token"], wf_id, s2, "reject", reject_comment)

        wf = client.get(f"{API}/workflows/{wf_id}", headers=_h(engineer_token))
        comments = {s["id"]: s["comment"] for s in wf.json()["steps"]}
        assert comments[s1] == approve_comment
        assert comments[s2] == reject_comment

    def test_redecide_already_decided_step_conflict(
        self, client, wf_env, engineer_token, manager_token
    ):
        """WEB-WF-002 (行279) — 決定済みステップの再決定 (再実行) は 409.

        期待: 承認済み Step1 への再承認・却下はいずれも 409 で、
        コメント・決定結果は上書きされない。
        """
        wf_id, (s1, _s2, _s3) = _three_step(client, engineer_token, wf_env)
        _decide(client, manager_token, wf_id, s1, "approve", "初回コメント")
        for decision in ("approve", "reject"):
            resp = _decide(client, manager_token, wf_id, s1, decision, "上書き")
            assert resp.status_code == 409, decision
        wf = client.get(f"{API}/workflows/{wf_id}", headers=_h(engineer_token)).json()
        step1 = next(s for s in wf["steps"] if s["id"] == s1)
        assert step1["status"] == "approved"
        assert step1["comment"] == "初回コメント"
        assert wf["status"] == "in_progress"

    def test_invalid_decision_value_rejected(
        self, client, wf_env, engineer_token, manager_token
    ):
        """WEB-WF-002 — decision は approve/reject のみ. 不正値は 422."""
        wf_id, (s1, _s2, _s3) = _three_step(client, engineer_token, wf_env)
        resp = _decide(client, manager_token, wf_id, s1, "approved")
        assert resp.status_code == 422

    def test_unknown_approver_leaves_no_partial_workflow(
        self, client, wf_env, engineer_token, admin_token
    ):
        """WEB-WF-001 (行278) — 存在しない承認者を含む作成は失敗し、
        中途半端なワークフローや文書ステータス変更が残らない.

        期待: 404、文書は draft のまま、正しい内容で再作成すると 201。
        """
        bad = wf_env["approvers"][:1] + [str(uuid.uuid4())]
        resp = _create_wf(client, engineer_token, wf_env["doc"], bad)
        assert resp.status_code == 404
        assert _doc_status(client, admin_token, wf_env["doc"]) == "draft"
        retry = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        assert retry.status_code == 201

    def test_empty_approver_list_rejected(self, client, wf_env, engineer_token):
        """WEB-WF-001 (行278) 承認者指定は必須. 空配列は 400."""
        resp = _create_wf(client, engineer_token, wf_env["doc"], [])
        assert resp.status_code == 400

    def test_viewer_cannot_act_as_approver(
        self, client, wf_env, engineer_token, viewer_user, viewer_token, admin_token
    ):
        """旧 DEFECT-06. §5.2 ※1「viewer は承認者になれない（決定）」.

        期待: 文書を閲覧できる案件メンバーの viewer であっても、承認者に
        含めたワークフロー作成は 422 (detail に理由)。ワークフローは作られず
        文書は draft のまま。
        """
        _add_member(client, admin_token, wf_env["pid"], viewer_user.id)
        resp = _create_wf(
            client,
            engineer_token,
            wf_env["doc"],
            [wf_env["approvers"][0], viewer_user.id],
        )
        assert resp.status_code == 422
        assert viewer_user.id in resp.json()["detail"]
        assert _doc_status(client, admin_token, wf_env["doc"]) == "draft"
        listed = client.get(f"{API}/workflows/", headers=_h(admin_token)).json()
        assert wf_env["doc"] not in {w["document_id"] for w in listed}

    def test_admin_can_act_as_approver(
        self, client, wf_env, engineer_token, admin_user, admin_token
    ):
        """§5.2 承認・却下 admin「✅（担当のみ）」(requirements.md v1.1.0, 2026-10-03 決定).

        期待: admin を承認者に指定でき (201)、admin が自分の担当ステップを
        承認すると approved になる。
        """
        resp = _create_wf(client, engineer_token, wf_env["doc"], [admin_user.id])
        assert resp.status_code == 201
        wf = resp.json()
        dec = _decide(client, admin_token, wf["id"], wf["steps"][0]["id"])
        assert dec.status_code == 200
        assert dec.json()["status"] == "approved"
        assert _doc_status(client, admin_token, wf_env["doc"]) == "approved"

    def test_admin_cannot_decide_step_assigned_to_others(
        self, client, wf_env, engineer_token, admin_token
    ):
        """§5.2 承認・却下は「担当のみ」— admin でも他人の担当ステップは 403."""
        resp = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        assert resp.status_code == 201
        wf = resp.json()
        dec = _decide(client, admin_token, wf["id"], wf["steps"][0]["id"])
        assert dec.status_code == 403
        assert _doc_status(client, admin_token, wf_env["doc"]) == "pending_review"

    def test_self_approval_is_allowed(
        self, client, wf_env, engineer_user, engineer_token, admin_token
    ):
        """A-2 (決定) / §5.2 ※1「自己承認は許可する」.

        期待: 起案者 (文書所有者) が自分を唯一の承認者にして作成 201 →
        自己承認 200 → ワークフロー・文書とも approved。
        """
        resp = _create_wf(client, engineer_token, wf_env["doc"], [engineer_user.id])
        assert resp.status_code == 201
        wf = resp.json()
        dec = _decide(client, engineer_token, wf["id"], wf["steps"][0]["id"])
        assert dec.status_code == 200
        assert dec.json()["status"] == "approved"
        assert _doc_status(client, admin_token, wf_env["doc"]) == "approved"

    def test_non_member_approver_rejected_at_creation(
        self, client, db_session, wf_env, engineer_token, admin_token
    ):
        """A-3 (決定) / §5.2 ※1「承認者に指定できるのは、その文書を閲覧
        できるユーザーに限る」.

        期待: 案件メンバーでない (=文書を閲覧できない) engineer を承認者に
        含めた作成は 422 (detail に理由)。ワークフローは作られず文書は
        draft のまま。陽性対照として、閲覧できる承認者のみなら 201。
        """
        out_id, _out_token = _new_user(
            db_session, client, UserRole.ENGINEER, "outsider"
        )
        resp = _create_wf(
            client, engineer_token, wf_env["doc"], [wf_env["approvers"][0], out_id]
        )
        assert resp.status_code == 422
        assert out_id in resp.json()["detail"]
        assert _doc_status(client, admin_token, wf_env["doc"]) == "draft"
        ok = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        assert ok.status_code == 201

    def test_approver_who_lost_visibility_cannot_decide(
        self, client, db_session, wf_env, engineer_token, admin_token
    ):
        """A-3 (決定) — decide 時にも承認者が文書を閲覧できることを確認する.

        承認者に指定された後で案件メンバーから外れた (=文書を閲覧できなく
        なった) engineer の decide は 404 (存在の秘匿, D-3) で、状態は
        変わらない。
        """
        e2_id = wf_env["approvers"][1]
        resp = _create_wf(client, engineer_token, wf_env["doc"], [e2_id])
        assert resp.status_code == 201
        wf = resp.json()
        removed = client.delete(
            f"{API}/projects/{wf_env['pid']}/members/{e2_id}",
            headers=_h(admin_token),
        )
        assert removed.status_code == 204
        dec = _decide(client, wf_env["e2_token"], wf["id"], wf["steps"][0]["id"])
        assert dec.status_code == 404
        got = client.get(f"{API}/workflows/{wf['id']}", headers=_h(admin_token))
        assert got.json()["status"] == "in_progress"
        assert _doc_status(client, admin_token, wf_env["doc"]) == "pending_review"

    def test_approver_demoted_to_viewer_cannot_decide(
        self, client, db_session, wf_env, engineer_token, admin_token
    ):
        """A-3 / §5.2 承認・却下 viewer「-」 — decide 時にも承認者の条件を再確認する.

        承認者に指定された後で viewer に変更された engineer は、文書は閲覧
        できても承認できない (403)。状態は変わらない。
        """
        e2_id = wf_env["approvers"][1]
        resp = _create_wf(client, engineer_token, wf_env["doc"], [e2_id])
        assert resp.status_code == 201
        wf = resp.json()
        row = db_session.query(User).filter(User.id == e2_id).one()
        row.role = UserRole.VIEWER
        db_session.commit()
        dec = _decide(client, wf_env["e2_token"], wf["id"], wf["steps"][0]["id"])
        assert dec.status_code == 403
        got = client.get(f"{API}/workflows/{wf['id']}", headers=_h(admin_token))
        assert got.json()["status"] == "in_progress"
        assert got.json()["steps"][0]["status"] == "pending"

    def test_resubmission_after_rejection_current_behavior(
        self, client, wf_env, engineer_token, manager_token
    ):
        """仕様未定 (WEB-WF-005 差戻し・再申請は未着手, 行282):
        却下後に同じ文書へ再申請 (新ワークフロー作成) できるか.

        現状挙動 (記録): 却下済みでも 1 文書 1 ワークフロー制約により 409。
        却下された文書は修正後も再承認の手段がない。
        """
        resp = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        wf = resp.json()
        _decide(client, manager_token, wf["id"], wf["steps"][0]["id"], "reject")
        again = _create_wf(client, engineer_token, wf_env["doc"], wf_env["approvers"])
        assert again.status_code == 409


# ─── D. 削除・復元の業務シナリオ ─────────────────────────────────────────


@pytest.fixture
def own_doc(client, admin_token, engineer_user, engineer_token):
    pid = _create_project(client, admin_token, "削除案件")
    _add_member(client, admin_token, pid, engineer_user.id)
    doc = _upload_ok(client, engineer_token, pid, "削除対象")
    return {"pid": pid, "doc": doc}


class TestDeleteRestore:
    def test_deleted_document_leaves_list_and_enters_trash(
        self, client, own_doc, engineer_token, admin_token
    ):
        """AT-DOC-006 前半 (行704) / WEB-DOC-005 (行267).

        期待: 削除 204 後、所有者・admin の一覧から消え、ごみ箱に入る。
        """
        doc = own_doc["doc"]
        assert (
            client.delete(
                f"{API}/documents/{doc}", headers=_h(engineer_token)
            ).status_code
            == 204
        )
        assert doc not in _doc_ids(client, engineer_token)
        assert doc not in _doc_ids(client, admin_token, project_id=own_doc["pid"])
        assert doc in _trash_ids(client, engineer_token)

    def test_deleted_document_direct_url_returns_404(
        self, client, own_doc, engineer_token, admin_token
    ):
        """旧 DEFECT-08. AT-DOC-006 後半 (requirements.md 行746).

        期待: 削除後に文書の直接 URL (詳細・ダウンロード・タイムスタンプ検証)
        は所有者・admin とも 404 で、実在しない ID と同じ応答 (存在の秘匿)。
        ごみ箱一覧と復元 API は従来どおり使え、復元後は詳細・ダウンロード
        とも 200 に戻る。
        """
        doc = own_doc["doc"]
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        missing = client.get(
            f"{API}/documents/{uuid.uuid4()}", headers=_h(engineer_token)
        )
        for token in (engineer_token, admin_token):
            detail = client.get(f"{API}/documents/{doc}", headers=_h(token))
            assert detail.status_code == 404
            assert detail.json() == missing.json()
            for suffix in ("download", "timestamp/verify"):
                resp = client.get(f"{API}/documents/{doc}/{suffix}", headers=_h(token))
                assert resp.status_code == 404, suffix

        assert doc in _trash_ids(client, engineer_token)
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 200
        h = _h(engineer_token)
        assert client.get(f"{API}/documents/{doc}", headers=h).status_code == 200
        assert client.get(f"{API}/documents/{doc}/download", headers=h).status_code == (
            200
        )

    def test_restore_brings_document_back(self, client, own_doc, engineer_token):
        """WEB-DOC-005 ごみ箱・復元 (行267).

        期待: 復元 200、deletion_requested_at が消え、一覧に戻りごみ箱から消える。
        """
        doc = own_doc["doc"]
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        resp = client.post(f"{API}/documents/{doc}/restore", headers=_h(engineer_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["deletion_requested_at"] is None
        assert body["is_archived"] is False
        assert doc in _doc_ids(client, engineer_token)
        assert doc not in _trash_ids(client, engineer_token)

    def test_restore_not_deleted_document_conflict(
        self, client, own_doc, engineer_token
    ):
        """WEB-DOC-005 — ごみ箱にない文書の復元は 409."""
        resp = client.post(
            f"{API}/documents/{own_doc['doc']}/restore", headers=_h(engineer_token)
        )
        assert resp.status_code == 409

    def test_double_delete_keeps_first_request_time(
        self, client, db_session, own_doc, engineer_token
    ):
        """B-4 (決定) / WEB-DOC-005 決定事項「二重削除」.

        期待: 削除済み文書への2回目の削除も 204 (冪等) だが、
        deletion_requested_at は最初の削除要求日時のまま上書きされない
        (30日の猶予起算点がリセットされない)。監査ログの
        document.soft_deleted は1件のみ (二重記録しない)。
        """
        doc = own_doc["doc"]
        assert (
            client.delete(
                f"{API}/documents/{doc}", headers=_h(engineer_token)
            ).status_code
            == 204
        )
        # 1回目の削除が 20 日前だったことにする
        old = datetime.now(timezone.utc) - timedelta(days=20)
        row = db_session.query(Document).filter(Document.id == doc).one()
        row.deletion_requested_at = old
        db_session.commit()

        second = client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        assert second.status_code == 204
        db_session.expire_all()
        row = db_session.query(Document).filter(Document.id == doc).one()
        stored = row.deletion_requested_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        # 起算点は最初の削除要求日時のまま
        if old.tzinfo is None:
            old = old.replace(tzinfo=timezone.utc)
        assert abs(stored - old) < timedelta(seconds=1)
        logs = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.action == "document.soft_deleted",
                AuditLog.resource_id == doc,
            )
            .all()
        )
        assert len(logs) == 1

    def test_restore_after_approval_returns_to_approved(
        self, client, own_doc, engineer_token, manager_user, manager_token, admin_token
    ):
        """C-1 (決定) / WEB-DOC-005 決定事項「復元すると削除前の状態に戻る。
        承認記録は保持する」.

        期待: 承認済み文書を削除→復元すると文書ステータスは approved に戻り、
        is_archived も削除前 (False) に戻る。ワークフロー (承認記録) は
        approved のまま変わらず、各ステップの決定日時も保持される。
        """
        _add_member(client, admin_token, own_doc["pid"], manager_user.id)
        doc = own_doc["doc"]
        wf = _create_wf(client, engineer_token, doc, [manager_user.id]).json()
        _decide(client, manager_token, wf["id"], wf["steps"][0]["id"])
        assert _doc_status(client, admin_token, doc) == "approved"

        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "approved"
        assert restored.json()["is_archived"] is False
        assert _doc_status(client, admin_token, doc) == "approved"
        got = client.get(f"{API}/workflows/{wf['id']}", headers=_h(engineer_token))
        assert got.json()["status"] == "approved"
        assert all(s["decided_at"] is not None for s in got.json()["steps"])
        # 1 文書 1 ワークフロー制約は従来どおり
        assert (
            _create_wf(client, engineer_token, doc, [manager_user.id]).status_code
            == 409
        )

    @pytest.mark.parametrize(
        "prior_status", ["draft", "pending_review", "rejected", "finalized"]
    )
    def test_restore_returns_each_pre_deletion_status(
        self, client, db_session, own_doc, engineer_token, prior_status
    ):
        """C-1 (決定) — 削除前のステータスが何であっても復元で元に戻る.

        削除前の値は extra_data に退避され、復元後は extra_data から取り除かれる。
        """
        doc = own_doc["doc"]
        row = db_session.query(Document).filter(Document.id == doc).one()
        row.status = prior_status
        row.extra_data = {"other": "keep"}
        db_session.commit()

        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == prior_status
        db_session.expire_all()
        row = db_session.query(Document).filter(Document.id == doc).one()
        assert row.extra_data == {"other": "keep"}

    def test_restore_legacy_trash_without_saved_status_falls_back_to_draft(
        self, client, db_session, own_doc, engineer_token
    ):
        """C-1 — 削除前ステータスの退避がない古いデータは draft に戻す."""
        doc = own_doc["doc"]
        row = db_session.query(Document).filter(Document.id == doc).one()
        row.status = "archived"
        row.is_archived = True
        row.deletion_requested_at = datetime.now(timezone.utc)
        row.extra_data = {}
        db_session.commit()
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "draft"
        assert restored.json()["is_archived"] is False

    def test_restore_after_privacy_deletion_request_keeps_status(
        self, client, db_session, own_doc, engineer_token
    ):
        """C-1 — 状態を退避しない経路 (プライバシーの削除要求) でごみ箱に入った
        文書は、復元時に元の状態を保つ (draft に落とさない).

        api/privacy.py の削除要求は deletion_requested_at を設定するだけで
        status を変えないため、復元で status をそのまま残す。
        """
        doc = own_doc["doc"]
        row = db_session.query(Document).filter(Document.id == doc).one()
        row.status = "approved"
        row.is_archived = False
        row.deletion_requested_at = datetime.now(timezone.utc)
        row.extra_data = {}
        db_session.commit()
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "approved"
        assert restored.json()["is_archived"] is False

    def test_physically_deleted_document_cannot_be_restored(
        self, client, db_session, own_doc, engineer_token
    ):
        """物理削除済み (ファイル消去済み) の文書は復元できない (409).

        services/deletion_job.py は file_path を空にして記録だけ残す。
        ファイルのない文書を一覧に戻さない。
        """
        doc = own_doc["doc"]
        assert (
            client.delete(
                f"{API}/documents/{doc}", headers=_h(engineer_token)
            ).status_code
            == 204
        )
        row = db_session.query(Document).filter(Document.id == doc).one()
        row.file_path = None
        db_session.commit()
        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.status_code == 409
        assert "physically deleted" in restored.json()["detail"]
        assert doc in _trash_ids(client, engineer_token)

    def test_trashed_document_rejects_writes_and_ai(
        self, client, own_doc, engineer_token, admin_token
    ):
        """AT-DOC-006 の拡張 — ごみ箱の文書は書込み・AI 送信の対象にもならない.

        更新 (PATCH)・タイムスタンプ付与・版の追加・AI 分類は 404 (存在しない
        ID と同じ応答)。AI の外部呼出しは発生しない。
        """
        from unittest.mock import patch

        doc = own_doc["doc"]
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        h = _h(admin_token)
        assert (
            client.patch(
                f"{API}/documents/{doc}", json={"title": "x"}, headers=h
            ).status_code
            == 404
        )
        assert (
            client.post(f"{API}/documents/{doc}/timestamp", headers=h).status_code
            == 404
        )
        rev = client.post(
            f"{API}/documents/{doc}/revisions",
            files={"file": ("r.pdf", io.BytesIO(_pdf()), "application/pdf")},
            headers=h,
        )
        assert rev.status_code == 404
        with (
            patch("api.ai._get_anthropic_client") as client_fn,
            patch("api.ai.ai_settings_service.is_ai_enabled", return_value=True),
        ):
            ai = client.post(f"{API}/ai/documents/{doc}/classify", headers=h)
        assert ai.status_code == 404
        client_fn.assert_not_called()

    def test_workflow_on_trashed_document_conflict(
        self, client, own_doc, engineer_token, manager_user, admin_token
    ):
        """C-2 (決定) / WEB-DOC-005 決定事項「ごみ箱にある文書には、
        ワークフロー作成・承認・却下を行えない」.

        期待: ごみ箱の文書へのワークフロー作成は 409 (detail に理由)。
        文書はごみ箱に残り、ステータスは archived のまま。
        """
        _add_member(client, admin_token, own_doc["pid"], manager_user.id)
        doc = own_doc["doc"]
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))
        resp = _create_wf(client, engineer_token, doc, [manager_user.id])
        assert resp.status_code == 409
        assert "trash" in resp.json()["detail"]
        trash = client.get(f"{API}/documents/trash", headers=_h(engineer_token))
        item = next(d for d in trash.json() if d["id"] == doc)
        assert item["status"] == "archived"

    @pytest.mark.parametrize("decision", ["approve", "reject"])
    def test_decide_on_trashed_document_conflict(
        self,
        client,
        own_doc,
        engineer_token,
        manager_user,
        manager_token,
        admin_token,
        decision,
    ):
        """C-2 (決定) — ワークフロー進行中に文書をごみ箱へ入れた場合、
        承認・却下は 409 で、ステップ・ワークフローは変わらない。
        復元後は承認できる (削除前の pending_review に戻る, C-1)。
        """
        _add_member(client, admin_token, own_doc["pid"], manager_user.id)
        doc = own_doc["doc"]
        wf = _create_wf(client, engineer_token, doc, [manager_user.id]).json()
        step_id = wf["steps"][0]["id"]
        client.delete(f"{API}/documents/{doc}", headers=_h(engineer_token))

        resp = _decide(client, manager_token, wf["id"], step_id, decision)
        assert resp.status_code == 409
        assert "trash" in resp.json()["detail"]
        got = client.get(f"{API}/workflows/{wf['id']}", headers=_h(admin_token))
        assert got.json()["status"] == "in_progress"
        assert got.json()["steps"][0]["status"] == "pending"

        restored = client.post(
            f"{API}/documents/{doc}/restore", headers=_h(engineer_token)
        )
        assert restored.json()["status"] == "pending_review"
        assert (
            _decide(client, manager_token, wf["id"], step_id, decision).status_code
            == 200
        )

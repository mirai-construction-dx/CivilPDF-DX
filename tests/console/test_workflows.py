"""Approval workflow API tests."""

import io


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _upload_doc(client, admin_token, project_id: str, title: str = "Doc") -> str:
    resp = client.post(
        "/api/v1/documents/",
        data={"project_id": project_id, "title": title},
        files={"file": ("f.pdf", io.BytesIO(_pdf()), "application/pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_project(client, admin_token) -> str:
    import uuid

    code = f"WF-{uuid.uuid4().hex[:6].upper()}"
    resp = client.post(
        "/api/v1/projects/",
        json={"name": "WF Project", "code": code},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return resp.json()["id"]


def _create_manager(client, admin_token, session_factory) -> tuple[str, str]:
    """Create a manager user and return (user_id, token)."""
    resp = client.post(
        "/api/v1/users/",
        json={
            "email": "manager@example.com",
            "username": "manager1",
            "full_name": "Test Manager",
            "password": "Manager123!",
            "role": "manager",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = resp.json()["id"]
    token_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "manager@example.com", "password": "Manager123!"},
    )
    return user_id, token_resp.json()["access_token"]


class TestWorkflow:
    def test_create_workflow(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)

        resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["document_id"] == doc_id
        assert data["status"] == "in_progress"
        assert len(data["steps"]) == 1

    def test_duplicate_workflow_rejected(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        payload = {"document_id": doc_id, "approver_ids": [admin_user.id]}
        client.post(
            "/api/v1/workflows/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.post(
            "/api/v1/workflows/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_workflow_no_approvers_rejected(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": []},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_approve_step(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        step_id = wf_resp.json()["steps"][0]["id"]

        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "approve", "comment": "Looks good"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_step(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        step_id = wf_resp.json()["steps"][0]["id"]

        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "reject", "comment": "Need revision"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_wrong_approver_forbidden(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        step_id = wf_resp.json()["steps"][0]["id"]

        # Create another user to attempt approving
        client.post(
            "/api/v1/users/",
            json={
                "email": "other@example.com",
                "username": "other1",
                "full_name": "Other",
                "password": "Other123!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        other_token = client.post(
            "/api/v1/auth/token",
            data={"username": "other@example.com", "password": "Other123!"},
        ).json()["access_token"]

        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403

    def test_get_workflow(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        resp = client.get(
            f"/api/v1/workflows/{workflow_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == workflow_id

    def test_create_workflow_document_not_found(self, client, admin_user, admin_token):
        resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": "nonexistent-doc-id", "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_create_workflow_approver_not_found(self, client, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": ["nonexistent-user-id"]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_get_workflow_not_found(self, client, admin_token):
        resp = client.get(
            "/api/v1/workflows/nonexistent-workflow-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_decide_step_not_found(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/nonexistent-step-id/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_decide_already_decided_step(self, client, admin_user, admin_token):
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)
        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        workflow_id = wf_resp.json()["id"]
        step_id = wf_resp.json()["steps"][0]["id"]

        # First decision
        client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Second decision on the same step should fail
        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_multi_step_workflow_next_step_activated(
        self, client, admin_user, admin_token
    ):
        """Approving step 1 should leave step 2 pending (next step activation)."""
        project_id = _create_project(client, admin_token)
        doc_id = _upload_doc(client, admin_token, project_id)

        # Create a second user to be the second approver
        client.post(
            "/api/v1/users/",
            json={
                "email": "approver2@example.com",
                "username": "approver2",
                "full_name": "Second Approver",
                "password": "Approver123!",
                "role": "manager",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        approver2_id = client.get(
            "/api/v1/users/",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()[-1]["id"]

        wf_resp = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [admin_user.id, approver2_id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert wf_resp.status_code == 201
        workflow_id = wf_resp.json()["id"]
        step1_id = next(s["id"] for s in wf_resp.json()["steps"] if s["order"] == 1)

        # Admin approves step 1
        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step1_id}/decide",
            json={"decision": "approve", "comment": "Step 1 approved"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        # Workflow should still be in_progress (step 2 not yet approved)
        assert resp.json()["status"] == "in_progress"


def _create_user(
    client,
    admin_token,
    email: str,
    username: str,
    role: str = "manager",
) -> tuple[str, str]:
    """Create a user through the API and return (user_id, access_token)."""
    password = "Workflow123!"
    resp = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "username": username,
            "full_name": username,
            "password": password,
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    token = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    ).json()["access_token"]
    return user_id, token


def _workflow_doc(client, admin_token, approver_ids: list[str]):
    """Create a project + document + workflow; return (doc_id, workflow, steps)."""
    project_id = _create_project(client, admin_token)
    doc_id = _upload_doc(client, admin_token, project_id)
    resp = client.post(
        "/api/v1/workflows/",
        json={"document_id": doc_id, "approver_ids": approver_ids},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    return doc_id, project_id, resp.json()


def _document_status(client, token: str, doc_id: str) -> str:
    resp = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


class TestWorkflowReturn:
    """WEB-WF-005: 差戻し（return）と再申請（resubmit）."""

    def test_return_step_marks_workflow_and_document(
        self, client, admin_user, admin_token
    ):
        """差戻し: step=returned / workflow=returned / 文書は再編集可能な draft。"""
        doc_id, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "数量表を修正してください"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "returned"
        assert body["steps"][0]["status"] == "returned"
        assert body["steps"][0]["comment"] == "数量表を修正してください"
        assert body["steps"][0]["decided_at"] is not None
        assert body["completed_at"] is None
        assert _document_status(client, admin_token, doc_id) == "draft"

    def test_return_notifies_owner(self, client, admin_user, admin_token):
        """差戻しは起票者へ通知され、理由が本文に含まれる。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "図面番号が不一致"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text

        notes = client.get(
            "/api/v1/notifications/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert notes.status_code == 200
        returned = [n for n in notes.json()["items"] if "差戻" in n["title"]]
        assert returned, notes.json()["items"]
        assert "図面番号が不一致" in returned[0]["body"]

    def test_return_records_audit_log(self, client, admin_user, admin_token):
        """差戻しは監査ログに workflow.step.returned として追記される。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]

        client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.get(
            "/api/v1/audit-logs/",
            params={"action": "workflow.step.returned"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= 1
        detail = resp.json()["items"][0]["detail"]
        assert '"decision": "return"' in detail

    def test_resubmit_restarts_same_workflow(self, client, admin_user, admin_token):
        """再申請: 全ステップが pending に戻り、先頭承認者へ再通知される。"""
        doc_id, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]

        client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "in_progress"
        assert [s["status"] for s in body["steps"]] == ["pending"]
        assert body["steps"][0]["comment"] is None
        assert body["steps"][0]["decided_at"] is None
        assert _document_status(client, admin_token, doc_id) == "pending_review"

        notes = client.get(
            "/api/v1/notifications/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert any(
            "再申請" in n["body"]
            for n in notes.json()["items"]
            if n["notification_type"] == "workflow.assigned"
        ), notes.json()["items"]

    def test_resubmit_then_approve_completes(self, client, admin_user, admin_token):
        """差戻し → 再申請 → 承認 でワークフローが完了する。"""
        doc_id, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]
        auth = {"Authorization": f"Bearer {admin_token}"}

        client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers=auth,
        )
        assert (
            client.post(
                f"/api/v1/workflows/{wf['id']}/resubmit", headers=auth
            ).status_code
            == 200
        )

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "approve", "comment": "修正確認"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"
        assert _document_status(client, admin_token, doc_id) == "approved"

    def test_return_after_previous_step_approved_is_conflict(
        self, client, admin_user, admin_token
    ):
        """先行ステップが承認済みの場合、後続ステップからの差戻しは 409。

        承認済みの上流判断を巻き戻す仕様が未定義のため（設計 D2）。
        """
        approver2_id, approver2_token = _create_user(
            client, admin_token, "wf-r2@example.com", "wf-r2"
        )
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id, approver2_id])
        step1_id = next(s["id"] for s in wf["steps"] if s["order"] == 1)
        step2_id = next(s["id"] for s in wf["steps"] if s["order"] == 2)

        first = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step1_id}/decide",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert first.status_code == 200

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step2_id}/decide",
            json={"decision": "return", "comment": "戻したい"},
            headers={"Authorization": f"Bearer {approver2_token}"},
        )
        assert resp.status_code == 409
        assert "return" in resp.json()["detail"]

    def test_resubmit_requires_returned_state(self, client, admin_user, admin_token):
        """差戻しされていないワークフローの再申請は 409。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_resubmit_not_found(self, client, admin_token):
        resp = client.post(
            "/api/v1/workflows/nonexistent-workflow-id/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_resubmit_forbidden_for_non_owner(self, client, admin_user, admin_token):
        """起票者でも admin でもない利用者の再申請は 403（文書が見える場合）。"""
        other_id, other_token = _create_user(
            client, admin_token, "wf-other@example.com", "wf-other", role="engineer"
        )
        _, project_id, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]

        client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 文書の可視性は保ったまま、所有者でない利用者の権限だけを検証する
        added = client.post(
            f"/api/v1/projects/{project_id}/members/{other_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert added.status_code == 204, added.text

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/resubmit",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403

    def test_invalid_decision_value_rejected(self, client, admin_user, admin_token):
        """decision は approve / reject / return のみ（契約の固定）。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]
        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "send_back"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_return_twice_is_conflict(self, client, admin_user, admin_token):
        """差戻し済みステップへの再操作は 409（二重決定の防止）。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]
        auth = {"Authorization": f"Bearer {admin_token}"}

        first = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers=auth,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "もう一度"},
            headers=auth,
        )
        assert second.status_code == 409

    def test_audit_action_names_keep_existing_contract(
        self, client, admin_user, admin_token
    ):
        """approve の監査アクション名は従来どおり workflow.step.decided。"""
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]
        auth = {"Authorization": f"Bearer {admin_token}"}

        approved = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "approve"},
            headers=auth,
        )
        assert approved.status_code == 200

        resp = client.get(
            "/api/v1/audit-logs/",
            params={"action": "workflow.step.decided"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= 1
        assert '"decision": "approve"' in resp.json()["items"][0]["detail"]

        # 新しいアクション名は差戻しでのみ使う
        assert (
            client.get(
                "/api/v1/audit-logs/",
                params={"action": "workflow.step.approved"},
                headers=auth,
            ).json()["total"]
            == 0
        )

    def test_return_before_approval_returns_workflow_to_first_step(
        self, client, admin_user, admin_token
    ):
        """先行ステップが未承認のまま後続から差戻しても、先行の承認は無いので許可。

        差戻し後の再申請は先頭ステップから再開する（設計 D2 / D6）。
        """
        approver2_id, approver2_token = _create_user(
            client, admin_token, "wf-r3@example.com", "wf-r3"
        )
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id, approver2_id])
        step2_id = next(s["id"] for s in wf["steps"] if s["order"] == 2)

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step2_id}/decide",
            json={"decision": "return", "comment": "全体を戻す"},
            headers={"Authorization": f"Bearer {approver2_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "returned"

        resubmitted = client.post(
            f"/api/v1/workflows/{wf['id']}/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resubmitted.status_code == 200, resubmitted.text
        assert [s["status"] for s in resubmitted.json()["steps"]] == [
            "pending",
            "pending",
        ]

    def test_return_forbidden_for_non_approver(self, client, admin_user, admin_token):
        """差戻しはステップの承認者だけが可能（403）。"""
        other_id, other_token = _create_user(
            client, admin_token, "wf-r4@example.com", "wf-r4", role="engineer"
        )
        _, project_id, wf = _workflow_doc(client, admin_token, [admin_user.id])
        step_id = wf["steps"][0]["id"]
        added = client.post(
            f"/api/v1/projects/{project_id}/members/{other_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert added.status_code == 204, added.text

        resp = client.post(
            f"/api/v1/workflows/{wf['id']}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "戻したい"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403

    def test_resubmit_as_non_admin_owner(self, client, admin_token):
        """admin ではない起票者でも自分の文書は再申請できる（設計 D5）。"""
        owner_id, owner_token = _create_user(
            client, admin_token, "wf-owner@example.com", "wf-owner"
        )
        project_id = _create_project(client, admin_token)
        # owner をプロジェクトメンバーにしてから owner 本人が文書を登録する
        added = client.post(
            f"/api/v1/projects/{project_id}/members/{owner_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert added.status_code == 204, added.text
        doc_id = _upload_doc(client, owner_token, project_id)
        wf = client.post(
            "/api/v1/workflows/",
            json={"document_id": doc_id, "approver_ids": [owner_id]},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert wf.status_code == 201, wf.text
        workflow_id = wf.json()["id"]
        step_id = wf.json()["steps"][0]["id"]

        returned = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step_id}/decide",
            json={"decision": "return", "comment": "要修正"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert returned.status_code == 200, returned.text

        resp = client.post(
            f"/api/v1/workflows/{workflow_id}/resubmit",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "in_progress"

        # 二度目の再申請は returned ではないので 409
        again = client.post(
            f"/api/v1/workflows/{workflow_id}/resubmit",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert again.status_code == 409

    def test_decide_is_blocked_while_returned(self, client, admin_user, admin_token):
        """差戻し中は再申請するまで承認・却下・再差戻しを受け付けない（設計 D2）。

        ここを許すと、差戻しされた依頼が resubmit を経ずに承認完了へ進む。
        """
        approver2_id, approver2_token = _create_user(
            client, admin_token, "wf-r5@example.com", "wf-r5"
        )
        _, _, wf = _workflow_doc(client, admin_token, [admin_user.id, approver2_id])
        step1_id = next(s["id"] for s in wf["steps"] if s["order"] == 1)
        step2_id = next(s["id"] for s in wf["steps"] if s["order"] == 2)
        workflow_id = wf["id"]

        returned = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step2_id}/decide",
            json={"decision": "return", "comment": "全体を戻す"},
            headers={"Authorization": f"Bearer {approver2_token}"},
        )
        assert returned.status_code == 200, returned.text
        assert returned.json()["status"] == "returned"

        # 差戻し中の承認は 409（resubmit を経ずに完了させられない）
        blocked = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step1_id}/decide",
            json={"decision": "approve", "comment": "ついでに承認"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert blocked.status_code == 409
        assert "resubmit" in blocked.json()["detail"]

        # 却下も同様に 409
        rejected = client.post(
            f"/api/v1/workflows/{workflow_id}/steps/{step1_id}/decide",
            json={"decision": "reject"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rejected.status_code == 409

        # 再申請で再開できる
        resumed = client.post(
            f"/api/v1/workflows/{workflow_id}/resubmit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "in_progress"
        assert [s["status"] for s in resumed.json()["steps"]] == [
            "pending",
            "pending",
        ]

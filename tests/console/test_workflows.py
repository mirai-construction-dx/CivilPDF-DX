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
        client.post("/api/v1/workflows/", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
        resp = client.post("/api/v1/workflows/", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
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
            json={"email": "other@example.com", "username": "other1", "full_name": "Other", "password": "Other123!"},
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
        resp = client.get(f"/api/v1/workflows/{workflow_id}", headers={"Authorization": f"Bearer {admin_token}"})
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

    def test_multi_step_workflow_next_step_activated(self, client, admin_user, admin_token):
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

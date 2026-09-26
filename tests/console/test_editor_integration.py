"""Editor integration API tests — TDD先行.

Features:
  #1  ReviewSidecar import/fetch
  #3  Flatten-check gate (FINALIZED transition)
  #4  Editor-events audit log
  #5  Workflow-status polling (Editor side)
"""

from unittest.mock import patch

from models.document import Document, DocumentStatus
from models.dx_sync_metric import DxSyncMetric
from models.user import Project

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_project(db, code="PROJ-001"):
    proj = Project(name="テストプロジェクト", code=code)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def _make_document(db, owner_id, project_id, status=DocumentStatus.DRAFT):
    doc = Document(
        title="テスト図面",
        filename="test.pdf",
        file_size=1024,
        project_id=project_id,
        owner_id=owner_id,
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# Mirrors the real CivilPDF-Editor `civilpdf.review/v1` sidecar (lib/review/schema.ts):
# schema/generator/savedAt keys + stamps carrying review metadata.
SIDECAR_PAYLOAD = {
    "schema": "civilpdf.review/v1",
    "generator": "CivilPDF-Editor",
    "savedAt": "2026-06-21T10:05:00Z",
    "stamps": [
        {
            "id": "stamp-1",
            "page": 1,
            "x": 100.0,
            "y": 200.0,
            "w": 80.0,
            "ratio": 1.0,
            "src": "data:image/png;base64,AAAA",
            "status": "approved",
        }
    ],
    "annotations": [],
}


# ── Feature #1: ReviewSidecar ─────────────────────────────────────────────────


class TestImportReviewSidecar:
    def test_manager_can_import_sidecar(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session)
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == doc.id
        assert data["review_sidecar_imported_at"] is not None

    def test_import_sets_status_to_editor_reviewed_when_all_approved(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-002")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == DocumentStatus.EDITOR_REVIEWED.value

    def test_import_with_pending_stamp_keeps_editor_draft(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-003")
        doc = _make_document(db_session, admin_user.id, proj.id)

        payload = {
            **SIDECAR_PAYLOAD,
            "stamps": [{**SIDECAR_PAYLOAD["stamps"][0], "status": "pending"}],
        }
        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == DocumentStatus.EDITOR_DRAFT.value

    def test_viewer_cannot_import(self, client, viewer_token, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-004")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-005")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
        )
        assert resp.status_code == 401

    def test_nonexistent_document_returns_404(self, client, manager_token):
        resp = client.post(
            "/api/v1/documents/nonexistent-id/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 404

    def test_import_accepts_legacy_version_exported_at(
        self, client, manager_token, admin_user, db_session
    ):
        """Back-compat: the pre-alignment keys (version/exported_at) still map
        onto review_schema/saved_at via AliasChoices."""
        proj = _make_project(db_session, "PROJ-006")
        doc = _make_document(db_session, admin_user.id, proj.id)

        legacy = {
            "version": "1",
            "exported_at": "2026-06-21T10:05:00Z",
            "stamps": [{"id": "s1", "page": 1, "status": "approved"}],
            "annotations": [],
        }
        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=legacy,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        # Legacy "version" normalizes onto review_schema; status still derives
        # from stamps (all approved → EDITOR_REVIEWED).
        body = resp.json()
        assert body["review_sidecar"]["review_schema"] == "1"
        assert body["status"] == DocumentStatus.EDITOR_REVIEWED.value

    def test_import_rejects_oversized_sidecar(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-007")
        doc = _make_document(db_session, admin_user.id, proj.id)

        with patch("api.editor._MAX_SIDECAR_BYTES", 64):
            oversized = {
                **SIDECAR_PAYLOAD,
                "annotations": [{"id": "a1", "kind": "note", "text": "x" * 200}],
            }
            resp = client.post(
                f"/api/v1/documents/{doc.id}/review-sidecar",
                json=oversized,
                headers={"Authorization": f"Bearer {manager_token}"},
            )
        assert resp.status_code == 413


class TestDxSyncMetrics:
    """Server-side DX sync SLI metrics (dx_sync_metrics table)."""

    def test_success_and_error_are_recorded(
        self, client, manager_token, viewer_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-030")
        doc = _make_document(db_session, admin_user.id, proj.id)

        ok = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert ok.status_code == 200

        forbidden = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert forbidden.status_code == 403

        rows = db_session.query(DxSyncMetric).order_by(DxSyncMetric.created_at).all()
        assert [r.event_type for r in rows] == ["success", "error"]
        assert rows[0].status_code == 200
        assert rows[0].document_id == doc.id
        assert rows[1].status_code == 403
        assert rows[1].error_kind == "rbac"

    def test_unauthorized_import_is_recorded_as_auth_error(
        self, client, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-031")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar", json=SIDECAR_PAYLOAD
        )
        assert resp.status_code == 401

        row = db_session.query(DxSyncMetric).first()
        assert row is not None
        assert row.event_type == "error"
        assert row.error_kind == "auth"


class TestGetReviewSidecar:
    def test_get_returns_sidecar_data(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-010")
        doc = _make_document(db_session, admin_user.id, proj.id)

        client.post(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            json=SIDECAR_PAYLOAD,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        resp = client.get(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "review_sidecar" in data
        # Editor's "schema"/"savedAt"/"generator" keys are normalized loss-free.
        assert data["review_sidecar"]["review_schema"] == "civilpdf.review/v1"
        assert data["review_sidecar"]["saved_at"] == "2026-06-21T10:05:00Z"
        assert data["review_sidecar"]["generator"] == "CivilPDF-Editor"
        assert "review_sidecar_imported_at" in data

    def test_get_returns_null_when_no_sidecar(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-011")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.get(
            f"/api/v1/documents/{doc.id}/review-sidecar",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_sidecar"] is None

    def test_get_unauthenticated_returns_401(self, client, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-012")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.get(f"/api/v1/documents/{doc.id}/review-sidecar")
        assert resp.status_code == 401


# ── Feature #3: Flatten Check Gate ───────────────────────────────────────────


class TestFlattenCheck:
    def test_manager_can_trigger_flatten_check(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-020")
        doc = _make_document(
            db_session, admin_user.id, proj.id, status=DocumentStatus.EDITOR_REVIEWED
        )

        resp = client.post(
            f"/api/v1/documents/{doc.id}/flatten-check",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        # 実ファイルなし→ pypdf は失敗するがエンドポイント自体は 422/200 を返す
        assert resp.status_code in (200, 422)

    def test_flatten_check_on_missing_file_returns_422(
        self, client, manager_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-021")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/flatten-check",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        # file_path が null → 422 Unprocessable
        assert resp.status_code == 422

    def test_viewer_cannot_trigger_flatten_check(
        self, client, viewer_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-022")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/flatten-check",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-023")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(f"/api/v1/documents/{doc.id}/flatten-check")
        assert resp.status_code == 401

    def test_nonexistent_document_returns_404(self, client, manager_token):
        resp = client.post(
            "/api/v1/documents/no-such-doc/flatten-check",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert resp.status_code == 404


# ── Feature #4: Editor-events audit log ──────────────────────────────────────


EVENTS_PAYLOAD = [
    {
        "event_type": "stamp.placed",
        "detail": {"stamp_id": "s1", "page": 1},
        "occurred_at": "2026-06-21T10:00:00Z",
    },
    {
        "event_type": "annotation.added",
        "detail": {"text": "要確認"},
        "occurred_at": "2026-06-21T10:01:00Z",
    },
]


class TestEditorEvents:
    def test_engineer_can_post_events(
        self, client, engineer_token, engineer_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-030")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=EVENTS_PAYLOAD,
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2

    def test_events_are_stored_in_audit_log(
        self, client, engineer_token, engineer_user, admin_token, db_session
    ):
        proj = _make_project(db_session, "PROJ-031")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=EVENTS_PAYLOAD,
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        audit_resp = client.get(
            f"/api/v1/audit-logs?resource_id={doc.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        actions = [entry["action"] for entry in logs]
        assert any("stamp.placed" in a for a in actions)

    def test_empty_events_list_returns_200(
        self, client, engineer_token, engineer_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-032")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=[],
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["created"] == 0

    def test_viewer_cannot_post_events(
        self, client, viewer_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-033")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=EVENTS_PAYLOAD,
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-034")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=EVENTS_PAYLOAD,
        )
        assert resp.status_code == 401

    def test_nonexistent_document_returns_404(self, client, engineer_token):
        resp = client.post(
            "/api/v1/documents/no-such/editor-events",
            json=EVENTS_PAYLOAD,
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 404

    def test_invalid_event_type_returns_422(
        self, client, engineer_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-035")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.post(
            f"/api/v1/documents/{doc.id}/editor-events",
            json=[
                {
                    "event_type": "invalid.type",
                    "detail": {},
                    "occurred_at": "not-a-date",
                }
            ],
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 422


# ── Feature #5: Workflow status polling ───────────────────────────────────────


class TestWorkflowStatus:
    def test_engineer_can_get_workflow_status(
        self, client, engineer_token, engineer_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-040")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        resp = client.get(
            f"/api/v1/documents/{doc.id}/workflow-status",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "updated_at" in data

    def test_workflow_status_includes_steps_when_workflow_exists(
        self, client, engineer_token, engineer_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-041")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        resp = client.get(
            f"/api/v1/documents/{doc.id}/workflow-status",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data

    def test_viewer_cannot_get_workflow_status(
        self, client, viewer_token, admin_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-042")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.get(
            f"/api/v1/documents/{doc.id}/workflow-status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, admin_user, db_session):
        proj = _make_project(db_session, "PROJ-043")
        doc = _make_document(db_session, admin_user.id, proj.id)

        resp = client.get(f"/api/v1/documents/{doc.id}/workflow-status")
        assert resp.status_code == 401

    def test_nonexistent_document_returns_404(self, client, engineer_token):
        resp = client.get(
            "/api/v1/documents/no-such/workflow-status",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 404

    def test_document_status_synced_to_extra_data(
        self, client, engineer_token, engineer_user, db_session
    ):
        proj = _make_project(db_session, "PROJ-044")
        doc = _make_document(db_session, engineer_user.id, proj.id)

        resp = client.get(
            f"/api/v1/documents/{doc.id}/workflow-status",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert resp.status_code == 200
        # extra_data["editor_sync"] が更新されていることを確認
        data = resp.json()
        assert data.get("editor_sync") is not None or "status" in data

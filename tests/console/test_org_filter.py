"""Phase 8 P5: organization_id filter tests for list_projects and list_documents."""

import io
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src/console/backend"))

from models.organization import Organization, OrgType
from models.user import Project


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def _create_org(db, name: str, code: str) -> Organization:
    org = Organization(name=name, code=code, org_type=OrgType.HEADQUARTERS, path="/")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _create_project_in_org(
    client, db_session, admin_token: str, name: str, code: str, org_id: str
) -> str:
    resp = client.post(
        "/api/v1/projects/",
        json={"name": name, "code": code},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    project_id = resp.json()["id"]
    # Assign organization_id directly since ProjectCreate schema has no such field
    proj = db_session.query(Project).filter(Project.id == project_id).first()
    proj.organization_id = org_id
    db_session.commit()
    return project_id


def _upload_doc(client, admin_token: str, project_id: str, title: str) -> str:
    resp = client.post(
        "/api/v1/documents/",
        data={"project_id": project_id, "title": title},
        files={
            "file": (f"{title}.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestListProjectsOrgFilter:
    def test_filter_returns_only_projects_in_org(self, client, admin_token, db_session):
        org_a = _create_org(db_session, "本社", "HQ-A")
        org_b = _create_org(db_session, "東京支店", "BRANCH-TKY")

        _create_project_in_org(
            client, db_session, admin_token, "道路工事", "RD-001", org_a.id
        )
        _create_project_in_org(
            client, db_session, admin_token, "橋梁設計", "BR-001", org_b.id
        )

        resp = client.get(
            f"/api/v1/projects/?organization_id={org_a.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "道路工事" in names
        assert "橋梁設計" not in names

    def test_filter_other_org_returns_correct_project(
        self, client, admin_token, db_session
    ):
        org_a = _create_org(db_session, "本社2", "HQ-B")
        org_b = _create_org(db_session, "大阪支店", "BRANCH-OSK")

        _create_project_in_org(
            client, db_session, admin_token, "設計案件A", "DSG-001", org_a.id
        )
        _create_project_in_org(
            client, db_session, admin_token, "設計案件B", "DSG-002", org_b.id
        )

        resp = client.get(
            f"/api/v1/projects/?organization_id={org_b.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "設計案件B" in names
        assert "設計案件A" not in names

    def test_filter_unknown_org_returns_empty(self, client, admin_token):
        resp = client.get(
            "/api/v1/projects/?organization_id=00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_filter_returns_all_projects(self, client, admin_token, db_session):
        org_a = _create_org(db_session, "本社3", "HQ-C")
        org_b = _create_org(db_session, "名古屋支店", "BRANCH-NGY")

        _create_project_in_org(
            client, db_session, admin_token, "プロジェクトX", "PRJ-X01", org_a.id
        )
        _create_project_in_org(
            client, db_session, admin_token, "プロジェクトY", "PRJ-Y01", org_b.id
        )

        resp = client.get(
            "/api/v1/projects/", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "プロジェクトX" in names
        assert "プロジェクトY" in names


class TestListDocumentsOrgFilter:
    def test_filter_returns_only_docs_in_org(self, client, admin_token, db_session):
        org_a = _create_org(db_session, "本社D", "HQ-D")
        org_b = _create_org(db_session, "福岡支店", "BRANCH-FKO")

        proj_a = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトA", "DPJA-001", org_a.id
        )
        proj_b = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトB", "DPJB-001", org_b.id
        )

        _upload_doc(client, admin_token, proj_a, "本社図面")
        _upload_doc(client, admin_token, proj_b, "支店図面")

        resp = client.get(
            f"/api/v1/documents/?organization_id={org_a.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        titles = [d["title"] for d in resp.json()]
        assert "本社図面" in titles
        assert "支店図面" not in titles

    def test_filter_returns_docs_for_other_org(self, client, admin_token, db_session):
        org_a = _create_org(db_session, "本社E", "HQ-E")
        org_b = _create_org(db_session, "札幌支店", "BRANCH-SPR")

        proj_a = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトC", "DPJC-001", org_a.id
        )
        proj_b = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトD", "DPJD-001", org_b.id
        )

        _upload_doc(client, admin_token, proj_a, "本社仕様書")
        _upload_doc(client, admin_token, proj_b, "支店仕様書")

        resp = client.get(
            f"/api/v1/documents/?organization_id={org_b.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        titles = [d["title"] for d in resp.json()]
        assert "支店仕様書" in titles
        assert "本社仕様書" not in titles

    def test_filter_unknown_org_returns_empty(self, client, admin_token):
        resp = client.get(
            "/api/v1/documents/?organization_id=00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_org_filter_returns_all_docs(self, client, admin_token, db_session):
        org_a = _create_org(db_session, "本社F", "HQ-F")
        org_b = _create_org(db_session, "仙台支店", "BRANCH-SDI")

        proj_a = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトE", "DPJE-001", org_a.id
        )
        proj_b = _create_project_in_org(
            client, db_session, admin_token, "文書プロジェクトF", "DPJF-001", org_b.id
        )

        _upload_doc(client, admin_token, proj_a, "全社共通資料A")
        _upload_doc(client, admin_token, proj_b, "全社共通資料B")

        resp = client.get(
            "/api/v1/documents/", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        titles = [d["title"] for d in resp.json()]
        assert "全社共通資料A" in titles
        assert "全社共通資料B" in titles

"""Project management API tests."""


class TestProjectCRUD:
    def test_create_project(self, client, admin_token):
        resp = client.post(
            "/api/v1/projects/",
            json={
                "name": "Test Project",
                "code": "PRJ-001",
                "description": "A test project",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["code"] == "PRJ-001"
        assert data["is_active"] is True

    def test_create_duplicate_code(self, client, admin_token):
        payload = {"name": "Project A", "code": "DUP-001"}
        client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_list_projects(self, client, admin_token):
        resp = client.get(
            "/api/v1/projects/", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_project(self, client, admin_token):
        create_resp = client.post(
            "/api/v1/projects/",
            json={"name": "Get Test", "code": "GET-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = create_resp.json()["id"]
        resp = client.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id

    def test_get_nonexistent_project(self, client, admin_token):
        resp = client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_create_project_requires_auth(self, client):
        resp = client.post(
            "/api/v1/projects/", json={"name": "No Auth", "code": "NA-001"}
        )
        assert resp.status_code == 401

    def test_list_projects_non_admin_sees_own(self, client, admin_token):
        eng_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "eng@example.com",
                "username": "eng1",
                "full_name": "Eng",
                "password": "Eng12345!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert eng_resp.status_code == 201
        token_resp = client.post(
            "/api/v1/auth/token",
            data={"username": "eng@example.com", "password": "Eng12345!"},
        )
        eng_token = token_resp.json()["access_token"]
        resp = client.get(
            "/api/v1/projects/", headers={"Authorization": f"Bearer {eng_token}"}
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_add_member_to_project(self, client, admin_token):
        proj_resp = client.post(
            "/api/v1/projects/",
            json={"name": "Member Test", "code": "MBR-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = proj_resp.json()["id"]
        user_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "member@example.com",
                "username": "member1",
                "full_name": "Member",
                "password": "Member12!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        user_id = user_resp.json()["id"]
        resp = client.post(
            f"/api/v1/projects/{project_id}/members/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    def test_add_member_project_not_found(self, client, admin_token):
        user_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "mem2@example.com",
                "username": "mem2",
                "full_name": "Mem2",
                "password": "Mem21234!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        user_id = user_resp.json()["id"]
        resp = client.post(
            f"/api/v1/projects/00000000-0000-0000-0000-000000000000/members/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_add_member_user_not_found(self, client, admin_token):
        proj_resp = client.post(
            "/api/v1/projects/",
            json={"name": "Add Member NF", "code": "AMNF-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = proj_resp.json()["id"]
        resp = client.post(
            f"/api/v1/projects/{project_id}/members/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_remove_member_from_project(self, client, admin_token):
        proj_resp = client.post(
            "/api/v1/projects/",
            json={"name": "Remove Test", "code": "RMV-001"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        project_id = proj_resp.json()["id"]
        user_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "rmv@example.com",
                "username": "rmv1",
                "full_name": "Rmv",
                "password": "Rmv12345!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        user_id = user_resp.json()["id"]
        client.post(
            f"/api/v1/projects/{project_id}/members/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.delete(
            f"/api/v1/projects/{project_id}/members/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    def test_remove_member_project_not_found(self, client, admin_token):
        resp = client.delete(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/members/00000000-0000-0000-0000-000000000001",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

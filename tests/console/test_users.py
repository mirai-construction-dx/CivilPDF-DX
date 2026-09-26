"""User management API tests."""


class TestUserCRUD:
    def test_create_user(self, client, admin_token):
        resp = client.post(
            "/api/v1/users/",
            json={
                "email": "engineer@example.com",
                "username": "engineer1",
                "full_name": "Test Engineer",
                "password": "Engineer123!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "engineer@example.com"
        assert data["role"] == "engineer"
        assert "hashed_password" not in data

    def test_create_duplicate_email(self, client, admin_token):
        payload = {
            "email": "dup@example.com",
            "username": "dup1",
            "full_name": "Dup User",
            "password": "Dup12345!",
        }
        client.post(
            "/api/v1/users/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.post(
            "/api/v1/users/",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_create_user_weak_password(self, client, admin_token):
        resp = client.post(
            "/api/v1/users/",
            json={
                "email": "weak@example.com",
                "username": "weak1",
                "full_name": "Weak Pass",
                "password": "short",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_list_users(self, client, admin_token):
        resp = client.get(
            "/api/v1/users/",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_users_requires_admin(self, client, admin_token):
        client.post(
            "/api/v1/users/",
            json={
                "email": "viewer@example.com",
                "username": "viewer1",
                "full_name": "Viewer",
                "password": "Viewer123!",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        viewer_resp = client.post(
            "/api/v1/auth/token",
            data={"username": "viewer@example.com", "password": "Viewer123!"},
        )
        viewer_token = viewer_resp.json()["access_token"]
        resp = client.get(
            "/api/v1/users/", headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert resp.status_code == 403

    def test_create_duplicate_username(self, client, admin_token):
        client.post(
            "/api/v1/users/",
            json={
                "email": "first@example.com",
                "username": "taken",
                "full_name": "First",
                "password": "First123!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.post(
            "/api/v1/users/",
            json={
                "email": "second@example.com",
                "username": "taken",
                "full_name": "Second",
                "password": "Second123!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409
        assert "Username" in resp.json()["detail"]

    def test_get_user_by_admin(self, client, admin_user, admin_token):
        resp = client.get(
            f"/api/v1/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(admin_user.id)

    def test_get_user_forbidden_for_other_non_admin(self, client, admin_token):
        create_resp = client.post(
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
        engineer_id = create_resp.json()["id"]
        viewer_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "view@example.com",
                "username": "view1",
                "full_name": "View",
                "password": "View1234!",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        viewer_id = viewer_resp.json()["id"]
        token_resp = client.post(
            "/api/v1/auth/token",
            data={"username": "view@example.com", "password": "View1234!"},
        )
        viewer_token = token_resp.json()["access_token"]
        resp = client.get(
            f"/api/v1/users/{engineer_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
        assert viewer_id is not None  # suppress unused warning

    def test_get_user_not_found(self, client, admin_token):
        resp = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_update_user_role(self, client, admin_token):
        create_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "upd@example.com",
                "username": "upd1",
                "full_name": "Update",
                "password": "Update12!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        user_id = create_resp.json()["id"]
        resp = client.patch(
            f"/api/v1/users/{user_id}",
            json={"role": "manager"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "manager"

    def test_update_user_not_found(self, client, admin_token):
        resp = client.patch(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_delete_user(self, client, admin_token):
        create_resp = client.post(
            "/api/v1/users/",
            json={
                "email": "del@example.com",
                "username": "del1",
                "full_name": "Del",
                "password": "Delete12!",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        user_id = create_resp.json()["id"]
        resp = client.delete(
            f"/api/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    def test_delete_user_not_found(self, client, admin_token):
        resp = client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_delete_self_forbidden(self, client, admin_user, admin_token):
        resp = client.delete(
            f"/api/v1/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

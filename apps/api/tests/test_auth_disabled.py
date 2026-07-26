"""Auth-free contract.

Authentication has been removed: no cookie is required, every request runs as
the fixed default admin (a PLATFORM_ADMIN), and writes succeed. These replace
the former login/session/tenant-isolation suite, which asserted behavior that no
longer exists.
"""

from atip_api.auth import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_NAME, DEFAULT_ORG_NAME


async def test_me_returns_default_admin_without_a_cookie(anon_client):
    response = await anon_client.get("/api/auth/me")  # no cookie sent
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == DEFAULT_ADMIN_EMAIL
    assert body["display_name"] == DEFAULT_ADMIN_NAME
    assert body["role"] == "PLATFORM_ADMIN"
    assert body["organization"]["name"] == DEFAULT_ORG_NAME


async def test_protected_routes_are_open_and_writable(anon_client):
    # a read that used to require auth now works with no cookie
    assert (await anon_client.get("/api/workspaces")).status_code == 200

    # and a write succeeds and persists
    created = await anon_client.post("/api/workspaces", json={"name": "Open WS"})
    assert created.status_code == 201
    ws_id = created.json()["id"]

    listed = (await anon_client.get("/api/workspaces")).json()
    assert any(w["id"] == ws_id for w in listed)


async def test_login_and_register_are_noops_returning_admin(anon_client):
    login = await anon_client.post(
        "/api/auth/login", json={"email": "whatever@x.test", "password": "does-not-matter"}
    )
    assert login.status_code == 200
    assert login.json()["email"] == DEFAULT_ADMIN_EMAIL

    logout = await anon_client.post("/api/auth/logout")
    assert logout.status_code == 204

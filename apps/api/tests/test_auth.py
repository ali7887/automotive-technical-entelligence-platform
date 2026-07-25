"""Authentication and RBAC boundaries.

Contract under test:
- no cookie / bad cookie / expired session -> 401 problem details
- login sets an HttpOnly SameSite=Strict cookie; logout revokes server-side
- cross-organization workspace access -> 404 (existence is not leaked)
- same-org, no membership -> 403; viewer hitting editor routes -> 403
- org_admin bypasses memberships inside its org only
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from atip_api.auth import hash_password, hash_token
from atip_api.config import get_settings
from atip_api.db import get_session_factory
from atip_api.main import create_app
from atip_api.models import (
    Organization,
    Session,
    User,
    UserRole,
    WorkspaceMember,
    WorkspaceRole,
)

from .pdf_utils import pdf_with_text

_PASSWORD = "correct-horse-battery"
_PAGES = ["S5.1 General requirements\nEach headlamp shall conform to Table XIX."]


async def _make_user(
    *,
    email: str,
    org_name: str,
    role: UserRole = UserRole.MEMBER,
    password: str = _PASSWORD,
    token: str | None = None,
) -> User:
    """Create org (if needed) + user (+ session when `token` is given)."""
    from sqlalchemy import select

    async with get_session_factory()() as db:
        org = (await db.scalars(select(Organization).where(Organization.name == org_name))).first()
        if org is None:
            org = Organization(name=org_name)
            db.add(org)
            await db.flush()
        user = User(
            organization_id=org.id,
            email=email,
            password_hash=hash_password(password),
            display_name=email.split("@", 1)[0],
            role=role,
        )
        db.add(user)
        await db.flush()
        if token is not None:
            db.add(
                Session(
                    user_id=user.id,
                    token_hash=hash_token(token),
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        await db.commit()
        return user


def _client_with(token: str | None) -> AsyncClient:
    cookies = {get_settings().session_cookie_name: token} if token else None
    return AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test", cookies=cookies
    )


async def _grant(workspace_id: str, user: User, role: WorkspaceRole) -> None:
    async with get_session_factory()() as db:
        db.add(
            WorkspaceMember(
                workspace_id=uuid.UUID(workspace_id), user_id=user.id, role=role
            )
        )
        await db.commit()


# --- authentication ---


async def test_routes_require_authentication(anon_client):
    for method, path in [
        ("GET", "/api/workspaces"),
        ("POST", "/api/workspaces"),
        ("GET", f"/api/workspaces/{uuid.uuid4()}/documents"),
        ("POST", f"/api/workspaces/{uuid.uuid4()}/search"),
        ("POST", f"/api/workspaces/{uuid.uuid4()}/ask"),
        ("GET", f"/api/workspaces/{uuid.uuid4()}/chat?question=x"),
        ("GET", f"/api/documents/{uuid.uuid4()}"),
        ("GET", f"/api/jobs/{uuid.uuid4()}"),
        ("GET", "/api/evidence/review-queue"),
        ("GET", "/api/auth/me"),
    ]:
        response = await anon_client.request(method, path, json={})
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
        body = response.json()
        assert body["code"] == "authentication_required"
        assert body["request_id"], "problem details must carry the correlation id"


async def test_health_stays_public(anon_client):
    assert (await anon_client.get("/health/live")).status_code == 200


async def test_login_sets_cookie_and_me_returns_user(anon_client):
    await _make_user(email="eng@acme.test", org_name="ACME", role=UserRole.MEMBER)

    bad = await anon_client.post(
        "/api/auth/login", json={"email": "eng@acme.test", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"

    ok = await anon_client.post(
        "/api/auth/login", json={"email": "eng@acme.test", "password": _PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["email"] == "eng@acme.test"
    assert ok.json()["organization"]["name"] == "ACME"
    set_cookie = ok.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie.lower().replace(
        "samesite=strict", "SameSite=strict"
    )

    me = await anon_client.get("/api/auth/me")  # cookie persisted on the client
    assert me.status_code == 200
    assert me.json()["email"] == "eng@acme.test"


async def test_logout_revokes_session_server_side(anon_client):
    await _make_user(email="out@acme.test", org_name="ACME-Out")
    login = await anon_client.post(
        "/api/auth/login", json={"email": "out@acme.test", "password": _PASSWORD}
    )
    assert login.status_code == 200
    assert (await anon_client.get("/api/auth/me")).status_code == 200

    assert (await anon_client.post("/api/auth/logout")).status_code == 204
    # even if a stolen copy of the cookie were replayed, the row is gone
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_logout_without_session_is_idempotent(anon_client):
    """Logout with no session cookie still succeeds and clears the cookie."""
    response = await anon_client.post("/api/auth/logout")
    assert response.status_code == 204
    # a Set-Cookie expiring the session is emitted even when none was presented
    assert get_settings().session_cookie_name in response.headers.get("set-cookie", "")


async def test_logout_blocks_protected_routes(anon_client):
    await _make_user(email="bye@acme.test", org_name="ACME-Bye")
    await anon_client.post(
        "/api/auth/login", json={"email": "bye@acme.test", "password": _PASSWORD}
    )
    assert (await anon_client.get("/api/workspaces")).status_code == 200

    assert (await anon_client.post("/api/auth/logout")).status_code == 204
    # the server-side session is revoked: protected routes now 401
    blocked = await anon_client.get("/api/workspaces")
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "authentication_required"


async def test_expired_session_is_rejected(_database):
    user = await _make_user(email="old@acme.test", org_name="ACME-Old", token=None)
    async with get_session_factory()() as db:
        db.add(
            Session(
                user_id=user.id,
                token_hash=hash_token("expired-token"),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await db.commit()
    async with _client_with("expired-token") as client:
        response = await client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.json()["code"] == "authentication_required"


# --- public self-service registration ---

_REGISTER = {
    "display_name": "Dana Engineer",
    "email": "dana@newco.test",
    "organization_name": "NewCo Automotive",
    "password": "correct-horse-9",
}


async def test_register_creates_org_admin_and_logs_in(anon_client):
    response = await anon_client.post("/api/auth/register", json=_REGISTER)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "dana@newco.test"
    assert body["display_name"] == "Dana Engineer"
    assert body["role"] == UserRole.ORG_ADMIN
    assert body["organization"]["name"] == "NewCo Automotive"

    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "samesite=strict" in set_cookie.lower()

    # the session cookie persists on the client: the user is logged straight in
    me = await anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "dana@newco.test"

    # org_admin can immediately create and use a workspace in the new org
    workspace = await anon_client.post("/api/workspaces", json={"name": "Homologation"})
    assert workspace.status_code == 201


async def test_register_normalizes_email(anon_client):
    payload = {**_REGISTER, "email": "Dana@NewCo.TEST"}
    response = await anon_client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["email"] == "dana@newco.test"


async def test_register_duplicate_email_is_409(anon_client):
    assert (await anon_client.post("/api/auth/register", json=_REGISTER)).status_code == 201
    # same email (case-insensitive), different org name
    dup = await anon_client.post(
        "/api/auth/register",
        json={**_REGISTER, "email": "DANA@newco.test", "organization_name": "Other Org"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "email_already_registered"


async def test_register_duplicate_organization_is_409(anon_client):
    assert (await anon_client.post("/api/auth/register", json=_REGISTER)).status_code == 201
    # different email, same organization name (case-insensitive)
    dup = await anon_client.post(
        "/api/auth/register",
        json={**_REGISTER, "email": "someone@newco.test", "organization_name": "newco automotive"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "organization_exists"


async def test_register_rejects_weak_or_invalid_input(anon_client, monkeypatch):
    # this exercises validation, not throttling: lift the register limit so the
    # several invalid attempts below are not turned into 429s
    monkeypatch.setattr(get_settings(), "rate_limit_register_per_minute", 100)
    cases = [
        {**_REGISTER, "password": "short-1"},  # < 8 chars
        {**_REGISTER, "password": "no-digits-here"},  # missing a digit
        {**_REGISTER, "password": "12345678"},  # missing a letter
        {**_REGISTER, "password": _REGISTER["email"]},  # equals the email
        # <= 72 characters but > 72 bytes: must be 422, never a bcrypt 500
        {**_REGISTER, "password": "é" * 70 + "a1"},
        {**_REGISTER, "email": "not-an-email"},  # invalid email
        {**_REGISTER, "display_name": ""},  # empty name
        {**_REGISTER, "organization_name": "   "},  # blank org after trim
    ]
    for payload in cases:
        response = await anon_client.post("/api/auth/register", json=payload)
        assert response.status_code == 422, payload
        assert response.json()["code"] == "validation_error"
    # nothing was persisted by the rejected attempts
    login = await anon_client.post(
        "/api/auth/login",
        json={"email": _REGISTER["email"], "password": _REGISTER["password"]},
    )
    assert login.status_code == 401


async def test_register_multibyte_password_is_422_not_500(anon_client):
    """Regression: a password <= 72 chars but > 72 bytes must be rejected by
    validation, not raise inside bcrypt and surface as a 500."""
    response = await anon_client.post(
        "/api/auth/register",
        json={**_REGISTER, "password": "pä55word-" + "ü" * 40},  # ~80+ bytes
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_register_accepts_72_byte_password(anon_client):
    """The 72-byte boundary itself is valid and must succeed."""
    password = "a1" + "b" * 70  # exactly 72 ASCII bytes, has a letter and a digit
    assert len(password.encode("utf-8")) == 72
    response = await anon_client.post(
        "/api/auth/register", json={**_REGISTER, "password": password}
    )
    assert response.status_code == 201


async def test_register_is_rate_limited(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_register_per_minute", 2)
    ok1 = await anon_client.post(
        "/api/auth/register", json={**_REGISTER, "email": "a@r.test", "organization_name": "R A"}
    )
    ok2 = await anon_client.post(
        "/api/auth/register", json={**_REGISTER, "email": "b@r.test", "organization_name": "R B"}
    )
    assert ok1.status_code == 201 and ok2.status_code == 201
    limited = await anon_client.post(
        "/api/auth/register", json={**_REGISTER, "email": "c@r.test", "organization_name": "R C"}
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert "retry-after" in limited.headers


# --- tenant isolation & workspace roles ---


async def test_cross_org_workspace_is_404_not_403(client):
    """A workspace in another organization must be indistinguishable from a
    missing one — on reads, writes, search, chat, and uploads."""
    ws = (await client.post("/api/workspaces", json={"name": "Org A ws"})).json()

    await _make_user(
        email="rival@other.test", org_name="Other Org", role=UserRole.ORG_ADMIN,
        token="rival-token",
    )
    async with _client_with("rival-token") as rival:
        assert (await rival.get(f"/api/workspaces/{ws['id']}")).status_code == 404
        assert (
            await rival.post(f"/api/workspaces/{ws['id']}/search", json={"query": "brakes"})
        ).status_code == 404
        assert (
            await rival.get(f"/api/workspaces/{ws['id']}/chat", params={"question": "x"})
        ).status_code == 404
        upload = await rival.post(
            f"/api/workspaces/{ws['id']}/documents",
            files={"file": ("a.pdf", pdf_with_text(_PAGES), "application/pdf")},
        )
        assert upload.status_code == 404
        assert (await rival.get("/api/workspaces")).json() == []


async def test_member_without_membership_gets_403(client, auth_user):
    ws = (await client.post("/api/workspaces", json={"name": "Members only"})).json()

    # same organization as the default fixture user, but no membership row
    await _make_user(
        email="peer@example.com", org_name="Test Org", role=UserRole.MEMBER,
        token="peer-token",
    )
    async with _client_with("peer-token") as peer:
        response = await peer.get(f"/api/workspaces/{ws['id']}")
        assert response.status_code == 403
        body = response.json()
        assert body["code"] == "forbidden"
        assert body["title"] == "Forbidden"
        assert body["request_id"]
        # and it is absent from their listing
        assert (await peer.get("/api/workspaces")).json() == []


async def test_viewer_can_read_but_not_mutate(client, auth_user):
    ws = (await client.post("/api/workspaces", json={"name": "Viewer ws"})).json()
    upload = await client.post(
        f"/api/workspaces/{ws['id']}/documents",
        files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    doc_id = upload.json()["document"]["id"]

    viewer = await _make_user(
        email="viewer@example.com", org_name="Test Org", role=UserRole.MEMBER,
        token="viewer-token",
    )
    await _grant(ws["id"], viewer, WorkspaceRole.WORKSPACE_VIEWER)

    async with _client_with("viewer-token") as vc:
        # reads work: listing, search, document detail + file
        assert (await vc.get(f"/api/workspaces/{ws['id']}")).status_code == 200
        assert (
            await vc.post(f"/api/workspaces/{ws['id']}/search", json={"query": "headlamp"})
        ).status_code == 200
        assert (await vc.get(f"/api/documents/{doc_id}")).status_code == 200
        assert (await vc.get(f"/api/documents/{doc_id}/file")).status_code == 200
        assert [w["id"] for w in (await vc.get("/api/workspaces")).json()] == [ws["id"]]

        # mutations are editor-only
        assert (
            await vc.post(
                f"/api/workspaces/{ws['id']}/documents",
                files={"file": ("b.pdf", pdf_with_text(_PAGES), "application/pdf")},
            )
        ).status_code == 403
        assert (
            await vc.patch(f"/api/workspaces/{ws['id']}", json={"name": "renamed"})
        ).status_code == 403
        assert (await vc.delete(f"/api/workspaces/{ws['id']}")).status_code == 403
        assert (await vc.post(f"/api/documents/{doc_id}/evidence/extract")).status_code == 403


async def test_editor_membership_can_mutate(client, auth_user):
    ws = (await client.post("/api/workspaces", json={"name": "Editor ws"})).json()
    editor = await _make_user(
        email="editor@example.com", org_name="Test Org", role=UserRole.MEMBER,
        token="editor-token",
    )
    await _grant(ws["id"], editor, WorkspaceRole.WORKSPACE_EDITOR)

    async with _client_with("editor-token") as ec:
        upload = await ec.post(
            f"/api/workspaces/{ws['id']}/documents",
            files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
        )
        assert upload.status_code == 202
        assert (
            await ec.patch(f"/api/workspaces/{ws['id']}", json={"name": "renamed"})
        ).status_code == 200


async def test_document_and_job_routes_enforce_tenancy(client):
    ws = (await client.post("/api/workspaces", json={"name": "Docs ws"})).json()
    upload = await client.post(
        f"/api/workspaces/{ws['id']}/documents",
        files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    doc_id = upload.json()["document"]["id"]
    job_id = upload.json()["job"]["id"]

    await _make_user(
        email="spy@other.test", org_name="Spy Org", role=UserRole.ORG_ADMIN,
        token="spy-token",
    )
    async with _client_with("spy-token") as spy:
        assert (await spy.get(f"/api/documents/{doc_id}")).status_code == 404
        assert (await spy.get(f"/api/documents/{doc_id}/file")).status_code == 404
        assert (await spy.get(f"/api/jobs/{job_id}")).status_code == 404


async def test_review_queue_is_tenant_scoped_without_workspace_filter(client, monkeypatch):
    """Without workspace_id the queue only shows the caller's workspaces."""
    import json as jsonlib
    from collections.abc import AsyncIterator

    class ExtractionFakeLLM:
        def __init__(self, quote: str) -> None:
            self.quote = quote

        async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
            payload = {
                "requirements": [
                    {
                        "text": "Each headlamp shall conform to Table XIX.",
                        "citations": [{"source": 1, "quote": self.quote}],
                    }
                ]
            }
            yield jsonlib.dumps(payload)

    ws = (await client.post("/api/workspaces", json={"name": "Queue ws"})).json()
    upload = await client.post(
        f"/api/workspaces/{ws['id']}/documents",
        files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    doc_id = upload.json()["document"]["id"]
    monkeypatch.setattr(
        "atip_api.ai.llm.get_llm_client",
        lambda s: ExtractionFakeLLM("Each headlamp shall conform to Table XIX."),
    )
    assert (await client.post(f"/api/documents/{doc_id}/evidence/extract")).status_code == 201
    assert (await client.get("/api/evidence/review-queue")).json()["total"] == 1

    await _make_user(
        email="outsider@other.test", org_name="Outsider Org", role=UserRole.ORG_ADMIN,
        token="outsider-token",
    )
    async with _client_with("outsider-token") as outsider:
        assert (await outsider.get("/api/evidence/review-queue")).json()["total"] == 0

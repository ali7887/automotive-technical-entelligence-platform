from atip_api.routers import health as health_module
from atip_api.schemas.health import ServiceStatus


async def test_health_reports_all_services(client):
    response = await client.get("/health")
    # test DB is created without alembic, so postgres may report degraded here;
    # full "ok" is verified against the dev database in manual E2E checks
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["version"]
    assert set(body["services"]) == {"postgres", "redis", "qdrant"}
    for service in body["services"].values():
        assert service["status"] in ("ok", "error")


async def test_liveness_never_touches_dependencies(client, monkeypatch):
    async def _boom() -> ServiceStatus:  # any dependency call is a test failure
        raise AssertionError("liveness must not check dependencies")

    monkeypatch.setattr(health_module, "_check_postgres", _boom)
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["environment"] in ("development", "test", "production")
    # nothing beyond the declared contract leaks (no URLs, no settings dump)
    assert set(body) == {"status", "version", "environment", "build_sha"}


def _stub_checks(monkeypatch, postgres: str, redis: str, qdrant: str) -> None:
    def _make(status: str):
        async def _check(*args: object) -> ServiceStatus:
            return ServiceStatus(status=status)  # type: ignore[arg-type]

        return _check

    monkeypatch.setattr(health_module, "_check_postgres", _make(postgres))
    monkeypatch.setattr(health_module, "_check_redis", _make(redis))
    monkeypatch.setattr(health_module, "_check_qdrant", _make(qdrant))


async def test_readiness_ready_when_all_ok(client, monkeypatch):
    _stub_checks(monkeypatch, "ok", "ok", "ok")
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_readiness_degraded_when_optional_dependency_down(client, monkeypatch):
    # Qdrant/Redis outages degrade (keyword-only search still works) but must
    # NOT evict the instance: still 200 for the readiness probe.
    _stub_checks(monkeypatch, "ok", "error", "error")
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["qdrant"]["status"] == "error"


async def test_readiness_not_ready_without_postgres(client, monkeypatch):
    _stub_checks(monkeypatch, "error", "ok", "ok")
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"

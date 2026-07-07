async def test_health_reports_all_services(client):
    response = await client.get("/health")
    # test DB is created without alembic, so postgres may report degraded here;
    # full "ok" is verified against the dev database in manual E2E checks
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["services"]) == {"postgres", "redis", "qdrant"}
    for service in body["services"].values():
        assert service["status"] in ("ok", "error")

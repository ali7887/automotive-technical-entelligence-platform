import uuid


async def test_create_and_get_workspace(client):
    created = await client.post("/api/workspaces", json={"name": "UNECE R155"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "UNECE R155"
    assert uuid.UUID(body["id"])

    fetched = await client.get(f"/api/workspaces/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "UNECE R155"


async def test_list_workspaces(client):
    assert (await client.get("/api/workspaces")).json() == []
    await client.post("/api/workspaces", json={"name": "ISO 26262"})
    await client.post("/api/workspaces", json={"name": "UNECE R156"})
    listed = await client.get("/api/workspaces")
    assert listed.status_code == 200
    assert {ws["name"] for ws in listed.json()} == {"ISO 26262", "UNECE R156"}


async def test_create_workspace_rejects_empty_name(client):
    response = await client.post("/api/workspaces", json={"name": ""})
    assert response.status_code == 422


async def test_get_missing_workspace_returns_404(client):
    response = await client.get(f"/api/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_rename_workspace(client):
    created = await client.post("/api/workspaces", json={"name": "Old name"})
    ws_id = created.json()["id"]
    renamed = await client.patch(f"/api/workspaces/{ws_id}", json={"name": "New name"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New name"


async def test_delete_workspace(client):
    created = await client.post("/api/workspaces", json={"name": "Temp"})
    ws_id = created.json()["id"]
    deleted = await client.delete(f"/api/workspaces/{ws_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/workspaces/{ws_id}")).status_code == 404

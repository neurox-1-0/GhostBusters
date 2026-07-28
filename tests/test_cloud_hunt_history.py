from fastapi.testclient import TestClient

from app.main import app


def test_cloud_hunt_history_retains_runs_and_links_findings() -> None:
    client = TestClient(app)
    client.post("/api/demo/reset", json={"confirm": True})
    first = client.post("/api/cloud/hunts", json={"provider_scope": "aws", "inventory_source": "fixtures"}).json()
    second = client.post("/api/cloud/hunts", json={"provider_scope": "gcp", "inventory_source": "fixtures"}).json()

    page = client.get("/api/cloud/hunts?page=1&page_size=1&sort=oldest")
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 2
    assert payload["has_next"] is True
    assert payload["items"][0]["id"] == first["id"]
    assert payload["items"][0]["data_source_mode"] == "Fixture-backed"
    assert "audit_events" not in payload["items"][0]

    detail = client.get(f"/api/cloud/hunts/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == first["id"]
    cases = client.get("/api/reviews").json()
    first_cases = [item for item in cases if item["source_reference"] == first["id"]]
    second_cases = [item for item in cases if item["source_reference"] == second["id"]]
    assert first_cases and second_cases
    assert {item["id"] for item in first_cases}.isdisjoint({item["id"] for item in second_cases})
    assert all(item["originating_run_id"] == first["id"] for item in first_cases)


def test_cloud_hunt_history_filters_and_refresh_are_read_only() -> None:
    client = TestClient(app)
    client.post("/api/demo/reset", json={"confirm": True})
    client.post("/api/cloud/hunts", json={"provider_scope": "aws"})
    client.post("/api/cloud/hunts", json={"provider_scope": "azure"})
    before = client.get("/api/cloud/hunts?page=1&page_size=100").json()
    filtered = client.get("/api/cloud/hunts?provider=azure&search=azure&page=1&page_size=20")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["provider_scope"] == "azure"
    after = client.get("/api/cloud/hunts?page=1&page_size=100").json()
    assert after["total"] == before["total"] == 2


def test_cloud_hunt_fixture_mode_is_explicit() -> None:
    client = TestClient(app)
    client.post("/api/demo/reset", json={"confirm": True})
    response = client.post("/api/cloud/hunts", json={"provider_scope": "multi_cloud", "inventory_source": "fixtures"})
    assert response.status_code == 200
    assert response.json()["data_source_mode"] == "Fixture-backed"

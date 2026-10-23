"""Contract tests for the built-in preset catalog API."""
from fastapi.testclient import TestClient

from backend.app import app


def test_preset_catalog_is_available_without_qloo_credentials() -> None:
    response = TestClient(app).get("/api/v1/presets")

    assert response.status_code == 200
    presets = response.json()
    assert isinstance(presets, list)
    assert {preset["id"] for preset in presets} == {
        "brand_launch",
        "brand_repositioning",
        "market_entry",
    }
    assert all({"id", "name", "description", "risk_tolerance"} <= preset.keys() for preset in presets)

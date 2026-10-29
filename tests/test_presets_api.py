"""Contract and validation tests for the report preset catalog."""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.src.services.presets import list_presets, resolve_preset


def test_preset_catalog_exposes_exactly_four_ids() -> None:
    expected_ids = {
        "porsche-aime-leon-dore",
        "coachella-jacquemus",
        "lululemon-nfl",
        "market_entry",
    }
    assert {preset["id"] for preset in list_presets()} == expected_ids

    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {"XC_API_TOKEN": "test-token"}):
        response = TestClient(app).get("/api/v1/presets", headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert {preset["id"] for preset in response.json()} == expected_ids


def test_preset_brand_match_is_case_insensitive() -> None:
    result = resolve_preset(
        "porsche-aime-leon-dore",
        acquirer_brand="pOrScHe",
        target_brand="aImÉ lEoN dOrE",
    )
    assert result["acquirer_brand"] == "Porsche"
    assert result["target_brand"] == "Aimé Leon Dore"


def test_preset_derives_omitted_brands() -> None:
    result = resolve_preset("coachella-jacquemus")
    assert result["acquirer_brand"] == "Coachella"
    assert result["target_brand"] == "Jacquemus"


def test_preset_rejects_conflict_and_unknown_id() -> None:
    with pytest.raises(ValueError, match="acquirer_brand does not match"):
        resolve_preset("porsche-aime-leon-dore", acquirer_brand="BMW")
    with pytest.raises(ValueError, match="Unknown preset_id"):
        resolve_preset("unknown-preset")

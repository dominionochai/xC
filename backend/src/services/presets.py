"""Built-in analysis presets shared with the web client."""
from __future__ import annotations
from typing import Any

PRESETS: tuple[dict[str, Any], ...] = (
    {"id": "brand_launch", "name": "Brand launch", "description": "Assess cultural fit and market opportunity for a new brand launch.", "risk_tolerance": "low"},
    {"id": "brand_repositioning", "name": "Brand repositioning", "description": "Evaluate audience overlap and transition paths for a repositioning.", "risk_tolerance": "medium"},
    {"id": "market_entry", "name": "Market entry", "description": "Compare cultural affinity and regional opportunity before entering a market.", "risk_tolerance": "medium"},
)
_PRESETS_BY_ID = {preset["id"]: preset for preset in PRESETS}

def list_presets() -> list[dict[str, Any]]:
    """Return copies so callers cannot mutate the registry."""
    return [dict(preset) for preset in PRESETS]

def get_preset(preset_id: str) -> dict[str, Any]:
    """Return a preset by stable id."""
    try:
        return dict(_PRESETS_BY_ID[preset_id])
    except KeyError as exc:
        raise ValueError(f"unknown analysis preset: {preset_id}") from exc

"""Server-validated xC cultural due-diligence report presets."""
from __future__ import annotations
from typing import Any
PRESETS: tuple[dict[str, Any], ...] = (
  {"id":"market_entry","label":"Market Entry","acquirer_brand":"","target_brand":"","description":"Market entry analysis."},
  {"id":"porsche-aime-leon-dore","label":"Porsche x Aimé Leon Dore","acquirer_brand":"Porsche","target_brand":"Aimé Leon Dore","description":"Cultural fit assessment for a premium automotive and fashion partnership."},
  {"id":"coachella-jacquemus","label":"Coachella x Jacquemus","acquirer_brand":"Coachella","target_brand":"Jacquemus","description":"Cultural fit assessment for a live-music and luxury-fashion partnership."},
  {"id":"lululemon-nfl","label":"Lululemon x NFL","acquirer_brand":"Lululemon","target_brand":"NFL","description":"Cultural fit assessment for an athletic-apparel and professional-sports partnership."},
)
def list_presets() -> list[dict[str, Any]]:
    return [dict(p) for p in PRESETS]
def get_preset(preset_id: str) -> dict[str, Any]:
    for p in PRESETS:
        if p["id"] == preset_id:
            return dict(p)
    raise ValueError(f"Unknown preset_id: {preset_id}")
def _norm(value: str) -> str:
    return " ".join(value.casefold().split())
def resolve_preset(preset_id: str | None, acquirer_brand: str | None = None, target_brand: str | None = None) -> dict[str, Any]:
    """Derive omitted brands from a preset and reject conflicting user values."""
    if not preset_id:
        if not acquirer_brand or not target_brand:
            raise ValueError("acquirer_brand and target_brand are required without preset_id")
        return {"id":None,"acquirer_brand":acquirer_brand.strip(),"target_brand":target_brand.strip()}
    preset=get_preset(preset_id)
    for field, supplied in (("acquirer_brand",acquirer_brand),("target_brand",target_brand)):
        if supplied and _norm(supplied) != _norm(preset[field]):
            raise ValueError(f"{field} does not match preset {preset_id}")
    return {**preset,"acquirer_brand":preset["acquirer_brand"],"target_brand":preset["target_brand"]}

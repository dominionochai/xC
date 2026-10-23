# xC API

The backend serves the API from the FastAPI application in `backend.app`.

## Built-in analysis presets

`GET /api/v1/presets` returns the built-in analysis preset catalog as a JSON array. Each item includes its stable `id`, display `name`, `description`, and `risk_tolerance`. This read-only endpoint does not require Qloo credentials, so clients can populate a preset selector before a report is submitted.

```sh
curl http://localhost:8000/api/v1/presets
```

The current identifiers are `brand_launch`, `brand_repositioning`, and `market_entry`. Use a returned `id` as `preset_id` in `POST /api/v1/reports/analyze`.

## Analyze a report

`POST /api/v1/reports/analyze` accepts JSON with `source_entity_id`, `comparison_entity_id`, `regions` (a non-empty mapping of region names to non-negative integer populations), and `annual_spend_per_person`. `entity_type` defaults to `urn:entity:brand`; `preset_id` defaults to `market_entry`. The endpoint requires a `QLOO_API_KEY` and returns a `503` when that credential is not configured. Qloo request failures are surfaced as `502`.

```sh
curl -X POST http://localhost:8000/api/v1/reports/analyze \
  -H 'content-type: application/json' \
  -d '{"source_entity_id":"urn:entity:brand:source","comparison_entity_id":"urn:entity:brand:target","regions":{"US":1000},"annual_spend_per_person":25,"preset_id":"market_entry"}'
```

`GET /health` is a lightweight process health check and does not make external service requests.

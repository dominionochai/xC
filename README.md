# xC

A minimal Python project with the original `xc` starter CLI and a small Qloo-backed FastAPI report-analysis slice.

## Requirements and setup

Python 3.10 or newer is required. From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
```

Runtime dependencies are also listed in `requirements.txt` for deployments that do not need the editable package or test extra.

## Run the backend

Set your real Qloo API key in the process environment; the app does not read a checked-in key or a `.env` file. The Qloo client uses `https://hackathon.api.qloo.com`, `GET /v2/insights`, the `X-Api-Key` header, and Qloo's `signal.interests.entities`, `filter.type`, and `take` query parameters.

```sh
# Supply QLOO_API_KEY from your own secret-management method before starting.
uvicorn backend.app:app --reload
```

`GET /health` is a configuration-independent liveness check. `POST /api/v1/reports/analyze` requires two Qloo entity IDs, regional population assumptions, and annual per-person spend. Example request (replace entity ID placeholders with IDs from your Qloo account):

```sh
curl -X POST http://127.0.0.1:8000/api/v1/reports/analyze \\
  -H 'Content-Type: application/json' \\
  -d '{"source_entity_id":"<SOURCE_QLOO_ENTITY_ID>","comparison_entity_id":"<COMPARISON_QLOO_ENTITY_ID>","entity_type":"urn:entity:brand","regions":{"US":1000000,"CA":250000},"annual_spend_per_person":24.50}'
```

The response includes Jaccard affinity clash/risk, the shortest deterministic affinity bridge of up to three graph hops, regional population shares, and annual TAM in USD. Population and spend are caller-supplied assumptions, not Qloo facts. Requests have a bounded retry budget; a missing key returns HTTP 503 and upstream failures return HTTP 502.

## Tests

Run the standard-library suite (including mocked Qloo transport and API tests) or pytest:

```sh
python -m unittest discover -s tests -v
pytest
```

## Original CLI starter

```sh
xc hello world
# hello world
xc
# xC starter
```

# Demo Readiness (W5)

## Purpose and status

This document is a readiness template for exercising the report-analysis demo. The request examples below are intentionally templates: replace every placeholder with owner-approved values and valid Qloo entity IDs before sending a request. The preset pair names are scenario labels, not Qloo entity IDs. Do not treat a label as an ID or fabricate IDs.

The request matrix and results are **pending valid Qloo entity IDs and a live Qloo key**. Record the results only after running the actual requests. Do not include or paste raw Qloo response data in this document.

## Verified local application details

- Start the local server: `uvicorn backend.app:app --reload`
- POST endpoint: `http://127.0.0.1:8000/api/v1/reports/analyze`
- Required request fields: entity IDs, `entity_type`, `regions`, and `annual_spend_per_person`.

## Request template

Replace the placeholders with valid, owner-specific values accepted by the API. `ENTITY_IDS` must contain valid Qloo entity IDs for the selected pair; `ENTITY_TYPE`, `REGIONS`, and annual spend must also be supplied with valid input values. The example is not ready to execute until those values and a live Qloo key are available.

### Python

```python
import os
import requests

url = "http://127.0.0.1:8000/api/v1/reports/analyze"

# Set QLOO_API_KEY in the environment once a live key is available.
headers = {"Authorization": f"Bearer {os.environ['QLOO_API_KEY']}"}

# Replace each placeholder with owner-specific valid inputs.
payload = {
    "entity_ids": ["<VALID_QLOO_ENTITY_ID_1>", "<VALID_QLOO_ENTITY_ID_2>"],
    "entity_type": "<ENTITY_TYPE>",
    "regions": ["<REGION>"],
    "annual_spend_per_person": <ANNUAL_SPEND_NUMBER>,
}

response = requests.post(url, json=payload, headers=headers, timeout=120)
print("status:", response.status_code)
# Inspect only the status/validation outcome for this readiness record;
# do not copy raw Qloo response data into this document.
```

`<ANNUAL_SPEND_NUMBER>` is a placeholder, not valid Python syntax; replace it with the approved numeric input before running. Confirm the authentication mechanism against the local application configuration before execution.

### curl

```bash
curl --fail-with-body --silent --show-error \
  -X POST 'http://127.0.0.1:8000/api/v1/reports/analyze' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${QLOO_API_KEY}" \
  --data '{
    "entity_ids": ["<VALID_QLOO_ENTITY_ID_1>", "<VALID_QLOO_ENTITY_ID_2>"],
    "entity_type": "<ENTITY_TYPE>",
    "regions": ["<REGION>"],
    "annual_spend_per_person": <ANNUAL_SPEND_NUMBER>
  }'
```

This curl body is also a placeholder template, not executable JSON until all placeholders are replaced (including the numeric annual-spend value). Confirm the configured authentication mechanism before running; never commit or record a live key.

## Preset pair labels

Use these exact labels for the planned scenarios. Resolve valid Qloo entity IDs for each label before running; the labels themselves are not IDs.

1. Porsche/Aime Leon Dore
2. Coachella/Jacquemus
3. Lululemon/NFL
4. Nike/Super Bowl
5. Apple/Met Gala
6. obscure: local independent coffee roaster x regional streetwear label
7. obscure: niche tabletop game publisher x small music festival

## Eight-run results

Complete all eight run slots with real observations after the live Qloo key and valid entity IDs are available. Fill the table with real timings once a live Qloo key exists. Record the measured wall time, Qloo call count, warnings, and validation outcome; do not paste raw Qloo data. Use `pending` until a slot has actually been run, and do not infer or estimate results.

| run | success/failure | wall time | Qloo call count | warnings | validation result |
|---|---|---|---|---|---|
| 1 | pending | pending | pending | pending | pending |
| 2 | pending | pending | pending | pending | pending |
| 3 | pending | pending | pending | pending | pending |
| 4 | pending | pending | pending | pending | pending |
| 5 | pending | pending | pending | pending | pending |
| 6 | pending | pending | pending | pending | pending |
| 7 | pending | pending | pending | pending | pending |
| 8 | pending | pending | pending | pending | pending |

## Readiness checklist

- [ ] Local server starts with the verified command above.
- [ ] A live Qloo key is configured securely and the app's expected authentication mechanism is confirmed.
- [ ] Valid Qloo entity IDs have been resolved for the selected scenarios; no IDs are guessed from scenario labels.
- [ ] Required request fields have owner-approved values.
- [ ] Eight actual runs have been recorded with real timings and validation outcomes.
- [ ] The results contain no raw Qloo response data or secrets.

# P7a: Qloo service adapter

## Methods
| method | endpoint | params | normalize |
| --- | --- | --- | --- |
| search | /search | build_search_params (query, types, take, extra) | normalize_results |
| tags_for | /v2/insights | build_insights_params (signal.interests.entities, filter.type=urn:tag, take) | normalize_results |
| affinity_pair | two tags_for calls | weighted overlap = |intersection| / |union| over tag ids | derived |
| affinity_batch | pairwise affinity_pair | n*(n-1)/2 pairs | derived |
| demographics_for | /v2/insights | UNVERIFIED until P14 | normalize_results |
| heatmap | /v2/insights | UNVERIFIED until P14 (min-max normalized per area) | normalize_results |
| trending | /trending | UNVERIFIED until P14 | normalize_results |

## Rules
- Params are built ONLY through backend/qloo/params.py builders.
- Responses pass ONLY through backend/qloo/normalize.py; raw payloads are never returned.
- The QlooClient enforces the call budget (CallBudgetExceeded propagates; no service-level retries).
- Empty results surface the client's suspect_empty flag as an "empty_results" warning, including possibly_ignored param names.
- Evidence recording (derived values only, never raw payloads, never the API key) is wired in P7b via the evidence ledger.
- demographics_for, heatmap and trending routes/params are UNVERIFIED until the P14 probe; tests use synthetic payloads only.

## Acceptance
- Fake-transport suite tests/test_qloo_service.py runs offline and deterministically.
- The P7b acceptance run drives two brand names through this service to a contract-valid ReportResult.

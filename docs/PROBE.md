# Qloo probe: provisional discovery checks

This document describes `scripts/qloo_probe.py`. **P1–P13 are provisional discovery questions, not verified Qloo API guarantees.** The probe records observations from a small, combined request; it does not establish a production contract or isolate the effect of each parameter. Do not treat an `observed` result as a claim that the behavior is stable, supported, or generally applicable.

## What it does

A live run uses the configured `QLOO_API_HOST` (or the client default) and sends only the existing bounded GET request shapes:

1. `GET /search` with the supplied term and `types=urn:entity:brand`.
2. If a usable candidate is returned, `GET /v2/insights` for that candidate with `signal.interests.entities`, `filter.type=urn:tag`, and `take=5`.

The probe does **not** try other routes, mutate data, enumerate locale/geography parameters, induce rate limiting, or run parameter-by-parameter experiments. A `take=5` request is not evidence of a server-side cap. The script uses a bounded client call budget and retry configuration; the JSON report records the attempts actually used. At most one search and one insights operation are initiated by `run_probe`; client retries can affect transport attempt counts.

## P1–P13 checklist and interpretation

| Check | Provisional question / observation | What it does not prove |
| --- | --- | --- |
| P1 | Did the configured host return a JSON response to the authenticated known GET search route? | Credential validity beyond this request, other hosts/routes, or durable access. |
| P2 | Did the combined known search query and entity-type request return a JSON object? | The individual effect or validity of either parameter. |
| P3 | Was `results` missing, an array, an object, or another type; and how many array items were observed? | Complete result availability, pagination behavior, or a maximum result count. |
| P4 | Did normalization find a search candidate with a usable identity/name? | Entity identity correctness or a stable schema. |
| P5 | Did the combined known insights request return a JSON object? | General availability or support for other insights inputs. |
| P6 | Was the existing `signal.interests.entities` request field sent successfully as part of that request? | That the field caused the response or is independently accepted. |
| P7 | Was `filter.type=urn:tag` sent as part of that request? | Independent filter semantics or filtering correctness. |
| P8 | What result shape/count was observed after requesting `take=5`? | That five is a server-enforced limit or that more/fewer cannot be returned. |
| P9 | Were returned insight items direct objects or objects nested under `entity`? | That either response shape is exhaustive or fixed. |
| P10 | How many insight items normalized to identity/name fields? | The correctness or completeness of those fields. |
| P11 | Was the insights `results` key missing, empty, or populated (and what shape did it have)? | Behavior for other queries, entities, or times. |
| P12 | Which HTTP status codes and numeric `Retry-After` values were exposed by the observed calls? | Rate-limit thresholds, retry policy, or behavior under induced throttling. |
| P13 | Were locale/geography parameter names and semantics verified? **No: the probe does not send them.** | Any locale or geographic API capability. |

`observed`, `failed`, and `not_tested` are local report statuses. A failure means this particular attempt did not complete; it does not by itself diagnose the provider. P2/P6/P7/P8 are explicitly combined observations. P13 remains `not_tested` unless a separate, approved and safely designed investigation is performed.

## Safe use

### Offline selftest (recommended first)

From the repository root:

```sh
python scripts/qloo_probe.py --selftest
```

This mode reads the checked-in deterministic fixtures under `tests/synthetic/`, substitutes an in-memory transport, and must not make network requests, require a key, or create `.qloo-probe/` output. It is suitable for routine local checks.

### Live discovery (only with approval)

A live run requires an authorized Qloo account/key and approval to send the chosen query to the configured service. Set the key in the process environment, not in a command-line argument or source file:

```sh
export QLOO_API_KEY='…'
python scripts/qloo_probe.py --term coffee
```

Use a generic, non-sensitive term and the approved host. The probe does not print the key, but no redaction routine can guarantee removal of every secret or personal datum from arbitrary provider responses. Do not pass names, account identifiers, health data, private interests, or other sensitive/personal information. Do not paste raw outputs into tickets, chat, or public logs.

The live mode writes raw response payloads and a report under `.qloo-probe/`, which is git-ignored and created with restrictive directory permissions. Treat these files as sensitive: restrict access, inspect them before sharing, and delete them when the approved retention period ends. Git ignore is not encryption or a retention control. The report redacts known credential fields and the supplied key, but raw API payloads may contain other sensitive data.

No live API calls or credentials are required for the test suite. Do not use live mode as a CI test.

## Reproducibility and evidence

For any approved live discovery, record the run time, configured host (without secrets), script/repository revision, non-sensitive term, statuses, attempt counts, and any response schema notes. Keep raw payloads access-controlled. Repeat observations before proposing a capability as supported, and obtain an approved API specification or provider confirmation before converting a provisional observation into a contract. Never infer semantics from a single combined request.
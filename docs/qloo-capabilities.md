# Qloo capabilities — verified from live probe

Status: These findings are from live probe runs on 2026-10-29 against https://hackathon.api.qloo.com with a real API key. Raw responses are not committed.

> Verdicts: `works` = behaves as expected, `ignored` = silently ignored, `error` = returns error, `ambiguous` = unclear/needs more probing, `not_tested` = not probed.

## P1 — GET /search with types parameter
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `types=urn:entity:brand` (URN required) | JSON with `results` array |
| error | `types=brand` (plain) | HTTP 400 |
| works | omit `types` | 20 results of mixed types |

**Verified**: probe with "porsche" - 1 result with URN type, 20 mixed without types.

## P2 — GET /search with query and types parameters
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `query` + `types=urn:entity:brand` | JSON with `results` array |

## P3 — Search results array size
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `take=5` (default 50) | `results` array (observed 1 item for "porsche", 5 items for broader queries) |

## P4 — Search result exposes usable entity identifier/name
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `id`/`entity_id`/`urn` + `name`/`label`/`title` | `{"id": "urn:entity:brand:...", "name": "Brand Name"}` |

## P5 — GET /v2/insights for first entity
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `signal.interests.entities=<id>` + `filter.type=urn:entity:brand` + `take=5` | `results` object with type-grouped arrays |

## P6 — signal.interests.entities request shape
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | single id, comma-separated list, or repeated params | Both comma and repeated give identical results; single differs |

## P7 — filter.type=urn:tag request shape
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `filter.type=urn:tag` | Tag filtering works |

## P8 — take parameter limits
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `take=5` returns 5 items | Server respects `take` up to 50 |
| error | `take=60` | HTTP 400 "take must be an integer value between 1 and 50" |

## P9 — Insight result structure
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | N/A | `results` is an object grouped by type: `results.entities`, `results.tags`, `results.heatmap`, `results.demographics` |

## P10 — Entity item keys (insights)
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | N/A | `entity_id`, `name`, `type`, `subtype`, `popularity`, `disambiguation`, `external`, `tags`, `properties` (~55 brand fields, many None), `query.affinity` (0..1), `query.measurements.audience_growth` (int) |

## P11 — Tag insights
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `filter.type=urn:tag` | Items have `name`, `popularity`, `query`, `subtype`, `tag_id`, `tag_value`, `types`; per-tag `query.affinity` |

## P12 — /entities?entity_ids=<id> (cheap per-entity tag fetch)
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `entity_ids=<id>` | One item with `name`, `entity_id`, `types`, `popularity`, `disambiguation`, `properties`, `tags` (92 tags observed) |

## P13 — Locations
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| ignored | `filter.type=urn:entity:brand` + `filter.location.query=Tokyo` | Results identical to baseline (ignored) |
| works | `filter.type=urn:entity:brand` + `signal.location.query=Tokyo` | Changes brand results |
| works | `filter.type=urn:entity:place` + `filter.location.query=Tokyo` | Changes results |

**Key finding**: For brand types, use `signal.location.query`, NOT `filter.location.query` (silently ignored).

## P14 — Heatmap
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `filter.type=urn:heatmap` + `signal.interests.entities=<id>` + `signal.location.query=<location>` | 109 points with `location` (lat/lon/geohash) + `query` (affinity int, affinity_rank float, popularity int, entity_brand_affinity int, entity_brand_affinity_rank float) |

**Note**: Heatmap requires `filter.type=urn:heatmap` + `signal.interests.entities` + `signal.location.query`. Without location, returns 400. Integer affinity scale unconfirmed.

## P15 — Demographics
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `filter.type=urn:demographics` + `signal.interests.entities=<id>` | `results.demographics[0] = {entity_id, query: {age: {24_and_younger..55_and_older}, gender: {male, female}}}` all floats |

## P16 — Trending and other
| Verdict | Working parameter forms | Shape summary |
|---|---|---|
| works | `/v2/tags?filter.query=luxury&take=5` | `results.tags` with id, name, type, popularity, parents |
| works | `/v2/trending` with `signal.interests.entities` + `filter.start_date` + `filter.end_date` | Requires all three; guessed filter.type-only fails with 400 |
| ignored | Unknown parameters (e.g., `filter.zz_bogus=1`) | Silently ignored, 200 with baseline results |
| observed | `bias.trends=high` changes ranking | Confirmed |

---

## Parameter validation rules (implementation)

### Search (`/search`)
- `types` must be URN format (e.g., `urn:entity:brand`), plain `brand` returns 400
- `types` accepts comma-separated URNs
- `take` integer 1..50

### Insights (`/v2/insights`)
- `filter.type` required, must be valid URN (e.g., `urn:entity:brand`, `urn:tag`, `urn:heatmap`, `urn:demographics`)
- `signal.interests.entities`: single URN, comma-separated list, or repeated params
- `filter.entities`: pairwise affinity target (single or comma-separated)
- `signal.location.query`: for brand-type locality (NOT `filter.location.query`)
- `take`: 1..50
- `feature.explainability=true` adds per-signal contribution scores

### Pairwise affinity (V6)
- `signal.interests.entities=<A>` + `filter.type=urn:entity:brand` + `filter.entities=<B>`
- Returns exactly one item (B) with `query.affinity` relative to A
- Directional: swap A/B for reverse

### Locality (V13)
- For brand types: MUST use `signal.location.query`, NOT `filter.location.query` (silently ignored)
- Region queries to try: "SoHo, New York", "Shibuya, Tokyo", "Mayfair, London"

### Heatmap (V14)
- `filter.type=urn:heatmap` + `signal.interests.entities=<id>` + `signal.location.query=<location>`
- Returns `results.heatmap` array of points with `location` (lat/lon/geohash) + `query` (affinity int, rank float, popularity, brand affinity, brand affinity rank)
- Integer affinity scale UNVERIFIED

### Demographics (V15)
- `filter.type=urn:demographics` + `signal.interests.entities=<id>`
- Returns `results.demographics[0]` with age/gender buckets as floats

### Tags (V11)
- `filter.type=urn:tag` + `signal.interests.entities=<id>`
- Per-tag `query.affinity`

## UNVERIFIED (needs follow-up probe)
- Heatmap integer affinity scale and min-max normalization
- Whether neighbourhood names (SoHo / Shibuya / Mayfair) resolve
- `filter.entities` vs `filter.entity_ids`: identical result?
- Multiple IDs in `filter.entities`, large signal lists
- `filter.start_date` / `filter.end_date` format for `/v2/trending`
- Rate limits and Retry-After under load
- Non-brand pairs (artists, places) and ambiguous brand names under no-type search
- Whether `/search` without types is the right ambiguity probe (V1: 1 result with brand type, 20 without)
- `filter.entities` vs `filter.entity_ids` identical?
- Multiple IDs in `filter.entities`, large signal lists
- `filter.start_date`/`filter.end_date` format for `/v2/trending`
- Rate limits under load
- Non-brand pairs behavior
- Ambiguous brand names ranking under no-type search

---

Probe date: 2026-10-29
Raw responses NOT committed (git-ignored `.qloo-probe/`)
Probe commands: `scripts/qloo_probe.py --term porsche` and `scripts/qloo_probe_full.py --budget 40`
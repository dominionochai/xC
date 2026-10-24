# W2 — Methods Design Draft (Gate G1, part 2: STOP for lead review)

> **DESIGN ONLY — not implementation.** All behaviors are proposals pending lead review; live probes have **NOT** run (`docs/qloo-capabilities.md` lists P1–P13 as “not yet probed”); every (pending Px) mark is provisional.

## M1 Entity Resolution

### Goal
Resolve a free-text brand/culture query to a single stable Qloo entity before affinity scoring. Failure must be explicit, never silent guessing.

### Inputs and probe dependencies
- `GET /search` with `query` (free text). First pass: `entity_type='urn:entity:brand'` (brand only); second-pass fallback without `entity_type` restriction (broader types).
- `take=max_candidates`; order by popularity if available.
- **P1 (pending):** entity id format `urn:entity:brand` vs bare `'brand'`; alternative bare form if P1 says otherwise. P1 also covers popularity field presence; if absent, rank by score plus a modeled popularity proxy (flagged alternative).
- **P2 (pending):** array style; not needed by M1, noted.
- **P4 (pending):** batch scoring; out of scope, adjacent.

### Resolution formula
A. Brand-only first pass.
B. Build candidate list from results.
C. Exact case-insensitive name match (`candidate name.lower() == query.lower()`).
D. Rank exact matches by popularity descending, then non-exact matches by popularity descending.

**Auto-select:** (a) exactly one exact match exists, or (b) top candidate popularity ≥ `popularity_ratio_threshold ×` second candidate popularity. Otherwise return `AMBIGUOUS_ENTITY` with ranked candidate list (maximum `max_candidates`).

### Free parameters
| Name | Default | Why |
|---|---:|---|
| `max_candidates` | 20 | P1 take cap unknown; conservative, revisit after P1. |
| `popularity_ratio_threshold` | 2.0 | 2× gap is defensible dominance; below it reasonable humans disagree. |
| `brand_first` | `True` | M&A primary case; broader pass is recall net. |
| `exact_match_required` | `False` | Governs auto-select, not filtering. |
| `confidence_alpha` | 0.6 | Exact match is strongest evidence, dominance second. |

### Confidence (MODELED)
`confidence = confidence_alpha * (1 if exact match else 0) + (1 - confidence_alpha) * min(1.0, (top_pop - second_pop) / top_pop)`

Never presented as measured.

### Measurement labels
| Quantity | Label |
|---|---|
| Name match | MEASURED |
| Popularity | MEASURED (pending P1) |
| Popularity ratio | MEASURED (derived) |
| Confidence | MODELED |
| Entity id stability | MEASURED (pending P1) |

### Failure and null behavior
- No exact match and no 2× dominance → `AMBIGUOUS_ENTITY` with ranked list.
- Zero results on both passes → `ENTITY_NOT_FOUND` (proposed new label, flagged for lead review since brief only defines `AMBIGUOUS_ENTITY`).
- Missing/empty popularity → treat as 0, note in candidate list, never crash.
- **P12 silent-ignore risk (pending):** if `entity_type` is silently ignored, passes return identical broad sets; detector compares pass A vs pass B result sets and flags (pending P12).

### Worked examples — SYNTHETIC (not real)
**Example 1 — query `porsche`:** brand pass `[{name:'Porsche', popularity:92, id:'urn:entity:brand:1'}, {name:'Porsche Design', popularity:41, id:'urn:entity:brand:2'}, {name:'Porsche Club', popularity:12, id:'urn:entity:brand:3'}]`. One exact match → auto-select Porsche. Confidence = `0.6*1 + 0.4*min(1,(92-41)/92) = 0.6 + 0.4*0.554 = 0.822`.

**Example 2 — query `aimé`:** candidates `[{name:'Aimé Studio', popularity:38}, {name:'Aimé Leon Dore', popularity:29}]` — no exact case-insensitive match (neither equals `aimé`), ratio `38/29 = 1.31 < 2.0` → `AMBIGUOUS_ENTITY` with both candidates, confidence = `0.4*min(1,(38-29)/38) = 0.095`, generation fails as specified.

### Probe-contrarian note
Live probes have **NOT** run. If P1 shows bare ids, the input section changes. If popularity is absent, Step D falls back to score and the 2× rule is suspended, leaving exact-match as the only auto-select path.

**STOP — awaiting lead review (Gate G1 part 2). Do not implement until approved.**
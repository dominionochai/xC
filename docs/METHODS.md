# W2 — Methods Design Draft (Gate G1, part 2: STOP for lead review)

> **DESIGN ONLY — not implementation.** All behaviors are proposals pending lead review; live probes have NOT run (`docs/qloo-capabilities.md` lists P1–P13 as “not yet probed”); every (pending Px) mark is provisional. Do not implement until approved.

## M1 Entity Resolution

### Goal
Resolve a free-text brand/culture query to a single stable Qloo entity before affinity scoring; failure explicit, never silent guessing.

### Inputs and probe dependencies
`GET /search` with `query` (free text); first pass `entity_type='urn:entity:brand'` (brand only), second pass fallback without `entity_type` (broader types); `take=max_candidates`; order by popularity if available. P1 (pending): entity id format `urn:entity:brand` vs bare `'brand'` (alternative bare form if P1 says otherwise), and popularity field presence (if absent, rank by score + modeled popularity proxy; flagged alternative). P2 array style (not needed by M1, noted); P4 batch scoring (out of scope, adjacent).

### Resolution formula
A. Brand-only pass. B. Build candidate list. C. Exact case-insensitive name match (`candidate name lower() == query lower()`). D. Rank exact matches by popularity descending, then non-exact by popularity descending. Auto-select when (a) exactly one exact match, OR (b) top candidate popularity >= `popularity_ratio_threshold` × second candidate popularity. Else `AMBIGUOUS_ENTITY` with ranked list (maximum `max_candidates`).

### Free parameters
| Name | Default | Why |
|---|---:|---|
| `max_candidates` | 20 | P1 take cap unknown; conservative, revisit after P1. |
| `popularity_ratio_threshold` | 2.0 | 2× gap is defensible dominance; below it reasonable humans disagree. |
| `brand_first` | True | M&A primary case; broader pass is recall net. |
| `exact_match_required` | False | Governs auto-select, not filtering. |
| `confidence_alpha` | 0.6 | Exact match strongest evidence, dominance second. |

### Confidence (MODELED)
`confidence = confidence_alpha*(1 if exact match else 0) + (1-confidence_alpha)*min(1.0, (top_pop - second_pop)/top_pop)`. Never presented as measured.

### Measurement labels
Name match MEASURED; popularity MEASURED (pending P1); popularity ratio MEASURED (derived); confidence MODELED; entity id stability MEASURED (pending P1).

### Failure and null behavior
No exact + no 2× dominance → `AMBIGUOUS_ENTITY` with ranked list; zero results both passes → `ENTITY_NOT_FOUND` (new proposed label, lead review: brief defines only `AMBIGUOUS_ENTITY`); missing/empty popularity → 0, note in list, never crash. P12 silent-ignore risk: if `entity_type` ignored, passes return identical broad sets; compare pass A/B sets and flag (pending P12).

### Worked examples — SYNTHETIC
Ex1 query `porsche`: `[{name:'Porsche',popularity:92,id:'urn:entity:brand:1'}, {name:'Porsche Design',popularity:41,id:'urn:entity:brand:2'}, {name:'Porsche Club',popularity:12,id:'urn:entity:brand:3'}]`. One exact match → auto-select Porsche. Confidence `0.6*1 + 0.4*min(1,(92-41)/92) = 0.6 + 0.4*0.554 = 0.822`.

Ex2 query `aimé`: `[{name:'Aimé Studio',popularity:38}, {name:'Aimé Leon Dore',popularity:29}]`; no exact case-insensitive match, ratio `38/29=1.31<2.0` → `AMBIGUOUS_ENTITY` with both candidates; confidence `0.4*min(1,(38-29)/38)=0.095`, generation fails.

### Probe-contrarian note
Live probes have NOT run. If P1 shows bare ids, input section changes; if popularity is absent, Step D falls back to score and the 2× rule is suspended, leaving exact-match as the only auto-select path.

## M2 Fit

### Goal
Quantify how naturally target T fits acquirer A's audience and vice versa.

### Inputs and probe dependencies
`GET insights/affinity` signal entity A / results entity T (and symmetric T→A); exact params pending P3 (pairwise affinity forms), design assumes `signal.entities` + `filter.results.entities`. Tag profiles via `urn:tag` (P6), top 50 each; demographics via `urn:demographics` (P7).

### Formula
`fit.affinity = 100 × mean(s_AT,s_TA)`; notes ALWAYS list both directions (gap is informative, asymmetric affinity is real signal). `tag_overlap` = weighted Jaccard: sum shared `min(wA,wT)` / sum union `max(wA,wT)`; weights from top-50 profiles. Shared signals sorted by `min(wA,wT)` descending. Contrast axes sorted by `(wT-wA)` descending if positive (target), ascending if negative (acquirer); normalize strength by largest profile weight to `[-1,1]`. Demographics: normalized shares per age/gender bucket compared per bucket; difference is modeled demographic skew.

### Free parameters
`top_tags=50` (P6 cap unknown; assumption pending P6); demographic buckets = whatever P7 returns, no hardcoded list before probe.

### Measurement labels
`s_AT`,`s_TA` MEASURED (pending P3/P4); fit.affinity MODELED (mean); tag_overlap and shared/contrast tags MEASURED-derived; demographic skew MODELED.

### Failure and null behavior
Missing one direction → fit null with missing direction noted; never impute. Empty tag profile either side → tag_overlap null, shared/contrast empty, warning. Missing demographics → skew omitted and labeled null.

### Worked example — SYNTHETIC
`s_AT=.52`,`s_TA=.61` → fit=56.5, list both. Top 5 of 50 weights A `{a:.8,b:.6,c:.4}`, T `{b:.7,c:.5,d:.3}`; shared `{b,c}`. Jaccard `(min(.6,.7)+min(.4,.5))/(max(.8,0)+max(.6,.7)+max(.4,.5)+max(0,.3))=1.0/2.3=.435`. Contrast c +.1 target, b +.1 target, a -.8 acquirer; normalized by .8, a=-1.0.

### Probe-contrarian note
If P3 says cross-call affinities are not comparable, use paired single-call form or label fit MODELED with normalization note. If P6 cap <50, reduce top_tags to cap and document.

## M3 Low-affinity (anti-co-occurrence) vector

### Goal
Measure contradiction—what T's world implies A's audience does NOT like—without a bottom-ranked query.

### Inputs and probe dependencies
No bottom-ranked query exists (design assumption; P12-adjacent silent-ignore risk); derive from signature items. GET batch affinity (P4 pending: batch cap, ordering/normalization) scoring T's top signature items against A and symmetrically A's against T. Domains: brand, artist, movie, tv_show, podcast, book, place, destination, person.

### Formula
Per domain k: `F_k=mean aff_A(item)` over T items (A audience likes T world); `C_k=mean aff_T(item)` over A items (T audience likes A world); `Anti_k` = share of T items whose aff_A is below lower tercile of ALL affinities this run (data-driven, never hand-tuned; if <3 items in run, cutoff is single lowest observed and axis flagged); `Anti_k∈[0,1]`.

### Downstream
F_k, C_k, Anti_k feed `pandering_authenticity_risk(C, Anti, F)` from market_strategy.py unchanged (formula in A5; not re-derived).

### Normalization
If P3/P4 show per-call min-max normalization, switch to within-call rank `rank/N`, say so; never mix normalization families.

### Free parameters
Domains fixed above; `signature_items_per_domain=5` (pending P4 cap; loop batches if lower); `lower_tercile_cutoff` has no free parameter, computed per run (anti-hand-tuning).

### Measurement labels
F_k,C_k,Anti_k MODELED (derived from measured); item affinities MEASURED (pending P4).

### Failure and null behavior
Domain with <3 items dropped with warning in evidence refs; zero items → axis omitted, never silent zero.

### Interpretation
Contradiction: Anti_k (A audience rejects T signature world); overclaim: high F + low C (T claims affinity A doesn't reciprocate); misalignment: high C + high Anti (T likes what A rejects). Keep raw per-domain arrays in evidence payload for alternative formula without re-scoring.

### Worked example — SYNTHETIC
Movie T items m1,m2,m3 aff_A=[.12,.18,.09]; all-run tercile cutoff .15; 2/3 below → Anti_movie=.67; F_movie=.13; C_movie=.42 → high C + Anti flags misalignment.

### Probe-contrarian note
If P4 has no batch endpoint, use sequential single-call loop and state call-budget implication.

## M4 Communities

### Goal
Compress target-side contrast signal into at most 5 interpretable audience communities.

### Inputs and probe dependencies
Target-side positive `wT-wA` contrast tags from M2; category = tag URN category segment (P6 pending URN format); evidence refs = probe outputs + item IDs.

### Formula
Primary grouping by tag category (P6 pending). If degenerate (one category holds everything or >5 categories), greedy co-weighting: sort tags by contrast strength descending, assign to community with highest summed co-weight (co-occurrence in same target profile item), cap 5, fold remainder into nearest by co-weight.

Per-community: basis tags/entities = top by contrast strength; `core_audience_share` = community contrast weight / total; `anti_strength` = mean contrast strength; evidence refs.

Labels: LLM if configured, validated against basis tags (R3; template fallback on validation failure); else deterministic top-two template `'{tag1} + {tag2}'`.

### Free parameters
`max_communities=5` (brief); `min_community_share=.05` (fold <5% into nearest larger, prevents noise).

### Measurement labels
Membership MODELED; core_audience_share and anti_strength MEASURED-derived; labels MODELED (LLM) or TEMPLATE (deterministic).

### Failure and null behavior
No contrast tags → zero communities, empty result with reason, never synthetic single community. LLM unavailable → deterministic labels only, state it.

### Worked example — SYNTHETIC
Tags c1..c6, 3 categories -> 3 communities. Cat X `{c1:.5,c2:.3}` share `.8/2=.40`, anti_strength mean contrast, template `c1 + c2`. Degenerate one category all six -> greedy split e.g. `{c1,c2,c3}` share .55 and `{c4,c5,c6}` .45.

### Probe-contrarian note
If P6 shows no category segment in tag URNs, replace category grouping entirely with greedy co-weighting and state this.

## M5 Rebellion simulation (Monte Carlo agent simulation)

> **MODEL — uncalibrated assumed parameters, NOT an empirical measurement. Calibration/backtest is future work and is NOT claimed.**

### Goal
Translate community anti-strength, authenticity gap and fit into a distribution of lost brand value under rebellion scenarios.

### Inputs
Communities i=1..N with share s_i, anti strength a_i, value weight v_i=1 (default, reported); authenticity gap `g=rebellion.index.components.alignment_gap`; seed=42 and R=5000 runs (both reported); use `random.Random(seed+r)` per run.

### Per-run formulas
`m_i=clamp(0.5*a_i+0.3*g+0.2*(1-fit_ratio_i),0.01,0.99)`, `fit_ratio_i=community fit.affinity/100` (all components assumed, not measured). `p_i~Beta(m_i*kappa,(1-m_i)*kappa)`, kappa=20; `d_i~Beta(p_i*kappa2,(1-p_i)*kappa2)`, kappa2=10 (defecting fraction). T=3 rounds: `d_i <- clamp(d_i+lambda*sum_j W_ij(d_j-d_i),0,1)`, lambda=.2, W_ij weighted Jaccard of community tag sets, rows sum to 1. `rebel_i=(d_i>=theta)`, theta=.15. `loss_r=sum_i s_i*v_i*d_i/sum_i s_i*v_i`; `ip_at_risk_pct_r=100*clamp(loss_r,0,1)`.

### Outputs
Histogram 24 bins, lo=0, hi=smallest multiple of 5 >= max observed (minimum 20); mean, median, p5, p95 nearest-rank; per-community rebellion_probability=mean rebel_i; streaming running mean/p5/p95 snapshots every R/40 runs.

### Free parameters — all ASSUMED
| Name | Default | Why |
|---|---:|---|
| kappa | 20 | Propensity dispersion; narrower = more herd-like. |
| kappa2 | 10 | Defection dispersion. |
| lambda | .2 | Influence strength; <1 keeps dynamics stable. |
| T | 3 | Rounds; beyond 3 process converges to consensus. |
| theta | .15 | Rebellion threshold. |
| seed | 42 | Reproducibility. |
| R | 5000 | Stable p5/p95, cheap per run. |
| v_i | 1 | Equal value weight default; overridable. |
| bins | 24 | Fixed by brief. |

### Measurement labels
All params ASSUMED; m_i MODELED; p_i,d_i MODELED (sampled); rebel_i MODELED (thresholded); loss/ip_at_risk MODELED; outputs never measured.

### Failure and null behavior
No communities → `rebellion.simulation=null` + warning, never fake one-community run. Missing fit_ratio_i → community mean fit or 1, note and flag for lead. Zero/negative total share → loss null + warning.

### Calibration/backtest — FUTURE WORK, not claimed
(a) Historical brand controversies with known revenue impact as ground truth. (b) Grid-search (kappa,kappa2,lambda,theta) maximizing hit rate on rebel community membership. (c) Validate p5/p95 coverage of realized losses. (d) Report sensitivity run over all defaults. **No calibration has been performed; these parameters are assumptions.**

### Worked example — SYNTHETIC
Two communities s=[.6,.4], a=[.8,.2], g=.5, fit_ratio=[.9,.5]: m1=clamp(.4+.15+.02)=.57, m2=clamp(.1+.15+.1)=.35; illustrative p1~.61,p2~.33,d1~.58,d2~.31 from the Beta draws; influence rounds pull them together; theta=.15 -> both rebel; loss=(.6*.58+.4*.31)/1=.472 -> ip_at_risk=47.2%. Illustrates math path, not calibrated forecast.

### Probe-contrarian note
No Qloo dependency beyond M2-M4 inputs. If fit_ratio_i unavailable due to M2 null fit, fallback above applies; simulation then runs on anti-strength + gap only.

## M6 Bridge

### Goal
When direct fit is too weak, build a credible cultural bridge A -> m1 -> m2 -> T with acceptable edges and distinct categories.

### Inputs and probe dependencies
Direct fit s=fit.affinity (M2); candidate pool M (~60 category-diverse items) from top results for A and T across M3 domains (P1 search per domain); batch affinities a(A->m), a(T->m) over M (P4 pending; if no batch endpoint use sequential calls and note budget); a(m1->m2) up to 5 batch calls; category from dominant tag or type.

### Formula
If s>=tau, status=`not_needed`. Else build M; two batch calls score A->m and T->m; top 5 M1 (high with A), top 5 M2 (high with T); score m1->m2 up to 5 batch calls; choose pair maximizing weakest edge `min(a(A->m1),a(m1->m2),a(m2->T))`, subject to distinct categories across A,m1,m2,T. Step objectives come from `build_transition_campaign` plus evidence (existing code unchanged).

Friction (MODELED): `friction_before=100-fit.affinity`; `friction_after=100-100*min(edge scores)` (weakest-link); `friction_reduction_pct=max(0,100*(before-after)/before)`.

### Free parameters
`tau=60` (assumed presentation threshold; below 60 fit feels forced and bridge earns cost); M≈60 (coverage vs budget); M1=M2=5 (top candidates each side); distinct categories hard constraint (bridge integrity). Budget ≈12 calls total (2 batch pool + up to 5 triple + margin).

### Measurement labels
s MEASURED-derived (M2); edge affinities MEASURED (pending P4); triple choice MODELED (max-min); friction MODELED.

### Failure and null behavior
Weakest edge not better than direct affinity → status=`not_found`, return evidence with all scored edges, never fabricate bridge. If category constraint unsatisfiable, widen categories one at a time in documented order and log each widening.

### Worked example — SYNTHETIC
A=brand X, T=brand Y, fit=38<60; winning edges A->m1=.71, m1->m2=.64, m2->T=.69, categories brand/artist/book/brand; weakest=.64; friction_before=62, friction_after=36, reduction=41.9%; bridge found. Counterexample best weakest=.31 < direct .38 -> not_found with evidence.

### Probe-contrarian note
P4 pending: if batch cap < pool, shrink M or loop batches and state call count increase. If P3/P4 scores min-max normalized, compare edges with within-call rank normalization as M3 specifies; never mix.

## M7 Locality

### Goal
Quantify whether A and T fit better in specific regions vs global with identical method for comparable deltas.

### Inputs and probe dependencies
Regions: soho_nyc (SoHo, New York), shibuya_tokyo (Shibuya, Tokyo), mayfair_london (Mayfair, London), plus global baseline. Same pairwise affinity per region. Location parameter forms P8 pending (neighborhood resolution, honored params).

### Resolution ladder
1. Region-conditioned `filter.results.entities` affinity using P8-honored `signal.location.query` or `filter.location.query`.
2. Heatmap overlap = cosine of normalized cell vectors for A and T over area (`urn:heatmap`, P8).
3. City-level fallback with explicit caveat and sample_note `neighborhood granularity not supported by the data provider` if neighborhood queries do not resolve. Never silently substitute city for neighborhood without caveat.

Metrics (derived MODELED): friction=100-affinity; delta_vs_global=affinity_region-global_affinity, computed by backend, not client.

### Failure and null behavior
Unresolved neighborhood → city fallback + caveat + sample_note, never silent; heatmap unavailable → skip level 2 with note; all levels fail → region null with reason.

### Measurement labels
Region affinity MEASURED (pending P3/P8); heatmap cosine MODELED (from measured cells); friction/delta MODELED-derived.

### Worked example — SYNTHETIC
Global fit=52; SoHo=61 -> delta +9, friction39; Shibuya=44 -> delta -8; Mayfair=55 -> delta +3. Same method everywhere; deltas comparable.

### Probe-contrarian note
P8 pending: if neighborhoods do not resolve, level 3 primary, caveat+sample_note on every region result; heatmap overlap only neighborhood-granularity signal if cells exist.

## M8 TAM expansion

**RULE FIRST:** all dollar inputs are ASSUMED and come from `backend/data/regions.json` or request overrides. NEVER invent figures: every default needs source URL and year in file (entry `{value, source_url, source_year}`); without a cite leave value null, emit warning, and return TAM PARTIAL.

### Goal
Dollarize cultural fit into defensible TAM expansion estimate with every assumption sourced/labeled.

### Model
Per region r: `reach_r=pop_r*penetration`; `expansion_r=reach_r*spend*(affinity_r/100)*(1-ip_loss/100)`; `baseline=sum_r reach_r*spend`. pop_r is sourced regional population; penetration is assumed population share reached (sourced or null); spend is assumed annual per-person category spend (sourced or null); affinity_r/100 is M7 regional affinity multiplier; ip_loss is M5 mean (base), p95 (low), p5 (high).

Sensitivity: low/high USD as each assumption moves by stated range (default ±30%), shown as tornado chart per assumption, never a single point.

### Free parameters
Penetration/spend must each have source or null; `sensitivity_range=.30`.

### Measurement labels
pop, penetration, spend ASSUMED (sourced or null + warning); reach/expansion/baseline MODELED arithmetic; affinity_r MEASURED-derived (M7); ip_loss MODELED (M5).

### Failure and null behavior
Any null term → region expansion null; TAM PARTIAL with null assumptions and warnings. All regions null → TAM null + reason, never invented.

### Worked example — SYNTHETIC
pop=1,000,000 (source X, 2024), penetration=.10 (source Y, 2025), spend=200 (source Z, 2024), affinity=60, base ip_loss=.20 -> reach=100,000; expansion=100,000*200*.60*.80=$9,600,000; low/high use p95/p5; tornado ±30% each assumption. Placeholder sources are synthetic, not real citations.

### Probe-contrarian note
No Qloo dependency. affinity_r must exist or region excluded with warning.

## M9 Verdict and confidence (presentation rules)

### Goal
Map numbers to a human verdict with DETERMINISTIC rules; thresholds documented as PRESENTATION-ONLY, not measurement.

### Presentation-only rules
| Verdict | Rule (PRESENTATION-ONLY) |
|---|---|
| proceed | fit>=55 AND delta_vs_global>=0 AND ip_at_risk mean<=15 |
| proceed_with_remediation | fit>=40 AND (delta>=0 OR bridge status!='not_found') AND ip mean<=30 |
| high_risk | ip mean>30 OR anti_strength_max>.7 |
| insufficient_data | required input null: fit, ip_at_risk, or >=half region affinities |

`headline.confidence` = MODELED data coverage: share expected evidence obtained (ledger entries present/expected) minus .15 per suspect_empty call (client/M10), minus .10 per dropped axis (M3) or null community set (M4), clamped [0,1]. Never statistical confidence; report each penalty.

### Failure and null behavior
All-null inputs -> insufficient_data + null confidence. Otherwise confidence uses evidence obtained and reports penalties explicitly.

### Worked examples — SYNTHETIC
fit=58, delta=+4, ip mean=12 -> proceed; confidence=.90 evidence -0 suspect_empty -0 dropped axes=.90. fit=42, bridge found, ip mean=25 -> proceed_with_remediation; confidence=.80 with -.15 suspect_empty noted.

### Probe-contrarian note
Thresholds are presentation-only per brief, uncalibrated; calibration future work linked to M5 plan.

## M10 Evidence ledger

### Goal
Every Qloo call and computed metric has a verifiable ledger entry; evidence_refs point at rows; evidence_verification comes from `XcEvidenceLedger.verify()`.

### Entry fields
source (endpoint + parameter names, never values); reference (stable id/hash); claim (supported statement); payload derived values and IDs only (never raw response bodies/API keys). Computed metrics also get entries: source=`computed:<method>`, reference=method+inputs hash, claim=metric claim, payload=derived values+IDs.

`evidence_verification = XcEvidenceLedger.verify()` (existing class unchanged). Ledger rows are the single source for evidence_refs everywhere: M3/M4 refs, M6 not_found evidence, M8 warnings.

### Failure and null behavior
Failed call gets entry claim=`call failed`; dependent metric null with row ID in reason; never store raw bodies.

## Gate G1 deliverable

Deliverables: (1) probe report `docs/qloo-capabilities.md` IF run (currently NOT run; P1–P13 “not yet probed”); (2) this METHODS.md design draft (M1–M10, all STOP for lead review); (3) Capability gaps list (R11): popularity field presence (P1), entity id format (P1), pairwise affinity comparability (P3), batch scoring availability (P4), tag URN category segment (P6), neighborhood-level location support (P8), silent-ignore behavior (P12) all unverified; no calibration for M5/M9 assumptions; TAM sources pending (`backend/data/regions.json`).

**STOP - awaiting lead approval (Gate G1). Do not start W3 before the lead approves the design.**
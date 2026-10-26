# P6 Locality

## Flow and ladder

The locality engine is `methods.locality.locality_analysis`. The contract boundary is
`locality_adapter.run_locality_adapter`, which maps engine results into the Pydantic
models in `contract_locality`:

`engine -> locality_adapter.run_locality_adapter -> methods.locality.locality_analysis`

The deterministic ladder is:

1. **Region query** — `region_query` returns region-level affinity when available.
2. **Heatmap cosine** — `heatmap_cosine` derives affinity from heatmap vectors when the region query cannot resolve it.
3. **City fallback** — `city_fallback` supplies city-level affinity. Since this is coarser than a neighborhood, the result carries the caveat and `sample_note`: `neighborhood granularity not supported by the data provider`.

The backend computes friction as `100 - affinity` and `delta_vs_global` as
`affinity - global_affinity`; callers do not supply those derived values.

## Measurement labels and statuses

- Region affinity is **measured pending P3/P8** when a region query supplies it; until then it may be modeled.
- Heatmap cosine affinity is **modeled**.
- Friction and delta are **modeled-derived**.
- `resolved` means every requested region has affinity; `partial` means some regions resolve; `failed` means none resolve.

Qloo client wiring through `make_qloo_locality_fns` is **UNVERIFIED until P7**.

## Caveats and TAM use

Identical resolved affinity values for every requested region trigger the suspect-empty
caveat: `identical affinity across all regions: location filter may be ignored for this entity type`.
This is a warning signal, not proof that filtering was ignored. `sample_note` carries the
same caveat text on affected rows. The neighborhood fallback note likewise remains
attached to city-fallback results.

Region affinity feeds TAM (P2) and is supplied by the locality engine/provider; it is
never sourced from a data file.

## Acceptance checks

- Identical affinity values across all regions set the suspect-empty caveat on every row and set its provenance trigger to true.
- For each resolved row with a global affinity, verify the delta sum-check:
  `delta_vs_global == affinity - global_affinity`.
- Output rows preserve deterministic input region ordering.
- The offline tests cover region query, heatmap cosine, city fallback, total failure,
  partial resolution, and identical-value detection.

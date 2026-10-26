"""Map the locality analysis ladder onto the P6 API contract."""

import asyncio
import inspect
import math
from collections import defaultdict
from collections.abc import Mapping

try:
    from methods.locality import locality_analysis, _NEIGHBORHOOD_CAVEAT
except ModuleNotFoundError:
    try:
        from backend.methods.locality import locality_analysis, _NEIGHBORHOOD_CAVEAT
    except ModuleNotFoundError:
        from locality import locality_analysis, _NEIGHBORHOOD_CAVEAT

try:
    from contract_locality import LocalityResult, RegionLocality
except ModuleNotFoundError:
    try:
        from src.contract_locality import LocalityResult, RegionLocality
    except ModuleNotFoundError:
        from backend.src.contract_locality import LocalityResult, RegionLocality


DEFAULT_REGIONS = ('soho_nyc', 'shibuya_tokyo', 'mayfair_london')
_LADDER_METHODS = {1: 'region_query', 2: 'heatmap_cosine', 3: 'city_fallback'}
_IDENTICAL_CAVEAT = (
    'identical affinity across all regions: location filter may be ignored for this entity type'
)


def _mapping(value):
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, 'model_dump', None)
    if callable(dump):
        return dump()
    if hasattr(value, '__dict__'):
        return vars(value)
    return {}


def _rows_from_analysis(raw, regions):
    if isinstance(raw, Mapping):
        rows = raw.get('regions', raw.get('results', raw.get('localities', [])))
    else:
        rows = raw
    if rows is None:
        rows = []
    if isinstance(rows, Mapping):
        rows = list(rows.values())
    try:
        rows = list(rows)
    except TypeError:
        rows = []
    by_region = defaultdict(list)
    for index, row in enumerate(rows):
        item = _mapping(row)
        name = item.get('region')
        if name is None and index < len(regions):
            name = regions[index]
        if name is not None:
            by_region[str(name)].append(item)
    return by_region


def _level_for(row):
    level = row.get('ladder_level', row.get('level'))
    if level is None:
        method = row.get('method', row.get('source_method'))
        reverse = {name: number for number, name in _LADDER_METHODS.items()}
        level = reverse.get(method)
    try:
        level = int(level) if level is not None else None
    except (TypeError, ValueError):
        level = None
    return level if level in _LADDER_METHODS else None


def _await_if_needed(value):
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    # Resolve an awaitable without nesting a new event loop in the caller's loop.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, value).result()


def run_locality_adapter(
    region_query_fn,
    heatmap_fn,
    city_fallback_fn,
    regions=DEFAULT_REGIONS,
    global_affinity=None,
):
    ordered_regions = list(regions)
    inputs = {
        'regions': list(ordered_regions),
        'global_affinity': global_affinity,
    }
    analysis_error = None
    try:
        raw = _await_if_needed(
            locality_analysis(
                region_query_fn,
                heatmap_fn,
                city_fallback_fn,
                regions=list(regions),
            )
        )
    except Exception as exc:
        raw = None
        analysis_error = exc

    raw_map = _rows_from_analysis(raw, ordered_regions)
    raw_mapping = _mapping(raw)
    raw_warnings = raw_mapping.get('warnings', [])
    warnings = list(raw_warnings) if isinstance(raw_warnings, (list, tuple)) else []
    evidence_refs = list(raw_mapping.get('evidence_refs', []) or [])
    rows = []

    for region in ordered_regions:
        candidates = raw_map.get(str(region), [])
        item = candidates.pop(0) if candidates else {}
        affinity = item.get('affinity')
        if affinity is not None:
            try:
                affinity = float(affinity)
                if not math.isfinite(affinity):
                    affinity = None
            except (TypeError, ValueError):
                affinity = None

        if affinity is None:
            warnings.append(f'{region}:all_levels_failed')
            rows.append(
                RegionLocality(
                    region=region,
                    affinity=None,
                    ladder_level=None,
                    friction=None,
                    delta_vs_global=None,
                    reason='all_levels_failed',
                    provenance=list(item.get('provenance', []) or []),
                )
            )
            continue

        level = _level_for(item)
        method = _LADDER_METHODS.get(level)
        row_provenance = list(item.get('provenance', []) or [])
        row_provenance.append(
            {'source': 'methods.locality.locality_analysis', 'method': method}
        )
        evidence_refs.append(
            {
                'source': 'methods.locality.locality_analysis',
                'region': region,
                'method': method,
                'ladder_level': level,
            }
        )
        caveat = None
        sample_note = None
        if level == 3:
            caveat = _NEIGHBORHOOD_CAVEAT
            sample_note = _NEIGHBORHOOD_CAVEAT
            warnings.append(f'{region}:city_fallback:{_NEIGHBORHOOD_CAVEAT}')
        delta = (
            affinity - float(global_affinity)
            if global_affinity is not None
            else None
        )
        rows.append(
            RegionLocality(
                region=region,
                affinity=affinity,
                ladder_level=level,
                friction=100.0 - affinity,
                delta_vs_global=delta,
                caveat=caveat,
                sample_note=sample_note,
                provenance=row_provenance,
            )
        )

    if analysis_error is not None and not rows:
        warnings.append(f'locality_analysis:{type(analysis_error).__name__}')

    all_resolved = bool(rows) and all(row.affinity is not None for row in rows)
    suspect_empty = (
        all_resolved
        and len(rows) > 0
        and all(row.affinity == rows[0].affinity for row in rows)
    )
    if suspect_empty:
        for row in rows:
            row.caveat = _IDENTICAL_CAVEAT
            row.sample_note = _IDENTICAL_CAVEAT
        warnings.append(_IDENTICAL_CAVEAT)

    success_count = sum(row.affinity is not None for row in rows)
    status = (
        'resolved'
        if rows and success_count == len(rows)
        else 'failed'
        if success_count == 0
        else 'partial'
    )
    provenance = [
        {
            'source': 'methods.locality.locality_analysis',
            'inputs': inputs,
        },
        {'source': 'contract_locality.map'},
        {'source': 'locality_adapter.suspect_empty', 'triggered': bool(suspect_empty)},
    ]
    assumptions = {
        'regions': list(ordered_regions),
        'ladder': [
            {'level': level, 'method': method}
            for level, method in _LADDER_METHODS.items()
        ],
        'global_affinity': global_affinity,
        'labels': {
            'affinity': 'measured-or-modeled',
            'friction': 'modeled-derived',
            'delta_vs_global': 'modeled-derived',
        },
        'suspect_empty_detection': 'identical-region-values',
    }
    return LocalityResult(
        status=status,
        regions=rows,
        global_affinity=global_affinity,
        warnings=warnings,
        evidence_refs=evidence_refs,
        provenance=provenance,
        assumptions=assumptions,
    )


def _normalized_scalar(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(score):
        return None
    if 0.0 <= score <= 1.0:
        return score * 100.0
    return min(100.0, max(0.0, score))


def _normalize_qloo_result(value, preserve_vector=False):
    if isinstance(value, Mapping):
        normalized = dict(value)
        for key in ('affinity', 'score', 'value'):
            item = normalized.get(key)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                normalized[key] = _normalized_scalar(item)
        return normalized
    if preserve_vector and isinstance(value, (list, tuple)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _normalized_scalar(value)
    return value


async def make_qloo_locality_fns(client):
    """Create defensive async wrappers for the Qloo locality client methods."""

    async def invoke(method_name, *args, preserve_vector=False, **kwargs):
        method = getattr(client, method_name, None)
        if not callable(method):
            return None
        try:
            result = method(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return _normalize_qloo_result(result, preserve_vector=preserve_vector)
        except Exception:
            return None

    async def region_query_fn(*args, **kwargs):
        return await invoke('region_affinity', *args, **kwargs)

    async def heatmap_fn(*args, **kwargs):
        return await invoke('region_heatmap', *args, preserve_vector=True, **kwargs)

    async def city_fallback_fn(*args, **kwargs):
        return await invoke('city_affinity', *args, **kwargs)

    # UNVERIFIED until P7
    return region_query_fn, heatmap_fn, city_fallback_fn

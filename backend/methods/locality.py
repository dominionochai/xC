"""Compare regional affinity using a transparent, explicit locality fallback ladder."""

from math import sqrt


_NEIGHBORHOOD_CAVEAT = "neighborhood granularity not supported by the data provider"


def _cosine_affinity(a_vec, t_vec):
    """Return cosine similarity on a 0–100 affinity scale, or None if unusable."""
    try:
        a_values = [float(value) for value in a_vec]
        t_values = [float(value) for value in t_vec]
    except (TypeError, ValueError):
        return None

    if len(a_values) != len(t_values):
        return None

    a_norm = sqrt(sum(value * value for value in a_values))
    t_norm = sqrt(sum(value * value for value in t_values))
    if a_norm == 0 or t_norm == 0:
        return 0.0

    cosine = sum(a * t for a, t in zip(a_values, t_values)) / (a_norm * t_norm)
    # Guard small floating point excursions outside cosine's mathematical range.
    return 100.0 * max(-1.0, min(1.0, cosine))


def locality_analysis(
    region_query_fn,
    heatmap_fn,
    city_fallback_fn,
    regions=['soho_nyc', 'shibuya_tokyo', 'mayfair_london'],
    global_affinity=None,
):
    """Analyze regional affinity with region, heatmap, then explicit city fallback.

    The callbacks receive a region name. A missing result (or an unavailable
    callback result) advances the ladder; a city result is always labeled with
    the neighborhood-granularity caveat and is never presented as regional data.
    Heatmap cosine similarity is converted to the same 0–100 scale as provider
    affinities. ``delta_vs_global`` is the region affinity minus the baseline.
    """
    results = {}
    for region_name in regions:
        affinity = None
        ladder_level = None

        try:
            affinity = region_query_fn(region_name)
        except Exception:
            affinity = None
        if affinity is not None:
            ladder_level = 1
        else:
            heatmap = None
            try:
                heatmap = heatmap_fn(region_name)
            except Exception:
                heatmap = None
            if heatmap is not None:
                try:
                    a_vec, t_vec = heatmap
                    affinity = _cosine_affinity(a_vec, t_vec)
                except (TypeError, ValueError):
                    affinity = None
            if affinity is not None:
                ladder_level = 2
            else:
                try:
                    affinity = city_fallback_fn(region_name)
                except Exception:
                    affinity = None
                if affinity is not None:
                    ladder_level = 3

        if affinity is None:
            results[region_name] = {"affinity": None, "reason": "all_levels_failed"}
            continue

        result = {
            "affinity": affinity,
            "ladder_level": ladder_level,
            "friction": 100 - affinity,
            "delta_vs_global": (
                affinity - global_affinity if global_affinity is not None else None
            ),
        }
        if ladder_level == 3:
            result["caveat"] = _NEIGHBORHOOD_CAVEAT
            result["sample_note"] = _NEIGHBORHOOD_CAVEAT
        results[region_name] = result

    return results

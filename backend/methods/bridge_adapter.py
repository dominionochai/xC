from __future__ import annotations
from backend.methods.bridge import build_bridge
from backend.src.contract_bridge import BridgeResult, BridgeStep
TAU = 60.0  # fit threshold above which no remediation bridge is needed (documented)
STEP_NAMES = ('Familiarization', 'Bridge adoption', 'Conversion')
def _step(step_index, name, evidence_from, edge_key, edges, evidence):
    lift = edges[edge_key] / 100.0
    refs = [e['from'] + '->' + e['to'] for e in evidence if e.get('from') == evidence_from]
    return BridgeStep(name=name, affinity_lift=round(lift, 4), evidence_refs=refs)
def run_bridge_adapter(fit_affinity, pool, affinity_fn, category_fn=None, tau=TAU, top_n=5, max_triple_calls=5, budget_note='~12 calls') -> BridgeResult:
    raw = build_bridge(fit_affinity=fit_affinity, pool=pool, affinity_fn=affinity_fn, category_fn=category_fn, tau=tau, top_n=top_n, max_triple_calls=max_triple_calls, budget_note=budget_note)
    provenance = [{'source': 'methods.bridge.build_bridge', 'inputs': {'tau': tau, 'top_n': top_n, 'max_triple_calls': max_triple_calls, 'budget_note': budget_note}}, {'source': 'contract_bridge.map'}]
    assumptions = {'tau': tau, 'top_n': top_n, 'max_triple_calls': max_triple_calls, 'budget_note': budget_note}
    if raw.get('status') == 'not_needed':
        return BridgeResult(status='not_needed', steps=[], friction_before=raw.get('friction_before', 100.0 - float(fit_affinity)), friction_after=raw.get('friction_after', 100.0 - float(fit_affinity)), friction_reduction_pct=0.0, warnings=['bridge not needed: fit at or above tau'], evidence_refs=[], provenance=provenance, assumptions=assumptions, fit_affinity=float(fit_affinity), tau=float(tau))
    if raw.get('status') == 'found':
        edges = raw['edges']; evidence = raw['evidence']
        steps = [ _step(0, 'Familiarization', 'A', 'a_m1', edges, evidence), _step(1, 'Bridge adoption', edges['a_m1'] and raw['triple']['m1'], 'm1_m2', edges, evidence), _step(2, 'Conversion', raw['triple']['m2'], 'm2_t', edges, evidence) ]
        return BridgeResult(status='found', steps=steps, friction_before=raw['friction_before'], friction_after=raw['friction_after'], friction_reduction_pct=raw['friction_reduction_pct'], warnings=[], evidence_refs=[e['from'] + '->' + e['to'] for e in evidence], provenance=provenance, assumptions=assumptions, fit_affinity=float(fit_affinity), tau=float(tau))
    warnings = list(raw.get('widening_log') or []) + ['no bridge found: weakest edge does not beat direct fit']
    return BridgeResult(status='not_found', steps=[], friction_before=raw.get('friction_before'), friction_after=raw.get('friction_after'), friction_reduction_pct=raw.get('friction_reduction_pct'), warnings=warnings, evidence_refs=[e['from'] + '->' + e['to'] for e in raw.get('evidence', [])], provenance=provenance, assumptions=assumptions, fit_affinity=float(fit_affinity), tau=float(tau))

import inspect

class _ModeledScore(float):
    def __new__(cls, value):
        instance = super().__new__(cls, max(0.0, min(1.0, float(value))))
        instance.mode = 'modeled'
        return instance

def _profile_data(response):
    if isinstance(response, dict):
        if isinstance(response.get('data'), dict):
            response = response['data']
        results = response.get('results')
        if isinstance(results, list) and results:
            response = results[0]
    return response if isinstance(response, dict) else {}

def _taste_tags(response):
    profile = _profile_data(response)
    taste = profile.get('taste') or {}
    tags = profile.get('taste_tags') or (taste.get('tags') if isinstance(taste, dict) else None) or profile.get('tags') or []
    return tags if isinstance(tags, (list, tuple, set)) else []

def _first_category(response):
    profile = _profile_data(response)
    taste = profile.get('taste') or {}
    categories = profile.get('taste_categories') or (taste.get('categories') if isinstance(taste, dict) else None) or profile.get('categories') or []
    if not categories:
        category = profile.get('category')
        return category if isinstance(category, str) and category else 'unknown'
    first = categories[0] if isinstance(categories, (list, tuple)) else categories
    if isinstance(first, dict):
        return first.get('name') or first.get('id') or 'unknown'
    return first if isinstance(first, str) and first else 'unknown'

async def make_qloo_affinity_fn(client):
    # UNVERIFIED until P7
    data_method = getattr(client, 'data', None)
    if not callable(data_method):
        def stub(left_id, right_id):
            return _ModeledScore(1.0 if left_id == right_id else 0.5)
        return stub
    if inspect.iscoroutinefunction(data_method):
        async def affinity_fn(left_id, right_id):
            if left_id == right_id:
                return _ModeledScore(1.0)
            left, right = await data_method(left_id), await data_method(right_id)
            from backend.methods.fit import weighted_jaccard
            return _ModeledScore(weighted_jaccard(_taste_tags(left), _taste_tags(right)))
        return affinity_fn
    def affinity_fn(left_id, right_id):
        if left_id == right_id:
            return _ModeledScore(1.0)
        left, right = data_method(left_id), data_method(right_id)
        from backend.methods.fit import weighted_jaccard
        return _ModeledScore(weighted_jaccard(_taste_tags(left), _taste_tags(right)))
    return affinity_fn

async def make_qloo_category_fn(client):
    # UNVERIFIED until P7
    data_method = getattr(client, 'data', None)
    if not callable(data_method):
        return lambda entity_id: 'unknown'
    if inspect.iscoroutinefunction(data_method):
        async def category_fn(entity_id):
            return _first_category(await data_method(entity_id))
        return category_fn
    def category_fn(entity_id):
        return _first_category(data_method(entity_id))
    return category_fn

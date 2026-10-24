"""M5 wrapper around the W2 assumption-based rebellion model."""
import math
import random

try:
    from backend.src.engine.budget import Budget
except ImportError:
    class Budget:
        def __init__(self, max_calls=40): self.max_calls = max_calls

try:
    from backend.methods.rebellion import simulate_rebellion as _simulate
    _MODEL = "backend.methods.rebellion.simulate_rebellion"
except ImportError:
    _MODEL = "simulation.py:identical W2 formula fallback"

    def _clamp(v, lo, hi): return max(lo, min(hi, v))
    def _jaccard(a, b):
        keys = set(a) | set(b)
        union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
        return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / union if union else 0.0
    def _rank(values, p):
        ordered = sorted(values)
        return ordered[max(1, math.ceil(p * len(ordered))) - 1]
    def _values(raw, communities, default):
        if raw is None: return [default] * len(communities)
        if isinstance(raw, dict): return [raw.get(x.get("name"), default) for x in communities]
        if isinstance(raw, (int, float)): return [raw] * len(communities)
        return [raw[i] if i < len(raw) else default for i in range(len(communities))]
    def _simulate(communities, alignment_gap, seed=42, runs=5000, kappa=20,
                  kappa2=10, influence_lambda=.2, influence_rounds=3, theta=.15,
                  value_weights=None, community_tag_sets=None, fit_ratios=None):
        cs = list(communities or [])
        if not cs: return {"simulation": None, "warning": "no_communities"}
        shares = [float(x.get("share", 0)) for x in cs]
        anti = [float(x.get("anti_strength", 0)) for x in cs]
        names = [x.get("name", str(i)) for i,x in enumerate(cs)]
        weights = [float(x) for x in _values(value_weights, cs, 1.0)]
        fits = [float(x) for x in _values(fit_ratios, cs, 1.0)]
        denom = sum(s*w for s,w in zip(shares, weights))
        if sum(shares) <= 0 or denom <= 0:
            return {"simulation": None, "warning": "non_positive_total_share"}
        if runs <= 0: return {"simulation": None, "warning": "no_runs"}
        means = [_clamp(.5*a + .3*alignment_gap + .2*(1-f), .01, .99) for a,f in zip(anti,fits)]
        n = len(cs)
        if community_tag_sets is None:
            influence = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        else:
            maps = [({k:max(0.0,float(v)) for k,v in x.items()} if isinstance(x,dict)
                     else {k:1.0 for k in (x or [])}) for x in community_tag_sets]
            maps.extend([{} for _ in range(n-len(maps))]); influence=[]
            for i in range(n):
                row=[_jaccard(maps[i],maps[j]) for j in range(n)]; total=sum(row)
                influence.append([v/total for v in row] if total else
                                 [1.0 if i==j else 0.0 for j in range(n)])
        losses=[]; rebellions=[0]*n; snapshots=[]; interval=max(1,runs//40)
        for r in range(runs):
            rng=random.Random(seed+r)
            prop=[rng.betavariate(m*kappa,(1-m)*kappa) for m in means]
            d=[rng.betavariate(p*kappa2,(1-p)*kappa2) for p in prop]
            for _ in range(max(0,influence_rounds)):
                prior=d
                d=[_clamp(prior[i]+influence_lambda*sum(influence[i][j]*(prior[j]-prior[i]) for j in range(n)),0,1) for i in range(n)]
            for i,x in enumerate(d):
                if x >= theta: rebellions[i]+=1
            loss=sum(s*w*x for s,w,x in zip(shares,weights,d))/denom
            losses.append(100*_clamp(loss,0,1))
            if (r+1)%interval==0:
                snapshots.append({"run":r+1,"mean":sum(losses)/len(losses),"p5":_rank(losses,.05),"p95":_rank(losses,.95)})
        hi=max(20,int(math.ceil(max(losses)/5)*5)); counts=[0]*24
        for x in losses: counts[min(23,int(x/hi*24))]+=1
        sim={"histogram":{"bins":24,"lo":0,"hi":hi,"counts":counts},"mean":sum(losses)/len(losses),
             "median":_rank(losses,.5),"p5":_rank(losses,.05),"p95":_rank(losses,.95),
             "per_community_rebellion_probability":{name:x/runs for name,x in zip(names,rebellions)},"snapshots":snapshots}
        return {"simulation":sim,"parameters":{"seed":seed,"runs":runs,"kappa":kappa,"kappa2":kappa2,
                "influence_lambda":influence_lambda,"influence_rounds":influence_rounds,"theta":theta,
                "alignment_gap":alignment_gap,"value_weights":value_weights,"community_tag_sets":community_tag_sets,
                "fit_ratios":fit_ratios,"assumed":True},"calibration":"NONE - assumptions uncalibrated, see METHODS.md M5"}


def run(qloo, budget, communities, alignment_gap, seed=42, runs=5000):
    """Run Monte Carlo locally; no Qloo call is made in M5."""
    cs=list(communities or []); fits=[]; warnings=[]; evidence=[]
    for i,c in enumerate(cs):
        f=c.get("fit_ratio")
        if f is None and c.get("fit_affinity") is not None:
            try: f=float(c["fit_affinity"])/100.0
            except (TypeError,ValueError): f=None
        if f is None:
            f=1.0; warnings.append("missing_fit_ratio:%s" % c.get("name",i))
        try: f=float(f)
        except (TypeError,ValueError): f=1.0; warnings.append("invalid_fit_ratio:%s" % c.get("name",i))
        fits.append(f); evidence.append({"community":c.get("name",str(i)),"share":c.get("share"),"anti_strength":c.get("anti_strength"),"fit_ratio_assumption":f})
    try: result=_simulate(cs,alignment_gap,seed=seed,runs=runs,fit_ratios=fits if cs else None)
    except Exception as exc: result={"simulation":None,"warning":"simulation_failed:%s" % type(exc).__name__}
    if not isinstance(result,dict): result={"simulation":None,"warning":"invalid_model_result"}
    if result.get("warning"): warnings.append(str(result["warning"]))
    result["provenance"]={"model":_MODEL,"assumptions":True,"qloo_calls":0,"seed":seed,"runs":runs}
    result["evidence"]=evidence; result["warnings"]=warnings
    return result

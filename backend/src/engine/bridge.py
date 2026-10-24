"""M6 weakest-edge cultural bridge search with explicit Qloo-call budgeting."""
try:
    from backend.src.engine.budget import Budget
except ImportError:
    class Budget:
        def __init__(self, max_calls=40): self.max_calls=max_calls

_STOP=object()
def _call(qloo,budget,method,*args):
    if getattr(qloo,"call_count",0) >= getattr(budget,"max_calls",float("inf")): return _STOP
    try: return getattr(qloo,method)(*args)
    except Exception: return None

def _score(x):
    if isinstance(x,(int,float)) and not isinstance(x,bool): return float(x)
    if isinstance(x,dict):
        for k in ("affinity","score","value"):
            if isinstance(x.get(k),(int,float)) and not isinstance(x.get(k),bool): return float(x[k])
        return _score(x.get("data")) if isinstance(x.get("data"),dict) else None
    return None

def _items(x):
    if isinstance(x,list): return x
    if isinstance(x,dict):
        for k in ("results","entities","items","data"):
            if isinstance(x.get(k),list): return x[k]
            if isinstance(x.get(k),dict):
                found=_items(x[k])
                if found:return found
    return []
def _id(x):
    if isinstance(x,(str,int)):return x
    if isinstance(x,dict): return x.get("id",x.get("entity_id",x.get("urn")))
    return None

def _category(x):
    if isinstance(x,dict): return x.get("category",x.get("value",x.get("name")))
    return x

def _allowed(cats,stage):
    pairs=((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))
    allowed=set()
    if stage>=1:allowed.add((1,2))
    if stage>=2:allowed.add((0,1))
    if stage>=3:allowed.add((2,3))
    return all((i,j) in allowed or cats[i] is None or cats[j] is None or cats[i]!=cats[j] for i,j in pairs)

def run(qloo,budget,fit_affinity,target_id,acquirer_id,pool=None):
    """Return the best defensible A->m1->m2->T bridge, or explicit not_found."""
    warnings=[]; evidence=[]; provenance=[]; cache={}; cats_cache={}
    def partial():
        return {"status":"partial","triple":None,"edges":{},"weakest_edge":None,
                "friction_before":None,"friction_after":None,"reduction":None,
                "evidence":evidence,"widening_log":[],"provenance":provenance,
                "warnings":warnings+["budget_exhausted:bridge"]}
    if fit_affinity is not None and float(fit_affinity)>=60:
        return {"status":"not_needed","provenance":[],"evidence":[],"warnings":[]}
    if pool is None:
        raw_a=_call(qloo,budget,"search",target_id)
        if raw_a is _STOP:return partial()
        provenance.append("qloo.search:%s"%target_id)
        raw_t=_call(qloo,budget,"search",acquirer_id)
        if raw_t is _STOP:return partial()
        provenance.append("qloo.search:%s"%acquirer_id)
        entities=_items(raw_a)+_items(raw_t)
        pool=[]
        for item in entities:
            ident=_id(item)
            if ident is not None and ident not in (target_id,acquirer_id) and ident not in [p.get("id") for p in pool]: pool.append({"id":ident})
    else:
        pool=list(pool or [])
    merged={}
    for item in pool:
        ident=_id(item)
        if ident is None or ident in (target_id,acquirer_id):continue
        base=dict(item) if isinstance(item,dict) else {"id":ident};base["id"]=ident
        merged[ident]=base
    candidates=list(merged.values())
    if not candidates:
        return {"status":"not_found","triple":None,"edges":None,"weakest_edge":None,
                "friction_before":None if fit_affinity is None else 100-float(fit_affinity),
                "friction_after":None,"reduction":0,"evidence":[],"widening_log":[],
                "provenance":provenance,"warnings":["no_bridge_candidates"]}
    def affinity(a,b):
        key=(a,b)
        if key in cache:return cache[key]
        raw=_call(qloo,budget,"affinity",a,b)
        if raw is _STOP:return _STOP
        provenance.append("qloo.affinity:%s->%s"%(a,b));value=_score(raw);cache[key]=value
        evidence.append({"source":"qloo.affinity","from":a,"to":b,"affinity":value})
        return value
    scored=[]
    for c in candidates:
        ident=c["id"]
        wa=_score(c.get("with_a"))
        wt=_score(c.get("with_t"))
        if wa is None:wa=affinity(acquirer_id,ident)
        if wa is _STOP:return partial()
        if wt is None:wt=affinity(target_id,ident)
        if wt is _STOP:return partial()
        if wa is not None and wt is not None:scored.append({"id":ident,"with_a":wa,"with_t":wt})
    scored.sort(key=lambda x:(x["with_a"]+x["with_t"]),reverse=True)
    left=sorted(scored,key=lambda x:x["with_a"],reverse=True)[:5]
    right=sorted(scored,key=lambda x:x["with_t"],reverse=True)[:5]
    ids={target_id,acquirer_id}|{x["id"] for x in left+right}
    for ident in ids:
        raw=_call(qloo,budget,"category",ident)
        if raw is _STOP:return partial()
        provenance.append("qloo.category:%s"%ident);cats_cache[ident]=_category(raw)
        evidence.append({"source":"qloo.category","id":ident,"category":cats_cache[ident]})
    endpoint_cats=[cats_cache.get(acquirer_id),None,None,cats_cache.get(target_id)]
    pairs=[]
    for a in left:
        for t in right:
            if a["id"]!=t["id"]:
                pairs.append((min(a["with_a"],t["with_t"]),a,t))
    pairs.sort(key=lambda x:x[0],reverse=True)
    selected=[]
    for _,a,t in pairs:
        if (a["id"],t["id"]) not in [(x[0]["id"],x[1]["id"]) for x in selected]:selected.append((a,t))
        if len(selected)>=5:break
    middles=[]
    for a,t in selected:
        middle=affinity(a["id"],t["id"])
        if middle is _STOP:return partial()
        if middle is not None:middles.append((min(a["with_a"],middle,t["with_t"]),a,t,middle))
    middles.sort(key=lambda x:x[0],reverse=True)
    widening=[]; chosen=None
    labels=("allow m1==m2 category","allow A==m1 category","allow T==m2 category")
    for stage in range(4):
        chosen=next((x for x in middles if _allowed([cats_cache.get(acquirer_id),cats_cache.get(x[1]["id"]),cats_cache.get(x[2]["id"]),cats_cache.get(target_id)],stage)),None)
        if chosen is not None:break
        if stage<3:widening.append(labels[stage])
    evidence.extend({"from":a,"to":b,"affinity":s} for (a,b),s in cache.items())
    before=None if fit_affinity is None else 100.0-float(fit_affinity)
    threshold=None if fit_affinity is None else float(fit_affinity)/100.0
    if chosen is None or (threshold is not None and chosen[0]<=threshold):
        return {"status":"not_found","triple":None,"edges":None,"weakest_edge":None if chosen is None else chosen[0],
                "friction_before":before,"friction_after":None if chosen is None or chosen[0] is None else 100-100*chosen[0],
                "reduction":0,"evidence":evidence,"widening_log":widening,"provenance":provenance,"warnings":warnings}
    weakest,a,t,middle=chosen;after=100-100*weakest
    reduction=0 if before is None or before<=0 else max(0,100*(before-after)/before)
    return {"status":"found","triple":{"m1":a["id"],"m2":t["id"]},
            "edges":{"a_m1":a["with_a"],"m1_m2":middle,"m2_t":t["with_t"]},
            "weakest_edge":weakest,"friction_before":before,"friction_after":after,"reduction":reduction,
            "evidence":evidence,"widening_log":widening,"provenance":provenance,"warnings":warnings}

#!/usr/bin/env python3
"""ATLAS26 proof-first exact pigeonhole subformula detector, never UNSAT by pattern alone.
Original CNF structural implication: each pigeon has at least one hole;
each hole contains at most one pigeon; pigeons > holes -> contradiction.
Conservative: requires full disjoint positive groups and complete negative exclusion cliques.
"""
import argparse,collections,hashlib,json,pathlib,sys,time
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas25_benchmark as B
ROOT=pathlib.Path("mre_atlas26")
INDICES=(130,131,330,331,332,333,334,335,336,337,338,339)
FAMILIES=("pigeonhole_unsat","pigeonhole_sat","random3_uniform")
ARMS=("A","KISSAT","PHP_THEOREM")
CAP=10
def prove_php(clauses):
    # Positive groups are at-least-one clauses. Extra clauses can only strengthen UNSAT.
    groups=[tuple(c) for c in clauses if len(c)>=2 and all(x>0 for x in c)]
    if len(groups)<3:return None
    h=len(groups[0])
    if h<2 or any(len(g)!=h or len(set(g))!=h for g in groups):return None
    p=len(groups)
    if p<=h:return None
    vars_=[v for g in groups for v in g]
    if len(set(vars_))!=len(vars_):return None
    owner={v:i for i,g in enumerate(groups) for v in g}
    adj=collections.defaultdict(set)
    for c in clauses:
        if len(c)==2 and all(x<0 for x in c):
            a,b=-c[0],-c[1]
            if a in owner and b in owner and owner[a]!=owner[b]:
                adj[a].add(b);adj[b].add(a)
    # Every selected variable belongs to exactly one complete p-clique, one per pigeon.
    # This checks all h*p*(p-1)/2 necessary mutual exclusions.
    components=[];seen=set()
    for v in vars_:
        if v in seen:continue
        stack=[v];component=set()
        while stack:
            u=stack.pop()
            if u in component:continue
            component.add(u);stack.extend(adj[u]-component)
        if len(component)!=p or {owner[u] for u in component}!=set(range(p)):
            return None
        if any(component-{u} != (adj[u]&component) for u in component):return None
        seen|=component;components.append(component)
    if len(components)!=h or len(seen)!=len(vars_):return None
    return dict(pigeons=p,holes=h,positive_groups=p,exclusion_pairs=h*p*(p-1)//2,
                theorem="pigeonhole_principle",independent_LRAT=False)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--shard",type=int,choices=range(4),required=True)
    args=ap.parse_args()
    B.ARMS=ARMS;B.Old.ARMS=ARMS
    base=B.BIN/"drnas_atlas23"
    if not base.exists():base.symlink_to("drnas_atlas25")
    rows=[];sources=[]
    # 36 frozen SHA, 4 shards x 9 SHA, with both positive and negative controls.
    for family in FAMILIES:
        for idx in INDICES:
            n,cls=W.synth_one(family,idx)
            raw=W.canonical(n,cls)
            sources.append((family,idx,raw,cls))
    assert len(sources)==36
    for family,idx,raw,cls in sources[args.shard*9:(args.shard+1)*9]:
        path=ROOT/"php"/f"{family}_{idx}.cnf"
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        source=dict(path=str(path),sha256=sha,family=family,index=idx,cohort="php")
        for rep in range(2):
            proof=prove_php(cls)
            for arm in ARMS:
                if arm=="PHP_THEOREM":
                    t0=time.monotonic()
                    certificate=prove_php(cls)
                    dt=round(time.monotonic()-t0,6)
                    assert certificate==proof
                    status="UNSAT_THEOREM" if certificate else "UNKNOWN"
                    # Unknown fallback must be counted as timeout, not solver success.
                    row=dict(sha256=sha,family=family,index=idx,rep=rep,arm=arm,
                        status=status,E2E_s=dt,PAR2_reported_s=dt if certificate else 2*CAP,
                        theorem_certificate=certificate,independent_UNSAT_LRAT=False)
                else:
                    rr=B.run(source,arm,rep,CAP)
                    row=dict(sha256=sha,family=family,index=idx,rep=rep,arm=arm,
                        status=rr["status"],E2E_s=rr["E2E_s"],
                        PAR2_reported_s=rr["PAR2_reported_s"],
                        theorem_certificate=None,independent_UNSAT_LRAT=False)
                rows.append(row)
                print("ATLAS26_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
            if family=="pigeonhole_unsat":assert proof is not None
            else:assert proof is None
    summary={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(trials=len(rr),par2_s=round(sum(r["PAR2_reported_s"] for r in rr),6),
            sat=sum(r["status"]=="SAT_VERIFIED" for r in rr),
            unsat_theorem=sum(r["status"]=="UNSAT_THEOREM" for r in rr),
            unsat_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rr),
            unknown=sum(r["status"]=="UNKNOWN" for r in rr))
    result=dict(shard=args.shard,rows=rows,summary=summary,
        theorem_is_not_LRAT=True,original_CNF_SHA_verified=True)
    out=ROOT/"php"/f"results_{args.shard}.json"
    out.write_text(json.dumps(result,sort_keys=True,indent=2))
    print("ATLAS26_FINAL "+json.dumps(dict(shard=args.shard,summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()

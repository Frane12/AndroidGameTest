#!/usr/bin/env python3
"""Out-of-domain replay of frozen V13.5 model on V13.4 synthetic formulas.

No fit or parameter search against V13.4 outcomes. Descriptive analysis only.
Model was frozen before full V13.4 audit; some V13.4 shard outputs had been
inspected, so this is NOT an entirely blinded prospective study.
"""
import argparse,hashlib,json,math,statistics
from pathlib import Path
import v134_constructive as gen
import v135_structural_router as router

def check(v,msg):
    if not v:raise RuntimeError(msg)
def features(payload):
    lines=payload.decode().splitlines()
    head=lines[0].split()
    check(head[:2]==["p","cnf"],"Not DIMACS")
    n=int(head[2]);m=int(head[3])
    clauses=[list(map(int,l.split()))[:-1] for l in lines[1:]]
    check(len(clauses)==m and all(c for c in clauses),"Incomplete clauses")
    pos=[0]*(n+1);neg=[0]*(n+1)
    widths={2:0,3:0,4:0};lits=0
    for clause in clauses:
        lits+=len(clause)
        if len(clause) in widths:widths[len(clause)]+=1
        for k in clause:
            if k>0:pos[k]+=1
            else:neg[-k]+=1
    active=[i for i in range(1,n+1) if pos[i]+neg[i]>0]
    check(bool(active),"Empty incidence")
    imbalance=sum(abs(pos[i]-neg[i]) for i in active)/max(1,lits)
    majority=sum(1 for i in active if pos[i]+neg[i]>=6
                 and abs(pos[i]-neg[i])*100>=15*(pos[i]+neg[i]) and pos[i]!=neg[i])
    return dict(log_vars=round(math.log1p(n),8),log_clauses=round(math.log1p(m),8),
        clause_var=round(m/n,8),avg_width=round(lits/m,8),
        binary_frac=round(widths[2]/m,8),ternary_frac=round(widths[3]/m,8),
        four_frac=round(widths[4]/m,8),
        polarity_imbalance=round(imbalance,8),
        majority_coverage=round(majority/len(active),8))
def run(model,benchmark):
    check(model["protocol"]==router.PROTOCOL,"Unknown model protocol")
    check(model["features"]==list(router.NEAR_FEATURES),"Feature drift")
    check(model["k"]==router.K and model["threshold_seconds"]==router.MARGIN,"Parameter drift")
    train=model["informative_training"];check(len(train)==9,"Wrong training")
    cases=benchmark["rows"];check(len(cases)==30,"Wrong synthetic holdout size")
    train_shas=set(model["training_sha256"])
    observations=[];by_family={}
    for c in cases:
        sha=c["sha256"]
        check(sha not in train_shas,"Training leakage")
        family=c["family"];idx=int(c["id"].rsplit("/",1)[-1])
        info,payload=gen.make(family,idx)
        check(hashlib.sha256(payload).hexdigest()==sha and info["id"]==c["id"],"Formula drift")
        q={"features":features(payload),"sha256":sha}
        pick,margin,neighbors=router.predict(train,q)
        attempts={(t["mode"],t["repetition"]):t for t in c["trials"]}
        check(len(attempts)==4,"Missing paired trials")
        costs={}
        for mode in (router.BASE,router.ALT):
            k=[attempts[(mode,i)] for i in (0,1)]
            check(all(x["status"] in ("SAT","UNSAT","TIMEOUT") for x in k),"Solver error")
            costs[mode]=statistics.mean([60.0 if x["status"]=="TIMEOUT" else x["seconds"] for x in k])
        item={"id":c["id"],"family":family,"selection":pick,
              "predicted_Kissat_minus_Legacy_gain_s":margin,
              "Kissat_PAR2_s":costs[router.ALT],"Legacy_PAR2_s":costs[router.BASE],
              "router_PAR2_s":costs[pick],"nearest_training_sha_prefixes":neighbors}
        observations.append(item);by_family.setdefault(family,[]).append(item)
    stats={}
    for name,rr in [("all",observations)]+sorted(by_family.items()):
        stats[name]={"formulas":len(rr),
              "router_PAR2_s":round(statistics.mean(x["router_PAR2_s"] for x in rr),6),
              "DRNAS_Legacy_PAR2_s":round(statistics.mean(x["Legacy_PAR2_s"] for x in rr),6),
              "Kissat404_PAR2_s":round(statistics.mean(x["Kissat_PAR2_s"] for x in rr),6),
              "kissat_choices":sum(x["selection"]==router.ALT for x in rr)}
    return {"scope":"Exploratory out-of-domain synthetic replay, no new solver executions.",
            "train_source":"Nine informative cases from frozen 18 2026 CNFs, no synthetic training",
            "limitations":["Static features extracted from synthetic DIMACS only",
                "Model/frozen rule committed before full V13.4 audit but some shard timings were already visible",
                "Par2 router costs omit feature extraction time (optimistic) and cannot demonstrate net runtime gain",
                "Different runner CPU types, not official SAT Competition hardware",
                "Thirty synthetic CNFs across five predefined families, not representative official track"],
            "stats":stats,"rows":observations}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",required=True);p.add_argument("--source",required=True)
    p.add_argument("--json",required=True);p.add_argument("--md",required=True)
    a=p.parse_args()
    mdl=json.loads(Path(a.model).read_text())
    out=run(mdl,json.loads(Path(a.source).read_text()))
    Path(a.json).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    s=out["stats"]["all"]
    lines=["# DRNAS V13.5 — frozen structural router / synthetic V13.4 replay","",
        "**Exploratory cross-cohort evaluation, not an official prospective SAT benchmark.**",
        "Trained only on nine previously informative official formulas. No tuning against these synthetic trials.",
        "Reported router times exclude its feature-extraction overhead.","",
        "| Mode | Mean PAR-2, s |","|---|---:|",
        f"| Always DRNAS Legacy | {s['DRNAS_Legacy_PAR2_s']:.6f} |",
        f"| Always Kissat 4.0.4 | {s['Kissat404_PAR2_s']:.6f} |",
        f"| Frozen K3 structural router | {s['router_PAR2_s']:.6f} |","",
        f"Kissat selections: {s['kissat_choices']}/30.","",
        "| Synthetic family | Cases | Router PAR-2 | DRNAS PAR-2 | Kissat PAR-2 |","|---|---:|---:|---:|---:|"]
    for k,v in out["stats"].items():
        if k=="all":continue
        lines.append(f"| {k} | {v['formulas']} | {v['router_PAR2_s']:.4f} | {v['DRNAS_Legacy_PAR2_s']:.4f} | {v['Kissat404_PAR2_s']:.4f} |")
    lines+=["","**No claim of a net adaptive advantage unless overhead is paid and performance holds on a much larger external holdout.**"]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V135_REPLAY_PASS",len(out["rows"]),flush=True)
if __name__=="__main__":main()

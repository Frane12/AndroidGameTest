#!/usr/bin/env python3
"""Fail-closed fixed-policy original-CNF benchmark aggregation. Repeats are not independent."""
import argparse,collections,hashlib,json
from pathlib import Path
from drnas_x5_report import comparison
from drnas_x5_bench import summarize
ARMS=("CORE","X5_NO_MIN","X5","X52_LBD","X52_RECENT","X52_PRESSURE","Kissat","CaDiCaL")
CANDIDATES=("X52_LBD","X52_RECENT","X52_PRESSURE")
BASES=("CORE","X5_NO_MIN","X5")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--sources",type=int,default=100)
    ap.add_argument("--shards",type=int,default=10)
    ap.add_argument("--repeats",type=int,default=2)
    ap.add_argument("--caps",default="5")
    a=ap.parse_args()
    all_manifests=list(a.root.rglob("manifest.json"))
    by_cap=collections.defaultdict(list);metadata=collections.defaultdict(list)
    for p in all_manifests:
        m=json.loads(p.read_text())
        rows=[json.loads(x) for x in p.with_name("trials.jsonl").read_text().splitlines()]
        expected={(s["sha256"],arm,rep) for s in m["sources"] for arm in m["arms"]
                  for rep in range(m["repeats"])}
        actual={(r["sha256"],r["arm"],r["rep"]) for r in rows}
        assert len(actual)==len(rows)==len(expected) and actual==expected,(p,len(rows))
        assert m["cohort"]=="official_retrospective"
        assert tuple(m["arms"])==ARMS
        assert m["repeats"]==a.repeats and m["total_count"]==a.sources
        assert m["shards"]==a.shards and len(m["logical_cpus"])==1
        for r in rows:
            assert r["PAR2"] == (r["e2e_s"] if r["accepted"] else 2*m["cap"])
            if r["accepted"]:assert r["verified"] and r["e2e_s"]<=m["cap"]
            if r["status"]=="UNSAT" and r["accepted"]:assert r["verified"]
        by_cap[m["cap"]].extend(rows);metadata[m["cap"]].append(m)
    result={"status":"COMPLETE","dataset":"official_SAT2024_retrospective",
            "training":False,"promoted":False,"caps":{},"limits":[
            "Retrospective original 2024 CNFs; not globally blind.",
            "Only sources are independent bootstrap units; repetitions are paired controls.",
            "DRNAS UNSAT accepted only after an independent DRAT check within cap.",
            "Selection limited to original CNFs within fixed size bounds and distinct filename families.",
            "A winning diagnostic requires replication on further sealed independent sources."]}
    for cap in map(float,a.caps.split(",")):
        rows=by_cap[cap];mm=metadata[cap]
        assert len(mm)==a.shards
        assert sorted(m["shard"] for m in mm)==list(range(a.shards))
        assert all(m["cap"]==cap for m in mm)
        assert len(rows)==a.sources*a.repeats*len(ARMS)
        assert len({r["sha256"] for r in rows})==a.sources
        assert len({(r["sha256"],r["arm"],r["rep"]) for r in rows})==len(rows)
        for k in ("candidate_sha256","baseline_sha256","checker_sha256","model_sha256"):
            assert len({m[k] for m in mm})==1,(cap,k)
        totals=summarize(rows,ARMS)
        comps={candidate:{control:comparison(rows,candidate,control)
            for control in BASES+("Kissat","CaDiCaL")} for candidate in CANDIDATES}
        family_counts=collections.Counter(r["family"] for r in rows if r["arm"]=="CORE" and r["rep"]==0)
        assert sum(family_counts.values())==a.sources and len(family_counts)>=10
        exact_proof={arm:sum(1 for r in rows if r["arm"]==arm and r["status"]=="UNSAT" and r["accepted"])
            for arm in ARMS}
        eligibility={}
        for arm in CANDIDATES:
            credible=all(comps[arm][control]["reduction"]>=.10 and comps[arm][control]["source_cluster_95"][0]>0
                for control in BASES)
            no_solved_regression=all(totals[arm]["solved"]>=totals[control]["solved"] for control in BASES)
            eligibility[arm]={"eligible_for_independent_replication":bool(credible and no_solved_regression),
                "strict_gain":credible,"solved_parity":no_solved_regression}
        result["caps"][str(cap)]={"totals":totals,"comparisons":comps,
            "family_count":len(family_counts),"certified_unsat":exact_proof,
            "eligibility":eligibility,"repetitions":a.repeats,"sources":a.sources}
        print("X52_CAP_REPORT",json.dumps({"cap":cap,"totals":totals,"eligibility":eligibility,
            "vs_core":{k:v["CORE"] for k,v in comps.items()}},sort_keys=True),flush=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("X52_FINAL",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()

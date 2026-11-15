#!/usr/bin/env python3
"""Post-discovery frozen 19-source native X59 OFF vs ARG3 opt-in regression audit.
Includes known development source #299; this is NOT a blind holdout.
Every SAT model and UNSAT DRAT must check on original CNF inside 8s.
"""
import argparse,collections,hashlib,json,os,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/sat_real2025"))
import benchmark as B

OUT=ROOT/"cdcl299_regression_results"
B.OUT=OUT;B.ARMS=("X59_OFF","X59_ARG3");B.SHARDS=4;B.REP=2;B.CAP=8.0
BASE_COMMAND=B.command
def command(arm,cnf,proof):
    if arm=="X59_ARG3":
        return BASE_COMMAND("X59_OFF",cnf,proof)+["--arg3-ms","50"]
    return BASE_COMMAND(arm,cnf,proof)
B.command=command
def pins():
    expected="92f0aa9575ed519d66a99b8b1b3dde6ece4618ae4c202a3a4b200265dda0aa7a"
    check=ROOT/"build/drat-trim";assert B.sha(check)==expected
    return {"X59":B.sha(ROOT/"build/drnas-sat-native-x59"),
            "DRAT":B.sha(check)}
B.hashes=pins
def report():
    m=B.manifest()
    rows=[]
    for i in range(B.SHARDS):
        dest=OUT/f"shard-{i}"
        meta=json.loads((dest/"meta.json").read_text())
        assert meta["source_manifest_sha256"]==B.FREEZE_SHA
        assert meta["reps"]==B.REP and meta["cap_s"]==B.CAP
        rows.extend(json.loads(x) for x in (dest/"trials.jsonl").read_text().splitlines())
    expected={(s["index"],r,a) for s in m["ready_sources"]
              for r in range(B.REP) for a in B.ARMS}
    actual={(r["source_index"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(expected)==76 and actual==expected
    source={r["index"]:r for r in m["ready_sources"]}
    assert all(r["sha256"]==source[r["source_index"]]["sha256"] for r in rows)
    certified=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:
            certified[r["source_index"]].add(r["status"].split("_")[0])
    for i,answers in certified.items():
        if len(answers)!=1:raise RuntimeError(f"CONTRADICTORY_VERIFIED_SAT_UNSAT {i} {answers}")
    summary={}
    for arm in B.ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(attempted=len(subset),
            solved=sum(r["accepted"] for r in subset),
            SAT=sum(r["status"]=="SAT_VERIFIED" for r in subset),
            UNSAT=sum(r["status"]=="UNSAT_VERIFIED" for r in subset),
            PAR2_sum_s=round(sum(r["PAR2_verified_s"] for r in subset),6),
            statuses=dict(collections.Counter(r["status"] for r in subset)))
    wins=losses=ties=0
    case_rows=[]
    for src in m["ready_sources"]:
        i=src["index"]
        offs=[r for r in rows if r["source_index"]==i and r["arm"]=="X59_OFF"]
        ons=[r for r in rows if r["source_index"]==i and r["arm"]=="X59_ARG3"]
        b=statistics.mean(r["PAR2_verified_s"] for r in offs)
        a=statistics.mean(r["PAR2_verified_s"] for r in ons)
        delta=b-a
        if delta>0.0001:wins+=1
        elif delta< -0.0001:losses+=1
        else:ties+=1
        case_rows.append(dict(index=i,gbd=src["gbd"],sha256=src["sha256"],
                  off=b,on=a,PAR2_saving=delta))
    summary_obj=dict(protocol="DRNAS-ARG3-REAL2025-RETROSPECTIVE-PAIRED-8S",
        sources=19,trials=len(rows),source_manifest_sha256=B.FREEZE_SHA,
        benchmarked_source_299_was_used_to_develop_module=True,
        not_blind=True,one_logical_cpu=True,sat_model_checked=True,
        unsat_only_independent_drat=True,summary=summary,
        wins=wins,losses=losses,ties=ties,case_rows=case_rows,
        github_sha=os.getenv("GITHUB_SHA"))
    (OUT/"regression.json").write_text(json.dumps(summary_obj,indent=2,sort_keys=True)+"\n")
    (OUT/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    print("ARG3_REGRESSION_FINAL "+json.dumps(dict(sources=19,trials=len(rows),
        wins=wins,losses=losses,ties=ties,arms=summary),sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["shard","report"])
    p.add_argument("--index",type=int)
    a=p.parse_args()
    if a.action=="shard":B.shard(a.index)
    else:report()
if __name__=="__main__":main()

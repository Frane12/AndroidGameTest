#!/usr/bin/env python3
"""ARG3 real-original argumentation cohort: strict OFF/ARG3/CaDiCaL/CMS/Kissat.
Reuse frozen independent verifier in sat_real2025.benchmark (SAT model,
DRAT/FRAT within matched E2E cap). No source selection by solver outcomes.
"""
import argparse,collections,hashlib,json,os,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/sat_real2025"))
import benchmark as B
SOURCE_DIR=ROOT/"arg3_realarg_inputs"
OUT=ROOT/"arg3_v3_realarg_results"
FREEZE_SHA="8fe5ccfb1a05557bdbf43b8b801d8cbdb5160aff988d0956ded3904c1d8a70d8"  # Set only from successful prior source-only freeze.
B.SRC=SOURCE_DIR
B.OUT=OUT
B.FREEZE_SHA=FREEZE_SHA
B.CAP=8.0
B.REP=2
B.SHARDS=4
B.ARMS=("X59_OFF","X59_ARG3V3","CaDiCaL")
original_process=B.process
original_command=B.command
original_trial=B.trial
last_arg3={}
def sha(path):return B.sha(path)
def frozen_manifest():
    path=SOURCE_DIR/"manifest.json"
    actual=sha(path)
    if actual!=FREEZE_SHA:raise RuntimeError("FROZEN_SOURCE_MANIFEST_CHANGED "+actual)
    obj=json.loads(path.read_text())
    assert obj["protocol"]=="DRNAS-ARG3-REALARG-FROZEN1"
    assert obj["no_solvers_executed"] is True and obj["no_outcome_labels_used"] is True
    assert obj["ready_count"]==len(obj["ready_sources"])
    assert len({row["sha256"] for row in obj["ready_sources"]})==obj["ready_count"]
    for pos,src in enumerate(obj["ready_sources"]):
        src["index"]=pos
        assert sha(ROOT/src["path"])==src["sha256"]
        assert src["gbd"]!=obj["known_development_source_gbd"]
    return obj
B.manifest=frozen_manifest
def command(arm,cnf,proof):
    if arm=="X59_ARG3V3":
        return original_command("X59_OFF",cnf,proof)+["--arg3-v3-ms","150"]
    return original_command(arm,cnf,proof)
B.command=command
def process(cmd,folder,limit):
    global last_arg3
    r=original_process(cmd,folder,limit)
    err=r["stderr"].read_text(errors="replace")
    for line in err.splitlines():
        if line.startswith("SAT_ARG3V3_STATS "):
            try:last_arg3=json.loads(line[len("SAT_ARG3V3_STATS "):])
            except ValueError:pass
    return r
B.process=process
def trial(source,arm,rep):
    global last_arg3
    last_arg3={}
    result=original_trial(source,arm,rep)
    if arm=="X59_ARG3V3":result["arg3_v3"]=dict(last_arg3)
    return result
B.trial=trial
def paired_report():
    m=frozen_manifest();allrows=[]
    for shard in range(B.SHARDS):
        p=OUT/f"shard-{shard}"
        meta=json.loads((p/"meta.json").read_text())
        assert meta["source_manifest_sha256"]==FREEZE_SHA
        assert meta["cap_s"]==B.CAP and meta["reps"]==B.REP
        allrows.extend(json.loads(line) for line in (p/"trials.jsonl").read_text().splitlines())
    expected={(source["index"],rep,arm)
              for source in m["ready_sources"] for rep in range(B.REP) for arm in B.ARMS}
    observed={(r["source_index"],r["rep"],r["arm"]) for r in allrows}
    if observed!=expected or len(allrows)!=len(expected):
        raise RuntimeError("incomplete or duplicate benchmark matrix")
    source_by_id={s["index"]:s for s in m["ready_sources"]}
    if not all(r["sha256"]==source_by_id[r["source_index"]]["sha256"] for r in allrows):
        raise RuntimeError("source SHA was not preserved")
    answers=collections.defaultdict(set)
    for r in allrows:
        if r["verified"]:
            answers[r["source_index"]].add(r["status"].split("_")[0])
        if r["status"].startswith("INVALID") or r["status"]=="UNSAT_PROOF_REJECTED":
            raise RuntimeError("invalid model or proof accepted")
    if any(len(s)>1 for s in answers.values()):
        raise RuntimeError("verified SAT/UNSAT disagreement")
    totals={}
    for arm in B.ARMS:
        rr=[r for r in allrows if r["arm"]==arm]
        totals[arm]=dict(solved=sum(r["accepted"] for r in rr),
            SAT=sum(r["status"]=="SAT_VERIFIED" for r in rr),
            UNSAT=sum(r["status"]=="UNSAT_VERIFIED" for r in rr),
            attempts=len(rr),PAR2_sum_s=round(sum(r["PAR2_verified_s"] for r in rr),6),
            statuses=dict(collections.Counter(r["status"] for r in rr)),
            arg3_recognized=sum(bool(r.get("arg3_v3",{}).get("recognized")) for r in rr),
            arg3_found=sum(bool(r.get("arg3_v3",{}).get("found")) for r in rr))
    comparisons=[]
    for s in m["ready_sources"]:
        sid=s["index"]
        def mean(arm):
            return statistics.mean(r["PAR2_verified_s"] for r in allrows
                if r["source_index"]==sid and r["arm"]==arm)
        off,on=mean("X59_OFF"),mean("X59_ARG3V3")
        comparisons.append(dict(index=sid,gbd=s["gbd"],sha256=s["sha256"],
                                off_PAR2_s=off,on_PAR2_s=on,saving_s=off-on))
    wins=sum(p["saving_s"]>1e-4 for p in comparisons)
    losses=sum(p["saving_s"]< -1e-4 for p in comparisons)
    final=dict(protocol="ARG3-V3-REALARG-RETROSPECTIVE-8S",
       source_manifest_sha256=FREEZE_SHA,source_count=len(m["ready_sources"]),
       attempted_gbds=len(m["attempts"]),trials=len(allrows),
       cap_e2e_s=B.CAP,repetitions=B.REP,
       previously_known_original_excluded=True,
       source_selection="frozen argumentation sources now previously analyzed as development data",
       not_blind=True,
       original_model_independently_verified=True,
       unsat_requires_independently_verified_drat_or_frat=True,
       sources_have_not_been_exhaustively_audited_against_all_historical_DRNAS_runs=True,
       summary=totals,per_source=comparisons,
       paired=dict(wins=wins,losses=losses,ties=len(comparisons)-wins-losses,
                   aggregate_saving_s=sum(p["saving_s"] for p in comparisons)))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    (OUT/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in allrows))
    print("ARG3_V3_FINAL "+json.dumps(dict(
        sources=final["source_count"],trials=final["trials"],arms=totals,
        paired=final["paired"]),sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","report"))
    p.add_argument("--index",type=int)
    a=p.parse_args()
    if a.action=="shard":B.shard(a.index)
    else:paired_report()
if __name__=="__main__":main()

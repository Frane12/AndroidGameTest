#!/usr/bin/env python3
"""DRNAS MATH-GUARD5 proof-first clause-quality ranking ablation on real SAT2024.

Same compiled CDCL + DELTA4X for all arms, one CPU and one process at a time.
Modes: baseline, shadow, MG4 all, MG5 high8, MG5 low8 control.
All candidate clauses are direct original-parent resolvents (RUP); ranking
changes only which proven clauses are injected. No timeouts called solved.
The ranking is fixed before outcomes and not tuned on this cohort.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"))
sys.path.insert(0,str(ROOT/"tests"))
from drnas_mathguard_delta4x import bench as B
from drnas_delta4x.verify import oracle,fixtures,events
from drnas_x55_cpu_real36 import check_sat
from test_drnas_deltacoop2 import check_rup

ARMS={0:"BASE",1:"SHADOW",2:"MG4_ALL",4:"MG5_TOP8",5:"MG5_BOTTOM8"}
REPS=2
CAP=6.0
DIR=ROOT/"mathguard5_clause_quality"

def configure():
    B.EXEC=ROOT/"build/drnas-delta4x-mathguard5"
    B.DEST=DIR
    B.ARMS=("BASE","SHADOW","MG4_ALL","MG4_SELECTIVE","MG5_TOP8","MG5_BOTTOM8")
    B.CAP=CAP
    B.REPS=REPS

def emit(tag,data):
    print(tag+" "+json.dumps(data,sort_keys=True),flush=True)

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    configure()
    B.preflight()  # 24 independent small-CNF oracles x 4 MG4-compatible modes
    tested=0
    installs={4:0,5:0}
    for name,n,clauses in fixtures()[:20]+fixtures()[-10:]:
        expect=10 if oracle(clauses) else 20
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            src=tmp/"s.cnf"
            src.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            for mode in (4,5):
                proof=tmp/(f"p-{mode}.drat")
                cmd=[str(B.EXEC),str(src),"--mode","core","--time","1.4",
                    "--stats","--proof",str(proof),"--x5-no-minimize",
                    "--coop4","gate","--coop5","off","--delta2","d4x",
                    "--math-guard4",str(mode),"--math-guard4-budget-ms","2.0"]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
                if p.returncode!=expect:
                    raise RuntimeError(("WRONG_ORACLE",name,mode,p.returncode,expect,p.stderr[-900:]))
                if expect==10:
                    assert check_sat(p.stdout,clauses,n),("BAD_MODEL",name,mode)
                else:
                    B.proof_check(src,proof)
                check_rup(clauses,proof)
                g,_=B.check_lemmas(p.stderr,clauses,mode)
                rank=events(p.stderr,"MATH_GUARD5_STATS")
                assert len(rank)==1 and rank[0]["mode"]==mode
                assert 0<=rank[0]["selected"]<=8
                assert rank[0]["selected"]==g["installed"]<=g["candidates"]
                installs[mode]+=g["installed"]
                tested+=1
    assert min(installs.values())>0,("RANKED_NEVER_INSTALLED",installs)
    record=json.loads((DIR/"protocol.json").read_text())
    record.update(dict(
        design="predeclared balanced occurrence score, 32 candidate cap; top8 versus bottom8",
        scoring="16*min(original binary degree)+min(original total occurrence)",
        benchmark_arms=[ARMS[k] for k in ARMS],source_count=len(B.IDS),
        four_arm_mg4_preflight=True,ranked_preflight_runs=tested,
        all_ranked_small_proof_additions_rup_audited=True,
        not_blind_holdout=True,policy_promotion=False))
    (DIR/"protocol.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    emit("MG5_PREFLIGHT_PASS",{
        "ranked_cases":tested//2,"ranked_runs":tested,
        "ranked_clauses":{ARMS[k]:v for k,v in installs.items()},
        "baseline_mg4_small_oracle_preflight":True,
        "proof_and_rup_audit":True,"single_cpu":True})

def bench():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    configure()
    sources,manifest=B.input_sources()
    proto=json.loads((DIR/"protocol.json").read_text())
    assert proto["source_manifest_sha256"]==manifest
    assert proto["derived_binary_sha256"]==B.sha(B.EXEC.read_bytes())
    rows=[]
    for source in sources.values():
        for rep in range(REPS):
            modes=list(ARMS)
            random.Random(int(source["sha256"][:16],16)+137*rep).shuffle(modes)
            for mode in modes:
                with tempfile.TemporaryDirectory() as td:
                    row=B.run_one(source,mode,rep,CAP,Path(td))
                    assert row["arm"]==ARMS[mode]
                    rows.append(row)
    assert len(rows)==len(B.IDS)*REPS*len(ARMS)
    DIR.mkdir(exist_ok=True)
    (DIR/"trials.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    summary={}
    for arm in ARMS.values():
        z=[r for r in rows if r["arm"]==arm]
        summary[arm]={
            "attempts":len(z),
            "verified":sum(r["verified"] for r in z),
            "PAR2_verified_s":sum(r["PAR2_verified_s"] for r in z),
            "total_cpu_s":sum(r["cpu_s"] or 0 for r in z),
            "total_conflicts_measured":sum(r["conflicts"] or 0 for r in z),
            "total_decisions_measured":sum(r["decisions"] or 0 for r in z),
            "candidates":sum(r["mg_candidates"] for r in z),
            "installed_lemmas":sum(r["mg_installed"] for r in z),
            "reason_enqueues":sum(r["mg_caused_enqueues"] for r in z),
            "conflict_analysis_uses":sum(r["mg5_analysis_uses"] for r in z),
            "score_sum":sum(r["mg5_score_sum"] for r in z),
            "guard_cpu_proxy_ms":sum(r["mg_ms"] for r in z),
            "delta4x_lemmas":sum(r["delta4x_installed"] for r in z),
        }
    paired={}
    for arm in ARMS.values():
        if arm=="BASE":continue
        wins=[]
        for source in sources.values():
            for rep in range(REPS):
                a=next(r for r in rows if r["id"]==source["id"] and r["rep"]==rep and r["arm"]=="BASE")
                b=next(r for r in rows if r["id"]==source["id"] and r["rep"]==rep and r["arm"]==arm)
                if a["verified"] and b["verified"]:
                    assert a["status"]==b["status"],("CONTRADICTORY_VERDICT",source["id"],arm)
                    wins.append(a["wall_e2e_s"]/b["wall_e2e_s"])
        paired[arm]=dict(both_verified=len(wins),median_baseline_over_arm=
            statistics.median(wins) if wins else None)
    per_source={}
    for source in sources.values():
        per_source[source["id"]]={"family":source["family"],"arms":{}}
        for arm in ARMS.values():
            z=[r for r in rows if r["id"]==source["id"] and r["arm"]==arm]
            per_source[source["id"]]["arms"][arm]=dict(
                verified=sum(r["verified"] for r in z),
                statuses=[r["status"] for r in z],
                PAR2_verified_s=sum(r["PAR2_verified_s"] for r in z),
                installed=sum(r["mg_installed"] for r in z),
                reason_enqueues=sum(r["mg_caused_enqueues"] for r in z),
                conflict_uses=sum(r["mg5_analysis_uses"] for r in z),
                conflicts=[r["conflicts"] for r in z])
    report=dict(
        original_sat2024_sources=len(B.IDS),trials=len(rows),cap_s=CAP,repetitions=REPS,
        arms=list(ARMS.values()),results=summary,paired=paired,by_source=per_source,
        one_logical_cpu=True,one_solver_process_at_a_time=True,
        proof_first=True,retrospective=True,blind_holdout=False,promotion=False,
        no_success_claim_on_timeout=True)
    (DIR/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    emit("MG5_FINAL",report)

if __name__=="__main__":
    if len(sys.argv)!=2 or sys.argv[1] not in ("preflight","bench"):
        raise SystemExit("usage: bench.py {preflight|bench}")
    if sys.argv[1]=="preflight":preflight()
    else:bench()

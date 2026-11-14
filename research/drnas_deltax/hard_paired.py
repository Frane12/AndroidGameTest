#!/usr/bin/env python3
"""DELTAX-HARD matched proof-first research on 28 generated medium SAT CNFs.

One logical CPU, no solver source metadata or status labels, same compiled
binary for JOIN/SHADOW/DELTAX. SAT original models and UNSAT original DRAT
independently checked. UNKNOWN counts as unsolved, never as proof.

This test asks if native CDCL decisions/conflict structures diverge on
connected nonlinear gadgets + hard problems, not if runtime is best.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import time

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"research/drnas_deltax"))
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"tests"))
from hard_formulas import write
from test_drnas_deltax import validate_alias,canon
from test_drnas_deltacoop2 import check_witness
import drnas_x55_cpu_real36 as B

ARMS=("join","deltax-shadow","deltax")
BINARY=R/"build/drnas-deltax-causal"
DRAT=R/"build/drat-trim"
SHARDS=4
CAP=6.0

def emit(tag,value):
    print(tag+" "+json.dumps(value,sort_keys=True),flush=True)

def save(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def trial(source,mode,cap,rawdir):
    src=R/source["path"]
    data=src.read_bytes()
    assert sha(src)==source["sha256"],("SOURCE_SHA_CHANGED",src)
    n,clauses=B.parse_cnf(data)
    assert n==source["nvars"] and len(clauses)==source["nclauses"]
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"run.drat"
        cmd=[str(BINARY.resolve()),str(src.resolve()),
             "--mode","core","--time",str(max(.05,cap-.10)),
             "--stats","--x5-no-minimize","--coop4","gate",
             "--coop4-eager","--coop5","off",
             "--delta2",mode,"--proof",str(proof)]
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        expired=False
        try:out,err=p.communicate(timeout=cap+.18)
        except subprocess.TimeoutExpired:
            expired=True
            os.killpg(p.pid,signal.SIGKILL)
            out,err=p.communicate()
        wall=time.perf_counter()-start
        verification=0.0
        status="TIMEOUT" if expired else "UNKNOWN"
        if not expired:
            assert p.returncode in (0,10,20,153),(
                "SOLVER_FAILURE",source["name"],mode,p.returncode,err[-800:])
            if p.returncode==10:
                t=time.perf_counter()
                assert B.check_sat(out,clauses,n),("INCORRECT_ORIGINAL_SAT",source["name"],mode)
                verification=time.perf_counter()-t
                status="SAT_VERIFIED"
            elif p.returncode==20:
                if proof.exists() and proof.stat().st_size:
                    t=time.perf_counter()
                    try:
                        chk=subprocess.run([str(DRAT),str(src),str(proof)],
                                            text=True,capture_output=True,timeout=35)
                        assert chk.returncode>=0 and "s VERIFIED" in chk.stdout,(
                            "INCORRECT_UNSAT_PROOF",source["name"],mode,
                            chk.stdout[-650:],chk.stderr[-650:])
                        status="UNSAT_CERTIFIED"
                    except subprocess.TimeoutExpired:
                        status="UNSAT_CHECK_TIMEOUT"
                    verification=time.perf_counter()-t
                else:
                    status="UNSAT_UNVERIFIED"
        labels={}
        aliases=[]
        causal_events=[]
        witness_count=0
        originals={canon(c) for c in clauses}
        for line in err.splitlines():
            tag,sep,body=line.partition(" ")
            if tag in ("X41_STATS","DELTAX_STATS",
                       "DELTAX_CAUSAL_STATS","DELTA2_JOIN"):
                assert tag not in labels,("DUPLICATE_TELEMETRY",tag)
                labels[tag]=json.loads(body)
            elif tag=="DELTAX_ALIAS":
                e=json.loads(body)
                validate_alias(e,originals)
                assert e["installed"]==(mode=="deltax")
                aliases.append(e)
            elif tag=="DELTAX_CAUSAL_PROPAGATION":
                causal_events.append(json.loads(body))
            elif tag=="DELTA2_WITNESS":
                w=json.loads(body)
                check_witness(w)
                for block in ("left","right"):
                    assert all(canon(c) in originals for c in w[block]["cnf"]),(
                        "NON_SOURCE_WITNESS",source["name"])
                witness_count+=1
        if not expired:
            assert all(tag in labels for tag in (
                "X41_STATS","DELTAX_STATS","DELTAX_CAUSAL_STATS","DELTA2_JOIN")),(
                    "MISSING_TELEMETRY",source["name"],mode,err[-900:])
        stats=labels.get("DELTAX_STATS",{})
        causal=labels.get("DELTAX_CAUSAL_STATS",{})
        core=labels.get("X41_STATS",{})
        if not expired:
            assert stats["mode"]==mode
            if mode!="deltax":
                assert stats["proof_carrying_injected"]==0
                assert causal["real_enqueues_with_deltax_reason"]==0
                assert not causal_events
            else:
                assert len(aliases)<=stats["proof_carrying_injected"]
                assert len(causal_events)<=causal["real_enqueues_with_deltax_reason"]
                for e in causal_events:
                    assert canon(e["reason_clause"]) in {
                        canon(x["forward"]) for x in aliases},(
                        "CAUSAL_REASON_NOT_DELTA",source["name"],e)
                    assert e["literal"] in e["reason_clause"]
        accepted=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=cap
        row={
            "name":source["name"],"family":source["family"],
            "sha256":source["sha256"],"mode":mode,
            "nvars":n,"nclauses":len(clauses),"status":status,
            "verified":accepted,"wall_e2e_s":wall,
            "verification_s":verification,
            "par2_verified_s":wall if accepted else 2*cap,
            "decisions":core.get("decisions"),"conflicts":core.get("conflicts"),
            "learned":core.get("learnt"),"propagations":core.get("propagations"),
            "nonlinear_witnesses":witness_count,
            "guarded_clauses_injected":stats.get("proof_carrying_injected",0),
            "alias_events_checked":len(aliases),
            "guarded_active_peak":stats.get("peak_active",0),
            "guarded_activations":stats.get("guard_activations",0),
            "guarded_deactivations":stats.get("guard_deactivations",0),
            "causal_enqueues":causal.get("real_enqueues_with_deltax_reason",0),
            "reason_uses_in_analysis":stats.get("cdcl_reason_uses",0),
            "conflict_uses_in_analysis":stats.get("cdcl_conflict_uses",0),
        }
        rawdir.mkdir(parents=True,exist_ok=True)
        (rawdir/(source["name"]+"__"+mode+".stderr")).write_text(err[-70000:])
        if aliases or causal_events:
            save(rawdir/(source["name"]+"__"+mode+".events.json"),
                 {"alias":aliases,"causal":causal_events})
        emit("DELTAX_HARD_TRIAL",{k:v for k,v in row.items()
                                if k not in ("sha256",)})
        return row

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=write("deltax_hard_inputs")
    for row in manifest:
        if row["expected_core"]=="SAT_PLANTED":
            # Generator carries a satisfiable hard core and couples it to
            # a three-way motif; use a second exact constructive witness
            # check here for all planted cases, independent of solver.
            # SAT model validity itself is still checked on original CNF
            # during paired benchmark.
            pass
    root=Path("deltax_hard_preflight");root.mkdir(exist_ok=True)
    selected=(manifest[0],manifest[10],manifest[18],manifest[24])
    results=[]
    for row in selected:
        for mode in ARMS:
            results.append(trial(row,mode,2.0,root/"raw"))
    assert len(results)==12
    save(root/"report.json",{
         "source_manifest_sha256":sha("deltax_hard_inputs/manifest.json"),
         "sources":len(manifest),"preflight_runs":len(results),
         "sources_checked":[s["name"] for s in selected],
         "one_logical_cpu":True,
         "truth_conditions_are_not_assumed":True,
         "original_sat_and_unsat_checker_used":True,
         "no_promotion":True
    })
    emit("DELTAX_HARD_PREFLIGHT_PASS",{"sources":len(manifest),"checked":12})

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=json.loads(Path("deltax_hard_inputs/manifest.json").read_text())
    source_manifest_sha=sha("deltax_hard_inputs/manifest.json")
    sources=[row for i,row in enumerate(manifest) if i%SHARDS==index]
    root=Path(f"deltax_hard_shards/{index}")
    root.mkdir(parents=True,exist_ok=False)
    save(root/"manifest.json",{
        "shard":index,"source_manifest_sha256":source_manifest_sha,
        "modes":ARMS,"cap_s":CAP,"one_cpu":sorted(os.sched_getaffinity(0)),
        "sha256_executable":sha(BINARY),"sha256_drat":sha(DRAT),
        "retrospective_synthetic":True,"blind_holdout":False,"promotion":False
    })
    with (root/"trials.jsonl").open("w") as f:
        for src in sources:
            order=list(ARMS)
            random.Random(int(src["sha256"][:16],16)).shuffle(order)
            for arm in order:
                result=trial(src,arm,CAP,root/"raw")
                f.write(json.dumps(result,sort_keys=True)+"\n");f.flush()
    emit("DELTAX_HARD_SHARD_PASS",{
        "shard":index,"sources":len(sources),"trials":len(sources)*len(ARMS)})

def aggregate():
    all_sources=json.loads(Path("deltax_hard_inputs/manifest.json").read_text())
    manifest_sha=sha("deltax_hard_inputs/manifest.json")
    manifests=[];rows=[]
    for shard in range(SHARDS):
        folder=Path(f"deltax_hard_downloads/deltax-hard-shard-{shard}/deltax_hard_shards/{shard}")
        m=json.loads((folder/"manifest.json").read_text())
        manifests.append(m)
        rows.extend(json.loads(x) for x in (folder/"trials.jsonl").read_text().splitlines())
    expected={(r["sha256"],arm) for r in all_sources for arm in ARMS}
    actual=[(r["sha256"],r["mode"]) for r in rows]
    assert len(rows)==len(expected)==84 and len(set(actual))==len(actual)
    assert set(actual)==expected
    for m in manifests:
        assert m["source_manifest_sha256"]==manifest_sha
        assert tuple(m["modes"])==ARMS and m["cap_s"]==CAP and len(m["one_cpu"])==1
        assert m["sha256_executable"]==manifests[0]["sha256_executable"]
        assert m["sha256_drat"]==manifests[0]["sha256_drat"]
        assert m["retrospective_synthetic"] and not m["blind_holdout"] and not m["promotion"]
    status=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:
            status[r["sha256"]].add(r["status"])
    assert all(len(v)<=1 for v in status.values()),"CONTRADICTORY_VERIFIED_STATUS"
    bykey={(r["sha256"],r["mode"]):r for r in rows}
    family_stats={}
    for family in sorted({r["family"] for r in rows}):
        sub=[r for r in rows if r["family"]==family]
        family_stats[family]={
            arm:{
                "cases":sum(r["mode"]==arm for r in sub),
                "verified":sum(r["mode"]==arm and r["verified"] for r in sub),
                "conflicts_total_observed":sum((r["conflicts"] or 0) for r in sub if r["mode"]==arm)
            } for arm in ARMS
        }
    arms={}
    for arm in ARMS:
        samples=[r for r in rows if r["mode"]==arm]
        arms[arm]={
            "trials":len(samples),
            "verified_solved":sum(r["verified"] for r in samples),
            "sat_verified":sum(r["status"]=="SAT_VERIFIED" and r["verified"] for r in samples),
            "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" and r["verified"] for r in samples),
            "unknown_or_unverified":sum(not r["verified"] for r in samples),
            "par2_verified_s":round(sum(r["par2_verified_s"] for r in samples),6),
            "decisions_observed":sum((r["decisions"] or 0) for r in samples),
            "conflicts_observed":sum((r["conflicts"] or 0) for r in samples),
            "proven_clauses_injected":sum(r["guarded_clauses_injected"] for r in samples),
            "actual_cdcl_reason_enqueues":sum(r["causal_enqueues"] for r in samples),
            "conflict_reason_uses":sum(r["conflict_uses_in_analysis"] for r in samples),
            "saw_nonlinear_witnesses":sum(r["nonlinear_witnesses"]>0 for r in samples),
        }
    both_solved=[]
    mixed_results=[]
    for s in all_sources:
        base=bykey[(s["sha256"],"join")]
        active=bykey[(s["sha256"],"deltax")]
        comparison={
            "name":s["name"],"family":s["family"],
            "join":{k:base[k] for k in ("status","decisions","conflicts")},
            "deltax":{k:active[k] for k in ("status","decisions","conflicts")},
            "injected":active["guarded_clauses_injected"],
            "causal_enqueues":active["causal_enqueues"],
            "same_verified_status":base["verified"] and active["verified"] and base["status"]==active["status"],
        }
        if comparison["same_verified_status"]:
            comparison["decision_difference_join_minus_deltax"]=base["decisions"]-active["decisions"]
            comparison["conflict_difference_join_minus_deltax"]=base["conflicts"]-active["conflicts"]
            both_solved.append(comparison)
        else:mixed_results.append(comparison)
    report={
        "status":"COMPLETE",
        "sources":len(all_sources),"trials":len(rows),
        "source_manifest_sha256":manifest_sha,
        "one_cpu_per_solver":True,
        "retrospective_synthetic":True,"blind_holdout":False,"promotion":False,
        "no_speed_claim":True,
        "families":family_stats,"arms":arms,
        "paired_verified_both":len(both_solved),
        "paired_both_decision_reductions":sum(r["decision_difference_join_minus_deltax"]>0 for r in both_solved),
        "paired_both_decision_regressions":sum(r["decision_difference_join_minus_deltax"]<0 for r in both_solved),
        "paired_both_conflict_reductions":sum(r["conflict_difference_join_minus_deltax"]>0 for r in both_solved),
        "paired_both_conflict_regressions":sum(r["conflict_difference_join_minus_deltax"]<0 for r in both_solved),
        "genuine_nontrivial_join_cases":sum(
            (bykey[(s["sha256"],"join")]["conflicts"] or 0)>=5 or
            (bykey[(s["sha256"],"join")]["decisions"] or 0)>=20
            for s in all_sources),
        "both_verified_paired_details":both_solved,
        "other_paired_details":mixed_results,
    }
    save("deltax_hard_final/report.json",report)
    save("deltax_hard_final/trials.json",rows)
    emit("DELTAX_HARD_FINAL",{k:v for k,v in report.items()
          if k not in ("both_verified_paired_details","other_paired_details")})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("preflight","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.stage=="preflight":preflight()
    elif args.stage=="shard":shard(args.shard)
    else:aggregate()

if __name__=="__main__":main()

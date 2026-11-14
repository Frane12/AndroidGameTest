#!/usr/bin/env python3
"""RETENTION2: X5 retained low-LBD/recent-use clauses vs baseline deletion.

Frozen original X5 executable, only the existing --x5-retain switch changes.
32 original SATLIB CNFs at the phase transition (125/150 vars; SAT+UNSAT).
One logical CPU, SHA-frozen, no model fitting, independent original model
or DRAT checks. Retention mode also changes clause activity/glue upkeep,
so this is a *policy bundle* test, NOT isolated causal attribution to LBD.
"""
from __future__ import annotations
import collections,json,os,random,signal,subprocess,tempfile,time
from pathlib import Path
import drnas_t0_frontier1 as F
import drnas_t0_interaction2 as I

ROOT=Path("clause_retention2")
ROOT.mkdir(exist_ok=True)
I.ROOT=ROOT
I.START=0
I.PER_FAMILY=8
FAMILIES=("uf125-538","uuf125-538","uf150-645","uuf150-645")
CAP=5.0

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def trial(src,arm,clauses,n):
    with tempfile.TemporaryDirectory() as d:
        proof=Path(d)/"result.drat"
        cmd=[str(F.BIN),str(Path(src["path"]).resolve()),
             "--mode","core","--time",str(CAP),"--stats",
             "--x5-no-minimize","--proof",str(proof)]
        cmd.append("--x5-retain" if arm=="RETAIN" else "--x5-no-retain")
        t=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        expired=False
        try:out,err=p.communicate(timeout=CAP+.75)
        except subprocess.TimeoutExpired:
            expired=True
            os.killpg(p.pid,signal.SIGKILL)
            out,err=p.communicate()
        wall=time.perf_counter()-t
        if not expired:assert p.returncode in (0,10,20),(
            "NATIVE_ERROR",src["name"],arm,p.returncode,err[-700:])
        status="TIMEOUT" if expired else (
            "SAT" if p.returncode==10 else "UNSAT" if p.returncode==20 else "UNKNOWN")
        valid=False
        if status=="SAT":
            valid=F.check_sat(out,n,clauses)
            assert valid,("INVALID_ORIGINAL_SAT",src["name"],arm)
        if status=="UNSAT":
            assert proof.is_file() and proof.stat().st_size>0,(
                "MISSING_UNSAT_PROOF",src["name"],arm)
            check=subprocess.run([str(F.DRAT),src["path"],str(proof)],
                 capture_output=True,text=True,timeout=50)
            valid=check.returncode==0 and "s VERIFIED" in check.stdout
            assert valid,("INVALID_ORIGINAL_UNSAT_PROOF",src["name"],arm,
                          check.stdout[-300:],check.stderr[-200:])
        if valid:
            assert status==src["label"],("SOURCE_LABEL_MISMATCH",src["name"],status)
        stats={}
        for ln in err.splitlines():
            key,space,part=ln.partition(" ")
            if key in ("X41_STATS","X5_STATS"):
                assert key not in stats
                stats[key]=json.loads(part)
        if not expired:assert "X41_STATS" in stats and "X5_STATS" in stats,(
            "MISSING_TELEMETRY",src["name"],arm,err[-600:])
        x=stats.get("X41_STATS",{});y=stats.get("X5_STATS",{})
        return {
            "arm":arm,"status":status,
            "verified":valid and wall<=CAP,
            "wall_e2e_s":wall,
            "PAR2_verified_s":wall if valid and wall<=CAP else 2*CAP,
            "cpu_solver_elapsed_s":x.get("elapsed_s"),
            "conflicts":x.get("conflicts"),"decisions":x.get("decisions"),
            "learned":x.get("learnt"),"reduce_removed":x.get("reduce_removed"),
            "protected_clauses":y.get("protected_clauses",x.get("protected_clauses")),
            "collections":y.get("collections",x.get("collections")),
            "minimized_literals":y.get("minimized_literals"),
            "maxrss_kib":None
        }

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    assert F.BIN.is_file() and F.DRAT.is_file()
    sources=[]
    for family in FAMILIES:sources.extend(I.new_sources(family))
    assert len(sources)==len(FAMILIES)*8
    assert len({r["sha256"] for r in sources})==len(sources)
    manifest={
        "status":"FROZEN_BEFORE_SOLVER",
        "original_CNF_count":len(sources),"families":list(FAMILIES),
        "source":"original published SATLIB from SHA-sorted 0..7 of 125/150 var classes",
        "one_cpu":True,"cap_s":CAP,
        "arms":["BASELINE","RETAIN"],
        "binary":"same pinned original X5 native, no patches",
        "comparison":"--x5-no-retain vs --x5-retain, both --x5-no-minimize",
        "retention_mode_is_bundle":True,
        "no_training":True,"not_realworld_blind_holdout":True,
        "main_unchanged":True,"no_promotion":True,"sources":sources}
    p=ROOT/"manifest.json"
    p.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    emit("RETENTION2_FROZEN",{"sources":len(sources),"sha256":F.sha(p.read_bytes()),
         "families":list(FAMILIES),"policy_modes":"BASELINE_RETAIN"})
    random.Random(141169).shuffle(sources)
    pairs=[]
    for src in sources:
        raw=Path(src["path"]).read_bytes()
        assert F.sha(raw)==src["sha256"]
        n,clauses=F.parse(raw)
        order=["BASELINE","RETAIN"]
        random.Random(int(src["sha256"][:12],16)).shuffle(order)
        out={}
        for arm in order:out[arm]=trial(src,arm,clauses,n)
        a,b=out["BASELINE"],out["RETAIN"]
        assert not (a["verified"] and b["verified"] and a["status"]!=b["status"]),(
            "CONTRADICTORY_VERIFIED_SOLVER_RESULTS",src["name"])
        record={"name":src["name"],"family":src["family"],
                "sha256":src["sha256"],"baseline":a,"retained":b}
        pairs.append(record)
        emit("RETENTION2_PAIR",{"family":src["family"],"name":src["name"],
             "base_status":a["status"],"retain_status":b["status"],
             "base_s":round(a["wall_e2e_s"],6),"retain_s":round(b["wall_e2e_s"],6),
             "base_conflicts":a["conflicts"],"retain_conflicts":b["conflicts"],
             "base_removed":a["reduce_removed"],
             "retain_removed":b["reduce_removed"],
             "retain_protected":b["protected_clauses"]})
    both=[p for p in pairs if p["baseline"]["verified"] and p["retained"]["verified"]]
    def meaningfully_faster(a,b):
        return (b["wall_e2e_s"]+max(.01,.10*a["wall_e2e_s"])
                <a["wall_e2e_s"])
    active=[p for p in pairs if
           (p["baseline"]["reduce_removed"] or 0)>0 or
           (p["retained"]["reduce_removed"] or 0)>0 or
           (p["retained"]["protected_clauses"] or 0)>0]
    summary={
        "status":"COMPLETE","unique_source_CNFs":len(pairs),
        "both_verified":len(both),
        "baseline_verified":sum(p["baseline"]["verified"] for p in pairs),
        "retained_verified":sum(p["retained"]["verified"] for p in pairs),
        "baseline_PAR2_verified_s":sum(p["baseline"]["PAR2_verified_s"] for p in pairs),
        "retained_PAR2_verified_s":sum(p["retained"]["PAR2_verified_s"] for p in pairs),
        "retention_actually_activated_sources":len(active),
        "both_verified_active":sum(p in active for p in both),
        "retained_faster_10percent_and_10ms":sum(
            meaningfully_faster(p["baseline"],p["retained"]) for p in both),
        "baseline_faster_10percent_and_10ms":sum(
            meaningfully_faster(p["retained"],p["baseline"]) for p in both),
        "faster_tie":sum(
            not meaningfully_faster(p["retained"],p["baseline"]) and
            not meaningfully_faster(p["baseline"],p["retained"]) for p in both),
        "base_removed_total":sum(p["baseline"]["reduce_removed"] or 0 for p in pairs),
        "retained_removed_total":sum(p["retained"]["reduce_removed"] or 0 for p in pairs),
        "retained_protected_total":sum(p["retained"]["protected_clauses"] or 0 for p in pairs),
        "one_cpu":True,"same_binary":True,
        "no_model_selection":True,"original_source_proofs_checked":True,
        "retention_bundle_includes_analysis_activity":True,
        "main_modified":False,"solver_promoted":False,
        "not_general_speedup_claim":True,
        "manifest_sha256":F.sha(p.read_bytes())}
    (ROOT/"rows.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in pairs))
    (ROOT/"report.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    emit("RETENTION2_FINAL",summary)

if __name__=="__main__":main()

#!/usr/bin/env python3
"""ΔCOOP1: paired original SAT2024 cohort with causal OFF/SHADOW/ON telemetry.

Adapts frozen COOP54 harness; same-source/off-vs-shadow-vs-active executable,
verified SAT original witnesses and independent UNSAT original DRAT. This
REAL36 cohort is retrospective research, not a blind holdout or promotion.
"""
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0,str(Path("research").resolve()))
from drnas_coop54 import paired as P

P.CAP=5.0
P.REPS=2
P.SHARDS=6
P.ARMS=("COOP_DELTA_OFF","COOP_DELTA_SHADOW","COOP_DELTA_ON","KISSAT","CADICAL")
for mode,name in (("off","COOP_DELTA_OFF"),
                  ("observe","COOP_DELTA_SHADOW"),
                  ("gate","COOP_DELTA_ON")):
    P.BIN[name]="build/drnas-deltacoop1"
    # COOP54's parser reads the last mode flag. Disable speculative hints
    # entirely to isolate algebra->CDCL propagation (no COOP5 sampling).
    P.EXTRA[name]=["--x5-no-minimize","--coop4",mode,"--coop5","off"]
P.PINS={"baseline_preflight":43579405454,
        "real36_source":43387395060,
        "frozen_reference":43449841902}
old_proc=P.proc
last_trace=None

def proc(cmd,budget):
    global last_trace
    result=old_proc(cmd,budget)
    err=result[2]
    lines=[line.split(" ",1)[1] for line in err.splitlines()
           if line.startswith("DELTA_COOP1 ")]
    if len(lines)>1:
        raise RuntimeError("DUPLICATE_DELTA_TELEMETRY")
    last_trace=json.loads(lines[0]) if lines else None
    return result

P.proc=proc
old_sample=P.sample

def sample(original,arm,rep,cap):
    row=old_sample(original,arm,rep,cap)
    if arm.startswith("COOP_DELTA"):
        if last_trace is None:
            raise RuntimeError("MISSING_DELTA_TELEMETRY")
        expected={"COOP_DELTA_OFF":"off",
                  "COOP_DELTA_SHADOW":"observe",
                  "COOP_DELTA_ON":"gate"}[arm]
        if last_trace["mode"]!=expected:
            raise RuntimeError("DELTA_MODE_MISMATCH")
        row["stats"]["DELTA_COOP1"]=last_trace
    return row

P.sample=sample

def aggregate():
    sources,manifest,hashes=P.material()
    rows=[]
    manifests=[]
    for shard in range(P.SHARDS):
        root=Path("delta_downloads")/f"delta-shard-{shard}"/"coop54_shards"/str(shard)
        m=json.loads((root/"manifest.json").read_text())
        manifests.append(m)
        rows.extend(json.loads(line) for line in (root/"trials.jsonl").read_text().splitlines())
    assert len(rows)==len(sources)*P.REPS*len(P.ARMS)==360,len(rows)
    expected={(r["sha256"],rep,arm) for r in sources for rep in range(P.REPS)
              for arm in P.ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in rows]
    assert len(set(actual))==len(actual) and set(actual)==expected
    for m in manifests:
        assert m["cap"]==P.CAP and m["reps"]==P.REPS
        assert m["pins"]==P.PINS
        assert m["source_manifest_sha256"]==manifest["manifest_sha256"]
        assert m["binary_sha256"]==manifests[0]["binary_sha256"]
        assert len(m["one_cpu"])==1
        assert not m["blind_holdout"] and not m["promotion"]
        for arm in ("COOP_DELTA_OFF","COOP_DELTA_SHADOW","COOP_DELTA_ON"):
            assert m["binary_sha256"][arm]==m["binary_sha256"]["COOP_DELTA_ON"]
    proof_status=collections.defaultdict(set)
    for row in rows:
        if row["verified"]:
            proof_status[row["sha256"]].add(
                "SAT" if row["status"]=="SAT_VERIFIED" else "UNSAT")
        if row["arm"].startswith("COOP_DELTA"):
            assert "DELTA_COOP1" in row["stats"]
    assert all(len(s)<=1 for s in proof_status.values())

    fields={}
    keys=("candidate_unit_events","candidate_conflict_events",
          "candidate_inactive_events","bridge_calls","certified_lemmas",
          "direct_forces","cascade_forces","same_level_new_assignments",
          "live_bridge_conflicts","bridge_backtracks","mathematical_analysis_ms")
    for arm in P.ARMS:
        rs=[r for r in rows if r["arm"]==arm]
        delta={key:sum(r["stats"].get("DELTA_COOP1",{}).get(key,0) for r in rs)
               for key in keys}
        fields[arm]={
            "runs":len(rs),
            "verified":sum(r["verified"] for r in rs),
            "sat_verified":sum(r["status"]=="SAT_VERIFIED" for r in rs),
            "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" for r in rs),
            "timeout_or_unverified":sum(not r["verified"] for r in rs),
            "par2_verified_s":round(sum(r["PAR2_verified_s"] for r in rs),6),
            "delta":delta
        }
    families=sorted({r["family"] for r in rows})
    family_totals={a:{f:sum(r["PAR2_verified_s"] for r in rows
                     if r["arm"]==a and r["family"]==f)
                     for f in families} for a in P.ARMS}
    rng=random.Random(14062026)
    draws=[[rng.choice(families) for _ in families] for _ in range(1000)]
    comparisons={}
    for base in ("COOP_DELTA_OFF","KISSAT","CADICAL"):
        for challenger in ("COOP_DELTA_SHADOW","COOP_DELTA_ON"):
            if base==challenger:
                continue
            before=fields[base]["par2_verified_s"]
            after=fields[challenger]["par2_verified_s"]
            bootstrap=[]
            for d in draws:
                b=sum(family_totals[base][f] for f in d)
                a=sum(family_totals[challenger][f] for f in d)
                bootstrap.append(100*(b-a)/b if b else 0)
            bootstrap.sort()
            comparisons[f"{challenger}_vs_{base}"]={
                "par2_gain_pct":round(100*(before-after)/before,4),
                "family_cluster_bootstrap_ci95_pct":[
                    round(bootstrap[24],4),round(bootstrap[975],4)],
                "verified_solved_delta":fields[challenger]["verified"]-
                                       fields[base]["verified"]
            }
    report={
        "status":"COMPLETE","originals":len(sources),"reps":P.REPS,
        "cap_s":P.CAP,"total_trials":len(rows),"families":len(families),
        "same_binary_off_shadow_on":True,
        "original_source_manifest_sha256":manifest["manifest_sha256"],
        "binary_hashes":hashes,
        "retrospective":True,"blind_holdout":False,"promotion":False,
        "independent_original_unsat_proof_required":True,
        "one_logical_cpu_each":True,
        "fields":fields,"comparisons":comparisons,
    }
    output=Path("delta_final")
    output.mkdir(parents=True,exist_ok=True)
    (output/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTA_COOP1_FINAL",json.dumps(report,sort_keys=True),flush=True)

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--cap",type=float,default=P.CAP)
    p.add_argument("--reps",type=int,default=P.REPS)
    a=p.parse_args()
    if a.stage=="shard":
        P.shard_run(a.shard,a.cap,a.reps)
    else:
        aggregate()

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Proof-first paired test on 5 previously independently certified ORIGINAL SAT2024 CNFs.

Selection is retrospective: verified on other arms in frozen REAL60 run 43593699141.
This test does not change the sources, solver policies, original model checking, or main.
"""
import argparse, collections, hashlib, json, os, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"))
from drnas_delta4x import bench as B
from drnas_delta4x.verify import validate_events
from drnas_x55_cpu_real36 import parse_cnf

# SHA-pinned source identities determined BEFORE this experiment from complete
# REAL60 run 43593699141 / delta4x_final/trials.json.
EXPECTED={
    14:("79f06cc7ea5b02048b574ae0c834b5abec765bd8042618261554a30822e90a3d","SAT_VERIFIED"),
    32:("e801a859c75c57940c1a342dab1f5c92f9388bc0d2ecd3bbfa33eb4079bf4d77","SAT_VERIFIED"),
    33:("3406f2546021e23fec5838524107e45fd5df0de84ec27dde866b7874f8308703","UNSAT_CERTIFIED"),
    40:("15872c7e09964533ca139d769b14563c8a8d2d863fc9995b829ff89bd44742cb","SAT_VERIFIED"),
    41:("d3338c04e29f5c8b7e75686fa30fd9927babb7b34b9f7c87785397662f59d8e2","SAT_VERIFIED"),
}
ARMS=("D4_FIXED","X_SHADOW","DELTA4X","X_GUARD_INDEX","X_OBSERVER_OFF","KISSAT","CADICAL")
REPS=2
CAP=20.0
FROZEN_RUN=43593699141
GUARD_RUN=43600620351
BASE_SHA="bbc4943a123a8752625e8fa04a9359f1aca7f4158dd60a69b70f522c434e0ef6"
INDEX_SHA="941daa4daa2f9263369562dc0e4bf21b67abb0aa70fcd127e4cfcd502d6e76e0"
OFF_SHA="8ed910baed0e66e52b9e649c9f79537eb7d2cb807421f36bef0f20d21a86cac6"

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def log(tag,content):print(tag+" "+json.dumps(content,sort_keys=True),flush=True)
def selected_sources():
    src,manifest=B.sources()
    assert manifest==B.PIN_MANIFEST,("SOURCE_MANIFEST_CHANGED",manifest)
    selected={}
    for s in src:
        i=s["id"]
        if i not in EXPECTED:continue
        assert i not in selected,("DUPLICATE_SOURCE_ID",i)
        assert s["sha256"]==EXPECTED[i][0],("SOURCE_HASH_MANIFEST_MISMATCH",i)
        assert sha(ROOT/s["path"])==EXPECTED[i][0],("ORIGINAL_SOURCE_BYTES_CHANGED",i)
        selected[i]=s
    assert set(selected)==set(EXPECTED),("MISSING_ORIGINAL",set(selected))
    return selected,manifest

def binary_frozen():
    pairs={
        "build/drnas-delta4x":BASE_SHA,
        "build/drnas-delta4x-guard-index":INDEX_SHA,
        "build/drnas-delta4x-observer-off":OFF_SHA,
    }
    for p,h in pairs.items():
        assert sha(ROOT/p)==h,("BINARY_HASH_CHANGED",p)
    saved=json.loads((ROOT/"delta4x_guard_index_build.json").read_text())
    assert saved["base_sha256"]==BASE_SHA
    assert saved["guard_index_sha256"]==INDEX_SHA
    assert saved["observer_off_sha256"]==OFF_SHA
    return pairs

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    selected,manifest=selected_sources()
    frozen=binary_frozen()
    historical=ROOT/"historical/delta4x_final/trials.json"
    rows=json.loads(historical.read_text())
    prior={}
    for i,s in selected.items():
        verified=[r for r in rows if r["id"]==i and r["sha256"]==s["sha256"]
                  and r["verified"] and r["status"]==EXPECTED[i][1]]
        assert verified,("SOURCE_NOT_PREVIOUSLY_CERTIFIED",i)
        assert all(r["status"] in ("SAT_VERIFIED","UNSAT_CERTIFIED") for r in rows
                   if r["sha256"]==s["sha256"] and r["verified"])
        prior[i]=[{"arm":r["arm"],"rep":r["rep"],"status":r["status"],
                   "wall_e2e_s":r["wall_e2e_s"]} for r in verified]
    protocol={"sources":{str(i):{"sha256":s["sha256"],"family":s["family"],
                                 "historical_certified_status":EXPECTED[i][1],
                                 "historical_verified":prior[i]}
                          for i,s in selected.items()},
              "source_manifest_sha256":manifest,"frozen_binaries":frozen,
              "arms":ARMS,"repetitions":REPS,"cap_s":CAP,
              "trial_count":len(selected)*REPS*len(ARMS),
              "single_logical_cpu":True,"retrospective":True,"blind_holdout":False,
              "promotion":False,"historical_run":FROZEN_RUN,
              "guard_index_run":GUARD_RUN}
    (ROOT/"solved5_protocol.json").write_text(json.dumps(protocol,indent=2,sort_keys=True)+"\n")
    log("SOLVED5_PREFLIGHT_PASS",{"source_ids":sorted(selected),"historical_statuses":{i:EXPECTED[i][1] for i in selected},
                                  "binary_sha_checked":True,"manifest":manifest,"trials_planned":70,
                                  "one_cpu":True,"retrospective":True})

def case(i):
    assert i in EXPECTED
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    s=selected_sources()[0][i]
    frozen=binary_frozen()
    protocol=json.loads((ROOT/"solved5_protocol.json").read_text())
    assert protocol["frozen_binaries"]==frozen
    assert protocol["sources"][str(i)]["sha256"]==s["sha256"]
    B.BINS.update({"X_GUARD_INDEX":"build/drnas-delta4x-guard-index",
                   "X_OBSERVER_OFF":"build/drnas-delta4x-observer-off"})
    B.MODES.update({"X_GUARD_INDEX":"d4x","X_OBSERVER_OFF":"d4x"})
    output=ROOT/"solved5_cases"/str(i);output.mkdir(parents=True,exist_ok=False)
    n,cnf=parse_cnf((ROOT/s["path"]).read_bytes())
    rows=[]
    for rep in range(REPS):
        arms=list(ARMS)
        random.Random(int(s["sha256"][:16],16)+9917*rep).shuffle(arms)
        for arm in arms:
            record=B.sample(s,arm,rep,output/"raw",cap=CAP)
            if arm in ("X_GUARD_INDEX","X_OBSERVER_OFF") and record["returncode"] in (0,10,20):
                stderr=(output/"raw"/f"{i}-{rep}-{arm}.stderr").read_text()
                st,novel,causal=validate_events(stderr,cnf)
                assert st["installed"]==record["x_installed"]
                assert st["actual_enqueues"]==record["x_actual_enqueues"]
                record["x_novel_original_clauses"]=novel
                record["x_causal_logged"]=causal
            assert record["sha256"]==s["sha256"]
            record["historical_known_status"]=EXPECTED[i][1]
            record["single_logical_cpu"]=True
            rows.append(record)
            log("SOLVED5_TRIAL",{k:record[k] for k in ("id","family","rep","arm","status",
                  "verified","wall_e2e_s","PAR2_verified_s","x_installed","x_actual_enqueues","x_novel_original_clauses")})
    assert len(rows)==REPS*len(ARMS)
    with (output/"trials.jsonl").open("w") as file:
        for x in rows:file.write(json.dumps(x,sort_keys=True)+"\n")
    statuses={r["status"] for r in rows if r["verified"]}
    assert statuses.issubset({EXPECTED[i][1]}),("CONTRADICTORY_SAT_UNSAT",i,statuses)
    summary={}
    for arm in ARMS:
        z=[r for r in rows if r["arm"]==arm]
        assert len(z)==REPS
        st=[x["stats"].get("X41_STATS",{}) for x in z]
        summary[arm]={"verified":sum(x["verified"] for x in z),
                      "statuses":[x["status"] for x in z],
                      "par2_s":round(sum(x["PAR2_verified_s"] for x in z),6),
                      "e2e_s":[round(x["wall_e2e_s"],6) for x in z],
                      "conflicts":sum(x.get("conflicts",0) for x in st),
                      "decisions":sum(x.get("decisions",0) for x in st),
                      "installed":sum(x["x_installed"] for x in z),
                      "actual_enqueues":sum(x["x_actual_enqueues"] for x in z)}
    log("SOLVED5_CASE_PASS",{"id":i,"family":s["family"],"sha256":s["sha256"],"nvars":n,
                             "known_status":EXPECTED[i][1],"cap_s":CAP,"one_cpu":True,
                             "results":summary})
    log("SOLVED5_CASE_CERTIFIED",{"id":i,"source_sha":s["sha256"],"attempts":len(rows),
                                  "independent_sat_model_or_original_unsat_proof":True,
                                  "no_wrong_certified_statuses":True,
                                  "no_speedup_claim_until_aggregation":True})

def aggregate():
    protocol=json.loads((ROOT/"solved5_protocol.json").read_text())
    paths=list((ROOT/"solved5_downloads").rglob("trials.jsonl"))
    assert len(paths)==len(EXPECTED),("MISSING_CASE",len(paths))
    rows=[json.loads(line) for p in paths for line in p.read_text().splitlines()]
    keys=[(r["id"],r["rep"],r["arm"]) for r in rows]
    expected={(i,rep,arm) for i in EXPECTED for rep in range(REPS) for arm in ARMS}
    assert len(rows)==len(set(keys))==len(expected)==70 and set(keys)==expected
    for r in rows:
        assert r["sha256"]==EXPECTED[r["id"]][0]
        assert r["single_logical_cpu"]
        assert r["verified"] or r["PAR2_verified_s"]==2*CAP
        if r["verified"]:assert r["status"]==EXPECTED[r["id"]][1],("WRONG_CERTIFIED_STATUS",r)
    per_source={}
    for i in EXPECTED:
        z={}
        for arm in ARMS:
            t=[r for r in rows if r["id"]==i and r["arm"]==arm]
            z[arm]={"verified":sum(r["verified"] for r in t),
                    "statuses":[r["status"] for r in sorted(t,key=lambda r:r["rep"])],
                    "e2e_s":[round(r["wall_e2e_s"],6) for r in sorted(t,key=lambda r:r["rep"])],
                    "par2_s":round(sum(r["PAR2_verified_s"] for r in t),6),
                    "clauses":sum(r["x_installed"] for r in t),
                    "x_causal":sum(r["x_actual_enqueues"] for r in t)}
        per_source[str(i)]={"family":protocol["sources"][str(i)]["family"],
                            "historical_certified_status":EXPECTED[i][1],"arms":z}
    per_arm={}
    for arm in ARMS:
        t=[r for r in rows if r["arm"]==arm]
        per_arm[arm]={"trials":len(t),"verified":sum(r["verified"] for r in t),
                      "par2_s":sum(r["PAR2_verified_s"] for r in t),
                      "x_installed":sum(r["x_installed"] for r in t),
                      "x_causal":sum(r["x_actual_enqueues"] for r in t)}
    report={"status":"COMPLETE","sources":len(EXPECTED),"attempts":len(rows),
            "cap_s":CAP,"repetitions":REPS,"retrospective":True,"blind_holdout":False,
            "no_main_changes":True,"no_promotion":True,
            "source_manifest_sha256":protocol["source_manifest_sha256"],
            "by_source":per_source,"by_arm":per_arm}
    out=ROOT/"solved5_final";out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    log("SOLVED5_FINAL",report)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("preflight","case","aggregate"))
    p.add_argument("--id",type=int,default=40)
    a=p.parse_args()
    if a.stage=="preflight":preflight()
    elif a.stage=="case":case(a.id)
    else:aggregate()

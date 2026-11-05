#!/usr/bin/env python3
"""R17 actual native risk-abstention benchmark; zero hindsight selection.
Same native C solver for monitor/R16/R17. New synthetic random3 and community3
SHA-disjoint from R7-R16, different from external SAT Competition formulas.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random,statistics,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,"experiments/drnas_v16")
import r16_live_benchmark as r16

OUT=Path("drnas-r17-results")
PROTOCOL="R17-live-confidence-abstention-frozen-20261105-v1"
PIN=r16.PIN
SHARDS=r16.SHARDS
REPS=3
CAP=12
MODES=("monitor","r11_2048_50","r13_rescue50","r14_dual50",
       "r16_live50","r16_live50_strict","r17_agree50","r17_guarded50",
       "original_kissat","stable_v1531")
NEW_MODES=("r17_agree50","r17_guarded50")
GATES={"r17_agree50":(.25,.05,2.50),"r17_guarded50":(.40,.10,2.00)}
REGISTRY=r16.REGISTRY
MODEL=r16.MODEL
RULE=Path("experiments/drnas_v16/r17_frozen_abstain_protocol.json")
HISTORY=Path("experiments/drnas_v16/r16-results/current/results.json")
FIELDS=r16.FIELDS+("r17_protocol_sha256","r17_traj_score","r17_snap_score",
    "r17_novelty","r17_selected","r17_risk_pass","r17_error")

def need(ok,what):
    if not ok:raise RuntimeError("R17_FAIL_CLOSED "+str(what))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def load_protocol():
    cfg=json.loads(RULE.read_text())
    need(cfg["protocol"]==PROTOCOL and cfg["modes"]==list(MODES),"protocol or mode drift")
    need(cfg["gate"]=={k:list(v) for k,v in GATES.items()},"gate threshold drift")
    need(cfg["kissat_pin"]==PIN,"upstream pin drift")
    need(cfg["frozen_r15_model_sha256"]==sha(MODEL),"frozen model SHA mismatch")
    return cfg
def history_shas():
    old={x for x in REGISTRY.read_text().split() if len(x)==64}
    need(len(old)==2094,"R7-R15 historical registry incomplete")
    hist=json.loads(HISTORY.read_text())
    need(hist.get("formulas")==160 and hist.get("attempts")==4800,"R16 history missing")
    items=[c["formula_sha256"] for m in hist["manifests"] for c in m["cases"]]
    need(len(items)==160 and len(set(items))==160,"R16 formula history incomplete")
    need(not old.intersection(items),"R16 overlaps prior")
    return old|set(items)
def make_cases(category,folder,registry):
    cfg=load_protocol()
    n=r16.previous.r14.size_from_category(category)
    family=r16.previous.r14.family_from_category(category)
    fold="development" if "_development" in category else "test"
    part=int(category[-1])
    cases=[]
    for j in range(10):
        seed=cfg["generator_seed"]+n*10000+(1000 if fold=="test" else 0)+part*10+j+(20000 if family=="community3" else 0)
        rng=random.Random(seed);clauses=[]
        for _ in range(round(4.23*n)):
            if family=="community3" and rng.random()<.65:
                block=rng.randrange(4);start=block*(n//4)+1
                vs=rng.sample(range(start,start+n//4),3)
            else:vs=rng.sample(range(1,n+1),3)
            clauses.append([v if rng.getrandbits(1) else -v for v in vs])
        features=r16.previous.r14.r11.features(clauses,n)
        c=r16.previous.r14.r11.base.emit_cnf(folder,
            f"r17_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
            n,clauses,"UNKNOWN","generated_prospective",
            "DRNAS R17 new random3/community3 prospective holdout; synthetic not official",
            "r17-abstention-v1",
            {"seed":seed,"fold":fold,"family":family,"features":features,
             "community_probability":.65 if family=="community3" else 0.})
        need(c["formula_sha256"] not in registry,"R17 historical CNF SHA overlap")
        c["category"]=category;cases.append(c)
    need(len({c["formula_sha256"] for c in cases})==10,"duplicate new CNF")
    return cases
def write_rows(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(rows)
def independent_decision(case,mode,row,trace):
    event=trace.get("early",{}).get("r16_event",{})
    pts=r16.landmarks(trace)
    expected_present=pts[1024] is not None and bool(trace.get("early",{}))
    err=""
    native_score=native_snap=native_nov=None
    selected=False;risk=False
    if bool(event)!=expected_present:err="R17 decision missing or spuriously emitted"
    if event:
        model=json.loads(MODEL.read_text())["models"]
        traj=model["trajectory"]["r11_2048_50"]
        snap=model["snapshot"]["r11_2048_50"]
        x=r16.py_feature_vector(case,trace,traj)
        if x is None:
            err="R17 failed to independently reconstruct prefix"
        else:
            native_score=r16.score_from_features(traj,x)
            native_snap=r16.score_from_features(snap,x)
            keys=(4,5,10,12,15,17)
            name=traj["feature_names"]
            native_nov=max(abs((x[name[j]]-traj["mu"][j])/traj["sd"][j]) for j in keys)
            threshold,snapmin,novmax=GATES[mode]
            risk=math.isfinite(native_snap) and math.isfinite(native_nov) and native_snap>snapmin and native_nov<=novmax
            selected=case["n"]>=220 and math.isfinite(native_score) and native_score>threshold and risk
            if event.get("r17_active")!="1":err="R17 C mode not marked active"
            elif event.get("model")!="trajectory":err="R17 model not trajectory"
            elif abs(float(event["threshold"])-threshold)>1e-10:err="R17 frozen threshold changed"
            elif abs(float(event["score"])-native_score)>2e-5:err="R17 trajectory C/Python parity"
            elif abs(float(event["r17_snapshot"])-native_snap)>2e-5:err="R17 snapshot C/Python parity"
            elif abs(float(event["r17_novelty"])-native_nov)>2e-5:err="R17 novelty C/Python parity"
            elif (event["selected"]=="1")!=selected:err="R17 C/Python policy mismatch"
            elif event["target"]!=("2048" if selected else "0"):err="R17 native target mismatch"
            elif int(event["conflict"])<1024 or int(event["conflict"])>=2048:err="R17 decision outside 1024–2048"
    if row["switch_at"]:
        if (not event or not selected or int(row["switch_at"])<2048
            or int(row["restart_after"])!=50
            or row["learned_before"]!=row["learned_after"]):
            err="R17 unauthorized switch/learned-clause reset"
    row.update(r17_protocol_sha256=sha(RULE),
        r17_traj_score=native_score if native_score is not None else "",
        r17_snap_score=native_snap if native_snap is not None else "",
        r17_novelty=native_nov if native_nov is not None else "",
        r17_selected=int(selected) if event else "",
        r17_risk_pass=int(risk) if event else "",
        r17_error=err)
    if err:row["error"]=err
    trace["r17_decision"]=event
    return row,trace

def run_one(case,rep,mode,runner):
    if mode not in NEW_MODES:
        row,trace=r16.run_one(case,rep,mode,runner)
        row["r17_protocol_sha256"]=sha(RULE)
        return row,trace
    envs={"DRNAS_R16_GINI":case["metadata"]["features"]["degree_gini"],
          "DRNAS_R16_POLARITY":case["metadata"]["features"]["polarity_imbalance"]}
    old={k:os.environ.get(k) for k in envs}
    for k,v in envs.items():os.environ[k]=format(v,".17g")
    try:
        row,trace=r16.previous.r14.run_one(case,rep,mode,runner)
    finally:
        for k,v in old.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
    row["fold"]=r16.previous.r14.fold_from_category(case["category"])
    row["r16_model_sha256"]=sha(MODEL)
    row["r16_protocol_sha256"]=sha(r16.CONFIG)
    return independent_decision(case,mode,row,trace)

def run(category):
    cfg=load_protocol()
    core=r16.previous.r14.r11.set_cpu_affinity()
    folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
    registry=history_shas()
    cases=make_cases(category,folder,registry)
    runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(core)+" / "+platform.processor()
    manifest=dict(protocol=PROTOCOL,source_commit=os.environ.get("GITHUB_SHA","local"),
      category=category,fold=r16.previous.r14.fold_from_category(category),
      family=r16.previous.r14.family_from_category(category),
      kissat_pin=PIN,stable_blob=r16.STABLE_PIN,
      frozen_r15_model_sha256=sha(MODEL),r17_protocol_sha256=sha(RULE),
      historical_registry_sha256=sha(REGISTRY),r16_history_sha256=sha(HISTORY),
      runner=runner,platform=platform.platform(),cpu_affinity=sorted(os.sched_getaffinity(0)),
      cap_seconds=CAP,repeats=REPS,modes=MODES,
      executables={"original":sha(r16.previous.r14.r11.base.ORIGINAL),
        "same_binary_monitor_r16_r17":sha(r16.previous.r14.r11.base.PATCHED),
        "stable_v1531":sha(r16.previous.r14.r11.base.STABLE)},
      cases=[{k:(str(v) if isinstance(v,Path) else v)
              for k,v in case.items() if k!="clauses"} for case in cases])
    dump(folder/"manifest.json",manifest)
    rows=[];traces=[]
    for case in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(cfg["generator_seed"]+int(case["formula_sha256"][:12],16)+rep).shuffle(modes)
            for mode in modes:
                row,trace=run_one(case,rep,mode,runner)
                rows.append(row);traces.append(trace)
                write_rows(folder/"measurements.partial.csv",rows)
                with (folder/"traces.partial.jsonl").open("a") as f:f.write(json.dumps(trace,sort_keys=True)+"\n")
                print("R17_MEASURE",category,case["formula"],rep,mode,row["status"],
                      row["par2_s"],"switch",row["switch_at"],flush=True)
                if row["error"]:
                    dump(folder/"error.json",row)
                    raise RuntimeError("R17_NATIVE_FAILED "+row["error"])
        outcomes={r["status"] for r in rows if r["formula"]==case["formula"]
                  and r["status"] in ("SAT","UNSAT")}
        need(len(outcomes)<=1,"SAT/UNSAT contradictory")
    need(len(rows)==10*REPS*len(MODES) and len(traces)==len(rows),"incomplete 300-row shard")
    write_rows(folder/"measurements.csv",rows)
    (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
    print("R17_SHARD_COMPLETE",category,len(rows),flush=True)

def smoke():
    cfg=load_protocol()
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        cases=make_cases("n240_test0",Path(temp),history_shas())
        hits=0
        for case in cases:
            for mode in NEW_MODES:
                r,t=run_one(case,0,mode,"R17 smoke")
                need(not r["error"],"smoke mismatch "+str(r["error"]))
                if t.get("early",{}).get("r16_event"):hits+=1
            if hits>=2:break
        need(hits>=2,"no complete R17 1024-conflict decisions in smoke")
    print("R17_C_PYTHON_NATIVE_SMOKE_PASS",hits,flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--category",choices=SHARDS)
    ap.add_argument("--smoke",action="store_true")
    a=ap.parse_args()
    if a.smoke:smoke()
    elif a.category:run(a.category)
    else:ap.error("select --category or --smoke")

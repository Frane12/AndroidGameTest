#!/usr/bin/env python3
"""Frozen-source DELTA4X utility audit. No solver promotion, no original changes.

Ablation removes ONLY observational per-trail/backtrack alias tracking.
Both active arms still emit original-parent RUP clauses and let CDCL use them.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"))
from drnas_delta4x import bench as B
from drnas_delta4x.verify import validate_events,events
from drnas_x55_cpu_real36 import parse_cnf

BASE_SHA="bbc4943a123a8752625e8fa04a9359f1aca7f4158dd60a69b70f522c434e0ef6"
COHORT_SHA="d714d58cce595b6f5a5b67703a773d0adc8530fe83b12f1b736ffe0b9ce79597"
IDS=(8,19,28,38)
ARMS=("X_ACTIVE","X_OBSERVER_OFF","X_SHADOW","D4_FIXED")
CAP=3.0
REPS=3

def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def log(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)
def one(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def build_observer_off():
    """Rebuild original once; require bit-for-bit pinned SHA, then patch only TWO observer hooks."""
    assert digest(ROOT/"build/drnas-delta4x")==BASE_SHA,"FROZEN_DELTA4X_DRIFT"
    assert B.sources()[1]==COHORT_SHA
    frozen={str(p):digest(ROOT/p) for p in ("build/drnas-delta4x","build/drnas-deltacoop4","build/drat-trim",
                                           "cross/x59/build/kissat","cross/x59/build/cadical")}
    subprocess.run([sys.executable,"research/drnas_delta4x/build.py"],cwd=ROOT,check=True)
    assert digest(ROOT/"build/drnas-delta4x")==BASE_SHA,"REBUILT_ORIGINAL_SHA_CHANGED"
    src=(ROOT/"build/drnas_delta4x.cpp").read_text()
    src=one(src,"            coop_.trailChange(lit,values_);",
            "            /* observer ablation: no per-assignment alias scan */")
    src=one(src,"        if(!probing_ && !x46_clone_)coop_.refresh(values_);",
            "        /* observer ablation: no per-backtrack alias scan */")
    assert src.count("delta4x_origin")>=3
    p=ROOT/"build/drnas_delta4x_observer_off.cpp";p.write_text(src)
    flags=["-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra","-Wpedantic","-Werror",
           "-DCOOP5_DYNAMIC_DEFAULT=0","-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1"]
    out=ROOT/"build/drnas-delta4x-observer-off"
    subprocess.run(["g++",*flags,str(p),"-o",str(out)],cwd=ROOT,check=True)
    assert all(digest(ROOT/k)==v for k,v in frozen.items()),"REFERENCE_MODIFIED"
    report={"base_sha256":BASE_SHA,"variant_sha256":digest(out),"variant_source_sha256":digest(p),
            "source_manifest_sha256":COHORT_SHA,"observer_hooks_removed":2,"baseline_unchanged":True,
            "equivalence_alias_tracker_only":True,"clauses_and_reason_checks_preserved":True,
            "no_main_changes":True}
    (ROOT/"delta4x_utility_build.json").write_text(json.dumps(report,indent=2)+"\n")
    log("DELTA4X_UTILITY_BUILD",report)

def preflight():
    from drnas_delta4x.verify import fixtures,oracle,text as dimacs
    from drnas_x55_cpu_real36 import check_sat
    cases={name:(n,cs) for name,n,cs in fixtures()}
    folder=ROOT/"delta4x_utility_safety";folder.mkdir(exist_ok=True)
    rows=[]
    for name in ("core","unsat","shifted_5005"):
        n,cs=cases[name]
        src=folder/(name+".cnf");src.write_text(dimacs(n,cs))
        for mode,exe in (("active","build/drnas-delta4x"),
                         ("observer_off","build/drnas-delta4x-observer-off")):
            proof=folder/(name+"-"+mode+".drat")
            expected=10 if oracle(cs) else 20
            args=[str(ROOT/exe),str(src),"--mode","core","--time","1.8","--stats",
                  "--x5-no-minimize","--coop4","gate","--coop4-eager","--coop5","off",
                  "--delta2","d4x","--proof",str(proof)]
            p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=12)
            assert p.returncode==expected,("RESULT_MISMATCH",name,mode,p.returncode,p.stderr[-1200:])
            if expected==10: assert check_sat(p.stdout,cs,n),(name,mode)
            else:
                q=subprocess.run([str(ROOT/"build/drat-trim"),str(src),str(proof)],
                     capture_output=True,text=True,timeout=20)
                assert "s VERIFIED" in q.stdout,(name,mode,q.returncode,q.stdout[-400:])
            st,novel,causal=validate_events(p.stderr,cs)
            rows.append({"case":name,"arm":mode,"installed":st["installed"],
                         "actual_enqueues":st["actual_enqueues"],"novel":novel,
                         "guard_activations":st["guard_activations"]})
    for name in ("core","unsat","shifted_5005"):
        z=[r for r in rows if r["case"]==name]
        assert z[0]["installed"]==z[1]["installed"] and z[0]["actual_enqueues"]==z[1]["actual_enqueues"],("TRAJECTORY_DRIFT_ON_SMALL",z)
    assert sum(r["actual_enqueues"] for r in rows if r["arm"]=="observer_off")>0
    (folder/"report.json").write_text(json.dumps(rows,indent=2)+"\n")
    log("DELTA4X_UTILITY_PREFLIGHT_PASS",{"cases":3,"runs":6,"same_installed_and_enqueues":True,"original_models_and_unsat_proofs":True,
                                          "records":rows})

def run_one(index):
    assert index in IDS
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    src,d=B.sources();assert d==COHORT_SHA
    s=next(x for x in src if x["id"]==index)
    assert len([x for x in src if x["id"]==index])==1
    assert digest(ROOT/s["path"])==s["sha256"],"SOURCE_DRIFT"
    assert digest(ROOT/"build/drnas-delta4x")==BASE_SHA,"BASE_BINARY_DRIFT"
    expected=json.loads((ROOT/"delta4x_utility_build.json").read_text())["variant_sha256"]
    assert digest(ROOT/"build/drnas-delta4x-observer-off")==expected,"VARIANT_DRIFT"
    B.BINS.update({"X_ACTIVE":"build/drnas-delta4x","X_OBSERVER_OFF":"build/drnas-delta4x-observer-off"})
    B.MODES.update({"X_ACTIVE":"d4x","X_OBSERVER_OFF":"d4x"})
    parent=ROOT/"delta4x_utility"/str(index)
    parent.mkdir(parents=True,exist_ok=False)
    rows=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(int(s["sha256"][:16],16)+987*rep).shuffle(order)
        for arm in order:
            x=B.sample(s,arm,rep,parent/"raw",cap=CAP)
            # Original SAT model/UNSAT DRAT certification done in B.sample.
            # Always verify every new clause's ORIGINAL parents and its causal events.
            if arm in ("X_ACTIVE","X_OBSERVER_OFF") and x["returncode"] in (0,10,20):
                stderr=(parent/"raw"/f"{index}-{rep}-{arm}.stderr").read_text()
                n,cs=parse_cnf((ROOT/s["path"]).read_bytes())
                st,novel,causal=validate_events(stderr,cs)
                x["x_novel_original_clauses"]=novel
                x["x_causal_logged"]=causal
                assert st["installed"]==x["x_installed"]
            x["diagnostic_cap_s"]=CAP
            rows.append(x)
    assert len(rows)==len(ARMS)*REPS
    with (parent/"rows.jsonl").open("w") as f:
        for x in rows:f.write(json.dumps(x,sort_keys=True)+"\n")
    summary={}
    for arm in ARMS:
        t=[x for x in rows if x["arm"]==arm]
        st=[x["stats"].get("X41_STATS",{}) for x in t]
        summary[arm]={"reps":len(t),"accepted":sum(x["verified"] for x in t),
                     "installed":sum(x["x_installed"] for x in t),
                     "actual_enqueues":sum(x["x_actual_enqueues"] for x in t),
                     "conflicts":sum(x.get("conflicts",0) for x in st),
                     "decisions":sum(x.get("decisions",0) for x in st),
                     "propagations":sum(x.get("propagations",0) for x in st),
                     "cpu_s":round(sum(x["cpu_s"] or 0 for x in t),4),
                     "mean_maxrss_kib":round(sum(x["maxrss_kib"] or 0 for x in t)/len(t)),
                     "raw_stats": [x["stats"].get("DELTA4X_STATS",{}) for x in t]}
    log("DELTA4X_UTILITY_CASE_PASS",{"id":index,"family":s["family"],"source_sha256":s["sha256"],
            "nvars":summary["X_ACTIVE"]["raw_stats"][0].get("declared_variables"),
            "summaries":summary,"paired_test_not_speed_claim":True})
    assert all(a["status"] in ("UNKNOWN","SAT_VERIFIED","UNSAT_CERTIFIED","UNSAT_CHECK_TIMEOUT","TIMEOUT") for a in rows)
    assert all(a["verified"] or a["PAR2_verified_s"]==2*CAP for a in rows)
    log("DELTA4X_UTILITY_VALIDATED",{"id":index,"attempts":len(rows),"all_original_models_or_proofs_checked":True})

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage",choices=("build","preflight","case"));p.add_argument("--id",type=int,default=38)
    q=p.parse_args()
    if q.stage=="build":build_observer_off()
    elif q.stage=="preflight":preflight()
    else:run_one(q.id)

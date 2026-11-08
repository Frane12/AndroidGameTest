#!/usr/bin/env python3
"""MRE11-EASY12: paired real SAT/UNSAT replay on the reference-easy official
SAT2021-2025 originals from the earlier MRE7E pilot-16 cohort.
Development/replay, NOT a prospective or globally unseen holdout.
Predeclare 12 by distance of ORIGINAL CMS reference screen runtime to 0.6s;
never select by any MRE10 or MRE11 performance or reduction observation.
Compare identical locked MRE11 C++ executable to its native, clean, rename,
and joint arms using four paired source-hash seeds and 12s wall cap.
Original SAT witness replayed; UNSAT consensus is prior CaDiCaL crosscheck
WITHOUT independent LRAT. Keep source/seed accounting and 12s PAR2 totals.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, pathlib, random, shutil, tempfile
import mre11_holdout as original
import mre8_abcx_ablation as old

PROTO="DRNAS-MRE11-EASY12-2021-2025-DEVREPLAY-5ARMS-4SEEDS-12S-v1"
ROOT=pathlib.Path("mre11_easy")
PREVIOUS=pathlib.Path("mre7_easy")
CAP=12.0
REPS=4
SHARDS=4
TARGET=12
MODES=("cpp_native","cpp_clean","cpp_rename","cpp_joint","cpp_mre11_sel")
SALT="MRE11-EASY12-SCREEN-ONLY-DEVELOPMENT-NO-DRNAS-GATE-20261108"

def need(ok,msg): original.need(ok,msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def save(p,obj): original.save(p,obj)
def seed(c,rep):
    need(rep in range(REPS),"invalid repetition")
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)

def source_cohort():
    old_cases=old.frozen_cases()
    need(len(old_cases)==16,"16 historical original sources missing")
    selected=[c for c in old_cases if c["reference_screen_status"] in ("SAT","UNSAT")
        and 0.08<=float(c["reference_screen_s"])<=5.0]
    need(len(selected)>=TARGET,"fewer than 12 previously screened reference-easy cases")
    selected.sort(key=lambda c: (
        abs(math.log(float(c["reference_screen_s"])/0.6)),
        sha((SALT+"|"+c["sha256"]).encode())))
    chosen=selected[:TARGET]
    need(len({c["gbd"] for c in chosen})==TARGET and
         len({c["sha256"] for c in chosen})==TARGET,"duplicate GBD or SHA")
    for c in chosen:
        p=PREVIOUS/c["filename"]
        need(p.exists() and sha(p.read_bytes())==c["sha256"],"MRE7E source SHA")
        need(c["year"] in ("2021","2022","2023","2024","2025"),
             "MRE7E year changed")
        if c["reference_screen_status"]=="SAT":
            need(c["witness_checked"],"reference screen SAT witness absent")
        else:
            need(c["unsat_cross_solver"],"reference screen UNSAT concordance absent")
    return chosen

def freeze():
    ROOT.mkdir(exist_ok=True)
    chosen=source_cohort()
    frozen=[]
    for c in chosen:
        src=PREVIOUS/c["filename"]
        dst=ROOT/c["filename"]
        shutil.copyfile(src,dst)
        frozen.append({
           "gbd":c["gbd"],"sha256":c["sha256"],"filename":c["filename"],
           "bytes":dst.stat().st_size,"year":c["year"],
           "variables":c["vars"],"clauses":c["clauses"],
           "reference_screen_s":c["reference_screen_s"],
           "reference_screen_status":c["reference_screen_status"],
           "SAT_original_witness_reference_checked":bool(c["witness_checked"]),
           "UNSAT_CaDiCaL_reference_crosschecked_no_LRAT":bool(c["unsat_cross_solver"])
        })
    manifest={"protocol":PROTO,"cases":frozen,"source_pool":"MRE7E existing 16 exact SHA originals",
        "source_selection":"12 closest to original CMS screen 0.6s (no MRE10/MRE11 gate or runtime)",
        "source_reuse_development_not_blind":True,
        "2026_claim":False,"prior_outcomes_on_originals_known":True,
        "original_cms_screen_band_s":[0.08,5.0],"cap_s":CAP,
        "repetitions":REPS,"modes":list(MODES),"expected_trials":TARGET*REPS*len(MODES),
        "original_SAT_witness_checked":True,
        "original_UNSAT_CaDiCaL_crosscheck_without_independent_LRAT":True,
        "no_auto_promotion":True}
    save(ROOT/"manifest.json",manifest)
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in frozen))
    print("MRE11_EASY12_FROZEN",json.dumps({
        "protocol":PROTO,"num_originals":len(frozen),
        "status":dict(collections.Counter(c["reference_screen_status"] for c in frozen)),
        "screen_s":[c["reference_screen_s"] for c in frozen],
        "development_not_blind":True},sort_keys=True),flush=True)

def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["expected_trials"]==240,"wrong MRE11-EASY12 manifest")
    cc=m["cases"]
    need(len(cc)==TARGET and len({c["gbd"] for c in cc})==TARGET,"cohort mismatch")
    for c in cc:
        p=ROOT/c["filename"]
        need(p.exists(),"CNF absent")
        need(sha(p.read_bytes())==c["sha256"] and
             p.stat().st_size==c["bytes"],"original CNF SHA drift")
        need(c["reference_screen_status"] in ("SAT","UNSAT"),"unverified reference")
    return cc

def policy_snapshot(binary):
    cc=cases()
    with tempfile.TemporaryDirectory(prefix="mre11-easy-gates-") as td:
        tmp=pathlib.Path(td)/"rewritten.cnf"
        rows=[]
        for c in cc:
            src=ROOT/c["filename"]
            row={"gbd":c["gbd"],"sha256":c["sha256"],"year":c["year"],
                 "source_screen_s":c["reference_screen_s"],"modes":{}}
            for mode in MODES:
                g=original.subprocess_gate(src,mode,tmp,binary)
                row["modes"][mode]=g
            rows.append(row)
            print("MRE11_EASY12_GATE",json.dumps(row,sort_keys=True),flush=True)
    save(ROOT/"gate_diagnostics.json",rows)
    print("MRE11_EASY12_GATE_PARITY_PASS",len(rows),flush=True)

def trial(c,rep,mode,binary):
    import subprocess, time
    need(0<=rep<REPS and mode in MODES,"invalid trial")
    src=ROOT/c["filename"]
    need(sha(src.read_bytes())==c["sha256"],"CNF SHA mutation")
    begin=time.perf_counter()
    cmd=[str(pathlib.Path(binary).resolve()),str(src.resolve()),mode,str(seed(c,rep))]
    p=None
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,
                         timeout=CAP,check=False,errors="replace")
    except subprocess.TimeoutExpired:pass
    wall=time.perf_counter()-begin
    verdict="TIMEOUT";gate=None;native=None;verified=False
    if p is not None:
        need(p.returncode==0,mode+" native process crashed: "+p.stderr[-500:])
        gate=original.parse_gate(p.stdout)
        verdict,model,native=original.native_ref.parsed_native(p.stdout)
        need(verdict in ("SAT","UNSAT","UNKNOWN","BUDGET"),"bad terminal")
        if verdict=="SAT":
            original.native_ref.verify_model(src,model)
            verified=True
        if verdict in ("SAT","UNSAT"):
            need(verdict==c["reference_screen_status"],
                 "disagrees with previously screened original")
    if verdict in ("UNKNOWN","BUDGET") or wall>CAP:
        verdict="TIMEOUT";verified=False
    need(verdict!="SAT" or verified,"SAT witness not independently replayed")
    return {
        "protocol":PROTO,"mode":mode,"rep":rep,"seed":seed(c,rep),
        "gbd":c["gbd"],"year":c["year"],"original_sha256":c["sha256"],
        "reference_screen_status":c["reference_screen_status"],
        "reference_screen_s":c["reference_screen_s"],
        "verdict":verdict,"SAT_original_witness_verified":verified,
        "UNSAT_prior_CaDiCaL_crosschecked_no_LRAT":verdict=="UNSAT",
        "wall_s":round(wall,6),"par2_s":round(wall if verdict in ("SAT","UNSAT") else CAP*2,6),
        "native_stats":native,"gate":gate}

def shard(index,binary):
    need(index in range(SHARDS),"invalid shard")
    cc=cases()
    subset=[c for i,c in enumerate(cc) if i%SHARDS==index]
    need(len(subset)==3,"wrong frozen cohort distribution")
    rows=[]
    for c in subset:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(sha((PROTO+c["sha256"]+str(rep)).encode())).shuffle(order)
            for mode in order:
                r=trial(c,rep,mode,binary)
                rows.append(r)
                save(ROOT/("shard-%d.json"%index),rows)
                print("MRE11_EASY12_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==60,"incomplete easy shard")
    print("MRE11_EASY12_SHARD_PASS",index,60,flush=True)

def audit():
    cc=cases()
    allrows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.exists(),"missing easy shard artifact")
        allrows+=json.loads(p.read_text())
    need(len(allrows)==240,"incomplete easy PAR2")
    co={c["sha256"]:c for c in cc}
    observed={}
    for r in allrows:
        c=co.get(r["original_sha256"])
        need(c is not None and c["gbd"]==r["gbd"],"alien source SHA")
        need(r["protocol"]==PROTO and r["mode"] in MODES and
             r["rep"] in range(REPS) and r["seed"]==seed(c,r["rep"]),"protocol/seed mismatch")
        if r["verdict"]=="SAT":
            need(r["SAT_original_witness_verified"] and c["reference_screen_status"]=="SAT",
                 "SAT witness or reference mismatch")
        if r["verdict"]=="UNSAT":
            need(r["UNSAT_prior_CaDiCaL_crosschecked_no_LRAT"] and
                 c["reference_screen_status"]=="UNSAT",
                 "UNSAT original screen contradiction")
        need(r["verdict"] in ("SAT","UNSAT","TIMEOUT"),"unsupported terminal status")
        key=(c["sha256"],r["rep"],r["mode"])
        need(key not in observed,"duplicate paired trial")
        observed[key]=r
    need(len(observed)==240,"missing one source-seed-mode")
    scores={}
    for mode in MODES:
        a=[r for r in allrows if r["mode"]==mode]
        scores[mode]={
            "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in a),
            "SAT":sum(r["verdict"]=="SAT" for r in a),
            "UNSAT_no_independent_LRAT":sum(r["verdict"]=="UNSAT" for r in a),
            "timeouts":sum(r["verdict"]=="TIMEOUT" for r in a),
            "PAR2_total_s":round(sum(r["par2_s"] for r in a),6),
            "gate_applied_visible":sum(bool((r["gate"] or {}).get("applied")) for r in a)
        }
    baseline=scores["cpp_native"]["PAR2_total_s"]
    for x in scores.values():
        x["PAR2_speedup_vs_native_x"]=round(baseline/x["PAR2_total_s"],6)
    per_case=[]
    for c in cc:
        sl=[r for r in allrows if r["original_sha256"]==c["sha256"]]
        per_case.append({
            "gbd":c["gbd"],"year":c["year"],
            "original_SHA":c["sha256"],
            "original_cms_reference_screen_s":c["reference_screen_s"],
            "reference_status":c["reference_screen_status"],
            "modes":{mode:{"PAR2_total_s":round(sum(r["par2_s"] for r in sl if r["mode"]==mode),6),
                   "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in sl if r["mode"]==mode)}
                   for mode in MODES}
        })
    result={"protocol":PROTO,"cohort":"MRE7E pre-screened 2021-2025 development reused",
        "development_not_blind":True,"SAT2026":False,"sources":TARGET,
        "repetitions":REPS,"modes":list(MODES),"real_end_to_end_sat_unsat":True,
        "cap_s":CAP,"total_trials":240,"same_pinned_cpp_binary_as_MRE11":True,
        "SAT_original_witness_verified":True,
        "UNSAT_CaDiCaL_reference_screen_no_independent_LRAT":True,
        "no_auto_promotion":True,"scores":scores,"per_source":per_case}
    save(ROOT/"report.json",result)
    print("MRE11_EASY12_FINAL",json.dumps({k:v for k,v in result.items()
          if k!="per_source"},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","policy","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre11/bin/native")
    p.add_argument("--standalone",default="mre11/bin/standalone")
    z=p.parse_args()
    if z.action=="freeze":freeze()
    elif z.action=="verify":
        print("MRE11_EASY12_SOURCE_SHA_PASS",len(cases()),flush=True)
    elif z.action=="policy":policy_snapshot(z.standalone)
    elif z.action=="shard":shard(z.shard,z.native)
    else:audit()

#!/usr/bin/env python3
"""R192: fair source-locked Gaussian-first (R28) -> CryptoMiniSat 5.11.15 fallback.

All five arms see identical original CNFs. Two paired repetitions of 38
preexposed cases (25 external + 13 generated controls). The native R28 code
handles certified pure XOR SAT or source GF2 contradiction UNSAT, else execv()
its exact fallback command via the pinned shell wrapper. Includes process and
preprocessing wall time; 12 s cap. SAT models verified against ORIGINAL DIMACS.
This does not certify arbitrary CDCL UNSAT via LRAT. Not a blind competition.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, random, re, statistics
import subprocess, time

import r190_cms_mixed_benchmark as prior
import r188_feedback_benchmark as auditlib

ROOT=pathlib.Path("r192")
SOURCE=pathlib.Path("r189/frozen")
PROTO="DRNAS-R192-GAUSSIAN-FIRST-CMS-FALLBACK-5ARM-v1"
SOURCE_SHA=prior.SOURCE_MANIFEST_SHA
REPS=2
SHARDS=12
CAP=12.0
MODES=("r28_cms_gauss_first","r28_cms_forced_first","cms_default",
       "cms_forced_gauss","r28_kissat")

def need(ok,msg):
    if not ok:raise RuntimeError("R192_FAIL_CLOSED "+msg)

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

def verify():
    need(sha(SOURCE/"manifest.json")==SOURCE_SHA,"source manifest sha mismatch")
    m=json.loads((SOURCE/"manifest.json").read_text())
    cases=m["cases"]
    need(len(cases)==38 and sum(bool(x["real"]) for x in cases)==25,
         "source count/cohort drift")
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],
             "source SHA mismatch: "+c["id"])
    pins=json.loads((ROOT/"pins.json").read_text())
    for f,s in pins.items():
        need(sha(f)==s,"pinned file changed: "+f)
    for filename in ("r190_cms_mixed/r28","built/bin/kissat_4_0_4",
                     "r192/cms_single.sh","r192/cms_gauss_forced.sh",
                     "/usr/bin/cryptominisat5"):
        need(pathlib.Path(filename).is_file(),"missing binary "+filename)
    return cases

def command(mode,src):
    filename=str(src.resolve())
    if mode=="cms_default":
        return ["/usr/bin/cryptominisat5","--threads=1",filename]
    if mode=="cms_forced_gauss":
        return ["/usr/bin/cryptominisat5","--threads=1",
                "--autodisablegauss=0","--maxnummatrices=5",filename]
    if mode=="r28_cms_gauss_first":
        return [str(pathlib.Path("r190_cms_mixed/r28").resolve()),
                filename,str(pathlib.Path("r192/cms_single.sh").resolve())]
    if mode=="r28_cms_forced_first":
        return [str(pathlib.Path("r190_cms_mixed/r28").resolve()),
                filename,str(pathlib.Path("r192/cms_gauss_forced.sh").resolve())]
    if mode=="r28_kissat":
        return [str(pathlib.Path("r190_cms_mixed/r28").resolve()),
                filename,str(pathlib.Path("built/bin/kissat_4_0_4").resolve())]
    raise ValueError(mode)

def inspect(out,rc):
    need(rc in (0,10,20), "solver returned unexpected exit="+str(rc)+" tail="+out[-250:])
    if re.search(r"^s\s+UNSATISFIABLE\b",out,re.M):status="UNSAT"
    elif re.search(r"^s\s+SATISFIABLE\b",out,re.M):status="SAT"
    else:need(False,"solver missing result line "+out[-250:])
    model={}
    if status=="SAT":
        for line in out.splitlines():
            if line.startswith("v "):
                for v in map(int,line.split()[1:]):
                    if v:
                        need(abs(v) not in model or model[abs(v)]==(v>0),
                             "SAT model conflicting assignments")
                        model[abs(v)]=(v>0)
        need(model,"SAT missing witness")
    route=re.search(r"^c R28_ROUTE\s+([^\n]+)",out,re.M)
    return status,model,route.group(1) if route else None

def trial(c,mode,rep,idx):
    source=SOURCE/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"original CNF changed during run")
    t0=time.perf_counter()
    try:
        p=subprocess.run(command(mode,source),capture_output=True,
                         text=True,timeout=CAP,check=False)
        elapsed=min(CAP,time.perf_counter()-t0)
        raw=p.stdout+"\n"+p.stderr
        status,model,route=inspect(raw,p.returncode)
        need(elapsed<CAP,"returned after cap")
        if status=="SAT":
            _,clauses=auditlib.gf.dimacs(source)
            auditlib.gf.sat_check(clauses,model)
            proof="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
        elif route and route.startswith("certified_xor_contradiction"):
            proof="R28_SOURCE_GF2_CONTRADICTION"
        else:
            proof="UNSAT_NO_INDEPENDENT_LRAT"
        output=ROOT/"logs"/f"shard-{idx}"/f"{c['id']}-{mode}-{rep}.log"
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(raw[-60000:])
    except subprocess.TimeoutExpired:
        elapsed=CAP
        status="TIMEOUT";route=None;proof="CAP_TIMEOUT"
    if c["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(c["expected"]==status,"known source truth mismatch")
    return dict(id=c["id"],sha256=c["sha256"],real=c["real"],family=c["family"],
      mode=mode,rep=rep,status=status,elapsed_s=round(elapsed,6),
      par2_s=round(CAP*2 if status=="TIMEOUT" else elapsed,6),
      r28_route=route,proof=proof)

def shard(idx):
    cases=verify()
    need(0<=idx<SHARDS,"bad shard")
    rows=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=trial(c,mode,rep,idx)
                rows.append(r)
                write(ROOT/f"shard-{idx}.json",rows)
                print("R192_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(cases[idx::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R192_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=verify()
    rows=[];seen=set();ids={x["sha256"]:x for x in cases}
    for i in range(SHARDS):
        f=ROOT/f"shard-{i}.json"
        need(f.is_file(),"missing shard "+str(i))
        part=json.loads(f.read_text())
        need(len(part)==len(cases[i::SHARDS])*REPS*len(MODES),
             "partial shard "+str(i))
        for x in part:
            need(x["sha256"] in ids and ids[x["sha256"]]["id"]==x["id"],
                 "unknown or mismatched source")
            k=(x["sha256"],x["mode"],x["rep"])
            need(k not in seen,"duplicate pair")
            seen.add(k)
            need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"bad result status")
            need(abs(x["par2_s"]-(CAP*2 if x["status"]=="TIMEOUT" else x["elapsed_s"]))<0.00001,
                 "PAR2 arithmetic mismatch")
            rows.append(x)
    need(len(rows)==38*REPS*len(MODES)==380,"wrong total count")
    for c in cases:
        for rep in range(REPS):
            rr=[x for x in rows if x["sha256"]==c["sha256"] and x["rep"]==rep]
            need({x["mode"] for x in rr}==set(MODES),"unpaired arms")
            truth={x["status"] for x in rr if x["status"]!="TIMEOUT"}
            need(len(truth)<=1,"SAT and UNSAT disagreement across same CNF")
    groups={"all":cases,
            "external_original_25":[x for x in cases if x["real"]],
            "synthetic_controls_13":[x for x in cases if not x["real"]]}
    for fam in sorted({x["family"] for x in cases if x["real"]}):
        groups["external:"+fam]=[x for x in cases if x["real"] and x["family"]==fam]
    outcome={}
    for cohort,selected in groups.items():
        allowed={x["sha256"] for x in selected}
        modes={}
        for mode in MODES:
            rr=[x for x in rows if x["sha256"] in allowed and x["mode"]==mode]
            solved=[x for x in rr if x["status"]!="TIMEOUT"]
            routes=collections.Counter((x.get("r28_route") or "none").split(" ")[0] for x in rr)
            modes[mode]={
                "attempts":len(rr),"solved":len(solved),
                "SAT":sum(x["status"]=="SAT" for x in rr),
                "UNSAT":sum(x["status"]=="UNSAT" for x in rr),
                "timeouts":sum(x["status"]=="TIMEOUT" for x in rr),
                "PAR2_s":round(sum(x["par2_s"] for x in rr),6),
                "median_s_solved":round(statistics.median(x["elapsed_s"] for x in solved),6) if solved else None,
                "route_first_tokens":dict(routes),
                "source_Gf2_contradictions":sum(x["proof"]=="R28_SOURCE_GF2_CONTRADICTION" for x in rr),
            }
        outcome[cohort]={"cases":len(selected),"modes":modes}
    report={
        "protocol":PROTO,"status":"R192_AUDIT_PASS",
        "original_manifest_sha256":SOURCE_SHA,
        "sources_reused_not_blind":True,
        "cases":38,"repeats":REPS,"attempts":len(rows),"cap_s":CAP,
        "SAT_witness_original_verified":True,"independent_CMS_UNSAT_LRAT":False,
        "reliability":"R28 + exact CMS wrapper, same original CNFs, no changed constraints",
        "summary":outcome
    }
    write(ROOT/"report.json",report)
    write(ROOT/"all_trials.json",rows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R192 Gaussian-first R28 -> CryptoMiniSat vs CryptoMiniSat alone\n\n")
        f.write("38 previously exposed formulas, 25 external originals + 13 generated controls. "
                "Not blind. Same source SHA, 2 paired repeats, 12s wall cap including R28 detection, "
                "SAT models checked against original CNF. UNSAT without source XOR proof "
                "does not have independent LRAT.\n\n")
        f.write("| Cohort | Mode | Solved | PAR2 s | SAT | UNSAT | Timeouts |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|\n")
        for cohort in ("external_original_25","synthetic_controls_13","all"):
            for mode,s in outcome[cohort]["modes"].items():
                f.write(f"| {cohort} | {mode} | {s['solved']}/{s['attempts']} "
                        f"| {s['PAR2_s']} | {s['SAT']} | {s['UNSAT']} | {s['timeouts']} |\n")
    print("R192_FINAL",json.dumps(outcome,sort_keys=True),flush=True)

def smoke():
    cases=verify()
    p=ROOT/"smoke.cnf"
    p.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
    for mode in MODES:
        x=command(mode,p)
        out=subprocess.run(x,capture_output=True,text=True,timeout=5)
        status,model,route=inspect(out.stdout+"\n"+out.stderr,out.returncode)
        need(status=="SAT" and model.get(1) and model.get(2),
             "smoke failure "+mode)
    need(len(cases)==38,"source count drift")
    print("R192_SMOKE_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["smoke","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    else:audit()

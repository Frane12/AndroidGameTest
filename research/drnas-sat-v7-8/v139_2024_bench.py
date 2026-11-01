#!/usr/bin/env python3
"""V13.8 external SAT Competition 2026 pilot: actual downloaded competition CNFs.

Reuses 18 SHA-pinned genuine 2026 Main Track instances from the already
observed 2026 mini benchmark. These are NOT a blind sample. Strict checks
for SHA-256, official labels, identical CPU affinity and binary hashes.
Measure DRNAS_Legacy, upstream Kissat404, and real-input-safe V13.7 as
separate executable processes, including Python startup and fallback costs.
This is NOT an official competition submission or ranking.
"""
import argparse,hashlib,json,os,random,resource,statistics,subprocess,sys,time
from collections import Counter,defaultdict
from pathlib import Path
import official_shortlong_select as source
import official_2026_mini_sim as mini
import v137_fastpath as v137

PROTOCOL="DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101"
N=12;SHARDS=6;REPS=2;CAP=20.0;MEMORY_GIB=3
MODES=("DRNAS_Legacy","Kissat404","V137_RealSafe")
mini.CAP=CAP
mini.MEMORY_GIB=MEMORY_GIB
source.RAW_CAP=96*1024**2
source.CNF_CAP=96*1024**2
source.VARIABLE_CAP=1000000
source.CLAUSE_CAP=4000000

def check(v,msg):
    if not v:raise RuntimeError(msg)
def load(path):return json.loads(Path(path).read_text())
def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mem():
    resource.setrlimit(resource.RLIMIT_AS,(MEMORY_GIB*1024**3,MEMORY_GIB*1024**3))

def entry(a):
    """Child-process V13.7 actual wall-time cost with conservative fallback.

    Exact recognizer handles only small enough, strict 3-XOR/PHP DIMACS.
    Other real-world CNFs, including commented/oversized files, fall back to
    V13.7's original DRNAS default. No label or family used for selection.
    """
    start=time.monotonic()
    raw=Path(a.cnf).read_bytes()
    detection_start=time.monotonic()
    try:
        decision=v137.decide(raw)
        reason=decision["path"]
    except (ValueError,AssertionError,UnicodeDecodeError) as exc:
        decision={"status":"FALLBACK","solver":"DRNAS_Legacy"}
        reason="unsupported_real_dimacs"
    detection=time.monotonic()-detection_start
    if decision["status"]!="FALLBACK":
        label=decision["status"]
        n,clauses=v137.read_dimacs(raw)
        check(v137.verify(n,clauses,decision),"Certificate rejected")
        status=label
    else:
        mode=decision["solver"]
        if mode=="Kissat404":
            cmd=[str(Path(a.kissat).resolve()),str(Path(a.cnf).resolve())]
        else:
            cmd=[str(Path(a.drnas).resolve()),"v100_late_legacy_force",
                 str(Path(a.cnf).resolve()),str(a.seed)]
        remaining=CAP-(time.monotonic()-start)
        if remaining<=0.01:
            status="TIMEOUT"
        else:
            try:
                out=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                   timeout=remaining,preexec_fn=mem,check=False)
                if mode=="Kissat404":
                    check(out.returncode in (10,20),"Kissat exit "+str(out.returncode))
                    status="SAT" if out.returncode==10 else "UNSAT"
                    expected="s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE"
                    check(expected in out.stdout,"Kissat status missing")
                else:
                    check(out.returncode==0,"DRNAS exit "+str(out.returncode)+":"+out.stderr[-250:])
                    lines=[s for s in out.stdout.splitlines() if s.startswith("DRNAS_CAUSAL\t")]
                    check(len(lines)==1,"DRNAS telemetry missing")
                    pairs=dict(part.split("=",1) for part in lines[0].split("\t")[1:])
                    status=pairs["answer"]
                    check(status in ("SAT","UNSAT"),"Bad solver answer")
            except subprocess.TimeoutExpired:
                status="TIMEOUT"
    elapsed=time.monotonic()-start
    if elapsed>CAP:status="TIMEOUT"
    result={"status":status,"selection":decision.get("solver","exact_math"),
      "reason":reason,"detect_wall_s":round(detection,6),
      "internal_elapsed_s":round(min(CAP,elapsed),6)}
    print("V139_REAL_CHILD\t"+json.dumps(result,sort_keys=True),flush=True)

def selftest():
    # Unsupported DIMACS must not be inferred as a solved formula.
    raw=b"c external metadata\np cnf 2 1\n1 2 0\n"
    try:
        result=v137.decide(raw)
        check(result["status"]=="FALLBACK","Unexpected solve")
    except (ValueError,AssertionError,UnicodeDecodeError):
        pass
    # A small valid XOR instance exercises direct SAT witness verification.
    eq=b"p cnf 3 4\n1 2 3 0\n-1 -2 3 0\n-1 2 -3 0\n1 -2 -3 0\n"
    solved=v137.decide(eq)
    check(solved["status"]=="SAT","Exact GF2 SAT selftest")
    n,cs=v137.read_dimacs(eq)
    check(v137.verify(n,cs,solved),"Bad GF2 model")
    print("V138_REAL_SELFTEST_PASS",flush=True)

def freeze(a):
    selftest()
    p=load(a.prior)
    check(p["protocol"]=="DRNAS-V139-SC2024-NEW-SHA-DISJOINT-20261101-v1"
          and len(p["cases"])==N,"New locked 2026 set identity mismatch")
    check(len({c["sha256"] for c in p["cases"]})==N,"Duplicate CNF SHA")
    check(p["unseen_excluded_shas"]>=132 and
          p["unseen_excluded_ids"]>=132,"Prior-history exclusion missing")
    check(all(c["official_label"] in ("SAT","UNSAT") and
          c["source_url"].startswith("https://benchmark-database.de/file/")
          for c in p["cases"]),"Invalid verified public provenance")
    save(a.out,{"protocol":PROTOCOL,"cases":p["cases"],
         "selector_manifest_sha256":sha(a.prior),
         "official_source_meta_sha256":p["metadata_sha256"],
         "official_source_results_sha256":p["results_zip_sha256"],
         "selection_rule":p["selection_rule"],
         "excluded_history_count_sha":p["unseen_excluded_shas"],
         "n":N,"shards":SHARDS,"reps":REPS,"cap_s":CAP,"modes":MODES,
         "v137_code_sha256":sha(a.fastpath),
         "warnings":p["warnings"]+[
          "New to listed prior cohorts, real 2024 SAT Competition instances; not statistically representative.",
          "V13.7 code and SHA frozen before new solver measurements.",
          "V137_RealSafe complete Python startup + real solver time included.",
          "Fall back to DRNAS Legacy if formula is not an exact recognized structure.",
          "UNSAT fallback checked against published official SAT/UNSAT labels, no fresh proof certificate.",
          "No 2026 official world record, P=NP, or rank claim."
         ]})
    print("V139_FRESH_REAL_BENCHMARK_FREEZE_PASS",N,flush=True)

def v137_trial(cnf,drnas,kissat,seed,official):
    args=[sys.executable,str(Path(__file__).resolve()),"entry",
          "--cnf",str(cnf.resolve()),"--drnas",str(Path(drnas).resolve()),
          "--kissat",str(Path(kissat).resolve()),"--seed",str(seed)]
    start=time.monotonic()
    try:
        proc=subprocess.run(args,capture_output=True,text=True,errors="replace",
           timeout=CAP,preexec_fn=mem,check=False)
        elapsed=time.monotonic()-start
        check(proc.returncode==0,"V13.7 real-entry error: "+proc.stderr[-420:])
        lines=[x for x in proc.stdout.splitlines() if x.startswith("V139_REAL_CHILD\t")]
        check(len(lines)==1,"Missing/duplicate child result")
        d=json.loads(lines[0].split("\t",1)[1])
        check(d["status"] in ("SAT","UNSAT","TIMEOUT"),"Bad V13.7 status")
        check(d["status"]=="TIMEOUT" or d["status"]==official,"Wrong SAT/UNSAT label")
        return {"status":d["status"],"seconds":round(elapsed,6),
           "selection":d["selection"],"reason":d["reason"],
           "detect_wall_s":d["detect_wall_s"],"error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"selection":"timeout",
                "reason":"process_timeout","detect_wall_s":None,"error":""}

def run(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and m["v137_code_sha256"]==sha(a.fastpath),
          "Frozen protocol or V13.7 changed")
    check(0<=a.shard<SHARDS,"Bad shard")
    cases=m["cases"][a.shard::SHARDS]
    check(len(cases)==2,"Wrong shard size")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    save(out/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
       "ids":[x["id"] for x in cases],
       "cpu":cpu,"v137_sha256":sha(a.fastpath),
       "binaries":{mode:sha(getattr(a,mode)) for mode in ("drnas","kissat")}})
    rows=[]
    for c in cases:
        cnf=out/(c["id"]+".cnf")
        actual=source.download_and_features(c["id"],cnf)
        check(actual["sha256"]==c["sha256"] and actual["features"]==c["features"],
              "Source CNF changed or wrong SHA")
        observations=[]
        for rep in range(REPS):
            seed=(1382026+1009*rep+int(c["sha256"][:8],16))%(2**32)
            modes=list(MODES);random.Random(seed^138).shuffle(modes)
            for mode in modes:
                if mode=="V137_RealSafe":
                    data=v137_trial(cnf,a.drnas,a.kissat,seed,c["official_label"])
                else:
                    obs=mini.trial(mode,cnf,seed,a.drnas,a.kissat,c["official_label"])
                    check(obs["status"]!="ERROR","Comparator solver error: "+obs["error"])
                    data={"status":obs["status"],"seconds":obs["seconds"],
                          "selection":mode,"reason":"fixed_baseline","detect_wall_s":0.0,"error":""}
                check(data["status"]=="TIMEOUT" or data["status"]==c["official_label"],
                     "Incorrect SAT answer")
                check(0<=data["seconds"]<=CAP+0.5,"Solver time > cap")
                observations.append({"mode":mode,"repetition":rep,**data})
                print("V139_REAL_TRIAL",a.shard,c["id"][:10],rep,mode,
                    data["status"],data["seconds"],data["reason"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"cohort":c["cohort"],
          "label":c["official_label"],"trials":observations})
        save(out/"rows.json",rows)
        cnf.unlink()
    check(len(rows)==2,"Missing shard rows")
    print("V139_REAL_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and len(m["cases"])==N,"Wrong audit manifest")
    rows=[];bins=set();cpus=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v139-real-shard-{shard}"
        if not (folder/"meta.json").is_file():folder=folder/"results"
        meta=load(folder/"meta.json");part=load(folder/"rows.json")
        expected=m["cases"][shard::SHARDS]
        check(meta["v137_sha256"]==m["v137_code_sha256"] and meta["protocol"]==PROTOCOL and meta["shard"]==shard and
              meta["ids"]==[x["id"] for x in expected],"Wrong shard provenance")
        check(len(part)==2 and [x["id"] for x in part]==meta["ids"],"Missing formulas")
        bins.add(json.dumps(meta["binaries"],sort_keys=True));cpus.add(meta["cpu"])
        rows.extend(part)
    check(len(rows)==N and len(bins)==1 and len({x["sha256"] for x in rows})==N,
          "Incomplete or heterogeneous comparison")
    known={x["id"]:x for x in m["cases"]}
    groups={"all":rows}
    for cohort in sorted({r["cohort"] for r in rows}):
        groups[cohort]=[r for r in rows if r["cohort"]==cohort]
    summaries={}
    for group,part in groups.items():
        times=defaultdict(list);solved=Counter();route=Counter();recognized=Counter()
        by_case=[]
        for r in part:
            c=known[r["id"]]
            check(r["sha256"]==c["sha256"] and r["label"]==c["official_label"],
                  "Case identity drift")
            records={(x["mode"],x["repetition"]):x for x in r["trials"]}
            check(len(records)==REPS*len(MODES),"Missing or duplicate attempts")
            for mode in MODES:
                for rep in range(REPS):
                    x=records[(mode,rep)]
                    check(x["status"] in ("SAT","UNSAT","TIMEOUT") and not x["error"],
                          "Invalid result")
                    check(x["status"]=="TIMEOUT" or x["status"]==r["label"],
                          "Wrong published official label")
                    check(0<=x["seconds"]<=CAP+0.5,"Runtime invalid")
                    solved[mode]+=int(x["status"]!="TIMEOUT")
                    times[mode].append(2*CAP if x["status"]=="TIMEOUT" else x["seconds"])
                    if mode=="V137_RealSafe":
                        route[x["selection"]]+=1;recognized[x["reason"]]+=1
            by_case.append({"id":r["id"],"cohort":r["cohort"],
              "attempts":{mode:[records[(mode,i)] for i in range(REPS)] for mode in MODES}})
        summaries[group]={"formulas":len(part),
            "methods":{mode:{"solved":solved[mode],"attempts":len(part)*REPS,
              "PAR2_s":round(statistics.mean(times[mode]),6)} for mode in MODES},
            "V137_selections":dict(route),"V137_recognition":dict(recognized)}
    report={"protocol":PROTOCOL,"n_formulas":N,"n_attempts":N*REPS*len(MODES),
        "warning":m["warnings"],"cpu_models":sorted(cpus),
        "summaries":summaries,"cases":rows}
    save(a.out,report)
    lines=["# DRNAS V13.9 — locked V13.7 against new external SAT Competition 2024 Main Track CNFs","",
       "**12 new SHA-disjoint external 2024 SAT CNFs; fixed code and selection before new solver runs. NOT representative.**",
       "SHA-verified 12 CNFs, 2 repetitions, 3 methods, 20 second cutoff, 3 GiB; 72 paired attempts.","",
       "| Sample | Method | Solved | PAR-2 s |",
       "|---|---|---:|---:|"]
    for group in ("all",)+tuple(sorted(g for g in summaries if g!="all")):
        q=summaries[group]
        for mode in MODES:
            d=q["methods"][mode]
            lines.append(f"| {group} | {mode} | {d['solved']}/{d['attempts']} | {d['PAR2_s']:.5f} |")
        lines.append(f"V13.7 selected: {q['V137_selections']}; recognition: {q['V137_recognition']}.")
    lines+=["","## Scope limits"]
    lines.extend("- "+s for s in m["warnings"])
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V139_REAL_AUDIT_PASS",json.dumps(summaries["all"],sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest="cmd",required=True)
    subs.add_parser("selftest")
    q=subs.add_parser("freeze")
    for k in ("prior","fastpath","out"):q.add_argument("--"+k,required=True)
    q=subs.add_parser("run")
    for k in ("manifest","fastpath","drnas","kissat","out"):
        q.add_argument("--"+k,required=True)
    q.add_argument("--shard",type=int,required=True)
    q=subs.add_parser("audit")
    for k in ("manifest","combined","out","md"):
        q.add_argument("--"+k,required=True)
    q=subs.add_parser("entry")
    for k in ("cnf","drnas","kissat"):q.add_argument("--"+k,required=True)
    q.add_argument("--seed",required=True,type=int)
    args=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(args),
     "run":lambda:run(args),"audit":lambda:audit(args),
     "entry":lambda:entry(args)}[args.cmd]()
if __name__=="__main__":main()

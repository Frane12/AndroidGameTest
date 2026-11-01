#!/usr/bin/env python3
"""V13.7 four-policy pinned benchmark and SHA-verified offline audit.

Comparison: fixed DRNAS Legacy, upstream Kissat404, unchanged V13.6 router,
and V13.7 exact XOR/PHP solver with full Python startup and certificate
verification measured by a separate process. Strictly no official rank claim.
"""
import argparse,collections,hashlib,json,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
import v137_holdout as holdout
import v137_fastpath as fastpath
import v136_symbolic as v136
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-V137-FASTPATH-NEW-40-20261101"
CAP=24.0;REPS=2;SHARDS=8;CASES=40;MIB=1024**2
MODES=("DRNAS_Legacy","Kissat404","Router136","V137_Exact")
mini.CAP=CAP;mini.MEMORY_GIB=3
def check(condition,message):
    if not condition:raise RuntimeError(message)
def load(file):return json.loads(Path(file).read_text())
def save(file,data):
    p=Path(file);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def digest(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
def selftest():
    fastpath.selftest();holdout.selftest()
    check(CAP==24.0 and CASES==40 and SHARDS==8,"Protocol drift")
    print("V137_EVAL_SELFTEST_PASS",flush=True)
def freeze(a):
    selftest()
    cases=[holdout.fresh(f,i)[0] for i in range(8) for f in holdout.FAMILIES]
    check(len(cases)==40 and len({c["sha256"] for c in cases})==40,"Duplicate holdout")
    save(a.out,{"protocol":PROTOCOL,"cases":cases,"cap_s":CAP,"reps":REPS,
      "shards":SHARDS,"modes":MODES,"routing_source_sha256":digest(a.source),
      "generator_source_sha256":digest(a.generator),
      "limitations":[
        "All 40 are freshly seeded, variable-permuted synthetic CNFs, not an official SAT 2026 holdout.",
        "Five familiar families were studied in V13.4 and V13.6; generalization only to new instances of familiar classes.",
        "GF(2) Gaussian elimination and the pigeonhole principle are established algorithms/theorems, not novel complexity results.",
        "SAT models verified against every clause; GF(2) UNSAT linear-combination certificate verified; PHP exact encoding reverified.",
        "No independent general-purpose UNSAT proof certificate such as DRAT for PHP; mathematical structural proof checked.",
        "End-to-end separate Python process startup included for V13.7; default V13.6 classifier measured in-process.",
        "Only two pinned comparator builds, not all 2026 championship solvers, and no world record claim.",
        "24 s per attempt, 3GiB per process, pinned single CPU, GitHub runner CPU models may differ.",
        "Baseline and routing solver results are checked against independent generator's mathematical labels."]})
    print("V137_FREEZE_PASS",len(cases),flush=True)

def memory():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def exact_trial(file,seed,drnas,kissat,label):
    cmd=[sys.executable,str((Path(__file__).parent/"v137_fastpath.py").resolve()),
         str(file.resolve()),"--seed",str(seed),
         "--drnas",str(Path(drnas).resolve()),"--kissat",str(Path(kissat).resolve())]
    start=time.monotonic()
    try:
        proc=subprocess.run(cmd,text=True,capture_output=True,errors="replace",
                  timeout=CAP,preexec_fn=memory)
        elapsed=time.monotonic()-start
        check(proc.returncode==0,"V137 subprocess error: "+proc.stderr[-600:])
        lines=[r for r in proc.stdout.splitlines() if r.startswith("DRNAS_V137_RESULT\t")]
        check(len(lines)==1,"Missing V137 result")
        details=json.loads(lines[0].split("\t",1)[1])
        check(details["status"] in ("SAT","UNSAT"),"Invalid V137 answer")
        check(details["status"]==label,"Wrong V137 SAT answer")
        if details["path"] in ("affine_exact","pigeonhole_exact"):
            n,clauses=fastpath.read_dimacs(file.read_bytes())
            check(fastpath.verify(n,clauses,details),"Certificate invalid")
        if elapsed>CAP:return {"status":"TIMEOUT","seconds":CAP,"error":""}
        return {"status":details["status"],"seconds":round(elapsed,6),"error":"",
                "selected":details["path"],"verified_certificate":details["path"] in
                    ("affine_exact","pigeonhole_exact")}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"error":"","selected":"timeout",
                "verified_certificate":False}

def legacy_router(file,seed,drnas,kissat,label):
    begin=time.monotonic()
    mode,why=v136.classify(file.read_bytes())
    overhead=time.monotonic()-begin
    check(overhead<CAP,"V13.6 router too slow")
    mini.CAP=CAP-overhead
    try:out=mini.trial(mode,file,seed,drnas,kissat,label)
    finally:mini.CAP=CAP
    check(out["status"]!="ERROR","Legacy router: "+out["error"])
    elapsed=overhead+out["seconds"]
    return {"status":out["status"] if elapsed<=CAP else "TIMEOUT",
            "seconds":round(min(CAP,elapsed),6),"error":"","selected":mode,
            "overhead_s":round(overhead,6)}

def run(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and m["routing_source_sha256"]==digest(a.source)
          and m["generator_source_sha256"]==digest(a.generator),"Frozen source drift")
    check(0<=a.shard<SHARDS,"Bad shard")
    cases=m["cases"][a.shard::SHARDS]
    check(len(cases)==5,"Bad shard size")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
             if x.startswith("model name")),"unknown")
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    save(root/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
         "ids":[x["id"] for x in cases],"cpu":cpu,
         "routing_sha256":digest(a.source),
         "generator_sha256":digest(a.generator),
         "fastpath_sha256":digest(a.fastpath),
         "binaries":{mode:digest(getattr(a,mode)) for mode in ("drnas","kissat")}})
    rows=[]
    for c in cases:
        info,raw=holdout.fresh(c["family"],c["index"])
        check(info==c and hashlib.sha256(raw).hexdigest()==c["sha256"],"Source mismatch")
        cnf=root/(c["sha256"][:20]+".cnf");cnf.write_bytes(raw)
        trials=[]
        for rep in range(REPS):
            seed=(1372026+1009*rep+int(c["sha256"][:8],16))%(2**32)
            order=list(MODES);random.Random(seed^137).shuffle(order)
            for mode in order:
                if mode=="V137_Exact":
                    data=exact_trial(cnf,seed,a.drnas,a.kissat,c["label"])
                elif mode=="Router136":
                    data=legacy_router(cnf,seed,a.drnas,a.kissat,c["label"])
                else:
                    obs=mini.trial(mode,cnf,seed,a.drnas,a.kissat,c["label"])
                    check(obs["status"]!="ERROR","Comparator error: "+obs["error"])
                    data={"status":obs["status"],"seconds":obs["seconds"],
                          "error":"","selected":mode,"verified_certificate":False}
                check(data["status"] in ("SAT","UNSAT","TIMEOUT"),"Bad status")
                check(data["status"]=="TIMEOUT" or data["status"]==c["label"],
                      "Incorrect formula result")
                trials.append({"mode":mode,"repetition":rep,**data})
                print("V137_TRIAL",a.shard,c["id"],rep,mode,data["status"],
                      data["seconds"],data.get("selected","unknown"),flush=True)
        rows.append({"id":c["id"],"family":c["family"],"sha256":c["sha256"],
              "label":c["label"],"trials":trials})
        save(root/"rows.json",rows);cnf.unlink()
    print("V137_SHARD_PASS",a.shard,len(rows),flush=True)

def aggregate(rows):
    groups={"all":rows}
    for f in holdout.FAMILIES:groups[f]=[r for r in rows if r["family"]==f]
    summary={}
    for group,part in groups.items():
        costs=collections.defaultdict(list);solved=collections.Counter()
        path_counts=collections.Counter();matched=0
        for q in part:
            rr={(t["mode"],t["repetition"]):t for t in q["trials"]}
            check(len(rr)==REPS*len(MODES),"Duplicate/missing trial")
            for mode in MODES:
                for rep in range(REPS):
                    t=rr[(mode,rep)]
                    check(t["status"] in ("SAT","UNSAT","TIMEOUT") and not t["error"],
                          "Trial error")
                    check(t["status"]=="TIMEOUT" or t["status"]==q["label"],"SAT mismatch")
                    check(0<=t["seconds"]<=CAP+0.1,"Runtime over cap")
                    solved[mode]+=int(t["status"]!="TIMEOUT")
                    costs[mode].append(2*CAP if t["status"]=="TIMEOUT" else t["seconds"])
                    if mode=="V137_Exact":path_counts[t.get("selected","unknown")]+=1
            if rr[("V137_Exact",0)]["status"]!="TIMEOUT" and rr[("V137_Exact",1)]["status"]!="TIMEOUT":
                matched+=1
        summary[group]={"formulas":len(part),
           "methods":{x:{"solved":solved[x],"attempts":2*len(part),
                    "PAR2_s":round(statistics.mean(costs[x]),6)} for x in MODES},
           "v137_fastpath_counts":dict(path_counts),"v137_two_successes":matched}
    return summary

def audit(a):
    m=load(a.manifest);check(m["protocol"]==PROTOCOL and len(m["cases"])==CASES,"Bad audit")
    rows=[];binary_hashes=set();source_hashes=set();models=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v137-shard-{shard}"
        if not (folder/"meta.json").exists():folder=folder/"results"
        meta=load(folder/"meta.json");part=load(folder/"rows.json")
        expected=m["cases"][shard::SHARDS]
        check(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
              meta["ids"]==[c["id"] for c in expected],"Wrong shard")
        check(len(part)==len(expected) and [q["id"] for q in part]==meta["ids"],
              "Missing cases")
        binary_hashes.add(json.dumps(meta["binaries"],sort_keys=True))
        source_hashes.add((meta["routing_sha256"],meta["generator_sha256"],meta["fastpath_sha256"]))
        models.add(meta["cpu"]);rows.extend(part)
    check(len(binary_hashes)==1 and len(source_hashes)==1 and len(rows)==CASES,
          "Heterogeneous or incomplete runs")
    shas={};forbidden=set()
    for c in m["cases"]:
        check(c["sha256"] not in forbidden,"Duplicate SHA")
        forbidden.add(c["sha256"]);shas[c["id"]]=c
    for r in rows:
        c=shas[r["id"]]
        check(r["sha256"]==c["sha256"] and r["label"]==c["label"],"Case identity drift")
    result={"protocol":PROTOCOL,"n_formulas":CASES,"attempts":CASES*REPS*len(MODES),
       "summary":aggregate(rows),"limitations":m["limitations"],
       "runner_cpu_models":sorted(models),"rows":rows}
    save(a.out,result)
    lines=["# DRNAS V13.7 — exact affine / PHP fast path versus three fixed policies","",
        "**40 fresh synthetic formulas from five already-known families. This is NOT an official SAT benchmark.**",
        "Each method had two runs per formula and 24 seconds cap.",
        "V13.7 is a separate Python process; its process startup + structural decision are included in wall time.","",
        "| Group | V13.7 solved | V13.7 PAR2 | V13.6 PAR2 | DRNAS PAR2 | Kissat PAR2 |",
        "|---|---:|---:|---:|---:|---:|"]
    for group in ("all",)+holdout.FAMILIES:
        x=result["summary"][group];d=x["methods"]
        lines.append(f"| {group} | {d['V137_Exact']['solved']}/{d['V137_Exact']['attempts']} | {d['V137_Exact']['PAR2_s']:.5f} | {d['Router136']['PAR2_s']:.5f} | {d['DRNAS_Legacy']['PAR2_s']:.5f} | {d['Kissat404']['PAR2_s']:.5f} |")
    lines+=["","## Limitations"]
    lines.extend("- "+x for x in m["limitations"])
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V137_AUDIT_PASS",json.dumps(result["summary"]["all"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    a=sub.add_parser("freeze")
    for key in ("out","source","generator"):a.add_argument("--"+key,required=True)
    a=sub.add_parser("run")
    for key in ("manifest","source","generator","fastpath","drnas","kissat","out"):
        a.add_argument("--"+key,required=True)
    a.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for key in ("manifest","combined","out","md"):a.add_argument("--"+key,required=True)
    args=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(args),
     "run":lambda:run(args),"audit":lambda:audit(args)}[args.cmd]()
if __name__=="__main__":main()

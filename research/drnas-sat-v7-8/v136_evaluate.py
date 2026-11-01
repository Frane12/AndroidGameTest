#!/usr/bin/env python3
"""V13.6: reproducible symbolic routing diagnostic on 40 unseen synthetic CNFs.

Synthetic formulas are previously unseen SHA-distinct fresh sizes/seeds; they
come from the same five KNOWN families as V13.4 (NOT independent SAT benchmark
distribution). Rule committed before new solve timings.
"""
import argparse,collections,hashlib,json,os,random,statistics,time
from pathlib import Path
import v136_symbolic as gen
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-V136-NEW-40-STRUCTURAL-LOCKED-20261101"
SHARDS=8;REPS=2;CAP=24.0;MODES=("DRNAS_Legacy","Kissat404","Router")
mini.CAP=CAP;mini.MEMORY_GIB=3

def check(cond,msg):
    if not cond:raise RuntimeError(msg)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def freeze(a):
    gen.selftest()
    cases=[gen.make(f,i)[0] for i in range(8) for f in gen.FAMILIES]
    check(len(cases)==40 and len({c["sha256"] for c in cases})==40,"Invalid 40-case manifest")
    save(a.out,{"protocol":PROTOCOL,"cases":cases,"shards":SHARDS,"repetitions":REPS,
      "cap_s":CAP,"memory_gib":3,
      "fixed_rule":"Kissat for verified complete pigeonhole or odd-global-XOR contradiction; otherwise DRNAS Legacy",
      "router_source_sha256":sha(a.router_source),
      "limitations":[
       "40 new synthetic instances, five familiar structure families and new size/seed ladder.",
       "Synthetic distribution is not a fully independent generalization test.",
       "Family identities previously studied in V13.4; strategy is theory motivated but informed by prior outcomes.",
       "Only upstream Kissat 4.0.4 and DRNAS Legacy tested, no all-SAT dominance claim.",
       "Every router run measures its own parsing + solver time, and is capped at 24 seconds end to end.",
       "One pinned core per runner, runner CPU models may differ between shards.",
       "No independent UNSAT proof certificates output, mathematical generator truth verified.",
       "No official 2026 competition ranking or world-record claim."]})
    print("V136_FREEZE_PASS",len(cases),flush=True)
def selftest():
    gen.selftest()
    check(SHARDS==8 and CAP==24.0 and REPS==2,"Protocol constants drift")
    print("V136_PROTOCOL_SELFTEST_PASS",flush=True)
def trial_router(path,drnas,kissat,official,seed):
    start=time.monotonic()
    raw=path.read_bytes()
    selection,reason=gen.classify(raw)
    overhead=time.monotonic()-start
    check(overhead<CAP,"Detection exceeded cap")
    # Keep full route within the same nominal wall budget as baseline.
    mini.CAP=max(0.01,CAP-overhead)
    try:
        ans=mini.trial(selection,path,seed,drnas,kissat,official)
    finally:
        mini.CAP=CAP
    total=overhead+ans["seconds"]
    status=ans["status"]
    check(status!="ERROR","Router solver failed: "+str(ans["error"]))
    # Budget race: cap failures are failures even if backend narrowly finishes.
    if total>CAP and status!="TIMEOUT":
        status="TIMEOUT"
    return {"mode":"Router","selected_solver":selection,"selection_reason":reason,
            "preprocess_s":round(overhead,6),
            "status":status,"seconds":round(min(CAP,total),6),
            "answer":ans["answer"] if status!="TIMEOUT" else None,
            "error":"","exit_code":ans["exit_code"]}
def run(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and 0<=a.shard<SHARDS,"Wrong protocol")
    check(m["router_source_sha256"]==sha(a.router_source),"Router source changed after freeze")
    cases=m["cases"][a.shard::SHARDS]
    check(len(cases)==5,"Expected five cases per shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((l.split(":",1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
             if l.startswith("model name")),"unknown")
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    save(dest/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
      "ids":[c["id"] for c in cases],"cpu":cpu,
      "generator_sha256":sha(a.generator_source),
      "router_source_sha256":sha(a.router_source),
      "binaries":{k:sha(getattr(a,k)) for k in ("drnas","kissat")}})
    rows=[]
    for c in cases:
        info,raw=gen.make(c["family"],c["index"])
        check(info==c,"Generator drift")
        file=dest/(str(c["index"])+"-"+c["family"]+".cnf")
        file.write_bytes(raw)
        check(sha(file)==c["sha256"],"Wrong CNF SHA")
        trials=[]
        for rep in range(REPS):
            seed=(1362026+1009*rep+int(c["sha256"][:8],16))%(2**32)
            modes=list(MODES);random.Random(seed^136).shuffle(modes)
            for mode in modes:
                if mode=="Router":
                    data=trial_router(file,a.drnas,a.kissat,c["label"],seed)
                else:
                    o=mini.trial(mode,file,seed,a.drnas,a.kissat,c["label"])
                    check(o["status"]!="ERROR","Solver error: "+str(o["error"]))
                    data={"mode":mode,"selected_solver":mode,
                          "selection_reason":"fixed_baseline","preprocess_s":0.0,**o}
                check(data["status"] in ("SAT","UNSAT","TIMEOUT"),"Invalid status")
                check(data["status"]=="TIMEOUT" or data["status"]==c["label"],"Wrong label")
                trials.append({"rep":rep,**data})
                print("V136_TRIAL",a.shard,c["id"],rep,mode,
                      data["selected_solver"],data["status"],data["seconds"],
                      data["preprocess_s"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"family":c["family"],
                     "label":c["label"],"trials":trials})
        save(dest/"rows.json",rows)
        file.unlink()
    check(len(rows)==5,"Missing rows")
    print("V136_SHARD_PASS",a.shard,len(rows),flush=True)
def aggregate(rows):
    output={}
    for group in ("all",)+gen.FAMILIES:
        subset=[r for r in rows if group=="all" or r["family"]==group]
        modes={m:[] for m in MODES};solved=collections.Counter();overheads=[]
        decisions=collections.Counter();wins=collections.Counter()
        for r in subset:
            pair={(t["mode"],t["rep"]):t for t in r["trials"]}
            check(len(pair)==REPS*len(MODES),"Missing or duplicate paired trials")
            for mode in MODES:
                for rep in range(REPS):
                    v=pair[(mode,rep)]
                    check(0<=v["seconds"]<=CAP+0.1 and not v["error"],"Bad runtime")
                    check(v["status"] in ("SAT","UNSAT","TIMEOUT"),"Bad result")
                    check(v["status"]=="TIMEOUT" or v["status"]==r["label"],"Wrong result")
                    solved[mode]+=int(v["status"]!="TIMEOUT")
                    modes[mode].append(2*CAP if v["status"]=="TIMEOUT" else v["seconds"])
            decision=pair[("Router",0)]["selected_solver"]
            check(all(pair[("Router",i)]["selected_solver"]==decision for i in range(REPS)),
                  "Unstable routing")
            decisions[decision]+=1
            overheads.extend(pair[("Router",i)]["preprocess_s"] for i in range(REPS))
            par={mode:statistics.mean([2*CAP if pair[(mode,i)]["status"]=="TIMEOUT"
                 else pair[(mode,i)]["seconds"] for i in range(REPS)]) for mode in MODES}
            best=min(("DRNAS_Legacy","Kissat404"),key=lambda mode:par[mode])
            if (par["DRNAS_Legacy"]-par["Kissat404"]>=0.25 and
                par["DRNAS_Legacy"]-par["Kissat404"]>=0.20*par["DRNAS_Legacy"]):
                wins["Kissat_clear"]+=1
            if (par["Kissat404"]-par["DRNAS_Legacy"]>=0.25 and
                par["Kissat404"]-par["DRNAS_Legacy"]>=0.20*par["Kissat404"]):
                wins["DRNAS_clear"]+=1
        output[group]={"formulas":len(subset),
           "methods":{mode:{"solved":solved[mode],"attempts":len(subset)*REPS,
             "PAR2_s":round(statistics.mean(modes[mode]),6)} for mode in MODES},
           "routing":dict(decisions),"clear_pair_wins":dict(wins),
           "mean_detection_s":round(statistics.mean(overheads),6),
           "max_detection_s":round(max(overheads),6)}
    return output
def audit(a):
    m=load(a.manifest)
    check(m["protocol"]==PROTOCOL and len(m["cases"])==40,"Incorrect frozen manifest")
    rows=[];hashes=set();cpus=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v136-shard-{shard}"
        # GitHub artifact path results/ is flattened to root.
        if not (folder/"meta.json").is_file():folder=folder/"results"
        meta=load(folder/"meta.json");part=load(folder/"rows.json")
        expected=m["cases"][shard::SHARDS]
        check(meta["shard"]==shard and meta["protocol"]==PROTOCOL and
              meta["ids"]==[x["id"] for x in expected],"Shard identity mismatch")
        check(meta["router_source_sha256"]==m["router_source_sha256"],
              "Selected rule changed")
        check(len(part)==5 and [x["id"] for x in part]==[x["id"] for x in expected],
              "Missing shard formulas")
        hashes.add(json.dumps(meta["binaries"],sort_keys=True));cpus.add(meta["cpu"])
        rows.extend(part)
    check(len(hashes)==1 and len(rows)==40 and len({r["sha256"] for r in rows})==40,
          "Incomplete/heterogeneous experiment")
    index={r["id"]:r for r in m["cases"]}
    for row in rows:
        info,raw=gen.make(row["family"],int(row["id"].rsplit("/",1)[-1]))
        check(info==index[row["id"]] and row["sha256"]==info["sha256"],"Input changed")
        selection,reason=gen.classify(raw)
        check(all(t["selected_solver"]==selection and t["selection_reason"]==reason
                  for t in row["trials"] if t["mode"]=="Router"),"Router selection drift")
    report={"protocol":PROTOCOL,"cases":40,"attempts":40*REPS*len(MODES),
            "manifest_sha256":sha(a.manifest),"limitations":m["limitations"],
            "cpu_models":sorted(cpus),"summary":aggregate(rows),"rows":rows}
    save(a.out,report)
    lines=["# DRNAS V13.6 — symbolic structural routing / new synthetic holdout","",
           "**40 new synthetic CNFs, same five known families as V13.4. NOT independent real-world SAT evidence.**",
           "48? NO: 40 formulas x 2 repetitions x 3 methods = 240 solver attempts.",
           "24 s cap and 3 GiB; routing does parse + solver as an actual additional invocation.","",
           "| Family | Solved Router | PAR2 Router | PAR2 DRNAS | PAR2 Kissat | Kissat selections |",
           "|---|---:|---:|---:|---:|---:|"]
    for fam in ("all",)+gen.FAMILIES:
        q=report["summary"][fam];d=q["methods"]
        lines.append(f"| {fam} | {d['Router']['solved']}/{d['Router']['attempts']} | {d['Router']['PAR2_s']:.5f} | {d['DRNAS_Legacy']['PAR2_s']:.5f} | {d['Kissat404']['PAR2_s']:.5f} | {q['routing'].get('Kissat404',0)}/{q['formulas']} |")
    lines+=["","## Routing and limitations"]
    lines.extend("- "+s for s in m["limitations"])
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V136_AUDIT_PASS",json.dumps(report["summary"]["all"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    f.add_argument("--out",required=True);f.add_argument("--router-source",required=True)
    r=sub.add_parser("run")
    for name in ("manifest","router-source","generator-source","drnas","kissat","out"):
        r.add_argument("--"+name,required=True)
    r.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for name in ("manifest","combined","out","md"):z.add_argument("--"+name,required=True)
    a=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(a),"run":lambda:run(a),
     "audit":lambda:audit(a)}[a.cmd]()
if __name__=="__main__":main()

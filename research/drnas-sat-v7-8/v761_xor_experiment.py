#!/usr/bin/env python3
"""V7.6.1 frozen XOR experiment: 20 exact-case timing repetitions + 48 new XOR.

Same existing frozen V13.4 XOR UNSAT /3 case, unchanged 30s/3GiB constraints,
plus 48 preregistered XOR formulas, across 8 separate pinned-CPU runners.
All four solver modes tested with paired order counterbalancing. No tuning.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
import v761_xor_holdout as xor
import v76_v134_matched as prior
import official_2026_mini_sim as mini
import v134_constructive as v134

P="DRNAS-V761-XOR-REPEATS-AND-48-FROZEN-20261101-v1"
OLD="DRNAS-V134-LOCKED-STRUCTURAL-LADDERS-20261101"
CASE_ID="generated/v134/cubic_xor_unsat/3"
MODES=prior.MODES
REPS=2
CAP=30.0;SHARDS=8;REPEAT_COUNT=20
mini.CAP=CAP;mini.MEMORY_GIB=3
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def read(p):return json.loads(Path(p).read_text())
def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def selftest():
    xor.selftest()
    prior.selftest()
    need(len(MODES)==4 and CAP==30.0 and SHARDS==8,"Settings changed")
    print("V761_SELFTEST_PASS",flush=True)
def freeze(a):
    old=read(a.original)
    need(old["protocol"]==OLD and len(old["cases"])==30,"Wrong original 30")
    chosen=next(c for c in old["cases"] if c["id"]==CASE_ID)
    expect,raw=v134.make(chosen["family"],chosen["index"])
    need(chosen==expect and hashlib.sha256(raw).hexdigest()==chosen["sha256"],
         "Exact original XOR CNF drift")
    known=set(c["sha256"] for c in old["cases"])
    xor.selftest(known)
    new=[xor.make(i)[0] for i in range(xor.COUNT)]
    need(len(new)==48 and not known.intersection(c["sha256"] for c in new),
         "Novelty collision")
    write(a.out,{"protocol":P,"old_v134_manifest_sha256":sha(a.original),
                 "original_case":chosen,"new_cases":new,
                 "repeats_exact_case":REPEAT_COUNT,"new_reps":REPS,
                 "cap_seconds":CAP,"memory_gib":3,"shards":SHARDS,
                 "source_implementation_sha":"a254356a45b70f02f33b9506f1122dad33916ca7",
                 "method_order":list(MODES),"design":[
                    "Same single V13.4 XOR UNSAT case repeated 20 times: fixed seed per run, randomized method execution order.",
                    "48 new XOR cases: 40 UNSAT and 8 SAT, fixed graph sizes 48..90, predeclared before outcomes.",
                    "Same runner and one pinned CPU for four methods per repetition; 30s/3GiB.",
                    "No performance-based instance filtering; timeouts recorded as PAR2=60 seconds.",
                    "Prior baseline and new holdout are exploratory: no official SAT Competition rank.",
                    "Repeating one fixed deterministic formula checks runtime stability, not generalization.",
                    "V7.6 native telemetry available in its stdout: hints, learning and continuation at 256 conflicts.",
                    "Phase hints causal impact tested via guided vs plain matched V7.6 modes; no hot-loop change."]})
    print("V761_FREEZE_PASS",CASE_ID,len(new),sha(a.out),flush=True)
def pin():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def v76_trial(mode,cnf,seed,v76,truth):
    method={"V76_adaptive_guided":"adaptive_guided","V76_adaptive_plain":"adaptive_plain"}[mode]
    start=time.monotonic()
    try:
        p=subprocess.run([str(Path(v76).resolve()),method,str(Path(cnf).resolve()),str(seed)],
           capture_output=True,text=True,errors="replace",timeout=CAP,
           preexec_fn=mini.memory_limit)
        elapsed=min(CAP+0.2,time.monotonic()-start)
        need(p.returncode==0,"V7.6 process exit "+str(p.returncode)+" "+p.stderr[-180:])
        lines=[x for x in p.stdout.splitlines() if x.startswith("DRNAS_RESULT\t")]
        need(len(lines)==1,"Missing V7.6 result")
        fields=lines[0].split("\t")
        need(len(fields)>=21 and fields[1]==method,"Bad V7.6 stdout")
        need(fields[2]==truth,"SAT/UNSAT truth mismatch")
        names={4:"hint_count",5:"first_budget",6:"stage1",7:"extended",
               8:"learned_256",9:"learned_threshold",10:"active_pre",
               11:"active_256",12:"second_budget",13:"stage2",14:"resumed"}
        diag={name:int(fields[index]) for index,name in names.items()}
        return {"status":truth,"seconds":round(elapsed,6),"answer":truth,
                "error":"","exit_code":p.returncode,"diag":diag}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"answer":None,
                "error":"","exit_code":None,"diag":None}
    except Exception as exc:
        return {"status":"ERROR","seconds":min(time.monotonic()-start,CAP),
                "answer":None,"error":str(exc)[:300],"exit_code":None,"diag":None}
def run_one(mode,cnf,seed,truth,a):
    if mode.startswith("V76_"):return v76_trial(mode,cnf,seed,a.v76,truth)
    return prior.trial(mode,cnf,seed,truth,a.v76,a.legacy,a.kissat)
def provenance(a,ids):
    return {"protocol":P,"manifest_sha256":sha(a.manifest),"ids":ids,
            "binaries":{x:sha(getattr(a,x)) for x in ("v76","legacy","kissat")},
            "cpu_model":next((z.split(":",1)[1].strip() for z in Path("/proc/cpuinfo").read_text().splitlines()
                              if z.startswith("model name")),"unknown")}
def run_repeat(a):
    m=read(a.manifest);need(m["protocol"]==P,"Protocol drift")
    pin();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    c=m["original_case"];expected,raw=v134.make(c["family"],c["index"])
    need(c==expected,"Original case mutated")
    f=out/"original.cfn";f.write_bytes(raw)
    need(sha(f)==c["sha256"],"Original case checksum drift")
    write(out/"meta.json",provenance(a,[CASE_ID]))
    seed=(1342026+int(c["sha256"][:8],16))%(2**32)
    all_rows=[]
    for rep in range(REPEAT_COUNT):
        order=list(MODES);random.Random(761*100000+rep).shuffle(order)
        obs=[]
        for mode in order:
            v=run_one(mode,f,seed,c["official_label"],a)
            need(v["status"]!="ERROR","Solver failed "+mode+": "+v["error"])
            obs.append({"mode":mode,"repetition":rep,"seed":seed,**v})
            print("V761_REPEAT",rep,mode,v["status"],v["seconds"],flush=True)
        all_rows.append({"rep":rep,"trials":obs})
        write(out/"rows.json",all_rows)
    need(len(all_rows)==20,"Incomplete repeats")
    f.unlink()
    print("V761_REPEAT_PASS",len(all_rows),flush=True)
def run_holdout(a):
    m=read(a.manifest)
    need(m["protocol"]==P and 0<=a.shard<SHARDS,"Protocol/shard drift")
    cases=m["new_cases"][a.shard::SHARDS]
    need(len(cases)==6,"Wrong fixed partition")
    pin();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    write(out/"meta.json",provenance(a,[c["id"] for c in cases]))
    rows=[]
    for c in cases:
        entry,raw=xor.make(c["index"])
        need(entry==c,"Generator source mismatch")
        f=out/(c["id"].split("/")[-1]+".cnf");f.write_bytes(raw)
        need(sha(f)==c["sha256"],"Holdout SHA mismatch")
        obs=[]
        for rep in range(REPS):
            seed=(7612026+int(c["sha256"][:8],16)+1009*rep)%(2**32)
            order=list(MODES);random.Random(seed^761).shuffle(order)
            for mode in order:
                v=run_one(mode,f,seed,c["official_label"],a)
                need(v["status"]!="ERROR","Solver failed "+mode+": "+v["error"])
                obs.append({"mode":mode,"repetition":rep,"seed":seed,**v})
                print("V761_HOLDOUT",a.shard,c["id"],rep,mode,v["status"],v["seconds"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"family":c["family"],
                    "size":c["graph_vertices"],"label":c["official_label"],"trials":obs})
        write(out/"rows.json",rows)
        f.unlink()
    need(len(rows)==6,"Shard incomplete")
    print("V761_HOLDOUT_SHARD_PASS",a.shard,flush=True)
def stats(rows):
    solved=Counter();times=defaultdict(list);per={}
    for r in rows:
        lookup={(o["mode"],o["repetition"]):o for o in r["trials"]}
        need(len(lookup)==8,"Wrong mode-repetition count for "+r["id"])
        per[r["id"]]={"size":r["size"],"label":r["label"],"family":r["family"],"par2":{}}
        for mode in MODES:
            tt=[]
            for rep in range(2):
                x=lookup[mode,rep]
                need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"Invalid outcome")
                need(x["status"]=="TIMEOUT" or x["status"]==r["label"],"Wrong truth")
                need(x["status"]=="TIMEOUT" or 0<=x["seconds"]<=30.2,"Bad runtime")
                solved[mode]+=int(x["status"]!="TIMEOUT")
                val=60 if x["status"]=="TIMEOUT" else x["seconds"]
                tt.append(val);times[mode].append(val)
            per[r["id"]]["par2"][mode]=statistics.mean(tt)
    return {"case_count":len(rows),"solvers":{k:{"solved":solved[k],"total":2*len(rows),
             "PAR2_s":round(statistics.mean(times[k]),6)} for k in MODES},
            "cases":per}
def repeat_stats(rows):
    out=defaultdict(list);diag=defaultdict(list);paired=defaultdict(list)
    for row in rows:
        lookup={t["mode"]:t for t in row["trials"]}
        need(set(lookup)==set(MODES),"Missing repeat modes")
        for mode in MODES:
            v=lookup[mode];need(v["status"]=="UNSAT","Exact repeat should solve UNSAT")
            out[mode].append(v["seconds"])
            if v.get("diag"):diag[mode].append(v["diag"])
        paired["guided_vs_legacy_s"].append(lookup["DRNAS_Legacy"]["seconds"]-lookup["V76_adaptive_guided"]["seconds"])
        paired["guided_vs_plain_s"].append(lookup["V76_adaptive_plain"]["seconds"]-lookup["V76_adaptive_guided"]["seconds"])
    def one(x):return {"mean_s":round(statistics.mean(x),6),"median_s":round(statistics.median(x),6),
                       "min_s":round(min(x),6),"max_s":round(max(x),6),
                       "stddev_s":round(statistics.stdev(x),6)}
    return {"number_of_repetitions":len(rows),"same_seed_all_repeats":True,
            "solvers":{k:one(v) for k,v in out.items()},
            "paired":{k:one(v) for k,v in paired.items()},
            "v76_telemetry":{k:{field:sorted(set(v[field] for v in vs)) for field in
                              ("learned_256","active_256","hint_count","extended","resumed")}
                             for k,vs in diag.items()}}
def audit(a):
    m=read(a.manifest);need(m["protocol"]==P,"Protocol drift")
    repeat_dir=Path(a.repeat)
    rep_meta=read(repeat_dir/"meta.json")
    rep_rows=read(repeat_dir/"rows.json")
    need(len(rep_rows)==REPEAT_COUNT and [x["rep"] for x in rep_rows]==list(range(REPEAT_COUNT)),
         "Missing repeat")
    sha_set={json.dumps(rep_meta["binaries"],sort_keys=True)}
    need(rep_meta["manifest_sha256"]==sha(a.manifest),"Repeat input drift")
    all_rows=[];cpu=set([rep_meta["cpu_model"]])
    for shard in range(SHARDS):
        d=Path(a.holdouts)/f"v761-shard-{shard}"
        meta=read(d/"meta.json");rows=read(d/"rows.json")
        expected=m["new_cases"][shard::SHARDS]
        need(meta["ids"]==[x["id"] for x in expected] and len(rows)==6,
             "Wrong holdout case provenance")
        need(meta["manifest_sha256"]==sha(a.manifest),"Holdout manifest drift")
        sha_set.add(json.dumps(meta["binaries"],sort_keys=True));cpu.add(meta["cpu_model"])
        all_rows.extend(rows)
    need(len(sha_set)==1,"Different pinned solver binaries")
    index={x["id"]:x for x in m["new_cases"]}
    need(len(all_rows)==48 and len({r["sha256"] for r in all_rows})==48,
         "Incomplete SHA-unique holdout")
    for row in all_rows:
        c=index[row["id"]]
        need(row["sha256"]==c["sha256"] and row["label"]==c["official_label"],
             "Holdout source mismatch")
    summary={"all":stats(all_rows),"xor_unsat":stats([r for r in all_rows if r["label"]=="UNSAT"]),
             "xor_sat":stats([r for r in all_rows if r["label"]=="SAT"])}
    rpt={"protocol":P,"repeat":repeat_stats(rep_rows),"holdout":summary,
         "case_id":CASE_ID,"new_samples":len(all_rows),"reps":REPS,
         "binaries_sha256":json.loads(next(iter(sha_set))),"CPU_models":sorted(cpu),
         "source_manifest_sha256":sha(a.manifest),"limitations":m["design"]}
    write(a.out,rpt)
    lines=["# DRNAS V7.6.1 – single XOR repeat plus independent 48-XOR holdout","",
      "Same original source code and immutable old V13.4 case; no new heuristic.",
      "20 same-seed repeats on one runner; 48 new preregistered cases on 8 runners.","",
      "## 20 repetitions of the old XOR UNSAT case","",
      "| Solver | Mean wall s | Median s | Standard deviation s |","|---|---:|---:|---:|"]
    for mode,v in rpt["repeat"]["solvers"].items():
        lines.append(f"| {mode} | {v['mean_s']:.6f} | {v['median_s']:.6f} | {v['stddev_s']:.6f} |")
    lines+=["","## New holdout: 48 XOR cases, 2 reps per solver",""]
    for label,group in summary.items():
        lines +=[f"### {label}: {group['case_count']} formulas","",
                 "| Solver | Solved attempts | PAR2 s |","|---|---:|---:|"]
        for mode,v in group["solvers"].items():
            lines.append(f"| {mode} | {v['solved']}/{v['total']} | {v['PAR2_s']:.6f} |")
        lines.append("")
    lines+=["## Caveats"]+["- "+x for x in m["design"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V761_AUDIT_PASS",json.dumps({"repeat":rpt["repeat"]["solvers"],
          "holdout":summary["all"]["solvers"]}),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    a=sub.add_parser("freeze")
    for field in ("original","out"):a.add_argument("--"+field,required=True)
    for name in ("repeat","holdout"):
        x=sub.add_parser(name)
        for field in ("manifest","v76","legacy","kissat","out"):x.add_argument("--"+field,required=True)
        if name=="holdout":x.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for field in ("manifest","repeat","holdouts","out","md"):a.add_argument("--"+field,required=True)
    z=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(z),"repeat":lambda:run_repeat(z),
     "holdout":lambda:run_holdout(z),"audit":lambda:audit(z)}[z.command]()
if __name__=="__main__":main()

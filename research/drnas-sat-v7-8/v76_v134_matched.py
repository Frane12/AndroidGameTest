#!/usr/bin/env python3
"""Frozen V13.4 30-CNF V7.6 comparison. No adaptive tuning or case filtering.

Four modes, each 2 repeats, 30 s and 3 GiB, on same runner + pinned CPU:
original V7.6 adaptive_guided and adaptive_plain, DRNAS Legacy, Kissat 4.0.4.
Time is externally measured (wall clock) including parsing for all binaries.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
import official_2026_mini_sim as mini
import v134_constructive as formulas
PROTOCOL="DRNAS-V76-against-V134-30-locked-20261101-v1"
ORIGINAL="DRNAS-V134-LOCKED-STRUCTURAL-LADDERS-20261101"
MODES=("V76_adaptive_guided","V76_adaptive_plain","DRNAS_Legacy","Kissat404")
REPS=2;CAP=30.0;SHARDS=6
mini.CAP=CAP;mini.MEMORY_GIB=3
def require(cond,msg):
    if not cond:raise RuntimeError(msg)
def read(path):return json.loads(Path(path).read_text())
def write(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def selftest():
    formulas.selftest()
    require(CAP==30 and REPS==2 and SHARDS==6,"Bench settings drift")
    require(MODES[:2]==("V76_adaptive_guided","V76_adaptive_plain"),"V76 policy drift")
    require(len(MODES)==4 and len(set(MODES))==4,"Wrong modes")
    print("V76_V134_SELFTEST_PASS",flush=True)
def freeze(a):
    m=read(a.original)
    require(m["protocol"]==ORIGINAL and len(m["cases"])==30,"Wrong frozen V13.4 cohort")
    require(m["cap_seconds"]==CAP and m["reps"]==REPS and m["shards"]==SHARDS,
            "Frozen settings drift")
    require([c["sha256"] for c in m["cases"]]==[
       formulas.make(c["family"],c["index"])[0]["sha256"] for c in m["cases"]],
       "Generator/SHA drift in old V13.4 cases")
    # Preserve EXACT original frozen manifest, not a regenerated replacement.
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_bytes(Path(a.original).read_bytes())
    print("V76_FROZEN_V134_PASS",len(m["cases"]),sha(a.out),flush=True)
def trial(mode,cnf,seed,original_label,v76,legacy,kissat):
    if mode in ("DRNAS_Legacy","Kissat404"):
        return mini.trial(mode,cnf,seed,legacy,kissat,original_label)
    method={"V76_adaptive_guided":"adaptive_guided",
            "V76_adaptive_plain":"adaptive_plain"}[mode]
    start=time.monotonic()
    try:
        p=subprocess.run([str(Path(v76).resolve()),method,str(cnf.resolve()),str(seed)],
                         capture_output=True,text=True,errors="replace",
                         check=False,timeout=CAP,preexec_fn=mini.memory_limit)
        elapsed=min(time.monotonic()-start,CAP+0.2)
        require(p.returncode==0,"Nonzero V7.6 exit: "+str(p.returncode)+" "+p.stderr[-240:])
        lines=[line for line in p.stdout.splitlines() if line.startswith("DRNAS_RESULT\t")]
        require(len(lines)==1,"Missing/duplicate V7.6 telemetry")
        fields=lines[0].split("\t")
        require(len(fields)>=5 and fields[1]==method,"Wrong V7.6 mode")
        answer=fields[2]
        require(answer in ("SAT","UNSAT") and answer==original_label,
                "V7.6 inconsistent SAT/UNSAT result: "+str(answer))
        return {"status":answer,"seconds":round(elapsed,6),"answer":answer,
                "error":"","exit_code":p.returncode}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"answer":None,
                "error":"","exit_code":None}
    except Exception as exc:
        return {"status":"ERROR","seconds":min(time.monotonic()-start,CAP),
                "answer":None,"error":str(exc)[:340],"exit_code":None}
def run(a):
    manifest=read(a.manifest)
    require(manifest["protocol"]==ORIGINAL and len(manifest["cases"])==30,
            "Wrong V13.4 manifest")
    require(0<=a.shard<SHARDS,"Wrong shard")
    cases=manifest["cases"][a.shard::SHARDS]
    require(len(cases)==5,"Bad case partition")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    cpuinfo=Path("/proc/cpuinfo").read_text()
    model=next((x.split(":",1)[1].strip() for x in cpuinfo.splitlines()
                if x.startswith("model name")),"unknown")
    write(root/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
       "manifest_sha256":sha(a.manifest),"case_ids":[c["id"] for c in cases],
       "cpu":model,"binary_sha256":{key:sha(getattr(a,key)) for key in ("v76","legacy","kissat")},
       "mode_order":list(MODES),"cap":CAP,"repetitions":REPS})
    rows=[]
    for c in cases:
        entry,raw=formulas.make(c["family"],c["index"])
        require(entry==c,"SHA/deterministic formula mismatch "+c["id"])
        f=root/(hashlib.sha256(c["id"].encode()).hexdigest()[:20]+".cnf")
        f.write_bytes(raw)
        require(sha(f)==c["sha256"],"Input SHA mismatch")
        trials=[]
        for repetition in range(REPS):
            # Matches original V13.4 seed exactly, for all four strategies.
            seed=(1342026+1009*repetition+int(c["sha256"][:8],16))%(2**32)
            order=list(MODES);random.Random(seed^760134).shuffle(order)
            for mode in order:
                obs=trial(mode,f,seed,c["official_label"],a.v76,a.legacy,a.kissat)
                trials.append({"mode":mode,"repetition":repetition,"seed":seed,**obs})
                print("V76V134_TRIAL",a.shard,c["id"],mode,repetition,
                      obs["status"],f'{obs["seconds"]:.6f}',flush=True)
                require(obs["status"]!="ERROR","Solver error "+mode+": "+obs["error"])
        rows.append({"id":c["id"],"family":c["family"],"index":c["index"],
                     "sha256":c["sha256"],"label":c["official_label"],"trials":trials})
        write(root/"rows.json",rows)
        f.unlink(missing_ok=True)
    require(len(rows)==5,"Shard incomplete")
    print("V76V134_SHARD_PASS",a.shard,len(rows),flush=True)
def group_result(rows):
    costs=defaultdict(list);solved=Counter();cases={};leaders=Counter()
    for r in rows:
        lookup={(t["mode"],t["repetition"]):t for t in r["trials"]}
        require(len(lookup)==len(MODES)*REPS,"Missing mode/rep")
        medians={}
        for mode in MODES:
            cc=[]
            for rep in range(REPS):
                v=lookup[mode,rep]
                require(v["status"] in ("SAT","UNSAT","TIMEOUT") and not v["error"],
                        "Invalid status")
                require(v["status"]=="TIMEOUT" or v["status"]==r["label"],
                        "Wrong solver truth value")
                require(0<=v["seconds"]<=CAP+0.2,"Invalid wall time")
                solved[mode]+=int(v["status"]!="TIMEOUT")
                val=2*CAP if v["status"]=="TIMEOUT" else v["seconds"]
                costs[mode].append(val);cc.append(val)
            medians[mode]=statistics.mean(cc)
        leader=min(MODES,key=lambda name:medians[name])
        second=sorted(medians.values())[1]
        clear=(second-medians[leader]>=0.25 and
               (second-medians[leader])/max(second,0.0001)>=0.20)
        if clear:leaders[leader]+=1
        cases[r["id"]]={"family":r["family"],"par2_mean_by_solver":medians,
                       "clear_best":leader if clear else None}
    return {"cases":len(rows),"attempts_per_solver":len(rows)*REPS,
        "solvers":{m:{"solved":solved[m],"total":len(rows)*REPS,
                      "PAR2_s":round(statistics.mean(costs[m]),6)}
                   for m in MODES},
        "clear_single_case_wins":dict(leaders),"case_details":cases}
def audit(a):
    manifest=read(a.manifest)
    require(manifest["protocol"]==ORIGINAL,"Wrong frozen protocol")
    rows=[];binary_sha=set();cpu=set()
    for shard in range(SHARDS):
        root=Path(a.combined)/f"v76v134-shard-{shard}"
        meta=read(root/"meta.json")
        part=read(root/"rows.json")
        expected=manifest["cases"][shard::SHARDS]
        require(meta["shard"]==shard and meta["protocol"]==PROTOCOL,
                "Wrong shard meta")
        require(meta["manifest_sha256"]==sha(a.manifest),"Manifest drift")
        require(meta["case_ids"]==[x["id"] for x in expected],"Formula ID drift")
        require(len(part)==5 and [x["id"] for x in part]==[x["id"] for x in expected],
                "Missing case row")
        binary_sha.add(json.dumps(meta["binary_sha256"],sort_keys=True));cpu.add(meta["cpu"])
        rows.extend(part)
    require(len(binary_sha)==1,"Binary differs between GitHub runners")
    require(len(rows)==30 and len({r["sha256"] for r in rows})==30,"Case SHA mismatch")
    by_id={c["id"]:c for c in manifest["cases"]}
    for r in rows:
        c=by_id[r["id"]]
        require(r["sha256"]==c["sha256"] and r["family"]==c["family"] and
                r["label"]==c["official_label"],"Case provenance wrong")
    groups={"all":group_result(rows)}
    for family in formulas.FAMILIES:
        group=[r for r in rows if r["family"]==family]
        require(len(group)==6,"Missing family")
        groups[family]=group_result(group)
    old=read(a.original_report)
    require(old["protocol"]==ORIGINAL,"V13.4 audit provenance mismatch")
    prior={r["id"]:r for r in old["rows"]}
    require(len(prior)==30 and all(prior[c["id"]]["sha256"]==c["sha256"] for c in manifest["cases"]),
            "Original V13.4 benchmark SHA mismatch")
    report={"protocol":PROTOCOL,"original_v134_manifest_sha256":sha(a.manifest),
            "previous_v134_report_sha256":sha(a.original_report),
            "paired_rebenchmark":groups,"original_v134_report_baseline":old["summary"]["all"]["solvers"],
            "binaries_sha256":json.loads(next(iter(binary_sha))),"CPU_models":sorted(cpu),
            "rows":rows,"limits":[
              "Original 30 synthetic CNFs and seeds identical to V13.4. No replacement instances.",
              "All 4 modes measured on same shard/runner core; comparisons across shards have CPU variation.",
              "V7.6 source exact pinned SHA a254356a45b70f02f33b9506f1122dad33916ca7.",
              "V7.6 uses unmodified CaDiCaL 3.0.1; Legacy uses instrumented CaDiCaL.",
              "Run uses 30s 3GiB one CPU and two repetitions, NOT official SAT Competition.",
              "Wall-clock overhead includes subprocess startup and DIMACS parsing.",
              "Original V13.4 baseline is cross-run, so compare primarily the live four-mode matched results.",
              "No claims about statistical generalization or world-record performance."]}
    write(a.out,report)
    lines=["# DRNAS V7.6 versus V13.4 frozen 30 CNFs","",
        "Strict 30s / 3 GiB / 1 core / 2 repeats, four modes on matched runners.",
        "Same 30 formulas and seed rule, all formula SHA256 verified.",
        "V7.6 adaptive_guided vs adaptive_plain matched control and DRNAS Legacy vs Kissat.",
        "Results are unofficial and do not establish world ranking.",""]
    for name in ["all",*formulas.FAMILIES]:
        group=groups[name]
        lines.extend([f"## {name} — {group['cases']} formulas","",
          "| Mode | Solved | PAR2 seconds (lower better) |","|---|---:|---:|"])
        for mode in MODES:
            t=group["solvers"][mode]
            lines.append(f"| {mode} | {t['solved']}/{t['total']} | {t['PAR2_s']:.6f} |")
        lines+=["",f"Clear case wins (>20% and 0.25s): {group['clear_single_case_wins']}.",""]
    lines+=["## Original V13.4 independent run baseline","",
        "The two baseline modes were rerun above in the same jobs as V7.6.",
        "## Limitations"]+["- "+x for x in report["limits"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V76V134_AUDIT_PASS",json.dumps(groups["all"]["solvers"]),flush=True)
def main():
    p=argparse.ArgumentParser();su=p.add_subparsers(dest="cmd",required=True)
    su.add_parser("selftest")
    f=su.add_parser("freeze")
    for key in ("original","out"):f.add_argument("--"+key,required=True)
    r=su.add_parser("run")
    for key in ("manifest","v76","legacy","kissat","out"):r.add_argument("--"+key,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=su.add_parser("audit")
    for key in ("manifest","combined","original_report","out","md"):a.add_argument("--"+key,required=True)
    args=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(args),
     "run":lambda:run(args),"audit":lambda:audit(args)}[args.cmd]()
if __name__=="__main__":main()

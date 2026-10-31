#!/usr/bin/env python3
"""V13 early-256 CaDiCaL diagnostic on 120+12 SHA-distinct archived 2026 cases.

Retrospective association analysis, not a newly trained/adapted solver or blind holdout.
Kissat's internal metrics are NOT measured: paired Kissat results come from frozen logs.
"""
import argparse,hashlib,json,os,resource,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
import official_shortlong_select as source

PROTOCOL="DRNAS-V13-CaDiCaL256-RETROSPECTIVE-v1"
SHARDS=8
CAP=14.0
MAX_MEM=3*1024**3
FIELDS=("v90_conflicts_256","v90_learned_256","v90_lbd2_256","v90_lbd4_256",
        "v90_lbd_sum_256","v90_props_256","v90_jumps_256",
        "v90_jumpdepth_256","v90_backtracks_256","active_256","stage1","cpu_256_ns")
DERIVED=("LBD2_fraction","LBD4_fraction","mean_raw_LBD",
         "propagations_per_conflict","jump_depth_per_jump","learned_per_conflict",
         "conflicts_before_stop","prefix_cpu_ms")

def check(v,msg):
    if not v:raise RuntimeError(msg)
def read(p):return json.loads(Path(p).read_text())
def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_manifests(a,b):
    v103=read(Path(a)/"frozen/v103_manifest.json")
    v11=read(Path(b)/"frozen/v11_manifest.json")
    check(v103["accepted_cases"]==120 and v11["accepted_count"]==50,"Unexpected source size")
    u={c["id"]:c for c in v103["cases"]};v={c["id"]:c for c in v11["cases"]}
    common=set(u)&set(v)
    check(len(common)==38 and all(u[x]["sha256"]==v[x]["sha256"] for x in common),
          "Unexpected overlap or changed source input")
    other=[c for c in v11["cases"] if c["id"] not in u]
    check(len(other)==12,"Unexpected new cohort size")
    check({c["sha256"] for c in other}.isdisjoint({c["sha256"] for c in v103["cases"]}),
          "SHA overlap between cohorts")
    return v103,v11,other

def freeze(args):
    a,b,other=source_manifests(args.v103,args.v11)
    cases=[]
    for tag,src in (("V103_train",a["cases"]),("V11_SHA_disjoint",other)):
        for x in src:
            cases.append({"id":x["id"],"sha256":x["sha256"],"cohort":tag,
                          "features":x["features"],"official_label":x["official_label"]})
    check(len(cases)==132 and len({c["sha256"] for c in cases})==132,"Duplicate frozen case")
    save(args.out,{"protocol":PROTOCOL,"cases":cases,"shards":SHARDS,
      "max_prefix_conflicts":256,"timeout_s":CAP,
      "instrumentation":"CaDiCaL 3.0.1, strict v10.1 first-256 unphased replay",
      "training_run":41249978820,"reference_run":41250184539,
      "v103_manifest_sha256":digest(Path(args.v103)/"frozen/v103_manifest.json"),
      "v11_manifest_sha256":digest(Path(args.v11)/"frozen/v11_manifest.json"),
      "warnings":["NOT a blind model test: historical solver results were already known.",
                  "No Kissat first-256 telemetry; only CaDiCaL counters are measured.",
                  "V11 12 cases are source-disjoint but are NOT newly unseen to researchers.",
                  "Some cases may not reach 256 conflicts before the time cap.",
                  "Not an official SAT Competition result."]})
    print("V13_FREEZE_PASS",len(cases),len(other),flush=True)

def limit_memory():
    resource.setrlimit(resource.RLIMIT_AS,(MAX_MEM,MAX_MEM))
def probe(args):
    m=read(args.manifest)
    check(m["protocol"]==PROTOCOL and 0<=args.shard<SHARDS,"Wrong protocol or shard")
    cases=m["cases"][args.shard::SHARDS]
    check(len(cases) in (16,17),"Unexpected number per shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    source.RAW_CAP=160*1024**2;source.CNF_CAP=160*1024**2
    source.VARIABLE_CAP=1000000;source.CLAUSE_CAP=4000000
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    save(out/"meta.json",{"protocol":PROTOCOL,"shard":args.shard,
        "case_ids":[c["id"] for c in cases],
        "probe_binary_sha256":digest(args.binary)})
    rows=[]
    for c in cases:
        cnf=out/(c["id"]+".cnf")
        actual=source.download_and_features(c["id"],cnf)
        check(actual["sha256"]==c["sha256"] and actual["features"]==c["features"],
              "Source SHA or feature drift "+c["id"])
        seed=int(c["sha256"][:8],16);started=time.monotonic()
        try:
            r=subprocess.run([str(Path(args.binary).resolve()),"v100_late_plain_force",
                              str(cnf),str(seed)],capture_output=True,
                             text=True,timeout=CAP,preexec_fn=limit_memory)
            stdout=r.stdout
            err=r.stderr[-300:]
            exitcode=r.returncode
            status="OK" if r.returncode==0 else "ERROR"
        except subprocess.TimeoutExpired as e:
            stdout=e.stdout or ""
            if isinstance(stdout,bytes):stdout=stdout.decode("utf-8","replace")
            err="Probe timeout before checkpoint or during parsing"
            exitcode=None;status="NO_TRACE"
        early=[line for line in stdout.splitlines() if line.startswith("DRNAS_EARLY\t")]
        if len(early)==1:
            pairs=dict(f.split("=",1) for f in early[0].split("\t")[1:])
            check(all(k in pairs for k in FIELDS),"Early telemetry incomplete")
            t={k:int(pairs[k]) for k in FIELDS}
            check(0<=t["v90_conflicts_256"]<=256,"Conflict count invalid")
            check(0<=t["v90_lbd2_256"]<=t["v90_lbd4_256"]<=t["v90_learned_256"],
                  "LBD count invalid")
            status="TRACE"
        else:
            check(len(early)==0,"Multiple prefix traces")
            t=None
            if status=="OK":status="ERROR"
        check(status!="ERROR","Probe crashed "+c["id"]+" "+err)
        rows.append({"id":c["id"],"sha256":c["sha256"],"cohort":c["cohort"],
                     "status":status,"telemetry":t,
                     "wall_s":round(time.monotonic()-started,5),
                     "returncode":exitcode,"error":err if status=="NO_TRACE" else ""})
        save(out/"rows.json",rows)
        print("V13_PREFIX",args.shard,c["id"][:12],status,
              t["v90_conflicts_256"] if t else "NA",flush=True)
        cnf.unlink(missing_ok=True)
    check(len(rows)==len(cases),"Missing telemetry rows")
    print("V13_SHARD_PASS",args.shard,len(rows),flush=True)

def paired_outcomes(root103,root11):
    a,b,other=source_manifests(root103,root11)
    result={}
    for name,root,m,prefix,n,cap,ids in (
        ("V103_train",root103,a,"v103-shard",6,15.0,[c["id"] for c in a["cases"]]),
        ("V11_SHA_disjoint",root11,b,"v11-shard",10,30.0,[c["id"] for c in other])):
        ref={c["id"]:c for c in m["cases"]}
        trials=defaultdict(dict)
        for shard in range(n):
            for r in read(Path(root)/"combined"/(prefix+"-"+str(shard))/"results/rows.json"):
                cid=r.get("id",r.get("cnf_id"))
                h=r.get("sha256",r.get("cnf_sha256"))
                check(cid in ref and h==ref[cid]["sha256"],"Result input provenance mismatch")
                check(r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"],
                      "Bad historic outcome")
                k=(r["mode"],r["repetition"])
                check(k not in trials[cid],"Duplicate paired trial")
                trials[cid][k]=2*cap if r["status"]=="TIMEOUT" else float(r["seconds"])
        for cid in ids:
            t=trials[cid]
            check(all((mode,k) in t for mode in ("DRNAS_Legacy","Kissat404") for k in (0,1)),
                  "Missing historic matched trial")
            ks=sum(t["Kissat404",k]<2*cap for k in (0,1))
            ls=sum(t["DRNAS_Legacy",k]<2*cap for k in (0,1))
            group=("Kissat_only" if ks==2 and ls==0 else
                   "DRNAS_only" if ls==2 and ks==0 else
                   "Both" if ls==2 and ks==2 else
                   "Neither" if ls==0 and ks==0 else "Mixed")
            result[cid]={"group":group,"cohort":name,
                         "kissat_par2":statistics.mean(t["Kissat404",k] for k in (0,1)),
                         "drnas_par2":statistics.mean(t["DRNAS_Legacy",k] for k in (0,1))}
    check(len(result)==132,"Outcome cases incomplete")
    return result

def derived(t):
    l=max(1,t["v90_learned_256"]);c=max(1,t["v90_conflicts_256"])
    j=max(1,t["v90_jumps_256"])
    return {
        "LBD2_fraction":t["v90_lbd2_256"]/l,
        "LBD4_fraction":t["v90_lbd4_256"]/l,
        "mean_raw_LBD":t["v90_lbd_sum_256"]/l,
        "propagations_per_conflict":t["v90_props_256"]/c,
        "jump_depth_per_jump":t["v90_jumpdepth_256"]/j,
        "learned_per_conflict":t["v90_learned_256"]/c,
        "conflicts_before_stop":t["v90_conflicts_256"],
        "prefix_cpu_ms":t["cpu_256_ns"]/1e6,
    }
def audit(args):
    manifest=read(args.manifest)
    check(manifest["protocol"]==PROTOCOL and len(manifest["cases"])==132,
          "Wrong audit protocol")
    reference={c["id"]:c for c in manifest["cases"]}
    outcome=paired_outcomes(args.v103,args.v11)
    data=[];binaries=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/("v13-shard-"+str(shard))/"results"
        meta=read(folder/"meta.json")
        expected=manifest["cases"][shard::SHARDS]
        check(meta["shard"]==shard and meta["case_ids"]==[c["id"] for c in expected],
              "Shard input order drift")
        binaries.add(meta["probe_binary_sha256"])
        group=read(folder/"rows.json")
        check(len(group)==len(expected),"Missing telemetry in shard")
        data+=group
    check(len(binaries)==1,"Different probe binary across runners")
    check(len(data)==132 and len({r["id"] for r in data})==132,
          "Missing/duplicate telemetry formula")
    report={"protocol":PROTOCOL,"source_v103_run":41249978820,
            "source_v11_run":41250184539,"total_cases":132,
            "probe_binary_sha256":next(iter(binaries)),
            "cohorts":{},"warnings":manifest["warnings"]}
    for r in data:
        check(r["id"] in reference and reference[r["id"]]["sha256"]==r["sha256"],
              "Telemetry SHA verification failed")
        check(r["status"] in ("TRACE","NO_TRACE") and
              (r["status"]=="TRACE")==(r["telemetry"] is not None),
              "Invalid trace completeness")
    lines=["# V13 — early 256-conflict CaDiCaL diagnostic","",
           "**Retrospective diagnostic only, NOT a new adaptive-solver win.**",
           "CaDiCaL early prefix telemetry; Kissat results are historical solve outcomes.","",
           "| Cohort | CNFs | Trace received | Kissat-only wins | DRNAS-only wins |",
           "|---|---:|---:|---:|---:|"]
    for cohort in ("V103_train","V11_SHA_disjoint"):
        cohort_rows=[r for r in data if r["cohort"]==cohort]
        valid=[r for r in cohort_rows if r["telemetry"] is not None]
        labels=Counter(outcome[r["id"]]["group"] for r in cohort_rows)
        tables={}
        for group in ("Kissat_only","DRNAS_only","Both","Neither","Mixed"):
            matched=[derived(r["telemetry"]) for r in valid if outcome[r["id"]]["group"]==group]
            tables[group]={"trace_n":len(matched),"median":{
                k:(round(statistics.median(x[k] for x in matched),6) if matched else None)
                for k in DERIVED}}
        report["cohorts"][cohort]={"total":len(cohort_rows),"with_telemetry":len(valid),
                                   "outcomes":dict(labels),"group_medians":tables}
        lines.append(f'| {cohort} | {len(cohort_rows)} | {len(valid)} | '
                     f'{labels["Kissat_only"]} | {labels["DRNAS_only"]} |')
    for cohort,record in report["cohorts"].items():
        lines.extend(["",f"## {cohort}","| Winner cohort | Trace N | LBD<=2 | Propagation/conflict | Jump depth |",
                      "|---|---:|---:|---:|---:|"])
        for group,details in record["group_medians"].items():
            vals=details["median"]
            def fmt(key):
                return "n/a" if vals[key] is None else str(vals[key])
            lines.append(f'| {group} | {details["trace_n"]} | {fmt("LBD2_fraction")} | '
                         f'{fmt("propagations_per_conflict")} | {fmt("jump_depth_per_jump")} |')
    save(args.out,report)
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V13_AUDIT_PASS",132,sum(r["status"]=="TRACE" for r in data),flush=True)

def selftest():
    check(len(FIELDS)==12 and len(DERIVED)==8 and SHARDS==8,"Protocol changed")
    example={k:1 for k in FIELDS}
    example.update(v90_conflicts_256=256,v90_learned_256=100,v90_lbd2_256=10,
                   v90_lbd4_256=40,v90_props_256=30000,v90_jumps_256=200)
    check(len(derived(example))==8,"Metric shape incorrect")
    print("V13_SELFTEST_PASS",flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for k in ("v103","v11","out"):f.add_argument("--"+k,required=True)
    r=sub.add_parser("run")
    for k in ("manifest","binary","out"):r.add_argument("--"+k,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("manifest","v103","v11","combined","out","md"):a.add_argument("--"+k,required=True)
    args=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(args),
     "run":lambda:probe(args),"audit":lambda:audit(args)}[args.cmd]()
if __name__=="__main__":main()

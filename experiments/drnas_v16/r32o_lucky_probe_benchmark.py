#!/usr/bin/env python3
"""R32o diagnostic replay of 65 frozen R32n source CNFs.

Single-solver read-only lucky trace, zero policy changes.
NOT a fresh or official holdout: R32n already analyzed these sources.
"""
from __future__ import annotations
import argparse,collections,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r32n_omission_timing_benchmark as n

PROTO="DRNAS-R32O-LUCKY-TRACE-20261103-v1"
MODES=("clean","native_off","full","omit4","omit24","omit48")
REPEATS=3
SHARDS=4
CAP=8
DIRECTIONS={"forward_false","forward_true","backward_false","backward_true"}

def check(ok,msg):
    if not ok: raise RuntimeError("R32O_AUDIT_FAIL "+str(msg))

def trace(output,mode,phases):
    dirrows=[]
    for line in output.splitlines():
        if not line.startswith("c R32O_DIR "): continue
        m=re.fullmatch(
          r"c R32O_DIR call=(\\d+) direction=([a-z_]+) result=(\\d+) probes=(\\d+) failures=(\\d+) first_probe=(-?\\d+) first_conflict=(-?\\d+)",
          line)
        check(m is not None,"Malformed lucky direction trace: "+line[:140])
        call,way,result,probes,failures,first,firstfail=m.groups()
        r=dict(call=int(call),direction=way,result=int(result),
               probes=int(probes),failures=int(failures),
               first_probe=int(first),first_conflict=int(firstfail))
        check(r["direction"] in DIRECTIONS,"Unexpected lucky direction")
        check(r["result"] in (0,10,20),"Invalid lucky return")
        check(r["failures"]<=r["probes"],"More failures than attempts")
        check((r["first_conflict"]==0)==(r["failures"]==0),"First conflict not accounted")
        check((r["first_probe"]==0)==(r["probes"]==0),"First probe not accounted")
        dirrows.append(r)
    calls=[]
    for line in output.splitlines():
        if not line.startswith("c R32O_LUCKY "):continue
        m=re.fullmatch(r"c R32O_LUCKY call=(\\d+) result=(\\d+) shortcut=(none|all_true|all_false)",line)
        check(m is not None,"Malformed lucky call trace "+line[:140])
        call,res,shortcut=m.groups()
        calls.append(dict(call=int(call),result=int(res),shortcut=shortcut))
    if mode=="clean":
        check(not calls and not dirrows,"Clean Kissat emitted new lucky trace")
        return dict(calls=[],directions=[],terminal_winner=None)
    check(len(calls)<=2,"A single solve invoked lucky >2 times")
    check([c["call"] for c in calls]==list(range(1,len(calls)+1)),
          "Missing/duplicate native lucky call")
    bycall=collections.defaultdict(list)
    for r in dirrows:bycall[r["call"]].append(r)
    for c in calls:
        ev=bycall.pop(c["call"],[])
        check(len(ev)<=4,"More than four lucky directions")
        check(len({r["direction"] for r in ev})==len(ev),"Repeated lucky direction")
        check([r["direction"] for r in ev]==list(DIRECTIONS_ORDER[:len(ev)]),
              "Non-forward lucky direction ordering")
        if c["shortcut"]!="none":
            check(c["result"]==10 and not ev,"Shortcut ran lucky direction")
        if any(x["result"] in (10,20) for x in ev):
            check(ev[-1]["result"]==c["result"],
                  "Direction outcome does not match lucky outcome")
    check(not bycall,"Orphan lucky trace direction")
    if phases["terminal"] in ("lucky_early","lucky_late"):
        check(calls and calls[-1]["result"] in (10,20),
              "Lucky terminal phase missing successful direction")
    winner=None
    if calls and calls[-1]["result"] in (10,20):
        ev=[r for r in dirrows if r["call"]==calls[-1]["call"]]
        winner=ev[-1]["direction"] if ev else calls[-1]["shortcut"]
    return dict(calls=calls,directions=dirrows,terminal_winner=winner)

DIRECTIONS_ORDER=("forward_false","forward_true","backward_false","backward_true")

def one(case,source,mode,binaries):
    env=os.environ.copy()
    if mode!="clean":
        env.update(R32B_MODE="off" if mode=="native_off" else "r32k",
                   R32L_TRACE="1",R32M_PHASES="1",R32O_TRACE="1")
        if mode not in ("native_off",):env["R32K_VARIANT"]=mode
    binary=binaries["clean"] if mode=="clean" else binaries["native"]
    t=time.monotonic()
    try:
        r=subprocess.run([str(binary),str(source)],stdout=subprocess.PIPE,
           stderr=subprocess.PIPE,text=True,errors="replace",env=env,timeout=CAP)
        wall=time.monotonic()-t
        check(r.returncode in (10,20),"Kissat returned "+str(r.returncode)+" "+r.stderr[:300])
        status="SAT" if r.returncode==10 else "UNSAT"
        check(status==case["expected"],"Original CNF verdict mismatch "+case["name"])
        if status=="SAT":n.b.sat_check(source,r.stdout)
        output=r.stdout
    except subprocess.TimeoutExpired:
        wall=CAP;status="TIMEOUT";output=""
    probe,final=n.b.parse_native(output)
    if mode=="clean":
        check(not probe and final is None,"Clean native trace detected")
    else:
        check(final and final["status"]==(10 if status=="SAT" else 20),
              "No final native verdict")
        if mode=="native_off":
            check(not probe,"Native off emitted GF2 probes")
        else:
            root=n.b.get_root(probe)
            check(n.b.compare_root(root,source)["status"]=="independent_proof_match",
                  "Root unit original CNF proof failed")
    phases=n.phase_log(output,mode,status,final)
    lucky=trace(output,mode,phases)
    return dict(status=status,wall_s=round(wall,6),
         par2_s=round(wall,6) if status!="TIMEOUT" else 2*CAP,
         terminal=phases["terminal"],lucky=lucky,
         inject_mode=mode,phase_cpu_us={
           p:phases["stages"][p]["cpu_us"] for p in n.PHASES
         } if mode!="clean" else {})

def measure(args):
    frozen=Path(args.inputs)
    m=json.loads((frozen/"manifest.json").read_text())
    check(m["protocol"].startswith("DRNAS-R32N-") and len(m["cases"])==65,
          "R32n frozen original inputs required")
    check(0<=args.shard<SHARDS,"bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={k:Path(getattr(args,k)).resolve() for k in ("clean","native")}
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    meta=dict(protocol=PROTO,shard=args.shard,
       manifest_sha=n.sha(frozen/"manifest.json"),
       binary_sha={k:n.sha(v) for k,v in binaries.items()})
    (out/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for c in m["cases"][args.shard::SHARDS]:
        source=frozen/c["name"]
        check(n.sha(source)==c["sha256"],"Source SHA mismatch")
        for repeat in range(REPEATS):
            order=list(MODES)
            random.Random(int(n.sha((c["sha256"]+str(repeat)+PROTO).encode()),16)).shuffle(order)
            for mode in order:
                record=one(c,source,mode,binaries)
                rows.append(dict(case=c["name"],cohort=c["cohort"],
                                 family=c["family"],repeat=repeat,mode=mode,**record))
                print("R32O_TRIAL",args.shard,c["name"],repeat,mode,
                      record["status"],record["wall_s"],
                      record["terminal"],record["lucky"]["terminal_winner"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32O_SHARD_PASS",args.shard,len(rows),flush=True)

def aggregate(args):
    frozen=Path(args.inputs)
    m=json.loads((frozen/"manifest.json").read_text())
    rows=[];binary_shas=set()
    for shard in range(SHARDS):
        p=Path(args.combined)/("r32o-shard-"+str(shard))/"results"
        meta=json.loads((p/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha"]==n.sha(frozen/"manifest.json"),
              "Shard source manifest drift")
        binary_shas.add(json.dumps(meta["binary_sha"],sort_keys=True))
        sample=json.loads((p/"rows.json").read_text())
        check(len(sample)==sum(REPEATS*len(MODES) for _ in m["cases"][shard::SHARDS]),
              "Shard rows missing")
        rows.extend(sample)
    check(len(binary_shas)==1 and len(rows)==65*REPEATS*len(MODES),
          "Missing exact paired R32o rows")
    grouped=collections.defaultdict(list)
    for r in rows:grouped[r["case"],r["mode"]].append(r)
    for c in m["cases"]:
        for mode in MODES:
            sample=grouped[c["name"],mode]
            check(len(sample)==REPEATS and {r["repeat"] for r in sample}==set(range(REPEATS)),
                  "Missing matched policy attempts")
            check(all(r["status"]==c["expected"] for r in sample),
                  "Original-CNF correctness failure")
    report={"protocol":PROTO,"source_manifest_sha":n.sha(frozen/"manifest.json"),
            "trials":len(rows),"source_count":len(m["cases"]),
            "warning":"R32n 65-source replay, NOT a fresh independent or external SAT holdout."}
    case_rows=[]
    for c in m["cases"]:
        policies={}
        for mode in MODES:
            sample=grouped[c["name"],mode]
            terminal={s["terminal"] for s in sample}
            winners={s["lucky"]["terminal_winner"] for s in sample}
            check(len(terminal)==1 and len(winners)==1,"Unstable exact lucky trace pathway")
            policies[mode]=dict(median_ms=round(statistics.median(
              r["par2_s"] for r in sample)*1000,3),
              total_s=round(sum(r["par2_s"] for r in sample),6),
              terminal=next(iter(terminal)),winner=next(iter(winners)))
        case_rows.append(dict(case=c["name"],cohort=c["cohort"],
                              family=c["family"],policies=policies))
    summary={}
    for label,cases in (("all",case_rows),
                         ("prior_development",[x for x in case_rows if x["cohort"]=="prior_development"]),
                         ("R32n_replayed_60",[x for x in case_rows if x["cohort"]!="prior_development"])):
        vals={}
        for mode in MODES:
            vals[mode]=dict(total_wall_s=round(sum(x["policies"][mode]["total_s"] for x in cases),6),
                 terminal= dict(collections.Counter(x["policies"][mode]["terminal"] for x in cases)),
                 winners=dict(collections.Counter(str(x["policies"][mode]["winner"]) for x in cases)))
        off=vals["native_off"]["total_wall_s"]
        for mode in MODES[2:]:
            vals[mode]["delta_pct"]=round(100*(vals[mode]["total_wall_s"]/off-1),4)
        vals["full_faster_case_count"]=sum(
            x["policies"]["full"]["median_ms"]<x["policies"]["native_off"]["median_ms"] for x in cases)
        vals["full_slower_case_count"]=sum(
            x["policies"]["full"]["median_ms"]>x["policies"]["native_off"]["median_ms"] for x in cases)
        summary[label]=vals
        print("R32O_SUMMARY",label,json.dumps(vals,sort_keys=True),flush=True)
    transitions=[]
    for x in case_rows:
        off=x["policies"]["native_off"];full=x["policies"]["full"]
        if off["terminal"]!=full["terminal"] or off["winner"]!=full["winner"]:
            transitions.append(dict(case=x["case"],cohort=x["cohort"],
                off_phase=off["terminal"],full_phase=full["terminal"],
                off_winner=off["winner"],full_winner=full["winner"],
                off_ms=off["median_ms"],full_ms=full["median_ms"]))
    report.update(summary=summary,per_case=case_rows,transitions=transitions,rows=rows)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    md=["# R32o — native lucky probe causality, R32n original-source replay","",
        "Pinned one-process Kissat; same policy as R32n; read-only lucky function instrumentation.",
        "65 R32n source CNFs, three serial repeats, six policies, 1170 trials.",
        "**Not a new holdout**: the 60 so-called new formulas were used in R32n first.","",
        "## Wall timing (s)","",
        "| Cohort | Native OFF | Full certified | Delta % | Full faster source medians | Full slower source medians |",
        "|---|---:|---:|---:|---:|---:|"]
    for k,v in summary.items():
        off=v["native_off"]["total_wall_s"];full=v["full"]
        md.append(f'| {k} | {off:.6f} | {full["total_wall_s"]:.6f} | {full["delta_pct"]:+.3f}% | {v["full_faster_case_count"]} | {v["full_slower_case_count"]} |')
    md+=["","## Phase or winning lucky direction transitions","","| CNF | OFF phase | FULL phase | OFF winner | FULL winner | OFF ms | FULL ms |",
          "|---|---|---|---|---|---:|---:|"]
    for t in transitions:
        md.append(f'| {t["case"]} | {t["off_phase"]} | {t["full_phase"]} | {t["off_winner"]} | {t["full_winner"]} | {t["off_ms"]} | {t["full_ms"]} |')
    md+=["","R32O_AUDIT_PASS "+str(len(rows))+" serial trials, "+str(len(transitions))+" changed lucky paths."]
    Path(args.report).write_text("\n".join(md)+"\n")
    print("R32O_AUDIT_PASS",len(rows),"serial runs",len(transitions),"path changes",flush=True)

def main():
    ap=argparse.ArgumentParser();subs=ap.add_subparsers(dest="command",required=True)
    p=subs.add_parser("measure")
    for x in ("inputs","clean","native","outdir"):p.add_argument("--"+x,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=subs.add_parser("aggregate")
    for x in ("inputs","combined","output","report"):p.add_argument("--"+x,required=True)
    a=ap.parse_args()
    if a.command=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()

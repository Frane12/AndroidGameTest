#!/usr/bin/env python3
"""R32h prospective, paired restart-sham vs certified-root-unit timing ablation.
Reuses SHA-frozen R32g synthetic CNFs and pinned native binaries. No solver edits.
"""
import argparse, collections, csv, hashlib, json, os, random, re, statistics
import tempfile, time
from pathlib import Path
import r32g_cooperative_relay_benchmark as g
import r31_consistent_gf2_test as r31

MODES=("race","observe","sham0","units0","sham20","units20","sham50","units50")
TIMING={"sham0":("sham",0.),"units0":("units",0.),
        "sham20":("sham",.020),"units20":("units",.020),
        "sham50":("sham",.050),"units50":("units",.050)}
MANIFEST_SHA="627598d18d9e0865ec34854cbfac137383bdeb4ba3ef11c00e6be3e5a94d4b97"
SOURCE_SHA="4059e45d1cb2c72c3844a3b0cf20ee11985f7614"
RUN=41642371038
PROTO="DRNAS-R32H-PAIRED-RESTART-UNIT-CAUSAL-20261103-v1"
CAP=8.0
REPS=3
SHARDS=4

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(x,msg):
    if not x: raise RuntimeError("R32H_AUDIT_FAILURE: "+str(msg))
def manifest(folder):
    p=Path(folder)/"manifest.json"
    check(sha(p)==MANIFEST_SHA,"source manifest SHA drift")
    m=json.loads(p.read_text())
    check(m["protocol"]==g.PROTO and len(m["cases"])==36,"unexpected R32g source")
    check(len({c["sha256"] for c in m["cases"]})==36,"source duplicate SHA")
    for c in m["cases"]:
        f=Path(folder)/c["name"]
        check(f.is_file() and sha(f)==c["sha256"],"CNF SHA drift "+c["name"])
    return m

def dual(case,original,mode,binaries,cores,certified):
    if mode=="race":
        z=g.parallel(case,original,"independent_race",binaries,cores,certified)
        return dict(status=z["status"],par2=z["par2"],wall_s=z["wall_s"],
          cpu_s=z["cpu_s"],winner=z["winner"],message_seen=False,
          message_s=None,message_units=0,restarted=False,restart_s=None)
    kind,delay=TIMING.get(mode,("observe",None))
    start_cpu=g.f.cpu_usage()
    begin=time.monotonic()
    pending=None;message_at=None;restarted=False;restart_at=None
    with tempfile.TemporaryDirectory(prefix="r32h-") as tmp:
        folder=Path(tmp)
        logs={"native_off":folder/"off.log","r32e_active":folder/"active.log"}
        tasks={"native_off":g.start(binaries["native"],original,"native_off",
                                    cores[0],logs["native_off"]),
               "r32e_active":g.start(binaries["native"],original,"r32e_active",
                                      cores[1],logs["r32e_active"])}
        stream=open(logs["r32e_active"],"r",encoding="utf-8",errors="replace")
        buffered=""
        try:
            while time.monotonic()-begin < CAP:
                winner=next((k for k in ("native_off","r32e_active")
                             if tasks[k].poll() is not None),None)
                if winner is not None:
                    end=time.monotonic()
                    code=tasks[winner].returncode
                    for key,task in tasks.items():
                        if key!=winner: g.reap(task)
                    cpu=g.f.cpu_usage()-start_cpu
                    status,_,_=g.audit_status(case,original,
                                   logs[winner].read_text(),code,winner)
                    duration=round(end-begin,6)
                    return dict(status=status,par2=duration,wall_s=duration,
                       cpu_s=round(cpu,6),winner=winner,
                       message_seen=pending is not None,message_s=message_at,
                       message_units=len(pending or []),restarted=restarted,
                       restart_s=restart_at)
                added=stream.read()
                if added:
                    buffered+=added
                    while "\n" in buffered:
                        line,buffered=buffered.split("\n",1)
                        if not line.startswith("c R32C_INJECTED_LITS "): continue
                        hit=re.fullmatch(
                           r"c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)",
                           line)
                        check(hit is not None,"malformed producer root message")
                        lits=[int(v) for v in hit.group(2).split(",")]
                        check(len(lits)==int(hit.group(1))
                              and 0<len(lits)<=12
                              and len(lits)==len(set(lits))
                              and set(lits).issubset(certified),
                              "uncertified signed producer root unit")
                        if pending is not None:
                            check(pending==lits,"inconsistent repeated message")
                        else:
                            pending=lits
                            message_at=round(time.monotonic()-begin,6)
                if (kind!="observe" and pending and not restarted
                        and time.monotonic()-begin>=delay
                        and tasks["native_off"].poll() is None):
                    g.reap(tasks["native_off"])
                    src=original
                    if kind=="units":
                        src=folder/"augmented.cnf"
                        g.make_augmented(original,pending,src)
                    logs["native_off"]=folder/"restart.log"
                    tasks["native_off"]=g.start(binaries["native"],src,
                       "native_off",cores[0],logs["native_off"])
                    restarted=True
                    restart_at=round(time.monotonic()-begin,6)
                time.sleep(g.POLL_S)
            end=time.monotonic()
            for task in tasks.values():g.reap(task)
            return dict(status="TIMEOUT",par2=2*CAP,
                wall_s=round(end-begin,6),
                cpu_s=round(g.f.cpu_usage()-start_cpu,6),
                winner=None,message_seen=pending is not None,
                message_s=message_at,message_units=len(pending or []),
                restarted=restarted,restart_s=restart_at)
        finally:
            stream.close()
            for task in tasks.values():
                if task.poll() is None:g.reap(task)

def measure(args):
    m=manifest(args.inputs)
    check(args.shard in range(SHARDS),"bad shard")
    binaries={k:Path(getattr(args,k)).resolve() for k in ("clean","native")}
    cores=sorted(os.sched_getaffinity(0))
    check(len(cores)>=2,"need two allocated cores")
    cores=cores[:2]
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    meta=dict(protocol=PROTO,shard=args.shard,source_run=RUN,
         source_sha=SOURCE_SHA,manifest_sha=MANIFEST_SHA,
         runner=os.environ.get("RUNNER_NAME","local"),
         run_id=os.environ.get("GITHUB_RUN_ID","local"),
         run_sha=os.environ.get("GITHUB_SHA","local"),
         cpu_cores=cores,binaries={k:sha(v) for k,v in binaries.items()})
    (folder/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in m["cases"][args.shard::SHARDS]:
        original=Path(args.inputs)/case["name"]
        root,_=r31.structure(original)
        proven={int(u["literal"]) for u in root["units"]}
        check(root["signal"]=="CONSISTENT_EXTRA_UNITS" or not proven,
              "root literal under unsupported signal")
        for rep in range(REPS):
            seed=int(hashlib.sha256(
                (case["sha256"]+":"+str(rep)+":R32H").encode()
                ).hexdigest(),16)
            modes=list(MODES);random.Random(seed).shuffle(modes)
            for mode in modes:
                row=dual(case,original,mode,binaries,cores,proven)
                check(row["status"] in (case["expected"],"TIMEOUT"),
                      "incorrect solver verdict")
                check(not row["restarted"] or (
                      mode in TIMING and row["message_seen"]
                      and 0<row["message_units"]<=12),
                      "unproven intervention")
                rows.append(dict(case=case["name"],sha256=case["sha256"],
                       family=case["family"],cohort=case["cohort"],
                       expected=case["expected"],repeat=rep,mode=mode,
                       seed=str(seed),root_units=len(proven),**row))
                print("R32H_TRIAL",args.shard,case["name"],rep,mode,
                      row["status"],row["par2"],"restart",row["restarted"],
                      flush=True)
            (folder/"rows.json").write_text(json.dumps(rows)+"\n")
    check(len(rows)==len(m["cases"][args.shard::SHARDS])*REPS*len(MODES),
          "missing shard trials")

def aggregate(args):
    m=manifest(args.inputs)
    base={c["name"]:c for c in m["cases"]}
    rows=[];binary_hashes=set();provenance=[]
    for shard in range(SHARDS):
        folder=Path(args.combined)/("r32h-shard-"+str(shard))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and meta["protocol"]==PROTO
              and meta["manifest_sha"]==MANIFEST_SHA
              and meta["source_sha"]==SOURCE_SHA and meta["source_run"]==RUN,
              "shard provenance mismatch")
        provenance.append(meta)
        binary_hashes.add(json.dumps(meta["binaries"],sort_keys=True))
        part=json.loads((folder/"rows.json").read_text())
        check(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
              "incomplete shard")
        rows.extend(part)
    check(len(binary_hashes)==1,"solver binary mismatches")
    check(len(rows)==864,"expected 864 real trials")
    keyed=collections.defaultdict(dict);identities=set()
    for r in rows:
        key=(r["case"],r["repeat"],r["mode"])
        check(key not in identities,"duplicate attempt")
        identities.add(key)
        check(r["case"] in base and r["sha256"]==base[r["case"]]["sha256"],
              "formula identity mismatch")
        check(r["status"] in (base[r["case"]]["expected"],"TIMEOUT"),
              "SAT/UNSAT disagreement")
        check(abs(r["par2"]-(16.0 if r["status"]=="TIMEOUT"
                              else r["wall_s"]))<.00001,
              "incorrect PAR2")
        check(not r["restarted"] or (r["message_seen"]
              and r["mode"] in TIMING and r["message_units"]>0),
              "restart without proof")
        keyed[(r["case"],r["repeat"])][r["mode"]]=r
    check(len(keyed)==108 and all(set(x)==set(MODES) for x in keyed.values()),
          "paired mode incompleteness")
    baseline=sum(x["observe"]["par2"] for x in keyed.values())
    summary={}
    for mode in MODES:
        selected=[x for x in rows if x["mode"]==mode]
        total=sum(x["par2"] for x in selected)
        summary[mode]=dict(n=len(selected),par2_s=round(total,6),
             change_vs_observe_pct=round(100*(total-baseline)/baseline,4),
             cpu_s=round(sum(x["cpu_s"] for x in selected),6),
             restarts=sum(x["restarted"] for x in selected),
             messages=sum(x["message_seen"] for x in selected),
             timeouts=sum(x["status"]=="TIMEOUT" for x in selected))
    rng=random.Random(32026);bycase={}
    for case in base:
        subset=[p for (name,rep),p in keyed.items() if name==case]
        bycase[case]={mode:statistics.median(p[mode]["par2"]
                   for p in subset) for mode in MODES}
    ci={}
    for mode in MODES:
        if mode=="observe":continue
        draws=[]
        names=list(base)
        for _ in range(2000):
            sample=[rng.choice(names) for _ in names]
            before=sum(bycase[n]["observe"] for n in sample)
            after=sum(bycase[n][mode] for n in sample)
            draws.append(100*(before-after)/before)
        draws.sort()
        ci[mode]=[round(draws[49],3),round(draws[1949],3)]
    report=dict(protocol=PROTO,source_run=RUN,source_sha=SOURCE_SHA,
       frozen_manifest_sha256=MANIFEST_SHA,original_formulas=36,
       new_formula_sha256_count=0,attempts=len(rows),meta=provenance,
       summary=summary,bootstrap_95pct_gain_vs_observe=ci,rows=rows,
       warnings=[
        "Reuse 36 synthetic R32g original CNFs, not official or previously unseen",
        "Real new 864 trials; do not ingest as 36 new formula identities",
        "Observe reads/validates IPC, no restart; SHAM restarts original CNF",
        "UNITS restarts OFF worker with only independently certified original root units",
        "Source-to-restart delays 0/20/50ms; all modes run on pinned native binaries",
        "No learnt-clause sharing or in-process CDCL state transfer",
        "No LRAT certificates for UNSAT; generator labels and SAT witnesses only",
        "Formula-level bootstrap, not a claim of universal SAT speedup"])
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    with open(args.paired,"w",newline="") as fp:
        wr=csv.DictWriter(fp,fieldnames=[
             "case","sha256","family","cohort","repeat","mode","par2",
             "cpu_s","observe_par2","gain_s","status","message_seen",
             "restarted","message_s","restart_s","message_units","seed"])
        wr.writeheader()
        for (name,rep),pair in sorted(keyed.items()):
            for mode in MODES:
                r=pair[mode]
                wr.writerow({**{k:r[k] for k in
                     ("sha256","family","cohort","repeat","mode","par2",
                     "cpu_s","status","message_seen","restarted","message_s",
                     "restart_s","message_units","seed")},
                     "case":name,"observe_par2":pair["observe"]["par2"],
                     "gain_s":pair["observe"]["par2"]-r["par2"]})
    lines=["# R32h controlled relay ablation",
       "36 reused synthetic CNFs x 3 repeats x 8 randomized-order strategies = 864 real trials.",
       "Positive change means SLOWER relative to observe (which reads IPC but never restarts).",
       "| Mode | PAR2 total s | Delta vs observe | CPU s | Actual restarts | Timeouts |",
       "|---|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        s=summary[mode]
        lines.append(f"| {mode} | {s['par2_s']:.4f} | "
           f"{s['change_vs_observe_pct']:+.2f}% | {s['cpu_s']:.4f} | "
           f"{s['restarts']} | {s['timeouts']} |")
    lines.extend(["","95% formula-level bootstrap gain vs observe (positive faster):"])
    for mode,v in ci.items():
        lines.append(f"- {mode}: [{v[0]:+.2f}%, {v[1]:+.2f}%]")
    lines.extend(["","SHAM vs UNITS at matched delay separates restart overhead from "
                   "net benefit of the independently certified units.",
                   "SAT witnesses checked; UNSAT proof certification unavailable.",
                   "No new formula SHA identities. Do not infer universal speedup."])
    Path(args.markdown).write_text("\n".join(lines)+"\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(8,6))
        for mode in ("sham20","units20","sham50","units50"):
            ax.scatter([p["observe"]["par2"] for p in keyed.values()],
                       [p[mode]["par2"] for p in keyed.values()],
                       alpha=.4,s=18,label=mode)
        high=max([1]+[r["par2"] for r in rows])
        ax.plot([0,high],[0,high],"--")
        ax.set(xlabel="Observe PAR-2 s",ylabel="Policy PAR-2 s",
               title="R32h paired causal ablation")
        ax.legend();fig.tight_layout();fig.savefig(args.scatter,dpi=140)
        plt.close(fig)
    except ImportError:
        print("NO_MATPLOTLIB")
    print("R32H_AUDIT_PASS",len(rows),"trials",len(base),"reused SHA")
    print("\n".join(lines))

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="task",required=True)
    p=sub.add_parser("measure")
    for s in ("inputs","clean","native","output"):p.add_argument("--"+s,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=sub.add_parser("aggregate")
    for s in ("inputs","combined","output","paired","markdown","scatter"):
        p.add_argument("--"+s,required=True)
    args=ap.parse_args()
    if args.task=="measure": measure(args)
    else: aggregate(args)
if __name__=="__main__":main()

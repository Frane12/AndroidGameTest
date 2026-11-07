#!/usr/bin/env python3
"""R87 frozen feedback-cadence DEVELOPMENT replay of R85's 12 SHA-frozen 2025 originals.

Tests adaptive feedback and fixed 4/16/64/256 scans with the same source-certified native
reason logic vs pinned clean Kissat. R85's sources were already observed:
R87 is not an unseen holdout and cannot confirm generalized speedups.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, re, subprocess, time
from pathlib import Path
import r85_fresh_abcd as old

PROTO="DRNAS-R87-FROZEN-UTILITY-GATED-DEVELOPMENT-REPLAY-20261104-v1"
MODES=("clean","active4","active16","active64","active256","adaptive")
SCAN={"active4":4,"active16":16,"active64":64,"active256":256,"adaptive":16}
REPS,SHARDS,CAP=2,12,35.0
BEGIN=re.compile(r"^c R84_BEGIN active=(\d+) interval=(\d+) prepared=(\d+)$",re.M)
ADAPT=re.compile(r"^c R87_MODE dynamic=(\d+) initial_interval=(\d+) window_scans=(\d+)$",re.M)
SWITCH=re.compile(r"^c R87_SWITCH scans=(\d+) from=(\d+) to=(\d+)",re.M)

def ck(ok,msg):
    if not ok:raise RuntimeError("R87_FAIL_CLOSED "+str(msg))
def sha(p):return old.sha(p)
def save(p,obj):Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def read_manifest(root):
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==old.PROTO and len(mf["cases"])==SHARDS,
       "not the locked R85 source cohort")
    ck(sum(c["structural_xor_positive"] for c in mf["cases"])==4,
       "R85 4-XOR/8-control design drift")
    ck(len({c["sha256"] for c in mf["cases"]})==SHARDS,"source SHA duplicate")
    return mf

def trial(source,case,mode,clean,native,proof_cache):
    start=time.monotonic();env=os.environ.copy()
    if mode!="clean":
        env.update(R32B_MODE="r32u",R32U_ACTIVE="1",
                   R84_SCAN_EVERY=str(SCAN[mode]),R85_DIVERSE="0",
                   R85_CAP="64",R32S_PASSIVE_TRACE="0",
                   R87_ADAPT="1" if mode=="adaptive" else "0")
    try:
        p=subprocess.run([str(clean if mode=="clean" else native),str(source)],
                         env=env,capture_output=True,text=True,errors="replace",timeout=CAP)
        ck(p.returncode in (10,20),"solver crashed "+str(p.returncode)+" "+p.stderr[-400:])
        stdout=p.stdout
        answer="SAT" if p.returncode==10 else "UNSAT"
    except subprocess.TimeoutExpired as e:
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        answer="TIMEOUT"
    wall=time.monotonic()-start
    if answer=="SAT":old.r32p.verify_sat_witness(source,stdout)
    if mode!="clean":
        matched=BEGIN.findall(stdout)
        ck(len(matched)==1 and int(matched[0][0])==1 and
           int(matched[0][1])==SCAN[mode],
           "native scan cadence was not the fixed requested interval")
    if mode!="clean":
        mode_match=ADAPT.findall(stdout)
        ck(len(mode_match)==1 and int(mode_match[0][0])==int(mode=="adaptive")
           and int(mode_match[0][1])==SCAN[mode]
           and int(mode_match[0][2])==128,"R87 adaptive mode/initial interval incorrect")
    changed=SWITCH.findall(stdout) if mode=="adaptive" else []
    diag=old.parse_counts(stdout,"clean" if mode=="clean" else "B_active16",source,proof_cache)
    return dict(answer=answer if wall<=CAP else "TIMEOUT",
        wall_s=round(min(wall,CAP),6),
        par2_s=round(wall if answer!="TIMEOUT" and wall<=CAP else 2*CAP,6),
        telemetry=diag,adaptive_logged_switches=len(changed),
        sat_witness_checked=(answer=="SAT"),
        independent_unsat_proof_checked=False)

def measure(args):
    root=Path(args.sources).resolve();mf=read_manifest(root)
    ck(0<=args.shard<SHARDS,"shard")
    c=mf["cases"][args.shard]
    source=root/c["filename"]
    ck(sha(source)==c["sha256"],"CNF SHA mismatch")
    binaries=Path(args.compiled).resolve()
    p=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],cwd=binaries,
                     capture_output=True,text=True)
    ck(p.returncode==0,"solver pin mismatch "+p.stderr[-250:])
    clean,native=binaries/"clean",binaries/"native-r87"
    ck(all(x.is_file() and os.access(x,os.X_OK) for x in (clean,native)),
       "missing pinned executables")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    rows=[];proof_cache={}
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(int(hashlib.sha256(
            (PROTO+c["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
        for mode in modes:
            result=trial(source,c,mode,clean,native,proof_cache)
            row=dict(sha256=c["sha256"],gbd=c["gbd"],group=c["group"],rep=rep,
                     mode=mode,runner=os.environ.get("RUNNER_NAME",""),
                     commit=os.environ.get("GITHUB_SHA",""),
                     run_id=os.environ.get("GITHUB_RUN_ID",""),**result)
            rows.append(row)
            save(out/"r87-shard.json",dict(protocol=PROTO,shard=args.shard,
                 source_manifest_sha=sha(root/"manifest.json"),
                 binary_sha=dict(clean=sha(clean),native_r87=sha(native)),
                 rows=rows))
            d=result["telemetry"]
            print("R87_TRIAL",json.dumps(dict(gbd=c["gbd"],group=c["group"],
                rep=rep,mode=mode,answer=result["answer"],par2_s=result["par2_s"],
                rows=d["source_rows"],
                scans=(d["last"] or {}).get("scans",0),
                attached=(d["last"] or {}).get("attached",0),
                first_uip=(d["last"] or {}).get("first_uip_reason_uses",0))),flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete matched trial")
    print("R87_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    root=Path(args.sources);mf=read_manifest(root)
    cases=mf["cases"]
    allrows=[];pins=set()
    for i,c in enumerate(cases):
        ck(sha(root/c["filename"])==c["sha256"],"CNF original bytes drift")
        p=Path(args.combined)/f"r87-shard-{i}"/"results"/"r87-shard.json"
        ck(p.exists(),"missing shard "+str(i))
        j=json.loads(p.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==i and
           j["source_manifest_sha"]==sha(root/"manifest.json"),"shard provenance")
        ck(len(j["rows"])==REPS*len(MODES),"incomplete shard")
        pins.add(json.dumps(j["binary_sha"],sort_keys=True))
        for rep in range(REPS):
            pair=[r for r in j["rows"] if r["rep"]==rep]
            ck(len(pair)==len(MODES) and {r["mode"] for r in pair}==set(MODES),
               "missing or duplicate method")
            ck(all(r["sha256"]==c["sha256"] and r["gbd"]==c["gbd"]
                   and r["runner"] and r["commit"] and r["run_id"] for r in pair),
               "run/runner/commit/source metadata failure")
            ck(len({r["answer"] for r in pair if r["answer"]!="TIMEOUT"})<=1,
               "solver verdict contradiction")
            ck(all(r["telemetry"]["verified"] for r in pair),"GF2 source proof failed")
        allrows.extend(j["rows"])
    ck(len(pins)==1 and len(allrows)==SHARDS*REPS*len(MODES),
       "binary mismatch or partial benchmark")
    summaries={}
    grouped={}
    for group,source_set in [
      ("ALL",{c["sha256"] for c in cases}),
      ("XOR",{c["sha256"] for c in cases if c["structural_xor_positive"]}),
      ("CONTROL",{c["sha256"] for c in cases if not c["structural_xor_positive"]})]:
        rs=[r for r in allrows if r["sha256"] in source_set]
        grouped[group]={}
        for mode in MODES:
            rr=[r for r in rs if r["mode"]==mode]
            grouped[group][mode]=dict(trials=len(rr),
                solved=sum(r["answer"]!="TIMEOUT" for r in rr),
                par2_s=round(sum(r["par2_s"] for r in rr),6),
                reason_uses=sum((r["telemetry"]["last"] or {}).get("first_uip_reason_uses",0) for r in rr),
                attaches=sum((r["telemetry"]["last"] or {}).get("attached",0) for r in rr),
                scans=sum((r["telemetry"]["last"] or {}).get("scans",0) for r in rr))
    paired=[]
    for c in cases:
        rr=[r for r in allrows if r["sha256"]==c["sha256"]]
        paired.append({mode:sum(r["par2_s"] for r in rr if r["mode"]==mode)/REPS
                       for mode in MODES})
    bootstrap={}
    rng=random.Random(871104)
    for mode in MODES[1:]:
        diffs=[x["clean"]-x[mode] for x in paired]
        draws=sorted(sum(diffs[rng.randrange(len(diffs))]
                      for _ in range(len(diffs)))/len(diffs) for __ in range(2000))
        bootstrap[mode]=dict(mean_saved_s_per_source=round(sum(diffs)/len(diffs),6),
                             bootstrap_95ci_s=[round(draws[49],6),round(draws[1949],6)])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    report=dict(protocol=PROTO,status="PASS_DEVELOPMENT_REPLAY_NOT_HOLDOUT",
                source_count=SHARDS,total_trials=len(allrows),
                source_manifest_sha256=sha(root/"manifest.json"),
                binary_sha256=json.loads(next(iter(pins))),
                groups=grouped,paired_source_bootstrap=bootstrap,rows=allrows,
                limitations=[
                    "R87 is DEVELOPMENT replay of R85's 12 already-observed real SAT2025 originals.",
                    "Only scheduling of native scans differs; source-certified GF2 reasoning unchanged.",
                    "Adaptive interval based only on previous attached/first-UIP usage, not labels or timing.",
                    "XOR-positive group preselected, NOT representative of whole official SAT Competition.",
                    "Single core 35s cap with 70s PAR2 timeout penalty, not official competition.",
                    "UNSAT proof not independently replayed; SAT original witnesses validated.",
                    "Any gain requires a genuinely unseen SHA-disjoint holdout before claiming replication."
                ])
    save(out/"r87-final.json",report)
    lines=["# R87 scan-budget development replay",
      "", "12 previously observed original 2025 CNFs (4 XOR/8 controls).",
      "2 repeats x 6 methods = 144 paired trials, 35s cap, PAR2 timeout 70s.",
      "**Development replay, NOT a new unseen holdout.**",
      "", "| Group | Mode | Solved | PAR2 s | Scans | 1-UIP reason uses |",
      "|---|---|---:|---:|---:|---:|"]
    for group,modes in grouped.items():
        for m,s in modes.items():
            lines.append(f"| {group} | {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} | {s['scans']} | {s['reason_uses']} |")
    lines+=["","## Source-paired bootstrap (seconds saved per formula; positive favors R87)"]
    for m,s in bootstrap.items():lines.append(f"- {m}: {s}")
    lines+=["","## Limitations"]+["- "+s for s in report["limitations"]]
    (out/"r87-final.md").write_text("\n".join(lines)+"\n")
    print("R87_FINAL_REPLAY_AUDIT_PASS",len(allrows),json.dumps(grouped["ALL"]),flush=True)

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest="cmd",required=True)
    subs.add_parser("selftest")
    m=subs.add_parser("measure")
    for s in ("sources","compiled","out"):m.add_argument("--"+s,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=subs.add_parser("audit")
    for s in ("sources","combined","out"):a.add_argument("--"+s,required=True)
    v=p.parse_args()
    if v.cmd=="selftest":
        ck(len(MODES)==6 and SHARDS==12 and CAP==35,"protocol changed")
        print("R87_REPLAY_DESIGN_SELFTEST_PASS")
    elif v.cmd=="measure":measure(v)
    else:audit(v)
if __name__=="__main__":main()

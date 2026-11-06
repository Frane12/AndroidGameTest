#!/usr/bin/env python3
"""R192 precommitted three-window CDCL trajectory benchmark.

This is hypothesis testing, not proof of faster general SAT.
Seven arms on 102 *identical* R190/R191 frozen source CNFs, twice.
CaDiCaL 2.1 pinned. R192 windows are 3x128-conflict; all runtime is counted.
IPASIR learner reports clause length, not LBD or full propagation counts.
When restarting the solver, learned clauses are discarded by design.
25 previously seen real formulas are not a blind holdout.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,re,subprocess,time
import r191_early_cdcl_feedback as old

PROTO="DRNAS-R192-3x128-TRAJECTORY-CAUSAL-ABLATION-v1"
ROOT=pathlib.Path("r192")
FROZEN=ROOT/"frozen"
MANIFEST_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
SHARDS=8
REPS=2
MODES=("default","sat","windows_continue","windows_shadow",
       "windows_restart_default","windows_restart_sat","windows_adaptive")

def need(x,msg):
    if not x:raise RuntimeError("R192_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def verify():
    need(sha(FROZEN/"manifest.json")==MANIFEST_SHA,"original manifest sha drift")
    d=read(FROZEN/"manifest.json")
    need(d["protocol"]=="DRNAS-R190-GENERAL-CDCL-FROZEN-STRUCTURAL-ROUTER-v1"
         and len(d["cases"])==102,"original manifest invalid")
    for c in d["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"original CNF mismatch")
    return d["cases"]

def selftest():
    need(len(MODES)==7 and len(set(MODES))==7,"bad distinct arms")
    probe="R192_WINDOW index=0 status=UNKNOWN seconds=0.01 learned=23 short3=7 binary=4 mean_len=4.2 active_before=100 active_after=98"
    m=re.search(r"R192_WINDOW index=(\d+) status=(\w+) seconds=([0-9.]+) learned=(\d+) short3=(\d+) binary=(\d+) mean_len=([0-9.]+) active_before=(\d+) active_after=(\d+)",probe)
    need(m is not None and int(m[4])==23,"window parser invalid")
    print("R192_SELFTEST_PASS",flush=True)

def native(binary,source,cap,mode):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(source),str(cap),mode],
             capture_output=True,timeout=cap+3,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed=time.perf_counter()-start,
                    model={},stats={},windows=[],restarted=0,suggested="WATCHDOG")
    elapsed=time.perf_counter()-start
    raw=p.stdout.decode(errors="replace")
    err=p.stderr.decode(errors="replace")
    need(p.returncode==0,"native failure: "+err[-900:])
    m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
    need(m is not None,"missing native result: "+raw[-500:])
    state=m[1]
    pm=re.search(r"^R192_POLICY suggested=(\S+) restarted=(\d+) windows=(\d+)$",
                 raw,re.M)
    need(pm is not None,"missing decision telemetry")
    windows=[]
    for w in re.finditer(
        r"^R192_WINDOW index=(\d+) status=(\w+) seconds=([0-9.]+) "
        r"learned=(\d+) short3=(\d+) binary=(\d+) mean_len=([0-9.]+) "
        r"active_before=(\d+) active_after=(\d+)$",raw,re.M):
        win=dict(index=int(w[1]),status=w[2],seconds=float(w[3]),
                 learned=int(w[4]),short3=int(w[5]),binary=int(w[6]),
                 mean_len=float(w[7]),active_before=int(w[8]),
                 active_after=int(w[9]))
        need(win["short3"]<=win["learned"] and
             win["binary"]<=win["short3"],"window telemetry invalid")
        windows.append(win)
    if mode.startswith("windows_"):
        need(1<=len(windows)<=3,"expected one to three probed windows")
    else:need(not windows,"baseline unexpectedly probed")
    need(len(windows)==int(pm[3]) and
         [x["index"] for x in windows]==list(range(len(windows))),
         "probe index/count mismatch")
    model={}
    if state=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "native model inconsistent")
                    model[abs(lit)]=lit>0
    return dict(status=state,elapsed=elapsed,model=model,
       stats=old.old.stats(raw),windows=windows,
       restarted=int(pm[2]),suggested=pm[1])

def trial(c,mode,rep,binary):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"per trial source hash mismatch")
    cap=float(c["cap_s"])
    start=time.perf_counter()
    r=native(binary,path,cap,mode)
    elapsed=time.perf_counter()-start
    status=r["status"]
    if elapsed>=cap:status="TIMEOUT"
    proof="CAP" if status=="TIMEOUT" else "CADICAL_UNSAT_NO_INDEPENDENT_LRAT"
    if status=="SAT":
        _,clauses=old.old.gf.dimacs(path)
        old.old.gf.sat_check(clauses,r["model"])
        proof="SAT_WITNESS_VERIFIED_ON_ORIGINAL"
    if status!="TIMEOUT" and c["expected"]!="UNKNOWN":
        need(status==c["expected"],"expected known answer mismatch")
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
      cohort=c["cohort"],mode=mode,rep=rep,cap_s=cap,
      status=status,elapsed_s=round(elapsed,6),
      par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
      learned_windows=r["windows"],window_s=round(sum(w["seconds"] for w in r["windows"]),6),
      restarted=r["restarted"],suggested=r["suggested"],
      proof=proof,**r["stats"])

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and binary.is_file(),"bad shard/binary")
    rows=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                rows.append(r)
                save(ROOT/f"shard-{idx}.json",rows)
                print("R192_TRIAL",json.dumps({k:r[k] for k in
                   ("id","cohort","mode","rep","status","elapsed_s",
                    "window_s","restarted","suggested")},sort_keys=True),
                   flush=True)
    need(len(rows)==len(cases[idx::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R192_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=verify()
    rows=[]
    for i in range(SHARDS):
        p=read(ROOT/f"shard-{i}.json")
        need(len(p)==len(cases[i::SHARDS])*REPS*len(MODES),"shard incomplete")
        rows+=p
    need(len(rows)==102*REPS*len(MODES)==1428,"wrong total attempts")
    by=collections.defaultdict(list)
    original={c["sha256"]:c for c in cases}
    for r in rows:
        need(r["sha256"] in original and
             r["id"]==original[r["sha256"]]["id"],"paired sha drift")
        reference=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-reference)<1e-5,"PAR2 accounting mismatch")
        by[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            sample=by[c["sha256"],rep]
            need(len(sample)==len(MODES) and
                 set(x["mode"] for x in sample)==set(MODES),
                 "modes not matched on same source")
            need(len({x["status"] for x in sample
                      if x["status"]!="TIMEOUT"})<=1,
                 "contradictory solver statuses")
    cohorts={"all":cases}
    for tag in ("new_seed_synthetic","reused_external_original",
                "reused_synthetic_control"):
        cohorts[tag]=[c for c in cases if c["cohort"]==tag]
    totals={}
    for group,subset in cohorts.items():
        modes={}
        for mode in MODES:
            s=[r for c in subset for rep in range(REPS)
               for r in by[c["sha256"],rep] if r["mode"]==mode]
            modes[mode]=dict(attempts=len(s),
               solved=sum(r["status"]!="TIMEOUT" for r in s),
               SAT=sum(r["status"]=="SAT" for r in s),
               UNSAT=sum(r["status"]=="UNSAT" for r in s),
               par2_s=round(sum(r["par2_s"] for r in s),6),
               window_s=round(sum(r["window_s"] for r in s),6),
               restarted=sum(r["restarted"] for r in s),
               measured_windows=sum(len(r["learned_windows"]) for r in s),
               suggested_sat=sum(r["suggested"]=="sat" for r in s))
        totals[group]=dict(formulas=len(subset),modes=modes,
            speedup_vs_default={m:round(modes["default"]["par2_s"]/modes[m]["par2_s"],6)
                                for m in MODES if m!="default"},
            speedup_vs_sat={m:round(modes["sat"]["par2_s"]/modes[m]["par2_s"],6)
                                for m in MODES if m!="sat"})
    result=dict(protocol=PROTO,status="R192_AUDIT_PASS",
        source_manifest_sha256=MANIFEST_SHA,
        original_sha_each_trial=True,attempts=len(rows),
        independent_sat_witness_checked=True,
        independent_unsat_lrat=False,
        windows_learned_length_not_LBD=True,
        no_full_CDCL_propagations_reported=True,
        restarted_modes_discard_learnt_clauses=True,
        external_originals_seen_before_not_blind=True,
        groups=totals)
    save(ROOT/"report.json",result)
    save(ROOT/"trials.json",rows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R192 — CDCL three-window trajectory and causal restarts\n\n")
        f.write("102 same-SHA frozen R190/R191 CNFs, two repeats, seven modes. "
          "No new real blind holdout. Each probe counts 128 conflicts and full "
          "wall time. Learner yields clause lengths, NOT LBD or propagation. "
          "Restarts explicitly discard prior learned clauses. CaDiCaL UNSAT "
          "is not independently LRAT verified; SAT witness is checked.\n\n")
        f.write("| Cohort | Method | Solved | PAR2 s | vs default | vs SAT | Restarts |\n"
                "|---|---|---:|---:|---:|---:|---:|\n")
        for group in ("reused_external_original","reused_synthetic_control",
                      "new_seed_synthetic","all"):
            for mode,data in totals[group]["modes"].items():
                f.write(f"| {group} | {mode} | {data['solved']}/{data['attempts']} "
                        f"| {data['par2_s']} | "
                        f"{totals[group]['speedup_vs_default'].get(mode,'—')} | "
                        f"{totals[group]['speedup_vs_sat'].get(mode,'—')} | "
                        f"{data['restarted']} |\n")
        f.write("\nPrecommitted test: adaptive must beat BOTH standard and SAT profile "
                "on new real blind sources before any general claim.\n")
    print("R192_FINAL",json.dumps({"groups":totals},sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="r192/r192-driver")
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="verify":print("R192_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()

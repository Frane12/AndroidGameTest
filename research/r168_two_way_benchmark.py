#!/usr/bin/env python3
"""R168 exact-source two-way GF2/CDCL causal pilot. Research only; not blind."""
import collections, hashlib, json, os, pathlib, random, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r168")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
MODES=("clean","direct_full","direct_incremental","direct_watchlazy","direct_cooldown","direct_two_way")
REPS=2
SHARDS=4
def need(ok,why):
    if not ok:raise RuntimeError("R168_AUDIT_FAIL "+str(why))
def h(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def two_way(c,rep,prep,binary):
    src=base.FROZEN/(c["id"]+".cnf")
    need(h(src)==c["sha256"],"source SHA drift")
    tsv=ROOT/("full-"+c["id"]+".tsv")
    need(h(tsv)==prep["full_tsv_sha"],"source-certified GF2 proof mismatch")
    cap=30.0 if c["cohort"]=="mixed_residual" else 5.0
    charge=prep["preprocessing_s"]
    need(1.0<=cap-charge,"preprocessing dominates cap")
    begin=time.perf_counter()
    try:
        proc=subprocess.run([str(binary.resolve()),"direct_two_way",str(src.resolve()),str(tsv.resolve()),str(cap-charge)],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+12)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R168 native cap enforcement failed "+c["id"]) from exc
    elapsed=time.perf_counter()-begin+charge
    need(proc.returncode in (0,10,20),"native crash "+proc.stderr[-600:].decode(errors="replace"))
    txt,details,stats,source_rows,derived=base.parse_native(proc.stdout,"direct_two_way")
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[details["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"status/return mismatch")
    need(source_rows==prep["full_rows"],"source GF2 row drift")
    if status=="SAT":
        need(details["source_sat_witness_checked"]=="1","missing original SAT model verification")
        base.sat_check(src,txt)
    need(not int(details["disabled"]),"GF2 invariant failed")
    need(abs(float(details["solver_s"])-(elapsed-charge))<0.5,"native time mismatch")
    keys=("two_way_sweeps","two_way_row_xors","two_way_proposals","two_way_abstentions",
          "two_way_ns","direct_proposals","reason_clauses_completed")
    telemetry={k:int(details[k]) for k in keys}
    need(telemetry["two_way_proposals"]<=telemetry["direct_proposals"],"proposal provenance")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],family=c["family"],
                mode="direct_two_way",repeat=rep,status=status,
                elapsed=round(elapsed,6),cap=cap,
                par2=round(2*cap if status=="TIMEOUT" else min(cap,elapsed),6),
                charged_preprocess_s=charge,source_rows=source_rows,derived_rows=derived,
                native_stats=stats,proof="SOURCE_SAT_INDEPENDENT_CHECK" if status=="SAT"
                   else "UNSAT_NOT_INDEPENDENT_LRAT" if status=="UNSAT" else "TIMEOUT",
                **telemetry)
def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard")
    need(binary.is_file(),"R168 compiled binary missing")
    if hasattr(os,"sched_getaffinity"):
        affinity=os.sched_getaffinity(0)
        if affinity:os.sched_setaffinity(0,{min(affinity)})
    cases=base.sources()
    need(len(cases)==8,"frozen source count")
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=index:continue
        prep=base.prepare(c)
        for rep in range(REPS):
            modes=list(MODES)
            random.Random("R168-source-pair-"+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=two_way(c,rep,prep,binary) if mode=="direct_two_way" else base.trial(c,mode,rep,prep,binary)
                rows.append(r)
                save(ROOT/f"shard-{index}.json",rows)
                print("R168_TRIAL",json.dumps({k:r[k] for k in ("id","cohort","mode","repeat","status","elapsed","par2")},sort_keys=True),flush=True)
    need(len(rows)==24,"incomplete R168 shard")
    print("R168_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cases=base.sources()
    rows=[]
    for i in range(SHARDS):
        p=ROOT/f"shard-{i}.json"
        need(p.is_file(),"missing shard "+str(i))
        rows+=json.loads(p.read_text())
    need(len(rows)==8*len(MODES)*REPS,"missing 96 paired trials")
    keys={(r["sha256"],r["repeat"],r["mode"]) for r in rows}
    need(len(keys)==len(rows),"duplicate paired trial")
    groups={}
    for c in cases:
        a=[r for r in rows if r["sha256"]==c["sha256"]]
        need(len(a)==len(MODES)*REPS,"formula incomplete "+c["id"])
        need(len({r["status"] for r in a if r["status"]!="TIMEOUT"})<=1,"contradictory SAT/UNSAT")
        proof=json.loads((ROOT/("cert-"+c["id"]+".json")).read_text())
        base.independent_cert(c,proof)
        prep=json.loads((ROOT/("prep-"+c["id"]+".json")).read_text())
        need(h(base.FROZEN/(c["id"]+".cnf"))==prep["source_sha256"],"source digest mismatch")
        groups[c["id"]]=dict(cohort=c["cohort"],prep_s=prep["preprocessing_s"])
        for r in a:
            cap=r["cap"];expected=2*cap if r["status"]=="TIMEOUT" else min(cap,r["elapsed"])
            need(abs(r["par2"]-expected)<0.00001,"invalid PAR2")
            need(r["status"]!="SAT" or r["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK","unverified SAT")
    summary={}
    for cohort in ["all"]+sorted({r["cohort"] for r in rows}):
        data=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        summary[cohort]={}
        for mode in MODES:
            m=[r for r in data if r["mode"]==mode]
            summary[cohort][mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in m),
                trials=len(m),PAR2_s=round(sum(r["par2"] for r in m),6),
                elapsed_s=round(sum(r["elapsed"] for r in m),6),
                conflicts=sum((r["native_stats"].get("conflicts") or 0) for r in m),
                two_way_sweeps=sum(r.get("two_way_sweeps",0) for r in m),
                two_way_proposals=sum(r.get("two_way_proposals",0) for r in m),
                reason_clauses=sum(r.get("reason_clauses_completed",0) for r in m))
    result=dict(status="R168_RESEARCH_PILOT_COMPLETED",formulas=8,trials=len(rows),reps=2,
        modes=MODES,source_immutable=True,certificates_replayed=True,not_blind=True,
        summary=summary,rows=rows,
        caveats=["Previously seen R155/R154 development originals, not blind.",
                 "Full original source CNF untouched. Only source-certified parity equations used.",
                 "Native two-way GF2 combines equations with provenance replay; no heuristic XOR assumptions.",
                 "No independent LRAT for CDCL UNSAT. PAR2 timeout comparisons are censored.",
                 "GF2 preprocessor time charged to non-clean variants."])
    save(ROOT/"report.json",result)
    with open(ROOT/"summary.md","w") as out:
        out.write("# R168 — two-way GF(2) ↔ CDCL paired original-CNF development pilot\n\n")
        out.write("8 SHA-pinned formulas, 6 modes, 2 repetitions, 4 parallel shards; mixed 30 s, others 5 s.\n\n")
        out.write("| Mode | Solved | PAR2 s | Wall s | Conflicts | GF2 two-way proposals | Reasons |\n")
        out.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for mode in MODES:
            d=summary["all"][mode]
            out.write(f'| {mode} | {d["solved"]}/{d["trials"]} | {d["PAR2_s"]:.3f} | {d["elapsed_s"]:.3f} | {d["conflicts"]} | {d["two_way_proposals"]} | {d["reason_clauses"]} |\n')
        out.write("\n**Research only, NOT blind; zero completed cases means no demonstrated speedup.**\n")
    print("R168_FINAL",json.dumps({"status":result["status"],"summary":summary["all"]},sort_keys=True),flush=True)
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r168/r168-native")
    a=p.parse_args()
    if a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()

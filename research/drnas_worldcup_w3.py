#!/usr/bin/env python3
"""W3: repeated-cohort, unofficial short SAT2026 comparison."""
import argparse, json, os, random, subprocess, sys, tempfile
from pathlib import Path
import drnas_worldsim_w1 as w
import drnas_turn2_structural as t
ROOT=Path("worldcup_w3")
PROTO="DRNAS-W3-SAT2026-24x7x2-10s-v1"
CAP=10.0
REPS=2
MODES=("kissat_struct_signed",)+w.MODES
SHARDS=8
old_command=w.command_for
w.PROTO=PROTO
def command(mode,source,proof):
    if mode=="kissat_struct_signed":
        return [sys.executable,Path(__file__).resolve(),"signed", "--source",source.resolve(),"--proof",proof.resolve()],None
    return old_command(mode,source,proof)
w.command_for=command
def signed(source,proof):
    n,clauses=t.t1.parse(source)
    transformed,mapping=t.transformation(n,clauses,"kissat_struct_signed")
    with tempfile.TemporaryDirectory(dir=Path(proof).parent) as tmp:
        path=Path(tmp)/"signed.cnf"
        t.t1.write_cnf(path,n,transformed)
        p=subprocess.run([str(Path(t.KISSAT).resolve()),str(path),str(proof)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        status,model=w.parse_answer(p.stdout,p.returncode)
        # Reconstruct model before outer harness checks every original clause.
        if status=="SAT":
            model=t.t1.inverse_model(model,mapping)
            print("s SATISFIABLE")
            lits=[str(k if v else -k) for k,v in sorted(model.items())]
            for i in range(0,len(lits),20): print("v "+" ".join(lits[i:i+20])+" 0")
        else: print("s UNSATISFIABLE")
def original():
    # W1 protocol must be restored for its immutable provenance verifier.
    proto=w.PROTO
    w.PROTO="DRNAS-WORLDSIM-W1-SAT2026-24x6x3-60s-proof-v2"
    try: return w.verify_pins()
    finally: w.PROTO=proto
def trial(c,m,rep,shard,cap=CAP):
    row=w.trial(c,m,rep,shard,cap=cap,emit=False)
    row["protocol"]=PROTO
    row["independent_unsat_certificate"]=False
    # Avoid accumulating large proofs; this test reports UNSAT as unverified.
    folder=w.ROOT/"raw"/str(shard)/c["id"]/str(rep)/m
    import shutil
    for p in folder.iterdir():
        if p.name!="stdout.log":
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
    print("W3_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row
def prepare():
    manifest=original()
    w.selector()
    # Truth-equivalence test plus SAT/UNSAT smoke for every actual configuration.
    t.selftest()
    ROOT.mkdir(exist_ok=True)
    src=w.SOURCE/"w3-smoke.cnf"
    try:
        for status,cnf in [("SAT","p cnf 3 2\n1 2 0\n-2 3 0\n"),("UNSAT","p cnf 1 2\n1 0\n-1 0\n")]:
            src.write_text(cnf)
            c=dict(id="w3-smoke",sha256=w.digest(src),expected=status)
            for m in MODES:
                r=trial(c,m,0,-3,cap=15)
                w.need(r["status"]==status,"smoke "+m)
    finally: src.unlink(missing_ok=True)
    files=["research/drnas_worldcup_w3.py","research/drnas_turn2_structural.py","research/drnas_turn1_representation.py",".github/workflows/drnas-worldcup-w3.yml"]
    w.save(ROOT/"pins.json",{p:w.digest(p) for p in files})
    w.save(ROOT/"manifest.json",dict(protocol=PROTO,cases=manifest["cases"],modes=MODES,cap_s=CAP,reps=REPS,trials=336,source_run=42397824391,selection="all frozen W1 24 originals; repeated evaluation, not fresh holdout",candidate_selection="TURN2 signed exploratory signal; not established universal best",independent_unsat_certificate=False,official_ranking=False,proof_policy="requested then deleted for bounded disk; no independent UNSAT certification",timing="includes process start, transformations, selection; original SAT validation off timing"))
    print("W3_PREPARE_PASS",flush=True)
def verify():
    original()
    for p,digest in json.loads((ROOT/"pins.json").read_text()).items(): w.need(w.digest(p)==digest,"W3 code drift "+p)
    manifest=json.loads((ROOT/"manifest.json").read_text())
    w.need(manifest["protocol"]==PROTO and len(manifest["cases"])==24,"W3 manifest")
    return manifest
def shard(i):
    manifest=verify()
    w.need(i in range(SHARDS),"shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    w.selector()
    rows=[]
    for c in manifest["cases"][i::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for m in order:
                rows.append(trial(c,m,rep,i))
                w.save(ROOT/f"shard-{i}.json",dict(protocol=PROTO,manifest_sha256=w.digest(ROOT/"manifest.json"),affinity=sorted(os.sched_getaffinity(0)),cpu=Path("/proc/cpuinfo").read_text().split("model name",1)[-1].split("\n",1)[0],rows=rows))
    w.need(len(rows)==42,"incomplete shard")
    print("W3_SHARD_PASS",i,len(rows),flush=True)
def audit():
    manifest=verify()
    rows=[]; keys=set()
    for i in range(SHARDS):
        d=json.loads((ROOT/f"shard-{i}.json").read_text())
        w.need(d["protocol"]==PROTO and d["manifest_sha256"]==w.digest(ROOT/"manifest.json") and len(d["affinity"])==1,"shard provenance")
        w.need(len(d["rows"])==42,"shard count")
        allowed={(c["sha256"],c["id"]) for c in manifest["cases"][i::SHARDS]}
        for r in d["rows"]:
            key=(r["sha256"],r["rep"],r["mode"])
            w.need(key not in keys and (r["sha256"],r["id"]) in allowed and r["shard"]==i and r["protocol"]==PROTO,"row identity")
            w.need(r["status"] in ("SAT","UNSAT","TIMEOUT") and 0<=r["elapsed_s"]<=CAP,"row verdict/time")
            w.need(r["status"]!="SAT" or r["evidence"]=="SAT_MODEL_ORIGINAL_CNF_VERIFIED","unchecked SAT")
            expected=2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]
            w.need(abs(expected-r["par2_s"])<1e-5,"PAR2")
            keys.add(key); rows.append(r)
    expected={(c["sha256"],rep,m) for c in manifest["cases"] for rep in range(REPS) for m in MODES}
    w.need(keys==expected and len(rows)==336,"missing pairs")
    for c in manifest["cases"]:
        w.need(len({r["status"] for r in rows if r["sha256"]==c["sha256"] and r["status"]!="TIMEOUT"})<=1,"solver disagreement")
    totals={}
    for m in MODES:
        rr=[r for r in rows if r["mode"]==m]
        totals[m]=dict(attempts=len(rr),solved=sum(r["status"]!="TIMEOUT" for r in rr),distinct=len({r["sha256"] for r in rr if r["status"]!="TIMEOUT"}),PAR2_s=round(sum(r["par2_s"] for r in rr),6),elapsed_s=round(sum(r["elapsed_s"] for r in rr),6))
    candidate=totals[MODES[0]]["PAR2_s"]
    report=dict(status="W3_AUDIT_PASS",protocol=PROTO,manifest=manifest,totals=totals,ratio_vs_signed={m:totals[m]["PAR2_s"]/candidate for m in MODES},independent_unsat_certificate=False)
    w.save(ROOT/"report.json",report); w.save(ROOT/"all-trials.json",rows)
    lines=["# W3 short SAT2026 comparison","", "24 repeated official sources × 7 solvers × 2 repetitions, 10s cap. One CPU; serial randomized arms.","","| Solver | Solved / 48 | Distinct / 24 | PAR-2 s | PAR-2 / Signed |","|---|---:|---:|---:|---:|"]
    for m in sorted(MODES,key=lambda m:totals[m]["PAR2_s"]):
        d=totals[m]
        lines.append(f"| {m} | {d['solved']} | {d['distinct']} | {d['PAR2_s']:.6f} | {d['PAR2_s']/candidate:.4f}× |")
    lines+=["","UNSAT is reported, not independently certified. Repeated cohort; unofficial short-budget test. Signed is a candidate selected on TURN2, not a proven universal best."]
    (ROOT/"report.md").write_text("\n".join(lines)+"\n")
    print("W3_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["prepare","shard","audit","signed"]);p.add_argument("--shard",type=int);p.add_argument("--source");p.add_argument("--proof");a=p.parse_args()
    if a.action=="signed": signed(a.source,a.proof)
    elif a.action=="shard": shard(a.shard)
    else: globals()[a.action]()

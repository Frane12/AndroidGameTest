#!/usr/bin/env python3
"""W4O: repeated-cohort, unofficial short SAT2026 comparison."""
import argparse, json, os, random, subprocess, sys, tempfile, time, re
from pathlib import Path
import drnas_worldsim_w1 as w
import drnas_turn2_structural as t
ROOT=Path("worldcup_w4o")
PROTO="DRNAS-W4OSR-SAT2026-24x6x3-30s-v2"
CAP=30.0
REPS=3
MODES=("r28_optimized","r28_kissat","kissat_404","satsuma_iter_kissat_2026","cms_51115","cadical_301")
SHARDS=8
old_command=w.command_for
w.PROTO=PROTO
w.SOURCE=Path("history/w4sources/sources")
def command(mode,source,proof):
    if mode=="r28_optimized":
        return [Path("optimized/r28").resolve(),source.resolve(),Path("built/bin/kissat_4_0_4").resolve()],None
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
    saved=w.SOURCE;w.SOURCE=Path("ta3_2026/sources")
    try: return w.verify_pins()
    finally: w.PROTO=proto;w.SOURCE=saved
def trial(c,m,rep,shard,cap=CAP):
    row=w.trial(c,m,rep,shard,cap=cap,emit=False)
    row["protocol"]=PROTO
    validation_start=time.perf_counter()
    row["independent_unsat_certificate"]=False
    if row["status"]=="UNSAT":
        proof=w.ROOT/"raw"/str(shard)/c["id"]/str(rep)/m/"proof.out"
        source=w.SOURCE/(c["id"]+".cnf")
        checked=False
        if proof.is_file() and proof.stat().st_size:
            try:
                if m=="satsuma_iter_kissat_2026":
                    # Submitted SAT2026 Satsuma emits binary SR, not DRAT.
                    sr=Path("worldsim_w1/official/anders/satsuma-iter-kissat/src/dsr-trim/bin/dsr-trim").resolve()
                    w.need(sr.is_file(), "bundled SR checker missing")
                    checker=[str(sr), "-f", str(source), str(proof), "/dev/null", "-q"]
                    required="s VERIFIED UNSAT"
                    row["proof_checker"]="dsr-trim-SR"
                else:
                    checker=["checker/drat-trim", str(source), str(proof)]
                    required="s VERIFIED"
                    row["proof_checker"]="drat-trim"
                check=subprocess.run(checker,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
                checked=check.returncode==0 and required in check.stdout
                (proof.parent/"certificate.log").write_text(check.stdout)
            except subprocess.TimeoutExpired:
                (proof.parent/"certificate.log").write_text("CHECKER_TIMEOUT")
                row["proof_checker_timeout"]=True
        row["reported_status"]="UNSAT"
        row["independent_unsat_certificate"]=checked
        if checked: row["evidence"]="UNSAT_DRAT_VERIFIED"
        else:
            row["status"]="TIMEOUT";row["par2_s"]=2*cap
            row["evidence"]="UNSAT_UNCERTIFIED_NOT_SCORED"

    row["validation_s"]=round(time.perf_counter()-validation_start,6)
    row["elapsed_plus_validation_s"]=row["elapsed_s"]+row["validation_s"]
    folder=w.ROOT/"raw"/str(shard)/c["id"]/str(rep)/m
    raw=(folder/"stdout.log").read_text()
    route=re.search(r"^c R28_ROUTE (.*)$",raw,re.M)
    prep=re.search(r"^c R28_PREP_S ([0-9.eE+-]+)$",raw,re.M)
    row["r28_route"]=route.group(1) if route else None
    row["r28_prep_s"]=float(prep.group(1)) if prep else None
    import shutil
    for p in folder.iterdir():
        if p.name not in ("stdout.log","certificate.log"):
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
    print("W4O_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row
def prepare():
    original()
    sr=Path("worldsim_w1/official/anders/satsuma-iter-kissat/src/dsr-trim/bin/dsr-trim")
    w.need(sr.is_file(), "bundled SR proof checker missing")
    manifest=json.loads(Path("worldcup_w4/manifest.json").read_text())
    w.need(len(manifest["cases"])==24,"same W4 cohort")
    ROOT.mkdir(exist_ok=True)
    src=w.SOURCE/"w4o-smoke.cnf"
    try:
        for status,cnf in [("SAT","p cnf 3 2\n1 2 0\n-2 3 0\n"),("UNSAT","p cnf 1 2\n1 0\n-1 0\n")]:
            src.write_text(cnf)
            c=dict(id="w4o-smoke",sha256=w.digest(src),expected=status)
            for m in MODES:
                r=trial(c,m,0,-5,cap=15)
                w.need(r["status"]==status,"smoke "+m)
    finally: src.unlink(missing_ok=True)
    manifest.update(protocol=PROTO,modes=MODES,trials=432,selection="exact frozen W4 cohort reused for development; not blind",candidate_selection="pointer lookup and direct exec; original R28 concurrent control",parent_manifest_sha256=w.digest("worldcup_w4/manifest.json"))
    w.save(ROOT/"manifest.json",manifest)
    paths=["research/drnas_worldcup_w4o.py","research/r28_w4_optimized.cpp","optimized/r28","checker/drat-trim",".github/workflows/drnas-worldcup-w4o.yml",str(ROOT/"manifest.json")]
    w.save(ROOT/"pins.json",{p:w.digest(p) for p in paths})
    print("W4O_PREPARE_PASS",flush=True)
def verify():
    original()
    for p,digest in json.loads((ROOT/"pins.json").read_text()).items(): w.need(w.digest(p)==digest,"W4O code drift "+p)
    manifest=json.loads((ROOT/"manifest.json").read_text())
    w.need(manifest["protocol"]==PROTO and len(manifest["cases"])==24,"W4O manifest")
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
    w.need(len(rows)==54,"incomplete shard")
    print("W4O_SHARD_PASS",i,len(rows),flush=True)
def audit():
    manifest=verify()
    rows=[]; keys=set()
    for i in range(SHARDS):
        d=json.loads((ROOT/f"shard-{i}.json").read_text())
        w.need(d["protocol"]==PROTO and d["manifest_sha256"]==w.digest(ROOT/"manifest.json") and len(d["affinity"])==1,"shard provenance")
        w.need(len(d["rows"])==54,"shard count")
        allowed={(c["sha256"],c["id"]) for c in manifest["cases"][i::SHARDS]}
        for r in d["rows"]:
            key=(r["sha256"],r["rep"],r["mode"])
            w.need(key not in keys and (r["sha256"],r["id"]) in allowed and r["shard"]==i and r["protocol"]==PROTO,"row identity")
            w.need(r["status"] in ("SAT","UNSAT","TIMEOUT") and 0<=r["elapsed_s"]<=CAP,"row verdict/time")
            w.need(r["status"]!="SAT" or r["evidence"]=="SAT_MODEL_ORIGINAL_CNF_VERIFIED","unchecked SAT")
            w.need(r["status"]!="UNSAT" or (r["independent_unsat_certificate"] and r["evidence"]=="UNSAT_DRAT_VERIFIED"),"unchecked UNSAT")
            expected=2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]
            w.need(abs(expected-r["par2_s"])<1e-5,"PAR2")
            keys.add(key); rows.append(r)
    expected={(c["sha256"],rep,m) for c in manifest["cases"] for rep in range(REPS) for m in MODES}
    w.need(keys==expected and len(rows)==432,"missing pairs")
    for c in manifest["cases"]:
        w.need(len({r["status"] for r in rows if r["sha256"]==c["sha256"] and r["status"]!="TIMEOUT"})<=1,"solver disagreement")
    totals={}
    for m in MODES:
        rr=[r for r in rows if r["mode"]==m]
        totals[m]=dict(attempts=len(rr),solved=sum(r["status"]!="TIMEOUT" for r in rr),distinct=len({r["sha256"] for r in rr if r["status"]!="TIMEOUT"}),PAR2_s=round(sum(r["par2_s"] for r in rr),6),elapsed_s=round(sum(r["elapsed_s"] for r in rr),6))
    candidate=totals[MODES[0]]["PAR2_s"]
    report=dict(status="W4O_AUDIT_PASS",protocol=PROTO,manifest=manifest,totals=totals,ratio_vs_r28={m:totals[m]["PAR2_s"]/candidate for m in MODES},independent_unsat_certificate=False)
    w.save(ROOT/"report.json",report); w.save(ROOT/"all-trials.json",rows)
    lines=["# W4O short SAT2026 comparison","", "Same 24 W4 official sources × 6 solvers × 3 repetitions, 30s cap. One CPU; serial randomized arms.","","| Solver | Solved / 72 | Distinct / 24 | PAR-2 s | PAR-2 / R28 |","|---|---:|---:|---:|---:|"]
    for m in sorted(MODES,key=lambda m:totals[m]["PAR2_s"]):
        d=totals[m]
        lines.append(f"| {m} | {d['solved']} | {d['distinct']} | {d['PAR2_s']:.6f} | {d['PAR2_s']/candidate:.4f}× |")
    lines+=["","Only independently checked UNSAT and validated SAT count as solved. Development reuse of W4 cohort; unofficial 30s test."]
    (ROOT/"report.md").write_text("\n".join(lines)+"\n")
    print("W4O_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["prepare","shard","audit","signed"]);p.add_argument("--shard",type=int);p.add_argument("--source");p.add_argument("--proof");a=p.parse_args()
    if a.action=="signed": signed(a.source,a.proof)
    elif a.action=="shard": shard(a.shard)
    else: globals()[a.action]()


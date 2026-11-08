#!/usr/bin/env python3
"""W4: repeated-cohort, unofficial short SAT2026 comparison."""
import argparse, json, os, random, subprocess, sys, tempfile
from pathlib import Path
import drnas_worldsim_w1 as w
import drnas_turn2_structural as t
ROOT=Path("worldcup_w4")
PROTO="DRNAS-W4-SAT2026-24x5x3-30s-v1"
CAP=30.0
REPS=3
MODES=("r28_kissat","kissat_404","satsuma_iter_kissat_2026","cms_51115","cadical_301")
SHARDS=8
old_command=w.command_for
w.PROTO=PROTO
w.SOURCE=Path("history/w4sources/sources")
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
    saved=w.SOURCE;w.SOURCE=Path("ta3_2026/sources")
    try: return w.verify_pins()
    finally: w.PROTO=proto;w.SOURCE=saved
def trial(c,m,rep,shard,cap=CAP):
    row=w.trial(c,m,rep,shard,cap=cap,emit=False)
    row["protocol"]=PROTO
    row["independent_unsat_certificate"]=False
    if row["status"]=="UNSAT":
        proof=w.ROOT/"raw"/str(shard)/c["id"]/str(rep)/m/"proof.out"
        source=w.SOURCE/(c["id"]+".cnf")
        checked=False
        if proof.is_file() and proof.stat().st_size:
            try:
                check=subprocess.run(["checker/drat-trim",str(source),str(proof)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
                checked=check.returncode==0 and "s VERIFIED" in check.stdout
                (proof.parent/"certificate.log").write_text(check.stdout)
            except subprocess.TimeoutExpired: pass
        row["reported_status"]="UNSAT"
        row["independent_unsat_certificate"]=checked
        if checked: row["evidence"]="UNSAT_DRAT_VERIFIED"
        else:
            row["status"]="TIMEOUT";row["par2_s"]=2*cap
            row["evidence"]="UNSAT_UNCERTIFIED_NOT_SCORED"

    # Avoid accumulating large proofs; this test reports UNSAT as unverified.
    folder=w.ROOT/"raw"/str(shard)/c["id"]/str(rep)/m
    import shutil
    for p in folder.iterdir():
        if p.name not in ("stdout.log","certificate.log"):
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
    print("W4_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row
def prepare():
    original()
    previous_known=t.known
    def excluded():
        hashes,ids=previous_known()
        for c in json.loads(Path("turn2/manifest.json").read_text())["cases"]:
            hashes.add(c["sha256"]);ids.add(c["id"])
        return hashes,ids
    t.known=excluded
    t.ROOT=Path("w4sources");t.SOURCE=t.ROOT/"sources";t.NCASES=24
    os.chdir("history")
    try:
        t.fetch()
        manifest=json.loads((t.ROOT/"manifest.json").read_text())
    finally: os.chdir("..")
    w.SOURCE=Path("history/w4sources/sources")
    w.selector()
    # Truth-equivalence test plus SAT/UNSAT smoke for every actual configuration.
    t.selftest()
    ROOT.mkdir(exist_ok=True)
    src=w.SOURCE/"w4-smoke.cnf"
    try:
        for status,cnf in [("SAT","p cnf 3 2\n1 2 0\n-2 3 0\n"),("UNSAT","p cnf 1 2\n1 0\n-1 0\n")]:
            src.write_text(cnf)
            c=dict(id="w4-smoke",sha256=w.digest(src),expected=status)
            for m in MODES:
                r=trial(c,m,0,-3,cap=15)
                w.need(r["status"]==status,"smoke "+m)
    finally: src.unlink(missing_ok=True)
    files=["research/drnas_worldcup_w4.py","research/drnas_turn2_structural.py","research/drnas_turn1_representation.py",".github/workflows/drnas-worldcup-w4.yml","checker/drat-trim"]
    w.save(ROOT/"pins.json",{p:w.digest(p) for p in files})
    w.save(ROOT/"manifest.json",dict(protocol=PROTO,cases=manifest["cases"],modes=MODES,cap_s=CAP,reps=REPS,trials=360,source_run=42397824391,selection="24 next eligible sources excluded by historical manifests including TURN2",candidate_selection="R28 frozen after W3; no tuning on W4 outcomes",independent_unsat_certificate=False,official_ranking=False,proof_policy="DRAT checked before deletion; uncertified UNSAT receives timeout penalty",timing="includes process start, transformations, selection; original SAT validation off timing"))
    print("W4_PREPARE_PASS",flush=True)
def verify():
    original()
    for p,digest in json.loads((ROOT/"pins.json").read_text()).items(): w.need(w.digest(p)==digest,"W4 code drift "+p)
    manifest=json.loads((ROOT/"manifest.json").read_text())
    w.need(manifest["protocol"]==PROTO and len(manifest["cases"])==24,"W4 manifest")
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
    w.need(len(rows)==45,"incomplete shard")
    print("W4_SHARD_PASS",i,len(rows),flush=True)
def audit():
    manifest=verify()
    rows=[]; keys=set()
    for i in range(SHARDS):
        d=json.loads((ROOT/f"shard-{i}.json").read_text())
        w.need(d["protocol"]==PROTO and d["manifest_sha256"]==w.digest(ROOT/"manifest.json") and len(d["affinity"])==1,"shard provenance")
        w.need(len(d["rows"])==45,"shard count")
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
    w.need(keys==expected and len(rows)==360,"missing pairs")
    for c in manifest["cases"]:
        w.need(len({r["status"] for r in rows if r["sha256"]==c["sha256"] and r["status"]!="TIMEOUT"})<=1,"solver disagreement")
    totals={}
    for m in MODES:
        rr=[r for r in rows if r["mode"]==m]
        totals[m]=dict(attempts=len(rr),solved=sum(r["status"]!="TIMEOUT" for r in rr),distinct=len({r["sha256"] for r in rr if r["status"]!="TIMEOUT"}),PAR2_s=round(sum(r["par2_s"] for r in rr),6),elapsed_s=round(sum(r["elapsed_s"] for r in rr),6))
    candidate=totals[MODES[0]]["PAR2_s"]
    report=dict(status="W4_AUDIT_PASS",protocol=PROTO,manifest=manifest,totals=totals,ratio_vs_r28={m:totals[m]["PAR2_s"]/candidate for m in MODES},independent_unsat_certificate=False)
    w.save(ROOT/"report.json",report); w.save(ROOT/"all-trials.json",rows)
    lines=["# W4 short SAT2026 comparison","", "24 new eligible official sources × 5 solvers × 3 repetitions, 30s cap. One CPU; serial randomized arms.","","| Solver | Solved / 72 | Distinct / 24 | PAR-2 s | PAR-2 / R28 |","|---|---:|---:|---:|---:|"]
    for m in sorted(MODES,key=lambda m:totals[m]["PAR2_s"]):
        d=totals[m]
        lines.append(f"| {m} | {d['solved']} | {d['distinct']} | {d['PAR2_s']:.6f} | {d['PAR2_s']/candidate:.4f}× |")
    lines+=["","Only independently checked UNSAT and validated SAT count as solved. Historical-manifest-disjoint cohort; unofficial 30s test."]
    (ROOT/"report.md").write_text("\n".join(lines)+"\n")
    print("W4_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["prepare","shard","audit","signed"]);p.add_argument("--shard",type=int);p.add_argument("--source");p.add_argument("--proof");a=p.parse_args()
    if a.action=="signed": signed(a.source,a.proof)
    elif a.action=="shard": shard(a.shard)
    else: globals()[a.action]()


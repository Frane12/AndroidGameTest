#!/usr/bin/env python3
"""Post-freeze synthetic holdout pilot. Not external validation."""
import argparse, hashlib, json, os, random, secrets, subprocess, time
from pathlib import Path
from smoke_test import generate
from verify_hall import verify

def dump(p, x):
    p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n")
def cnf_parse(raw):
    rows=raw.decode().splitlines()
    n=int(rows[0].split()[2])
    return n,[list(map(int,r.split()[:-1])) for r in rows[1:]]
def check_model(n, clauses, assignment):
    return len(assignment)==n and all(any(assignment.get(abs(l)) == (l>0) for l in c) for c in clauses)
def run(cmd, timeout, log):
    t=time.monotonic()
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors="replace",timeout=timeout)
        rc,out=p.returncode,p.stdout
    except subprocess.TimeoutExpired as e:
        rc=124
        out=e.stdout or b""
        if isinstance(out,bytes): out=out.decode(errors="replace")
    elapsed=time.monotonic()-t
    log.write_text(out)
    return rc,elapsed,out
def main(a):
    from ortools.sat.python import cp_model
    out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0)); os.sched_setaffinity(0,{cpu})
    master=a.seed if a.seed is not None else secrets.randbits(128)
    rng=random.Random(master)
    kinds=["UNSAT"]*40+["SAT"]*40+["DECOY"]*20
    rng.shuffle(kinds)
    manifest=[]
    for i,k in enumerate(kinds):
        seed=rng.getrandbits(64); bins=rng.randrange(7,19)
        d=out/f"{i:03}"; d.mkdir(); raw=generate(bins,k,seed)
        (d/"source.cnf").write_bytes(raw)
        manifest.append(dict(id=i,kind=k,expected="SAT" if k=="SAT" else "UNSAT",seed=seed,bins=bins,sha256=hashlib.sha256(raw).hexdigest()))
    assert len({m["sha256"] for m in manifest})==100
    dump(out/"manifest.json",dict(master_seed=master,cpu=cpu,freeze=a.freeze,cap=a.cap,cases=manifest))
    rows=[]; errors=[]
    for m in manifest:
        d=out/f'{m["id"]:03}'; src=d/"source.cnf"; raw=src.read_bytes(); n,cs=cnf_parse(raw)
        arms=["drnas","kissat","cadical","cpsat"]; rng.shuffle(arms)
        for arm in arms:
            r=dict(id=m["id"],kind=m["kind"],expected=m["expected"],sha256=m["sha256"],arm=arm,vars=n,clauses=len(cs),certified=False)
            if arm=="drnas":
                cert=d/"hall.json"
                rc,elapsed,log=run([a.drnas,str(src),"--mode","core","--time",str(a.cap),"--pcmax-hall-only","--pcmax-hall-budget-ms",str(min(1500,a.cap*1000)),"--pcmax-certificate",str(cert)],a.cap,d/"drnas.log")
                r.update(rc=rc,elapsed=elapsed,status={20:"UNSAT",10:"SAT",0:"UNKNOWN",124:"TIMEOUT"}.get(rc,"ERROR"))
                if rc==20 and cert.is_file():
                    t=time.monotonic()
                    try: r["certified"]=verify(raw,json.loads(cert.read_text()))["status"]=="SOURCE_HALL_UNSAT_VERIFIED"
                    except Exception as e: r["verify_error"]=str(e)
                    r.update(verify_s=time.monotonic()-t,proof_bytes=cert.stat().st_size,proof_type="custom-source-Hall")
            elif arm in ("kissat","cadical"):
                proof=d/(arm+".drat")
                cmd=[getattr(a,arm),str(src),str(proof)]
                rc,elapsed,log=run(cmd,a.cap,d/(arm+".log"))
                r.update(rc=rc,elapsed=elapsed,status={20:"UNSAT",10:"SAT",124:"TIMEOUT"}.get(rc,"ERROR"))
                if rc==10:
                    v=[int(x) for line in log.splitlines() if line.startswith("v ") for x in line[2:].split() if x!="0"]
                    r["certified"]=check_model(n,cs,{abs(x):x>0 for x in v})
                if rc==20 and proof.is_file():
                    _,vs,vl=run([a.checker,str(src),str(proof)],30,d/(arm+"-check.log"))
                    r.update(certified=any(x.strip()=="s VERIFIED" for x in vl.splitlines()),verify_s=vs,proof_bytes=proof.stat().st_size,proof_type="DRAT")
            else:
                t=time.monotonic(); model=cp_model.CpModel(); v=[model.new_bool_var(str(i)) for i in range(n)]
                for c in cs: model.add_bool_or([v[l-1] if l>0 else v[-l-1].Not() for l in c])
                solver=cp_model.CpSolver(); solver.parameters.num_search_workers=1
                solver.parameters.max_time_in_seconds=max(.001,a.cap-(time.monotonic()-t))
                st=solver.solve(model); elapsed=time.monotonic()-t
                status="SAT" if st in (cp_model.OPTIMAL,cp_model.FEASIBLE) else "UNSAT" if st==cp_model.INFEASIBLE else "UNKNOWN"
                r.update(elapsed=elapsed,status=status,certified=status=="SAT" and check_model(n,cs,{i+1:bool(solver.value(x)) for i,x in enumerate(v)}),proof_type="model" if status=="SAT" else "none")
            if r["elapsed"]>a.cap: r["within_cap"]=False
            else: r["within_cap"]=True
            if r["status"] in ("SAT","UNSAT") and r["status"]!=r["expected"]: errors.append(r)
            if arm=="drnas" and r["status"] in ("SAT","UNSAT") and not r["certified"]: errors.append(r)
            rows.append(r)
            with (out/"rows.jsonl").open("a") as f: f.write(json.dumps(r)+"\n")
            print("PCMAX_CONFERENCE_ROW",json.dumps(r),flush=True)
    summary={}
    for arm in ["drnas","kissat","cadical","cpsat"]:
        rr=[r for r in rows if r["arm"]==arm]; solved=[r for r in rr if r["within_cap"] and r["status"]==r["expected"]]; certified=[r for r in solved if r["certified"]]
        summary[arm]=dict(n=len(rr),reported=len(solved),certified=len(certified),reported_par2=sum(r["elapsed"] if r in solved else 2*a.cap for r in rr)/len(rr),certified_par2=sum(r["elapsed"] if r in certified else 2*a.cap for r in rr)/len(rr))
    dump(out/"summary.json",dict(summary=summary,errors=errors))
    print("PCMAX_CONFERENCE_FINAL",json.dumps(summary),flush=True)
    if errors: raise SystemExit("critical disagreement or missing DRNAS certificate")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ["drnas","kissat","cadical","checker"]: p.add_argument("--"+name,required=True)
    p.add_argument("--out",type=Path,required=True); p.add_argument("--seed",type=int)
    p.add_argument("--cap",type=int,default=5); p.add_argument("--freeze",required=True)
    main(p.parse_args())

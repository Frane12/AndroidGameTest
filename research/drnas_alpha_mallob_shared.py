#!/usr/bin/env python3
"""Experiment: upstream AlphaMapleSAT MCTS cuber -> MallobSat -> DRNAS SI scheduler.
FROZEN source manifest reused from R193. This is NOT a blind official benchmark.
All stage costs charged to identical wall-clock budgets. No frozen solver modified.
"""
import argparse
import hashlib
import itertools
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import time

ROOT = pathlib.Path("alpha_mallob_shared")
FROZEN = ROOT / "frozen"
ALPHA = pathlib.Path("external/AlphaMapleSAT/alphamaplesat").resolve()
MALLOB = pathlib.Path("external/mallob").resolve()
EXPECTED_MANIFEST = "9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
CAP = 30.0
REPS = 2
SHARDS = 8
MODES = ("mallob_direct", "alpha_mallob_drnas_si")
PROTO = "DRNAS-ALPHA-MALLOB-SHARED-24x2x2-30S-v1"

def need(v, reason):
    if not v:
        raise RuntimeError("AMDS_AUDIT_FAIL " + reason)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def store(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def load():
    need(sha(FROZEN/"manifest.json") == EXPECTED_MANIFEST, "original manifest changed")
    data=json.loads((FROZEN/"manifest.json").read_text())
    need(len(data["cases"])==102, "source not frozen102")
    cases=[]
    for cohort, number in (("new_seed_synthetic", 10), ("reused_synthetic_control", 6), ("reused_external_original", 8)):
        choices=sorted((c for c in data["cases"] if c["cohort"]==cohort),key=lambda x:x["sha256"])
        need(len(choices)>=number, "missing cohort "+cohort)
        cases+=choices[:number]
    need(len(cases)==24 and len({c["sha256"] for c in cases})==24, "not 24 SHA unique")
    for case in cases:
        need(sha(FROZEN/(case["id"]+".cnf"))==case["sha256"], "CNF hash drift")
    return cases

def header(path):
    n=0; m=0
    with path.open() as f:
        for line in f:
            if line.startswith("p cnf "):
                s=line.split()
                n,m=int(s[2]),int(s[3])
                break
    need(n>0 and m>=0, "invalid header")
    return n,m

def parse_cubes(path):
    cubes=[]
    if not path.is_file():
        return cubes
    for line in path.read_text(errors="replace").splitlines():
        tokens=line.strip().split()
        if not tokens or tokens[0]!="a":
            continue
        need(tokens[-1]=="0", "cube not terminated")
        cube=tuple(int(x) for x in tokens[1:-1])
        need(all(x and -x not in cube for x in cube), "contradictory cube")
        cubes.append(cube)
    return cubes

def cover(cubes, nvars):
    # An MCTS cuber may output arbitrary many cubes. Accept ONLY proven complete cover.
    if not cubes or len(cubes)>32:
        return False
    vs=sorted({abs(l) for cube in cubes for l in cube})
    if len(vs)>10 or any(v>nvars for v in vs) or len(set(cubes))!=len(cubes):
        return False
    for signs in itertools.product((False,True),repeat=len(vs)):
        truth=dict(zip(vs,signs))
        if not any(all(truth[abs(l)]==(l>0) for l in cube) for cube in cubes):
            return False
    return True

def try_cuber(case, rep, remaining):
    src=(FROZEN/(case["id"]+".cnf")).resolve()
    nv,nc=header(src)
    if nv>512 or nc>30000:
        return [],"GATE_large_CNF"
    if remaining<3.0:
        return [],"GATE_budget"
    fn="amds-"+case["sha256"][:15]+"-"+str(rep)+".cubes"
    output=ALPHA/fn
    output.unlink(missing_ok=True)
    env=dict(os.environ)
    env["WANDB_MODE"]="disabled"
    cmd=[sys.executable,"-u","main.py",str(src),"-d","1","-m",str(min(nv,24)),"-numMCTSSims","4","-o",fn,"-prod"]
    try:
        p=subprocess.run(cmd,cwd=ALPHA,env=env,capture_output=True,text=True,errors="replace",
                         timeout=min(remaining*.3,6.0))
    except subprocess.TimeoutExpired:
        return [],"CUBER_TIMEOUT"
    if p.returncode!=0:
        return [],"CUBER_ERROR_"+str(p.returncode)+":"+p.stderr[-100:].replace("\n"," ")
    try:
        cubes=parse_cubes(output)
        if not cover(cubes,nv):
            return [],"CUBES_NOT_COMPLETE"
        return cubes,"ALPHA_MCTS_COVER_VALID"
    except Exception as e:
        return [],"CUBES_INVALID_"+str(e)[:85]

def write_subproblem(source, cube, dest):
    # Preserve all clauses, constrain by unit assumptions.
    with source.open() as f:
        raw=f.readlines()
    hidx=next(i for i,l in enumerate(raw) if l.startswith("p cnf "))
    h=raw[hidx].split()
    raw[hidx]="p cnf %s %d\n" % (h[2],int(h[3])+len(cube))
    dest.write_text("".join(raw)+"".join(str(l)+" 0\n" for l in cube))

def mallob_solve(source, remaining, work):
    work.mkdir(parents=True,exist_ok=True)
    sol=(work/"solution.txt").resolve()
    cmd=[str(MALLOB/"build/mallob"),"-mono="+str(source.resolve()),"-mono-app=SAT",
         "-t=2","-satsolver=k","-s2f="+str(sol)]
    try:
        p=subprocess.run(cmd,cwd=MALLOB,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,errors="replace",timeout=max(.2,remaining))
    except subprocess.TimeoutExpired:
        return "TIMEOUT",{}, "WALL_TIMEOUT"
    txt=p.stdout[-100000:]
    (work/"mallob-tail.log").write_text(txt[-16000:])
    # Mallob logs may contain the solver's version names. Parse only explicit job-result lines.
    # Parse solution-to-file as the preferred source for a confirmed result.
    files=[sol]+list(work.glob("solution.txt.*"))
    result="UNKNOWN"
    model={}
    for fp in files:
        if not fp.is_file():continue
        data=fp.read_text(errors="replace")
        for line in data.splitlines():
            t=line.strip()
            if re.match(r"^s\s+UNSATISFIABLE\s*$",t): result="UNSAT"
            if re.match(r"^s\s+SATISFIABLE\s*$",t): result="SAT"
            if t.startswith("v "):
                for lit in re.findall(r"[-]?\d+",t[2:]):
                    k=int(lit)
                    if k:model[abs(k)]=k>0
    if result=="UNKNOWN":
        # Only terminal result lines, not mentions of solver features.
        for line in txt.splitlines():
            if re.search(r"\b(s UNSATISFIABLE|resultcode[=: ]+20|resultstring[=: ]+UNSAT)\b",line,re.I):
                result="UNSAT"
            elif re.search(r"\b(s SATISFIABLE|resultcode[=: ]+10|resultstring[=: ]+SAT)\b",line,re.I):
                result="SAT"
    if result=="UNKNOWN":
        return "TIMEOUT",{},"MALLOB_UNPARSED_OR_UNKNOWN_"+str(p.returncode)
    if result=="SAT" and not model:
        # Never label SAT as witnessed without an actual assignment.
        return "TIMEOUT",{},"MALLOB_SAT_NO_MODEL"
    return result,model,"MALLOB_SOLVED_"+str(p.returncode)

def check_model(source,model):
    # Validate original CNF (not just the cube) without treating a missing variable as false.
    vals=set()
    with source.open() as f:
        for line in f:
            if not line or line[0] in ("c","p","%"):continue
            if line.startswith("v"):continue
            for word in line.split():
                lit=int(word)
                if lit==0:
                    need(any(model.get(abs(q))==(q>0) for q in vals), "SAT witness does not satisfy original clause")
                    vals.clear()
                else:vals.add(lit)
    need(not vals, "unterminated original clause")

def drnas_shared_priority(cube, cnf):
    # Cheap explicit structural feedback: estimated clauses touched by cube.
    hits=sum(1 for line in cnf if any(str(x) in line.split() for x in cube))
    return hits / max(1,len(cube))

def trial(case,rep,mode):
    original=FROZEN/(case["id"]+".cnf")
    st=time.perf_counter()
    work=ROOT/"raw"/case["sha256"][:12]/str(rep)/mode
    work.mkdir(parents=True,exist_ok=True)
    cubes=[]
    gate="CONTROL"
    if mode=="alpha_mallob_drnas_si":
        cubes,gate=try_cuber(case,rep,CAP-(time.perf_counter()-st))
    jobs=[()] if not cubes else list(cubes)
    # DRNAS SI feedback ordering with explicit per-cube structure scores, pre-result only.
    if cubes:
        clauses=[line for line in original.read_text().splitlines() if line and line[0] not in ("c","p")]
        jobs=sorted(jobs,key=lambda cube:(-drnas_shared_priority(cube,clauses),cube))
    result="TIMEOUT";proof="CAP_TIMEOUT";backend=[]
    for i,cube in enumerate(jobs):
        left=CAP-(time.perf_counter()-st)
        if left<.25:break
        source=original
        if cube:
            source=work/("cube-%d.cnf"%i)
            write_subproblem(original,cube,source)
        status,model,evidence=mallob_solve(source,left,work/("job-%d"%i))
        backend.append({"cube":list(cube),"status":status,"evidence":evidence})
        if status=="SAT":
            check_model(original,model)
            result="SAT";proof="SAT_ORIGINAL_WITNESS_CHECKED";break
        if status!="UNSAT":
            break
    else:
        if backend and all(x["status"]=="UNSAT" for x in backend):
            result="UNSAT";proof="UNSAT_BACKEND_ONLY_NO_INDEPENDENT_PROOF"
    elapsed=time.perf_counter()-st
    if elapsed>=CAP:
        result="TIMEOUT";proof="CAP_TIMEOUT"
    if result!="TIMEOUT" and case.get("expected") not in (None,"UNKNOWN"):
        need(result==case["expected"],"known expected status mismatch")
    return dict(id=case["id"],source_sha256=case["sha256"],cohort=case["cohort"],family=case["family"],
                mode=mode,rep=rep,cap_s=CAP,status=result,elapsed_s=round(elapsed,6),
                par2_s=round(CAP*2 if result=="TIMEOUT" else elapsed,6),
                cuber_gate=gate,verified_cubes=len(cubes),cube_complete_cover=bool(cubes),
                backend=backend,proof=proof)

def shard(k):
    cases=load();need(0<=k<SHARDS,"shard outside range")
    rr=[]
    for c in cases[k::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                row=trial(c,rep,mode)
                rr.append(row)
                store(ROOT/("shard-%d.json"%k),rr)
                print("AMDS_TRIAL",json.dumps({key:row[key] for key in ("id","cohort","mode","rep","status","elapsed_s","verified_cubes","cuber_gate")}),flush=True)
    need(len(rr)==len(cases[k::SHARDS])*2*2,"incomplete shard")
    print("AMDS_SHARD_PASS",k,len(rr),flush=True)

def audit():
    cases=load();sha_to_case={x["sha256"]:x for x in cases}
    rr=[]
    for k in range(SHARDS):
        rows=json.loads((ROOT/("shard-%d.json"%k)).read_text())
        need(len(rows)==len(cases[k::SHARDS])*2*2,"incomplete shard "+str(k))
        rr+=rows
    need(len(rr)==96,"not 96 attempts")
    by={}
    for row in rr:
        need(row["source_sha256"] in sha_to_case and row["id"]==sha_to_case[row["source_sha256"]]["id"],"source mismatch")
        key=(row["source_sha256"],row["rep"],row["mode"])
        need(key not in by,"duplicate")
        by[key]=row
        need(abs(row["par2_s"]-(60 if row["status"]=="TIMEOUT" else row["elapsed_s"]))<1e-5,"PAR2 invalid")
        if row["verified_cubes"]:need(row["cube_complete_cover"],"cube incompleteness")
    need(len(by)==96,"unpaired")
    for c in cases:
        for rep in range(REPS):
            pair=[by[(c["sha256"],rep,m)] for m in MODES]
            need(len({x["status"] for x in pair if x["status"]!="TIMEOUT"})<=1,"contradictory results")
    totals={}
    for cohort in ("all","new_seed_synthetic","reused_synthetic_control","reused_external_original"):
        totals[cohort]={}
        for mode in MODES:
            vals=[x for x in rr if x["mode"]==mode and (cohort=="all" or x["cohort"]==cohort)]
            totals[cohort][mode]=dict(attempts=len(vals),solved=sum(x["status"]!="TIMEOUT" for x in vals),
                 par2_s=round(sum(x["par2_s"] for x in vals),6),
                 cubed=sum(x["verified_cubes"]>0 for x in vals),
                 fallback=sum(x["mode"]=="alpha_mallob_drnas_si" and not x["verified_cubes"] for x in vals))
    report=dict(protocol=PROTO,source_manifest_sha=EXPECTED_MANIFEST,
                actual_AlphaMapleSAT_upstream=True,actual_MallobSat_backend=True,
                shared_policy="deterministic_structural_priority",UNSAT_independent_proof=False,
                same_24_SHA_reused_originals_not_blind=True,attempts=len(rr),status="AUDIT_PASS",
                totals=totals)
    store(ROOT/"report.json",report)
    store(ROOT/"all-trials.json",rr)
    print("AMDS_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.mode=="verify":print("AMDS_SOURCE_PASS",len(load()))
    elif a.mode=="shard":shard(a.shard)
    else:audit()

#!/usr/bin/env python3
"""Focused retrospective failure analysis. Only 3 previously seen original CNFs.
30s strict E2E cap, identical frozen binaries, single logical CPU per solver.
NOT a blind benchmark or a new integrated solver.
"""
import argparse, collections, hashlib, json, os, random, sys, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
import importlib.util
# Both historical runners import a module named "benchmark". Load the frozen
# base under that exact name before loading the plus10 module under a unique name.
spec_base=importlib.util.spec_from_file_location(
    "benchmark", ROOT/"research/unified_evidence/benchmark.py")
base=importlib.util.module_from_spec(spec_base)
sys.modules["benchmark"]=base
spec_base.loader.exec_module(base)
spec_plus=importlib.util.spec_from_file_location(
    "plus10_diagnostic_runner", ROOT/"research/par2_plus10/benchmark.py")
plus=importlib.util.module_from_spec(spec_plus)
sys.modules["plus10_diagnostic_runner"]=plus
spec_plus.loader.exec_module(plus)

CAP=30.0
REPS=2
TARGETS=(("SAT2025",13),("SAT2026",25),("SAT2026",31))
ARMS=("X59_MATH5_VERIPB","X59_OFF","CXX_UNION","Kissat","CaDiCaL","CryptoMiniSat")
OUT=ROOT/"results/par2_targeted_probe"
plus.CAP=CAP
plus.base.CAP=CAP
plus.m5.CAP=CAP

def digest(p):
    return plus.base.sha(p)

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def select():
    data=plus.sources()
    return [next(x for x in data[era] if x["id"]==idx) for era,idx in TARGETS]

def features(source):
    path=ROOT/source["path"]
    lengths=collections.Counter()
    polar=collections.Counter()
    declared=None
    count=0
    max_len=0
    lits=[]
    with path.open(errors="strict") as inp:
        for line in inp:
            tokens=line.split()
            if not tokens or tokens[0] in ("c","%"):continue
            if tokens[0]=="p":
                assert len(tokens)==4 and tokens[1]=="cnf"
                declared=tuple(map(int,tokens[2:]))
                continue
            for word in tokens:
                lit=int(word)
                if lit:
                    lits.append(lit)
                else:
                    lengths[min(len(lits),10)]+=1
                    polar["positive_only" if all(l>0 for l in lits) else
                          "negative_only" if all(l<0 for l in lits) else "mixed"]+=1
                    max_len=max(max_len,len(lits))
                    count+=1
                    lits=[]
    assert not lits and declared is not None and count==declared[1]
    return dict(sha256=source["sha256"],bytes=path.stat().st_size,
                declared_vars=declared[0],declared_clauses=declared[1],
                parsed_clauses=count,clause_lengths_capped10=dict(lengths),
                polarity=dict(polar),max_clause_length=max_len)

def prepare():
    plus.base.affinity()
    srcs=select()
    pinned=plus.base.pinned()
    proof_controls=plus.m5.proof_preflight()
    metadata={f"{s['era']}:{s['id']}":features(s) for s in srcs}
    p=dict(protocol="DRNAS-TARGETED-FAILURE-ANALYSIS-V1",
        code_git_sha=os.environ.get("GITHUB_SHA"),script_sha=digest(Path(__file__)),
        source_manifest_sha2025=digest(plus.MANIFEST25),
        source_manifest_sha2026=digest(plus.base.DATA/"manifest.json"),
        binary_sha256=pinned,target_ids=TARGETS,arms=ARMS,reps=REPS,cap_s=CAP,
        expected_trials=len(TARGETS)*REPS*len(ARMS),
        original_cnf_features=metadata,proof_controls=proof_controls,
        strictly_retrospective=True,no_main_promotion=True,
        same_machine_sequential_one_cpu=True)
    save(OUT/"protocol.json",p)
    print("TARGETED_READY "+json.dumps(dict(sources=len(srcs),
        trials=p["expected_trials"],sources_meta=metadata),sort_keys=True),flush=True)

def verify():
    plus.base.affinity()
    proto=json.loads((OUT/"protocol.json").read_text())
    assert proto["protocol"]=="DRNAS-TARGETED-FAILURE-ANALYSIS-V1"
    assert proto["script_sha"]==digest(Path(__file__))
    assert proto["code_git_sha"]==os.environ.get("GITHUB_SHA")
    assert proto["binary_sha256"]==plus.base.pinned()
    assert proto["source_manifest_sha2025"]==digest(plus.MANIFEST25)
    assert proto["source_manifest_sha2026"]==digest(plus.base.DATA/"manifest.json")
    assert proto["cap_s"]==CAP and proto["reps"]==REPS
    return proto

def shard(i):
    assert 0<=i<len(TARGETS)
    p=verify()
    s=select()[i]
    folder=OUT/f"shard-{i}"
    folder.mkdir(parents=True,exist_ok=False)
    out=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(f"targeted:{s['sha256']}:{rep}").shuffle(order)
        snapshot={}
        for arm in order:
            row=plus.test_one(s,arm,rep)
            out.append(row)
            with (folder/"trials.jsonl").open("a") as log:
                log.write(json.dumps(row,sort_keys=True)+"\n")
                log.flush()
            snapshot[arm]=dict(
                status=row["status"],
                strict_e2e_s=row["PAR2_strict_s"],
                solver_s=row.get("solver_s"),
                checker_s=row.get("checker_s"),
                reason=row.get("reason"),
                certificate_kind=row.get("certificate_kind"))
        print("TARGETED_REP "+json.dumps(dict(era=s["era"],id=s["id"],
            rep=rep,results=snapshot),sort_keys=True),flush=True)
    assert len(out)==REPS*len(ARMS)
    print("TARGETED_SHARD "+json.dumps(dict(shard=i,era=s["era"],id=s["id"],
        trials=len(out)),sort_keys=True),flush=True)

def report():
    p=verify()
    src=select()
    rows=[]
    for i in range(len(TARGETS)):
        path=OUT/f"shard-{i}"/"trials.jsonl"
        assert path.is_file()
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    keys={(r["era"],r["id"],r["arm"],r["rep"]) for r in rows}
    expected={(s["era"],s["id"],a,r) for s in src for a in ARMS for r in range(REPS)}
    assert keys==expected and len(rows)==len(expected)
    critical=[dict(era=r["era"],id=r["id"],arm=r["arm"],status=r["status"])
              for r in rows if r["critical"]]
    for r in rows:
        assert r["source_sha256"]==next(s["sha256"] for s in src
            if s["era"]==r["era"] and s["id"]==r["id"])
        assert not r["strict_accepted"] or (
            r["accepted"] and r["certificate_kind"] in plus.STRICT
            and r["e2e_s"]<=CAP)
    cases=[]
    for s in src:
        rr=[r for r in rows if r["era"]==s["era"] and r["id"]==s["id"]]
        decisions={r["status"].split("_")[0] for r in rr if r["strict_accepted"]}
        if len(decisions)>1:critical.append(("CONTRADICTORY_SAT_UNSAT",s["era"],s["id"]))
        cases.append(dict(era=s["era"],id=s["id"],sha256=s["sha256"],
           arms={arm:dict(
               strict_verified=sum(bool(r["strict_accepted"]) for r in rr if r["arm"]==arm),
               strict_par2_s=round(sum(r["PAR2_strict_s"] for r in rr if r["arm"]==arm),6),
               status=list(r["status"] for r in rr if r["arm"]==arm),
               solver_s=list(r.get("solver_s") for r in rr if r["arm"]==arm),
               checker_s=list(r.get("checker_s") for r in rr if r["arm"]==arm))
              for arm in ARMS}))
    summary=dict(status="FAIL" if critical else "COMPLETE",cases=cases,
        critical=critical,protocol=p,attempts=len(rows),
        scope="RETROSPECTIVE targeted failures, no new holdout or general improvement")
    save(OUT/"final.json",summary)
    print("TARGETED_FINAL "+json.dumps(dict(status=summary["status"],
        cases=cases,critical=critical,attempts=len(rows)),sort_keys=True),flush=True)
    if critical:raise SystemExit(1)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","shard","report"])
    parser.add_argument("--index",type=int)
    a=parser.parse_args()
    {"prepare":prepare,"shard":lambda:shard(a.index),"report":report}[a.action]()

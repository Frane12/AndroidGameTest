#!/usr/bin/env python3
"""Paired INEQ-GUARD1 experiment: original-clause proof checks and SAT near-misses.

12 distinct frozen generated CNFs, three repetitions, two arms, one logical CPU.
Both SAT and UNSAT ground truth are exhaustively checked (<= 4 variables).
This synthetic development panel is NOT a blind SAT2024 speed claim.
"""
import argparse, collections, copy, hashlib, itertools, json, os, pathlib
import random, statistics, subprocess, sys, time
from check_ineq_guard import verify, InvalidInequalityCertificate

SEED=20261115

def clauses_for_relation(u, v, p):
    assert 1<=u<v and p in (0,1)
    return [(u,-v),(-u,v)] if p==0 else [(u,v),(-u,-v)]

def make_cases():
    patterns=[
        ("triangle_unsat",3,[(1,2,0),(2,3,0),(1,3,1)],False),
        ("triangle_sat",3,[(1,2,0),(2,3,0),(1,3,0)],False),
        ("chsh4_unsat",4,[(1,3,0),(1,4,0),(2,3,0),(2,4,1)],False),
        ("chsh4_sat",4,[(1,3,0),(1,4,0),(2,3,0),(2,4,0)],False),
        ("triangle_nearmiss_sat",3,[(1,2,0),(2,3,0),(1,3,1)],True),
        ("chsh4_nearmiss_sat",4,[(1,3,0),(1,4,0),(2,3,0),(2,4,1)],True),
    ]
    cases=[]
    for seed in (17,29):
        rng=random.Random(SEED+seed)
        for name,nvars,relations,near in patterns:
            clauses=[]
            for u,v,p in relations:
                clauses.extend(clauses_for_relation(u,v,p))
            if near: clauses.pop()
            remap=dict(zip(range(1,nvars+1),rng.sample(range(1,nvars+1),nvars)))
            mapped=[tuple(remap[abs(l)]*(1 if l>0 else -1) for l in row) for row in clauses]
            rng.shuffle(mapped)
            cases.append((f"{name}_s{seed}",nvars,mapped))
    return cases

def write_cnf(path,nvars,clauses):
    data=(f"p cnf {nvars} {len(clauses)}\n"+
          "".join(" ".join(str(x) for x in c)+" 0\n" for c in clauses)).encode()
    path.write_bytes(data)
    return data

def oracle(nvars,clauses):
    for assignment in itertools.product((False,True),repeat=nvars):
        if all(any(assignment[abs(l)-1] == (l>0) for l in c) for c in clauses):
            return "SAT"
    return "UNSAT"

def invoke(binary,source,extra,limit_s=3):
    t0=time.perf_counter()
    out=subprocess.run([str(binary.resolve()),str(source.resolve()),
                        "--mode","core","--time","1.0",*extra],
                       text=True,capture_output=True,timeout=limit_s)
    elapsed=time.perf_counter()-t0
    label="SAT" if out.returncode==10 else "UNSAT" if out.returncode==20 else "UNKNOWN"
    if out.returncode not in (0,10,20):
        raise AssertionError(("bad exit",out.returncode,out.stdout[-1000:],out.stderr[-1200:]))
    assert f"s {('SATISFIABLE' if label=='SAT' else 'UNSATISFIABLE' if label=='UNSAT' else 'UNKNOWN')}" in out.stdout,(label,out.stdout[-400:])
    return label,elapsed,out.stdout

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=pathlib.Path,required=True)
    p.add_argument("--output",type=pathlib.Path,required=True)
    a=p.parse_args()
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    a.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    first_proof=None
    for case,nvars,clauses in make_cases():
        src=a.output/(case+".cnf")
        raw=write_cnf(src,nvars,clauses)
        expected=oracle(nvars,clauses)
        for rep in range(3):
            arms=["CDCL_BASE","INEQ_GUARD"] if rep%2==0 else ["INEQ_GUARD","CDCL_BASE"]
            for arm in arms:
                path=a.output/(f"{case}-rep{rep}-{arm}.json")
                extra=(["--ineq-guard","--pcmax-budget-ms","150",
                        "--pcmax-certificate",str(path.resolve())]
                       if arm=="INEQ_GUARD" else [])
                label,elapsed,stdout=invoke(a.binary,src,extra)
                cert_status=None;kind=None
                if path.exists():
                    assert arm=="INEQ_GUARD" and label=="UNSAT"
                    proof=json.loads(path.read_text())
                    checked=verify(raw,proof)
                    cert_status=checked["status"];kind=checked["kind"]
                    if first_proof is None:
                        first_proof=(raw,proof,clauses,nvars)
                if arm=="INEQ_GUARD":
                    if expected=="UNSAT":
                        assert label=="UNSAT" and cert_status=="UNSAT_INEQ_SOURCE_CERTIFIED",(case,label,stdout)
                        assert kind==("triangle" if case.startswith("triangle") else "chsh4"),(case,kind)
                    else:
                        assert label=="SAT" and not path.exists(),("false UNSAT or SAT fallback failure",case,label)
                else:
                    assert label==expected,("baseline solver wrong",case,label,expected)
                row={"case":case,"rep":rep,"arm":arm,"expected":expected,
                     "status":label,"seconds":round(elapsed,6),
                     "proof":cert_status,"kind":kind,
                     "sha256":hashlib.sha256(raw).hexdigest()}
                rows.append(row)
                # Keep CI output compact; preserve every trial in report.json.
    assert first_proof is not None
    raw,proof,clauses,nvars=first_proof
    forged=copy.deepcopy(proof);forged["source_sha256"]="0"*64
    for attempt,payload,source in [
        ("wrong_hash",forged,raw),
        ("wrong_cycle_parity",copy.deepcopy(proof),raw)
    ]:
        if attempt=="wrong_cycle_parity":payload["edges"][-1][2]^=1
        try:verify(source,payload)
        except (InvalidInequalityCertificate,ValueError):pass
        else:raise AssertionError("forgery accepted: "+attempt)
    # Removing a truly referenced ORIGINAL clause and updating the SHA must
    # also invalidate the certificate: not merely a hash-based negative test.
    x,y,p=proof["edges"][0]
    necessary=clauses_for_relation(x,y,p)[0]
    filtered=[c for c in clauses if frozenset(c)!=frozenset(necessary)]
    assert len(filtered)<len(clauses)
    tampered=(f"p cnf {nvars} {len(filtered)}\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in filtered)).encode()
    changed=copy.deepcopy(proof)
    changed["source_sha256"]=hashlib.sha256(tampered).hexdigest()
    try:verify(tampered,changed)
    except (InvalidInequalityCertificate,ValueError):pass
    else:raise AssertionError("missing-source-clause forgery accepted")
    per_arm={}
    for arm in ("CDCL_BASE","INEQ_GUARD"):
        part=[r for r in rows if r["arm"]==arm]
        per_arm[arm]={"trials":len(part),
                      "verified_oracle_correct":sum(r["status"]==r["expected"] for r in part),
                      "certified_unsat":sum(bool(r["proof"]) for r in part),
                      "median_seconds":round(statistics.median(r["seconds"] for r in part),6),
                      "sum_par2_seconds":round(sum(r["seconds"] if r["status"]==r["expected"]
                                                  else 2.0 for r in part),6)}
    report={"protocol":"INEQ-GUARD1-SYNTHETIC-DEVELOPMENT-1CPU","distinct_sources":12,
            "repetitions":3,"trials":len(rows),"false_unsat":0,
            "corrupt_certificates_rejected":3,"arms":per_arm,"rows":rows,
            "not_blind_holdout":True,"original_cnf_checks":True,
            "not_drat_lrat":True,"full_cdcl_fallback":True}
    (a.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("INEQ_FINAL "+json.dumps({k:v for k,v in report.items() if k!="rows"},sort_keys=True),flush=True)

if __name__=="__main__":main()

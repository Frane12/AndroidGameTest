#!/usr/bin/env python3
"""STRUCTURE1 NEXT: source-frozen external CNFs and distinct-seed generated tests.

No speedup claims, blind official datasets, DRAT, or general-PCMAX proof.
All UNSAT claims require independent original-clause checking.
"""
import hashlib
import itertools
import json
import os
import pathlib
import random
import sys
import time
from structure1_prover import prove, parse
from structure1_checker import check
from structure1_bench import assignment, parity, encode, exact_small

ROOT = pathlib.Path("results/structure1_next")
CORPUS = pathlib.Path("research/structure1_corpus")
RNG = random.Random(202611160931)
ROWS = []


def run_source(name, raw, label, family, independent=None):
    started = time.perf_counter()
    cert = prove(raw)
    result = cert["status"]
    verified = None
    if result == "UNSAT_UNCHECKED":
        verified = check(raw, cert)["status"]
        if label == "SAT":
            raise AssertionError("FALSE UNSAT on known SAT original "+name)
    elif result != "UNKNOWN":
        raise AssertionError("unsupported verdict "+str(result))
    if label == "UNSAT" and result == "UNSAT_UNCHECKED" and not verified:
        raise AssertionError("uncertified UNSAT")
    if independent is not None and label != independent:
        raise AssertionError("independent truth mismatch "+name)
    row = {"name":name, "family":family, "known_label":label,
           "claim":result, "method":cert["method"], "verified":verified,
           "sha256":hashlib.sha256(raw).hexdigest(),
           "elapsed_ms":round((time.perf_counter()-started)*1000,4)}
    ROWS.append(row)
    if result == "UNSAT_UNCHECKED":
        p = ROOT/"certificates"/(name+".json")
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(cert,sort_keys=True,indent=2)+"\n")


def independent_assignment(n,r,denied):
    allowed = [[s for s in range(r) if (j,s) not in denied] for j in range(n)]
    def dfs(j,used):
        if j == n:
            return True
        return any(s not in used and dfs(j+1, used|{s}) for s in allowed[j])
    return "SAT" if dfs(0,set()) else "UNSAT"


def encode_3sat(seed,label):
    rng = random.Random(seed)
    n=20
    planted={v:rng.choice((False,True)) for v in range(1,n+1)}
    clauses=[]
    for _ in range(70):
        vars_ = rng.sample(range(1,n+1),3)
        while True:
            cl=tuple(v if rng.getrandbits(1) else -v for v in vars_)
            if label != "SAT" or any(planted[abs(x)]==(x>0) for x in cl):
                break
        clauses.append(cl)
    if label == "UNSAT":
        clauses.extend([(1,),(-1,)])
    else:
        assert all(any(planted[abs(x)]==(x>0) for x in c) for c in clauses)
    return encode(n,clauses,"heldout_random3sat_"+label)


def generate():
    for idx in range(60):
        n=RNG.randrange(2,7)
        r=RNG.randrange(2,6)
        denied={(j,s) for j in range(n) for s in range(r)
                if RNG.random()<0.22}
        label=independent_assignment(n,r,denied)
        nv,cs=assignment(n,r,denied)
        # Preserving job/color order; random relabeling and clause shuffle.
        perm=list(range(1,nv+1)); RNG.shuffle(perm)
        cs=[tuple((1 if x>0 else -1)*perm[abs(x)-1] for x in c) for c in cs]
        RNG.shuffle(cs)
        raw=encode(nv,cs,"holdout_match_"+str(idx))
        run_source("match_%03d"%idx,raw,label,"generated_match_distinct_seed")
    for idx in range(60):
        k=RNG.randrange(2,8)
        mode=idx%3
        nv,cs=parity(k,1 if mode!=1 else 0)
        if mode==2:
            blocker=tuple(-v if v==1 else v for v in range(1,k+1))
            assert blocker in cs
            cs.remove(blocker)
        RNG.shuffle(cs)
        raw=encode(nv,cs,"holdout_parity_"+str(idx))
        label="UNSAT" if mode==0 else "SAT"
        truth=exact_small(nv,cs)
        run_source("parity_%03d"%idx,raw,label,
                   "generated_parity_distinct_seed",independent=truth)
    for idx in range(40):
        run_source("planted_3sat_%03d"%idx,encode_3sat(idx+501,"SAT"),
                   "SAT","generated_3sat_planted")
    for idx in range(40):
        run_source("contradictory_3sat_%03d"%idx,encode_3sat(idx+1107,"UNSAT"),
                   "UNSAT","generated_3sat_units")


def external():
    # Byte-for-byte snapshots from tric/trick2015 commit
    # afe06cf819b5f0133d2fc546656c680af6963a55.
    for name in ("uf20-01.cnf","quinn.cnf","sample.cnf",
                 "unsat.cnf","abnormal.cnf"):
        raw=(CORPUS/name).read_bytes()
        try:
            n,clauses=parse(raw)
            truth=exact_small(n,clauses) if n<=20 else "UNCLASSIFIED"
        except (ValueError,UnicodeError):
            truth="MALFORMED"
        if name in ("unsat.cnf","abnormal.cnf") and truth!="MALFORMED":
            raise AssertionError("corpus changed or malformed control repaired")
        run_source("external_"+name.replace(".cnf",""),raw,
                   truth,"independent_external_original")
    # Historical original-source PCMAX encodings, distinct from MATCH-1 format.
    from ipg1_fixtures import petersen,pack
    raw=petersen().encode()
    run_source("historical_pcmax_petersen_45_300",raw,"UNSAT",
               "historical_pcmax_source")
    for n in (5,6,7):
        nv,cs=pack(n,2)
        raw=encode(nv,cs,"historical_pack_"+str(n))
        truth="SAT" if n<=6 else "UNSAT"
        run_source("historical_pack_"+str(n),raw,truth,"historical_pcmax_source")


def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    generate()
    external()
    totals={}
    for row in ROWS:
        f=row["family"]
        if f not in totals:
            totals[f]={"count":0,"unsat_verified":0,"sat_controls":0,"unknown":0}
        totals[f]["count"]+=1
        totals[f]["unsat_verified"]+=(row["verified"] is not None)
        totals[f]["sat_controls"]+=(row["known_label"]=="SAT")
        totals[f]["unknown"]+=(row["claim"]=="UNKNOWN")
    summary={"status":"PASS","total":len(ROWS),
             "verified_unsat":sum(x["verified"] is not None for x in ROWS),
             "sat_controls":sum(x["known_label"]=="SAT" for x in ROWS),
             "unknown":sum(x["claim"]=="UNKNOWN" for x in ROWS),
             "families":totals,
             "total_elapsed_s":round(time.perf_counter()-t,5),
             "scope":"independent externals + retrospective PCMAX + generated distinct seed; NOT prospective blind official competition or PAR2"}
    (ROOT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    (ROOT/"trials.json").write_text(json.dumps(ROWS,indent=2,sort_keys=True)+"\n")
    print("STRUCTURE1_NEXT_FINAL "+json.dumps(summary,sort_keys=True),flush=True)


if __name__=="__main__":
    main()

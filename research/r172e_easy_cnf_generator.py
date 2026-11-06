#!/usr/bin/env python3
"""R172E: 24 reproducible SMALL synthetic CNFs for calibrated paired timing.

These are NOT unseen official SAT competition benchmarks. Formula generation
is entirely seed-frozen, independent of solver outcomes, and source SHA-256
is committed to a run-local manifest before measurements begin.
"""
import argparse, hashlib, itertools, json, pathlib, random

ROOT=pathlib.Path("r172e/frozen")
SEED=202611060417
COUNT=24

def xor3(clauses,vs,rhs):
    # Forbid assignments with the wrong three-variable parity.
    assert len(vs)==3 and len(set(vs))==3
    for bits in itertools.product((0,1),repeat=3):
        if (sum(bits)&1)!=rhs:
            clauses.append(tuple(-v if bit else v for v,bit in zip(vs,bits)))

def satisfied_random_clause(rng,model,n,k=3,force=None):
    vs=rng.sample(range(1,n+1),k) if force is None else [force]+rng.sample(
        [v for v in range(1,n+1) if v!=force],k-1)
    lits=tuple(v if rng.getrandbits(1) else -v for v in vs)
    if not any((lit>0)==bool(model[abs(lit)]) for lit in lits):
        v=lits[0]
        lits=((abs(v) if model[abs(v)] else -abs(v)),)+lits[1:]
    return lits

def make_case(i):
    rng=random.Random(SEED+104729*i)
    clauses=[]
    if i<6:
        cohort="planted_3sat"
        expected="SAT"
        n=42+7*i
        model={v:rng.randrange(2) for v in range(1,n+1)}
        for _ in range(3*n+int(0.65*n)):
            clauses.append(satisfied_random_clause(rng,model,n))
    elif i<12:
        cohort="pigeonhole_unsat"
        expected="UNSAT"
        p=5+(i-6)
        h=p-1
        n=p*h
        def var(a,b):return a*h+b+1
        for a in range(p):
            clauses.append(tuple(var(a,b) for b in range(h)))
            for b in range(h):
                for c in range(b+1,h):
                    clauses.append((-var(a,b),-var(a,c)))
        for b in range(h):
            for a in range(p):
                for c in range(a+1,p):
                    clauses.append((-var(a,b),-var(c,b)))
    elif i<18:
        cohort="mixed_xor_sat"
        expected="SAT"
        n=32+6*(i-12)
        model={v:rng.randrange(2) for v in range(1,n+1)}
        equation_vars=set()
        for _ in range(4+(i-12)):
            vs=sorted(rng.sample(range(1,n+1),3))
            equation_vars.update(vs)
            xor3(clauses,vs,model[vs[0]]^model[vs[1]]^model[vs[2]])
        for _ in range(2*n):
            clauses.append(satisfied_random_clause(rng,model,n,3))
        # Ensure exact XOR rows have a connection into residual AND/OR CNF.
        for v in sorted(equation_vars):
            clauses.append(satisfied_random_clause(rng,model,n,3,force=v))
    else:
        cohort="mixed_xor_unsat"
        expected="UNSAT"
        n=30+5*(i-18)
        # E1 XOR E2 XOR E3 entails x5=0. A source unit fixes x5=1.
        xor3(clauses,(1,2,3),0)
        xor3(clauses,(1,2,4),0)
        xor3(clauses,(3,4,5),0)
        clauses.append((5,))
        # Remaining non-XOR CNF has a common all-false satisfying model.
        zero={v:0 for v in range(1,n+1)}
        for _ in range(n):
            clauses.append(satisfied_random_clause(rng,zero,n))
        for v in (1,2,3,4,5):
            clauses.append(satisfied_random_clause(rng,zero,n,3,force=v))
    if not clauses:
        raise RuntimeError("no clauses")
    if max(abs(v) for c in clauses for v in c)>n:
        raise RuntimeError("CNF variable range")
    text=(f"c DRNAS R172E synthetic seed {SEED} index {i} cohort {cohort}\n"
          +f"p cnf {n} {len(clauses)}\n"
          +"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return dict(id=f"easy-{i:02d}",cohort=cohort,expected=expected,
                index=i,variables=n,clauses=len(clauses),
                sha256=hashlib.sha256(text.encode()).hexdigest()),text

def generate(root=ROOT):
    root=pathlib.Path(root)
    root.mkdir(parents=True,exist_ok=True)
    records=[]
    for i in range(COUNT):
        rec,data=make_case(i)
        p=root/(rec["id"]+".cnf")
        if p.exists() and p.read_bytes()!=data.encode():
            raise RuntimeError("R172E original CNF changed "+rec["id"])
        p.write_text(data)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=rec["sha256"]:
            raise RuntimeError("R172E source SHA failure")
        records.append(rec)
    if len({c["sha256"] for c in records})!=COUNT:
        raise RuntimeError("R172E duplicate original CNF")
    manifest=dict(protocol="R172E-DETERMINISTIC-EASY-CNF-20261106-v1",
                  synthetic=True,not_blind=True,seed=SEED,cohort_counts={
                    cohort:sum(c["cohort"]==cohort for c in records)
                    for cohort in sorted(set(c["cohort"] for c in records))},
                  cases=records)
    path=root/"manifest.json"
    data=json.dumps(manifest,sort_keys=True,indent=2)+"\n"
    if path.exists() and path.read_text()!=data:
        raise RuntimeError("R172E manifest drift")
    path.write_text(data)
    print("R172E_EASY_SOURCE_SHA_PASS",json.dumps(dict(seed=SEED,
          cases=len(records),cohorts=manifest["cohort_counts"],
          manifest_sha256=hashlib.sha256(data.encode()).hexdigest()),
          sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default=str(ROOT))
    a=ap.parse_args()
    generate(pathlib.Path(a.output))

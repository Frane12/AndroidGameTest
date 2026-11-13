#!/usr/bin/env python3
"""X5.3: exact small-oracle, unchanged-baseline and DRAT regression checks."""
from __future__ import annotations
import itertools, json, os, pathlib, random, subprocess, tempfile

X52="build/drnas-x52"
X53="build/drnas-x53"
TRIM="build/drat-trim"
POLICIES=("baseline","glue","utility")


def truth(clauses,n):
    return any(all(any(bits[abs(v)-1]==(v>0) for v in clause) for clause in clauses)
               for bits in itertools.product((False,True),repeat=n))


def verify(stdout,clauses):
    values={}
    try:
        for line in stdout.splitlines():
            if not line.startswith("v "): continue
            for word in line[2:].split():
                lit=int(word)
                if lit==0: continue
                if abs(lit) in values and values[abs(lit)]!=(lit>0): return False
                values[abs(lit)]=(lit>0)
        return all(any(values.get(abs(lit))==(lit>0) for lit in clause) for clause in clauses)
    except ValueError:
        return False


def one(path,clauses,expected,binary,policy,temp):
    proof=temp/(f"{policy}.drat")
    proof.unlink(missing_ok=True)
    cmd=[binary,str(path),"--mode","core","--time","1.0","--proof",str(proof),
         "--x52-proof-deletions","--stats"]
    if policy!="original":cmd+=["--x53-policy",policy]
    cp=subprocess.run(cmd,capture_output=True,text=True,timeout=3)
    assert cp.returncode==(10 if expected else 20),(
        policy,cp.returncode,cp.stderr[-700:])
    if expected:
        assert verify(cp.stdout,clauses),("bad SAT witness",policy)
    else:
        ck=subprocess.run([TRIM,str(path),str(proof)],
                          capture_output=True,text=True,timeout=3)
        assert ck.returncode==0 and "s VERIFIED" in ck.stdout, (
            "bad UNSAT proof",policy,ck.stdout[-600:],ck.stderr[-600:])
    stat={}
    for line in cp.stderr.splitlines():
        if line.startswith("X53_STATS "):stat=json.loads(line[10:])
    if policy!="original":
        assert stat.get("policy")==policy
        assert stat["live_learnt"]==stat["live_used"]+stat["live_unused"]
        assert stat["deleted_unused"]+stat["deleted_used"]<=stat["deleted_lbd_le2"]+stat["deleted_lbd_3to4"]+stat["deleted_lbd_5to8"]+stat["deleted_lbd_ge9"]
        assert stat["deleted_unused"]+stat["deleted_used"]==sum(
            stat["deleted_lbd_"+n] for n in ("le2","3to4","5to8","ge9"))
    base={}
    for line in cp.stderr.splitlines():
        if line.startswith("X41_STATS "):base=json.loads(line[10:])
    assert base
    return base,stat


def main():
    assert all(pathlib.Path(p).is_file() for p in (X52,X53,TRIM))
    rng=random.Random(531113)
    count_sat=count_unsat=0
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d);f=root/"test.cnf"
        for k in range(44):
            n=5+k%5
            clauses=[]
            for _ in range(4*n+(k%13)):
                width=2+(k%2)
                vs=rng.sample(range(1,n+1),width)
                clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
            if k%11==0:clauses.extend([(1,),(-1,)])
            expected=truth(clauses,n)
            count_sat+=expected;count_unsat+=not expected
            f.write_text(f"p cnf {n} {len(clauses)}\n"+
                         "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            control,_=one(f,clauses,expected,X52,"original",root)
            baseline,_=one(f,clauses,expected,X53,"baseline",root)
            # Audit mode is observer-only. It must produce IDENTICAL search
            # counters, not merely the same final SAT/UNSAT status.
            for key in ("decisions","conflicts","learnt","propagations","reduce_removed"):
                assert control[key]==baseline[key],(k,key,control[key],baseline[key])
            for policy in ("glue","utility"):
                one(f,clauses,expected,X53,policy,root)
    assert count_sat>0 and count_unsat>0
    print("X53_SELFTEST_PASS "+json.dumps({
        "sources":44,"executions":176,"SAT_cases":count_sat,
        "UNSAT_cases":count_unsat,"identical_original_baseline_traces":True,
        "checked_UNSAT_proofs":count_unsat*4
    },sort_keys=True))


if __name__=="__main__":
    main()

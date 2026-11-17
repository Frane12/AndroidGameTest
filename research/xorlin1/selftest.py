#!/usr/bin/env python3
"""GF2 select-subset controls, non-degree2 proof and explicit SAT controls."""
from collections import Counter
from itertools import product,combinations
from pathlib import Path
import hashlib,json,os,random,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from extract import parse,derive,recover_xors
from emit_veripb import compile_source

VERIPB=ROOT/"veripb-tool/bin/veripb"

def dimacs(clauses):
    nv=max(abs(v) for clause in clauses for v in clause)
    return (f"p cnf {nv} {len(clauses)}\n"+
            "".join(" ".join(map(str,row))+" 0\n" for row in clauses)).encode()

def encode(rows,seed):
    r=random.Random(seed)
    clauses=[]
    for variables,rhs in rows:
        for bits in product((0,1),repeat=len(variables)):
            if sum(bits)%2!=rhs:
                literals=[-v if b else v for v,b in zip(variables,bits)]
                r.shuffle(literals)
                clauses.append(tuple(literals))
    r.shuffle(clauses)
    return dimacs(clauses)

def all_false_sat(raw):
    _,clauses=parse(raw)
    return all(any(v<0 for v in c) for c in clauses)

def check(raw,cert,folder,name):
    proof,meta=compile_source(raw,cert)
    source=folder/(name+".cnf")
    pb=folder/(name+".pbp")
    source.write_bytes(raw);pb.write_text(proof)
    chk=subprocess.run([str(VERIPB),"--cnf",str(source),str(pb)],
            capture_output=True,text=True,timeout=20)
    assert chk.returncode==0 and (
        "s VERIFIED UNSATISFIABLE" in chk.stdout+chk.stderr),(
        "EXTERNAL_VERIPB_REJECTED",name,chk.stdout[-1000:],chk.stderr[-1000:])
    return meta

def run():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    totals=Counter()
    with tempfile.TemporaryDirectory(prefix="xorlin1-safety-") as t:
        folder=Path(t)
        core=[((1,2,3),1),((3,4,5),0),((1,2,4,5),0)]
        unrelated=[((6,7,8),0),((8,9,10),0)]
        for seed in range(24):
            raw=encode(core+unrelated,seed)
            cert,report=derive(raw)
            assert cert is not None and len(cert["xor_rows"])==3
            assert report["complete_source_xor_rows"]==5
            assert report["selected_degrees"]=={2:5}
            check(raw,cert,folder,f"GF2-source-{seed}")
            totals["nontrivial_GF2_external_VERIPB"]+=1
            sat=encode([((1,2,3),0)]+core[1:]+unrelated,seed+200)
            assert all_false_sat(sat)
            assert derive(sat)[0] is None
            totals["satisfiable_parity_controls_UNKNOWN"]+=1
            _,clauses=parse(raw)
            original=frozenset((1,2,3))
            modified=[c for c in clauses if frozenset(c)!=original]
            assert len(modified)==len(clauses)-1
            tampered=dimacs(modified)
            assert all_false_sat(tampered)
            assert derive(tampered)[0] is None
            totals["SAT_missing_original_clause_UNKNOWN"]+=1
        # Ten K5 edge XOR rows; every source variable occurs FOUR times.
        edges=list(combinations(range(1,6),2))
        raw=encode([(edge,int(j==0)) for j,edge in enumerate(edges)],190)
        _,clauses=parse(raw)
        rows=recover_xors(clauses)
        assert len(rows)==10
        degree=Counter(v for row in rows for v in row["vars"])
        assert set(degree.values())=={4}
        manual={"format":"drnas-math5-eo-xor-unit-v1",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "xor_rows":rows,"exact_one_groups":[],"root_units":[]}
        check(raw,manual,folder,"all-degree4-original")
        totals["degree4_external_VERIPB"]+=1
        derived,report=derive(raw)
        assert derived and len(derived["xor_rows"])<10
        check(raw,derived,folder,"degree4-source-Gauss-subset")
        totals["degree4_Gauss_subselection_external_VERIPB"]+=1
        fake=dict(manual,source_sha256=hashlib.sha256(b"wrong source").hexdigest())
        try:compile_source(raw,fake)
        except (ValueError,TypeError,KeyError):totals["forged_SHA_rejected"]+=1
        else:raise AssertionError("UNSOUND_FAKE_SOURCE_SHA")
    assert totals==Counter({
      "nontrivial_GF2_external_VERIPB":24,
      "satisfiable_parity_controls_UNKNOWN":24,
      "SAT_missing_original_clause_UNKNOWN":24,
      "degree4_external_VERIPB":1,
      "degree4_Gauss_subselection_external_VERIPB":1,
      "forged_SHA_rejected":1})
    print("XORLIN1_SAFETY_PASS "+json.dumps(totals,sort_keys=True),flush=True)
if __name__=="__main__":run()

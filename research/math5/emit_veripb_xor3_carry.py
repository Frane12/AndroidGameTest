#!/usr/bin/env python3
"""Source-bound XOR3 carry => standard VeriPB 3.0 cutting planes.

Restricted conversion of independently checked MATH5 XOR-only certificates:
- every selected original XOR row has exactly 3 variables;
- every selected variable occurs EXACTLY TWICE among selected rows;
- XOR right-hand sides sum to odd parity (0=1);
- original source CNF must contain all four forbidden-assignment clauses.

For each XOR x+y+z=b (mod 2), introduce fresh carry t via redundant
extension (VeriPB RED): t=xyz if b=1, or t=MAJ(x,y,z) if b=0.
Derive integer equality x+y+z - 2t = b with source-backed RUP and CP,
sum all rows, divide by 2, and obtain 0 >= 1. The external VeriPB
checker must independently ACCEPT proof on unchanged original CNF;
this producer never declares UNSAT accepted on its own.

This is a standard known extension/cutting-planes mechanism, not a
polynomial proof for arbitrary SAT nor a new proof-complexity theorem.
No filename, family, expected status or prior solver outcomes are read.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
from check_math5 import verify as independent_original_source_verify

MAX_ROWS=512
MAX_STEPS=10000
MAX_PROOF_BYTES=5_000_000

def require(value, message):
    if not value:raise ValueError(message)

def ordered_cnf(raw):
    require(len(raw)<=12_000_000,"original CNF exceeds byte cap")
    nv=nc=None
    clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        toks=line.split()
        if not toks or toks[0]=="c":continue
        if toks[0]=="p":
            require(nv is None and len(toks)==4 and toks[1]=="cnf","bad DIMACS header")
            nv,nc=int(toks[2]),int(toks[3])
            require(0<nv<=6000 and 0<=nc<=100000,"original CNF size budget")
            continue
        require(nv is not None,"missing DIMACS header")
        for atom in toks:
            lit=int(atom)
            require(abs(lit)<=nv,"literal outside source DIMACS header")
            if lit:pending.append(lit)
            else:
                clauses.append(tuple(pending));pending=[]
    require(nv is not None and not pending and len(clauses)==nc,"DIMACS clause count mismatch")
    return nv,clauses

class Proof:
    def __init__(self,clauses):
        self.lines=["pseudo-Boolean proof version 3.0",f"f {len(clauses)} ;"]
        self.index={}
        for row_id,row in enumerate(clauses,1):
            self.index.setdefault(frozenset(row),row_id)
        self.last=len(clauses)
        self.steps=Counter()
    @staticmethod
    def clause(literals):
        return " ".join("1 "+("~" if v<0 else "")+"x"+str(abs(v))
                        for v in literals)+" >= 1"
    def red(self,literals,variable,setting):
        self.lines.append("red "+self.clause(literals)+
                          f" : x{variable} -> {setting} ;")
        self.last+=1;self.steps["RED"]+=1
        return self.last
    def rup(self,literals):
        self.lines.append("rup "+self.clause(literals)+" ;")
        self.last+=1;self.steps["RUP"]+=1
        return self.last
    def pol(self,operators):
        self.lines.append("pol "+" ".join(map(str,operators))+" ;")
        self.last+=1;self.steps["CP"]+=1
        return self.last
    def sum_constraints(self,ids):
        require(bool(ids),"empty CP sum")
        operators=[ids[0]]
        for source_id in ids[1:]:
            operators.extend((source_id,"+"))
        return self.pol(operators)

def compile_source(raw,certificate):
    start=time.perf_counter()
    checked=independent_original_source_verify(raw,certificate)
    require(checked.get("status")=="UNSAT_MATH5_CERTIFICATE_VERIFIED",
            "original-CNF checker did not verify source certificate")
    require(certificate.get("format")=="drnas-math5-eo-xor-unit-v1",
            "unsupported certificate format")
    require(not certificate.get("exact_one_groups") and
            not certificate.get("root_units"),
            "mixed exact-one/root unit: unsupported")
    rows=certificate.get("xor_rows")
    require(isinstance(rows,list) and 1<=len(rows)<=MAX_ROWS,
            "XOR row count cap")
    require(all(isinstance(r,dict) and
                isinstance(r.get("vars"),list) and
                len(r["vars"])==3 and
                r.get("forbidden_parity") in (0,1) and
                len(set(r["vars"]))==3 for r in rows),
            "only source-checked three-variable XOR rows supported")
    degree=Counter(var for r in rows for var in r["vars"])
    require(bool(degree) and set(degree.values())=={2},
            "selected original variables must occur exactly twice")
    total_rhs=sum(1-r["forbidden_parity"] for r in rows)
    require(total_rhs%2==1,"selected XOR equations do not contradict modulo two")
    nv,original=ordered_cnf(raw)
    p=Proof(original)
    lower_ids=[];upper_ids=[]
    extension=nv
    for row in rows:
        x,y,z=row["vars"]
        b=1-row["forbidden_parity"]
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)%2!=b:
                source_clause=frozenset(-v if bit else v
                                        for v,bit in zip((x,y,z),bits))
                require(source_clause in p.index,
                        "missing required XOR clause in unchanged original")
        extension+=1;t=extension
        if b==1:
            # Fresh t <-> x AND y AND z.
            fwd=[p.red((-t,v),t,0) for v in (x,y,z)]
            p.red((t,-x,-y,-z),t,1)
            src_alo=p.index[frozenset((x,y,z))]
            summed=p.sum_constraints(fwd)
            lower=p.pol((summed,2,"*",src_alo,"+",3,"d"))
            # Pairwise x=y=1 implies t=1, via RUP on original XOR
            # and the fresh t=xyz clauses.
            pairs=[p.rup((-a,-d,t)) for a,d in ((x,y),(x,z),(y,z))]
            summed=p.sum_constraints(pairs)
            upper=p.pol((summed,2,"d"))
        else:
            # Fresh t <-> majority(x,y,z). Allowed original parity
            # is 000,011,101,110, so sum(x)=2t.
            forward=[p.red((-t,a,d),t,0)
                     for a,d in ((x,y),(x,z),(y,z))]
            for a,d in ((x,y),(x,z),(y,z)):
                p.red((t,-a,-d),t,1)
            summed=p.sum_constraints(forward)
            lower=p.pol((summed,2,"d"))
            single=[p.rup((-v,t)) for v in (x,y,z)]
            summed=p.sum_constraints(single)
            src_no_111=p.index[frozenset((-x,-y,-z))]
            upper=p.pol((summed,2,"*",src_no_111,"+",3,"d"))
        lower_ids.append(lower)
        upper_ids.append(upper)
    # Derived for each row: S_i - 2t_i >= b_i and <= b_i.
    # Every selected original variable occurs twice, so after summing:
    # 2 sum(original x) - 2 sum(carry t) = odd number.
    # CP divide by 2, round both sides, add -> 0>=1.
    lo=p.sum_constraints(lower_ids)
    hi=p.sum_constraints(upper_ids)
    lo2=p.pol((lo,2,"d"))
    hi2=p.pol((hi,2,"d"))
    p.pol((lo2,hi2,"+"))
    p.lines.extend(("output NONE ;","conclusion UNSAT ;",
                    "end pseudo-Boolean proof ;"))
    require(sum(p.steps.values())<=MAX_STEPS,"proof step limit")
    proof="\n".join(p.lines)+"\n"
    require(len(proof.encode("ascii"))<=MAX_PROOF_BYTES,
            "emitted PBP exceeds bounded size")
    info={
        "status":"SOURCE_BOUND_VERIPB_EMITTED_EXTERNAL_CHECK_REQUIRED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "original_vars":nv,"original_clauses":len(original),
        "xor_rows":len(rows),"xor_variables":len(degree),
        "rhs_sum_odd":True,
        "fresh_carry_variables":len(rows),
        "steps":dict(p.steps),
        "proof_bytes":len(proof.encode("ascii")),
        "producer_elapsed_s":round(time.perf_counter()-start,6),
        "method":"3-XOR_CARRY_RED_RUP_CP_DIVISION",
        "checker_required":True,
        "no_CDCL":True,
        "retrospective_original6":True,
        "no_general_SAT_complexity_claim":True}
    return proof,info

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cnf",required=True,type=Path)
    ap.add_argument("--certificate",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--meta",type=Path)
    a=ap.parse_args()
    try:
        raw=a.cnf.read_bytes()
        cert=json.loads(a.certificate.read_text())
        proof,metadata=compile_source(raw,cert)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(proof)
        if a.meta:
            a.meta.write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n")
        print("MATH5_XOR3_VERIPB_EMITTED "+json.dumps(metadata,sort_keys=True),
              flush=True)
        return 0
    except (ValueError,TypeError,KeyError,IndexError,
            UnicodeError,OverflowError,OSError,AssertionError) as err:
        a.output.unlink(missing_ok=True)
        if a.meta:a.meta.unlink(missing_ok=True)
        print("MATH5_XOR3_VERIPB_UNSUPPORTED "+str(err),flush=True)
        return 2
if __name__=="__main__":
    raise SystemExit(main())

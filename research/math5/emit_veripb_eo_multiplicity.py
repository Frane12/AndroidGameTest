#!/usr/bin/env python3
"""Source-bound MATH5 exact-one multiplicity -> standard VeriPB 3.0 cutting planes.

A restricted compiler, NOT a generic conversion of MATH5 XOR/units to proof.
Every selected original EO clause and all pairwise AMO clauses are checked
by the independent MATH5 source checker first. For q groups, each selector
occurs exactly d>=2 times; if q % d != 0, sum EO equalities forces
d*sum(x)=q, impossible over integers.

Derive clique >= (k-1) on negated members with polynomial-size CP induction:
(k-2)*clique(k-1) + sum_{i<k}(~x_i + ~x_k >= 1)
followed by division (k-1). Separately add and divide all ALO and
all clique bounds by d, then sum for contradiction. No CDCL oracle.
The resulting .pbp is only accepted after EXTERNAL VeriPB 3.0.2 checks it
against the unchanged original CNF. NEVER trust emission alone.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
from check_math5 import verify as source_verify

def require(condition,message):
    if not condition:raise ValueError(message)

def ordered_clauses(raw):
    nv=expected=None;pending=[];clauses=[]
    require(len(raw)<=12000000,"source exceeds bounded size")
    for line in raw.decode("ascii").splitlines():
        row=line.split()
        if not row or row[0]=="c":continue
        if row[0]=="p":
            require(nv is None and len(row)==4 and row[1]=="cnf","bad DIMACS header")
            nv,expected=int(row[2]),int(row[3])
            require(0<nv<=6000 and 0<=expected<=100000,"source limit")
            continue
        require(nv is not None,"header missing")
        for t in row:
            v=int(t)
            require(abs(v)<=nv,"source literal outside header")
            if v:pending.append(v)
            else:
                clauses.append(tuple(pending));pending=[]
    require(nv is not None and not pending and len(clauses)==expected,"bad source clause count")
    return nv,clauses

def compile_source(raw,certificate):
    verified=source_verify(raw,certificate)
    require(verified.get("status")=="UNSAT_MATH5_CERTIFICATE_VERIFIED",
            "MATH5 checker did not accept original CNF")
    require(certificate.get("format")=="drnas-math5-eo-xor-unit-v1",
            "unknown MATH5 proof type")
    groups=certificate.get("exact_one_groups",[])
    require(type(groups)==list and len(groups)>=3 and len(groups)<=128,
            "unsupported selected EO group count")
    require(not certificate.get("xor_rows") and not certificate.get("root_units"),
            "mixed XOR/UP proof not supported by this standard exporter")
    require(all(type(g)==list and 3<=len(g)<=128 and all(type(v)==int and v>0 for v in g) for g in groups),
            "only positive exact-one groups supported")
    multiplicity=Counter(v for group in groups for v in group)
    degrees=set(multiplicity.values())
    require(len(degrees)==1,"multiplicity must be uniform")
    degree=next(iter(degrees))
    require(2<=degree<=32 and len(groups)%degree!=0,
            "no congruence contradiction for this group count/degree")
    nv,clauses=ordered_clauses(raw)
    source_index={}
    for i,c in enumerate(clauses,1):
        source_index.setdefault(frozenset(c),i)
    require(all(v<=nv for v in multiplicity),"selected literal outside DIMACS")
    proof=["pseudo-Boolean proof version 3.0",f"f {len(clauses)} ;"]
    last=len(clauses)
    upper_ids=[]
    for group in groups:
        require(len(set(group))==len(group),"duplicate group variable")
        require(frozenset(group) in source_index,"positive ALO missing")
        for a,b in itertools.combinations(group,2):
            require(frozenset((-a,-b)) in source_index,"pairwise AMO missing")
        previous=source_index[frozenset((-group[0],-group[1]))]
        for k in range(3,len(group)+1):
            new=group[k-1]
            ops=[str(previous)]
            if k-2!=1:ops.extend([str(k-2),"*"])
            for prior in group[:k-1]:
                ops.extend([str(source_index[frozenset((-prior,-new))]),"+"])
            ops.extend([str(k-1),"d"])
            proof.append("pol "+" ".join(ops)+" ;")
            last+=1
            previous=last
        upper_ids.append(previous)

    def sum_then_div(ids,divisor):
        nonlocal last
        require(bool(ids),"empty polynomial sum")
        ops=[str(ids[0])]
        for constraint in ids[1:]:
            ops.extend([str(constraint),"+"])
        ops.extend([str(divisor),"d"])
        proof.append("pol "+" ".join(ops)+" ;")
        last+=1
        return last
    lower_id=sum_then_div([source_index[frozenset(g)] for g in groups],degree)
    upper_id=sum_then_div(upper_ids,degree)
    proof.append(f"pol {lower_id} {upper_id} + ;")
    proof.extend(["output NONE ;","conclusion UNSAT ;","end pseudo-Boolean proof ;"])
    output="\n".join(proof)+"\n"
    require(len(output.encode())<=4000000,"generated PBP exceeds size budget")
    return output,{
        "status":"MATH5_VERIPB_EMITTED_EXTERNAL_VERIFICATION_REQUIRED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "source_variables":nv,"source_clauses":len(clauses),
        "selected_groups":len(groups),"uniform_occurrences":degree,
        "selected_variables":len(multiplicity),
        "proof_derived_pol_steps":last-len(clauses)+1,
        "proof_bytes":len(output.encode()),
        "method":"MATH5_EO_INTEGER_MULTIPLICITY_CUTTING_PLANES",
        "not_generic_xor_compiler":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--certificate",required=True,type=pathlib.Path)
    p.add_argument("--output",required=True,type=pathlib.Path)
    p.add_argument("--meta",type=pathlib.Path)
    a=p.parse_args()
    try:
        raw=a.cnf.read_bytes()
        cert=json.loads(a.certificate.read_text())
        pb,meta=compile_source(raw,cert)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(pb)
        if a.meta:
            a.meta.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
        print("MATH5_VERIPB_EMITTED "+json.dumps(meta,sort_keys=True),flush=True)
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,
            OverflowError,AssertionError,json.JSONDecodeError) as error:
        a.output.unlink(missing_ok=True)
        print("MATH5_VERIPB_UNSUPPORTED "+str(error),flush=True)
        return 2

if __name__=="__main__":raise SystemExit(main())

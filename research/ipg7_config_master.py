#!/usr/bin/env python3
"""IPG7 CONFIG-MASTER: global PCMAX incompatibility, no DPLL/CDCL search.

Source-bound mathematical research procedure for *direct* exactly-one
3-machine weighted packing CNF (n<=15). Exact source clauses are matched
to the complete minimal-overweight encoding (not names, labels or hashes).

If sum(weights)==3*T, EVERY solution must load EVERY machine exactly T.
Enumerate all exact-T job subsets by a bounded subset-sum profile (2^n).
If TWO such subsets are disjoint, the complement also loads T: return a
full SAT model, verified against original CNF.
If every two exact-T subsets INTERSECT, construct a DERIVED two-machine
configuration master with k choices per machine and k*k cross-machine
mutexes. The master is contradictory: all first-machine options exclude
ALL second-machine options. Emit a standard k+1-step pure cutting-plane
VeriPB proof on that DERIVED configuration master, no RUP, DPLL, CDCL.
The ORIGINAL-CNF implication is verified by an independent structural
checker, NOT by VeriPB directly on original source. Never mislabel
the master VeriPB proof as an original-CNF VeripB refutation.

Worst-case 2^n enumeration; no claim of P=NP or polynomial general PCMAX.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
import time
from collections import Counter

MAX_JOBS=15
MAX_CONFIGS=512
MAX_CLAUSES=25000

def read_dimacs(raw):
    nv=nclauses=None;clauses=[];partial=[]
    for lineno,line in enumerate(raw.decode("ascii").splitlines(),1):
        fields=line.split()
        if not fields or fields[0]=="c":continue
        if fields[0]=="p":
            if nv is not None or len(fields)!=4 or fields[1]!="cnf":
                raise ValueError("duplicate/invalid DIMACS header")
            nv,nclauses=int(fields[2]),int(fields[3])
            if nv<1 or nclauses<0 or nclauses>MAX_CLAUSES:
                raise ValueError("source exceeds bounded gates")
            continue
        if nv is None:raise ValueError("missing DIMACS header")
        for word in fields:
            lit=int(word)
            if abs(lit)>nv:raise ValueError(f"literal out of source range at {lineno}")
            if lit:partial.append(lit)
            else:
                clauses.append(tuple(partial))
                partial=[]
    if nv is None or partial or len(clauses)!=nclauses:
        raise ValueError("incomplete DIMACS clauses")
    return nv,clauses

def sums(weights):
    limit=1<<len(weights)
    out=[0]*limit
    for mask in range(1,limit):
        low=mask&-mask
        out[mask]=out[mask^low]+weights[low.bit_length()-1]
    return out

def expected_clauses(weights,capacity,loads):
    n=len(weights)
    x=lambda j,m:3*j+m+1
    result=[]
    for j in range(n):
        result.append((x(j,0),x(j,1),x(j,2)))
        for a,b in itertools.combinations(range(3),2):
            result.append((-x(j,a),-x(j,b)))
    for mask in range(1,1<<n):
        if loads[mask]<=capacity:continue
        if any(loads[mask]-weights[j]>capacity
               for j in range(n) if mask&(1<<j)):
            continue
        jobs=[j for j in range(n) if mask>>j&1]
        for machine in range(3):
            result.append(tuple(-x(j,machine) for j in jobs))
    return result

def canonical(clauses):
    return Counter(tuple(sorted(set(clause))) for clause in clauses)

def source_profile(raw,weights,capacity):
    if not isinstance(weights,list) or not 2<=len(weights)<=MAX_JOBS or (
        any(type(x)!=int or x<=0 or x>100000 for x in weights)):
        raise ValueError("unrecognized positive integer job weights")
    if type(capacity)!=int or capacity<=0 or capacity>200000:
        raise ValueError("unsupported capacity")
    nv,original=read_dimacs(raw)
    if nv!=3*len(weights):
        raise ValueError("source variable count does not match direct 3-machine encoding")
    loads=sums(weights)
    expected=expected_clauses(weights,capacity,loads)
    if canonical(original)!=canonical(expected) or len(original)!=len(expected):
        raise ValueError("source not complete exact minimal overweight CNF")
    return loads,len(original)

def master_source(configs):
    k=len(configs)
    if not 1<=k<=MAX_CONFIGS:
        raise ValueError("no manageable exact-capacity configurations")
    clauses=[tuple(range(1,k+1)),tuple(range(k+1,2*k+1))]
    for a in range(k):
        for b in range(k):
            if not (configs[a] & configs[b]):
                raise ValueError("two disjoint machine configurations -- not UNSAT")
            clauses.append((-(a+1),-(k+b+1)))
    if len(clauses)!=2+k*k:
        raise ValueError("master constraint count mismatch")
    text=(f"c IPG7 derived configuration master k={k}; NOT original source CNF\n"
          +f"p cnf {2*k} {len(clauses)}\n"
          +"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return text.encode("ascii"),clauses

def master_pure_pol(k,nclauses):
    # Derive ~y_first_machine_option_a >= 1 by combining all
    # conflicting second-machine options with the second ALO,
    # then integer division by k. k such lines plus final empty proof.
    lines=[]
    for a in range(k):
        ids=[2]+[3+a*k+b for b in range(k)]
        expression=[str(ids[0])]
        for cid in ids[1:]:expression.extend((str(cid),"+"))
        expression.extend((str(k),"d"))
        lines.append("pol "+" ".join(expression)+" ;")
    ids=[1]+[nclauses+i+1 for i in range(k)]
    expression=[str(ids[0])]
    for cid in ids[1:]:expression.extend((str(cid),"+"))
    lines.append("pol "+" ".join(expression)+" ;")
    return ("pseudo-Boolean proof version 3.0\n"
            +f"f {nclauses} ;\n"+"\n".join(lines)
            +"\noutput NONE ;\nconclusion UNSAT ;\n"
            +"end pseudo-Boolean proof ;\n")

def write_sat_model(n,first,second):
    if first&second:
        raise ValueError("SAT witness has intersecting full bins")
    masks=[first,second,((1<<n)-1)^(first|second)]
    true_variables=[3*j+m+1 for j in range(n)
                    for m in range(3) if masks[m]&(1<<j)]
    return true_variables,masks

def original_satisfies(clauses,variables):
    true=set(variables)
    return all(any((lit in true) if lit>0 else ((-lit) not in true)
                   for lit in c) for c in clauses)

def make(source,weights,capacity,prefix):
    begun=time.perf_counter()
    raw=source.read_bytes()
    loads,source_count=source_profile(raw,weights,capacity)
    digest=hashlib.sha256(raw).hexdigest()
    if sum(weights)!=3*capacity:
        return {"status":"UNKNOWN","reason":"source_total_load_not_exactly_three_capacity",
                "source_sha256":digest},None
    configs=[m for m,total in enumerate(loads) if total==capacity]
    if not configs:
        return {"status":"UNKNOWN","reason":"zero_exact_capacity_configs_master_not_supported",
                "source_sha256":digest},None
    if len(configs)>MAX_CONFIGS:
        return {"status":"UNKNOWN","reason":"explicit_exact_profile_size_gate",
                "source_sha256":digest},None
    witness=next(((a,b) for a in configs for b in configs if not(a&b)),None)
    result={
        "format":"DRNAS-IPG7-SOURCE-CONFIG-MASTER-V1",
        "source_sha256":digest,"source_vars":3*len(weights),
        "source_clauses":source_count,"weights":weights,
        "machine_count":3,"machine_capacity":capacity,
        "total_weight":sum(weights),
        "exact_capacity_masks":configs,
        "exact_capacity_config_count":len(configs),
        "proof_discovery":"EXPLICIT_SUBSET_SUM_PROFILES_NO_DPLL_CDCL",
        "complexity_scope":"O(2^n) explicit subset enumeration, n<=15",
    }
    prefix.parent.mkdir(parents=True,exist_ok=True)
    if witness:
        true_vars,masks=write_sat_model(len(weights),*witness)
        _,clauses=read_dimacs(raw)
        if not original_satisfies(clauses,true_vars):
            raise ValueError("original source SAT model false")
        result.update(status="SAT_MODEL_VERIFIED_BY_GENERATOR",
                      three_machine_masks=masks,
                      true_model_literals=true_vars)
        (prefix.with_suffix(".certificate.json")).write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n")
        result["elapsed_s"]=round(time.perf_counter()-begun,6)
        return result,None
    # All k*k intersections are NONZERO; pair conflict is independent
    # of whether source was originally encoded as bin packing.
    master,clauses=master_source(configs)
    master_file=prefix.with_suffix(".master.cnf")
    pb_file=prefix.with_suffix(".master.pbp")
    master_file.write_bytes(master)
    pb_file.write_text(master_pure_pol(len(configs),len(clauses)))
    result.update(
        status="UNSAT_SOURCE_STRUCTURAL_CANDIDATE_MASTER_VERIPB_UNCHECKED",
        master_sha256=hashlib.sha256(master).hexdigest(),
        master_variables=2*len(configs),master_clauses=len(clauses),
        master_pure_POL_steps=len(configs)+1,master_RUP_steps=0,
        master_pbp_bytes=pb_file.stat().st_size,
        every_exact_config_pair_intersects=True,
    )
    (prefix.with_suffix(".certificate.json")).write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n")
    result["elapsed_s"]=round(time.perf_counter()-begun,6)
    return result,(master_file,pb_file)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--weights-json",required=True,type=pathlib.Path)
    p.add_argument("--prefix",required=True,type=pathlib.Path)
    args=p.parse_args()
    try:
        definition=json.loads(args.weights_json.read_text())
        if definition.get("machines")!=3:
            raise ValueError("only three identical machines supported")
        report,files=make(args.cnf,definition["weights"],definition["capacity"],args.prefix)
        print("IPG7_CONFIG "+json.dumps(report,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,IndexError,KeyError,UnicodeError,
            OverflowError) as err:
        for ext in (".master.pbp",".master.cnf",".certificate.json"):
            args.prefix.with_suffix(ext).unlink(missing_ok=True)
        print("IPG7_CONFIG_UNKNOWN "+str(err),flush=True)
        return 1

if __name__=="__main__":raise SystemExit(main())

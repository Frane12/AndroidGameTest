#!/usr/bin/env python3
"""Emit standard VeriPB 3.0 cutting-planes UNSAT proof for original CNF.

Input: original source CNF and independent DRNAS-source-clique-capacity-v1
structural certificate. No CDCL calls or reformulation of the source CNF.
Output remains EMITTED_UNCHECKED until a separate pinned VeriPB accepts it.

For a complete binary-mutex clique S of size q:
  sum_{x in S} (1-x) >= q-1.
Obtain it in q-2 additions/divisions, reusing each original pair clause:
  q_new = q_old + 1, add the q_old pairs with new variable, plus
  (q_old-1) times the previously derived clique bound, divide by q_old.
Combine all source ALO clauses and clique bounds to derive false
when required group count exceeds resource count.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from check_php_partition import check as independent_structural_check

MAX_INPUT_SIZE = 22_000_000
MAX_PROOF_STEPS = 100_000

class Proof:
    def __init__(self, file, source_count):
        self.fd=file
        self.last=source_count
        self.pol_count=0
        file.write("pseudo-Boolean proof version 3.0\n")
        file.write(f"f {source_count} ;\n")
    def pol(self, terms, division=1, scale_last=1):
        if not terms or division<1 or scale_last<1:
            raise ValueError("invalid_pol_arguments")
        if self.pol_count >= MAX_PROOF_STEPS:
            raise ValueError("proof_step_limit")
        parts=[str(terms[0])]
        for i,cid in enumerate(terms[1:],1):
            parts.append(str(cid))
            if i==len(terms)-1 and scale_last>1:
                parts.extend((str(scale_last),"*"))
            parts.append("+")
        if division>1:
            parts.extend((str(division),"d"))
        self.fd.write("pol "+" ".join(parts)+" ;\n")
        self.last+=1
        self.pol_count+=1
        return self.last
    def finish(self,demand_ids,capacity_ids):
        self.pol([*demand_ids,*capacity_ids])
        self.fd.write("output NONE ;\n")
        self.fd.write("conclusion UNSAT ;\n")
        self.fd.write("end pseudo-Boolean proof ;\n")

def indices(cnf, cert):
    demands=[tuple(sorted(g)) for g in cert["selected_groups"]]
    resources=cert["capacity_cliques"]
    demand_targets=set(demands)
    mutex_targets=set()
    for clique in resources:
        for i,a in enumerate(clique):
            for b in clique[i+1:]:
                mutex_targets.add((min(a,b),max(a,b)))
    demand_index={}
    mutex_index={}
    clause=[]
    count=0
    declared_n=declared_m=None
    with Path(cnf).open("rb") as f:
        for line in f:
            t=line.split()
            if not t or t[0]==b"c":continue
            if t[0]==b"p":
                if declared_n is not None or len(t)!=4 or t[1]!=b"cnf":
                    raise ValueError("bad_dimacs_header")
                declared_n,declared_m=map(int,t[2:])
                continue
            if declared_n is None:raise ValueError("missing_dimacs_header")
            for piece in t:
                x=int(piece)
                if x:
                    if abs(x)>declared_n:raise ValueError("variable_out_of_range")
                    clause.append(x)
                    continue
                count+=1
                if clause and all(x>0 for x in clause):
                    k=tuple(sorted(clause))
                    if k in demand_targets and k not in demand_index:
                        demand_index[k]=count
                elif len(clause)==2 and clause[0]<0 and clause[1]<0:
                    a,b=sorted((-clause[0],-clause[1]))
                    if (a,b) in mutex_targets and (a,b) not in mutex_index:
                        mutex_index[(a,b)]=count
                clause=[]
    if declared_n is None or clause or count!=declared_m:
        raise ValueError("invalid_source_clause_count")
    if len(demand_index)!=len(demand_targets) or len(mutex_index)!=len(mutex_targets):
        raise ValueError(f"missing_source_clause_ids demands={len(demand_index)}/{len(demand_targets)} mutex={len(mutex_index)}/{len(mutex_targets)}")
    return count,demand_index,mutex_index

def emit(cnf, certificate, output):
    started=time.perf_counter()
    cnf=Path(cnf)
    certificate=Path(certificate)
    output=Path(output)
    if cnf.stat().st_size>MAX_INPUT_SIZE:
        raise ValueError("source_size_gate")
    cert=json.loads(certificate.read_text())
    checked=independent_structural_check(cnf,certificate)
    if checked["status"]!="UNSAT_SOURCE_CLIQUE_VERIFIED":
        raise ValueError("source_structural_certificate_rejected")
    count,demand_index,mutex_index=indices(cnf,cert)
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise ValueError("refuse_overwrite_existing_proof")
    try:
        with output.open("x") as f:
            p=Proof(f,count)
            capacity_ids=[]
            resource_sizes=[]
            for clique in cert["capacity_cliques"]:
                xs=sorted(clique)
                resource_sizes.append(len(xs))
                if len(xs)<2:
                    raise ValueError("resource_not_a_clique")
                prior=mutex_index[(xs[0],xs[1])]
                for j in range(2,len(xs)):
                    newest=xs[j]
                    pair_ids=[mutex_index[(xs[k],newest)] for k in range(j)]
                    # Induction: j*(sum_(prefix + newest) ~x) >= j*(j-1)+1
                    # then divide by j, round up to sum ~x >= j.
                    prior=p.pol([*pair_ids,prior],scale_last=j-1,division=j)
                capacity_ids.append(prior)
            demand_ids=[demand_index[tuple(sorted(group))]
                        for group in cert["selected_groups"]]
            p.finish(demand_ids,capacity_ids)
            f.flush()
        size=output.stat().st_size
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return dict(status="EMITTED_UNCHECKED",format="VeriPB3.0",
                source_sha256=hashlib.sha256(cnf.read_bytes()).hexdigest(),
                proof_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                source_clause_count=count,
                source_groups=len(demand_ids),resource_cliques=len(capacity_ids),
                capacity_gap=len(demand_ids)-len(capacity_ids),
                resource_clique_max=max(resource_sizes),
                proof_pol_steps=p.pol_count,proof_bytes=size,
                producer_s=round(time.perf_counter()-started,6))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cnf",type=Path,required=True)
    ap.add_argument("--certificate",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        r=emit(args.cnf,args.certificate,args.output)
        print("PHP_VERIPB_PRODUCED "+json.dumps(r,sort_keys=True),flush=True)
    except (ValueError,OSError,KeyError,TypeError,AssertionError) as e:
        print("PHP_VERIPB_NOT_EMITTED "+str(e),flush=True)
        raise SystemExit(1)

if __name__=="__main__":
    main()

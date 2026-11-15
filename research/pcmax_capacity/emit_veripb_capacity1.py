#!/usr/bin/env python3
"""DRNAS PCMAX -> VeriPB 3.0 RUP + cutting planes, original DIMACS only.

Experimental source-bound proof *producer*. Its output is UNSAT-verified ONLY
after an independent VeriPB checker accepts the entire original CNF and log.
The method is restricted to unit-weight groups, disjoint selected variables,
fully covered BDD machines of capacity 1 or 3, <=16 selected per machine,
and one-unit capacity deficit. No CDCL or other SAT backend is invoked.
"""
import argparse
import hashlib
import itertools
import json
import sys
import time
from functools import lru_cache
from pathlib import Path

from check_capacity import check as structural_check

def dimacs(raw):
    vars_=count=None
    clauses=[]
    partial=[]
    for line in raw.decode("ascii").splitlines():
        parts=line.split()
        if not parts or parts[0]=="c":continue
        if parts[0]=="p":
            if vars_ is not None or len(parts)!=4 or parts[1]!="cnf":
                raise ValueError("bad DIMACS header")
            vars_,count=map(int,parts[2:])
            continue
        if vars_ is None:raise ValueError("missing DIMACS header")
        for t in parts:
            lit=int(t)
            if abs(lit)>vars_:raise ValueError("out-of-range literal")
            if not lit:clauses.append(tuple(partial));partial=[]
            else:partial.append(lit)
    if vars_ is None or partial or len(clauses)!=count:
        raise ValueError("DIMACS clause count mismatch")
    return vars_,clauses

class Proof:
    def __init__(self,fd,source_count):
        self.f=fd
        self.last=source_count
        self.rup_count=0
        self.pol_count=0
        fd.write("pseudo-Boolean proof version 3.0\n")
        fd.write(f"f {source_count} ;\n")
    def rup(self,lits):
        if not lits:raise ValueError("empty intermediate RUP")
        self.last+=1;self.rup_count+=1
        self.f.write("rup "+" ".join(
            "1 "+("~" if lit<0 else "")+"x"+str(abs(lit))
            for lit in lits)+" >= 1 ;\n")
        return self.last
    def pol(self,ids,division=1,scale_last=1):
        assert ids and division>0 and scale_last>0
        terms=[str(ids[0])]
        for i,cid in enumerate(ids[1:],1):
            terms.append(str(cid))
            if i==len(ids)-1 and scale_last>1:
                terms += [str(scale_last),"*"]
            terms.append("+")
        if division>1:terms += [str(division),"d"]
        self.f.write("pol "+" ".join(terms)+" ;\n")
        self.last+=1;self.pol_count+=1
        return self.last
    def finish(self,alo,machine):
        self.pol([*alo,*machine])
        self.f.write("output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n")

class BDD:
    """Emit source-derived RUP no-goods bottom up through accepted BDD transitions."""
    def __init__(self,proof,machine):
        self.p=proof
        self.root=machine["root"]
        self.true=machine["true_terminal"]
        self.false=machine["false_terminal"]
        self.rank={x:i for i,x in enumerate(machine["variable_order"])}
        self.nodes={q:(x,lo,hi) for q,x,lo,hi in machine["transitions"]}
        assert len(self.nodes)==len(machine["transitions"])
        self.lemmas={}
    @lru_cache(None)
    def accepting(self,node,forced):
        if node==self.true:return True
        if node==self.false:return False
        x,lo,hi=self.nodes[node]
        later=tuple(v for v in forced if self.rank[v]>self.rank[x])
        if x in forced:return self.accepting(hi,later)
        return self.accepting(lo,later) or self.accepting(hi,later)
    def blocked(self,node,forced):
        if node==self.false:return None # Original CNF includes unit -false.
        if node==self.true:raise AssertionError("cannot block accepting terminal")
        x,lo,hi=self.nodes[node]
        forced=tuple(v for v in forced if self.rank[v]>=self.rank[x])
        key=(node,forced)
        if key in self.lemmas:return self.lemmas[key]
        if self.accepting(node,forced):
            raise ValueError("a BDD path accepts these forced selectors")
        later=tuple(v for v in forced if self.rank[v]>self.rank[x])
        if x in forced:
            self.blocked(hi,later)
        else:
            self.blocked(lo,later)
            self.blocked(hi,later)
        # With node and forced selectors TRUE, original transitions force
        # a blocked successor, or force both x and -x. Hence RUP.
        cid=self.p.rup([-node,*[-v for v in forced]])
        self.lemmas[key]=cid
        return cid
    def forbid(self,subset):
        forced=tuple(sorted(subset,key=self.rank.__getitem__))
        if self.accepting(self.root,forced):
            raise ValueError("source BDD does not prohibit selected subset")
        self.blocked(self.root,forced)
        return self.p.rup([-v for v in forced])

def machine_bound(p,m,subset):
    xs=tuple(sorted(subset))
    n=len(xs);k=m["capacity"]
    if k not in (1,3) or n>16 or n<=k:
        raise ValueError("unsupported machine size/capacity")
    bdd=BDD(p,m)
    if k==1:
        previous=bdd.forbid(xs[:2])
        for j in range(2,n):
            pairs=[bdd.forbid((v,xs[j])) for v in xs[:j]]
            # From n pairwise mutexes and (n-1) times previous clique bound:
            # n * sum_i(~xi) >= n^2-n+1; divide by n to get sum_i(~xi)>=n.
            previous=p.pol([*pairs,previous],scale_last=j-1,division=j)
        return previous,len(bdd.lemmas)
    # Full subset-lattice cutting planes for 3-capacity resources.
    # Base 4-selector forbidden subsets are source-justified RUP clauses.
    # For subset T of size s>=5, sum all s previous (s-1)-subset PB
    # inequalities then divide by s-1: sum_{x in T} ~x >= s-3.
    ids={}
    for tup in itertools.combinations(range(n),4):
        mask=sum(1<<t for t in tup)
        ids[mask]=bdd.forbid(tuple(xs[t] for t in tup))
    for s in range(5,n+1):
        for tup in itertools.combinations(range(n),s):
            mask=sum(1<<t for t in tup)
            ids[mask]=p.pol([ids[mask & ~(1<<t)] for t in tup],division=s-1)
    return ids[(1<<n)-1],len(bdd.lemmas)

def generate(cnf,certpath,output):
    start=time.perf_counter()
    raw=Path(cnf).read_bytes()
    cert=json.loads(Path(certpath).read_text())
    source_sha=hashlib.sha256(raw).hexdigest()
    if cert.get("source_sha256")!=source_sha:
        raise ValueError("source certificate SHA-256 mismatch")
    checked=structural_check(raw,cert)
    if checked["status"]!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
        raise ValueError("independent structural checker rejected")
    nvars,clauses=dimacs(raw)
    index={}
    for i,c in enumerate(clauses,1):index.setdefault(frozenset(c),i)
    groups=cert["selected_groups"]
    if not groups or len(groups)!=len(cert["group_weights"]) or any(
        type(w)!=int or w!=1 for w in cert["group_weights"]
    ):raise ValueError("only positive unit-weight disjoint groups supported")
    selectors=[v for group in groups for v in group]
    if len(set(selectors))!=len(selectors) or any(v<=0 for v in selectors):
        raise ValueError("overlapping or nonpositive selectors")
    alo=[index[frozenset(group)] for group in groups]
    source_selectors=set(selectors)
    owner={}
    machines=cert["machines"]
    selected_per_machine=[]
    for i,m in enumerate(machines):
        values=[x for x in m["variable_order"] if x in source_selectors]
        for x in values:
            if x in owner:raise ValueError("overlapping machine selectors")
            owner[x]=i
        selected_per_machine.append(values)
    if set(owner)!=source_selectors:
        raise ValueError("incomplete machine cover")
    if len(groups)!=cert["required"] or sum(m["capacity"] for m in machines)!=cert["capacity_sum"]:
        raise ValueError("capacity arithmetic mismatch")
    if cert["required"]-cert["capacity_sum"]!=1:
        raise ValueError("unsupported non-unit deficit")
    for values,m in zip(selected_per_machine,machines):
        if m["capacity"] not in (1,3) or len(values)>16 or len(values)<=m["capacity"]:
            raise ValueError("unsupported source machine")
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w") as fd:
        proof=Proof(fd,len(clauses))
        derived=[]
        lemma_counts=[]
        for m,values in zip(machines,selected_per_machine):
            new_id,count=machine_bound(proof,m,values)
            derived.append(new_id)
            lemma_counts.append(count)
        proof.finish(alo,derived)
        size=fd.tell()
        result={
            "status":"EMITTED_UNCHECKED", "format":"VeriPB3.0",
            "source_sha256":source_sha,"source_clauses":len(clauses),
            "source_variables":nvars,
            "structural_checked":True,"required":cert["required"],
            "capacity_sum":cert["capacity_sum"],
            "machine_capacities":[m["capacity"] for m in machines],
            "selected_per_machine":[len(v) for v in selected_per_machine],
            "BDD_nogood_lemmas":lemma_counts,
            "rup_steps":proof.rup_count,"cutting_planes_steps":proof.pol_count,
            "total_steps":proof.rup_count+proof.pol_count,
            "proof_bytes":size,"generator_s":round(time.perf_counter()-start,6)}
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cnf",type=Path,required=True)
    parser.add_argument("--certificate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    try:
        outcome=generate(a.cnf,a.certificate,a.output)
        print("PCMAX_VERIPB_EMITTED "+json.dumps(outcome,sort_keys=True),flush=True)
    except (ValueError,AssertionError,KeyError,TypeError,OSError) as exc:
        print("PCMAX_VERIPB_UNKNOWN "+str(exc),flush=True)
        return 1
    return 0

if __name__=="__main__":
    sys.exit(main())

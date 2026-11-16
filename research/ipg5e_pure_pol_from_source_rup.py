#!/usr/bin/env python3
"""IPG5E: turn a source-grounded RUP proof into pure VeriPB POL.

For each RUP clause, reproduce unit propagation under the negated clause,
record original-source or previous-lemma reasons, and eliminate propagated
variables by reverse chronological resolution. Simulate binary resolution
of (A or x) and (B or not x) with pure PB addition and saturation:
  pol <A-or-x-id> <B-or-not-x-id> + s ;
Output contains exactly one POL line per previously supplied RUP clause,
zero RUP proof lines. Every local resolvent is checked via an independent
literal-coefficient integer normalizer before output.

The RUP source trail was FOUND by bounded structural DPLL. Thus a pure POL
proof FORMAT is NOT evidence of a search-free discovery algorithm. The
generated proof is UNCHECKED until external VeriPB 3.0.2 accepts it.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time
from ipg4_rup_drat_to_veripb import dimacs, parse_rup_trace

def literal(l):
    return ("~" if l<0 else "")+"x"+str(abs(l))

def propagate(database,target):
    assigned={};why={};order=[]
    for lit in target:
        v=abs(lit)
        if v in assigned:raise ValueError("duplicate RUP assumption")
        assigned[v]=(lit<0)
        why[v]=None
        order.append(v)
    while True:
        changed=False
        for i,clause in enumerate(database):
            sat=False;free=[]
            for lit in clause:
                v=abs(lit)
                if v in assigned:
                    if assigned[v]==(lit>0):
                        sat=True;break
                else:free.append(lit)
            if sat:continue
            if not free:return i,assigned,why,order
            if len(free)==1:
                v=abs(free[0])
                if v in assigned:raise AssertionError("unit propagation error")
                assigned[v]=(free[0]>0)
                why[v]=i
                order.append(v)
                changed=True
        if not changed:return None,assigned,why,order

def pb_resolvent(left,right):
    # Independent exact literal-normal-form PB arithmetic:
    # add source clauses (rhs 1+1), cancel all literal complements,
    # saturate coefficients to at most the final rhs.
    coeff={}
    for clause in (left,right):
        for lit in clause:coeff[lit]=coeff.get(lit,0)+1
    rhs=2
    for v in {abs(l) for l in coeff}:
        common=min(coeff.get(v,0),coeff.get(-v,0))
        coeff[v]=coeff.get(v,0)-common
        coeff[-v]=coeff.get(-v,0)-common
        rhs-=common
    if rhs!=1:raise ValueError("not one-pivot clausal resolution")
    ans={l for l,c in coeff.items() if min(c,1)>0}
    if any(-l in ans for l in ans):raise ValueError("tautological resolvent")
    return ans

def convert(source,trace,destination,expected_sha):
    began=time.perf_counter()
    raw,nvars,original=dimacs(source)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=expected_sha:raise ValueError("input digest differs from precommitment")
    if not 9<=nvars<=45 or not 1<=len(original)<=20000:
        raise ValueError("source size outside pilot")
    targets=parse_rup_trace(trace,nvars)
    if not targets or len(targets)>120000 or targets[-1]:
        raise ValueError("source trail missing final contradiction")
    database=list(map(tuple,original))
    ids=list(range(1,len(database)+1))
    nextid=len(database)
    instructions=[];adds=0;saturations=0;weakening=0;maximum=0
    for number,target in enumerate(targets,1):
        found,assignment,why,order=propagate(database,target)
        if found is None:raise ValueError(f"RUP target {number} not source implied")
        current=set(database[found])
        words=[str(ids[found])]
        length=0
        for var in reversed(order):
            rid=why[var]
            if rid is None:continue
            true_lit=var if assignment[var] else -var
            if -true_lit not in current:continue
            reason=set(database[rid])
            if true_lit not in reason:raise ValueError("missing unit reason")
            expected=(current-{-true_lit})|(reason-{true_lit})
            if any(-l in expected for l in expected):
                raise ValueError("unit reason resolves to tautology")
            computed=pb_resolvent(current,reason)
            if computed!=expected:
                raise ValueError("integer PB saturation differs from exact resolvent")
            current=computed
            words.extend((str(ids[rid]),"+","s"))
            adds+=1;saturations+=1;length+=1
        if not current.issubset(set(target)):
            raise ValueError(f"failed to resolve original target {number}")
        for extra in sorted(set(target)-current,key=lambda l:(abs(l),l)):
            words.extend((literal(extra),"+"))
            current.add(extra);adds+=1;weakening+=1
        if current!=set(target):
            raise ValueError("RUP target cannot be copied in CP format")
        instructions.append("pol "+" ".join(words)+" ;")
        nextid+=1
        ids.append(nextid)
        database.append(target)
        maximum=max(maximum,length)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(
        "pseudo-Boolean proof version 3.0\n"+
        f"f {len(original)} ;\n"+
        "\n".join(instructions)+"\n"+
        "output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n"
    )
    return {
        "status":"POL_ONLY_EMITTED_NEEDS_EXTERNAL_VERIPB",
        "source_sha256":sha,"source_variables":nvars,
        "original_clauses":len(original),
        "upstream_rup_steps":len(targets),
        "veripb_pol_lines":len(instructions),
        "veripb_rup_lines":0,
        "pb_additions":adds,"pb_saturations":saturations,
        "literal_axiom_weakening":weakening,
        "longest_resolution_chain":maximum,
        "proof_bytes":destination.stat().st_size,
        "generator_s":round(time.perf_counter()-began,6),
        "provenance":"DPLL_DISCOVERED_RUP_TRACE_CONVERTED_TO_POL_ONLY",
        "limitation":"No RUP in final proof; upstream bounded exponential source DPLL still required"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--source-rup",required=True,type=pathlib.Path)
    p.add_argument("--pb-proof",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--expected-sha256",required=True)
    a=p.parse_args()
    try:
        report=convert(a.cnf,a.source_rup,a.pb_proof,a.expected_sha256)
        a.meta.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        print("IPG5E_POL_ONLY "+json.dumps(report,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,AssertionError,IndexError,UnicodeError) as err:
        a.pb_proof.unlink(missing_ok=True)
        print("IPG5E_POL_UNKNOWN "+str(err),flush=True)
        return 1
if __name__=="__main__":raise SystemExit(main())

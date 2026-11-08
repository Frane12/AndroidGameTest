#!/usr/bin/env python3
"""DRNAS MRE6: certified equivalence quotient, not another watched lemma.

If original CNF entails (-a OR b) and (a OR -b), substitute b := a in
the CNF and independently certified source XORs, then reconstruct SAT
witness for original variables. The implication certificates MUST be
replayed against the ORIGINAL CNF before this rewrite can be applied.

The transformation is equisatisfiable, not literally model-preserving
without reconstruction. NEVER substitute from a heuristic/prediction.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import mre4_trace_pilot as mre4
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

def need(ok, msg):
    if not ok: raise RuntimeError("MRE6_QUOTIENT_FAIL_CLOSED "+str(msg))

def canonical(clauses, *, from_var=None, to_var=None):
    """Pure canonicalization with optional proved positive equality b == a.

    Keep clauses in original order where possible; eliminate duplicated
    literals/clauses and tautologies, tracking each reduction for audit.
    """
    if from_var is not None:
        need(isinstance(to_var,int) and to_var>0 and
             isinstance(from_var,int) and from_var>0 and
             from_var!=to_var,"bad equivalence vars")
    out=[]
    seen=set()
    stats=dict(input_clauses=len(clauses),removed_tautologies=0,
               removed_duplicate_clauses=0,removed_duplicate_literals=0,
               output_clauses=0,replaced_occurrences=0,
               introduced_empty=0)
    for clause in clauses:
        vals=[]
        local=set()
        taulog=False
        for lit in clause:
            need(isinstance(lit,int) and lit!=0,"invalid literal")
            newlit=(to_var if lit>0 else -to_var) if from_var is not None and abs(lit)==from_var else lit
            stats["replaced_occurrences"]+=int(newlit!=lit)
            if -newlit in local:
                taulog=True
                break
            if newlit in local:
                stats["removed_duplicate_literals"]+=1
                continue
            local.add(newlit)
            vals.append(newlit)
        if taulog:
            stats["removed_tautologies"]+=1
            continue
        key=tuple(sorted(local,key=lambda x:(abs(x),x<0)))
        if key in seen:
            stats["removed_duplicate_clauses"]+=1
            continue
        seen.add(key)
        if not vals:stats["introduced_empty"]+=1
        out.append(tuple(vals))
    stats["output_clauses"]=len(out)
    return out,stats

def normalize_xors(source_rows,*,from_var=None,to_var=None):
    """Transform original certified GF2 parity rows under b := a.

    GF2 arithmetic is mod 2; repeated a cancels (a XOR a = 0).
    1-variable XOR constraints become CNF units, 0-variable unsatisfied
    rows fail closed. For an SAT original with certified equality, there
    should be no contradictory constant row.
    """
    rows=[]
    units=[]
    stats=dict(input_rows=len(source_rows),output_rows=0,
               degenerate_units=0,removed_tautological_rows=0)
    seen=set()
    for vars_,rhs in source_rows:
        vs=set()
        for v in vars_:
            x=to_var if from_var is not None and v==from_var else v
            if x in vs:vs.remove(x)
            else:vs.add(x)
        newvs=tuple(sorted(vs))
        if len(newvs)==0:
            need(not rhs,"certified source XOR contradicts equivalence quotient")
            stats["removed_tautological_rows"]+=1
            continue
        if len(newvs)==1:
            units.append((newvs[0] if rhs else -newvs[0],))
            stats["degenerate_units"]+=1
            continue
        need(2<=len(newvs)<=6,"CMS XOR width outside supported range")
        row=(newvs,rhs)
        if row not in seen:
            rows.append(row)
            seen.add(row)
    stats["output_rows"]=len(rows)
    return rows,units,stats

def extract_equivalence(original,source_rows,proofs):
    # Mandatory deterministic revalidation of full MRE1 proof chain
    need(mre1.verify_proofs(original,source_rows,proofs),
         "MRE1 replay not accepted")
    established={tuple(p["clause"]) for p in proofs}
    pairs=[]
    for clause in established:
        if len(clause)!=2:continue
        x,y=clause
        if abs(x)==abs(y) or (x>0)==(y>0):continue
        comp=(-x,-y)
        # Normalize by sorted absolute literal ordering to match MRE1
        comp=tuple(sorted(comp,key=lambda z:(abs(z),z<0)))
        if comp not in established:continue
        smaller,bigger=sorted((abs(x),abs(y)))
        if smaller>=bigger:continue
        # Both clauses must enforce POSITIVE equality: (-a OR b) & (a OR -b).
        req1=mre1.normalize((-smaller,bigger))
        req2=mre1.normalize((smaller,-bigger))
        if req1 not in established or req2 not in established:continue
        key=(smaller,bigger)
        if key not in pairs:pairs.append(key)
    return sorted(pairs)

def build_principles(original, source_rows, proofs):
    pairs=extract_equivalence(original,source_rows,proofs)
    out=[]
    for keep,remove in pairs:
        a=mre1.normalize((-keep,remove))
        b=mre1.normalize((keep,-remove))
        signature=hashlib.sha256(json.dumps(
            dict(kind="certified_equality",keep=keep,remove=remove,
                 certified_clauses=[a,b]),sort_keys=True
            ).encode()).hexdigest()
        out.append(dict(principle="certified_equality",
             keep=keep,remove=remove,proof_lemma_a=a,proof_lemma_b=b,
             principle_id=signature,
             action="quotient_variable_and_transform_GF2_then_reconstruct",
             proof_replayed=True))
    return out

def apply_quotient(original,source_rows,pr):
    need(pr["proof_replayed"] and pr["principle"]=="certified_equality",
         "not proven equivalence")
    keep,remove=pr["keep"],pr["remove"]
    cnf,cstats=canonical(original,from_var=remove,to_var=keep)
    rows,units,xstats=normalize_xors(source_rows,from_var=remove,to_var=keep)
    cnf,cstats2=canonical(cnf+units)
    need(not any(len(c)==0 for c in cnf),
         "empty clause after equivalence quotient in SAT-verified pilot")
    need(all(abs(l)!=remove for c in cnf for l in c) and
         all(remove not in vs for vs,rhs in rows),
         "removed variable leaked into quotient")
    return cnf,rows,dict(equality=pr,cnf=cstats,unit_dedup=cstats2,xor=xstats,
                         variable_eliminated=remove,
                         after_cnf=len(cnf),after_xors=len(rows))

def reconstruct(model,pr):
    model=dict(model)
    keep,remove=pr["keep"],pr["remove"]
    need(keep in model and isinstance(model[keep],bool),
         "missing retained variable in SAT witness")
    # Original 'remove' may be undef/false in transformed CNF. Override it
    # with its mathematically proven equivalent variable.
    model[remove]=model[keep]
    return model

def validate_reconstruction(original, transformed, pr, witness):
    # This checks the lifted witness against all original clauses, not only
    # the smaller transformed CNF.
    lifted=reconstruct(witness,pr)
    need(all(any(lifted.get(abs(l),False)==(l>0) for l in c)
             for c in original),"reconstructed witness falsifies ORIGINAL CNF")
    return lifted

def selftest():
    # Original explicitly enforces a == b. After quotient b:=a,
    # satisfiability and every satisfying assignment projected to survivors
    # must match exactly. Also check GF(2) parity cancellation.
    original=[(-1,2),(1,-2),(2,3),(-2,4),(3,-4),(1,1,3)]
    cnf,st=canonical(original,from_var=2,to_var=1)
    need(st["replaced_occurrences"]>=3,"canonical quotient failed")
    for av,cv,dv in itertools.product((False,True),repeat=3):
        assignment={1:av,2:av,3:cv,4:dv}
        orig=all(any(assignment[abs(l)]==(l>0) for l in c) for c in original)
        trans=all(any(assignment[abs(l)]==(l>0) for l in c) for c in cnf)
        need(orig==trans,"quotient exhaustive equivalence failed")
    rr,uu,x=normalize_xors([((1,2,3),1),((1,2),0),((2,4),1)],
                           from_var=2,to_var=1)
    need(((3,),1) not in rr and uu==[(3,)] and
         ((1,4),1) in rr and x["removed_tautological_rows"]==1,
         "GF2 cancelled terms incorrectly")
    pr=dict(principle="certified_equality",keep=1,remove=2,proof_replayed=True)
    lifted=validate_reconstruction(original,cnf,pr,{1:True,2:False,3:True,4:True})
    need(lifted[2] is True,"SAT witness not reconstructed")
    print("MRE6_QUOTIENT_SELFTEST_PASS",
          json.dumps(dict(cnf_stats=st,xor=x),sort_keys=True),flush=True)

if __name__=="__main__":
    selftest()

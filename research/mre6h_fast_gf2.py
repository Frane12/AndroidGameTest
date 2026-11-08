#!/usr/bin/env python3
"""DRNAS MRE6h: fast GF(2) equivalence discovery, no subprocess or resolution.

A source parity row is admitted only when every forbidden assignment is
represented by an ORIGINAL CNF clause (mre1.replay_source_xors).
Proof-producing GF(2) elimination returns at-most-2-variable rows with a
full XOR-combination trace. We emit both implication clauses and replay
each trace via mre1.verify_proofs on the ORIGINAL source, independently
of the elimination algorithm. A signed SCC proof then verifies both
directions and the original SAT model is reconstructed.

The *proof cost*, XOR extraction, transformation, original witness
verification and CMS.solve are included in end-to-end wall benchmark.
"""
from __future__ import annotations
import collections,itertools,json,pathlib,random,sys,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import r195_native_cms_benchmark as r195
import mre6g_proof_graph as graph

PROTO="DRNAS-MRE6H-FAST-CERTIFIED-GF2-ELIM-v1"
MAX_PROOF_CLAUSES=48
MAX_INPUT_ROWS=150
MAX_UNIT_INPUTS=64
MAX_PAIR_CHECKS=20000

class BudgetAbstain(Exception): pass

def need(ok,msg):
    if not ok:raise RuntimeError("MRE6H_FAIL_CLOSED "+str(msg))

def certified_fast(original,*,known_rows=None,budget_s=.18,
                   allow_units=True):
    start=time.perf_counter()
    until=start+budget_s
    rows=list(known_rows) if known_rows is not None else \
         r195.certified_source_rows(original)[:MAX_INPUT_ROWS]
    need(len(rows)<=MAX_INPUT_ROWS,"too many unverified GF2 source rows")
    if len(rows)<2:
        return rows,[],dict(status="insufficient_GF2_rows",
            rows=len(rows),derived_binary=0,derive_s=time.perf_counter()-start)
    # Independent CNF truth-table replay; fast path does NOT trust extractor.
    mre1.replay_source_xors(original,rows)
    if time.perf_counter()>until:raise BudgetAbstain("source_proof_budget")
    original_set={mre1.normalize(c) for c in original}
    original_set.discard(None)
    inputs=[(mre1.mask(vs),rhs,("source",vs,rhs)) for vs,rhs in rows]
    if allow_units:
        lits=sorted((c[0] for c in original_set if len(c)==1),
                     key=lambda x:(abs(x),x))[:MAX_UNIT_INPUTS]
        inputs += [(mre1.mask((abs(lit),)),int(lit>0),("unit",lit))
                   for lit in lits]
    # Pass one: elimination basis with full provenance.
    candidates=[]
    for m,b,trace in mre1.reduce_gf2(inputs):
        if m.bit_count()<=2 and m and (not (m==0)):
            candidates.append((m,b,trace))
    if time.perf_counter()>until:raise BudgetAbstain("linear_elimination_budget")
    # Pass two: cheap local cancellations of nearly-overlapping rows.
    # Adds a provably valid GF2 sum of TWO original rows. It cannot
    # produce spurious implications because proofs are replayed.
    checked=0
    if len(candidates)<MAX_PROOF_CLAUSES//2:
        for i in range(len(inputs)):
            im,ib,_=inputs[i]
            for j in range(i+1,len(inputs)):
                checked+=1
                if checked>MAX_PAIR_CHECKS:break
                jm,jb,_=inputs[j]
                m=im^jm
                if 0<m.bit_count()<=2:
                    candidates.append((m,ib^jb,(1<<i)|(1<<j)))
                if (checked&1023)==0 and time.perf_counter()>until:
                    raise BudgetAbstain("local_GF2_pair_budget")
            if checked>MAX_PAIR_CHECKS:break
    seen=set(original_set)
    lemmas=[]
    derived_equations=0
    for m,rhs,trace in candidates:
        if len(lemmas)+2>MAX_PROOF_CLAUSES:break
        if not m or m.bit_count()!=2:continue
        projected=mre1.clauses_for(m,rhs)
        if all(p in seen for p in projected):continue
        origins=[inputs[i][2] for i in range(len(inputs))
                  if trace&(1<<i)]
        # Independent arithmetic identity of every claimed GF2 trace.
        checkmask=checkrhs=0
        for i in range(len(inputs)):
            if trace&(1<<i):
                checkmask^=inputs[i][0];checkrhs^=inputs[i][1]
        need((checkmask,checkrhs)==(m,rhs),
             "GF2 proof origin parity mismatch")
        for c in projected:
            if c not in seen:
                lemmas.append(dict(kind="gf2",clause=c,mask=m,
                       rhs=rhs,origins=origins))
                seen.add(c)
        derived_equations+=1
        if time.perf_counter()>until:raise BudgetAbstain("proof_materialization_budget")
    if lemmas:
        # Required standalone proof verifier; fails closed on original CNF.
        need(mre1.verify_proofs(original,rows,lemmas),
             "fast GF2 derived clause proof did not replay")
    if time.perf_counter()>until:raise BudgetAbstain("independent_proof_budget")
    return rows,lemmas,dict(
        status="certified_GF2_short_rows" if lemmas else "no_new_short_GF2_rows",
        rows=len(rows),input_rows=len(inputs),
        derived_binary=len(lemmas),derived_equations=derived_equations,
        pairs_checked=checked,elimination_used=True,
        derive_s=round(time.perf_counter()-start,6),
        independent_original_CNF_proof_replay=True)

def find_certified_mapping(original,rows,*,budget_s=.27,
                           include_source_graph=True):
    start=time.perf_counter()
    source_mapping={}
    source_graph={}
    if include_source_graph:
        try:
            source_mapping,source_graph=graph.discover(original,budget_s=.12)
        except graph.Abstain as exc:
            source_graph=dict(status="abstain",reason=str(exc))
    if source_mapping:
        return source_mapping,[],dict(status="source_SCC_eq",
             graph=source_graph,GF2_skipped=True,
             wall_s=round(time.perf_counter()-start,6))
    remaining=budget_s-(time.perf_counter()-start)
    if remaining<=.02:
        return {},[],dict(status="pre_GF2_cost_guard",graph=source_graph)
    try:
        source_rows,proofs,trace=certified_fast(
           original,known_rows=rows,budget_s=remaining*.70)
    except BudgetAbstain as exc:
        return {},[],dict(status="GF2_CPU_budget_abstain",
               reason=str(exc),graph=source_graph,
               wall_s=round(time.perf_counter()-start,6))
    mapping={}
    gr={}
    if proofs:
        remaining=budget_s-(time.perf_counter()-start)
        if remaining<=.02:
            return {},[],dict(status="SCC_budget_exhausted_after_GF2",
                    GF2=trace,wall_s=round(time.perf_counter()-start,6))
        try:
            mapping,gr=graph.discover(original,source_rows,proofs,
                                   budget_s=remaining)
        except graph.Abstain as exc:
            gr=dict(status="abstain",why=str(exc))
    return mapping,proofs,dict(status="certified_fast_quotient" if mapping
             else "no_useful_certified_GF2_equivalence",
             GF2=trace,graph=gr,original_graph=source_graph,
             wall_s=round(time.perf_counter()-start,6))

def selftest():
    # Three proven parity equations: x1=x2 and x2=not x3,
    # without any direct binary original clauses.
    def xor_cnf(vs,rhs):
        out=[]
        for mask in range(1<<len(vs)):
            if (mask.bit_count()&1)==rhs:continue
            out.append(tuple(-v if mask&(1<<j) else v for j,v in enumerate(vs)))
        return out
    original=xor_cnf((1,2,4),0)+xor_cnf((2,3,4),1)
    rows,proofs,stats=certified_fast(original,budget_s=3)
    need(len(rows)==2 and len(proofs)>=2,
         "did not derive signed equality from GF2 source rows")
    mapping,p,diag=find_certified_mapping(original,rows,budget_s=3)
    need(bool(mapping) and len(mapping)>=1,"certified fast SCC found no equivalence")
    rewritten,transformed,evidence=graph.quotient(original,rows,mapping)
    for bits in itertools.product((False,True),repeat=4):
        m=dict(zip(range(1,5),bits))
        orig=all(any(m[abs(l)]==(l>0) for l in c) for c in original)
        if orig:need(all(m[v]==(m[abs(r)] if r>0 else not m[abs(r)])
                          for v,r in mapping.items()),"wrong signed GF2 model")
        reducedmodel=graph.reconstruct(
            {k:m[k] for k in m if k not in mapping},mapping)
        lhs=all(any(reducedmodel[abs(l)]==(l>0) for l in c)
                for c in original)
        rhs=all(any(reducedmodel[abs(l)]==(l>0) for l in c)
                for c in rewritten) and all(
                  (sum(reducedmodel[v] for v in vs)&1)==b
                    for vs,b in transformed)
        need(lhs==rhs,"quotient not equivalent on lifted models")
    # A one-way implication is not equivalence.
    rr,pp,st=certified_fast(xor_cnf((1,2,4),0),budget_s=3)
    mm,_,_=find_certified_mapping(xor_cnf((1,2,4),0),rr,budget_s=3)
    need(mm=={},"unsafe equality on one parity row")
    print("MRE6H_FAST_GF2_SELFTEST_PASS",json.dumps(dict(
      proofs=len(proofs),mapping=mapping,GF2=stats),sort_keys=True),flush=True)

if __name__=="__main__":
    selftest()

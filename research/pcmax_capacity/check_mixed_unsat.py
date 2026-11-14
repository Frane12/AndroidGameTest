#!/usr/bin/env python3
"""Independent, source-bound checker for tiny 2-SAT, XOR and DPLL UNSAT proofs.

The producer, native SAT solver, and their decisions are never trusted.
Every accepted inference is reconstructed from ORIGINAL input clauses.
This is an experimental bounded proof format, not DRAT or LRAT.
"""
import hashlib
import itertools
from check_capacity import parse_cnf

class InvalidProof(ValueError):
    pass

def need(ok,msg):
    if not ok:
        raise InvalidProof(msg)

def verify(raw, proof):
    need(type(proof) is dict and proof.get("format")=="drnas-mixed-unsat1",
         "invalid proof format")
    need(proof.get("source_sha256")==hashlib.sha256(raw).hexdigest(),
         "source hash mismatch")
    nvars, clauses=parse_cnf(raw)
    method=proof.get("method")
    if method=="binary_cycle":
        pivot=proof.get("pivot")
        need(type(pivot) is int and 0<pivot<=nvars, "invalid contradictory variable")
        for name,first,last in (("pos_to_neg",pivot,-pivot),("neg_to_pos",-pivot,pivot)):
            path=proof.get(name)
            need(type(path) is list and 2<=len(path)<=2*nvars+2,
                 "missing or oversized implication path")
            need(path[0]==first and path[-1]==last,"incorrect implication endpoints")
            for u,v in zip(path,path[1:]):
                need(type(u) is int and type(v) is int and
                     0<abs(u)<=nvars and 0<abs(v)<=nvars,
                     "invalid implication literal")
                need(frozenset((-u,v)) in clauses,
                     "implication edge absent from original clauses")
        return {"status":"UNSAT_VERIFIED","method":method,
                "implications":len(proof["pos_to_neg"])+len(proof["neg_to_pos"])-2}
    if method=="xor_gf2":
        blocks=proof.get("blocks")
        combine=proof.get("combine")
        need(type(blocks) is list and 1<=len(blocks)<=32 and
             type(combine) is list and bool(combine) and len(combine)<=32,
             "invalid XOR blocks/combination")
        rows=[]
        for block in blocks:
            need(type(block) is dict,"invalid XOR block")
            vs=block.get("vars")
            parity=block.get("forbidden_parity")
            need(type(vs) is list and 2<=len(vs)<=10 and
                 all(type(v) is int and 0<v<=nvars for v in vs) and
                 len(set(vs))==len(vs) and
                 parity in (0,1) and type(parity) is int,
                 "invalid XOR source row")
            # Every forbidden assignment of this parity must be excluded by an
            # ORIGINAL full-width clause. No generated/preprocessed CNF accepted.
            for bits in itertools.product((0,1),repeat=len(vs)):
                if sum(bits)%2==parity:
                    clause=frozenset(-v if b else v for v,b in zip(vs,bits))
                    need(clause in clauses,"missing original XOR-cover clause")
            rows.append((set(vs),1-parity))
        need(len(set(combine))==len(combine) and
             all(type(i) is int and 0<=i<len(rows) for i in combine),
             "invalid XOR combination indices")
        variables=set()
        parity=0
        for index in combine:
            variables.symmetric_difference_update(rows[index][0])
            parity^=rows[index][1]
        need(not variables and parity==1,"GF2 combination did not derive 0=1")
        return {"status":"UNSAT_VERIFIED","method":method,
                "rows":len(combine),"source_blocks":len(blocks)}
    if method=="dpll_tree":
        need(nvars<=8,"DPLL proof gate")
        tree=proof.get("tree")
        counter=[0]
        def walk(node,assign):
            counter[0]+=1
            need(counter[0]<=511 and type(node) is dict, "oversized or invalid tree")
            if "clause" in node:
                c=node["clause"]
                need(type(c) is list and frozenset(c) in clauses,
                     "leaf not backed by original clause")
                need(all(type(l) is int and abs(l) in assign and
                     assign[abs(l)]!=(l>0) for l in c),
                     "leaf clause not falsified under its branch")
                return
            v=node.get("split")
            need(type(v) is int and 0<v<=nvars and v not in assign,
                 "invalid or repeated DPLL split")
            need("false" in node and "true" in node,"missing DPLL branch")
            walk(node["false"],dict(assign,**{str(v):False}) if False else {**assign,v:False})
            walk(node["true"],{**assign,v:True})
        walk(tree,{})
        return {"status":"UNSAT_VERIFIED","method":method,
                "proof_nodes":counter[0]}
    raise InvalidProof("unknown certificate method")

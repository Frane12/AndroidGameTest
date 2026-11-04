#!/usr/bin/env python3
"""R81-D: bounded *partial* exact XOR -> CDCL feedback, fail closed.

Unlike R81C, no complete-CNF XOR coverage is required. The source DIMACS is
scanned even when older R28/R63 metadata labels it 'unscannable'. Only
complete parity clause groups count as equations. Unit clauses are included
as GF(2) rows. Bounded elimination produces unit/binary consequences, each
with an independently checkable XOR-row witness grounded in original CNF.
A blind structural rule injects at most 24 proven short clauses into an
unchanged SHA-pinned Kissat process. Passive and direct fallback controls
must be measured separately: sound lemmas can still slow down CDCL.
No in-process Kissat API or continuous live GF(2) interaction is claimed.
"""
from __future__ import annotations
import collections
import hashlib
import json
import tempfile
import time
from pathlib import Path

import r64_mixed_xor_implied as r64
import r81c_exact_algebra as r81c
import r28_exact_gf2_benchmark as r28

PROTOCOL="DRNAS-R81D-PARTIAL-EXACT-XOR-CDCL-20261104-v1"
MAX_SCAN_S=2.5
MAX_TOTAL_PREPROCESS_S=3.5
MAX_EQUATIONS=3072
MAX_DERIVED_CLAUSES=24
MAX_ELIMINATION_ROWS=3072
MAX_CERT_RECHECK=32

def clauses_for_row(vs,rhs):
    return [tuple(sorted(x)) for x in r81c.encode(vs,rhs)]

def verified_row_witness(original_clauses,rows,target_vars,target_rhs):
    """Validate XOR-combination proof using only ORIGINAL CNF clauses."""
    source=set(tuple(sorted(c)) for c in original_clauses)
    vector=0;rhs=0
    for row in rows:
        vs=list(row["vs"]); bit=row["rhs"]
        if (not vs or len(set(vs))!=len(vs) or
            vs!=sorted(vs) or bit not in (0,1)):
            return False
        if row["kind"]=="unit":
            if len(vs)!=1 or (vs[0] if bit else -vs[0],) not in source:
                return False
        elif row["kind"]=="xor":
            if not 2<=len(vs)<=6:
                return False
            if any(cl not in source for cl in clauses_for_row(vs,bit)):
                return False
        else:
            return False
        for v in vs:vector^=1<<(v-1)
        rhs^=bit
    expected=0
    for v in target_vars:expected^=1<<(v-1)
    return vector==expected and rhs==target_rhs

def _clauses_from_row(vars_,rhs):
    if len(vars_)==1:
        v=vars_[0];return [(v if rhs else -v,)]
    if len(vars_)==2:
        a,b=vars_
        if rhs==1:return [(a,b),(-a,-b)]
        return [(-a,b),(a,-b)]
    return []

def _unit_rows(short):
    rows=[]
    for clause in sorted(short):
        if len(clause)==1:
            lit=clause[0]
            rows.append(dict(vs=[abs(lit)],rhs=int(lit>0),kind="unit"))
    return rows

def _reduce(rows,existing,deadline):
    """Sparse independent rows with XOR-proven ancestry; time bounded."""
    basis={}
    short_proofs={}
    visited=0
    for i,row in enumerate(rows):
        if i>=MAX_ELIMINATION_ROWS or time.monotonic()>deadline:
            break
        vector=0
        for v in row["vs"]:vector^=1<<(v-1)
        rhs=row["rhs"]; proof=1<<i
        while vector:
            pivot=vector.bit_length()-1
            old=basis.get(pivot)
            if old is None:
                basis[pivot]=(vector,rhs,proof)
                break
            vector^=old[0];rhs^=old[1];proof^=old[2]
        if not vector and rhs:
            return {}, dict(contradiction=True,processed=i+1,rank=len(basis))
        visited+=1
    # Back-eliminate from lower to higher pivots to find low-weight implicates.
    for pivot in sorted(basis):
        if time.monotonic()>deadline:break
        vec,rhs,proof=basis[pivot]
        for upper in sorted(k for k in basis if k>pivot):
            high,b,ancestor=basis[upper]
            if (high>>pivot)&1:
                basis[upper]=(high^vec,b^rhs,ancestor^proof)
    for pivot in sorted(basis):
        if time.monotonic()>deadline:break
        vector,rhs,proof=basis[pivot]
        if not 1<=vector.bit_count()<=2:continue
        vars_=[];temp=vector
        while temp:
            low=temp&-temp
            vars_.append(low.bit_length())
            temp^=low
        for clause in _clauses_from_row(vars_,rhs):
            canon=tuple(sorted(clause))
            if canon not in existing and canon not in short_proofs:
                short_proofs[canon]=dict(vars=vars_,rhs=rhs,ancestry=proof)
    return short_proofs,dict(contradiction=False,processed=visited,rank=len(basis))

def prepare(original,case,max_budget=MAX_TOTAL_PREPROCESS_S, verify=True):
    """Return proven short lemmas and their independent source witnesses.

    Any failure/time-budget exceedance produces unchanged Kissat fallback.
    Data-driven selection NEVER uses historical solver timing or ground truth.
    """
    start=time.monotonic()
    deadline=start+max_budget
    path=Path(original)
    result=dict(route="kissat_fallback",equations=0,units=0,
                rank=0,derived=0,proven_clauses=[],certificates=[],
                scan_s=0.0,preprocess_s=0.0)
    def fallback(reason):
        result["route"]=reason
        result["preprocess_s"]=round(time.monotonic()-start,6)
        result["proven_clauses"]=[];result["certificates"]=[]
        result["derived"]=0
        return result
    try:
        # Original source SHA is independently checked by the calling runner.
        # Do NOT use case["supported"] or case["complete_blocks"] as a guard.
        r64.SCAN_BUDGET=min(MAX_SCAN_S,max_budget*0.75)
        eq,short=r64.extract_equations(
            path,case["variables"],case["clauses"],start)
        result["scan_s"]=round(time.monotonic()-start,6)
        result["equations"]=len(eq)
        unitrows=_unit_rows(short)
        result["units"]=len(unitrows)
        if time.monotonic()>deadline:
            return fallback("scan_budget_fallback")
        if not eq:
            return fallback("no_complete_xor_fallback")
        # Prefer original units and short equations; the choice is fixed from
        # source structure, never from solver runtime or reference status.
        selected=unitrows[:512]
        selected.extend(dict(vs=list(vs),rhs=int(bit),kind="xor")
                        for vs,bit in eq[:max(0,MAX_EQUATIONS-len(selected))])
        result["selected_equations"]=len(selected)
        proofs,meta=_reduce(selected,short,deadline)
        result.update(meta)
        if meta["contradiction"]:
            # Do not output UNSAT without complete proof verification.
            return fallback("xor_contradiction_unverified_fallback")
        if not proofs:
            return fallback("no_short_lemmas_fallback")
        # Rank short implied clauses by stable structural order:
        # unit, then binary, then variable IDs. Maximum 24 clauses.
        candidates=sorted(proofs,key=lambda clause:(len(clause),
                    tuple(abs(x) for x in clause),clause))[:MAX_DERIVED_CLAUSES]
        if time.monotonic()>deadline:
            return fallback("elimination_budget_fallback")
        if verify:
            # Independent original-CNF verification of each *selected* proof.
            _,cnf=r28.load_clauses(path)
            check=lambda x: bool(x)
            certs=[]
            for clause in candidates:
                if time.monotonic()>deadline:
                    return fallback("certificate_budget_fallback")
                p=proofs[clause]
                witness=[row for i,row in enumerate(selected)
                         if (p["ancestry"]>>i)&1]
                if not verified_row_witness(cnf,witness,p["vars"],p["rhs"]):
                    raise RuntimeError("R81D_INVALID_ORIGINAL_CNF_PROOF")
                certs.append(dict(clause=list(clause),vs=p["vars"],
                                  rhs=p["rhs"],proof=witness))
            result["certificates"]=certs
        result["proven_clauses"]=[list(c) for c in candidates]
        result["derived"]=len(candidates)
        result["route"]="certified_partial_xor_cdcl_lemmas"
        result["preprocess_s"]=round(time.monotonic()-start,6)
        return result
    except (TimeoutError,UnicodeError,ValueError,OSError) as exc:
        return fallback("scanner_error_or_timeout_fallback")
    
def selftest():
    def dimacs(n,clauses):
        return "p cnf %d %d\n"%(n,len(clauses)) + "".join(
            " ".join(map(str,c))+" 0\n" for c in clauses)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        def check_case(name,raw,expected, min_eq=0):
            f=root/name;f.write_text(raw)
            n,clauses=r28.load_clauses(f)
            c=dict(variables=n,clauses=len(clauses),supported=False,complete_blocks=0)
            out=prepare(f,c,3.5)
            assert out["equations"]>=min_eq,(name,out)
            assert out["route"]==expected,(name,out)
            return out,clauses
        xor1=list(r81c.encode([1,2,3],0))
        xor2=list(r81c.encode([1,2,4],0))
        # True XOR constraints + external arbitrary CNF.
        out,cl=check_case("mixed.cnf",dimacs(4,xor1+xor2+[(1,2,3,4)]),
                  "certified_partial_xor_cdcl_lemmas",min_eq=2)
        assert out["derived"]>0,out
        # Independently check semantic equivalence of original and augmented.
        augmented=cl+[tuple(x) for x in out["proven_clauses"]]
        for assignment in range(1<<4):
            def sat(clauses):
                return all(any(bool(assignment&(1<<(abs(v)-1)))==(v>0)
                    for v in row) for row in clauses)
            assert sat(cl)==sat(augmented),out
        near=xor1[:-1]+[(1,2,3,4)]
        decoy,_=check_case("near.cnf",dimacs(4,near),
                      "no_complete_xor_fallback",min_eq=0)
        assert decoy["derived"]==0
        # Unit propagation over certified XOR must derive new unit.
        fixed=list(r81c.encode([1,2,3],1))+[(1,),(2,),(2,3,4)]
        unit,_=check_case("unit.cnf",dimacs(4,fixed),
                  "certified_partial_xor_cdcl_lemmas",min_eq=1)
        assert any(x==[3] for x in unit["proven_clauses"]),unit
        # Metadatum "supported=False" must not suppress real XOR detection.
        print("R81D_PARTIAL_XOR_PROOF_SELFTEST_PASS",json.dumps(dict(
            derived=out["derived"],unit_derived=unit["derived"],
            decoy=decoy["route"],ignored_old_guard=True)),flush=True)

if __name__=="__main__":selftest()

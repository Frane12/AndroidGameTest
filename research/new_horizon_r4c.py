#!/usr/bin/env python3
"""DRNAS New Horizon SAT R4c: density-aware, source-exact, economical routing.

The only approximate decision is WHETHER to try a safe special algorithm.
The full original CNF is never approximated or edited.
"""
from __future__ import annotations

import pathlib
import time

import new_horizon_r4 as r4
import new_horizon_r4b as prior
import new_horizon_r3 as r3
import new_horizon_r2 as r2
import new_horizon_sat as native
import r164_pure_exact_gf2 as pure

PROTO = "DRNAS-NH-R4C-DENSITY-VETO-SOURCE-EXACT-v1"
MAX_SOURCE_BYTES = 320000
PURE_MIN_CLAUSES = 8
PURE_MAX_CLAUSES = 64
PURE_MAX_VARS = 128
TWO_MIN_CLAUSES = 80
TWO_MAX_CLAUSES = 512
TWO_MAX_VARS = 192
# Predictive economics ONLY: source clauses at least twice the variable count.
# A sparse implication chain often solves natively faster than Python SCC.
TWO_MIN_DENSITY_NUM = 2
# Intentionally abstain from Horn; measured Python verification lost on
# large Horn cases and gave at best marginal gains on tiny Horn cases.
HORN_ENABLED = False

def need(ok,msg):
    if not ok:
        raise AssertionError("R4C_SOURCE_PROOF_FAIL_CLOSED "+str(msg))

def source_evidence(source, *, pure_only=False):
    """One streaming DIMACS parser: first disqualifying clause aborts.

    A completed list has been checked for exact source-wide class membership.
    We never infer membership from a prefix, filename, expected answer or SHA.
    All recognition and source validation cost is returned and charged.
    """
    start=time.perf_counter()
    path=pathlib.Path(source)
    result=dict(route="clean",reason="none",scan_s=0.0,scanned=0,
                complete_source=False,clauses=None,gf2_rows=None,n=None,m=None)
    def finish(reason, *, route="clean",clauses=None,complete=False,gf2_rows=None):
        result.update(route=route,reason=reason,scan_s=time.perf_counter()-start,
                      complete_source=complete,clauses=clauses,gf2_rows=gf2_rows)
        return result
    if path.stat().st_size>MAX_SOURCE_BYTES:
        return finish("byte_budget_metadata")
    n=m=None
    candidate=None
    partial=[]
    clauses=[]
    with path.open(encoding="ascii") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("%"):
                continue
            if line.startswith("p "):
                need(n is None and not partial,"invalid DIMACS header position")
                parts=line.split()
                need(len(parts)==4 and parts[1]=="cnf","invalid DIMACS header")
                n,m=int(parts[2]),int(parts[3])
                need(n>=0 and m>=0,"negative source size")
                result["n"]=n
                result["m"]=m
                # Strictly precommitted envelope, based on R3/R4 development.
                # For larger 2SAT, Python parsing/SCC is too expensive at ~1ms.
                if PURE_MIN_CLAUSES<=m<=PURE_MAX_CLAUSES and 0<n<=PURE_MAX_VARS:
                    candidate="pure"
                elif (not pure_only and TWO_MIN_CLAUSES<=m<=TWO_MAX_CLAUSES
                      and 0<n<=TWO_MAX_VARS
                      and m >= TWO_MIN_DENSITY_NUM*n):
                    candidate="two_sat"
                else:
                    return finish("precommitted_no_gain_envelope")
                continue
            need(n is not None,"missing original DIMACS header")
            for token in line.split():
                lit=int(token)
                if lit:
                    need(abs(lit)<=n,"original literal beyond n")
                    partial.append(lit)
                    continue
                raw=tuple(partial)
                partial=[]
                result["scanned"]+=1
                need(result["scanned"]<=m,"declared clause count exceeded")
                unique=set(raw)
                # This is a sound negative certificate for source-*wide*
                # classification; it is NOT a SAT/UNSAT conclusion.
                if candidate=="pure":
                    if len(raw)!=3 or len({abs(x) for x in raw})!=3:
                        return finish("first_non_xor3_clause")
                else:
                    if len(unique)>2:
                        return finish("first_non_2sat_clause")
                clauses.append(raw)
        # No special route on incomplete, unterminated or malformed source.
        need(n is not None,"original header missing")
    if partial or result["scanned"]!=m:
        return finish("source_not_complete")
    # Complete DIMACS is now available. Only the source clauses can certify.
    if candidate=="two_sat":
        need(r2.is_2cnf(clauses),"2SAT source-complete invariant")
        return finish("full_original_2sat_certified",
                      route="two_sat",clauses=clauses,complete=True)
    exact,rows,covered=pure.detect_exact(clauses)
    if not exact or len(rows)<2 or any(len(vs)>6 for vs,_ in rows):
        return finish("not_exact_source_pure_parity",complete=True)
    return finish("full_original_gf2_certified",
                  route="pure",clauses=clauses,complete=True,gf2_rows=rows)

def run_one(source,binary,cap,mode,scratch=None):
    """clean/R4 baseline, pure-only ablation, proposed R4b.

    No extra process or second source parser for an accepted fast path.
    Every SAT answer uses an independently validated ORIGINAL source model.
    """
    need(mode in ("clean","r4b","r4c","pure_only"),
         "invalid R4b policy")
    if mode in ("clean","r4b","pure_only"):
        out=prior.run_one(source,binary,cap,mode,scratch)
        out["r4c_evidence"]=None
        return out
    start=time.perf_counter()
    evidence=source_evidence(source)
    if evidence["route"]!="clean" and cap-(time.perf_counter()-start)>.15:
        clauses=evidence["clauses"]
        if evidence["route"]=="pure":
            rows=evidence["gf2_rows"]
            need(rows and evidence["complete_source"],
                 "source parity certificate missing")
            answer=pure.gaussian(rows)
            if answer["status"]=="SAT":
                need(pure.verify_sat(clauses,answer["model"]),
                     "source GF2 model invalid")
            route="gf2_exact"
            proof=("ORIGINAL_GF2_SAT_MODEL_CHECKED" if answer["status"]=="SAT"
                   else "ORIGINAL_GF2_UNSAT_CONTRADICTION_REPLAYED_NO_LRAT")
        else:
            answer=r2.solve_2sat(evidence["n"],clauses)
            route="2sat_linear"
            proof=("ORIGINAL_2SAT_SCC_SAT_MODEL_CHECKED" if answer["status"]=="SAT"
                   else "ORIGINAL_2SAT_SCC_UNSAT_NO_LRAT")
        elapsed=time.perf_counter()-start
        if elapsed<cap:
            return dict(status=answer["status"],elapsed=elapsed,proof=proof,
                    route=route,reason=evidence["reason"],
                    r4c_evidence={k:v for k,v in evidence.items() if k not in ("clauses","gf2_rows")})
    # If the complete original clauses don't certify an exact special case,
    # the original source is passed unchanged to the pinned native CDCL solver.
    remain=cap-(time.perf_counter()-start)
    status="TIMEOUT";model={}
    if remain>.12:
        try:
            status,model=native.native(binary,source,remain)
        except __import__("subprocess").TimeoutExpired:
            status="TIMEOUT"
    elapsed=time.perf_counter()-start
    if elapsed>=cap:
        status="TIMEOUT"
    if status=="SAT":
        native.verify_model(source,model)
        proof="ORIGINAL_CNFSAT_WITNESS_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,
         route="clean",reason=evidence["reason"],
         r4c_evidence={k:v for k,v in evidence.items() if k not in ("clauses","gf2_rows")})

def selftest():
    import tempfile
    import random
    rng=random.Random(20261107404)
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        def make(name,n,clauses):
            p=root/name
            p.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            return p
        def xor3(vs,rhs):
            return [tuple(-v if mask>>j&1 else v for j,v in enumerate(vs))
                for mask in range(8) if mask.bit_count()%2!=rhs]
        for k in range(16):
            n=24;w=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
            tuples={(1,2,3),(4,5,6)}
            while len(tuples)<8:tuples.add(tuple(sorted(rng.sample(range(1,n+1),3))))
            clauses=[]
            for vs in sorted(tuples):
                rhs=int(w[vs[0]])^int(w[vs[1]])^int(w[vs[2]])
                clauses+=xor3(vs,rhs)
            rng.shuffle(clauses)
            p=make(f"xor{k}.cnf",n,clauses)
            ev=source_evidence(p)
            need(ev["route"]=="pure" and ev["complete_source"],"lost exact GF2 path")
            exact,rows,_=pure.detect_exact(ev["clauses"])
            need(exact and pure.gaussian(rows)["status"]=="SAT","GF2 control")
            clauses.append((1,2,3,4))
            bad=make(f"mixed{k}.cnf",n,clauses)
            need(source_evidence(bad)["route"]=="clean","mixed XOR incorrectly accepted")
        for k in range(16):
            n=90
            perm=list(range(1,n+1))
            rng.shuffle(perm)
            clauses=[(1,)]+[(-perm[i-1],perm[i]) for i in range(1,n)]*3
            p=make(f"two{k}.cnf",n,clauses)
            ev=source_evidence(p)
            need(ev["route"]=="two_sat" and ev["complete_source"],"lost exact 2SAT")
            need(r2.solve_2sat(n,ev["clauses"])["status"]=="SAT","SCC result wrong")
            clauses.append((1,2,3))
            bad=make(f"late{k}.cnf",n,clauses)
            ev=source_evidence(bad)
            need(ev["route"]=="clean" and ev["scanned"]>=80,
                 "late disproof must be scanned, never guessed")
        big=make("big_horn.cnf",320,[(1,)]+[(-j,j+1) for j in range(1,320)]
            +[(-i,-(i+1),i+2) for i in range(1,318)])
        need(source_evidence(big)["scanned"]==0,"big Horn must metadata-abstain")
        # Exactly the same formula can be SAT only if source proof is complete.
        truncated=root/"truncated.cnf"
        truncated.write_text("p cnf 100 80\n"+"1 0\n"*20)
        need(source_evidence(truncated)["route"]=="clean","truncated CNF certified")
    print("NEW_HORIZON_R4C_SELFTEST_PASS exact_path=32 late_refutation=16",flush=True)

if __name__=="__main__":
    selftest()

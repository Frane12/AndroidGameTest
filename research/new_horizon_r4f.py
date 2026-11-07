#!/usr/bin/env python3
"""DRNAS New Horizon R4f: selective mid-veto for chain-like dense 2SAT candidates.

An inexpensive source-only prefix screen may select a middle negative witness
probe. No prefix, tail, or middle sample ever *certifies* 2SAT/GF2/SAT/UNSAT.
Positive special routing remains exclusively R4d's complete source check.
Known-family development heuristic: not validated on external blind SAT.
"""
from __future__ import annotations
import pathlib
import subprocess
import time

import new_horizon_r4d as r4d
import new_horizon_r4e as r4e

PROTO = "DRNAS_NH_R4F_CHAIN_SELECTIVE_MID_V1"
MIN_DENSITY_NUM = 5
MIN_DENSITY_DEN = 2
PREFIX_CLAUSES = 18
CHAIN_LINK_THRESHOLD = 6


def cheap_source_risk(source):
    """Return only a cost prediction from n,m and <=18 complete prefix clauses.

    Generic chain signature: repeated (-u v), next (-v w), without requiring
    variable numbering, generator identity, original path, or expected result.
    """
    p = pathlib.Path(source)
    size = p.stat().st_size
    info = r4e.header_candidate(p, size)
    if info is None:
        return False, "not_candidate", 0
    n, m = info
    if m * MIN_DENSITY_DEN < MIN_DENSITY_NUM * n:
        return False, "sparse_cost_veto", 0
    prev_head = None
    links = 0
    seen = 0
    clause = []
    with p.open("rb") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith((b"c", b"p ", b"%")):
                continue
            try:
                values = [int(x) for x in line.split()]
            except ValueError:
                # Unfamiliar DIMACS syntax: no costly fast-path exploration.
                return False, "prefix_unrecognized", links
            for v in values:
                if v:
                    clause.append(v)
                    continue
                seen += 1
                # Binary implication-chain pattern, not a logical conclusion.
                if len(clause) == 2 and clause[0] < 0 and clause[1] > 0:
                    if prev_head is not None and -clause[0] == prev_head:
                        links += 1
                    prev_head = clause[1]
                elif len(clause) == 1 and seen == 1:
                    pass
                else:
                    prev_head = None
                clause = []
                if seen >= PREFIX_CLAUSES:
                    break
            if seen >= PREFIX_CLAUSES:
                break
    eligible = links >= CHAIN_LINK_THRESHOLD
    return eligible, ("chain_candidate" if eligible else "weak_chain_signal"), links


def source_evidence(source):
    """One negative cost gate before the complete R4d source-verification path."""
    started = time.perf_counter()
    p = pathlib.Path(source)
    eligible, reason, links = cheap_source_risk(p)
    def meta(reason, windows, evidence=None):
        out=dict(reason=reason,chain_links=links,windows=windows,
                 scan_s=time.perf_counter()-started)
        if evidence is not None:
            out["r4d_reason"]=evidence.get("reason")
            out["r4d_scanned"]=evidence.get("scanned")
        return out
    if not eligible:
        return False, meta(reason,0)
    # Check tail FIRST: it is a cheap disqualifying source observation,
    # and avoids redundant mid sampling for already-disqualified formulas.
    if r4d.suffix_refutes_2sat(p):
        return True,meta("tail_witness_before_mid",1)
    size=p.stat().st_size
    with p.open("rb") as fh:
        if r4e.window_has_complete_long_clause(fh,size,size//2):
            return True,meta("middle_long_clause_cost_veto",2)
    # Sampling found no disqualification. Never claim 2SAT from absence.
    return False,meta("no_negative_middle_witness",2)


def run_one(source, binary, cap, mode, scratch=None):
    r4d.need(mode in ("clean","r4d","r4e_mid","r4f_select"),"bad R4f mode")
    if mode == "r4e_mid":
        out=r4e.run_one(source,binary,cap,mode,scratch)
        out["r4f_evidence"]=None
        return out
    if mode in ("clean","r4d"):
        out=r4d.run_one(source,binary,cap,mode,scratch)
        out["r4f_evidence"]=None
        return out
    started=time.perf_counter()
    veto,info=source_evidence(source)
    if not veto:
        # R4d remains the only route allowed to certify exact special cases.
        remaining=cap-(time.perf_counter()-started)
        out=r4d.run_one(source,binary,max(0,remaining),"r4d",scratch)
        out["elapsed"]=time.perf_counter()-started
        if out["elapsed"]>=cap:
            out["status"]="TIMEOUT"
            out["proof"]="CAP"
        out["r4f_evidence"]=info
        return out

    # A complete 3+ literal clause is a sound NEGATIVE 2SAT witness.
    # Never return a SAT verdict from this scan. Use original native solver.
    remain=cap-(time.perf_counter()-started)
    status,model="TIMEOUT",{}
    if remain>.12:
        try:
            status,model=r4d.native.native(binary,source,remain)
        except subprocess.TimeoutExpired:
            status="TIMEOUT"
    elapsed=time.perf_counter()-started
    if elapsed>=cap:
        status="TIMEOUT"
    if status=="SAT":
        r4d.native.verify_model(source,model)
        proof="ORIGINAL_CNFSAT_WITNESS_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:
        proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,route="clean",
                reason=info["reason"],r4f_evidence=info)


def selftest():
    import tempfile
    import random
    r4d.selftest()
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        def write(name,n,clauses):
            p=root/name
            p.write_text(f"p cnf {n} {len(clauses)}\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            return p
        for i in range(16):
            n=122+i
            chain=[(1,)]+[(-k,k+1) for k in range(1,n)]
            dense=chain+[(-k,k+1) for k in range(1,n)]*2
            # Original exact 2SAT must never be eliminated as an accepted class.
            valid=write(f"valid{i}.cnf",n,dense)
            veto,ev=source_evidence(valid)
            r4d.need(not veto,"valid dense 2SAT wrongly vetoed")
            r4d.need(r4d.source_evidence(valid)["route"]=="two_sat",
                     "valid dense 2SAT lost exact route")
            mixed=dense.copy()
            mixed.insert(len(mixed)//2,(1,2,3))
            p=write(f"mixed{i}.cnf",n,mixed)
            r4d.need(not r4d.r2.is_2cnf(mixed),"bad mixed control")
            veto,ev=source_evidence(p)
            r4d.need(veto and ev["reason"]=="middle_long_clause_cost_veto",
                     "failed selective middle source veto")
            # Density should reject sparse original 2SAT at selector stage.
            sparse=write(f"sparse{i}.cnf",n,chain)
            veto,ev=source_evidence(sparse)
            r4d.need(not veto and ev["reason"]=="sparse_cost_veto",
                     "sparse candidate must skip window screening")
            # Tail non-2SAT must be rejected without the middle sample.
            tail=write(f"tail{i}.cnf",n,dense+[(1,2,3)])
            veto,ev=source_evidence(tail)
            r4d.need(veto and ev["reason"]=="tail_witness_before_mid",
                     "tail negative source witness missed")
            # Permutation and nonchain controls: never infer membership.
            perm=dense.copy()
            random.Random(60119+i).shuffle(perm)
            shuffled=write(f"perm{i}.cnf",n,perm)
            veto,_=source_evidence(shuffled)
            r4d.need(not veto,"shuffled valid 2SAT rejected")
        incomplete=root/"incomplete.cnf"
        incomplete.write_text("p cnf 125 375\n"+"1 0\n"*10)
        veto,_=source_evidence(incomplete)
        r4d.need(not veto,"incomplete source must not acquire a certificate")
    print("NH_R4F_SELFTEST_PASS",flush=True)


if __name__=="__main__":
    selftest()

#!/usr/bin/env python3
"""New Horizon SAT R3: early negative certificates, proof-gated exact fast paths.

Approximate timing/routing is allowed. SAT semantics never approximated.
An early clause can REFUTE a candidate tractable class, never certify it.
"""
from __future__ import annotations

import collections
import pathlib
import time
import new_horizon_r2 as r2
import new_horizon_sat as r1
import r164_pure_exact_gf2 as pure

PROTO = "DRNAS_NEW_HORIZON_R3_EARLY_ABSTENTION_v1"
SAMPLE_CAP = 64
TIME_GATE_S = 0.020

def need(c, msg):
    if not c:
        raise AssertionError("R3_FAIL_CLOSED "+str(msg))

def cheap_probe(path):
    """Minimal source-only probe with early stop when all fast methods excluded.
    
    UNKNOWN is not MIXED. Negative observations are sound: any clause with
    >1 positive lit rules out Horn; any >2-literal clause rules out 2-SAT;
    a non-ternary clause rules out source-pure XOR3. Early positive evidence
    is only a hypothesis, subject to full-source verification.
    """
    start=time.perf_counter()
    p=pathlib.Path(path)
    if p.stat().st_size > r2.MAX_SPECIAL_BYTES:
        return dict(route="clean",reason="byte_budget",scan_s=time.perf_counter()-start,
                    sampled=0,stopped_early=True,m=None,n=None,score=None)
    n=m=None;count=0;pending=[]
    horn_ok=True;two_ok=True;xor_ok=True
    patterns=collections.defaultdict(set)
    with p.open(encoding="ascii") as f:
        for raw in f:
            line=raw.strip()
            if not line or line.startswith(("c","%")):
                continue
            if line.startswith("p "):
                need(n is None,"duplicate source header")
                fields=line.split()
                need(len(fields)==4 and fields[1]=="cnf","bad original header")
                n,m=int(fields[2]),int(fields[3])
                need(n>=0 and m>=0,"bad source dimensions")
                if m>r2.MAX_SPECIAL_CLAUSES:
                    return dict(route="clean",reason="clause_budget",
                                scan_s=time.perf_counter()-start,sampled=0,
                                stopped_early=True,m=m,n=n,score=None)
                # Source-pure XOR3 R2 fast path requires all clauses sampled,
                # with at most 64 clauses and a certified full-source equation.
                xor_ok=0<m<=SAMPLE_CAP
                horn_ok=m>=50
                two_ok=m>=50
                if not(horn_ok or two_ok or xor_ok):
                    return dict(route="clean",reason="tiny_unknown",
                                scan_s=time.perf_counter()-start,sampled=0,
                                stopped_early=True,m=m,n=n,score=None)
                continue
            need(n is not None,"clauses before CNF header")
            for tok in line.split():
                lit=int(tok)
                if lit:
                    need(abs(lit)<=n and abs(lit)>0,"out-of-range literal")
                    pending.append(lit)
                else:
                    c=set(pending)
                    pending=[]
                    count+=1
                    need(count<=m,"source clause count overflow")
                    if horn_ok and sum(z>0 for z in c)>1:horn_ok=False
                    if two_ok and len(c)>2:two_ok=False
                    if xor_ok:
                        if len(c)!=3 or len({abs(z) for z in c})!=3:
                            xor_ok=False
                        else:
                            lits=sorted(c,key=abs)
                            vs=tuple(abs(z) for z in lits)
                            sign=sum((1<<k) for k,z in enumerate(lits) if z<0)
                            patterns[vs].add(sign)
                    if not (horn_ok or two_ok or xor_ok):
                        return dict(route="clean",reason="all_classes_refuted",
                                    scan_s=time.perf_counter()-start,
                                    sampled=count,stopped_early=True,m=m,n=n,score=None)
                    if count>=SAMPLE_CAP:break
            if count>=SAMPLE_CAP:break
    need(n is not None and count==min(m,SAMPLE_CAP),"partial source probe")
    info=dict(n=n,m=m,scan_s=time.perf_counter()-start,sample=count)
    cand=[]
    if xor_ok and count==m:
        quartets=0
        for masks in patterns.values():
            for parity in (0,1):
                if all(j in masks for j in range(8) if j.bit_count()%2==parity):
                    quartets+=1
        if quartets>=2:cand.append("pure")
    if horn_ok:cand.append("horn")
    if two_ok:cand.append("two_sat")
    if info["scan_s"]>TIME_GATE_S:
        return dict(route="clean",reason="scan_walltime_budget",sampled=count,
                    stopped_early=(count<m),score=None,**info)
    scored=[(method,r2.linear_cost_surrogate(info,method)) for method in cand]
    passed=[(method,score) for method,score in scored if score["choice"]=="certify"]
    if not passed:
        return dict(route="clean",reason="unknown_or_margin_rejected",
                    sampled=count,stopped_early=(count<m),score=dict(candidates=scored),
                    **info)
    route,score=max(passed,key=lambda x:x[1]["benefit_ms"])
    return dict(route=route,reason="candidate_requires_complete_source_proof",
                sampled=count,stopped_early=(count<m),score=score,**info)

def check_exact(source, route):
    """Full original clauses are required; no guessed transformation."""
    n,clauses=pure.parse_dimacs(source)
    if route=="horn":
        if not r2.is_horn(clauses):return None
        result=r2.solve_horn(n,clauses)
        return (result["status"],"HORN_SOURCE_FULL_EXACT_NO_LRAT","horn_linear")
    if route=="two_sat":
        if not r2.is_2cnf(clauses):return None
        result=r2.solve_2sat(n,clauses)
        return (result["status"],"2SAT_SOURCE_FULL_EXACT_NO_LRAT","2sat_linear")
    if route=="pure":
        exact,rows,covered=pure.detect_exact(clauses)
        if not exact or any(len(vs)>6 for vs,rhs in rows):return None
        result=pure.gaussian(rows)
        if result["status"]=="SAT":
            need(pure.verify_sat(clauses,result["model"]),"GF2 model invalid original")
        return (result["status"],
                "GF2_SOURCE_EQUIV_SAT_CHECK_OR_UNSAT_SOURCE_TRACE_NO_LRAT","gf2_exact")
    return None

def run_one(source,binary,cap,mode,scratch=None):
    """Four modes clean, shadow, r2, r3; true matched comparison."""
    need(mode in ("clean","shadow","r2","r3"),"unsupported R3 arm")
    if mode=="r2":
        a=r2.run_one(source,binary,cap,"r2",scratch)
        a["r3_probe"]=None
        return a
    if mode=="clean":
        a=r2.run_one(source,binary,cap,"clean",scratch)
        a["r3_probe"]=None
        return a
    start=time.perf_counter()
    fp=cheap_probe(source)
    route=fp["route"];reason=fp["reason"]
    if mode=="r3" and route!="clean" and cap-(time.perf_counter()-start)>0.15:
        exact=check_exact(source,route)
        if exact is not None:
            status,proof,method=exact
            elapsed=time.perf_counter()-start
            if elapsed<cap:
                return dict(status=status,elapsed=elapsed,proof=proof,
                            route=method,reason="full_source_certified",
                            screen=dict(scan_s=fp["scan_s"]),r3_probe=fp)
            route="clean";reason="full_source_preprocessing_expired"
        else:
            route="clean";reason="complete_source_refuted_candidate"
    else:
        route="clean"
        if mode=="shadow":reason="probe_shadow_only"
    rem=cap-(time.perf_counter()-start)
    status="TIMEOUT";model={}
    if rem>.12:
        try:status,model=r1.native(binary,source,rem)
        except __import__("subprocess").TimeoutExpired:status="TIMEOUT"
    elapsed=time.perf_counter()-start
    if elapsed>=cap:status="TIMEOUT"
    if status=="SAT":
        r1.verify_model(source,model)
        proof="ORIGINAL_SHA_SAT_WITNESS_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,route=route,
                reason=reason,screen=dict(scan_s=fp["scan_s"]),r3_probe=fp)

def selftest():
    import random,tempfile
    randomizer=random.Random(20261107103)
    with tempfile.TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        def write(name,n,clauses):
            p=root/name
            p.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(
                " ".join(map(str,c))+" 0\n" for c in clauses))
            return p
        # A single early clause can refute all classes. Must not scan 64.
        bad=write("bad.cnf",24,[(1,2,3),(4,5,6),(-1,-2,-3)])
        info=cheap_probe(bad)
        need(info["route"]=="clean" and info["sampled"]==1 and info["stopped_early"],
             "immediate abstention")
        # False-positive prefixes: never allow 2SAT/Horn answer without
        # checking the complete source, including clause 65+.
        clauses=[(-i,i+1) for i in range(1,96)]+[(1,2,3)]
        trap=write("late.cnf",96,clauses)
        p=cheap_probe(trap)
        need(p["route"] in ("horn","two_sat"),"tricky prefix hypothesis")
        need(check_exact(trap,p["route"]) is None,"late original clause escaped proof gate")
        # Equivalence under variable renaming and clause reordering for 2SAT.
        for k in range(20):
            n=80
            clauses=[(-i,i+1) for i in range(1,n)]
            perm=list(range(1,n+1));randomizer.shuffle(perm)
            source=write(f"two-{k}.cnf",n,[tuple((1 if v>0 else -1)*
                     perm[abs(v)-1] for v in c) for c in clauses[::-1]])
            s=cheap_probe(source)
            need(s["route"] in ("horn","two_sat"),"variable-rename lost tractable candidate")
            a=check_exact(source,s["route"])
            need(a is not None and a[0]=="SAT","renamed exact SAT model")
        # Known pure exact XOR3 R2 canonical path remains available.
        def xor(vs,rhs):
            return [tuple(-v if mask>>j&1 else v for j,v in enumerate(vs))
                    for mask in range(8) if mask.bit_count()%2 != rhs]
        clauses=xor((1,2,3),1)+xor((4,5,6),1)
        p=write("pure.cnf",6,clauses)
        info=cheap_probe(p)
        need(info["route"]=="pure","source-complete parity lost")
        need(check_exact(p,"pure")[0]=="SAT","pure GF2 source exact")
        # Early disproof on source with >>64 clauses cannot claim XOR-purity.
        p=write("many.cnf",100,clauses*9)
        need(cheap_probe(p)["route"]=="clean","more than 64 not pure proof")
    r2.selftest()
    print("NEW_HORIZON_R3_SELFTEST_PASS",flush=True)

if __name__=="__main__":selftest()

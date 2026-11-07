#!/usr/bin/env python3
"""DRNAS New Horizon SAT R4 — bounded negative evidence and robust method economics.

No SAT clause or proof is approximate. Only *cost selection* is approximate.
A small source-only preview may REFUTE a class, never certify membership.
R3 remains frozen as causal control.
"""
from __future__ import annotations
import collections
import pathlib
import time
import new_horizon_r2 as r2
import new_horizon_r3 as r3
import new_horizon_sat as r1

PROTOCOL="DRNAS-NH-R4-CERTIFIED-MICRO-COST-ABSTENTION-v1"
CLAUSE_PREVIEW=64
MAX_BYTES=r2.MAX_SPECIAL_BYTES
MAX_CLAUSES=r2.MAX_SPECIAL_CLAUSES
# A conservative, precommitted family-specific policy. The R3 development
# batch contains small Horn regressions. Avoid routing tiny Horn instances.
HORN_MIN_VARS=256
HORN_MIN_CLAUSES=300
TWO_MIN_CLAUSES=80
PURE_MAX_CLAUSES=64
PREFLIGHT_TIME_BUDGET_S=0.012

def need(x,msg):
    if not x:raise RuntimeError("NH_R4_FAIL_CLOSED "+str(msg))

def sniff(source):
    """At most 64 clauses. No SHA, filename, family or answer influences routing.

    A refutation of Horn/2SAT is sound *for the full formula*. A candidate
    match is not proof: the exact source verifier must still run.
    """
    start=time.perf_counter()
    path=pathlib.Path(source)
    size=path.stat().st_size
    if size>MAX_BYTES:
        return dict(route="clean",reason="file_size_abstain",sampled=0,
                    scan_s=time.perf_counter()-start,negative_certificates=[],
                    completed_source=False,score=None)
    n=m=None
    active=set()
    patterns=collections.defaultdict(set)
    nseen=0
    pending=[]
    seen_refute=set()
    stopped=False
    with path.open(encoding="ascii") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                need(n is None,"source header duplicated")
                hdr=line.split()
                need(len(hdr)==4 and hdr[1]=="cnf","unsupported DIMACS")
                n,m=int(hdr[2]),int(hdr[3])
                need(n>=0 and m>=0,"invalid source dimensions")
                if m>MAX_CLAUSES:
                    return dict(route="clean",reason="clause_count_abstain",
                                sampled=0,scan_s=time.perf_counter()-start,
                                negative_certificates=[],completed_source=False,score=None)
                if m>=HORN_MIN_CLAUSES and n>=HORN_MIN_VARS:
                    active.add("horn")
                if m>=TWO_MIN_CLAUSES:
                    active.add("two_sat")
                if 0<m<=PURE_MAX_CLAUSES:
                    active.add("pure")
                if not active:
                    return dict(route="clean",reason="precommitted_cost_envelope",
                                sampled=0,scan_s=time.perf_counter()-start,
                                negative_certificates=[],completed_source=False,score=None)
                continue
            need(n is not None,"clause preceding DIMACS header")
            for tok in line.split():
                lit=int(tok)
                if lit:
                    need(abs(lit)<=n and lit!=0,"source literal range")
                    pending.append(lit)
                else:
                    c=set(pending)
                    pending=[]
                    nseen+=1
                    if "horn" in active and sum(l>0 for l in c)>1:
                        active.remove("horn");seen_refute.add("horn")
                    if "two_sat" in active and len(c)>2:
                        active.remove("two_sat");seen_refute.add("two_sat")
                    if "pure" in active:
                        if len(c)!=3 or len({abs(l) for l in c})!=3:
                            active.remove("pure");seen_refute.add("pure")
                        else:
                            ordered=sorted(c,key=abs)
                            key=tuple(abs(l) for l in ordered)
                            mask=sum((1<<i) for i,l in enumerate(ordered) if l<0)
                            patterns[key].add(mask)
                    if not active:
                        stopped=True
                        break
                    if nseen==CLAUSE_PREVIEW:
                        stopped=True
                        break
            if stopped:break
    need(n is not None,"missing CNF header")
    need(nseen==min(m,CLAUSE_PREVIEW) or not active,
         "truncated preview / invalid source")
    scanned_s=time.perf_counter()-start
    complete=(nseen==m and not pending)
    opts=[]
    if "pure" in active and complete:
        count=0
        for patterns_for_vars in patterns.values():
            for parity in (0,1):
                if all((mask in patterns_for_vars) for mask in range(8)
                       if mask.bit_count()%2==parity):
                    count+=1
        if count>=2:opts.append("pure")
    if "two_sat" in active:opts.append("two_sat")
    if "horn" in active:opts.append("horn")
    if scanned_s>PREFLIGHT_TIME_BUDGET_S:
        return dict(route="clean",reason="probe_time_budget",
                    sampled=nseen,scan_s=scanned_s,n=n,m=m,score=None,
                    completed_source=complete,negative_certificates=sorted(seen_refute))
    info=dict(n=n,m=m,scan_s=scanned_s)
    predicted=[(method,r2.linear_cost_surrogate(info,method)) for method in opts]
    profitable=[(method,cost) for method,cost in predicted if cost["choice"]=="certify"]
    if profitable:
        method,score=max(profitable,key=lambda item:item[1]["benefit_ms"])
        return dict(route=method,reason="candidate_full_verification_required",
                    sampled=nseen,scan_s=scanned_s,n=n,m=m,score=score,
                    completed_source=complete,negative_certificates=sorted(seen_refute))
    return dict(route="clean",reason=("all_fast_classes_refuted" if not active
                else "cost_envelope_or_unrecognized"),
                sampled=nseen,scan_s=scanned_s,n=n,m=m,score=None,
                completed_source=complete,negative_certificates=sorted(seen_refute))

def run_one(source,binary,cap,mode,scratch=None):
    """Four arms: clean, shadow (R4 observer only), R3 and R4."""
    need(mode in ("clean","shadow","r3","r4"),"bad trial strategy")
    if mode in ("clean","r3"):
        out=r3.run_one(source,binary,cap,mode,scratch)
        out["r4_observer"]=None
        return out
    start=time.perf_counter()
    probe=sniff(source)
    route=probe["route"]
    reason=probe["reason"]
    if mode=="r4" and route!="clean" and cap-(time.perf_counter()-start)>0.15:
        # Before *any* special solve, verify the ENTIRE original CNF.
        exact=r3.check_exact(source,route)
        if exact is not None:
            status,proof,method=exact
            elapsed=time.perf_counter()-start
            if elapsed<cap:
                return dict(status=status,elapsed=elapsed,proof=proof,
                     reason="R4_FULL_SOURCE_VERIFIED",route=method,
                     r4_observer=probe)
            reason="source_check_exceeded_cap"
        else:
            reason="source_complete_verification_rejected"
    elif mode=="shadow":reason="R4_SHADOW_NO_DECISION"
    remaining=cap-(time.perf_counter()-start)
    status="TIMEOUT";model={}
    if remaining>0.12:
        try:
            status,model=r1.native(binary,source,remaining)
        except __import__("subprocess").TimeoutExpired:
            status="TIMEOUT"
    elapsed=time.perf_counter()-start
    if elapsed>=cap:status="TIMEOUT"
    if status=="SAT":
        r1.verify_model(source,model)
        proof="SOURCE_ORIGINAL_SHA_SAT_WITNESS"
    elif status=="UNSAT":proof="NATIVE_UNSAT_WITHOUT_INDEPENDENT_LRAT"
    else:proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,route="clean",
                reason=reason,r4_observer=probe)

def selftest():
    import random,tempfile
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d)
        def make(name,n,clauses):
            path=root/name
            path.write_text("p cnf "+str(n)+" "+str(len(clauses))+"\n"+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            return path
        # Tiny Horn should be avoided at metadata stage, not sampled.
        small=make("small_horn.cnf",80,[(1,)]+[(-i,i+1) for i in range(1,79)])
        p=sniff(small)
        need(p["route"]=="clean" and p["sampled"]==0,"small Horn should abstain")
        # First-clause disqualification of both exact classes -> no wasted scan.
        unknown=make("unknown.cnf",320,[(1,2,3,4)]*600)
        p=sniff(unknown)
        need(p["route"]=="clean" and p["sampled"]==1 and
             {"horn","two_sat"}<=set(p["negative_certificates"]),
             "early refutation did not trigger")
        # Larger exactly Horn, smaller 2SAT, XOR3 remain source complete.
        h=make("h.cnf",320,[(1,)]+[(-i,i+1) for i in range(1,320)]+
              [(-i,-(i+1),i+2) for i in range(1,319)])
        a=sniff(h)
        need(a["route"]=="horn","missed large source Horn")
        need(r3.check_exact(h,a["route"])[0]=="SAT","Horn witness")
        s=make("s.cnf",100,[(-i,i+1) for i in range(1,100)])
        a=sniff(s)
        need(a["route"]=="two_sat","missed source 2SAT")
        need(r3.check_exact(s,a["route"])[0]=="SAT","2SAT witness")
        def xor(vs,rhs):
            return [tuple(-v if mask>>j&1 else v for j,v in enumerate(vs))
                for mask in range(8) if mask.bit_count()%2!=rhs]
        pure=make("x.cnf",6,xor((1,2,3),1)+xor((4,5,6),0))
        a=sniff(pure)
        need(a["route"]=="pure" and r3.check_exact(pure,"pure")[0]=="SAT",
             "pure XOR regression")
        # Contradictory evidence after initial 64 clauses MUST reject before
        # special solving. A prefix never licenses an UNSAT assertion.
        trap=make("t.cnf",320,[(-i,i+1) for i in range(1,320)]+
             [(1,2,3)]+[(-i,-(i+1),i+2) for i in range(1,319)])
        a=sniff(trap)
        need(a["route"]=="horn","false-positive prefix test must be challenging")
        need(r3.check_exact(trap,"horn") is None,
             "late contradiction of family escaped full proof gate")
    # Existing R3 and R2 random brute force selfchecks still required.
    r3.selftest()
    print("NEW_HORIZON_R4_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    selftest()

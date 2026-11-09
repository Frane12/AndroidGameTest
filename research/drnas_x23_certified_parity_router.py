#!/usr/bin/env python3
"""DRNAS X23: source-certified GF(2) inconsistency before CDCL.

Four one-vCPU paired E2E strategies on six deliberately REUSED X21 CNFs:
Kissat original, native original, a shadow parity scan then Kissat, and the
exact proof-first parity router. Any algebraic UNSAT is checked by a SECOND
independently implemented parity-block reconstruction and GF2 elimination.
No LRAT, no new blindness claim, no promotion to stable solver.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, resource, signal
import subprocess, tempfile, time, random
import drnas_x22_exact_projection as x22
import drnas_x22_xor_forensics as gf
import drnas_x18_selective as x18
import drnas_x16_singlecore_dual as x16

ROOT=pathlib.Path("mre_x23")
PROTO="DRNAS-X23-SOURCE-PARITY-PROOF-FIRST-6KNOWN-4ARM-2REP-18S-v1"
ARMS=("kissat1","native1","parity_shadow","parity_certified")
CAP=18.0
MAX_BYTES=256*1024
REPS=2
SHARDS=6

def need(condition,msg):
    if not condition:raise RuntimeError("X23_FAIL_CLOSED "+str(msg))

def independently_certify(nvars,clauses):
    """Independent proof checker: exact truth-table CNF block cover + GF2.

    Every row verified against ORIGINAL clauses. Uses opposite pivot order
    from X22's extractor and independently replays contradiction dependency.
    """
    blocks={}
    for clause in clauses:
        length=len(clause)
        if length<2 or length>8:continue
        sorted_lits=sorted(clause,key=lambda z:abs(z))
        support=tuple(abs(z) for z in sorted_lits)
        if len(set(support))!=length:continue
        pattern=0
        for i,z in enumerate(sorted_lits):
            if z<0:pattern|=1<<i
        blocks.setdefault(support,set()).add(pattern)
    equations=[];direct=None
    for support,seen in blocks.items():
        k=len(support)
        if len(seen)==(1<<k):
            direct=dict(reason="all assignments forbidden by source clauses",
                        support=support,patterns=len(seen))
        if len(seen)!=(1<<(k-1)):continue
        # Verify every AND ONLY source falsification of a single parity.
        even={i for i in range(1<<k) if i.bit_count()%2==0}
        odd={i for i in range(1<<k) if i.bit_count()%2==1}
        if seen==even:rhs=1
        elif seen==odd:rhs=0
        else:continue
        mask=0
        for v in support:mask|=1<<(v-1)
        equations.append((mask,rhs,support))
    basis={};contradiction=None
    for idx,(orig,orhs,support) in enumerate(equations):
        mask=orig;rhs=orhs;deps=1<<idx
        while mask:
            low=(mask&-mask).bit_length()-1
            if low not in basis:
                basis[low]=(mask,rhs,deps)
                break
            a,b,c=basis[low]
            mask^=a;rhs^=b;deps^=c
        else:
            if rhs:
                used=[i for i in range(len(equations)) if deps>>i&1]
                total_mask=0;total_rhs=0
                for i in used:
                    a,b,_=equations[i]
                    total_mask^=a;total_rhs^=b
                need(total_mask==0 and total_rhs==1,
                     "independent GF2 certificate replay failed")
                contradiction=dict(reason="parity-source GF2 inconsistency",
                    count=len(used),row_indexes=used,
                    proof_replay_variables_xor_zero=True,
                    proof_replay_rhs_xor_one=True,
                    equations=[dict(vars=list(equations[i][2]),rhs=equations[i][1])
                               for i in used])
                break
    certificate=contradiction or direct
    return dict(verified=bool(certificate),certificate=certificate,
                rows=len(equations),rank=len(basis),
                clause_supports=len(blocks))

def parity_prepass(src):
    if src.stat().st_size>MAX_BYTES:
        return dict(verified=False,skipped="source_over_256KiB",certificate=None,
                    certified_rows=0)
    n,clauses,_=x22.parse(src)
    predicted=gf.analyze(n,clauses)
    independent=independently_certify(n,clauses)
    need(predicted["direct_source_GF2_contradiction"]==independent["verified"],
         "two independent algorithms disagree on source contradiction")
    need(predicted["certified_xor_rows"]==independent["rows"],
         "independent parity block counts disagree")
    result=dict(verified=independent["verified"],skipped=False,
        certified_rows=predicted["certified_xor_rows"],
        rank=predicted["xor_rank"],check_rank=independent["rank"],
        gf2_contradiction=bool(predicted["gaussian_contradiction"]),
        certificate=independent["certificate"],
        coverage=predicted["certified_xor_clause_coverage"],
        source_sha256=x22.sha(src))
    return result

def proof_selftest():
    gf.selftest()
    def parity(vars,forbidden):
        return [tuple(-v if m>>i&1 else v for i,v in enumerate(vars))
            for m in range(1<<len(vars)) if m.bit_count()%2==forbidden]
    uns=parity((1,2),1)+parity((2,3),1)+parity((1,3),0)
    yes=independently_certify(3,uns)
    need(yes["verified"] and yes["certificate"]["proof_replay_rhs_xor_one"],
         "GF2 parity inconsistency test")
    valid=independently_certify(3,parity((1,2,3),0))
    need(not valid["verified"],"single XOR must not be declared UNSAT")
    # Remove a forbidden pattern: no complete XOR block may be inferred.
    invalid=independently_certify(3,parity((1,2,3),0)[1:])
    need(not invalid["verified"] and invalid["rows"]==0,
         "incomplete source XOR group was accepted")
    print("X23_TWO_ALGORITHM_CERTIFICATE_SELFTEST_PASS",flush=True)

def cases():
    return x22.cases()

def trial(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"arm or rep invalid")
    src=x22.x21.ROOT/c["filename"];need(x22.sha(src)==c["sha256"],
                                           "original source sha mismatch")
    cpu=x16.topology()["first"];seed=x18.seed(c,rep)
    cb=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    pb=x16.rusage_snapshot(resource.RUSAGE_SELF)
    start=time.perf_counter();status="TIMEOUT";backend=None;pre={}
    if arm in ("parity_shadow","parity_certified"):
        pre=parity_prepass(src)
        if pre["verified"] and arm=="parity_certified":
            status="UNSAT";backend="independent_source_parity_proof"
    prep_s=time.perf_counter()-start
    if status!="UNSAT" and prep_s<CAP-.005:
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            out=open(pathlib.Path(td)/"stdout","w+t")
            err=open(pathlib.Path(td)/"stderr","w+t")
            try:
                which="native" if arm=="native1" else "kissat"
                p=subprocess.Popen(x16.command(which,src,seed),stdout=out,stderr=err,
                    start_new_session=True,
                    preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
                try:p.wait(timeout=CAP-(time.perf_counter()-start))
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait()
                out.flush();out.seek(0);err.flush();err.seek(0)
                stdout=out.read();stderr=err.read()
                if time.perf_counter()-start<CAP and p.returncode in (0,10,20):
                    status=x16.x14.outcome_of(which,p.returncode,stdout,stderr,src)
                    backend=which
            finally:
                out.close();err.close()
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status="TIMEOUT";backend=None
    cpu_s=x16.counters_diff(cb,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))["cpu_s"]
    parent_s=x16.counters_diff(pb,x16.rusage_snapshot(resource.RUSAGE_SELF))["cpu_s"]
    return dict(protocol=PROTO,gbd=c["gbd"],original_sha256=c["sha256"],
        arm=arm,rep=rep,seed=seed,status=status,selected_backend=backend,
        elapsed_s=round(elapsed,6),PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        preprocess_s=round(prep_s,6),child_cpu_s=cpu_s,parent_cpu_s=parent_s,
        max_logical_cpus=1,source_GF2_certificate_validated=bool(pre.get("verified")),
        SAT_original_witness_verified=status=="SAT",UNSAT_independent_LRAT=False,
        certified_xor_rows=pre.get("certified_rows",0),skipped=pre.get("skipped",False),
        certificate=pre.get("certificate") if arm=="parity_certified" else None)

def shard(i):
    roster=cases();need(0<=i<6,"shard id")
    c=roster[i];rows=[];ROOT.mkdir(exist_ok=True)
    for rep in range(REPS):
        arms=list(ARMS);random.Random(x18.seed(c,rep)).shuffle(arms)
        for arm in arms:
            r=trial(c,rep,arm);rows.append(r)
            x22.save(ROOT/("shard-%d.json"%i),rows)
            print("X23_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==8,"incomplete shard")
    print("X23_SHARD_PASS",i,8,flush=True)

def audit():
    roster=cases();rows=[]
    for i in range(SHARDS):
        rows+=json.loads((ROOT/("shard-%d.json"%i)).read_text())
    expected={(c["sha256"],rep,arm) for c in roster for rep in (0,1) for arm in ARMS}
    need(len(rows)==48 and {(r["original_sha256"],r["rep"],r["arm"]) for r in rows}==expected,
         "SHA seed arm matrix incomplete")
    for c in roster:
        g=[r for r in rows if r["original_sha256"]==c["sha256"]]
        need(len({r["status"] for r in g if r["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT contradiction")
        original_backends={r["selected_backend"] for r in g if
            r["arm"] in ("kissat1","native1") and r["status"]=="UNSAT"}
        corroborated=len(original_backends)>=2
        source_certificate=any(r["source_GF2_certificate_validated"] for r in g)
        if source_certificate:
            src=x22.x21.ROOT/c["filename"]
            need(parity_prepass(src)["verified"],"audit could not replay GF2 certificate")
        for r in g:
            need(r["protocol"]==PROTO and r["max_logical_cpus"]==1,
                 "protocol CPU mismatch")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "SAT witness mismatch")
            r["accepted"]=r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                                (corroborated or source_certificate))
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    scores={}
    for arm in ARMS:
        g=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(n=len(g),solved=sum(r["accepted"] for r in g),
            SAT_verified=sum(r["status"]=="SAT" and r["accepted"] for r in g),
            UNSAT_source_certified=sum(r["status"]=="UNSAT" and r["accepted"] and
                                       r["source_GF2_certificate_validated"] for r in g),
            unaccepted_UNSAT=sum(r["status"]=="UNSAT" and not r["accepted"] for r in g),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in g),6),
            CPU_PAR2_s=round(sum(r["child_cpu_s"]+r["parent_cpu_s"] if r["accepted"]
                                 else 2*CAP for r in g),6))
    report=dict(protocol=PROTO,sources=6,trials=48,overall=scores,
        per_source=[dict(gbd=c["gbd"],sha256=c["sha256"],
            trials=[r for r in rows if r["original_sha256"]==c["sha256"]]) for c in roster],
        evidence_type="independently_replayed_source_GF2_equational_contradiction_not_LRAT",
        development_on_known_X21_sources=True,no_global_blind_claim=True,
        independent_UNSAT_LRAT=False,no_auto_promotion=True)
    x22.save(ROOT/"report.json",report)
    print("X23_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
                                sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args();ROOT.mkdir(exist_ok=True)
    if a.action=="selftest":proof_selftest()
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__":main()

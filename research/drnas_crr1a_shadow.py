#!/usr/bin/env python3
"""DRNAS CRR1-A: certified cross-representation SHADOW, never edits solver CNF.

CNF complete parity blocks -> GF(2) row combinations -> logical unit/binary
consequences -> simulated CNF unit propagation; binary implication SCC metrics.
Every XOR candidate carries a replayable combination of exact CNF parity blocks.
The original input is passed byte-for-byte to pinned Kissat in BOTH benchmark
arms. This is a reused 24-source development cohort, NOT a blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time

ROOT=Path("crr1a")
SOURCE=Path("history/w4sources/sources")
PROTO="DRNAS-CRR1A-SHADOW-W4-24x2x3-15s-v1"
MODES=("kissat_plain","crr_shadow")
REPS=3
SHARDS=8
CAP=15.0
KISSAT=Path("built/bin/kissat_4_0_4")
CHECKER=Path("checker/drat-trim")
ANALYSIS_CAP=0.75
MAX_EQ=768
MAX_CANDIDATES=256

def need(ok,msg):
    if not ok:raise RuntimeError("CRR1A_FAIL_CLOSED "+str(msg))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def parse(path):
    n=declared=None
    clauses=[];pending=[]
    for line in Path(path).read_text().splitlines():
        st=line.strip()
        if not st or st.startswith(("c","%")):continue
        if st.startswith("p "):
            tok=st.split()
            need(len(tok)==4 and tok[:2]==["p","cnf"],"DIMACS header")
            n,declared=map(int,tok[2:])
            need(1<=n<=200000 and 0<=declared<=180000,"DIMACS bounds")
            continue
        need(n is not None,"missing DIMACS header")
        for tok in st.split():
            v=int(tok)
            need(abs(v)<=n,"out of bounds literal")
            if v:pending.append(v)
            else:
                clauses.append(tuple(pending));pending=[]
                need(len(clauses)<=declared,"too many clauses")
    need(n is not None and not pending and len(clauses)==declared,"incomplete CNF")
    return n,clauses

def xor_blocks(clauses,deadline):
    # Exact complete parity masks, same assignment semantics as R28.
    groups={}
    for index,c in enumerate(clauses):
        if index%512==0 and time.perf_counter()>=deadline:
            raise TimeoutError("xor collection budget")
        k=len(c)
        if k<2 or k>5 or len({abs(x) for x in c})!=k:continue
        lits=sorted(c,key=lambda v:abs(v))
        vars_=tuple(abs(x) for x in lits)
        m=sum((1<<j) for j,v in enumerate(lits) if v<0)
        g=groups.setdefault(vars_,{})
        g.setdefault(m,index)
    equations=[]
    premise_clauses=set()
    for vars_,masks in groups.items():
        k=len(vars_)
        for forbidden_parity in (0,1):
            req=[m for m in range(1<<k) if (m.bit_count()&1)==forbidden_parity]
            if all(mask in masks for mask in req):
                rhs=1-forbidden_parity
                ids=[masks[m] for m in req]
                equations.append((frozenset(vars_),rhs,tuple(ids)))
                premise_clauses.update(ids)
                if len(equations)>=MAX_EQ:
                    return equations,len(premise_clauses),True
    return equations,len(premise_clauses),False

def replay(equations,indices,variables,rhs,clauses):
    # Independent implication replay: each parity block must contain every
    # forbidden truth assignment as an actual ORIGINAL CNF clause.
    acc=set(); parity=0
    for i in indices:
        vs,bit,ids=equations[i]
        need(len(ids)==1<<(len(vs)-1),"incomplete CNF parity premise")
        signs=set()
        for idx in ids:
            c=clauses[idx]
            need(len(c)==len(vs) and frozenset(map(abs,c))==vs,
                 "parity premise variable mismatch")
            ordered=sorted(c,key=lambda x:abs(x))
            signs.add(sum((1<<j) for j,x in enumerate(ordered) if x<0))
        need(len(signs)==len(ids),"reused CNF parity masks")
        need(all(((m.bit_count()&1)!=bit) in (m in signs)
                 for m in range(1<<len(vs))),"parity premise invalid")
        acc.symmetric_difference_update(vs)
        parity^=bit
    need(acc==set(variables) and parity==rhs,"GF2 certificate replay mismatch")
    return True

def to_binary(vars_,rhs):
    a,b=sorted(vars_)
    if rhs==0: return ((a,-b),(-a,b))
    return ((a,b),(-a,-b))

def up(clauses,extra,deadline):
    # Bounded, straightforward oracle used ONLY for accurate shadow metrics.
    # If budget expires, no novel propagation count is reported.
    all_clauses=list(clauses)+list(extra)
    if len(all_clauses)>35000:return None
    values={}
    while True:
        if time.perf_counter()>deadline:return None
        changed=False
        for j,c in enumerate(all_clauses):
            if j%512==0 and time.perf_counter()>deadline:return None
            unknown=0;last=0;satisfied=False
            for lit in c:
                val=values.get(abs(lit))
                if val is None:unknown+=1;last=lit
                elif val==(lit>0):
                    satisfied=True;break
            if satisfied:continue
            if unknown==0:return {"conflict":True,"fixed":values}
            if unknown==1:
                v=abs(last);value=last>0
                if v in values and values[v]!=value:
                    return {"conflict":True,"fixed":values}
                if v not in values:
                    values[v]=value;changed=True
        if not changed:break
    return {"conflict":False,"fixed":values}

def graph_metrics(clauses,deadline):
    # Every directed edge is justified by an original binary clause.
    adj=collections.defaultdict(list)
    rev=collections.defaultdict(list)
    edges=0
    for i,c in enumerate(clauses):
        if i%1024==0 and time.perf_counter()>deadline:return {"skipped":"budget"}
        if len(c)!=2 or abs(c[0])==abs(c[1]):continue
        a,b=c
        for u,v in ((-a,b),(-b,a)):
            adj[u].append(v);rev[v].append(u);edges+=1
    nodes=set(adj)|set(rev)
    if len(nodes)>15000 or edges>45000:
        return {"skipped":"graph_size","nodes":len(nodes),"edges":edges}
    seen=set();order=[]
    for start in nodes:
        if start in seen:continue
        seen.add(start);stack=[(start,0)]
        while stack:
            v,i=stack[-1]
            if i<len(adj[v]):
                t=adj[v][i];stack[-1]=(v,i+1)
                if t not in seen:
                    seen.add(t);stack.append((t,0))
            else:
                order.append(v);stack.pop()
        if time.perf_counter()>deadline:return {"skipped":"budget"}
    component={}; sizes=[]
    for v in reversed(order):
        if v in component:continue
        idx=len(sizes);todo=[v];component[v]=idx;sz=0
        while todo:
            t=todo.pop();sz+=1
            for u in rev[t]:
                if u not in component:
                    component[u]=idx;todo.append(u)
        sizes.append(sz)
    contradictions=sorted({abs(v) for v in nodes
                           if -v in component and component[-v]==component[v]})
    return {"skipped":None,"nodes":len(nodes),"edges":edges,
            "components":len(sizes),
            "equivalent_literal_links":sum(sz-1 for sz in sizes if sz>1),
            "binary_unsat_variables":len(contradictions),
            "binary_unsat_sample":contradictions[:10]}

def analyze(n,clauses,budget=ANALYSIS_CAP):
    started=time.perf_counter()
    deadline=started+budget
    metrics={"status":"OK","source_variables":n,"source_clauses":len(clauses),
             "original_literals":sum(map(len,clauses)),
             "original_unit_clauses":sum(len(c)==1 for c in clauses),
             "complete_xor_equations":0,"complete_xor_premise_clauses":0,
             "gf2_rank":0,"gf2_contradiction":False,
             "derived_units":0,"derived_binary_clauses":0,
             "new_binary_vs_original":0,"new_units_vs_original":0,
             "root_up_fixed_original":None,"root_up_fixed_augmented":None,
             "new_root_up_fixed":None,"shadow_clauses_satisfied":None,
             "graph":None,"proposals":[],"analysis_s":None}
    try:
        original_bin={tuple(sorted(c)) for c in clauses if len(c)==2}
        original_units={c[0] for c in clauses if len(c)==1}
        eqs,covered,eq_cap=xor_blocks(clauses,deadline)
        metrics["complete_xor_equations"]=len(eqs)
        metrics["complete_xor_premise_clauses"]=covered
        metrics["xor_equation_cap_hit"]=eq_cap
        basis={};proposed={}
        rank=0;unsat=None
        for i,(vs,rhs,_) in enumerate(eqs):
            if i%32==0 and time.perf_counter()>deadline:
                raise TimeoutError("GF2 elimination budget")
            row=set(vs);bit=rhs;cert={i}
            while row:
                pivot=min(row)
                if pivot not in basis:break
                other,parity,proof=basis[pivot]
                row.symmetric_difference_update(other)
                bit^=parity
                cert.symmetric_difference_update(proof)
            if not row:
                if bit and unsat is None:
                    replay(eqs,cert,set(),1,clauses)
                    unsat=sorted(cert)
                continue
            pivot=min(row)
            basis[pivot]=(frozenset(row),bit,frozenset(cert))
            rank+=1
            # Only implications with ≤2 variables are soundly exported.
            # This includes both source equations and GF2 combinations.
            if len(row)<=2 and len(proposed)<MAX_CANDIDATES:
                key=(tuple(sorted(row)),bit)
                if key not in proposed:
                    need(replay(eqs,cert,row,bit,clauses),"GF2 proof invalid")
                    proposed[key]=sorted(cert)
        metrics["gf2_rank"]=rank
        metrics["gf2_contradiction"]=unsat is not None
        if unsat is not None:metrics["gf2_unsat_certificate"]=unsat[:64]
        # One more sweep to discover short combinations hidden behind pivots.
        for i,(v,bit,pr) in list(basis.items()):
            if time.perf_counter()>deadline:break
            row=set(v);rhs=bit;cert=set(pr)
            for pivot in sorted(basis,reverse=True):
                if pivot==i or pivot not in row:continue
                other,p,ids=basis[pivot]
                if len(other)<len(row)+3:
                    row.symmetric_difference_update(other);rhs^=p
                    cert.symmetric_difference_update(ids)
            if row and len(row)<=2 and len(proposed)<MAX_CANDIDATES:
                key=(tuple(sorted(row)),rhs)
                if key not in proposed:
                    replay(eqs,cert,row,rhs,clauses)
                    proposed[key]=sorted(cert)
        extra=[];unary=set();binary=set();certs=[]
        for (vs,rhs),proof in proposed.items():
            if len(vs)==1:
                lit=vs[0] if rhs else -vs[0]
                unary.add(lit)
                if lit not in original_units:extra.append((lit,))
            elif len(vs)==2:
                for c in to_binary(vs,rhs):
                    cc=tuple(sorted(c))
                    binary.add(cc)
                    if cc not in original_bin:extra.append(cc)
            if len(certs)<20:certs.append({"vars":vs,"rhs":rhs,"xor_source_indices":proof})
        metrics["derived_units"]=len(unary)
        metrics["derived_binary_clauses"]=len(binary)
        metrics["new_units_vs_original"]=len(unary-original_units)
        metrics["new_binary_vs_original"]=len(binary-original_bin)
        metrics["proposals"]=certs
        if time.perf_counter()<deadline:
            metrics["graph"]=graph_metrics(clauses,deadline)
        if time.perf_counter()<deadline:
            base=up(clauses,(),deadline)
            augmented=up(clauses,extra,deadline) if base is not None and not base["conflict"] else None
            if base is not None:
                metrics["root_up_fixed_original"]=len(base["fixed"])
                metrics["root_up_original_conflict"]=base["conflict"]
            if augmented is not None:
                metrics["root_up_fixed_augmented"]=len(augmented["fixed"])
                metrics["root_up_augmented_conflict"]=augmented["conflict"]
                metrics["new_root_up_fixed"]=sum(
                    k not in base["fixed"] for k in augmented["fixed"])
                metrics["shadow_clauses_satisfied"]=sum(any(
                    augmented["fixed"].get(abs(lit))==(lit>0)
                    for lit in c if abs(lit) in augmented["fixed"]) for c in clauses)
    except TimeoutError as ex:
        metrics["status"]="BUDGET_CUTOFF"
        metrics["budget_reason"]=str(ex)
        # Partial candidates are still certified, but no complete scan claim.
    metrics["analysis_s"]=round(time.perf_counter()-started,6)
    return metrics

def fixture_xor(variables,rhs):
    c=[]
    for assignment in itertools.product((0,1),repeat=len(variables)):
        if (sum(assignment)&1)==rhs:continue
        c.append(tuple(-v if bit else v for v,bit in zip(variables,assignment)))
    return c

def selftest():
    # Complete parity blocks and GF2 elimination derive z=1 from
    # x xor y = 0; x xor y xor z = 1 with no source unit.
    cnf=fixture_xor((1,2),0)+fixture_xor((1,2,3),1)
    report=analyze(3,cnf,3)
    need(report["new_units_vs_original"]>=1,"GF2 unit discovery fixture")
    need(any(p["vars"]==(3,) and p["rhs"]==1 for p in report["proposals"]),
         "GF2 derived unit missing")
    for seed in range(20):
        rng=random.Random(seed)
        clauses=fixture_xor((1,2,3),seed%2)+[
            tuple(rng.choice((-1,1))*rng.randint(1,4)
                  for _ in range(rng.randint(1,3))) for _ in range(5)]
        report=analyze(4,clauses,2)
        need(report["status"]=="OK","small exhaustive budget")
        for proposal in report["proposals"]:
            vs=proposal["vars"];rhs=proposal["rhs"]
            for values in itertools.product((False,True),repeat=4):
                env={i+1:values[i] for i in range(4)}
                sat=all(any(env[abs(l)]==(l>0) for l in c) for c in clauses)
                if sat:
                    need((sum(env[v] for v in vs)&1)==rhs,
                         "unsound GF2 implication")
    print("CRR1A_SELFTEST_PASS",flush=True)

def manifest_cases():
    m=json.loads(Path("history/w4sources/manifest.json").read_text())
    need(len(m["cases"])==24,"24 original sources required")
    cases=sorted(m["cases"],key=lambda c:c["sha256"])
    need(len({c["sha256"] for c in cases})==24,"duplicate source")
    return cases

def prepare():
    selftest()
    cases=manifest_cases()
    need(KISSAT.is_file() and CHECKER.is_file(),"pinned solver/checker missing")
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],
             "original CNF SHA drift")
    ROOT.mkdir(exist_ok=True)
    manifest={"protocol":PROTO,"modes":list(MODES),"cap_s":CAP,"reps":REPS,
         "shards":SHARDS,"sources":24,"source_manifest_sha256":sha("history/w4sources/manifest.json"),
         "case_sha256":[c["sha256"] for c in cases],
         "cohort":"W4 SAT2026 original CNFs reused for development",
         "blind_holdout":False,"promotion_allowed":False,
         "source_formula_unmodified_both_arms":True,
         "XOR_certification":"complete original CNF parity masks plus replayed GF2 combinations",
         "proof_policy":"SAT model checked on original; native UNSAT checked via drat-trim",
         "analysis_budget_s":ANALYSIS_CAP,
         "primary":"novel proven units/binary clauses and extra root UP with wall budget"}
    save(ROOT/"manifest.json",manifest)
    pinned=["research/drnas_crr1a_shadow.py",".github/workflows/drnas-crr1a-shadow.yml",
            "built/bin/kissat_4_0_4","checker/drat-trim",
            "history/w4sources/manifest.json","crr1a/manifest.json"]
    save(ROOT/"pins.json",{p:sha(p) for p in pinned})
    verify()
    print("CRR1A_PREPARE_PASS",sha(ROOT/"manifest.json"),flush=True)

def verify():
    cases=manifest_cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["case_sha256"]==[c["sha256"] for c in cases] and
         m["modes"]==list(MODES) and m["source_manifest_sha256"]==sha("history/w4sources/manifest.json"),
         "manifest mismatch")
    for p,d in json.loads((ROOT/"pins.json").read_text()).items():
        need(sha(p)==d,"pin mismatch "+p)
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"source SHA mismatch")
    return cases

def worker(source,mode,directory):
    started=time.perf_counter()
    telemetry=None
    if mode=="crr_shadow":
        # All mathematical work is observational; the source file is unchanged.
        n,clauses=parse(source)
        telemetry=analyze(n,clauses)
        print(json.dumps({"event":"analysis","telemetry":telemetry},sort_keys=True),flush=True)
    prep=time.perf_counter()-started
    proof=Path(directory)/"native.drat"
    cmd=[str(KISSAT.resolve()),str(Path(source).resolve()),str(proof.resolve())]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    stdout=result.stdout
    verdicts=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE)\\s*$",stdout)
    need(len(verdicts)==1,"missing or ambiguous solver verdict")
    status="SAT" if verdicts[0]=="SATISFIABLE" else "UNSAT"
    need(result.returncode==(10 if status=="SAT" else 20),"solver exit/verdict")
    if status=="SAT":
        model={}
        for line in stdout.splitlines():
            if line.startswith("v "):
                for tok in line[2:].split():
                    lit=int(tok)
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                             "contradictory SAT model")
                        model[abs(lit)]=lit>0
        _,clauses=parse(source)
        need(all(any(model.get(abs(l))==(l>0) for l in c)
                 for c in clauses),"SAT original witness invalid")
        save(Path(directory)/"model.json",model)
    (Path(directory)/"native.log").write_text(stdout[-6000:])
    print(json.dumps({"event":"result","status":status,
        "prep_s":round(prep,6),
        "source_sha256":sha(source),
        "unchanged_source":True},sort_keys=True),flush=True)

def trial(c,mode,rep,shard):
    source=SOURCE/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"trial SHA drift")
    d=ROOT/"raw"/str(shard)/(c["id"]+"-"+str(rep)+"-"+mode)
    d.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker","--source",str(source),
                        "--mode",mode,"--directory",str(d)],
           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
           text=True,start_new_session=True)
    timedout=False
    try:
        output,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-t)))
    except subprocess.TimeoutExpired:
        timedout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        output,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-t)
    events=[]
    for ln in output.splitlines():
        try:
            e=json.loads(ln)
            if isinstance(e,dict):events.append(e)
        except ValueError:pass
    analysis=[e["telemetry"] for e in events if e.get("event")=="analysis"]
    terminal=[e for e in events if e.get("event")=="result"]
    status="TIMEOUT";evidence="WALL_CAP_TIMEOUT";native=None
    prep=None
    if not timedout and elapsed<CAP:
        need(p.returncode==0 and len(terminal)==1,
             "worker crash "+output[-3000:])
        event=terminal[0]
        need(event["source_sha256"]==c["sha256"] and event["unchanged_source"],
             "source changed")
        native=event["status"];prep=event["prep_s"]
        if native=="SAT":
            model={int(k):v for k,v in json.loads((d/"model.json").read_text()).items()}
            _,clauses=parse(source)
            need(all(any(model.get(abs(l))==(l>0) for l in c) for c in clauses),
                 "original SAT witness parent recheck")
            status="SAT";evidence="SAT_ORIGINAL_MODEL_VERIFIED"
        else:
            proof=d/"native.drat"
            if proof.is_file() and proof.stat().st_size>0:
                try:
                    q=subprocess.run([str(CHECKER.resolve()),str(source.resolve()),str(proof)],
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
                    (d/"proof_validation.log").write_text(q.stdout[-3500:])
                    if q.returncode==0 and "s VERIFIED" in q.stdout:
                        status="UNSAT";evidence="UNSAT_DRAT_VERIFIED"
                    else:evidence="UNSAT_UNCERTIFIED_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    (d/"proof_validation.log").write_text("CHECKER_TIMEOUT")
                    evidence="UNSAT_PROOF_TIMEOUT_NOT_SCORED"
    # Destroy proof immediately; never upload large artifacts.
    proof=d/"native.drat"
    if proof.exists():proof.unlink()
    row={"protocol":PROTO,"sha256":c["sha256"],"id":c["id"],"mode":mode,
         "rep":rep,"shard":shard,"status":status,"native_status":native,
         "proof":evidence,"elapsed_s":round(elapsed,6),
         "par2_s":round(elapsed if status!="TIMEOUT" else 2*CAP,6),
         "prep_s":prep,"analysis":analysis[0] if analysis else None,
         "analysis_complete":len(analysis)==1}
    print("CRR1A_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(i):
    cases=verify()
    need(0<=i<SHARDS,"shard index")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for c in cases[i::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                rows.append(trial(c,mode,rep,i))
                save(ROOT/("shard-%d.json"%i),rows)
    need(len(rows)==(len(cases[i::SHARDS])*len(MODES)*REPS),"partial shard")
    print("CRR1A_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cases=verify()
    rows=[];seen=set()
    for i in range(SHARDS):
        rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(rr)==18,"expected 18 rows per shard")
        for r in rr:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen and r["protocol"]==PROTO and
                 r["sha256"] in {c["sha256"] for c in cases[i::SHARDS]} and
                 r["shard"]==i and r["rep"] in range(REPS) and
                 r["mode"] in MODES,"trial provenance")
            seen.add(key)
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad verdict")
            expected=2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]
            need(abs(expected-r["par2_s"])<.00002,"PAR2 mismatch")
            need(r["status"]!="SAT" or r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED",
                 "unverified SAT")
            need(r["status"]!="UNSAT" or r["proof"]=="UNSAT_DRAT_VERIFIED",
                 "unverified UNSAT")
            rows.append(r)
    want={(c["sha256"],rep,m) for c in cases for rep in range(REPS) for m in MODES}
    need(seen==want and len(rows)==144,"incomplete 144 paired")
    totals={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        totals[mode]={"attempts":len(rr),"solved":sum(r["status"]!="TIMEOUT" for r in rr),
                      "par2_s":round(sum(r["par2_s"] for r in rr),6),
                      "sat":sum(r["status"]=="SAT" for r in rr),
                      "unsat_verified":sum(r["status"]=="UNSAT" for r in rr)}
    tele=[r["analysis"] for r in rows if r["mode"]=="crr_shadow" and r["analysis"] is not None]
    # Every source has three equivalent shadow observations; summarize first
    # per SHA rather than pretending repeated telemetry is independent.
    unique={}
    for r in rows:
        if r["mode"]=="crr_shadow" and r["analysis"] is not None:
            unique.setdefault(r["sha256"],r["analysis"])
    counters=("complete_xor_equations","derived_units","derived_binary_clauses",
              "new_units_vs_original","new_binary_vs_original")
    reduction_metrics={p:sum(x.get(p,0) for x in unique.values()) for p in counters}
    reduction_metrics["extra_UP_fixed_total"]=sum(
        x["new_root_up_fixed"] or 0 for x in unique.values())
    reduction_metrics["sources_with_xor"]=sum(x["complete_xor_equations"]>0 for x in unique.values())
    reduction_metrics["sources_with_novel_units"]=sum(x["new_units_vs_original"]>0 for x in unique.values())
    reduction_metrics["sources_with_new_root_UP"]=sum(
        (x["new_root_up_fixed"] or 0)>0 for x in unique.values())
    reduction_metrics["sources_with_unfinished_shadow"]=sum(x["status"]!="OK" for x in unique.values())
    reduction_metrics["analyzed_unique_sources"]=len(unique)
    result={"status":"CRR1A_AUDIT_PASS","protocol":PROTO,
            "source_reuse_not_blind":True,"promotion_allowed":False,
            "SAT_original_model_checked":True,"native_UNSAT_independent_DRAT":True,
            "certified_proposals_only":True,"formulas":24,"attempts":144,
            "totals":totals,"reduction_metrics":reduction_metrics}
    save(ROOT/"report.json",result)
    save(ROOT/"all-trials.json",rows)
    print("CRR1A_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","shard","worker","audit","selftest"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--source")
    p.add_argument("--mode",choices=MODES)
    p.add_argument("--directory")
    args=p.parse_args()
    if args.action=="worker":worker(args.source,args.mode,args.directory)
    elif args.action=="shard":shard(args.shard)
    elif args.action=="selftest":selftest()
    else:globals()[args.action]()

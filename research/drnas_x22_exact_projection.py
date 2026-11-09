#!/usr/bin/env python3
"""X22: exact bounded Davis-Putnam variable projection with model lifting.

Development-only replay of six previously seen X21 original source SHAs.
Not global blind; no independent UNSAT LRAT. Unlike solver portfolios this
changes the mathematical representation through exact existential elimination.
Test every original witness after reconstructing eliminated variables.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, os, pathlib, random
import resource, signal, subprocess, tempfile, time

import drnas_x21_championship as x21
import drnas_x16_singlecore_dual as x16
import drnas_x18_selective as x18

ROOT=pathlib.Path("mre_x22")
PROTO="DRNAS-X22-EXACT-DP-PROJECTION-6KNOWN-X21SHA-5ARM-2REP-18S-v1"
ARMS=("kissat1","native1","rewrite","bve6","bve18")
CAP, REPS, SHARDS = 18.0, 2, 6
CHOSEN={
 "43610b90f01b816c1d8a1be5163090259192e3cc15e0ce9adc60df61a07765cc", # uncorroborated native UNSAT
 "dcd25a9b86c28bbc788f2f2aff7393cd4f0c91b7104dfeb30ce604bef9c3d906", # uncorroborated native UNSAT
 "eac5a18e5db7caef0d2af4e73d616ee8ee1fa7f4dfcaa8658ec53a13096dccb2", # native SAT better
 "58e5c4019f7bed6395044458752b7e87359cf7090c22bcd8b795de69a07bac44", # native SAT better
 "526c22fae9990ce68f5cf2a3f4fb3f7e49283f701cb030a22edc3dac09d9d14a", # kissat SAT better
 "dba3953978c0de58c0eff1acde1b7a5775d5ff9e1a7259062b3d24e05d628203", # verified reference UNSAT, native timed out
}

def need(ok,why):
    if not ok:raise RuntimeError("X22_FAIL_CLOSED "+str(why))

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def save(path,obj):
    pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def parse(src):
    nvars=None;expected=None;clauses=[];cur=[];count=0
    with open(src,"r",errors="strict") as f:
        for line in f:
            t=line.strip()
            if not t or t.startswith("c") or t.startswith("%"):continue
            if t.startswith("p "):
                a=t.split()
                need(len(a)>=4 and a[1]=="cnf" and nvars is None,"DIMACS header")
                nvars=int(a[2]);expected=int(a[3])
                need(0<nvars<=100000 and 0<=expected<=500000,"DIMACS size")
                continue
            need(nvars is not None,"DIMACS missing header")
            for z in t.split():
                lit=int(z)
                if lit==0:
                    count+=1
                    s=set(cur)
                    if not any(-v in s for v in s):
                        clauses.append(tuple(dict.fromkeys(cur)))
                    cur=[]
                else:
                    need(0<abs(lit)<=nvars,"invalid literal")
                    cur.append(lit)
    need(nvars is not None and not cur and count==expected,
         "DIMACS clause count mismatch")
    return nvars,clauses,count

def write(path,n,clauses):
    with open(path,"w") as f:
        f.write(f"p cnf {n} {len(clauses)}\n")
        for clause in clauses:
            f.write(" ".join(map(str,clause))+" 0\n")

def project(clauses,nvars,max_degree=6,max_product=12,max_elims=500,deadline=None):
    """Exact existential elimination. Add all non-tautological resolvents.

    Only eliminate if both polarities have sufficiently bounded degree and
    resolvent count does not increase clauses, or if variable is pure.
    Every removed positive/negative parent is stored for SAT model lifting.
    """
    active={i:tuple(c) for i,c in enumerate(clauses)}
    pos=collections.defaultdict(set);neg=collections.defaultdict(set)
    for k,c in active.items():
        for lit in c:(pos if lit>0 else neg)[abs(lit)].add(k)
    candidates=sorted((v for v in set(pos)|set(neg)),
        key=lambda v:(len(pos[v])+len(neg[v]),v))
    next_id=len(active);trace=[];res_added=0;deleted=0
    for v in candidates:
        if len(trace)>=max_elims or (deadline and time.perf_counter()>deadline):break
        p=pos[v].copy();q=neg[v].copy()
        if not p and not q:continue
        if p&q:raise AssertionError("taut source clause not removed")
        if len(p)+len(q)>max_degree or len(p)*len(q)>max_product:continue
        resolvents=set();valid=True
        for i in p:
            for j in q:
                merged=set(active[i])|set(active[j])
                merged.discard(v);merged.discard(-v)
                if any(-lit in merged for lit in merged):continue
                if len(merged)>40:valid=False;break
                resolvents.add(tuple(sorted(merged,key=lambda x:(abs(x),x<0))))
            if not valid:break
        if not valid or len(resolvents)>len(p)+len(q)-1:continue
        positives=[active[i] for i in sorted(p)]
        negatives=[active[i] for i in sorted(q)]
        for i in p|q:
            clause=active.pop(i)
            for lit in clause:
                (pos if lit>0 else neg)[abs(lit)].discard(i)
        for clause in sorted(resolvents):
            i=next_id;next_id+=1;active[i]=clause
            for lit in clause:
                (pos if lit>0 else neg)[abs(lit)].add(i)
        deleted+=len(p)+len(q);res_added+=len(resolvents)
        trace.append((v,positives,negatives))
    return list(active.values()),trace,dict(eliminated=len(trace),
        removed=deleted,added=res_added,clauses_before=len(clauses),
        clauses_after=len(active),max_degree=max_degree,
        max_product=max_product)

def verify_model(clauses,assignment):
    return all(any(assignment.get(abs(lit),False)==(lit>0) for lit in c)
               for c in clauses)

def lift(model,trace):
    # Modified Kissat may print irrelevant values of eliminated vars.
    for v,_,_ in trace:model.pop(v,None)
    for v,positives,negatives in reversed(trace):
        p=any(not any(model.get(abs(z),False)==(z>0)
                      for z in clause if abs(z)!=v) for clause in positives)
        q=any(not any(model.get(abs(z),False)==(z>0)
                      for z in clause if abs(z)!=v) for clause in negatives)
        need(not (p and q),"inconsistent reconstruction: resolvent violated")
        model[v]=bool(p)
    return model

def parse_kissat_model(stdout):
    model={}
    for line in stdout.splitlines():
        line=line.strip()
        if not line.startswith("v "):continue
        for tok in line[2:].split():
            lit=int(tok)
            if lit==0:continue
            need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                 "contradictory witness")
            model[abs(lit)]=lit>0
    return model

def cases():
    x21.setup()
    m=x21.verify()
    selected=[c for c in m["cases"] if c["sha256"] in CHOSEN]
    need(len(selected)==6 and {c["sha256"] for c in selected}==CHOSEN,
         "X21 frozen source roster changed")
    return selected

def trial(c,rep,arm):
    x21.setup();need(arm in ARMS,"arm invalid")
    src=x21.ROOT/c["filename"];need(sha(src)==c["sha256"],"source mutated")
    seed=x18.seed(c,rep);cpu=x16.topology()["first"]
    pb=x16.rusage_snapshot(resource.RUSAGE_SELF)
    cb=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    start=time.perf_counter();status="TIMEOUT";backend=None
    stats=dict(mode=arm,skipped=False,eliminated=0,removed=0,added=0)
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        transformed=src;orig=None;trace=[]
        if arm in ("rewrite","bve6","bve18"):
            if src.stat().st_size>12*1024*1024:
                stats["skipped"]="input_gt_12MiB"
            else:
                n,orig,count=parse(src)
                if time.perf_counter()-start>3.0:
                    stats["skipped"]="input_parse_over_3s"
                else:
                    output=orig
                    if arm!="rewrite":
                        degree,product=(6,12) if arm=="bve6" else (18,60)
                        output,trace,stats2=project(orig,n,degree,product,500,
                            deadline=start+4.0)
                        stats.update(stats2)
                    transformed=pathlib.Path(td)/"projected.cnf"
                    write(transformed,n,output)
                    need(len(trace)<=500,"projection safety cap exceeded")
        stats["preprocess_s"]=round(time.perf_counter()-start,6)
        remaining=CAP-(time.perf_counter()-start)
        if remaining>.05:
            out=open(pathlib.Path(td)/"stdout","w+t")
            err=open(pathlib.Path(td)/"stderr","w+t")
            try:
                which="native" if arm=="native1" else "kissat"
                cmd=x16.command(which,transformed,seed)
                p=subprocess.Popen(cmd,stdout=out,stderr=err,
                    start_new_session=True,
                    preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
                try:
                    p.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait()
                out.flush();out.seek(0);err.flush();err.seek(0)
                output=out.read();errors=err.read()
                if p.returncode in (0,10,20) and time.perf_counter()-start<CAP:
                    if arm in ("native1","kissat1"):
                        status=x16.x14.outcome_of(which,p.returncode,output,errors,src)
                    else:
                        need(p.returncode in (10,20),"projected Kissat bad return")
                        status="SAT" if p.returncode==10 else "UNSAT"
                        need("s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in output,
                             "projected output mismatch")
                        if status=="SAT":
                            model=parse_kissat_model(output)
                            # Need all variables from exact transformed CNF.
                            need(orig is not None or not trace,"missing original for lift")
                            if trace:model=lift(model,trace)
                            if orig is None:
                                _,orig,_=parse(src)
                            need(verify_model(orig,model),"lifted model violates original CNF")
                    backend=which
                else:status="TIMEOUT"
            finally:
                out.close();err.close()
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status="TIMEOUT";backend=None
    cpu_s=x16.counters_diff(cb,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))["cpu_s"]
    parent=x16.counters_diff(pb,x16.rusage_snapshot(resource.RUSAGE_SELF))["cpu_s"]
    return dict(protocol=PROTO,original_sha256=c["sha256"],gbd=c["gbd"],
        year=c["year"],rep=rep,arm=arm,seed=seed,status=status,
        selected_backend=backend,elapsed_s=round(elapsed,6),
        PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        child_cpu_s=cpu_s,parent_cpu_s=parent,
        max_logical_cpus=1,original_source_SHA_verified=True,
        SAT_original_witness_verified=status=="SAT",
        UNSAT_independent_LRAT=False,**stats)

def selftest():
    random.seed(20261109)
    for run in range(80):
        nv=random.randint(2,6)
        cnf=[tuple(random.sample(
            [z for v in range(1,nv+1) for z in (v,-v)],
            random.randint(1,min(4,nv*2)))) for _ in range(random.randint(0,16))]
        cnf=[c for c in cnf if not set(c)&{-v for v in c}]
        reduced,trail,_=project(cnf,nv,18,60,500)
        old_sat=any(verify_model(cnf,{i:bool(z>>i&1) for i in range(1,nv+1)})
                     for z in range(1<<nv))
        new_sat=False
        for z in range(1<<nv):
            m={i:bool(z>>i&1) for i in range(1,nv+1)}
            if verify_model(reduced,m):
                new_sat=True
                m=lift(m,trail)
                need(verify_model(cnf,m),"random original witness fail")
        need(old_sat==new_sat,"random exact projection SAT equivalence fail")
    print("X22_EXACT_ELIMINATION_SELFTEST_PASS",flush=True)

def shard(idx):
    chosen=cases();need(0<=idx<SHARDS,"shard index")
    c=chosen[idx];rows=[];ROOT.mkdir(exist_ok=True)
    for rep in range(REPS):
        order=list(ARMS);random.Random(x18.seed(c,rep)).shuffle(order)
        for arm in order:
            r=trial(c,rep,arm);rows.append(r)
            save(ROOT/("shard-%d.json"%idx),rows)
            print("X22_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==10,"shard rows incomplete")
    print("X22_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    selected=cases();rows=[]
    for i in range(SHARDS):rows+=json.loads((ROOT/("shard-%d.json"%i)).read_text())
    expected={(c["sha256"],rep,arm) for c in selected for rep in range(REPS) for arm in ARMS}
    need(len(rows)==60 and {(r["original_sha256"],r["rep"],r["arm"])
                             for r in rows}==expected,"incomplete source/seed matrix")
    for c in selected:
        g=[r for r in rows if r["original_sha256"]==c["sha256"]]
        need(len({r["status"] for r in g if r["status"]!="TIMEOUT"})<=1,
             "SAT vs UNSAT contradiction")
        original_backends={r["selected_backend"] for r in g
            if r["arm"] in ("kissat1","native1") and r["status"]=="UNSAT"}
        agreed=len(original_backends)>=2
        for r in g:
            need(r["protocol"]==PROTO and r["max_logical_cpus"]==1,
                 "protocol/CPU drift")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "SAT original witness missing")
            r["accepted"]=r["status"]=="SAT" or (r["status"]=="UNSAT" and agreed)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    totals={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        totals[arm]=dict(n=len(a),solved=sum(r["accepted"] for r in a),
            SAT_verified=sum(r["accepted"] and r["status"]=="SAT" for r in a),
            UNSAT_agreement_no_LRAT=sum(r["accepted"] and r["status"]=="UNSAT" for r in a),
            unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and not r["accepted"] for r in a),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in a),6),
            child_cpu_s=round(sum(r["child_cpu_s"] for r in a),6),
            eliminated=sum(r.get("eliminated",0) for r in a),
            skipped=sum(bool(r.get("skipped")) for r in a))
    report=dict(protocol=PROTO,source_count=len(selected),trials=len(rows),overall=totals,
        per_source=[dict(sha256=c["sha256"],gbd=c["gbd"],
            rows=[r for r in rows if r["original_sha256"]==c["sha256"]])
             for c in selected],no_global_blind_claim=True,
        development_replay_known_X21=True,
        independent_UNSAT_LRAT=False,no_auto_promotion=True)
    save(ROOT/"report.json",report)
    print("X22_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
                              sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args();ROOT.mkdir(exist_ok=True)
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__":main()

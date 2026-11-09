#!/usr/bin/env python3
"""X22: two-vCPU E2E causal test of an asynchronous C++ CNF helper.
X21's formerly unseen sources are REUSED; this is NOT a new blind holdout.
"""
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import resource
import shutil
import signal
import subprocess
import tempfile
import time

ROOT=pathlib.Path("mre_x22")
BIN=ROOT/"bin/reducer"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("/usr/bin/cadical")
PROTO="DRNAS-X22-CPP-ASYNC-SIGNED-SCC-24SHA-6ARM-2REP-15S-20261109-v1"
ARMS=("kissat1","cadical1","race_original","race_shadow","race_clean","race_quotient")
CAP=15.0
REPS=2
SHARDS=8
EXPECTED=24*REPS*len(ARMS)

def need(ok,msg):
    if not ok:raise RuntimeError("X22_FAIL_CLOSED "+str(msg))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):h.update(block)
    return h.hexdigest()
def save(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
def read_cnf(path):
    n=None;declared=None;clauses=[];current=[]
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            fields=line.split()
            if not fields or fields[0] in ("c","%"):continue
            if fields[0]=="p":
                need(n is None and len(fields)==4 and fields[1]=="cnf","header")
                n=int(fields[2]);declared=int(fields[3]);continue
            need(n is not None,"missing header")
            for t in fields:
                lit=int(t)
                if lit==0:clauses.append(tuple(current));current=[]
                else:
                    need(0<abs(lit)<=n,"literal range")
                    current.append(lit)
    need(n is not None and not current and len(clauses)==declared,"clause count")
    return n,clauses
def holds(clauses,model):
    return all(any(bool(model.get(abs(lit),False))==(lit>0) for lit in c)
               for c in clauses)
def parse_map(path,n):
    lines=pathlib.Path(path).read_text().splitlines()
    need(bool(lines) and lines[0].split()[:2]==["p","map"],"map header")
    header=lines[0].split()
    need(len(header)==4 and int(header[2])==n and int(header[3])==len(lines)-1,
         "mapping size")
    out={}
    for line in lines[1:]:
        a,b=map(int,line.split())
        need(0<a<=n and 0<abs(b)<a and a not in out,"noncanonical alias")
        out[a]=b
    need(len(out)<=64,"alias count")
    return out
def proof_replay(clauses,aliases):
    graph=collections.defaultdict(set)
    for clause in clauses:
        if len(clause)!=2:continue
        a,b=clause
        if a==b or a==-b:continue
        graph[-a].add(b);graph[-b].add(a)
    def path(a,b):
        if a==b:return True
        queue=collections.deque((a,));seen={a}
        while queue:
            for nxt in graph[queue.popleft()]:
                if nxt==b:return True
                if nxt not in seen:seen.add(nxt);queue.append(nxt)
        return False
    for var,target in aliases.items():
        need(path(var,target) and path(target,var),
             "SCC alias not supported by ORIGINAL source implications")
def lift(model,aliases):
    result=dict(model)
    for var,target in aliases.items():
        value=bool(result.get(abs(target),False))
        result[var]=value if target>0 else not value
    return result
def solver_result(name,rc,stdout,source_clauses,aliases):
    need(rc in (10,20),name+" unexpected exit "+str(rc))
    status="SAT" if rc==10 else "UNSAT"
    expected="s SATISFIABLE" if rc==10 else "s UNSATISFIABLE"
    need(expected in (line.strip() for line in stdout.splitlines()),
         name+" verdict and exit code mismatch")
    if rc==20:return status,False
    assignment={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for v in map(int,line.split()[1:]):
            if v==0:continue
            need(abs(v) not in assignment or assignment[abs(v)]==(v>0),
                 "conflicting witness bits")
            assignment[abs(v)]=v>0
    need(holds(source_clauses,lift(assignment,aliases)),
         name+" SAT model falsified ORIGINAL CNF")
    return status,True
def cpus():
    allowed=sorted(os.sched_getaffinity(0))
    need(len(allowed)>=2,"two logical CPUs required")
    return allowed[:2]
def child_cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime+r.ru_stime
def launch(name,command,cpu,temporary):
    stdout=open(pathlib.Path(temporary)/(name+".out"),"w+t")
    stderr=open(pathlib.Path(temporary)/(name+".err"),"w+t")
    try:
        p=subprocess.Popen([str(x) for x in command],stdout=stdout,stderr=stderr,
            close_fds=True,start_new_session=True,
            preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
    except Exception:
        stdout.close();stderr.close();raise
    return dict(name=name,p=p,out=stdout,err=stderr,read=False,cpu=cpu)
def read_output(e):
    e["out"].flush();e["err"].flush()
    e["out"].seek(0);e["err"].seek(0)
    return e["out"].read(),e["err"].read()
def cleanup(entries):
    for e in entries:
        if e["p"].poll() is None:
            try:os.killpg(e["p"].pid,signal.SIGKILL)
            except ProcessLookupError:pass
        try:e["p"].wait(timeout=2)
        except subprocess.TimeoutExpired:e["p"].kill();e["p"].wait()
        e["out"].close();e["err"].close()
def seed(case,rep):
    return int(hashlib.sha256((case["sha256"]+"|"+str(rep)).encode()).hexdigest()[:7],16)
def backend_hashes():
    return dict(kissat=digest(KISSAT),cadical=digest(CADICAL),reducer=digest(BIN))
def verify_frozen():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    need(manifest["protocol"]==PROTO and manifest["arms"]==list(ARMS)
         and len(manifest["cases"])==24
         and manifest["expected_trials"]==EXPECTED,"protocol changed")
    need(manifest["backend_sha256"]==backend_hashes()
         and manifest["code_sha256"]==digest(__file__),"binary/code changed")
    for case in manifest["cases"]:
        need(digest(ROOT/"cases"/case["filename"])==case["sha256"],
             "original source SHA changed")
    return manifest
def freeze():
    previous=json.loads(pathlib.Path("mre_x21/manifest.json").read_text())
    need(len(previous["cases"])==24,"X21 cohort missing")
    (ROOT/"cases").mkdir(parents=True,exist_ok=True)
    cases=[]
    for old in previous["cases"]:
        path=pathlib.Path("mre_x21")/old["filename"]
        need(digest(path)==old["sha256"],"source checksum invalid")
        shutil.copyfile(path,ROOT/"cases"/old["filename"])
        cases.append({k:old[k] for k in ("filename","sha256","gbd","year")})
    need(len({c["sha256"] for c in cases})==24,"duplicate original SHA")
    save(ROOT/"manifest.json",dict(
        protocol=PROTO,cases=cases,source_run_id=42586193407,
        x21_manifest_sha256=digest("mre_x21/manifest.json"),
        replay_of_previously_unseen_sources=True,not_blind=True,
        no_auto_promotion=True,original_source_SHA_unchanged=True,
        UNSAT_independent_LRAT=False,cap_s=CAP,repetitions=REPS,shards=SHARDS,
        arms=ARMS,expected_trials=EXPECTED,backend_sha256=backend_hashes(),
        code_sha256=digest(__file__),max_logical_cpus=2,
        measure="E2E including original parsing, C++ helper, proof replay, "
                "solver launches, source witness validation and cleanup"))
    verify_frozen()
    print("X22_FROZEN",len(cases),EXPECTED,flush=True)
def trial(case,rep,arm):
    need(arm in ARMS,"arm")
    src=ROOT/"cases"/case["filename"]
    need(digest(src)==case["sha256"],"SHA mismatch")
    cpu=cpus();begin=time.perf_counter();cpu_before=child_cpu()
    status="TIMEOUT";winner=None;sat_proof=False;prep_s=0.0
    telemetry={};aliases={};cadical_started=False;rewrite_winner=False
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        directory=pathlib.Path(tmp)
        entries=[];helper=None
        try:
            n,original=read_cnf(src)
            if arm!="cadical1":
                entries.append(launch("kissat",
                    [KISSAT,"--seed="+str(seed(case,rep)),src],cpu[0],tmp))
            if arm in ("cadical1","race_original"):
                entries.append(launch("cadical",[CADICAL,src],cpu[1],tmp))
                cadical_started=True
            elif arm in ("race_shadow","race_clean","race_quotient"):
                helper=launch("helper",[BIN,"clean" if arm=="race_clean" else "quotient",
                    src,directory/"reduced.cnf",directory/"alias.map"],cpu[1],tmp)
                entries.append(helper)
            while time.perf_counter()-begin<CAP:
                for entry in entries:
                    if entry["read"] or entry["p"].poll() is None:continue
                    entry["read"]=True
                    stdout,stderr=read_output(entry)
                    if entry is helper:
                        need(entry["p"].returncode==0,"helper "+stderr[-500:])
                        records=[s for s in stdout.splitlines() if s.startswith("X22_REDUCER ")]
                        need(len(records)==1,"missing helper telemetry")
                        telemetry=json.loads(records[0][len("X22_REDUCER "):])
                        aliases=parse_map(directory/"alias.map",n)
                        if arm=="race_clean":need(not aliases,"clean arm had aliases")
                        proof_replay(original,aliases)
                        prep_s=time.perf_counter()-begin
                        need(digest(src)==case["sha256"],"source mutated during work")
                        if time.perf_counter()-begin<CAP-.05:
                            target=src if arm=="race_shadow" else directory/"reduced.cnf"
                            added=launch("cadical",[CADICAL,target],cpu[1],tmp)
                            added["aliases"]=aliases if arm=="race_quotient" else {}
                            entries.append(added);cadical_started=True
                        break
                    result,checked=solver_result(entry["name"],entry["p"].returncode,
                        stdout,original,entry.get("aliases",{}))
                    status=result;sat_proof=checked;winner=entry["name"]
                    rewrite_winner=entry["name"]=="cadical" and arm=="race_quotient"
                    break
                if winner:break
                if all(e["read"] for e in entries):break
                time.sleep(.003)
        finally:cleanup(entries)
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;sat_proof=False;rewrite_winner=False
    return dict(protocol=PROTO,arm=arm,rep=rep,seed=seed(case,rep),
        original_sha256=case["sha256"],gbd=case["gbd"],
        status=status,winner=winner,
        SAT_original_witness_verified=sat_proof,
        UNSAT_independent_LRAT=False,
        transformed_UNSAT_uncertified=(status=="UNSAT" and rewrite_winner),
        reducer=telemetry,aliases_replayed=len(aliases),
        second_solver_launched=cadical_started,
        E2E_s=round(elapsed,6),child_cpu_s=round(child_cpu()-cpu_before,6),
        helper_ready_s=round(prep_s,6),cap_s=CAP,
        affinity=cpu,
        provisional_PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6))
def shard(index):
    frozen=verify_frozen()
    need(0<=index<SHARDS,"shard")
    rows=[]
    for case in frozen["cases"][index::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS);random.Random(seed(case,rep)).shuffle(order)
            for arm in order:
                row=trial(case,rep,arm);rows.append(row)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X22_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==36,"incomplete shard")
    print("X22_SHARD_PASS",index,len(rows),flush=True)
def audit():
    verify_frozen()
    rows=[]
    for i in range(SHARDS):
        path=ROOT/("shard-%d.json"%i)
        need(path.exists(),"missing shard "+str(i))
        group=json.loads(path.read_text())
        need(len(group)==36,"incomplete group")
        rows.extend(group)
    need(len(rows)==EXPECTED,"missing rows")
    keys=set();bycase=collections.defaultdict(list)
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in keys and r["arm"] in ARMS and r["protocol"]==PROTO,
             "duplicate/mismatched trial")
        keys.add(key);bycase[r["original_sha256"]].append(r)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"uncertified SAT witness")
        need(r["cap_s"]==CAP and r["E2E_s"]>=0,"cap/clock mismatch")
    need(len(keys)==EXPECTED,"coverage")
    certified={}
    for sha,group in bycase.items():
        statuses={r["status"] for r in group if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradiction among SAT reference solvers")
        original_unsat={r["arm"] for r in group if r["arm"] in ("kissat1","cadical1")
                        and r["status"]=="UNSAT"}
        certified[sha]=len(original_unsat)==2
    score={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and certified[r["original_sha256"]])]
        score[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
            verified_SAT=sum(r["status"]=="SAT" for r in accepted),
            UNSAT_original_cross_agreement_no_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
            unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted for r in subset),
            PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP for r in subset),4),
            child_CPU_s=round(sum(r["child_cpu_s"] for r in subset),4),
            aliases_replayed=sum(r["aliases_replayed"] for r in subset))
    base=score["race_original"]["PAR2_s"]
    for v in score.values():
        v["PAR2_change_vs_two_solver_race_pct"]=round(100*(v["PAR2_s"]/base-1),3)
    result=dict(protocol=PROTO,rows=len(rows),scores=score,confirmed_original_UNSAT=certified,
        X21_holdout_reused_not_blind=True,independent_LRAT=False,
        CPU_note="two pinned Linux logical CPUs; wall E2E plus child CPU")
    save(ROOT/"report.json",result)
    print("X22_FINAL",json.dumps(score,sort_keys=True),flush=True)
def selftest():
    need(BIN.is_file(),"C++ binary missing")
    rng=random.Random(2209)
    examples=[(2,[(1,-2),(-1,2)]),(2,[(1,2),(-1,-2)]),
              (2,[(1,2),(-1,2),(1,-2),(-1,-2)]),
              (3,[(1,-2),(-1,2),(2,-3),(-2,3)]),(1,[()])]
    for n in range(1,6):
        for _ in range(35):
            clauses=[tuple(rng.choice((-1,1))*rng.randrange(1,n+1)
                     for _ in range(rng.randrange(0,4)))
                     for j in range(rng.randrange(0,14))]
            examples.append((n,clauses))
    tested=0
    with tempfile.TemporaryDirectory() as tmp:
        d=pathlib.Path(tmp)
        for n,original in examples:
            src=d/"src.cnf"
            src.write_text("p cnf %d %d\n"%(n,len(original))+
                "".join(" ".join(map(str,c))+" 0\n" for c in original))
            for arm in ("clean","quotient"):
                run=subprocess.run([str(BIN),arm,str(src),
                    str(d/"reduced.cnf"),str(d/"aliases.map")],
                    capture_output=True,text=True)
                need(run.returncode==0,"C++ selftest: "+run.stderr)
                n2,reduced=read_cnf(d/"reduced.cnf")
                need(n2==n,"DIMACS domain changed")
                mp=parse_map(d/"aliases.map",n);proof_replay(original,mp)
                source_sat=False;reduced_sat=False
                for values in itertools.product((False,True),repeat=n):
                    model={i+1:values[i] for i in range(n)}
                    source_sat|=holds(original,model)
                    if holds(reduced,model):
                        reduced_sat=True
                        need(holds(original,lift(model,mp)),"unsound lifted witness")
                need(source_sat==reduced_sat,"satisfiability changed")
                tested+=1
    print("X22_SELFTEST_PASS",tested,"small CNF SAT/UNSAT parity checks",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","shard","audit","selftest"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:globals()[a.action]()

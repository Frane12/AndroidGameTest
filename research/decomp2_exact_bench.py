#!/usr/bin/env python3
"""DRNAS DECOMP2: exact SAT decomposition (not a shortcut to claiming UNSAT).
Source-SHA-frozen DECOMP1 followup. Source graph preselection, one logical CPU,
full end-to-end PAR2 and original witness verification.

F SAT iff for some x in {0,1}, all components of F|x solve SAT.
Original disconnected components can be solved separately without branching.
UNSAT is backend-only, no independently verified LRAT.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import resource
import subprocess
import tempfile
import time

import dmd1_bench as d1

PROTO="DRNAS-DECOMP2-EXACT-SAT-SEPARATOR-FROZEN8-ONECPU-v1"
ROOT=pathlib.Path("mre_decomp2")
SOURCE=pathlib.Path("mre_x20")
NATIVE=pathlib.Path("mre_decomp1/bin/decomp1_incidence")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
PIN="c96ebe32a7e333a02acad462679a0bbfbeeec54a7f9210421c4c0c8d53bbf95f"
ARMS=("kissat_raw","incidence_shadow","existing_components","cut_small_first")
CAP=12.0
REPS=2
SHARDS=4
MAX_PARTS=16

def need(cond,msg):
    if not cond:raise RuntimeError("DECOMP2_FAIL_CLOSED "+str(msg))

def pin():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    return cpu

def getcpu():
    a=resource.getrusage(resource.RUSAGE_SELF)
    b=resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime

def original_cases():
    m=json.loads((SOURCE/"manifest.json").read_text())
    need(len(m["cases"])==24,"frozen EQUIV2 24 cohort drift")
    cases={}
    for x in m["cases"]:
        f=SOURCE/x["filename"]
        need(f.is_file() and d1.sha(f)==x["sha256"],"source original SHA mismatch")
        cases[x["sha256"]]=dict(sha256=x["sha256"],filename=x["filename"],
                                path=str(f),gbd=x.get("gbd"))
    need(len(cases)==24,"source SHA collision")
    return cases

def components(clauses,omit=0):
    """Connected components of CNF clause-variable incidence graph.
       Isolated variables never impose constraints; empty clauses form their
       own components. 'omit' removes a variable, NOT a clause."""
    via=collections.defaultdict(list)
    for i,c in enumerate(clauses):
        for v in {abs(l) for l in c if abs(l)!=omit}:
            via[v].append(i)
    seen=bytearray(len(clauses))
    out=[]
    for i in range(len(clauses)):
        if seen[i]:continue
        seen[i]=1
        todo=[i];part=[];head=0
        while head<len(todo):
            j=todo[head];head+=1
            part.append(j)
            for v in {abs(l) for l in clauses[j] if abs(l)!=omit}:
                hits=via.pop(v,())
                for k in hits:
                    if not seen[k]:
                        seen[k]=1;todo.append(k)
        out.append(part)
    return out

def verify_separator(n,clauses,variable,expected):
    """Independent Python graph audit of the C++ Tarjan split sizes."""
    need(0<variable<=n,"invalid separator")
    cc=components(clauses)
    connected=[part for part in cc if any(abs(l)==variable
                      for j in part for l in clauses[j])]
    need(len(connected)==1,"separator must belong to one connected component")
    selected=[clauses[j] for j in connected[0]]
    sizes=sorted((len(x) for x in components(selected,omit=variable)),reverse=True)
    need(sizes==expected,"native C++ separator partition mismatch: "+str(sizes[:9]))
    need(len(sizes)>=2,"not an articulation point")
    return sizes

def prepare():
    ROOT.mkdir(exist_ok=True)
    need(d1.sha(KISSAT)==PIN,"pinned solver changed")
    allcases=original_cases()
    scan=json.loads(pathlib.Path("mre_decomp1/screen.json").read_text())
    need(len(scan)==24 and all(r["original_SHA_verified"] for r in scan),
         "screen incomplete or unverified")
    scanned={r["original_sha256"]:r for r in scan}
    need(set(scanned)==set(allcases),"DECOMP1 original SHA drift")
    good=[r for r in scan if r["status"]=="OK" and
          r["graph"].get("best_separator_var",0)>0]
    good.sort(key=lambda x:(-x["graph"]["best_second_largest_part"],x["original_sha256"]))
    disconnected=[r for r in scan if r["status"]=="OK" and r["graph"]["clause_components"]>1]
    disconnected.sort(key=lambda x:x["original_sha256"])
    chosen=[]
    for r in good+disconnected+sorted(scan,key=lambda x:x["original_sha256"]):
        if r["status"]!="OK" or r["original_sha256"] in chosen:continue
        chosen.append(r["original_sha256"])
        if len(chosen)==8:break
    need(len(chosen)==8 and bool(good),"no structural candidate or insufficient samples")
    selected=[]
    for h in chosen:
        c=dict(allcases[h]);g=scanned[h]["graph"]
        c.update(graph=g,signal=bool(g.get("best_separator_var")),
                 first_seen_in_DECOMP1=True)
        n,clauses=d1.read_cnf(c["path"])
        if g["best_separator_var"]:
            verify_separator(n,clauses,g["best_separator_var"],g["best_clause_parts"])
        selected.append(c)
    freeze={"protocol":PROTO,"cases":selected,"arms":ARMS,"reps":REPS,
            "cap_s":CAP,"expected_trials":len(selected)*len(ARMS)*REPS,
            "selection":"source-only DECOMP1 candidate first, then disconnected, then SHA controls",
            "source_count":len(selected),"source_sha_verified":True,
            "globally_blind":False,"solvers_pinned":PIN,
            "originals_never_modified":True,"original_cohort":"EQUIV2 2026 24"}
    (ROOT/"freeze.json").write_text(json.dumps(freeze,sort_keys=True,indent=2)+"\n")
    print("DECOMP2_FREEZE_PASS "+json.dumps({
      "selected":len(selected),"meaningful_separators":sum(c["signal"] for c in selected),
      "disconnected_sources":sum(c["graph"]["clause_components"]>1 for c in selected),
      "top": [{"sha":c["sha256"],"var":c["graph"]["best_separator_var"],
               "parts":c["graph"]["best_clause_parts"]} for c in selected if c["signal"]],
      "trials":freeze["expected_trials"]},sort_keys=True),flush=True)

def frozen():
    f=json.loads((ROOT/"freeze.json").read_text())
    cases=original_cases()
    need(f["protocol"]==PROTO and len(f["cases"])==8 and
         f["solvers_pinned"]==d1.sha(KISSAT),"freeze or pinned Kissat changed")
    need(set(x["sha256"] for x in f["cases"]).issubset(cases),"unseen frozen source")
    for x in f["cases"]:
        need(x["path"]==cases[x["sha256"]]["path"],"source path changed")
    return f

def simplify(clauses,var,truth):
    output=[]
    for c in clauses:
        if any(abs(l)==var and (l>0)==truth for l in c):
            continue
        output.append(tuple(l for l in c if abs(l)!=var))
    return output

def write_compact(target,clauses):
    vs=sorted({abs(l) for c in clauses for l in c})
    mp={v:i+1 for i,v in enumerate(vs)}
    tmp=tuple(tuple((1 if l>0 else -1)*mp[abs(l)] for l in c) for c in clauses)
    target.write_text(f"p cnf {len(vs)} {len(tmp)}\n"+
      "".join(" ".join(map(str,c))+" 0\n" for c in tmp))
    return vs,tmp

def parsed_model(text):
    vals={}
    for line in text.splitlines():
        if not line.startswith("v "):continue
        for w in line[2:].split():
            try:lit=int(w)
            except ValueError:continue
            if lit:
                v=abs(lit)
                need(v not in vals or vals[v]==(lit>0),"contradictory component model")
                vals[v]=lit>0
    return vals

def solve_raw(source,clauses,seed,deadline,cpu):
    rem=deadline-time.monotonic()
    if rem<=0.001:return "TIMEOUT",{},1,0
    rc,out,err,_,_,timed=d1.run_process(
         [KISSAT,"--seed="+str(seed),source],rem,cpu)
    if timed:return "TIMEOUT",{},1,0
    status,witness=d1.outcome(rc,out,clauses)
    return status, parsed_model(out) if status=="SAT" else {},1,0

def solve_parts(clauses,tmp,seed,deadline,cpu,small_first):
    if any(not c for c in clauses):
        return "UNSAT",{},0,0
    if not clauses:return "SAT",{},0,0
    comps=components(clauses)
    if len(comps)>MAX_PARTS:
        # Exact fallback: solve complete conditioned CNF, no invalid pruning.
        comps=[list(range(len(clauses)))]
    comps.sort(key=lambda c: (len(c), min(c)),reverse=not small_first)
    witness={};calls=0
    for part in comps:
        if time.monotonic()>=deadline:return "TIMEOUT",{},calls,len(comps)
        loc=[clauses[i] for i in part]
        file=tmp/("component-"+str(calls)+".cnf")
        variables,local=write_compact(file,loc)
        if not local:continue
        rem=deadline-time.monotonic()
        if rem<=0.001:return "TIMEOUT",{},calls,len(comps)
        rc,out,err,_,_,timed=d1.run_process(
            [KISSAT,"--seed="+str(seed),file],rem,cpu)
        calls+=1
        if timed:return "TIMEOUT",{},calls,len(comps)
        status,verified=d1.outcome(rc,out,local)
        if status=="UNSAT":return "UNSAT",{},calls,len(comps)
        check_model=parsed_model(out)
        for localid,b in check_model.items():
            need(1<=localid<=len(variables),"wrong local witness")
            actual=variables[localid-1]
            need(actual not in witness or witness[actual]==b,"component variable overlap")
            witness[actual]=b
    return "SAT",witness,calls,len(comps)

def trial(case,arm,rep):
    c=pin()
    start=time.monotonic();cpu0=getcpu();deadline=start+CAP
    source=pathlib.Path(case["path"])
    need(d1.sha(source)==case["sha256"],"original SHA mismatch")
    n,original=d1.read_cnf(source)
    status="TIMEOUT";model={};calls=0;parts=0;native={}
    route="direct";preps=0.0;abstained=False
    with tempfile.TemporaryDirectory(prefix="decomp2-") as td:
        tmp=pathlib.Path(td)
        if arm!="kissat_raw":
            rem=deadline-time.monotonic()
            if rem>0.01:
                p=subprocess.run([str(NATIVE),str(source),"2500"],
                  capture_output=True,text=True,timeout=min(3.2,rem))
                need(p.returncode in (0,75),"scanner failed "+p.stderr[-300:])
                msgs=[x.split(" ",1)[1] for x in p.stdout.splitlines()
                      if x.startswith(("DECOMP1_SCAN ","DECOMP1_ABSTAIN "))]
                need(len(msgs)==1,"scanner missing protocol")
                native=json.loads(msgs[0])
                need(p.returncode==0 and native.get("status")=="OK","scanner abstained on frozen source")
                g=case["graph"]
                need(native["best_separator_var"]==g["best_separator_var"] and
                     native["best_clause_parts"]==g["best_clause_parts"] and
                     native["clause_components"]==g["clause_components"],
                     "native structure changed since freeze")
            else:abstained=True
        preps=time.monotonic()-start
        if not abstained and deadline>time.monotonic()+.001:
            seed=1001+rep
            if arm in ("kissat_raw","incidence_shadow"):
                status,model,calls,parts=solve_raw(source,original,seed,deadline,c)
            elif arm=="existing_components":
                with tempfile.TemporaryDirectory(dir=tmp) as sub:
                    status,model,calls,parts=solve_parts(original,pathlib.Path(sub),
                                                seed,deadline,c,True)
                route="existing_incidence_components"
            elif arm=="cut_small_first":
                x=case["graph"].get("best_separator_var",0)
                if x:
                    verify_separator(n,original,x,case["graph"]["best_clause_parts"])
                    route="exact_articulation_branch"
                    statuses=[]
                    for b in (False,True):
                        if time.monotonic()>=deadline:
                            status="TIMEOUT";break
                        conditional=simplify(original,x,b)
                        with tempfile.TemporaryDirectory(dir=tmp) as sub:
                            st,vals,uses,num=solve_parts(conditional,pathlib.Path(sub),
                                                         seed,deadline,c,True)
                        calls+=uses;parts+=num;statuses.append(st)
                        if st=="SAT":
                            model={x:b,**vals}
                            status="SAT";break
                        if st=="TIMEOUT":
                            status="TIMEOUT";break
                    else:
                        if statuses==["UNSAT","UNSAT"]:status="UNSAT"
                else:
                    with tempfile.TemporaryDirectory(dir=tmp) as sub:
                        status,model,calls,parts=solve_parts(original,pathlib.Path(sub),
                                                        seed,deadline,c,True)
                    route="disconnected_or_fallback"
            else:raise RuntimeError("unknown arm")
    wall=time.monotonic()-start
    if status=="TIMEOUT":wall=min(wall,CAP)
    need(wall<=CAP+.12,"E2E budget exceeded")
    if status=="SAT":
        model={**{v:False for v in range(1,n+1)},**model}
        need(d1.holds(original,model),"SAT witness fails ORIGINAL CNF")
    need(d1.sha(source)==case["sha256"],"original SHA drift after trial")
    return dict(protocol=PROTO,original_sha256=case["sha256"],arm=arm,rep=rep,
       one_cpu=True,cpu_affinity=[c],cap_s=CAP,route=route,
       status=status,SAT_original_witness_verified=status=="SAT",
       UNSAT_independent_LRAT=False,UNSAT_backend_only=status=="UNSAT",
       original_SHA_verified=True,E2E_s=round(wall,6),
       CPU_s=round(getcpu()-cpu0,6),
       PAR2_s=round(2*CAP if status=="TIMEOUT" else wall,6),
       preprocess_wall_s=round(preps,6),solver_calls=calls,components_solved=parts,
       separator_var=case["graph"]["best_separator_var"],abstained=abstained)

def bench(shard):
    need(0<=shard<SHARDS,"invalid shard")
    f=frozen()
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for i,x in enumerate(f["cases"]):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(x["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=trial(x,arm,rep);row["shard"]=shard
                rows.append(row)
                (ROOT/("shard-"+str(shard)+".json")).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("DECOMP2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(f["cases"][shard::SHARDS])*REPS*len(ARMS),
         "incomplete shard")
    print("DECOMP2_SHARD_PASS",shard,len(rows),flush=True)

def summarize(rows):
    return dict(attempts=len(rows),
       solved=sum(r["status"]!="TIMEOUT" for r in rows),
       SAT_original_verified=sum(r["SAT_original_witness_verified"] for r in rows),
       UNSAT_backend_only=sum(r["UNSAT_backend_only"] for r in rows),
       PAR2_s=round(sum(r["PAR2_s"] for r in rows),6),
       E2E_s=round(sum(r["E2E_s"] for r in rows),6),
       CPU_s=round(sum(r["CPU_s"] for r in rows),6),
       prep_s=round(sum(r["preprocess_wall_s"] for r in rows),6),
       solver_calls=sum(r["solver_calls"] for r in rows))

def audit():
    f=frozen();rows=[]
    shards={}
    for i in range(SHARDS):
        path=ROOT/("shard-"+str(i)+".json")
        need(path.is_file(),"missing shard")
        data=json.loads(path.read_text())
        need(len(data)==len(f["cases"][i::SHARDS])*REPS*len(ARMS),
             "incomplete shard "+str(i))
        rows+=data
        shards[str(i)]={a:summarize([r for r in data if r["arm"]==a]) for a in ARMS}
    expected={(x["sha256"],a,rep) for x in f["cases"] for a in ARMS for rep in range(REPS)}
    got={(r["original_sha256"],r["arm"],r["rep"]) for r in rows}
    need(len(rows)==len(got)==len(expected)==64 and got==expected,
         "SHA paired matrix mismatch")
    need(all(r["protocol"]==PROTO and r["original_SHA_verified"] and
       r["one_cpu"] and len(r["cpu_affinity"])==1 and r["cap_s"]==CAP and
       0<=r["E2E_s"]<=CAP+.12 and
       (r["status"]!="SAT" or r["SAT_original_witness_verified"]) and
       abs(r["PAR2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["E2E_s"]))<.000001
       for r in rows),"provenance/E2E/SAT/PAR2 failure")
    for c in f["cases"]:
        actual={r["status"] for r in rows if
           r["original_sha256"]==c["sha256"] and r["status"]!="TIMEOUT"}
        need(len(actual)<=1,"SAT vs UNSAT contradiction")
    scores={a:summarize([r for r in rows if r["arm"]==a]) for a in ARMS}
    base=scores["kissat_raw"]["PAR2_s"]
    for a in scores:
        scores[a]["speedup_x_vs_kissat"]=round(base/scores[a]["PAR2_s"],6)
    by={(r["original_sha256"],r["arm"],r["rep"]):r for r in rows}
    paired={}
    for arm in ARMS[1:]:
        differences=[]
        for c in f["cases"]:
            for rep in range(REPS):
                a=by[(c["sha256"],arm,rep)]
                b=by[(c["sha256"],"kissat_raw",rep)]
                differences.append(dict(sha256=c["sha256"],rep=rep,
                    delta_PAR2_s=round(a["PAR2_s"]-b["PAR2_s"],6),
                    reference_status=b["status"],arm_status=a["status"],
                    cut_var=c["graph"]["best_separator_var"]))
        paired[arm]=dict(wins=sum(x["delta_PAR2_s"]<-.02 for x in differences),
            losses=sum(x["delta_PAR2_s"]>.02 for x in differences),
            ties=sum(abs(x["delta_PAR2_s"])<=.02 for x in differences),
            worst=sorted(differences,key=lambda x:-x["delta_PAR2_s"])[:4],
            best=sorted(differences,key=lambda x:x["delta_PAR2_s"])[:4])
    report=dict(protocol=PROTO,source_count=8,original_cohort="EQUIV2",
      source_selected_by_structure_only=True,globally_blind=False,
      one_logical_cpu_per_solver=True,UNSAT_independent_LRAT=False,
      SAT_original_witness_verified=True,no_automatic_promotion=True,
      E2E_includes_all_routing_and_component_solvers=True,
      total_trials=len(rows),cap_s=CAP,scores=scores,per_shard=shards,paired=paired)
    (ROOT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DECOMP2_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def selftest():
    # Exhaustive 2^(<=5) truth-table equivalence for all branch outcomes.
    rng=random.Random(27519)
    cases=0
    for j in range(120):
        n=rng.randrange(2,6)
        clauses=[tuple((1 if rng.randrange(2) else -1)*v
                    for v in rng.sample(range(1,n+1),rng.randrange(1,n+1)))
                 for _ in range(rng.randrange(1,12))]
        x=rng.randrange(1,n+1)
        true_formula=any(d1.holds(clauses,dict(zip(range(1,n+1),bits)))
              for bits in __import__("itertools").product((False,True),repeat=n))
        conditional_ok=False
        for b in (False,True):
            cond=simplify(clauses,x,b)
            for bits in __import__("itertools").product((False,True),repeat=n):
                model=dict(zip(range(1,n+1),bits));model[x]=b
                if d1.holds(cond,model):
                    conditional_ok=True;break
        need(true_formula==conditional_ok,"exact branch semantic mismatch")
        # Removing x from incidence must produce var-disjoint components.
        parts=components(simplify(clauses,x,False))
        sets=[{abs(v) for idx in part for v in simplify(clauses,x,False)[idx]}
              for part in parts]
        need(all(not(sets[k]&sets[l]) for k in range(len(sets))
                for l in range(k+1,len(sets))),"components share a variable")
        cases+=1
    print("DECOMP2_SELFTEST_PASS "+json.dumps({"exhaustive_small_CNF":cases,
       "branch_semantics_exact":True,"component_variable_disjoint":True}))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=("selftest","prepare","bench","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.mode=="bench":bench(args.shard)
    else:globals()[args.mode]()

#!/usr/bin/env python3
"""EQUIV5: 2x2 congruence x reluctant factorial and reduction interactions, source-locked originals.
Reuses X20 pre-registered original-source SHA, NOT fresh blind cases.
SAT must satisfy ORIGINAL source. UNSAT is scored only with historical
independent BACKEND consensus on original CNF, NOT LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import time
import resource
import re

import drnas_x22_parallel_reducer as x22
import drnas_x25_alias_dose as x25
import drnas_x20_select2_validation as x20

ROOT=pathlib.Path("mre_equiv5")
SOURCE=pathlib.Path("mre_x20")
CPP=ROOT/"bin/alias_dose"
CAD=pathlib.Path("/usr/bin/cadical")
CAD3=ROOT/"bin/cadical_3_0_1"
PROTO="DRNAS-EQUIV5-CONGRUENCE-X-RELUCTANT-432-9ARM-12S-v1"
ARMS=("cadical3_default","cadical3_no_congruence","cadical3_no_reluctant",
      "cadical3_both","cadical3_both_reduce10","cadical3_both_reduce100",
      "cadical_default","native1","kissat1")
REPS=2
SHARDS=8
CAP=12.0
EXPECTED=24*REPS*len(ARMS)
OPTIONS={
    "cadical3_default": [],
    "cadical3_no_congruence": ["--no-congruence"],
    "cadical3_no_reluctant": ["--no-reluctant"],
    "cadical3_both": ["--no-congruence","--no-reluctant"],
    "cadical3_both_reduce10": ["--no-congruence","--no-reluctant","--reduceint=10"],
    "cadical3_both_reduce100": ["--no-congruence","--no-reluctant","--reduceint=100"],
    "cadical_default": [],
}
def need(ok,why):
    if not ok:raise RuntimeError("EQUIV5_FAIL_CLOSED "+str(why))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def seed(case,rep):
    return x20.seed(case,rep)
def historical_consensus():
    """Two distinct unmodified solvers previously reported UNSAT on same SHA."""
    rows=[]
    for i in range(8):
        path=pathlib.Path("prior_x20")/("shard-%d.json"%i)
        need(path.is_file(),"missing original X20 shard "+str(i))
        rows+=json.loads(path.read_text())
    need(len(rows)==288,"prior X20 audit trial count")
    grouped=collections.defaultdict(set)
    for r in rows:
        if r["arm"] in ("native1","kissat1","cadical1") and r["status"]=="UNSAT":
            grouped[r["original_sha256"]].add(r["selected_backend"])
    return {sha for sha,v in grouped.items() if len(v)>=2}
def source_option_diff():
    paths={"old":ROOT/"options-1.7.3.hpp","new":ROOT/"options-3.0.1.hpp"}
    found={}
    regex=re.compile(r"\bOPTION\s*\(\s*([a-z][a-z0-9_]*)\s*,\s*([^,\s]+)",re.I)
    # Parse actual macro declarations, not prose (requires ~100 entries per version).
    for ver,p in paths.items():
        need(p.is_file(),"missing original source options "+str(p))
        text=p.read_text()
        found[ver]={name:value for name,value in regex.findall(text)}
        need(len(found[ver])>=100,"source option definitions not parsed: "+ver)
    old,new=found["old"],found["new"]
    changed={name:dict(old=old[name],new=new[name])
             for name in sorted(old.keys() & new.keys()) if old[name]!=new[name]}
    added={name:new[name] for name in sorted(new.keys()-old.keys())}
    removed={name:old[name] for name in sorted(old.keys()-new.keys())}
    diff=dict(version_tags={"old":"rel-1.7.3","new":"rel-3.0.1"},
              source_sha256={key:digest(path) for key,path in paths.items()},
              total_options={key:len(found[key]) for key in found},
              changed_defaults=changed,added_options=added,removed_options=removed,
              relevant={name:{"old":old.get(name),"new":new.get(name)}
                for name in ("factor","preprocesslight","congruence","sweep","probe",
                             "decompose","vivify","stabilize","restart")})
    save(ROOT/"option-diff.json",diff)
    print("EQUIV5_OPTION_DIFF",json.dumps(diff,sort_keys=True),flush=True)
    return diff
def check_options():
    versions={}
    for label,solver in (("old",CAD),("new",CAD3)):
        helptext=subprocess.run([str(solver),"--help"],capture_output=True,
                                text=True,timeout=15,check=True).stdout
        needed=("congruence","reluctant","reduceint") if label=="new" else ("decompose",)
        for word in needed:
            need(("--"+word) in helptext,label+" missing option "+word)
        v=subprocess.run([str(solver),"--version"],capture_output=True,
                         text=True,timeout=10,check=True)
        versions[label]=(v.stdout+" "+v.stderr).strip()
    need("3.0.1" in versions["new"] and "1.7.3" in versions["old"],
         "solver versions changed")
    return versions
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    m=json.loads((SOURCE/"manifest.json").read_text())
    need(len(m["cases"])==24 and m["expected_trials"]==288,
         "original X20 roster changed")
    need(len({c["sha256"] for c in m["cases"]})==24,"duplicate source SHA")
    need(CPP.is_file(),"native SCC executable missing")
    need(pathlib.Path("mre_x4/bin/native").is_file(),"native binary missing")
    need(pathlib.Path("built/bin/kissat_4_0_4").is_file(),"Kissat binary missing")
    for c in m["cases"]:
        need(digest(SOURCE/c["filename"])==c["sha256"],"original SHA drift")
    prior=historical_consensus()
    need(prior.issubset({c["sha256"] for c in m["cases"]}),"prior reference mismatch")
    version=check_options()
    option_diff=source_option_diff()
    save(ROOT/"manifest.json",dict(
        protocol=PROTO,source_run_id=42587550843,not_blind_reuses_x20=True,
        source_sha=[c["sha256"] for c in m["cases"]],cases=m["cases"],
        code_sha256=digest(__file__),source_manifest_sha256=digest(SOURCE/"manifest.json"),
        native_cpp_sha256=digest("research/drnas_x25_alias_dose.cpp"),
        helper_sha256=digest(CPP),cadical_sha256=digest(CAD),cadical3_sha256=digest(CAD3),
        cadical_version=version,
        option_diff_sha256=digest(ROOT/"option-diff.json"),
        options_old_sha256=digest(ROOT/"options-1.7.3.hpp"),
        options_new_sha256=digest(ROOT/"options-3.0.1.hpp"),
        kissat_sha256=digest("built/bin/kissat_4_0_4"),
        native_sha256=digest("mre_x4/bin/native"),
        original_unsat_backend_consensus=sorted(prior),
        independent_UNSAT_LRAT=False,original_SAT_witness_required=True,
        no_auto_promotion=True,reps=REPS,cap_s=CAP,arms=ARMS,
        shards=SHARDS,expected_trials=EXPECTED,
        cpu_policy="one allowed Linux logical CPU per arm, E2E wall + child CPU",
        mechanism="2x2 CaDiCaL 3.0.1 congruence x reluctant, interaction with reduceint 10 and 100, old 1.7.3 and Kissat Native baselines"))
    print("EQUIV5_FROZEN",json.dumps(dict(sources=24,attempts=EXPECTED,
          cadical_version=version,consensus_unsat=len(prior)),sort_keys=True),flush=True)
def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==24 and
         m["arms"]==list(ARMS) and m["expected_trials"]==EXPECTED,"protocol drift")
    need(m["code_sha256"]==digest(__file__) and
         m["native_cpp_sha256"]==digest("research/drnas_x25_alias_dose.cpp") and
         m["helper_sha256"]==digest(CPP),"implementation drift")
    need(m["source_manifest_sha256"]==digest(SOURCE/"manifest.json"),
         "source manifest drift")
    need(m["option_diff_sha256"]==digest(ROOT/"option-diff.json") and
         m["options_old_sha256"]==digest(ROOT/"options-1.7.3.hpp") and
         m["options_new_sha256"]==digest(ROOT/"options-3.0.1.hpp"),
         "CaDiCaL source option diff modified")
    need(m["cadical_sha256"]==digest(CAD) and
         m["cadical3_sha256"]==digest(CAD3),"CaDiCaL binary drift")
    need(m["kissat_sha256"]==digest("built/bin/kissat_4_0_4") and
         m["native_sha256"]==digest("mre_x4/bin/native"),"baseline binary drift")
    for c in m["cases"]:
        need(digest(SOURCE/c["filename"])==c["sha256"],"source modified")
    return m
def selftest():
    version=check_options()
    small="p cnf 3 4\n-1 2 0\n1 -2 0\n-2 3 0\n2 -3 0\n"
    with tempfile.TemporaryDirectory() as d:
        d=pathlib.Path(d);p=d/"src.cnf";p.write_text(small)
        for arm in OPTIONS:
            v=run_one(dict(filename="src.cnf",sha256=digest(p),
                           gbd="selftest",cohort="selftest",structure={}),0,arm,
                      source_root=d,only_test=True)
            need(v["status"]=="SAT" and v["SAT_original_witness_verified"],
                 "SAT original reconstruction failed for "+arm)
    print("EQUIV5_SELFTEST_PASS",json.dumps(version,sort_keys=True),len(OPTIONS),flush=True)
def stage(src,base,n,clauses,number):
    reduced=base/("pass-%d.cnf"%number)
    mapping=base/("pass-%d.map"%number)
    started=time.perf_counter()
    result=subprocess.run([str(CPP),"quotient",str(src),str(reduced),
                     str(mapping),"128"],capture_output=True,text=True,timeout=3)
    need(result.returncode==0,"reducer failed "+result.stderr[-500:])
    aliases=x25.load_alias_map(mapping,n,128)
    x25.proof_replay(clauses,n,aliases)
    n2,cleaned=x22.read_cnf(reduced)
    need(n2==n,"native SCC altered variable domain")
    tele=[json.loads(x[len("X25_REDUCER "):]) for x in result.stdout.splitlines()
          if x.startswith("X25_REDUCER ")]
    need(len(tele)==1 and tele[0]["aliases"]==len(aliases),
         "reducer telemetry mismatch")
    return reduced,cleaned,aliases,time.perf_counter()-started,tele[0]
def run_one(case,rep,arm,source_root=SOURCE,only_test=False):
    if not only_test:need(arm in ARMS,"unregistered arm")
    src=source_root/case["filename"]
    need(digest(src)==case["sha256"],"trial source SHA")
    cpu=sorted(os.sched_getaffinity(0))[0]
    began=time.perf_counter()
    before=x22.child_cpu()
    status="TIMEOUT";verified=False;replay_s=0.0;prep_s=0.0
    aliases_count=0;eligible=0;clauses_removed=0
    native_mechanism={}
    if arm in ("native1","kissat1"):
        need(not only_test,"native/kissat not included in synthetic test")
        r=x20.trial(case,rep,arm)
        need(r["original_sha256"]==case["sha256"] and
             r["SAT_original_witness_verified"]==(r["status"]=="SAT"),
             "X20 unchanged baseline invalid")
        return dict(protocol=PROTO,arm=arm,rep=rep,gbd=case["gbd"],
            original_sha256=case["sha256"],seed=r["seed"],
            status=r["status"],SAT_original_witness_verified=r["SAT_original_witness_verified"],
            UNSAT_independent_LRAT=False,E2E_s=r["elapsed_s"],
            child_CPU_s=r["child_cpu_s"],prep_E2E_s=0,aliases=0,
            eligible_aliases=0,clauses_removed=0,
            native_mechanism=r.get("native_mechanism",{}),cap_s=CAP)
    n,original=x22.read_cnf(src)
    with tempfile.TemporaryDirectory(dir=ROOT if ROOT.exists() else None) as temp:
        d=pathlib.Path(temp)
        target=src
        stages=[]
        try:
            if arm.startswith("external_scc"):
                t=time.perf_counter()
                target,current,aliases,duration,tele=stage(target,d,n,original,1)
                stages.append(aliases)
                eligible+=tele["eligible_aliases"]
                aliases_count+=len(aliases)
                clauses_removed+=tele["input_clauses"]-tele["output_clauses"]
                if arm=="external_scc_iter2" and aliases:
                    target,current,aliases2,duration2,tele2=stage(target,d,n,current,2)
                    stages.append(aliases2)
                    eligible+=tele2["eligible_aliases"]
                    aliases_count+=len(aliases2)
                    clauses_removed+=tele2["input_clauses"]-tele2["output_clauses"]
                prep_s=time.perf_counter()-t
            if time.perf_counter()-began < CAP-.07:
                command=[str(CAD3 if arm.startswith("cadical3_") else CAD),
                         *OPTIONS[arm],str(target)]
                child=x22.launch("solver",command,cpu,d)
                try:
                    while child["p"].poll() is None and time.perf_counter()-began<CAP-.02:
                        time.sleep(.006)
                    if child["p"].poll() is not None:
                        output,err=x22.read_output(child)
                        rc=child["p"].returncode
                        status,verified=x22.solver_result("cadical",rc,output,
                                        current if stages else original,{})
                        if status=="SAT" and stages:
                            assignment={}
                            for line in output.splitlines():
                                if line.startswith("v "):
                                    for lit in map(int,line.split()[1:]):
                                        if lit:assignment[abs(lit)]=(lit>0)
                            for amap in reversed(stages):
                                assignment=x22.lift(assignment,amap)
                            need(x22.holds(original,assignment),
                                 "lifting failed ORIGINAL CNF")
                            verified=True
                finally:
                    x22.cleanup([child])
        except subprocess.TimeoutExpired:
            status="TIMEOUT"
    elapsed=time.perf_counter()-began
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT without original witness")
    return dict(protocol=PROTO,arm=arm,rep=rep,gbd=case["gbd"],
        original_sha256=case["sha256"],seed=seed(case,rep),status=status,
        SAT_original_witness_verified=verified,UNSAT_independent_LRAT=False,
        E2E_s=round(elapsed,6),child_CPU_s=round(x22.child_cpu()-before,6),
        prep_E2E_s=round(prep_s,6),aliases=aliases_count,
        eligible_aliases=eligible,clauses_removed=clauses_removed,
        native_mechanism=native_mechanism,cap_s=CAP)
def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"invalid shard")
    rows=[]
    for c in m["cases"][idx::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed(c,rep)).shuffle(arms)
            for arm in arms:
                r=run_one(c,rep,arm)
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("EQUIV5_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==(24//SHARDS)*REPS*len(ARMS),"incomplete shard")
    print("EQUIV5_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=verify()
    rows=[]
    for idx in range(SHARDS):
        r=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(r)==(24//SHARDS)*REPS*len(ARMS),"incomplete shard "+str(idx))
        rows.extend(r)
    need(len(rows)==EXPECTED,"total incorrect")
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    observed={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(observed)==len(rows) and observed==expected,"missing/duplicate trials")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP,"protocol/cap drift")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified SAT")
        bysha[r["original_sha256"]].append(r)
    for sha,case in bysha.items():
        statuses={r["status"] for r in case if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory SAT/UNSAT on SHA "+sha)
    consensus=set(m["original_unsat_backend_consensus"])
    scores={}
    for arm in ARMS:
        group=[r for r in rows if r["arm"]==arm]
        def accepted(r):
            return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                          r["original_sha256"] in consensus)
        scores[arm]=dict(trials=len(group),
            solved=sum(accepted(r) for r in group),
            SAT_verified=sum(r["status"]=="SAT" for r in group),
            UNSAT_backend_consensus_no_LRAT=sum(r["status"]=="UNSAT" and
                accepted(r) for r in group),
            UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and
                not accepted(r) for r in group),
            PAR2_s=round(sum(r["E2E_s"] if accepted(r) else 2*CAP for r in group),6),
            CPU_PAR2_s=round(sum(r["child_CPU_s"] if accepted(r)
                else 2*CAP for r in group),6),
            actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in group),6),
            preprocessing_s=round(sum(r["prep_E2E_s"] for r in group),6),
            aliases=sum(r["aliases"] for r in group),
            eligible_aliases=sum(r["eligible_aliases"] for r in group),
            clauses_removed=sum(r["clauses_removed"] for r in group))
    baseline=scores["cadical_default"]["PAR2_s"]
    for x in scores.values():
        x["delta_vs_cadical_default_pct"]=round(
            100*(x["PAR2_s"]/baseline-1),4)
    focus_sha={c["sha256"] for c in m["cases"]
       if c["gbd"].startswith(("70af2c3b","26114429","00f2eb37",
                              "220bb8aa","d87714e0"))}
    focus={}
    for sha in sorted(focus_sha):
        case=bysha[sha]
        focus[sha]=dict(gbd=case[0]["gbd"],
            arms={arm:dict(statuses=[r["status"] for r in case if r["arm"]==arm],
              raw_E2E_s=[r["E2E_s"] for r in case if r["arm"]==arm])
              for arm in ARMS})
    report=dict(protocol=PROTO,source_run_id=42587550843,option_diff_sha256=m["option_diff_sha256"],
        sources=24,reps=REPS,trials=EXPECTED,cadical_version=m["cadical_version"],
        not_blind=True,independent_LRAT=False,no_auto_promotion=True,
        historical_consensus=sorted(consensus),scores=scores,
        high_interest_formulas=focus)
    save(ROOT/"report.json",report)
    print("EQUIV5_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        ret=globals()[args.action]()
        if args.action=="verify":print("EQUIV5_VERIFY_PASS",flush=True)

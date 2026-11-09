#!/usr/bin/env python3
"""DRNAS X25: native signed SCC quotient dose test 64,128,256,512 aliases.

Exact original SHA X21/X22 sources, original SAT witness verification,
independent replay of implications on ORIGINAL binary clauses,
two pinned logical CPUs, paired 15s end-to-end budget incl. proof replay.
No new blind claims; UNSAT cross-solver agreement is not independent LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import signal
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_x25")
BIN=ROOT/"bin/alias_dose"
PROTO="DRNAS-X25-NATIVE-SCC-DOSE-64-128-256-512-24SHA-7ARM-2REP-15S-v1"
ARMS=("kissat1","cadical1","race_original","cap64","cap128","cap256","cap512")
LIMITS=(64,128,256,512)
CAP=15.0
REPS=2
SHARDS=8
EXPECTED=24*REPS*len(ARMS)

def need(ok,why):
    if not ok:raise RuntimeError("X25_FAIL_CLOSED "+str(why))
def digest(path):return x22.digest(path)
def save(path,value):return x22.save(path,value)

def load_alias_map(path,n,cap):
    lines=pathlib.Path(path).read_text().splitlines()
    need(bool(lines),"missing map")
    header=lines[0].split()
    need(len(header)==4 and header[:2]==["p","map"] and
         int(header[2])==n and int(header[3])==len(lines)-1,
         "bad mapping header")
    out={}
    for line in lines[1:]:
        a,b=map(int,line.split())
        need(0<a<=n and 0<abs(b)<a and a not in out,
             "noncanonical or duplicate alias")
        out[a]=b
    need(len(out)<=cap,"map exceeded native dose")
    return out

def proof_replay(original,n,aliases):
    """Independent iterative Kosaraju on ORIGINAL signed implication graph.

    SCC equivalence is equivalent to X22's two-direction BFS paths,
    but computes all equivalences in one O(V+E) pass to avoid repeating
    512 separate BFS traversals. Verify positive AND complement SCC.
    """
    if not aliases:return
    graph=collections.defaultdict(list)
    reverse=collections.defaultdict(list)
    vertices=set()
    for clause in original:
        if len(clause)!=2:continue
        a,b=clause
        if a==b or a==-b:continue
        for src,dst in ((-a,b),(-b,a)):
            graph[src].append(dst);reverse[dst].append(src)
            vertices.add(src);vertices.add(dst)
    for v,target in aliases.items():
        need(v in vertices and target in vertices and
             -v in vertices and -target in vertices,
             "alias lacks original binary graph endpoints")
    seen=set();order=[]
    for root in sorted(vertices):
        if root in seen:continue
        seen.add(root);stack=[(root,0)]
        while stack:
            v,idx=stack[-1]
            outs=graph[v]
            if idx==len(outs):
                order.append(v);stack.pop();continue
            next_lit=outs[idx]
            stack[-1]=(v,idx+1)
            if next_lit not in seen:
                seen.add(next_lit);stack.append((next_lit,0))
    comp={};cid=0
    for root in reversed(order):
        if root in comp:continue
        comp[root]=cid;stack=[root]
        while stack:
            v=stack.pop()
            for parent in reverse[v]:
                if parent not in comp:
                    comp[parent]=cid;stack.append(parent)
        cid+=1
    for v,target in aliases.items():
        need(comp[v]==comp[target] and comp[-v]==comp[-target],
             "alias not implied by original source in both directions")
        need(comp[v]!=comp[-v],"contradictory signed source SCC")
    # X22 BFS criterion is strictly equivalent to these SCC relations.

def references():
    return dict(kissat=digest(x22.KISSAT),cadical=digest(x22.CADICAL),
                old_reducer=digest(x22.BIN),native_dose=digest(BIN))

def verify():
    old=x22.verify_frozen()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["caps"]==list(LIMITS) and m["expected_trials"]==EXPECTED and
         len(m["cases"])==24,"frozen protocol drift")
    need(m["code_sha256"]==digest(__file__) and
         m["native_cpp_sha256"]==digest("research/drnas_x25_alias_dose.cpp") and
         m["x22_manifest_sha256"]==digest(x22.ROOT/"manifest.json") and
         m["prior_x22_report_sha256"]==digest("prior_x22/report.json"),
         "code/source/report drift")
    need(m["backend_sha256"]==references(),"pinned binary drift")
    need(m["cases"]==old["cases"],"source roster drift")
    return m

def freeze():
    old=x22.verify_frozen()
    need(pathlib.Path("prior_x22/report.json").is_file(),
         "independent original pair consensus missing")
    reference=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    need(set(reference["confirmed_original_UNSAT"])==
         {c["sha256"] for c in old["cases"]},"missing X22 UNSAT roster")
    ROOT.mkdir(parents=True,exist_ok=True)
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=old["cases"],
        caps=LIMITS,arms=ARMS,cap_s=CAP,reps=REPS,shards=SHARDS,
        expected_trials=EXPECTED,source_run_id=42591977333,
        original_source_SHA_unchanged=True,
        x21_original_holdout_reused_not_blind=True,
        no_auto_promotion=True,independent_UNSAT_LRAT=False,
        x22_manifest_sha256=digest(x22.ROOT/"manifest.json"),
        prior_x22_report_sha256=digest("prior_x22/report.json"),
        code_sha256=digest(__file__),
        native_cpp_sha256=digest("research/drnas_x25_alias_dose.cpp"),
        backend_sha256=references(),
        cpu_affinity="pinned same 2 available Linux logical CPUs",
        certification="source-only implication SCC independent Python proof replay; SAT model on original CNF",
        E2E="source parse + concurrent Kissat + native helper + proof replay + CaDiCaL + SAT witness + cleanup"))
    verify()
    print("X25_FROZEN",json.dumps(dict(original_sha=24,trials=EXPECTED,
        arms=ARMS,caps=LIMITS),sort_keys=True),flush=True)

def run_reducer(src,cap,out,mapfile):
    return subprocess.run([str(BIN),"quotient",str(src),str(out),
             str(mapfile),str(cap)],capture_output=True,text=True)

def selftest():
    need(BIN.is_file() and x22.BIN.is_file(),"native binaries absent")
    rng=random.Random(251109)
    examples=[(1,[()]),(2,[(-1,2),(1,-2)]),
              (2,[(1,2),(-1,-2)]),
              (2,[(1,2),(-1,2),(1,-2),(-1,-2)]),
              (3,[(-1,2),(-2,3),(-3,1)])]
    for n in range(1,8):
        for _ in range(20):
            cs=[tuple(rng.choice((-1,1))*rng.randrange(1,n+1)
                for k in range(rng.randrange(0,5)))
                for j in range(rng.randrange(0,12))]
            examples.append((n,cs))
    checks=0
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td)
        src=td/"source.cnf";out=td/"out.cnf";mapping=td/"aliases.map"
        for n,clauses in examples:
            src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            original_digest=digest(src)
            original_models=[{i+1:bits[i] for i in range(n)}
                             for bits in itertools.product((False,True),repeat=n)]
            sat_source=any(x22.holds(clauses,model) for model in original_models)
            for cap in LIMITS:
                p=run_reducer(src,cap,out,mapping)
                need(p.returncode==0,"native selftest failed: "+p.stderr)
                aliases=load_alias_map(mapping,n,cap)
                proof_replay(clauses,n,aliases)
                n2,cleaned=x22.read_cnf(out)
                need(n2==n,"DIMACS source variable count changed")
                sat_out=False
                for model in original_models:
                    if x22.holds(cleaned,model):
                        sat_out=True
                        need(x22.holds(clauses,x22.lift(model,aliases)),
                             "unsound lifted SAT assignment")
                need(sat_source==sat_out,"source/transformed SAT disagree")
                checks+=1
            need(digest(src)==original_digest,"source CNF modified")
        # Synthetic source with 599 distinct independent equivalences,
        # beyond every tested dose, without relying on small random CNFs.
        n=600
        clauses=[(-1,v) for v in range(2,n+1)]+[(1,-v) for v in range(2,n+1)]
        src.write_text("p cnf %d %d\n"%(n,len(clauses))+
           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        for cap in LIMITS:
            p=run_reducer(src,cap,out,mapping)
            need(p.returncode==0,"large SCC benchmark failed: "+p.stderr)
            tele=[json.loads(line[len("X25_REDUCER "):])
                  for line in p.stdout.splitlines()
                  if line.startswith("X25_REDUCER ")]
            need(len(tele)==1,"missing telemetry")
            aliases=load_alias_map(mapping,n,cap)
            proof_replay(clauses,n,aliases)
            need(len(aliases)==cap and tele[0]["eligible_aliases"]==599,
                 "native dose did not respect cap/eligible count")
            need(tele[0]["aliases"]==cap,"alias telemetry mismatch")
            checks+=1
        # Byte-for-byte cap64 parity with frozen X22 original binary:
        # this proves the new native C++ cap64 code is identical in effect.
        old_cnf=td/"old.cnf";old_map=td/"old.map"
        for case in x22.verify_frozen()["cases"][:4]:
            source=x22.ROOT/"cases"/case["filename"]
            p=run_reducer(source,64,out,mapping)
            need(p.returncode==0,"native original parity run failed")
            baseline=subprocess.run([str(x22.BIN),"quotient",str(source),
                str(old_cnf),str(old_map)],capture_output=True,text=True)
            need(baseline.returncode==0,"frozen X22 parity run failed")
            need(digest(out)==digest(old_cnf) and
                 digest(mapping)==digest(old_map),
                 "native cap64 output not byte-identical to frozen X22")
            checks+=1
    print("X25_SELFTEST_PASS",checks,
          "exhaustive small CNF checks + all large 599-alias doses + cap64 pinned X22 output parity",
          flush=True)

def trial(case,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid trial")
    src=x22.ROOT/"cases"/case["filename"]
    need(digest(src)==case["sha256"],"original SHA mismatch")
    if arm in ("kissat1","cadical1","race_original"):
        r=x22.trial(case,rep,arm)
        return dict(protocol=PROTO,arm=arm,rep=rep,seed=x22.seed(case,rep),
            original_sha256=case["sha256"],gbd=case["gbd"],
            status=r["status"],winner=r.get("winner"),
            SAT_original_witness_verified=r["SAT_original_witness_verified"],
            UNSAT_independent_LRAT=False,
            cap_aliases=0,eligible_aliases=0,aliases_replayed=0,
            reducer={},second_solver_launched=r["second_solver_launched"],
            E2E_s=r["E2E_s"],child_CPU_s=r["child_cpu_s"],
            proof_replay_E2E_s=0,helper_ready_s=0,cap_s=CAP,
            provisional_PAR2_s=r["provisional_PAR2_s"])
    cap=int(arm.removeprefix("cap"))
    need(cap in LIMITS,"unsupported cap")
    cpu=x22.cpus()
    start=time.perf_counter()
    cpu_before=x22.child_cpu()
    status="TIMEOUT";winner=None;verified=False
    tele={};aliases={};proof_s=0;prep_s=0;second=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        tmp=pathlib.Path(td)
        entries=[];helper=None
        try:
            n,original=x22.read_cnf(src)
            entries.append(x22.launch("kissat",[x22.KISSAT,
                "--seed="+str(x22.seed(case,rep)),src],cpu[0],td))
            helper=x22.launch("dose_helper",[BIN,"quotient",src,
                     tmp/"reduced.cnf",tmp/"alias.map",str(cap)],cpu[1],td)
            entries.append(helper)
            while time.perf_counter()-start<CAP:
                for e in entries:
                    if e["read"] or e["p"].poll() is None:continue
                    e["read"]=True
                    stdout,stderr=x22.read_output(e)
                    if e is helper:
                        need(e["p"].returncode==0,
                             "native reducer failure "+stderr[-500:])
                        lines=[json.loads(line[len("X25_REDUCER "):])
                            for line in stdout.splitlines()
                            if line.startswith("X25_REDUCER ")]
                        need(len(lines)==1,"native reducer telemetry missing")
                        tele=lines[0]
                        need(tele["cap_aliases"]==cap and
                             tele["eligible_aliases"]>=tele["aliases"],
                             "dose telemetry inconsistent")
                        aliases=load_alias_map(tmp/"alias.map",n,cap)
                        need(len(aliases)==tele["aliases"],"alias mapping differs from telemetry")
                        t0=time.perf_counter()
                        proof_replay(original,n,aliases)
                        proof_s=time.perf_counter()-t0
                        need(digest(src)==case["sha256"],"source altered during proof")
                        prep_s=time.perf_counter()-start
                        if time.perf_counter()-start<CAP-.03:
                            next_solver=x22.launch("cadical",[x22.CADICAL,
                                          tmp/"reduced.cnf"],cpu[1],td)
                            next_solver["aliases"]=aliases
                            entries.append(next_solver);second=True
                        break
                    result,checked=x22.solver_result(e["name"],e["p"].returncode,
                          stdout,original,e.get("aliases",{}))
                    status=result;verified=checked;winner=e["name"]
                    break
                if winner:break
                if all(e["read"] for e in entries):break
                time.sleep(.003)
        finally:x22.cleanup(entries)
    wall=time.perf_counter()-start
    if wall>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;verified=False
    return dict(protocol=PROTO,arm=arm,rep=rep,seed=x22.seed(case,rep),
        original_sha256=case["sha256"],gbd=case["gbd"],
        status=status,winner=winner,SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,cap_aliases=cap,
        eligible_aliases=tele.get("eligible_aliases",0),
        aliases_replayed=len(aliases),reducer=tele,
        second_solver_launched=second,
        E2E_s=round(wall,6),
        child_CPU_s=round(x22.child_cpu()-cpu_before,6),
        helper_ready_s=round(prep_s,6),
        proof_replay_E2E_s=round(proof_s,6),cap_s=CAP,
        provisional_PAR2_s=round(wall if status!="TIMEOUT" else 2*CAP,6))

def shard(index):
    m=verify();need(0<=index<SHARDS,"invalid shard")
    rows=[]
    for case in m["cases"][index::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x22.seed(case,rep)).shuffle(order)
            for arm in order:
                r=trial(case,rep,arm)
                rows.append(r)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X25_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==42,"incomplete 42-trial shard")
    print("X25_SHARD_PASS",index,len(rows),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.exists(),"missing shard "+str(i))
        group=json.loads(p.read_text())
        need(len(group)==42,"incomplete shard "+str(i))
        rows.extend(group)
    need(len(rows)==EXPECTED,"incorrect total paired trials")
    keys=set();bysha=collections.defaultdict(list)
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in keys and r["protocol"]==PROTO
             and r["arm"] in ARMS and r["cap_s"]==CAP,
             "duplicate/incorrect trial")
        keys.add(key);bysha[r["original_sha256"]].append(r)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"SAT model not verified on original")
        if r["arm"].startswith("cap"):
            need(r["aliases_replayed"]<=r["cap_aliases"] and
                 r["eligible_aliases"]>=r["aliases_replayed"],
                 "invalid dose or proof telemetry")
    need(len(keys)==EXPECTED,"missing trial keys")
    reference=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    previous=reference["confirmed_original_UNSAT"]
    agreement={}
    for sha,group in bysha.items():
        verdicts={r["status"] for r in group if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"contradictory SAT/UNSAT outcomes")
        originals={r["arm"] for r in group
                   if r["status"]=="UNSAT" and
                   r["arm"] in ("kissat1","cadical1")}
        agreement[sha]=len(originals)==2 or previous[sha]
        if "SAT" in verdicts:
            need(not agreement[sha],"SAT contradicts original two-solver UNSAT")
    structural={sha:max((r["eligible_aliases"] for r in group),default=0)
                for sha,group in bysha.items()}
    high_sha={sha for sha,value in structural.items() if value>64}
    score={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and agreement[r["original_sha256"]])]
        def par2(part):
            return round(sum(r["E2E_s"] if r in accepted else 2*CAP for r in part),5)
        high=[r for r in subset if r["original_sha256"] in high_sha]
        low=[r for r in subset if r["original_sha256"] not in high_sha]
        score[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
             SAT_original_verified=sum(r["status"]=="SAT" for r in accepted),
             UNSAT_original_two_solver_agreement_no_LRAT=sum(
                 r["status"]=="UNSAT" for r in accepted),
             unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted for r in subset),
             PAR2_s=par2(subset),child_CPU_s=round(sum(r["child_CPU_s"] for r in subset),5),
             aliases_replayed=sum(r["aliases_replayed"] for r in subset),
             clauses_removed=sum(r["reducer"].get("input_clauses",0)-
                                 r["reducer"].get("output_clauses",0) for r in subset),
             reducer_E2E_s=round(sum(r["helper_ready_s"] for r in subset),5),
             proof_replay_E2E_s=round(sum(r["proof_replay_E2E_s"] for r in subset),5),
             high_alias_source_trials=len(high),
             high_alias_PAR2_s=par2(high),
             low_alias_PAR2_s=par2(low))
    base=score["race_original"]["PAR2_s"]
    base_high=score["race_original"]["high_alias_PAR2_s"]
    for s in score.values():
        s["PAR2_delta_vs_race_pct"]=round(100*(s["PAR2_s"]/base-1),4)
        s["high_alias_PAR2_delta_vs_race_pct"]=(
            round(100*(s["high_alias_PAR2_s"]/base_high-1),4)
            if base_high else None)
    report=dict(protocol=PROTO,expected_trials=EXPECTED,source_count=24,
         scores=score,source_eligible_aliases=structural,
         high_alias_source_shas=sorted(high_sha),high_alias_source_count=len(high_sha),
         accepted_UNSAT_earlier_X22_or_current_original_cross_agreement=agreement,
         source_run_id=42591977333,
         blinded_holdout=False,independent_LRAT=False,
         verified_SAT_original=True,
         no_auto_promotion=True,original_source_SHA_unchanged=True)
    save(ROOT/"report.json",report)
    print("X25_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()

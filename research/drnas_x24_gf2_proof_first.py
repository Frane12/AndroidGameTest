#!/usr/bin/env python3
"""DRNAS X24 proof-first native GF(2) experiment.

Native C++ emits suggestions, never a trusted rewrite. An independent Python
replayer checks every original XOR half-cube, every elimination combination,
and constructs only implied CNF clauses. This is repeated X22 source SHA,
NOT a new blind holdout. UNSAT cross-agreement is NOT LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import random
import resource
import shutil
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_x24")
BIN=ROOT/"bin/gf2_proof"
PROTO="DRNAS-X24-GF2-PROOF-FIRST-24SHA-3ARM-2REP-15S-20261109-v1"
ARMS=("race_original","race_quotient","gf2_proof_first")
CAP=15.0
SHARDS=8
REPS=2
EXPECTED=24*REPS*len(ARMS)
HELPER_CAP=0.75
MAX_ADDED=64

def need(value,message):
    if not value:raise RuntimeError("X24_FAIL_CLOSED "+str(message))
def save(path,value):return x22.save(path,value)
def sha(path):return x22.digest(path)

def parity(mask):
    return mask.bit_count() & 1

def read_line(line,kind):
    parts=line.split()
    need(len(parts)>=4 and parts[0]==kind and parts.count("|")==1,
         "bad certificate "+line[:100])
    sep=parts.index("|")
    rhs=int(parts[1]);count=int(parts[2])
    need(rhs in (0,1) and 0<=count<=4 and sep==3+count,
         "invalid GF2 row")
    variables=tuple(map(int,parts[3:sep]))
    refs=tuple(map(int,parts[sep+1:]))
    need(variables==tuple(sorted(set(variables))) and all(v>0 for v in variables),
         "noncanonical row")
    need(refs==tuple(sorted(set(refs))),"noncanonical proof ref")
    return rhs,variables,refs

def xor_vectors(rows):
    active=set();rhs=0
    for right,variables in rows:
        rhs^=right
        active.symmetric_difference_update(variables)
    return rhs,tuple(sorted(active))

def verify_certificate(src,cert,out):
    """Fail closed: original clause IDs -> exact XOR -> GF2 sum -> added CNF."""
    n,clauses=x22.read_cnf(src)
    text=pathlib.Path(cert).read_text().splitlines()
    need(len(text)>=2 and text[0]=="GF2V1" and text[-1]=="END",
         "bad or unfinished native certificate")
    eqs=[];derived=[];end_phase=False
    for line in text[1:-1]:
        if line.startswith("E "):
            need(not end_phase and len(eqs)<256,"equation order/limit")
            rhs,vs,ids=read_line(line,"E")
            k=len(vs)
            need(k in (2,3,4) and len(ids)==(1<<(k-1)),
                 "incomplete XOR cube")
            masks=set()
            for id_ in ids:
                need(0<=id_<len(clauses),"source clause ID out of range")
                c=clauses[id_]
                need(len(c)==k and tuple(sorted(abs(x) for x in c))==vs,
                     "source clause not exact XOR block")
                mask=sum(1<<vs.index(abs(v)) for v in c if v<0)
                need(mask not in masks and parity(mask)==(1-rhs),
                     "duplicate or wrong XOR pattern")
                masks.add(mask)
            need(len(masks)==(1<<(k-1)),"missing source pattern")
            eqs.append((rhs,vs))
        elif line.startswith("D "):
            end_phase=True
            need(len(derived)<32,"too many short derivations")
            rhs,vs,ids=read_line(line,"D")
            need(len(vs)<=2 and ids,"non-short or unsupported result")
            need(all(0<=i<len(eqs) for i in ids),"equation index invalid")
            need(xor_vectors(eqs[i] for i in ids)==(rhs,vs),
                 "algebraic proof replay mismatch")
            need(not (len(vs)==0 and rhs==0),"trivial zero row")
            derived.append((rhs,vs))
        else:
            need(False,"unknown certificate directive")
    new=[]
    for rhs,vs in derived:
        if not vs:
            new.append(())
        elif len(vs)==1:
            new.append((vs[0] if rhs else -vs[0],))
        else:
            a,b=vs
            if rhs==0:
                new.extend(((-a,b),(a,-b)))
            else:
                new.extend(((a,b),(-a,-b)))
    seen={tuple(sorted(set(c))) for c in clauses}
    added=[]
    for c in new:
        key=tuple(sorted(set(c)))
        if key not in seen:
            seen.add(key);added.append(c)
    need(len(added)<=MAX_ADDED,"too many implied CNF clauses")
    if added:
        with pathlib.Path(out).open("w") as stream:
            stream.write("p cnf %d %d\n"%(n,len(clauses)+len(added)))
            for c in itertools.chain(clauses,added):
                stream.write(" ".join(map(str,c))+" 0\n")
        need(x22.read_cnf(out)[0]==n,"rewritten DIMACS invalid")
    return dict(complete_xor_blocks=len(eqs),derived_short_rows=len(derived),
                added_clauses=len(added),contradiction=any(not vs for _,vs in derived),
                proof_replayed=True)

def run_gf2(case,rep):
    source=x22.ROOT/"cases"/case["filename"]
    need(sha(source)==case["sha256"],"source SHA changed")
    begin=time.perf_counter();before=x22.child_cpu()
    prep=0.;state="original_fallback";info={};warnings=[]
    status="TIMEOUT";winner=None;checked=False;reduced_unsat=False
    cpus=x22.cpus()
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        folder=pathlib.Path(tmp)
        enhanced=folder/"augmented.cnf";certificate=folder/"trace.cert"
        chosen=source
        try:
            helper=subprocess.run([str(BIN),str(source),str(certificate)],
                capture_output=True,text=True,timeout=HELPER_CAP,
                check=False)
            if helper.returncode==0:
                try:
                    info=verify_certificate(source,certificate,enhanced)
                    if info["added_clauses"]:
                        chosen=enhanced
                        state="verified_addition"
                    else:state="verified_no_gain"
                except Exception as e:
                    warnings.append("replay_rejected:"+str(e)[:200])
                    state="replay_failed_closed"
            else:
                warnings.append("native_exit:"+str(helper.returncode)+":"+helper.stderr[-120:])
                state="native_failed_closed"
        except subprocess.TimeoutExpired:
            state="native_budget_fallback"
        prep=time.perf_counter()-begin
        entries=[]
        try:
            original=x22.read_cnf(source)
            if time.perf_counter()-begin<CAP-0.1:
                entries.append(x22.launch("kissat",[x22.KISSAT,
                    "--seed="+str(x22.seed(case,rep)),source],cpus[0],tmp))
                entries.append(x22.launch("cadical",[x22.CADICAL,chosen],cpus[1],tmp))
                while time.perf_counter()-begin<CAP:
                    for entry in entries:
                        if entry["read"] or entry["p"].poll() is None:continue
                        entry["read"]=True
                        stdout,stderr=x22.read_output(entry)
                        result,proof=x22.solver_result(entry["name"],
                            entry["p"].returncode,stdout,original[1],{})
                        status=result;checked=proof;winner=entry["name"]
                        reduced_unsat=(result=="UNSAT" and entry["name"]=="cadical"
                                       and chosen==enhanced)
                        break
                    if winner:break
                    if all(e["read"] for e in entries):break
                    time.sleep(0.003)
        finally:x22.cleanup(entries)
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;checked=False;reduced_unsat=False
    need(sha(source)==case["sha256"],"post-solve source modified")
    return dict(protocol=PROTO,arm="gf2_proof_first",rep=rep,
        seed=x22.seed(case,rep),gbd=case["gbd"],
        original_sha256=case["sha256"],status=status,winner=winner,
        SAT_original_witness_verified=checked,
        UNSAT_independent_LRAT=False,
        augmented_UNSAT_without_LRAT=reduced_unsat,
        route=state,proof=info,warnings=warnings,
        preprocessing_E2E_s=round(prep,6),E2E_s=round(elapsed,6),
        child_cpu_s=round(x22.child_cpu()-before,6),cap_s=CAP)

def manifest():
    x=x22.verify_frozen()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS)
         and m["expected_trials"]==EXPECTED and len(m["cases"])==24,
         "protocol drift")
    need(m["py_sha256"]==sha(__file__) and m["cpp_sha256"]==
         sha("research/drnas_x24_gf2_proof_first.cpp") and
         m["bin_sha256"]==sha(BIN) and
         m["x22_manifest_sha256"]==sha(x22.ROOT/"manifest.json") and
         m["x22_report_sha256"]==sha("prior_x22/report.json"),
         "source/binary/reference changed")
    need([c["sha256"] for c in x["cases"]]==
         [c["sha256"] for c in m["cases"]],"frozen sources drift")
    return m

def freeze():
    parent=x22.verify_frozen()
    ROOT.mkdir(parents=True,exist_ok=True)
    need(BIN.exists(),"native build not found")
    need(pathlib.Path("prior_x22/report.json").exists(),
         "pinned original UNSAT agreement missing")
    save(ROOT/"manifest.json",dict(protocol=PROTO,arms=ARMS,
         cases=[{k:c[k] for k in ("filename","gbd","sha256","year")}
                for c in parent["cases"]],
         cap_s=CAP,reps=REPS,shards=SHARDS,expected_trials=EXPECTED,
         helper_cap_s=HELPER_CAP,max_added_clauses=MAX_ADDED,
         parent_x22_run=42591977333,
         x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
         x22_report_sha256=sha("prior_x22/report.json"),
         py_sha256=sha(__file__),
         cpp_sha256=sha("research/drnas_x24_gf2_proof_first.cpp"),
         bin_sha256=sha(BIN),source_SHA_unchanged=True,
         source_proof_replay_required=True,not_new_blind_holdout=True,
         UNSAT_independent_LRAT=False,no_auto_promotion=True,
         CPU_limit=2))
    manifest()
    print("X24_FROZEN",json.dumps(dict(trials=EXPECTED,
          sources=24,arms=ARMS,shards=SHARDS),sort_keys=True),flush=True)

def shard(index):
    m=manifest();need(0<=index<SHARDS,"shard")
    rows=[]
    for case in m["cases"][index::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(order)
            for arm in order:
                if arm=="gf2_proof_first":r=run_gf2(case,rep)
                else:r=x22.trial(case,rep,arm)
                r["arm"]=arm;r["protocol"]=PROTO
                rows.append(r);save(ROOT/("shard-%d.json"%index),rows)
                print("X24_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==18,"incomplete shard")
    print("X24_SHARD_PASS",index,len(rows),flush=True)

def audit():
    m=manifest();rows=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.exists(),"missing shard")
        part=json.loads(file.read_text())
        need(len(part)==18,"incomplete shard "+str(i))
        rows.extend(part)
    need(len(rows)==EXPECTED,"missing paired trials")
    originals=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    unsat=originals["confirmed_original_UNSAT"]
    need({c["sha256"] for c in m["cases"]}==set(unsat),"missing UNSAT reference")
    seen=set();groups=collections.defaultdict(list)
    for row in rows:
        k=(row["original_sha256"],row["rep"],row["arm"])
        need(k not in seen and row["protocol"]==PROTO and
             row["arm"] in ARMS and row["cap_s"]==CAP,
             "duplicate/invalid paired row")
        seen.add(k);groups[k[0]].append(row)
        if row["status"]=="SAT":
            need(row["SAT_original_witness_verified"],
                 "SAT original witness not verified")
        need(not (row["status"]=="SAT" and unsat[k[0]]),
             "SAT contradicts independent original reference")
    for sha_,rs in groups.items():
        statuses={r["status"] for r in rs if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT contradiction")
    scores={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and unsat[r["original_sha256"]])]
        scores[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
            SAT_witness_verified=sum(r["status"]=="SAT" for r in accepted),
            UNSAT_cross_agreement_no_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
            unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted
                                  for r in subset),
            PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                             for r in subset),6),
            child_CPU_s=round(sum(r["child_cpu_s"] for r in subset),6),
            gf2_proof_replayed=sum(r.get("proof",{}).get("proof_replayed",False)
                                  for r in subset),
            XOR_equations=sum(r.get("proof",{}).get("complete_xor_blocks",0)
                              for r in subset),
            implied_clauses=sum(r.get("proof",{}).get("added_clauses",0)
                                for r in subset),
            fallback=sum(r.get("route","").endswith("fallback") or
                         r.get("route","")=="replay_failed_closed"
                         for r in subset),
            preprocessing_s=round(sum(r.get("preprocessing_E2E_s",0)
                                      for r in subset),6))
    baseline=scores["race_original"]["PAR2_s"]
    for s in scores.values():
        s["delta_PAR2_vs_original_pct"]=round(
            100*(s["PAR2_s"]/baseline-1),4)
    save(ROOT/"report.json",dict(protocol=PROTO,total_trials=len(rows),
         scores=scores,not_blind=True,source_SHA_unchanged=True,
         LRAT=False,parent_X22=42591977333))
    print("X24_FINAL",json.dumps(scores,sort_keys=True),flush=True)

def xor_clauses(vs,rhs):
    out=[]
    for values in itertools.product((False,True),repeat=len(vs)):
        if (sum(values)&1)==rhs:continue
        out.append(tuple(-v if values[i] else v
                         for i,v in enumerate(vs)))
    return out

def selftest():
    need(BIN.is_file(),"native C++ not compiled")
    cases=[
      (4,xor_clauses((1,2,3),0)+xor_clauses((1,2,4),0),True),
      (3,xor_clauses((1,2,3),0)+xor_clauses((1,2,3),1),True),
      (4,xor_clauses((1,2,3,4),1),False),
      (3,xor_clauses((1,2,3),0)[:-1],False),
      (5,xor_clauses((1,2,3),0)+xor_clauses((3,4,5),1),False),
      (2,[(1,2),(-1,-2)],False),
      (2,[(1,2),(-1,-2),(1,-2),(-1,2)],True)]
    rng=random.Random(20261109)
    for n in range(2,6):
        for i in range(20):
            cs=[tuple(rng.choice((-1,1))*rng.randint(1,n)
                      for _ in range(rng.randint(1,4)))
                for _ in range(rng.randint(0,15))]
            cases.append((n,cs,False))
    with tempfile.TemporaryDirectory() as d:
        folder=pathlib.Path(d)
        for n,clauses,require_short in cases:
            src=folder/"original.cnf";cert=folder/"rows.cert"
            out=folder/"derived.cnf"
            if out.exists():out.unlink()
            src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            before=sha(src)
            call=subprocess.run([str(BIN),str(src),str(cert)],
                       capture_output=True,text=True)
            need(call.returncode==0,"native selftest: "+call.stderr)
            info=verify_certificate(src,cert,out)
            need(not require_short or info["derived_short_rows"]>=1,
                 "missed synthetic GF2 closure")
            _,transformed=x22.read_cnf(out) if out.exists() else (n,clauses)
            for bits in itertools.product((False,True),repeat=n):
                model=dict(enumerate(bits,1))
                need(x22.holds(clauses,model)==x22.holds(transformed,model),
                     "exhaustive CNF equivalence failed")
            need(sha(src)==before,"original CNF mutated")
    print("X24_SELFTEST_PASS",len(cases),
          "independent XOR-block replay, GF2 closure and exhaustive models",
          flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","freeze","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()

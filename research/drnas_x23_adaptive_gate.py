#!/usr/bin/env python3
"""DRNAS X23: cheap precommitted source-only gate before the X22 C++ helper.

X22 untouched: calls the exact same frozen X22 solver harness and source SHAs.
Previous X21 holdout reused. No new blind claim; no independent LRAT proof.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import time

import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_x23")
PROTO="DRNAS-X23-ADAPTIVE-CPP-SAMPLE-GATE-24SHA-6ARM-2REP-15S-v1"
ARMS=("kissat1","cadical1","race_original","race_quotient",
      "gate_liberal","gate_strict")
CAP=15.0
REPS=2
SHARDS=8
EXPECTED=24*REPS*len(ARMS)
SAMPLE_BYTES=131072

def need(condition,why):
    if not condition:
        raise RuntimeError("X23_FAIL_CLOSED "+str(why))

def save(path,data):
    x22.save(path,data)

def digest(path):
    return x22.digest(path)

def probe(path):
    """Inspect at most first and last 128 KiB, without changing source CNF.

    Incomplete lines, wrapped DIMACS clauses and nonnumeric content are ignored.
    False negatives merely skip reduction; all actual transformations are still
    proof replayed by frozen X22. No decision uses solver outcomes.
    """
    path=pathlib.Path(path)
    size=path.stat().st_size
    with path.open("rb") as stream:
        if size<=2*SAMPLE_BYTES:
            chunks=[stream.read()]
        else:
            front=stream.read(SAMPLE_BYTES)
            stream.seek(-SAMPLE_BYTES,2)
            back=stream.read(SAMPLE_BYTES)
            chunks=[front.rsplit(b"\n",1)[0],back.split(b"\n",1)[-1]]
            # For back retain all complete lines after the first partial line.
            chunks[1]=b"\n".join(back.split(b"\n")[1:])
    known=set()
    pairs=set()
    n=0;binary=0;duplicates=0;two_way=0;tauts=0
    for chunk in chunks:
        for line in chunk.splitlines():
            raw=line.strip()
            if not raw or raw[:1] in (b"c",b"p",b"%"):continue
            fields=raw.split()
            if len(fields)<2 or fields[-1]!=b"0":continue
            try: values=tuple(int(v) for v in fields[:-1])
            except ValueError:continue
            if not values or 0 in values:continue
            n+=1
            canonical=tuple(sorted(set(values)))
            if canonical in known:duplicates+=1
            known.add(canonical)
            if any(-v in canonical for v in canonical):tauts+=1
            if len(canonical)==2:
                binary+=1
                neg=tuple(sorted((-v for v in canonical)))
                if neg in pairs:two_way+=1
                pairs.add(canonical)
    density=binary/max(1,n)
    return dict(size_bytes=size,sampled_bytes=min(size,2*SAMPLE_BYTES),
                sample_clauses=n,binary_clauses=binary,
                binary_fraction=round(density,6),
                exact_duplicate_sample=duplicates,
                complementary_binary_pairs=two_way,
                tautology_sample=tauts)

def route(stats,policy):
    need(policy in ("liberal","strict"),"unknown policy")
    size=stats["size_bytes"]
    dup=stats["exact_duplicate_sample"]
    two=stats["complementary_binary_pairs"]
    density=stats["binary_fraction"]
    sample=stats["sample_clauses"]
    if policy=="strict":
        eligible=(size<=8*1024*1024 and
                  (two>=1 or dup>=2 or stats["tautology_sample"]>=2))
    else:
        eligible=(size<=20*1024*1024 and
                  (two>=1 or dup>=1 or stats["tautology_sample"]>=1 or
                   (sample>=64 and stats["binary_clauses"]>=16 and density>=0.10)))
    return "race_quotient" if eligible else "race_original"

def verify():
    source=x22.verify_frozen()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS)
         and m["expected_trials"]==EXPECTED and len(m["cases"])==24,
         "protocol or source count changed")
    need(m["code_sha256"]==digest(__file__) and
         m["x22_manifest_sha256"]==digest(x22.ROOT/"manifest.json"),
         "code or X22 manifest drift")
    need(m["x22_source_shas"]==[c["sha256"] for c in source["cases"]],
         "source roster changed")
    return m

def freeze():
    x22_manifest=x22.verify_frozen()
    ROOT.mkdir(exist_ok=True)
    m=dict(protocol=PROTO,arms=ARMS,expected_trials=EXPECTED,
           cap_s=CAP,shards=SHARDS,reps=REPS,
           cases=[{k:c[k] for k in ("sha256","gbd","year","filename")}
                  for c in x22_manifest["cases"]],
           x22_source_shas=[c["sha256"] for c in x22_manifest["cases"]],
           x22_manifest_sha256=digest(x22.ROOT/"manifest.json"),
           code_sha256=digest(__file__),
           source_run_id=42591977333,source_SHA_unchanged=True,
           former_X21_holdout_reused_not_blind=True,
           precommitted_rules={"sample_bytes_each_end":SAMPLE_BYTES,
                  "strict":"<=8 MiB and (>=1 complementary binary pair OR >=2 exact duplicates OR >=2 tautologies)",
                  "liberal":"<=20 MiB and (one direct signal OR >=16 binary and >=10% sample binary fraction)",
                  "time_budget_s":CAP},
           no_auto_promotion=True,UNSAT_independent_LRAT=False,
           maximum_logical_cpus=2,
           benchmark_comparison="same X22 runner and original SHA; 2 CPU wall E2E PAR2")
    save(ROOT/"manifest.json",m)
    verify()
    print("X23_FROZEN",json.dumps(dict(sources=len(m["cases"]),trials=EXPECTED,
        algorithms=ARMS),sort_keys=True),flush=True)

def trial(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid trial")
    start=time.perf_counter()
    cpu_before=x22.child_cpu()
    sampled={};selected=arm;probe_s=0.0
    if arm in ("gate_liberal","gate_strict"):
        src=x22.ROOT/"cases"/c["filename"]
        need(digest(src)==c["sha256"],"source original SHA altered")
        sampled=probe(src)
        selected=route(sampled,arm.removeprefix("gate_"))
        probe_s=time.perf_counter()-start
    need(selected in x22.ARMS,"unexpected X22 arm")
    # Charge probe to the strict original E2E 15s wall budget.
    remaining=CAP-(time.perf_counter()-start)
    if remaining<=0.02:
        result=dict(status="TIMEOUT",winner=None,
            SAT_original_witness_verified=False,UNSAT_independent_LRAT=False,
            reducer={},aliases_replayed=0,second_solver_launched=False)
    else:
        previous=x22.CAP
        try:
            x22.CAP=remaining
            result=x22.trial(c,rep,selected)
        finally:
            x22.CAP=previous
    duration=time.perf_counter()-start
    status=result["status"] if duration<=CAP else "TIMEOUT"
    row=dict(protocol=PROTO,arm=arm,route=selected,
        original_sha256=c["sha256"],gbd=c["gbd"],rep=rep,
        seed=x22.seed(c,rep),status=status,
        winner=result.get("winner") if status!="TIMEOUT" else None,
        SAT_original_witness_verified=(status=="SAT" and
                result.get("SAT_original_witness_verified",False)),
        UNSAT_independent_LRAT=False,
        reducer=result.get("reducer",{}),
        aliases_replayed=result.get("aliases_replayed",0),
        second_solver_launched=result.get("second_solver_launched",False),
        sample=sampled,sample_gate_s=round(probe_s,6),
        E2E_s=round(duration,6),child_cpu_s=round(x22.child_cpu()-cpu_before,6),
        cap_s=CAP,
        provisional_PAR2_s=round(duration if status in ("SAT","UNSAT") else 2*CAP,6))
    return row

def shard(index):
    m=verify()
    need(0<=index<SHARDS,"shard index")
    rows=[]
    for c in m["cases"][index::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(x22.seed(c,rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,rep,arm)
                rows.append(row)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X23_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==36,"unexpected shard cardinality")
    print("X23_SHARD_PASS",index,len(rows),flush=True)

def audit():
    m=verify()
    allrows=[]
    for i in range(SHARDS):
        part=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(part)==36,"incomplete shard "+str(i))
        allrows.extend(part)
    need(len(allrows)==EXPECTED,"incorrect number of measurements")
    unique=set()
    grouped=collections.defaultdict(list)
    for r in allrows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in unique and r["protocol"]==PROTO and
            r["arm"] in ARMS and r["cap_s"]==CAP,"key or protocol mismatch")
        unique.add(key)
        grouped[r["original_sha256"]].append(r)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"unverified SAT model")
    need(len(unique)==EXPECTED,"coverage mismatch")
    agreement={}
    for src, rows in grouped.items():
        statuses={r["status"] for r in rows if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory SAT verdicts")
        originals={r["arm"] for r in rows
                   if r["arm"] in ("kissat1","cadical1")
                   and r["status"]=="UNSAT"}
        agreement[src]=(len(originals)==2)
    scores={}
    for arm in ARMS:
        subset=[r for r in allrows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                 (r["status"]=="UNSAT" and agreement[r["original_sha256"]])]
        par2=sum(r["E2E_s"] if r in accepted else 2*CAP for r in subset)
        scores[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
             verified_SAT=sum(r["status"]=="SAT" for r in accepted),
             UNSAT_cross_solver_agreement_no_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
             unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted for r in subset),
             PAR2_s=round(par2,5),
             child_CPU_s=round(sum(r["child_cpu_s"] for r in subset),5),
             fallback_to_original=sum(r["route"]=="race_original" for r in subset
                if r["arm"].startswith("gate_")),
             reduction_selected=sum(r["route"]=="race_quotient" for r in subset
                if r["arm"].startswith("gate_")),
             aliased_variables=sum(r["aliases_replayed"] for r in subset),
             mean_sample_gate_s=round(sum(r["sample_gate_s"] for r in subset)/len(subset),6))
    baseline=scores["race_original"]["PAR2_s"]
    for score in scores.values():
        score["PAR2_change_vs_immediate_race_pct"]=round(
            100*(score["PAR2_s"]/baseline-1),3) if baseline else None
    report=dict(protocol=PROTO,trial_count=EXPECTED,source_count=24,
                x22_reference_run_id=42591977333,
                not_blind=True,independent_UNSAT_LRAT=False,
                strict_2cpu_E2E=True,score=scores,agreement=agreement,
                all_shards_complete=True,no_auto_promotion=True)
    save(ROOT/"report.json",report)
    print("X23_FINAL",json.dumps(scores,sort_keys=True),flush=True)

def selftest():
    examples=[
       ("equivalence","p cnf 2 2\n-1 2 0\n1 -2 0\n",True),
       ("negated","p cnf 2 2\n1 2 0\n-1 -2 0\n",True),
       ("duplicate","p cnf 2 3\n1 2 0\n1 2 0\n1 2 0\n",True),
       ("empty","p cnf 2 1\n1 2 0\n",False),
       ("wide","p cnf 3 1\n1 2 3 0\n",False)]
    import tempfile
    checks=0
    with tempfile.TemporaryDirectory() as tmp:
        p=pathlib.Path(tmp)/"test.cnf"
        for name,content,promising in examples:
            p.write_text(content)
            before=digest(p)
            feat=probe(p)
            yes=(feat["complementary_binary_pairs"]>0 or
                 feat["exact_duplicate_sample"]>0)
            need(yes==promising,"probe selftest "+name)
            need(digest(p)==before,"probe mutated source")
            checks+=1
        # Long input exercises exact first/last windows and no partial lines.
        p.write_text("p cnf 3 60000\n"+"1 2 3 0\n"*60000)
        feat=probe(p)
        need(feat["sampled_bytes"]==2*SAMPLE_BYTES and feat["sample_clauses"]>0,
            "bounded scan")
        checks+=1
    print("X23_SELFTEST_PASS",checks,"deterministic bounded gate tests",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()

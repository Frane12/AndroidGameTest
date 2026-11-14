#!/usr/bin/env python3
"""DELTA4: 60 SHA-frozen diverse original SAT2024 CNFs, cap 10s, 2x, 7 arms.

No accuracy inferred from timeouts. Every SAT model checked on original CNF,
every credited UNSAT has independently checked original-CNF DRAT.
All emitted bridge lemmas independently rechecked against two ORIGINAL parents.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import sys

sys.path.insert(0,str(Path("research").resolve()))
sys.path.insert(0,str(Path("tests").resolve()))
from drnas_deltacoop2 import paired as P
from drnas_deltacoop4.collect import load, N, SHARDS
from test_drnas_deltacoop3 import validate_lemma, canon
import drnas_x55_cpu_real36 as B

CAP=10.0
REPS=2
ARMS=("OFF","BRIDGE","D4-SHADOW","D4-STRUCT","D4","KISSAT","CADICAL")
BINS={"OFF":"build/drnas-deltacoop3",
      "BRIDGE":"build/drnas-deltacoop3",
      "D4-SHADOW":"build/drnas-deltacoop4",
      "D4-STRUCT":"build/drnas-deltacoop4",
      "D4":"build/drnas-deltacoop4",
      "KISSAT":"cross/x59/build/kissat",
      "CADICAL":"cross/x59/build/cadical"}
P.ARMS=ARMS;P.BINS=BINS;P.CAP=CAP;P.REPS=REPS;P.SHARDS=SHARDS
sample_parent=P.sample

def sample(src,arm,rep,cap,rawdir):
    row=sample_parent(src,arm,rep,cap,rawdir)
    row["original_source_resolvents_checked"]=0
    row["bridge_proof_emissions"]=0
    if arm not in ("KISSAT","CADICAL","OFF"):
        stderr=(rawdir/f"{src['id']}-{rep}-{arm}.stderr").read_text()
        events=[json.loads(l.split(" ",1)[1]) for l in stderr.splitlines()
                if l.startswith("DELTA3_LEMMA ") or l.startswith("DELTA4_LEMMA ")]
        st=row["stats"].get("DELTA2_JOIN",{})
        if st:
            if arm=="D4-SHADOW":
                assert st.get("bridge_injected",0)==0 and not events,("SHADOW_INJECTED",src["id"])
            if arm in ("D4","D4-STRUCT","BRIDGE"):
                assert len(events)<=st.get("bridge_injected",0),("INCONSISTENT_LOG",arm,src["id"])
            if events:
                _,cs=B.parse_cnf(Path(src["path"]).read_bytes())
                source={canon(c) for c in cs}
                for event in events:validate_lemma(event,source)
            row["original_source_resolvents_checked"]=len(events)
            row["bridge_proof_emissions"]=st.get("bridge_injected",0)
    P.emit("DELTA4_TRIAL",{k:v for k,v in row.items() if k!="stats"})
    return row

def shard(index):
    if not 0<=index<SHARDS:raise ValueError("shard index")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sources,digest=load()
    selected=[s for s in sources if s["shard"]==index]
    assert len(selected)==N//SHARDS
    folder=Path(f"delta4_shards/{index}")
    folder.mkdir(parents=True,exist_ok=False)
    P.save(folder/"manifest.json",
           {"source_manifest_sha256":digest,"binary_sha256":P.hashes(),
            "shard":index,"sources":[s["sha256"] for s in selected],
            "arms":ARMS,"cap_s":CAP,"reps":REPS,"one_cpu":sorted(os.sched_getaffinity(0)),
            "retrospective":True,"blind_holdout":False,"promotion":False,
            "policy":"general join-reduction, nonaffine-window ablation, original-source short RUP"})
    rows=[]
    with (folder/"trials.jsonl").open("w") as f:
        for s in selected:
            for rep in range(REPS):
                order=list(ARMS);random.Random(int(s["sha256"][:16],16)+rep*199).shuffle(order)
                for arm in order:
                    row=sample(s,arm,rep,CAP,folder/"raw")
                    rows.append(row)
                    f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
    assert len(rows)==N//SHARDS*REPS*len(ARMS)
    P.emit("DELTA4_SHARD_PASS",
           {"shard":index,"sources":len(selected),"trials":len(rows),
            "injected":sum(r["bridge_proof_emissions"] for r in rows if r["arm"]=="D4"),
            "d4_verified":sum(r["verified"] for r in rows if r["arm"]=="D4")})

def aggregate():
    sources,digest=load()
    rows=[];manifests=[]
    for index in range(SHARDS):
        p=Path(f"delta4_downloads/delta4-shard-{index}/delta4_shards/{index}")
        manifests.append(json.loads((p/"manifest.json").read_text()))
        rows.extend(json.loads(l) for l in (p/"trials.jsonl").read_text().splitlines())
    expected={(s["sha256"],rep,arm) for s in sources for rep in range(REPS) for arm in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in rows]
    assert len(rows)==N*REPS*len(ARMS)==840
    assert len(set(actual))==len(actual) and set(actual)==expected
    first=manifests[0]
    for m in manifests:
        assert m["source_manifest_sha256"]==digest
        assert m["binary_sha256"]==first["binary_sha256"]
        assert list(m["arms"])==list(ARMS) and m["cap_s"]==CAP and m["reps"]==REPS
        assert len(m["one_cpu"])==1 and m["retrospective"] and not m["promotion"]
    h=first["binary_sha256"]
    assert h["OFF"]==h["BRIDGE"]
    assert h["D4-SHADOW"]==h["D4-STRUCT"]==h["D4"]!=h["OFF"]
    outcomes=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:
            outcomes[r["sha256"]].add(r["status"])
    assert all(len(v)<=1 for v in outcomes.values()),"CONTRADICTORY_VERIFIED_VERDICTS"
    fields={}
    keys=("bridge_injected","bridge_witnesses","bridge_active_candidates",
          "d4_reduction_pairs","d4_nonaffine_pairs","d4_scan_calls",
          "d4_structural_calls","d4_injections","d4_large_formula",
          "d4_reservoir_replacements","d4_input_clauses",
          "nonlinear_tuple_events","analysis_ms")
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        fields[arm]={"trials":len(rr),"verified":sum(r["verified"] for r in rr),
                     "sat_verified":sum(r["status"]=="SAT_VERIFIED" for r in rr),
                     "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" for r in rr),
                     "par2_verified_s":round(sum(r["PAR2_verified_s"] for r in rr),6),
                     "original_source_resolvents_checked":
                        sum(r["original_source_resolvents_checked"] for r in rr),
                     "distinct_injected_sources":len({r["sha256"] for r in rr
                                                      if r["bridge_proof_emissions"]>0}),
                     "math":{k:sum(r["stats"].get("DELTA2_JOIN",{}).get(k,0) for r in rr)
                             for k in keys}}
    by={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    rng=random.Random(440421)
    compare={}
    for ref in ("OFF","BRIDGE","D4-SHADOW","D4-STRUCT","KISSAT","CADICAL"):
        gains=[]
        for _ in range(2000):
            draw=[rng.choice(sources)["sha256"] for _ in sources]
            old=sum(by[(s,rep,ref)]["PAR2_verified_s"] for s in draw for rep in range(REPS))
            new=sum(by[(s,rep,"D4")]["PAR2_verified_s"] for s in draw for rep in range(REPS))
            gains.append(100*(old-new)/old if old else 0)
        gains.sort()
        x=fields[ref]["par2_verified_s"];y=fields["D4"]["par2_verified_s"]
        compare["D4_vs_"+ref]={"gain_pct":round(100*(x-y)/x,5),
                              "source_bootstrap_ci95_pct":[round(gains[49],5),round(gains[1949],5)],
                              "verified_solved_delta":fields["D4"]["verified"]-fields[ref]["verified"]}
    # Descriptive runtime strata only, NOT used to select or score sources.
    medium_ids=sorted({s["sha256"] for s in sources
       if any((r["status"]=="SAT_VERIFIED" or r["status"]=="UNSAT_CERTIFIED")
              and 0.15<=r["wall_e2e_s"]<=CAP
              for r in rows if r["sha256"]==s["sha256"] and r["arm"]=="KISSAT")})
    report={"status":"COMPLETE","sources":N,"source_families":len({s["family"] for s in sources}),
            "attempts":len(rows),"reps":REPS,"cap_s":CAP,"one_cpu_per_solver":True,
            "original_manifest_sha256":digest,"binary_sha256":h,
            "retrospective":True,"blind_holdout":False,"promotion":False,
            "novel_mathematics_proven":False,
            "medium_runtime_stratum_count_posthoc":len(medium_ids),
            "medium_runtime_definition":"Kissat solved (verified) in 0.15s to 10s; descriptive only",
            "fields":fields,"comparisons":compare}
    P.save("delta4_final/report.json",report)
    P.save("delta4_final/trials.json",rows)
    P.emit("DELTA4_FINAL",report)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("stage",choices=("shard","aggregate"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.stage=="shard":shard(args.shard)
    else:aggregate()

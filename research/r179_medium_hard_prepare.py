#!/usr/bin/env python3
"""R179 prospective medium-hard mixed CNF SOURCE PREPARATION ONLY.
1. Precommit SHA-256 of 360 deterministic SAT/UNSAT 3-regular Tseitin-plus-CNF
   instances and 4 clearly marked KNOWN original mixed CNFs.
2. Run ONLY unchanged CaDiCaL 2.1.0 in a two-stage timing calibration.
3. Freeze up to 100 eligible (0.1--30s reference clock) originals + synthetic
   as development / validation / sealed DRNAS holdout BEFORE DRNAS evaluation.

Generated instances are never described as external, industrial or world ranking.
The sealed DRNAS holdout is conditioned on reference timings, NOT a completely
untouched distributional holdout. No current R177 variant is run by this script.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,os,pathlib,random,statistics,subprocess,time
from typing import Dict,List,Tuple

ROOT=pathlib.Path("r179")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-R179-MIXED-MEDIUM-SAT-UNSAT-REFERENCE-CALIBRATION-v1"
SEED=17920261106
SIZES=(24,30,36,42,50,60,72,84,100,120,148,184)
PER_SIZE=30
GENERATED=len(SIZES)*PER_SIZE
SHARDS=12
PRESCREEN_S=3.0
CONFIRM_S=30.0
REFERENCE_MIN_S=0.10
TARGET=100
REAL_IDS=("3e912cd2a499b8f956246b866e2f9f64",
          "99718c1729a8de3347a9946f1836421d",
          "b76b9699c2deb74dd9b4a99a05179acd",
          "c0e828fb967fc4f0935cf06c6a6b1055")

def need(ok,msg):
    if not ok:raise RuntimeError("R179_FAIL_CLOSED "+str(msg))
def hashbytes(data):return hashlib.sha256(data).hexdigest()
def sha(path):return hashbytes(pathlib.Path(path).read_bytes())
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def clause(values):
    xs=tuple(sorted(values,key=lambda z:(abs(z),z)))
    need(len(xs)==len({abs(z) for z in xs}),"non-simple CNF clause")
    return xs
def make_graph(rng,vertices):
    # A random simple connected 3-regular graph by stub pairing.
    # Each edge variable occurs in precisely two source-certified XOR3 rows.
    for attempt in range(800):
        stubs=[v for v in range(vertices) for _ in range(3)]
        rng.shuffle(stubs)
        edges=set()
        valid=True
        for p in range(0,len(stubs),2):
            a,b=stubs[p:p+2]
            if a==b or (min(a,b),max(a,b)) in edges:
                valid=False;break
            edges.add((min(a,b),max(a,b)))
        if not valid:continue
        adj=[set() for _ in range(vertices)]
        for a,b in edges:adj[a].add(b);adj[b].add(a)
        seen={0};stack=[0]
        while stack:
            for v in adj[stack.pop()]:
                if v not in seen:seen.add(v);stack.append(v)
        if len(seen)==vertices:
            return sorted(edges)
    raise RuntimeError("R179 connected cubic graph generator exhausted")

def generate(index):
    need(0<=index<GENERATED,"candidate index")
    size_bucket=index//PER_SIZE
    vertices=SIZES[size_bucket]
    sat=index%2==0
    rng=random.Random(SEED+index*1000003)
    edges=make_graph(rng,vertices)
    m=len(edges)
    need(m==3*vertices//2,"wrong cubic graph edge count")
    witness=[0]+[rng.randrange(2) for _ in range(m)]
    # Residual variables participate in ordinary AND/OR clauses, not XOR rows.
    ext=max(12,vertices//2)
    witness.extend(rng.randrange(2) for _ in range(ext))
    inc=[[] for _ in range(vertices)]
    for k,(a,b) in enumerate(edges,1):inc[a].append(k);inc[b].append(k)
    need(all(len(v)==3 for v in inc),"each vertex needs XOR width 3")
    flipped=rng.randrange(vertices)
    rhs=[]
    clauses=set()
    for v,variables in enumerate(inc):
        variables=tuple(sorted(variables))
        r=0
        for var in variables:r^=witness[var]
        if not sat and v==flipped:r^=1
        rhs.append(r)
        for bits in itertools.product((0,1),repeat=3):
            if (bits[0]^bits[1]^bits[2])==r:continue
            clauses.add(clause([-var if b else var
                                for var,b in zip(variables,bits)]))
    # All source XOR rows combined prove UNSAT iff one vertex RHS is flipped.
    need((sum(rhs)%2)==int(not sat),"global GF2 parity certificate wrong")
    residual_vars=list(range(m+1,m+ext+1))
    density=(2.0,2.8,3.6,4.4)[index%4]
    extra_target=int(density*(m+ext))
    ntries=0
    while len(clauses)<4*vertices+extra_target and ntries<extra_target*60:
        ntries+=1
        if ntries%4==0:
            vars_=rng.sample(range(1,m+ext+1),3)
        elif ntries%3==0:
            vars_=rng.sample(range(1,m+1),2)+[rng.choice(residual_vars)]
        else:
            vars_=[rng.randrange(1,m+1)]+rng.sample(residual_vars,2)
        signs=[rng.getrandbits(1) for _ in vars_]
        # SAT instances retain an independently checkable planted witness.
        # UNSAT instances are already inconsistent solely from source XOR rows.
        if sat and not any(signs[j]==witness[var] for j,var in enumerate(vars_)):
            k=rng.randrange(3)
            signs[k]=witness[vars_[k]]
        clauses.add(clause([var if bit else -var
                            for var,bit in zip(vars_,signs)]))
    need(ntries<extra_target*60,"residual mixed CNF quota missing")
    ordered=sorted(clauses,key=lambda c:(len(c),c))
    if sat:
        need(all(any((lit>0)==bool(witness[abs(lit)]) for lit in c)
                 for c in ordered),"planted SAT source model invalid")
    # Independent mathematical correctness certificate for generated UNSAT:
    # each edge appears in exactly two XORs, and XOR(all RHS) = 1.
    appearances=collections.Counter(x for row in inc for x in row)
    need(len(appearances)==m and all(v==2 for v in appearances.values()),
         "unbalanced graph XOR certificate")
    body=(f"c R179 deterministic connected cubic Tseitin mixed CNF index={index}"
          f" expected={'SAT' if sat else 'UNSAT'}\n"
          f"p cnf {m+ext} {len(ordered)}\n"+
          "".join(" ".join(map(str,c))+" 0\n" for c in ordered)).encode()
    cert={"index":index,"expected":"SAT" if sat else "UNSAT",
          "graph_vertices":vertices,"source_xor_rows":vertices,
          "xor_edges":edges,"xor_rhs":rhs,
          "xor_rhs_parity":sum(rhs)%2,
          "witness":witness[1:] if sat else None,
          "residual_count":len(ordered)-4*vertices,
          "cnf_variables":m+ext,"cnf_clauses":len(ordered),
          "source_sha256":hashbytes(body)}
    return body,cert

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for index in range(GENERATED):
        raw,proof=generate(index)
        digest=hashbytes(raw)
        case_id="s"+digest[:31]
        (FROZEN/(case_id+".cnf")).write_bytes(raw)
        save(FROZEN/(case_id+".proof.json"),proof)
        cases.append({"id":case_id,"sha256":digest,"origin":"generated_tseitin_mixed",
             "class":proof["expected"],"source_only_proof":"parity_sum_contradiction"
                 if proof["expected"]=="UNSAT" else "planted_original_cnf_witness",
             "cohort":"mixed_residual","family":"cubic_tseitin_with_crossing_and_or",
             "nominal_size":proof["graph_vertices"],"index":index})
    # Historical controls are not allowed to count as new/unseen cases.
    source_root=ROOT/"prior"/"frozen"
    old=load(source_root/"manifest.json")
    prior={x["id"]:x for x in old["cases"]}
    for id in REAL_IDS:
        need(id in prior and prior[id]["cohort"]=="mixed_residual",
             "prior mixed original source missing")
        src=source_root/(id+".cnf")
        need(sha(src)==prior[id]["sha256"],"historical raw CNF SHA mismatch")
        (FROZEN/(id+".cnf")).write_bytes(src.read_bytes())
        cases.append({"id":id,"sha256":prior[id]["sha256"],
          "origin":"KNOWN_external_original","class":"UNKNOWN",
          "source_only_proof":"external original SHA provenance only",
          "cohort":"mixed_residual","family":prior[id].get("family","unknown"),
          "nominal_size":None,"index":None})
    cases.sort(key=lambda x:x["id"])
    need(len(cases)==GENERATED+4
         and len(set(c["sha256"] for c in cases))==len(cases),
         "frozen pool contains duplicates")
    manifest={"protocol":PROTO,"status":"SOURCE_FROZEN_PRE_REFERENCE_TIMING",
      "source_count":len(cases),"generated":GENERATED,
      "known_external_originals":4,"baseline_only":True,
      "synthetic_not_external":True,"not_blind_to_reference_timing":True,
      "not_blind_to_earlier_four_originals":True,
      "no_DRNAS_solver_runs_in_preparation":True,
      "calibration_only":"CaDiCaL-2.1.0 baseline",
      "threshold_s":[REFERENCE_MIN_S,CONFIRM_S],
      "selection_is_reference_calibrated_not_random_sample":True,
      "original_source_archive_run":42112755104,
      "cases":cases}
    save(FROZEN/"manifest.json",manifest)
    verify()
    print("R179_SOURCE_FROZEN_PASS",json.dumps({
        "count":len(cases),"generated":GENERATED,"real_prior":4,
        "sat":sum(x["class"]=="SAT" for x in cases),
        "unsat":sum(x["class"]=="UNSAT" for x in cases),
        "manifest_sha256":sha(FROZEN/"manifest.json")},sort_keys=True),flush=True)

def verify():
    m=load(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and m["source_count"]==GENERATED+4,
         "manifest protocol/count mismatch")
    need(len({x["sha256"] for x in m["cases"]})==len(m["cases"]),
         "repeated CNF source SHA")
    for c in m["cases"]:
        path=FROZEN/(c["id"]+".cnf")
        need(sha(path)==c["sha256"],"source SHA changed: "+c["id"])
        if c["origin"]=="generated_tseitin_mixed":
            b,proof=generate(c["index"])
            need(hashbytes(b)==c["sha256"]
                 and proof==load(FROZEN/(c["id"]+".proof.json")),
                 "generative source and mathematical certificate drift")
    return m["cases"]

def timed_call(binary,src,cap):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(src.resolve())],
              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
              timeout=cap)
        t=time.perf_counter()-start
        need(p.returncode in (10,20),"CaDiCaL unexpected exit "+
             str(p.returncode)+" "+p.stderr[-250:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        if t>=cap:status="TIMEOUT"
        return {"status":status,"elapsed_s":round(min(t,cap),6)}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","elapsed_s":round(cap,6)}

def calibration_shard(index,binary):
    need(0<=index<SHARDS,"shard index wrong")
    cases=verify()
    pin=load(ROOT/"baseline-pin.json")
    need(sha(binary)==pin["cadical_binary_sha256"],
         "CaDiCaL baseline binary SHA changed")
    need(sha(FROZEN/"manifest.json")==pin["manifest_sha256"],
         "baseline manifest changed")
    if hasattr(os,"sched_getaffinity"):
        cpus=os.sched_getaffinity(0)
        if cpus:os.sched_setaffinity(0,{min(cpus)})
    rows=[]
    for j,c in enumerate(cases):
        if j%SHARDS!=index:continue
        src=FROZEN/(c["id"]+".cnf")
        screen=timed_call(binary,src,PRESCREEN_S)
        expected=c["class"]
        if expected!="UNKNOWN" and screen["status"]!="TIMEOUT":
            need(screen["status"]==expected,
                 "baseline contradicts independent SAT/UNSAT construction")
        confirmations=[]
        if screen["status"]=="TIMEOUT" or screen["elapsed_s"]>=0.07:
            for rep in range(2):
                x=timed_call(binary,src,CONFIRM_S)
                if expected!="UNKNOWN" and x["status"]!="TIMEOUT":
                    need(x["status"]==expected,
                         "baseline contradicts frozen mathematical proof")
                confirmations.append(x)
        selected=(
          len(confirmations)==2
          and confirmations[0]["status"]!="TIMEOUT"
          and confirmations[1]["status"]!="TIMEOUT"
          and confirmations[0]["status"]==confirmations[1]["status"]
          and REFERENCE_MIN_S<=statistics.median(
              x["elapsed_s"] for x in confirmations)<=CONFIRM_S
        )
        median=(round(statistics.median(x["elapsed_s"] for x in confirmations),6)
                if len(confirmations)==2 else None)
        row={"id":c["id"],"sha256":c["sha256"],"origin":c["origin"],
           "class":c["class"],"nominal_size":c["nominal_size"],
           "screen":screen,"confirmations":confirmations,
           "reference_median_s":median,"reference_eligible":selected,
           "scope":"REFERENCE_ONLY_NO_DRNAS_EXECUTED"}
        rows.append(row)
        save(ROOT/f"shard-{index}.json",rows)
        print("R179_BASELINE_CASE",json.dumps({k:row[k] for k in
           ("id","origin","class","nominal_size","reference_median_s",
            "reference_eligible")},sort_keys=True),flush=True)
    need(len(rows)==len(cases[index::SHARDS]),
         "baseline shard incomplete")
    print("R179_BASELINE_SHARD_PASS",index,len(rows),flush=True)

def band(v):
    if v<1.0:return "0.1-1s"
    if v<10.0:return "1-10s"
    return "10-30s"

def finalize():
    cases=verify()
    records=[]
    for k in range(SHARDS):
        rows=load(ROOT/f"shard-{k}.json")
        need(len(rows)==len(cases[k::SHARDS]),"baseline shard incomplete")
        records.extend(rows)
    need(len(records)==len(cases),"baseline calibration missing sources")
    lookup={x["sha256"]:x for x in cases}
    for r in records:
        need(r["sha256"] in lookup and r["id"]==lookup[r["sha256"]]["id"],
             "source identity drift on audit")
        need(r["scope"]=="REFERENCE_ONLY_NO_DRNAS_EXECUTED",
             "attempt to include DRNAS results in calibration")
    eligible=[r for r in records if r["reference_eligible"]]
    # Stratify by expected truth value and CaDiCaL reference bands.
    # Keep new generated cases separate from 4 previously seen controls.
    pool=[x for x in eligible if x["origin"]=="generated_tseitin_mixed"]
    controls=[x for x in eligible if x["origin"]=="KNOWN_external_original"]
    strata=collections.defaultdict(list)
    for row in pool:
        strata[(row["class"],band(row["reference_median_s"]))].append(row)
    for group in strata.values():group.sort(key=lambda x:x["sha256"])
    quotas={"SAT":50,"UNSAT":50}
    chosen=[]
    # Balanced by SAT/UNSAT and as even as possible over reference bands.
    for truth,quota in quotas.items():
        buckets=[strata[(truth,b)] for b in ("0.1-1s","1-10s","10-30s")]
        for b in buckets[:]:
            take=min(quota//3,len(b))
            chosen.extend(b[:take]);del b[:take]
        remaining=quota-sum(x["class"]==truth for x in chosen)
        rest=sorted((r for g in buckets for r in g),
                    key=lambda x:(x["reference_median_s"],x["sha256"]))
        chosen.extend(rest[:remaining])
    chosen=sorted(chosen,key=lambda r:r["sha256"])
    need(len({x["sha256"] for x in chosen})==len(chosen),"selection duplicates")
    # If fewer than 100 reference-calibrated cases exist, report a shortfall,
    # never fill missing slots with too-easy/timeout cases.
    groups=collections.defaultdict(list)
    for r in chosen:
        groups[(r["class"],band(r["reference_median_s"]))].append(r)
    partitions=[]
    for key,items in sorted(groups.items()):
        sorted_items=sorted(items,key=lambda x:x["sha256"])
        for j,r in enumerate(sorted_items):
            position=j%10
            partition="development" if position<7 else (
                "validation" if position<9 else "sealed_reference_calibrated_holdout")
            partitions.append({**r,"split":partition,
                "reference_band":band(r["reference_median_s"])})
    partitions.sort(key=lambda x:x["sha256"])
    manifest={
       "protocol":PROTO,
       "status":"REFERENCE_ONLY_SELECTION_FROZEN_NO_DRNAS_RUNS",
       "selection_target":TARGET,"selected_count":len(partitions),
       "selection_shortfall":TARGET-len(partitions),
       "target_reached":len(partitions)==TARGET,
       "calibrated_eligible_generated":len(pool),
       "calibrated_eligible_known_originals":len(controls),
       "known_originals_not_eligible_for_unseen_holdout":True,
       "source_candidates":len(cases),
       "reference_only_no_DRNAS_run":True,
       "reference_timing_conditioned_not_distribution_blind":True,
       "UNSAT_generated_parity_certificate":True,
       "SAT_generated_planted_witness":True,
       "threshold_seconds":[REFERENCE_MIN_S,CONFIRM_S],
       "source_manifest_sha256":sha(FROZEN/"manifest.json"),
       "baseline_pin_sha256":sha(ROOT/"baseline-pin.json"),
       "split_counts":dict(collections.Counter(x["split"] for x in partitions)),
       "class_counts":dict(collections.Counter(x["class"] for x in partitions)),
       "band_counts":dict(collections.Counter(x["reference_band"] for x in partitions)),
       "selected":partitions}
    save(ROOT/"r179-selected-freeze.json",manifest)
    counts=collections.Counter((x["class"],band(x["reference_median_s"]))
                                for x in eligible)
    report={"status":"R179_REFERENCE_CALIBRATION_AUDIT_PASS",
        "candidate_count":len(cases),"eligible_total":len(eligible),
        "eligible_generated":len(pool),
        "eligible_known_originals":len(controls),
        "eligible_by_class_band":{f"{a}/{b}":n
             for (a,b),n in sorted(counts.items())},
        "selected":len(partitions),"shortfall":TARGET-len(partitions),
        "split_counts":manifest["split_counts"],
        "frozen_sha256":sha(ROOT/"r179-selected-freeze.json"),
        "no_DRNAS_modes_benchmarked":True,
        "caveat":"CaDiCaL-only calibrated sources: not untouched holdout; generated Tseitin instances not external SAT Competition problems. Four known originals explicitly excluded from unseen selection."}
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R179 SAT/UNSAT mixed CNF source preparation\n\n")
        f.write("CaDiCaL-only calibration, **no DRNAS benchmark run**.\n\n")
        f.write(f"- Candidates: {len(cases)} (generated {GENERATED}, reused originals 4)\n")
        f.write(f"- Eligible generated 0.1-30s: {len(pool)}\n")
        f.write(f"- Selected for R179: {len(partitions)}/{TARGET}; shortfall {TARGET-len(partitions)}\n")
        f.write(f"- Partition sizes: {manifest['split_counts']}\n")
        f.write(f"- Class: {manifest['class_counts']}; timing bands: {manifest['band_counts']}\n")
        f.write("\nPreparation alone is not evidence of DRNAS speedup or a world record.\n")
    print("R179_CALIBRATION_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","shard","finalize"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--baseline",default="r179/cadical")
    a=p.parse_args()
    if a.action=="freeze":freeze()
    elif a.action=="verify":
        print("R179_SOURCE_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":calibration_shard(a.shard,pathlib.Path(a.baseline))
    else:finalize()

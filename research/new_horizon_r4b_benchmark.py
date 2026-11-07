#!/usr/bin/env python3
"""DRNAS New Horizon SAT R4b: original SHA-paired single-pass ablation.

R4 already inspected 194 source formulas; R4b adds 32 deterministic
prospective examples from known generators. None is a blind external holdout.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random
import new_horizon_r4 as r4
import new_horizon_r4b as r4b
import new_horizon_r2_benchmark as r2gen
import new_horizon_r3_benchmark as r3gen
import new_horizon_benchmark as xor_gen

ROOT=pathlib.Path("new_horizon_r4b")
FROZEN=ROOT/"frozen"
SOURCE=ROOT/"source/new_horizon_r4/frozen"
SOURCE_SHA="a827987192ffb6e02d9428ede63e036a7a9362aceb115720dff6bafdb4340026"
PROTO="NEW_HORIZON_R4B_SINGLE_PASS_PROSPECTIVE_20261107_v1"
PREVIOUS=194
NEW_PER_FAMILY=8
FAMILIES=("pure_xor","small_2sat","general_unknown","deceptive_suffix")
TOTAL=PREVIOUS+len(FAMILIES)*NEW_PER_FAMILY
MODES=("clean","r4","pure_only","r4b")
REPS=2
SHARDS=8

def need(x,msg):
    if not x:raise AssertionError("R4B_BENCH_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,value):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def cnf(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)

def new_example(family,i):
    if family=="pure_xor":
        return xor_gen.generated_pure(700+i)
    if family=="small_2sat":
        return r2gen.generated_two(900+i)
    if family=="general_unknown":
        return r3gen.generate_unknown(20+i)
    # A full source is NOT 2SAT even though first 90 source clauses are.
    n=96+i
    clauses=[(1,)]+[(-v,v+1) for v in range(1,90)]
    clauses.extend([(1,2,3),(4+i,5+i,6+i)])
    return n,clauses,"SAT"

def selftest():
    r4b.selftest()
    for family in FAMILIES:
        for i in range(NEW_PER_FAMILY):
            n,clauses,expected=new_example(family,i)
            need(n>0 and clauses,"new generator yielded no formula")
            if family=="pure_xor":
                exact,rows,_=r4b.pure.detect_exact(clauses)
                need(exact and r4b.pure.gaussian(rows)["status"]==expected,
                     "pure exact generated source result")
            elif family=="small_2sat":
                need(r4b.r2.is_2cnf(clauses) and
                     r4b.r2.solve_2sat(n,clauses)["status"]==expected,
                     "2SAT generated source result")
            elif family=="deceptive_suffix":
                need(not r4b.r2.is_2cnf(clauses),"deceptive suffix invalid")
            elif family=="general_unknown":
                need(not r4b.r2.is_2cnf(clauses),"general test accidentally 2SAT")
    print("NEW_HORIZON_R4B_GENERATOR_SELFTEST_PASS",len(FAMILIES)*NEW_PER_FAMILY,flush=True)

def freeze():
    need(sha(SOURCE/"manifest.json")==SOURCE_SHA,"R4 source manifest changed")
    prior=load(SOURCE/"manifest.json")
    need(len(prior["cases"])==PREVIOUS,"R4 count mismatch")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in prior["cases"]:
        p=SOURCE/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"old SHA drift")
        name="old-"+c["id"]
        dest=FROZEN/(name+".cnf")
        dest.write_bytes(p.read_bytes())
        cases.append(dict(id=name,origin="R4_reused_"+c["origin"],
               family="reused",cap_s=c["cap_s"],expected=c["expected"],
               sha256=sha(dest),prior_sha=c["sha256"]))
    for family in FAMILIES:
        for i in range(NEW_PER_FAMILY):
            n,clauses,expected=new_example(family,i)
            name=f"r4b-{family}-{i}"
            dest=FROZEN/(name+".cnf")
            dest.write_text(cnf(n,clauses))
            cases.append(dict(id=name,origin="new_seed_known_family",family=family,
                  cap_s=3.0,expected=expected,sha256=sha(dest)))
    need(len(cases)==TOTAL and len({c["sha256"] for c in cases})==TOTAL,
         "incomplete or duplicate frozen source SHA")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
         all_arms_identical_native=True,baseline_R4_SHA=SOURCE_SHA,
         benchmark_not_external_blind=True,
         thresholds_derived_from_development_R3_R4=True,
         family_labels_not_used_for_routing=True))
    verify()
    print("NEW_HORIZON_R4B_FROZEN_PASS",json.dumps({
        "sources":TOTAL,"manifest_sha256":sha(FROZEN/"manifest.json")}),flush=True)

def verify():
    data=load(FROZEN/"manifest.json")
    need(data["protocol"]==PROTO and len(data["cases"])==TOTAL,"bad manifest")
    for c in data["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "source SHA mismatch "+c["id"])
    return data["cases"]

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["sha256"],"trial source mutated")
    scratch=ROOT/"scratch"/(c["sha256"][:16]+f"-{mode}-{rep}")
    x=r4b.run_one(p,binary,float(c["cap_s"]),mode,scratch)
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
    if status!="TIMEOUT" and c["expected"] in ("SAT","UNSAT"):
        need(status==c["expected"],"wrong solved answer")
    evidence=x.get("r4b_evidence") or {}
    elapsed=round(x["elapsed"],6)
    return dict(id=c["id"],source_sha256=c["sha256"],
       cohort=c["origin"],family=c["family"],rep=rep,mode=mode,
       cap_s=c["cap_s"],status=status,elapsed_s=elapsed,
       par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
       route=x["route"],proof=x["proof"],reason=x["reason"],
       screening_s=round(evidence.get("scan_s",0),6),
       scanned=evidence.get("scanned"),
       certified_source=evidence.get("complete_source"))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),
         "bad shard or missing binary")
    out=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                z=trial(c,mode,rep,binary)
                out.append(z)
                save(ROOT/f"shard-{index}.json",out)
                print("NEW_HORIZON_R4B_TRIAL",json.dumps({k:z[k] for k in
                    ("id","mode","status","elapsed_s","route","screening_s","scanned")}),
                    flush=True)
    need(len(out)==len(cases[index::SHARDS])*REPS*len(MODES),
         "incomplete shard")
    print("NEW_HORIZON_R4B_SHARD_PASS",index,len(out),flush=True)

def audit():
    cases=verify()
    by_sha={c["sha256"]:c for c in cases}
    rows=[]
    for i in range(SHARDS):
        part=load(ROOT/f"shard-{i}.json")
        need(len(part)==len(cases[i::SHARDS])*REPS*len(MODES),
             "missing or incomplete shard "+str(i))
        rows.extend(part)
    need(len(rows)==TOTAL*REPS*len(MODES),"missing matched trials")
    pairs=collections.defaultdict(list)
    for row in rows:
        c=by_sha.get(row["source_sha256"])
        need(c is not None and c["id"]==row["id"],
             "source hash/ID mismatch")
        true_par2=2*row["cap_s"] if row["status"]=="TIMEOUT" else row["elapsed_s"]
        need(abs(true_par2-row["par2_s"])<0.00001,"PAR2 mismatch")
        pairs[row["source_sha256"],row["rep"]].append(row)
    for c in cases:
        for rep in range(REPS):
            group=pairs[c["sha256"],rep]
            need(len(group)==len(MODES) and {r["mode"] for r in group}==set(MODES),
                 "paired arm count/selection mismatch")
            need(len({r["status"] for r in group if r["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT/UNSAT answers")
    groups={"all":cases,"R4_reused":[c for c in cases if c["family"]=="reused"],
       "R4_real_reused":[c for c in cases if "external_original" in c["origin"]],
       "new_known_generators":[c for c in cases if c["origin"]=="new_seed_known_family"]}
    for family in FAMILIES:
        groups[family]=[c for c in cases if c["family"]==family]
    summary={}
    for name,caseset in groups.items():
        accepted={c["sha256"] for c in caseset}
        summary[name]={}
        for mode in MODES:
            z=[r for r in rows if r["source_sha256"] in accepted and r["mode"]==mode]
            summary[name][mode]=dict(trials=len(z),
              solved=sum(r["status"]!="TIMEOUT" for r in z),
              par2_s=round(sum(r["par2_s"] for r in z),6),
              elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
              screening_s=round(sum(r["screening_s"] for r in z),6),
              routes=dict(collections.Counter(r["route"] for r in z)))
    output=dict(protocol=PROTO,status="NEW_HORIZON_R4B_AUDIT_PASS_NOT_BLIND",
       sources=TOTAL,trials=len(rows),reps=REPS,shards=SHARDS,
       original_SHA_verified=True,all_paired=True,
       original_SAT_models_checked=True,UNSAT_standard_LRAT_absent=True,
       known_generators_and_reused_data_not_blind=True,
       policy_developed_using_R3_R4_not_independent=True,summary=summary)
    save(ROOT/"report.json",output)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        writer.writeheader();writer.writerows(rows)
    lines=["# DRNAS New Horizon SAT R4b — single-pass original-source proof","",
           f"{TOTAL} immutable SHA-paired sources; {len(rows)} paired trials.",
           "All source screening and solver time included.","",
           "| Cohort | Method | Solved | PAR2 (s) | Screening (s) | Routes |",
           "|---|---|---:|---:|---:|---|"]
    for cohort,v in summary.items():
        for mode,x in v.items():
            lines.append(f"| {cohort} | {mode} | {x['solved']}/{x['trials']} | "+
                         f"{x['par2_s']:.6f} | {x['screening_s']:.6f} | {x['routes']} |")
    lines.extend(["","## Scientific limits",
       "- No independent blind external real holdout.",
       "- R4b cost gate is informed by R3/R4 development results.",
       "- Exact source class checks and original SAT witness, not a general SAT shortcut.",
       "- Native UNSAT lacks independent LRAT/FRAT verification.",
       "- Sub-millisecond results require repeated confirmation on stable hardware."])
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NEW_HORIZON_R4B_FINAL",json.dumps({k:summary[k] for k in
        ("all","R4_real_reused","new_known_generators")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r4b/r190-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("NEW_HORIZON_R4B_VERIFY_PASS",len(verify()))
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    elif a.action=="audit":audit()

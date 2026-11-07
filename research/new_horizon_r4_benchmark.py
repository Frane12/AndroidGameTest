#!/usr/bin/env python3
"""DRNAS New Horizon SAT R4: frozen four-arm, original-SHA cost audit.

R3 146 reused sources + 48 NEW deterministic generator cases = 194.
4 arms x 2 reps = 1552 SHA-matched trials. NOT blind external real data.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,statistics
import new_horizon_r4 as r4
import new_horizon_r3_benchmark as r3bench

ROOT=pathlib.Path("new_horizon_r4")
FROZEN=ROOT/"frozen"
OLD=ROOT/"source/new_horizon_r3/frozen"
SOURCE_SHA="9c8a18686e6a83b2272dcb86b87cc4c5ca0fa9a82ea2dc81c407e7ad791f1b40"
PROTO="DRNAS-NH-R4-194-SHA-FOUR-ARM-1552-v1"
OLD_COUNT=146
NEW_GROUP_SIZE=12
TOTAL=OLD_COUNT+4*NEW_GROUP_SIZE
REPS=2
SHARDS=8
MODES=("clean","shadow","r3","r4")

def need(c,msg):
    if not c:raise AssertionError("R4_BENCH_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def cnf(n,clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)

def large_horn(i):
    rng=random.Random(20261107401+i*709)
    n=320+(i%4)*40
    clauses=[(1,)]+[(-j,j+1) for j in range(1,n)]
    # Two-body negative antecedents => exact Horn but not 2SAT.
    for _ in range(n*2):
        a,b,c=rng.sample(range(1,n+1),3)
        clauses.append((-a,-b,c))
    expected="SAT"
    if i%2:
        clauses.append((-n,))
        expected="UNSAT"
    rng.shuffle(clauses)
    return n,clauses,expected

def large_2sat(i):
    rng=random.Random(20261107402+i*907)
    n=320+(i%4)*40
    model=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[]
    seen=set()
    while len(clauses)<4*n:
        a,b=rng.sample(range(1,n+1),2)
        vals=[a if rng.getrandbits(1) else -a,b if rng.getrandbits(1) else -b]
        if not any((z>0)==model[abs(z)] for z in vals):
            k=rng.randrange(2)
            v=abs(vals[k])
            vals[k]=v if model[v] else -v
        cl=tuple(vals)
        if cl not in seen:
            seen.add(cl);clauses.append(cl)
    expected="SAT"
    if i%2:
        clauses.extend([(1,2),(1,-2),(-1,3),(-1,-3)])
        expected="UNSAT"
    rng.shuffle(clauses)
    return n,clauses,expected

def general_unknown(i):
    # New deterministic seeds of a known R3 planted 3-CNF generator family.
    return r3bench.generate_unknown(200+i)

def deceptive_prefix(i):
    # Source is SAT under all-true assignment. First 64 clauses appear
    # Horn/2SAT; late clause invalidates BOTH special classifications.
    n=320+i
    clauses=[(1,)]+[(-j,j+1) for j in range(1,n)]
    clauses.extend([(1,2,3),(8+i,9+i,10+i)])
    return n,clauses,"SAT"

GENERATORS={"new_large_horn":large_horn,"new_large_2sat":large_2sat,
            "new_general_unknown":general_unknown,"new_late_prefix":deceptive_prefix}

def selftest():
    r4.selftest()
    for name,func in GENERATORS.items():
        for i in range(NEW_GROUP_SIZE):
            n,clauses,expected=func(i)
            need(n>0 and len(clauses)>0,"generator created empty source")
            if name=="new_large_horn":
                need(r4.r2.is_horn(clauses),"large Horn source invalid")
                need(r4.r2.solve_horn(n,clauses)["status"]==expected,
                     "large Horn SAT/UNSAT expected")
            if name=="new_large_2sat":
                need(r4.r2.is_2cnf(clauses),"large 2SAT invalid")
                need(r4.r2.solve_2sat(n,clauses)["status"]==expected,
                     "large 2SAT SAT/UNSAT expected")
            if name=="new_late_prefix":
                need(not r4.r2.is_horn(clauses) and not r4.r2.is_2cnf(clauses),
                     "deceptive suffix fails to disqualify")
            if name=="new_general_unknown":
                need(not r4.r2.is_horn(clauses) and not r4.r2.is_2cnf(clauses),
                     "general control coincidentally tractable")
    print("NEW_HORIZON_R4_GENERATOR_SELFTEST_PASS",NEW_GROUP_SIZE*len(GENERATORS),flush=True)

def freeze():
    need(sha(OLD/"manifest.json")==SOURCE_SHA,"original R3 manifest SHA drift")
    prior=read(OLD/"manifest.json")
    need(len(prior["cases"])==OLD_COUNT,"unexpected R3 case count")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in prior["cases"]:
        src=OLD/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R3 frozen source mutated")
        id="r3-"+c["id"]
        dst=FROZEN/(id+".cnf")
        dst.write_bytes(src.read_bytes())
        cases.append(dict(id=id,origin="reused_"+c["origin"],
           family="R3_reused",expected=c["expected"],cap_s=c["cap_s"],
           sha256=sha(dst),original_sha256=c["sha256"]))
    for family,func in GENERATORS.items():
        for i in range(NEW_GROUP_SIZE):
            n,clauses,expected=func(i)
            id="r4-"+family+"-"+str(i)
            dst=FROZEN/(id+".cnf")
            dst.write_text(cnf(n,clauses))
            cases.append(dict(id=id,origin="new_deterministic_nonblind",
                    family=family,expected=expected,cap_s=3.0,sha256=sha(dst)))
    need(len(cases)==TOTAL and len({c["sha256"] for c in cases})==TOTAL,
         "nonunique or incomplete source corpus")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
         old_R3_manifest_sha=SOURCE_SHA,not_blind_real=True,
         new_generator_families_known=True,
         source_only_routing=True,repetitions=REPS,shards=SHARDS,
         arms=MODES))
    verify()
    print("NEW_HORIZON_R4_FREEZE_PASS",json.dumps(dict(formulas=TOTAL,
         manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,
         "manifest protocol or count")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original source SHA changed "+c["id"])
    return m["cases"]

def trial(case,mode,rep,binary):
    source=FROZEN/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"trial original source SHA drift")
    scratch=ROOT/"scratch"/(case["sha256"][:16]+"-"+mode+"-"+str(rep))
    x=r4.run_one(source,binary,case["cap_s"],mode,scratch)
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"solver invalid answer")
    if status!="TIMEOUT" and case["expected"] in ("SAT","UNSAT"):
        need(status==case["expected"],"expected source answer disagreement")
    fp=x.get("r4_observer")
    elapsed=round(x["elapsed"],6)
    return dict(id=case["id"],source_sha256=case["sha256"],
       cohort=case["origin"],family=case["family"],mode=mode,rep=rep,
       cap_s=case["cap_s"],status=status,elapsed_s=elapsed,
       par2_s=round(2*case["cap_s"] if status=="TIMEOUT" else elapsed,6),
       route=x["route"],proof=x["proof"],reason=x["reason"],
       screen_s=round(fp["scan_s"],6) if fp else 0,
       sampled=fp.get("sampled") if fp else None,
       negative_certificates=fp.get("negative_certificates") if fp else None,
       model_estimate_ms=(fp.get("score") or {}).get("benefit_ms") if fp else None)

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),
         "bad shard or missing pinned binary")
    out=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,mode,rep,binary)
                out.append(row)
                save(ROOT/f"shard-{index}.json",out)
                print("NEW_HORIZON_R4_TRIAL",json.dumps({k:row[k] for k in
                     ("id","mode","status","elapsed_s","route","sampled")}),
                     flush=True)
    need(len(out)==len(cases[index::SHARDS])*REPS*len(MODES),
         "shard trial count mismatch")
    print("NEW_HORIZON_R4_SHARD_PASS",index,len(out),flush=True)

def audit():
    cases=verify()
    by_sha={c["sha256"]:c for c in cases}
    rows=[]
    for i in range(SHARDS):
        data=read(ROOT/f"shard-{i}.json")
        need(len(data)==len(cases[i::SHARDS])*REPS*len(MODES),
             "missing shard or incomplete row count")
        rows.extend(data)
    need(len(rows)==TOTAL*REPS*len(MODES),"missing trial rows")
    paired=collections.defaultdict(list)
    for r in rows:
        c=by_sha.get(r["source_sha256"])
        need(c is not None and r["id"]==c["id"],"paired source discrepancy")
        need(abs(r["par2_s"]-(2*r["cap_s"] if r["status"]=="TIMEOUT"
             else r["elapsed_s"]))<0.00001,"incorrect PAR2 accounting")
        paired[(r["source_sha256"],r["rep"])].append(r)
    for c in cases:
        for rep in range(REPS):
            z=paired[(c["sha256"],rep)]
            need(len(z)==len(MODES) and {r["mode"] for r in z}==set(MODES),
                 "incomplete source-matched quadruple")
            need(len({r["status"] for r in z if r["status"]!="TIMEOUT"})<=1,
                 "opposing SAT/UNSAT answer across paired runs")
    cohorts=dict(all=cases,
         reused_R3=[c for c in cases if c["origin"].startswith("reused_")],
         reused_external=[c for c in cases if "external_original" in c["origin"]],
         R4_new=[c for c in cases if c["origin"]=="new_deterministic_nonblind"])
    for name in GENERATORS:
        cohorts[name]=[c for c in cases if c["family"]==name]
    results={}
    for cohort,subset in cohorts.items():
        allowed={c["sha256"] for c in subset}
        results[cohort]={}
        for mode in MODES:
            z=[r for r in rows if r["mode"]==mode and r["source_sha256"] in allowed]
            results[cohort][mode]=dict(trials=len(z),
             solved=sum(r["status"]!="TIMEOUT" for r in z),
             elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
             par2_s=round(sum(r["par2_s"] for r in z),6),
             screen_s=round(sum(r["screen_s"] for r in z),6),
             routes=dict(collections.Counter(r["route"] for r in z)),
             early_zero_sample=sum(r["sampled"]==0 for r in z),
             early_one_clause=sum(r["sampled"]==1 for r in z))
    report=dict(protocol=PROTO,status="DRNAS_R4_AUDIT_PASS_NOT_BLIND",
       sources=TOTAL,trials=len(rows),repetitions=REPS,shards=SHARDS,
       all_SHA_source_verified=True,
       same_pinned_native_binary_for_all_arms=True,
       original_SAT_models_checked=True,
       UNSAT_no_independent_LRAT=True,
       not_blind_external=True,
       conclusions="No general SAT advantage claim from this benchmark",
       summary=results)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        w.writeheader();w.writerows(rows)
    lines=["# DRNAS New Horizon R4 — source-pinned robustness and cost audit","",
       f"{TOTAL} immutable formulas, {len(rows)} trials, 4 matched policies × 2 repeats.",
       "All source pre-analysis and full certification time charged to wallclock.","",
       "| Cohort | Method | Solved | PAR2 s | Screening s | Routes |",
       "|---|---|---:|---:|---:|---|"]
    for cohort,group in results.items():
        for mode,x in group.items():
            lines.append("| "+cohort+" | "+mode+" | "+
              f"{x['solved']}/{x['trials']} | {x['par2_s']:.6f} | "+
              f"{x['screen_s']:.6f} | {x['routes']} |")
    lines.extend(["","## Strict limits",
       "- Reused original real CNFs are not blind; new generator families are known.",
       "- Source models independently verified for SAT, native UNSAT not LRAT replayed.",
       "- Source-complete Horn / 2SAT / GF2 proof gate remains exact.",
       "- Millisecond runtime differences may be affected by runner and process-start noise."])
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NEW_HORIZON_R4_FINAL",json.dumps({
        k:results[k] for k in ("all","reused_external","R4_new")
    },sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r4/r190-driver")
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":print("NEW_HORIZON_R4_VERIFY_PASS",len(verify()))
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()

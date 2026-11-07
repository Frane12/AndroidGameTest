#!/usr/bin/env python3
"""New Horizon R3 source-only early abstention paired benchmark.
114 R2 frozen sources + 32 new deterministic controls = 146 cases.
Four arms, two repeats = 1168 SHA matched trials; real originals reused.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random
import new_horizon_r2_benchmark as old
import new_horizon_r3 as r3

ROOT=pathlib.Path("new_horizon_r3")
FROZEN=ROOT/"frozen"
SRC=ROOT/"source/new_horizon_r2/frozen"
SOURCE_SHA="f2ced9794fbea5ab9420e6f7db0e43106e35c85a28a70cf5893cf7cc20ec19b7"
PROTO="NEW_HORIZON_R3_EARLY_ABSTENTION_SHA_PAIRED_v1"
R2_COUNT=114;MORE_HORN=12;MORE_TWO=12;MORE_UNKNOWN=8
TOTAL=R2_COUNT+MORE_HORN+MORE_TWO+MORE_UNKNOWN
REPS=2;SHARDS=4;MODES=("clean","shadow","r2","r3")

def need(ok, msg):
    if not ok:raise AssertionError("NH_R3_BENCH_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def make_cnf(n,cls):
    return f"p cnf {n} {len(cls)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cls)
def generate_unknown(i):
    """SAT planted general 3-CNF. Not proof of hard SAT distribution."""
    rng=random.Random(20261107+800000+i*317)
    n=96+4*i
    witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    seen=set();clauses=[]
    while len(clauses)<5*n:
        vs=rng.sample(range(1,n+1),3)
        cl=[v if rng.getrandbits(1) else -v for v in vs]
        if not any((v>0)==witness[abs(v)] for v in cl):
            j=rng.randrange(3);cl[j]=abs(cl[j]) if witness[abs(cl[j])] else -abs(cl[j])
        key=tuple(cl)
        if key not in seen:
            seen.add(key);clauses.append(key)
    # Place a disqualifying (non-Horn, non-2-SAT) satisfied clause first.
    first=next((c for c in clauses if sum(z>0 for z in c)>1),None)
    need(first is not None,"unknown generator lacks early discriminator")
    clauses.remove(first)
    clauses.insert(0,first)
    return n,clauses,"SAT"

def selftest():
    r3.selftest()
    for i in range(MORE_HORN):
        n,clauses,expected=old.generated_horn(500+i)
        need(r3.check_exact(write_temp(clauses,n),"horn")[0]==expected,
             "new Horn exact answer mismatch")
    for i in range(MORE_TWO):
        n,clauses,expected=old.generated_two(500+i)
        need(r3.check_exact(write_temp(clauses,n),"two_sat")[0]==expected,
             "new 2SAT exact answer mismatch")
    for i in range(MORE_UNKNOWN):
        n,clauses,expected=generate_unknown(i)
        need(not r3.r2.is_horn(clauses) and not r3.r2.is_2cnf(clauses),
             "unknown control accidentally pure family")
    print("NEW_HORIZON_R3_BENCH_SELFTEST_PASS",MORE_HORN+MORE_TWO+MORE_UNKNOWN,flush=True)

def write_temp(clauses,n):
    import tempfile
    p=pathlib.Path(tempfile.gettempdir())/"nh-r3-selftest-source.cnf"
    p.write_text(make_cnf(n,clauses))
    return p

def freeze():
    need(sha(SRC/"manifest.json")==SOURCE_SHA,"R2 published manifest SHA changed")
    prior=read(SRC/"manifest.json")
    need(len(prior["cases"])==R2_COUNT,"R2 source count mismatch")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in prior["cases"]:
        src=SRC/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R2 source hash drift")
        dst=FROZEN/("r2-"+c["id"]+".cnf")
        dst.write_bytes(src.read_bytes())
        cases.append(dict(id="r2-"+c["id"],origin="R2_reused_"+c["cohort"],
                          family="reused",expected=c["expected"],cap_s=c["cap_s"],
                          sha256=sha(dst),from_sha256=c["sha256"]))
    for family,count,generator in (("new_horn",MORE_HORN,old.generated_horn),
                                   ("new_2sat",MORE_TWO,old.generated_two),
                                   ("new_unknown",MORE_UNKNOWN,generate_unknown)):
        for i in range(count):
            n,cs,expected=generator(500+i) if family!="new_unknown" else generator(i)
            id=f"r3-{family}-{i}"
            dst=FROZEN/(id+".cnf")
            dst.write_text(make_cnf(n,cs))
            cases.append(dict(id=id,origin="new_deterministic_family",
                     family=family,expected=expected,cap_s=3.0,sha256=sha(dst)))
    need(len(cases)==TOTAL and len({x["sha256"] for x in cases})==TOTAL,
         "nonunique or incomplete source set")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
         R2_manifest_sha256=SOURCE_SHA,not_blind=True,
         outcome_and_family_excluded_from_routing=True,
         same_pinned_native_all_arms=True))
    verify()
    print("NEW_HORIZON_R3_FROZEN_PASS",json.dumps(dict(formulas=TOTAL,
          manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    d=read(FROZEN/"manifest.json")
    need(d["protocol"]==PROTO and len(d["cases"])==TOTAL,"manifest mismatch")
    for c in d["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "source SHA mismatch "+c["id"])
    return d["cases"]

def trial(c,mode,rep,binary):
    src=FROZEN/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"source hash changed at solve")
    scratch=ROOT/"scratch"/(c["sha256"][:12]+"-"+mode+"-"+str(rep))
    x=r3.run_one(src,binary,c["cap_s"],mode,scratch)
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"bad SAT solver status")
    if status!="TIMEOUT" and c["expected"] in ("SAT","UNSAT"):
        need(status==c["expected"],"answer disagrees with expected source")
    fp=x.get("r3_probe")
    elapsed=round(x["elapsed"],6)
    return dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],family=c["family"],
       mode=mode,rep=rep,status=status,elapsed_s=elapsed,cap_s=c["cap_s"],
       par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
       route=x["route"],reason=x["reason"],proof=x["proof"],
       screen_s=round(fp["scan_s"],6) if fp else 0,
       sampled=fp.get("sampled") if fp else None,
       stopped_early=fp.get("stopped_early") if fp else None,
       predicted_gain_ms=(fp.get("score") or {}).get("benefit_ms") if fp else None)

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),"bad index or binary")
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                result=trial(c,mode,rep,binary)
                rows.append(result)
                save(ROOT/f"shard-{index}.json",rows)
                print("NEW_HORIZON_R3_TRIAL",json.dumps({k:result[k] for k in (
                    "id","mode","status","elapsed_s","route","sampled","stopped_early")}),
                    flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(MODES),"shard count")
    print("NEW_HORIZON_R3_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    lookup={x["sha256"]:x for x in cases}
    rows=[]
    for i in range(SHARDS):
        z=read(ROOT/f"shard-{i}.json")
        need(len(z)==len(cases[i::SHARDS])*REPS*len(MODES),
             "missing or incomplete shard")
        rows.extend(z)
    need(len(rows)==TOTAL*REPS*len(MODES),"missing paired runs")
    groups=collections.defaultdict(list)
    for r in rows:
        c=lookup.get(r["sha256"])
        need(c is not None and c["id"]==r["id"],"wrong source or case")
        check=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(check-r["par2_s"])<0.00001,"wrong PAR2")
        groups[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            group=groups[c["sha256"],rep]
            need(len(group)==len(MODES) and set(x["mode"] for x in group)==set(MODES),
                 "not exactly matched four arm trial")
            need(len(set(x["status"] for x in group if x["status"]!="TIMEOUT"))<=1,
                 "contradictory SAT answers")
    summary={}
    cohorts={"all":cases,
             "R2_reused":[c for c in cases if c["origin"].startswith("R2_")],
             "R2_external_real":[c for c in cases if "external_original" in c["origin"]],
             "new_deterministic_family":[c for c in cases if c["origin"]=="new_deterministic_family"]}
    for f in ("new_horn","new_2sat","new_unknown"):
        cohorts[f]=[c for c in cases if c["family"]==f]
    for label,cohort in cohorts.items():
        keys={c["sha256"] for c in cohort}
        summary[label]={}
        for mode in MODES:
            z=[r for r in rows if r["sha256"] in keys and r["mode"]==mode]
            summary[label][mode]=dict(n=len(z),solved=sum(r["status"]!="TIMEOUT" for r in z),
               par2_s=round(sum(r["par2_s"] for r in z),6),
               elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
               screening_s=round(sum(r["screen_s"] for r in z),6),
               early_abstentions=sum(1 for r in z if r["stopped_early"] is True
                                    and r["route"]=="clean"),
               routes=dict(collections.Counter(r["route"] for r in z)))
    report=dict(protocol=PROTO,status="NEW_HORIZON_R3_AUDIT_PASS_NOT_BLIND",
                formulas=TOTAL,trials=len(rows),paired=True,
                source_sha_verified=True,canonical_gate_source_only=True,
                model_witness_checked_on_original=True,
                caveats=["R2 frozen originals reused; this is not a blind real holdout",
                         "New seeds are generated from already known formula families",
                         "UNSAT solver answers lack independent LRAT proofs",
                         "Sub-millisecond measurements are sensitive to runner noise"],
                summary=summary)
    save(ROOT/"report.json",report)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    lines=["# New Horizon SAT R3 — early abstention","",
           f"{TOTAL} SHA-frozen CNFs; 4 policies; 2 repetitions; {len(rows)} paired trials.",
           "Results include all screening and preprocessing costs.","",
           "| Cohort | Method | Solved | PAR2 s | Screening s | Early aborts |",
           "|---|---|---:|---:|---:|---:|"]
    for label, x in summary.items():
        for mode,y in x.items():
            lines.append(f"| {label} | {mode} | {y['solved']}/{y['n']} | {y['par2_s']:.6f} | {y['screening_s']:.6f} | {y['early_abstentions']} |")
    lines.extend(["","No general NP-SAT breakthrough claim. Unseen real industrial holdout needed."])
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NEW_HORIZON_R3_FINAL",json.dumps({k:summary[k] for k in
        ("all","R2_external_real","new_deterministic_family")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon_r3/r190-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("NEW_HORIZON_R3_VERIFY_PASS",len(verify()))
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()

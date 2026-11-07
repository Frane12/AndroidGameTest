#!/usr/bin/env python3
"""DRNAS New Horizon R2: 114 source-pinned formulas, 4 arms, 2 repeats = 912 trials.

Prospective (new generated source) not blind, original R1 sources reused.
All arms use identical CaDiCaL binary, same cap, source SHA and original CNF.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,pathlib,random,statistics,time
import new_horizon_r2 as r2
import new_horizon_sat as r1

ROOT=pathlib.Path("new_horizon_r2")
FROZEN=ROOT/"frozen"
OLD=ROOT/"source/new_horizon/frozen"
R1_MANIFEST_SHA="b0a5631a0b470ec9b0ab005cf1102ca0efc83783c8f3c8d8179ac621676e3d75"
PROTO="DRNAS_NEW_HORIZON_R2_ROBUST_LINEAR_20261107_v1"
MODES=("clean","shadow","r1","r2")
SHARDS=4
REPS=2
R1_COUNT=74
NEW_HORN=16
NEW_TWO=16
TRAP=8
TOTAL=R1_COUNT+NEW_HORN+NEW_TWO+TRAP

def need(ok,msg):
    if not ok:raise AssertionError("NH_R2_BENCH_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,x):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def cnf(n,cs):
    return f"p cnf {n} {len(cs)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cs)

def generated_horn(i):
    rng=random.Random(202611070102+i*103)
    n=80+(i%4)*10
    clauses=[(1,)]+[(-x,x+1) for x in range(1,n)]
    for _ in range(n*3):
        a,b,c=rng.sample(range(1,n+1),3)
        clauses.append((-a,-b,c))
    expected="SAT"
    if i%2:
        clauses.append((-n,))
        expected="UNSAT"
    rng.shuffle(clauses)
    return n,clauses,expected

def generated_two(i):
    rng=random.Random(202611070203+i*211)
    n=80+(i%4)*10
    model=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[]
    for _ in range(3*n):
        a,b=rng.sample(range(1,n+1),2)
        s=[a if rng.getrandbits(1) else -a,b if rng.getrandbits(1) else -b]
        if not any((x>0)==model[abs(x)] for x in s):
            j=rng.randrange(2)
            s[j]=abs(s[j]) if model[abs(s[j])] else -abs(s[j])
        clauses.append(tuple(s))
    expected="SAT"
    if i%2:
        clauses.extend([(1,2),(1,-2),(-1,3),(-1,-3)])
        expected="UNSAT"
    rng.shuffle(clauses)
    return n,clauses,expected

def generated_trap(i):
    """First >=64 clauses look like a tractable class; later clause disproves it.
    These SAT formulas must never be misrouted or edited.
    """
    n=96;clauses=[(1,)]
    if i%2==0: 
        clauses.extend([(-x,x+1) for x in range(1,96)])
        clauses.extend([(1,2,3),(4+i,5+i,6+i)]) # outside both classes; unique SHA
        kind="false_horn"
    else:
        clauses.extend([(-x,x+1) for x in range(1,96)])
        clauses.extend([(1,2,3),(4+i,5+i,6+i)]) # later disproof; unique SHA
        kind="false_2sat"
    return n,clauses,"SAT",kind

def selftest():
    r2.selftest()
    for method,gen,count in (("horn",generated_horn,NEW_HORN),
                              ("two_sat",generated_two,NEW_TWO)):
        for i in range(count):
            n,c,expected=gen(i)
            if method=="horn":got=r2.solve_horn(n,c)
            else:got=r2.solve_2sat(n,c)
            need(got["status"]==expected,method+" source expected")
    for i in range(TRAP):
        n,c,expected,kind=generated_trap(i)
        need(not r2.is_2cnf(c) and not r2.is_horn(c),"mixed-prefix trap invalid")
    print("NEW_HORIZON_R2_BENCH_SELFTEST_PASS",NEW_HORN+NEW_TWO+TRAP,flush=True)

def freeze():
    need(sha(OLD/"manifest.json")==R1_MANIFEST_SHA,
         "published R1 manifest sha changed")
    prev=load(OLD/"manifest.json")
    need(len(prev["cases"])==R1_COUNT,"R1 original count drift")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in prev["cases"]:
        p=OLD/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"R1 immutable source mismatch")
        name="r1-"+c["id"];dest=FROZEN/(name+".cnf")
        dest.write_bytes(p.read_bytes())
        cases.append(dict(id=name,cohort="reused_"+c["origin"],
                          family="reused_control",expected=c.get("expected","UNKNOWN"),
                          cap_s=c["cap_s"],sha256=sha(dest),prior_sha256=c["sha256"]))
    for family,generator,count in (("horn",generated_horn,NEW_HORN),
                                   ("two_sat",generated_two,NEW_TWO)):
        for i in range(count):
            n,c,expected=generator(i)
            name=f"r2-{family}-{i}"
            dest=FROZEN/(name+".cnf")
            dest.write_text(cnf(n,c))
            cases.append(dict(id=name,cohort="new_seed_structural",
                     family=family,expected=expected,cap_s=3.0,sha256=sha(dest)))
    for i in range(TRAP):
        n,c,expected,family=generated_trap(i)
        name=f"r2-trap-{i}"
        dest=FROZEN/(name+".cnf")
        dest.write_text(cnf(n,c))
        cases.append(dict(id=name,cohort="new_seed_adversarial_prefix",
                     family=family,expected=expected,cap_s=3.0,sha256=sha(dest)))
    need(len(cases)==TOTAL and len({x["sha256"] for x in cases})==TOTAL,
         "duplicate or missing R2 sources")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
         source_R1_SHA=R1_MANIFEST_SHA,not_blind_real=True,not_blind_new_families=True,
         routes_source_only=True,method_coefficients_frozen=True,
         all_four_arms_paired=True))
    verify()
    print("NEW_HORIZON_R2_FREEZE_PASS",json.dumps(dict(sources=len(cases),
        manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    m=load(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,"manifest protocol")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "source SHA drift "+c["id"])
    return m["cases"]

def trial(c,mode,rep,binary):
    source=FROZEN/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"original altered before solving")
    scratch=ROOT/"temp"/(c["sha256"][:18]+f"-{mode}-{rep}")
    res=r2.run_one(source,binary,float(c["cap_s"]),mode,scratch)
    status=res["status"];need(status in ("SAT","UNSAT","TIMEOUT"),"native status")
    if status!="TIMEOUT" and c["expected"] in ("SAT","UNSAT"):
        need(status==c["expected"],"expected SAT/UNSAT result mismatch")
    elapsed=res["elapsed"]
    screen=res.get("screen")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
        family=c["family"],mode=mode,rep=rep,status=status,
        route=res["route"],reason=res["reason"],proof=res["proof"],
        cap_s=c["cap_s"],elapsed_s=round(elapsed,6),
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
        scan_s=round(screen.get("scan_s",0),6) if screen else 0,
        sampled=screen.get("sample") if screen else None,
        surrogate_gain_ms=(res.get("r2_score") or {}).get("benefit_ms"),
        verified_method=res.get("r2_origin")=="source_verified",
        candidate=res.get("r2_candidate"))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),"bad shard/binary")
    out=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                z=trial(c,mode,rep,binary)
                out.append(z)
                save(ROOT/f"shard-{index}.json",out)
                print("NEW_HORIZON_R2_TRIAL",json.dumps({k:z[k] for k in
                    ("id","mode","status","elapsed_s","route","surrogate_gain_ms")}),
                    flush=True)
    need(len(out)==len(cases[index::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("NEW_HORIZON_R2_SHARD_PASS",index,len(out),flush=True)

def audit():
    cases=verify()
    bysha={c["sha256"]:c for c in cases}
    rows=[]
    for shard_id in range(SHARDS):
        part=load(ROOT/f"shard-{shard_id}.json")
        need(len(part)==len(cases[shard_id::SHARDS])*REPS*len(MODES),
             "incomplete shard artifacts")
        rows.extend(part)
    need(len(rows)==TOTAL*REPS*len(MODES),"exact 912 trials")
    pairs=collections.defaultdict(list)
    for z in rows:
        c=bysha.get(z["sha256"])
        need(c is not None and c["id"]==z["id"],"source tampering")
        target=2*z["cap_s"] if z["status"]=="TIMEOUT" else z["elapsed_s"]
        need(abs(target-z["par2_s"])<0.00001,"bad PAR2 accounting")
        pairs[(z["sha256"],z["rep"])].append(z)
    for c in cases:
        for rep in range(REPS):
            group=pairs[c["sha256"],rep]
            need(len(group)==len(MODES) and {z["mode"] for z in group}==set(MODES),
                 "broken same-source pairing")
            need(len({z["status"] for z in group if z["status"]!="TIMEOUT"})<=1,
                 "contradictory same-source answers")
    groups={"all":cases}
    for cohort in ("reused_reused_external_original","reused_new_seed_known_family",
                   "reused_synthetic_controlled","new_seed_structural",
                   "new_seed_adversarial_prefix"):
        groups[cohort]=[c for c in cases if c["cohort"]==cohort]
    for family in ("horn","two_sat","false_horn","false_2sat"):
        groups[family]=[c for c in cases if c["family"]==family]
    totals={}
    for label,sub in groups.items():
        shas={c["sha256"] for c in sub}
        out={}
        for mode in MODES:
            rs=[r for r in rows if r["mode"]==mode and r["sha256"] in shas]
            out[mode]=dict(n=len(rs),solved=sum(r["status"]!="TIMEOUT" for r in rs),
              par2_s=round(sum(r["par2_s"] for r in rs),6),
              elapsed_s=round(sum(r["elapsed_s"] for r in rs),6),
              scan_s=round(sum(r["scan_s"] for r in rs),6),
              routes=dict(collections.Counter(r["route"] for r in rs)))
        totals[label]=out
    output=dict(protocol=PROTO,status="NEW_HORIZON_R2_AUDIT_PASS_NOT_BLIND",
       formulas=TOTAL,trials=len(rows),reps=REPS,all_source_SHA_verified=True,
       all_original_SAT_witnesses_checked=True,
       independent_LRAT_proofs_not_included=True,
       source_motifs_not_generic_NP_shortcut=True,
       caveats=["R1 reused sources are not blind","new generators not external",
                "linear surrogate approximates runtime only, never clauses",
                "small benchmark walltimes subject to runner noise"],
       summary=totals)
    save(ROOT/"report.json",output)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    lines=["# DRNAS New Horizon SAT R2 — robust linearization","",
       f"{TOTAL} formulas; {len(rows)} paired runs; same frozen source and CaDiCaL binary.","",
       "| Cohort | Method | Solved | PAR2 (s) | Solver wall time (s) |",
       "|---|---|---:|---:|---:|"]
    for label,out in totals.items():
        if label not in ("all","reused_reused_external_original","reused_new_seed_known_family",
                         "reused_synthetic_controlled","new_seed_structural",
                         "new_seed_adversarial_prefix","horn","two_sat"):
            continue
        for mode,z in out.items():
            lines.append(f"| {label} | {mode} | {z['solved']}/{z['n']} | {z['par2_s']:.6f} | {z['elapsed_s']:.6f} |")
    lines += ["","No blind external holdout, no guarantee of general SAT improvement.",
              "Only cost/route estimated linearly; logical semantics exact.",
              "2SAT SCC and Horn reachability are exact linear-time special cases.",
              "Native CDCL UNSAT lacks independent LRAT proof; SAT witness checked."]
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NEW_HORIZON_R2_FINAL",json.dumps({
       key:dict(clean=totals[key]["clean"],r1=totals[key]["r1"],r2=totals[key]["r2"])
       for key in ("all","new_seed_structural","new_seed_adversarial_prefix")},
       sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--binary",default="new_horizon_r2/r190-driver")
    p=parser.parse_args()
    if p.action=="selftest":selftest()
    elif p.action=="freeze":freeze()
    elif p.action=="verify":print("NEW_HORIZON_R2_VERIFY_PASS",len(verify()))
    elif p.action=="shard":shard(p.shard,pathlib.Path(p.binary))
    elif p.action=="audit":audit()

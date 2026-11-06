#!/usr/bin/env python3
"""R190 general CDCL search policy test, independently auditable.

Question: Can a bounded source-only CNF fingerprint route the *same* pinned
CaDiCaL 2.1 solver to default/sat/unsat configurations on mixed SAT tasks?
This is a configuration/selection hypothesis, NOT a new SAT algorithm claim.
The 38 originals were used before; the 64 synthetic CNFs have new seeds but
reuse known generator families. Neither cohort is a truly blind real holdout.
No result/status/instance ID/family influences routing.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, random, time
import r186_cheap_selector as gen
import r188_feedback_benchmark as old

ROOT=pathlib.Path("r190")
FROZEN=ROOT/"frozen"
SOURCE_MANIFEST_SHA="3f0f67bea5547daa1ba07d9a1dba31d8d33f7d734db8eb6e8cae358a46c91ef3"
PROTO="DRNAS-R190-GENERAL-CDCL-FROZEN-STRUCTURAL-ROUTER-v1"
MODES=("default","sat_profile","unsat_profile","router","router_shadow")
REPS=2
SHARDS=8

def need(condition,message):
    if not condition:raise RuntimeError("R190_FAIL_CLOSED "+str(message))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    pathlib.Path(p).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")

def freeze():
    src=ROOT/"source"/"frozen"
    need(sha(src/"manifest.json")==SOURCE_MANIFEST_SHA,"prior 38 original manifest drift")
    sm=read(src/"manifest.json")
    need(len(sm["cases"])==38 and sm["originals"]==25,"source family changed")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in sm["cases"]:
        p=src/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"frozen source checksum drift")
        dst=FROZEN/(c["id"]+".cnf")
        dst.write_bytes(p.read_bytes())
        cases.append(dict(id=c["id"],family=c["family"],
            cohort="reused_external_original" if c["real"] else "reused_synthetic_control",
            expected=c["expected"],sha256=sha(dst),cap_s=15.0))
    # New precommitted seeds (not new generator families or blind external data).
    for family in gen.FAMILIES:
        for j in range(8):
            n,clauses,expected=gen.generated(family,200+j)
            cid="r190-new-"+family+"-"+str(j)
            p=FROZEN/(cid+".cnf")
            header=f"c R190 synthetic generator family={family} seed_index={200+j}\n"
            text=header+f"p cnf {n} {len(clauses)}\n"+"".join(
                " ".join(map(str,c))+" 0\n" for c in clauses)
            p.write_text(text)
            cases.append(dict(id=cid,family=family,cohort="new_seed_synthetic",
                expected=expected,sha256=sha(p),cap_s=6.0))
    need(len(cases)==102 and len({c["sha256"] for c in cases})==102,
         "nonunique frozen source or count error")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        pinned_r187_manifest_sha256=SOURCE_MANIFEST_SHA,not_blind_real=True,
        new_seed_generator_families_previously_used=True,
        profiles=MODES,repetitions=REPS))
    verify()
    print("R190_FREEZE_PASS",json.dumps({"cases":len(cases),
        "manifest_sha256":sha(FROZEN/"manifest.json")}),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==102,"manifest protocol/count")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"source SHA mismatched")
    return m["cases"]

def fingerprint(path):
    """Source-only first-2048-clause O(1)-memory gate; no family/labels."""
    start=time.perf_counter()
    n=m=0;total=three=two=horn=0
    with pathlib.Path(path).open() as f:
        for line in f:
            if line.startswith("p cnf "):
                a=line.split()
                need(len(a)==4,"missing DIMACS metadata")
                n,m=int(a[2]),int(a[3])
                break
        need(n>0 and m>0,"empty source")
        for line in f:
            if total>=2048:break
            line=line.strip()
            if not line or line.startswith("c"):continue
            a=[int(t) for t in line.split()]
            need(a and a[-1]==0,"broken DIMACS clause")
            lits=a[:-1];total+=1
            three+=len(lits)==3
            two+=len(lits)==2
            horn+=sum(x>0 for x in lits)<=1
    # These thresholds are fixed before any R190 outcome is observed.
    frac3=three/max(1,total)
    frac2=two/max(1,total)
    frac_horn=horn/max(1,total)
    ratio=m/max(1,n)
    profile="default";reason="conservative"
    if n<60 or m<400:
        reason="small_or_simple"
    elif frac_horn>=0.80 or frac2>=0.55:
        reason="horn_or_binary_default"
    elif frac3>=0.70 and ratio>=4.25:
        profile="unsat";reason="dense_ternary"
    elif frac3>=0.70 and ratio<=3.20:
        profile="sat";reason="sparse_ternary"
    else:
        reason="mixed_default"
    return profile,reason,round(time.perf_counter()-start,6),{
        "n":n,"m":m,"p3":round(frac3,4),"p2":round(frac2,4),
        "phorn":round(frac_horn,4),"density":round(ratio,4)}

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"smoke.cnf"
        p.write_text("p cnf 3 2\n1 2 0\n-1 3 0\n")
        profile,reason,t,features=fingerprint(p)
        need(profile=="default" and features["n"]==3 and t>=0,"small abstention")
        # Synthetic profiles: threshold functions must use only syntactic text.
        for density,want in ((3.0,"sat"),(5.0,"unsat")):
            n=100;m=int(n*density)
            p.write_text(f"p cnf {n} {m}\n"+("1 2 3 0\n"*m))
            found,_,_,_=fingerprint(p)
            need(found==want,"fixed generic profile router")
    print("R190_SELFTEST_PASS",flush=True)

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["sha256"],"source changed during paired trial")
    t=time.perf_counter()
    profile="default";reason="no_scan";screen=0;feats={}
    if mode in ("sat_profile","unsat_profile"):
        profile="sat" if mode=="sat_profile" else "unsat"
        reason="static_ablation"
    elif mode in ("router","router_shadow"):
        profile,reason,screen,feats=fingerprint(p)
        if mode=="router_shadow":profile="default"
    cap=c["cap_s"]
    left=cap-(time.perf_counter()-t)
    status="TIMEOUT";model={};stats=dict(conflicts=-1,decisions=-1,
                                        propagations=-1,learned=-1)
    if left>0.12:
        status,_,model,stats,_=old.native(binary,[p,left,profile],left,False)
    elapsed=time.perf_counter()-t
    if elapsed>=cap:status="TIMEOUT"
    proof="UNVERIFIED_CDCL_UNSAT" if status=="UNSAT" else "CAP"
    if status=="SAT":
        _,clauses=old.gf.dimacs(p)
        old.gf.sat_check(clauses,model)
        proof="SAT_WITNESS_CHECKED_ORIGINAL_CNF"
    if c["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==c["expected"],"expected original source answer disagrees")
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
        cohort=c["cohort"],cap_s=cap,mode=mode,rep=rep,
        profile=profile,reason=reason,scan_s=screen,
        features=feats,status=status,proof=proof,
        elapsed_s=round(elapsed,6),
        par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
        **stats)

def shard(index,binary):
    cases=verify()
    need(binary.is_file() and 0<=index<SHARDS,"binary/shard missing")
    trials=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=trial(c,mode,rep,binary)
                trials.append(r)
                save(ROOT/f"shard-{index}.json",trials)
                print("R190_TRIAL",json.dumps({k:r[k] for k in (
                    "id","cohort","mode","profile","status","elapsed_s",
                    "scan_s","conflicts")},sort_keys=True),flush=True)
    need(len(trials)==len(cases[index::SHARDS])*REPS*len(MODES),
         "incomplete shard")
    print("R190_SHARD_PASS",index,len(trials),flush=True)

def audit():
    cases=verify()
    rows=[]
    for index in range(SHARDS):
        part=read(ROOT/f"shard-{index}.json")
        need(len(part)==len(cases[index::SHARDS])*REPS*len(MODES),
             "incomplete shard audit")
        rows.extend(part)
    need(len(rows)==102*REPS*len(MODES),"not exactly 1020 paired runs")
    cases_by_sha={c["sha256"]:c for c in cases}
    groups=collections.defaultdict(list)
    for r in rows:
        need(r["sha256"] in cases_by_sha and
             r["id"]==cases_by_sha[r["sha256"]]["id"],"source drift")
        need(abs(r["par2_s"]-(2*r["cap_s"] if r["status"]=="TIMEOUT"
             else r["elapsed_s"]))<1e-5,"incorrect PAR2")
        groups[(r["sha256"],r["rep"])].append(r)
    for c in cases:
        for rep in range(REPS):
            rr=groups[c["sha256"],rep]
            need(len(rr)==len(MODES) and {x["mode"] for x in rr}==set(MODES),
                 "unpaired source/seed")
            need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
                 "contradictory solutions")
    cohorts={"all":cases}
    for cohort in ("reused_external_original","reused_synthetic_control","new_seed_synthetic"):
        cohorts[cohort]=[c for c in cases if c["cohort"]==cohort]
    for fam in gen.FAMILIES:
        cohorts["new:"+fam]=[c for c in cases if
            c["cohort"]=="new_seed_synthetic" and c["family"]==fam]
    result={}
    for name,subset in cohorts.items():
        d={}
        for mode in MODES:
            sample=[x for c in subset for rep in range(REPS)
                    for x in groups[c["sha256"],rep] if x["mode"]==mode]
            d[mode]=dict(attempts=len(sample),
                solved=sum(x["status"]!="TIMEOUT" for x in sample),
                sat=sum(x["status"]=="SAT" for x in sample),
                unsat=sum(x["status"]=="UNSAT" for x in sample),
                par2_s=round(sum(x["par2_s"] for x in sample),6),
                scan_s=round(sum(x["scan_s"] for x in sample),6),
                conflicts=sum(max(0,x["conflicts"]) for x in sample),
                used_sat=sum(x["profile"]=="sat" for x in sample),
                used_unsat=sum(x["profile"]=="unsat" for x in sample))
        result[name]={"formulas":len(subset),"modes":d,
            "clean_over_mode":{x:round(d["default"]["par2_s"]/d[x]["par2_s"],5)
                for x in MODES if x!="default"}}
    report=dict(protocol=PROTO,status="R190_PAIRED_AUDIT_PASS",
        formulas=len(cases),attempts=len(rows),reps=REPS,
        pinned_r187_manifest_sha256=SOURCE_MANIFEST_SHA,
        original_sat_witnesses_verified=True,
        non_GF2_UNSAT_no_independent_LRAT=True,
        reused_external_sources_not_blind=True,
        new_synthetic_seeds_not_new_families=True,
        no_claim_of_new_cdcl_algorithm=True,
        groups=result)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R190 — general CNF structural routing of CaDiCaL 2.1\n\n")
        f.write("Same pinned CaDiCaL, 38 previously seen frozen CNFs and 64 "
            "new-seed synthetic CNFs (same generator families). This is NOT "
            "blind general SAT validation. 2 repeats; 5 modes; source SHA checks. "
            "All runtime/probe overhead counted; SAT models independently checked. "
            "UNSAT from CaDiCaL has NO independent LRAT verification.\n\n")
        f.write("| Cohort | Mode | Solved | PAR2 s | Default/mode | Screen s |\n"
                "|---|---|---:|---:|---:|---:|\n")
        for cohort in ("reused_external_original","reused_synthetic_control",
                       "new_seed_synthetic","all"):
            s=result[cohort]
            for mode,d in s["modes"].items():
                f.write(f"| {cohort} | {mode} | {d['solved']}/{d['attempts']} | "
                    f"{d['par2_s']} | {s['clean_over_mode'].get(mode,'—')} | "
                    f"{d['scan_s']} |\n")
        f.write("\n**Critical:** A gain by fixed sat/unsat CaDiCaL settings is "
            "configuration tuning, not a novel algorithm. The router must beat "
            "both default and router_shadow on fresh real blind sources before "
            "any claim of general SAT benefit.\n")
    print("R190_FINAL",json.dumps({"groups":{k:result[k] for k in
        ("reused_external_original","new_seed_synthetic","all")}},
        sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="r190/r190-driver")
    args=ap.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="verify":
        print("R190_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="selftest":selftest()
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()

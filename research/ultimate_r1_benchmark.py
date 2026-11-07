#!/usr/bin/env python3
"""DRNAS Ultimate R1: frozen R153 certified GF(2), R160 structural routing,
R194 preserved dual-live CDCL; original SHA-pinned CNFs, paired source/rep tests.

45 UNIQUE originals: 25 R153/R195 overlapping historical cases, 12 R195
official 2026, 8 R197 official 2026 new-to-R195. THIS IS NOT A GLOBAL BLIND
HOLDOUT. No source selection based on outcomes or benchmark speed.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, os, pathlib
import platform, random, re, signal, statistics, subprocess, time

import r188_feedback_benchmark as helper

ROOT=pathlib.Path("ultimate_r1")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-ULTIMATE-R1-FROZEN-45-7ARM-2REP-SHA-20261107-v1"
MODES=("kissat","cadical3","cadical21_default","r153","r160","r194_dual","ultimate_r1")
REPS=2
SHARDS=9
CAPS={"historical_r153_r195":20.0,"official_r195_2026":30.0,
      "official_r197_2026":45.0}
SEEDS=(11,23)
R194_ID="20ca08f58828637815d93f46ef60b517"
R153_MANIFEST_PROTOCOL="DRNAS-R154-UNSEEN-LIGHTSOUT-XOR-UNIT-TRANSFER-20261105-v1"
R195_MANIFEST_PROTOCOL="DRNAS-R195-DUALKEEP-REAL-CAUSAL-PROSPECTIVE-20261107-v1"
R197_MANIFEST_PROTOCOL="DRNAS-R197-STATE-ABLATION-HOLDOUT-20261107-v1"
R153=ROOT/"source_r153"/"r153"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL3=pathlib.Path("built/bin/cadical_3_0_1")
CADICAL21=ROOT/"r194-compat"
R160=ROOT/"r160-dispatch"
ULTIMATE=ROOT/"ultimate-dispatch"

def need(condition,msg):
    if not condition: raise RuntimeError("ULTIMATE_R1_FAIL_CLOSED "+str(msg))
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def load(path):
    return json.loads(pathlib.Path(path).read_text())
def save(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
def cpu_model():
    path=pathlib.Path("/proc/cpuinfo")
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("model name"):return line.split(":",1)[1].strip()
    return platform.processor() or "unknown"

def freeze():
    old=ROOT/"source_r153"/"frozen"
    real=ROOT/"source_r195"/"frozen"
    prospective=ROOT/"source_r197"/"frozen"
    d153=load(old/"manifest.json")
    d195=load(real/"manifest.json")
    d197=load(prospective/"manifest.json")
    need(d153["protocol"]==R153_MANIFEST_PROTOCOL,"R153 source provenance")
    need(d195["protocol"]==R195_MANIFEST_PROTOCOL,"R195 source provenance")
    need(d197["protocol"]==R197_MANIFEST_PROTOCOL,"R197 source provenance")
    a153={c["id"]:c for c in d153["cases"]}
    historical=[c for c in d195["cases"] if c["cohort"]=="reused_real_r193"]
    official=[c for c in d195["cases"] if c["cohort"]=="new_r193_holdout_official_2026"]
    fresh=[c for c in d197["cases"] if c["cohort"]=="blind_new_to_R195_R196"]
    need(len(a153)==len(historical)==25 and len(official)==12 and len(fresh)==8,
         "archived source distribution changed")
    need({c["id"] for c in historical}==set(a153),
         "R153 pool not identical to R195 historical originals")
    need(R194_ID in a153,"R194 positive historical calibration case missing")
    cases=[]; seen=set()
    FROZEN.mkdir(parents=True,exist_ok=True)
    for cohort,subset,parent,key in (
        ("historical_r153_r195",historical,real,"original_sha256"),
        ("official_r195_2026",official,real,"original_sha256"),
        ("official_r197_2026",fresh,prospective,"sha")):
        for c in sorted(subset,key=lambda z:z[key]):
            digest=c[key];ident=c["id"]
            original=parent/(ident+".cnf")
            need(sha(original)==digest,"source archive corruption "+ident)
            need(digest not in seen and ident not in {x["id"] for x in cases},
                 "duplicate original SHA or identifier "+ident)
            if cohort=="historical_r153_r195":
                need(a153[ident]["sha256"]==digest
                     and sha(old/(ident+".cnf"))==digest,
                     "R153 and R195 original bytes disagree")
            (FROZEN/(ident+".cnf")).write_bytes(original.read_bytes())
            seen.add(digest)
            cases.append(dict(id=ident,sha256=digest,cohort=cohort,
               cap_s=CAPS[cohort],expected=c.get("expected","UNKNOWN"),
               family=a153[ident].get("family") if ident in a153 else "official2026",
               structural_cohort=a153[ident].get("cohort") if ident in a153 else "unknown",
               history="previously_used_not_globally_blind",
               source=c.get("source","archived_original")))
    need(len(cases)==45 and len(seen)==45,"unexpected cohort/source count")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        source_manifests_sha256={
           "r153":sha(old/"manifest.json"),"r195":sha(real/"manifest.json"),
           "r197":sha(prospective/"manifest.json")},
        overlap_removed=True,unique_sources=45,repetitions=REPS,modes=list(MODES),
        globally_blind=False,prospective_to_ultimate_r1=True,
        source_identity_never_used_by_policy=True,
        precommitted_selection="all 25 historical unique, all 12 R195 new, all 8 R197 new",
        no_rewriting_original_CNF=True))
    verify()
    print("ULTIMATE_FREEZE_PASS",json.dumps(dict(sources=45,attempts=45*REPS*len(MODES),
        manifest_sha=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    obj=load(FROZEN/"manifest.json")
    need(obj["protocol"]==PROTO and obj["unique_sources"]==45,"manifest protocol mismatch")
    cases=obj["cases"]
    need(len(cases)==45 and len({c["sha256"] for c in cases})==45,
         "original count or SHA duplicates")
    need(collections.Counter(c["cohort"] for c in cases)==
         {"historical_r153_r195":25,"official_r195_2026":12,"official_r197_2026":8},
         "cohort cardinality drift")
    for c in cases:
        need(c["cap_s"]==CAPS[c["cohort"]],"cap changed")
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original SHA drift "+c["id"])
    return cases

def replay_gf2_unsat(original,out):
    """Independent source-only replay of complete parity blocks and unit clauses."""
    n,clauses=helper.gf.dimacs(original)
    units={cl[0] for cl in clauses if len(cl)==1}
    blocks=collections.defaultdict(set)
    for clause in clauses:
        if not 2<=len(clause)<=6 or len({abs(x) for x in clause})!=len(clause):
            continue
        signed=sorted(clause,key=lambda x:abs(x))
        vs=tuple(abs(x) for x in signed)
        mask=sum(1<<i for i,x in enumerate(signed) if x<0)
        blocks[vs].add(mask)
    eq={}
    for line in out.decode(errors="replace").splitlines():
        m=re.fullmatch(r"c R28_EQ id=(\d+) rhs=([01]) vars=([\d,]+)",line)
        if not m:continue
        i=int(m[1]);rhs=int(m[2]);vs=tuple(map(int,m[3].split(",")))
        need(i not in eq and vs and len(set(vs))==len(vs)
             and all(0<v<=n for v in vs),"invalid XOR source equation")
        if len(vs)==1:
            need((vs[0] if rhs else -vs[0]) in units,"unproved unit")
        else:
            need(2<=len(vs)<=6 and vs==tuple(sorted(vs)),"invalid parity tuple")
            want={mask for mask in range(1<<len(vs))
                  if mask.bit_count()%2==1-rhs}
            need(want<=blocks[vs],"parity equation unsupported by original CNF")
        eq[i]=(rhs,vs)
    text=out.decode(errors="replace")
    cert=re.search(r"(?m)^c R28_UNSAT_CERT ids=([\d,]*)$",text)
    need(cert and "c R28_ROUTE certified_xor_contradiction" in text,
         "GF2 contradiction certificate absent")
    ids=[int(x) for x in cert[1].split(",") if x]
    need(ids and len(ids)==len(set(ids)) and all(i in eq for i in ids),
         "unknown/duplicate GF2 contradiction row")
    parity=0;bits=set()
    for i in ids:
        rhs,vs=eq[i];parity^=rhs
        for v in vs:
            if v in bits:bits.remove(v)
            else:bits.add(v)
    need(not bits and parity==1,"GF2 contradiction did not replay")
    return True

def parse_sat_model(out):
    model={}
    for line in out.decode(errors="replace").splitlines():
        if line.startswith("v "):
            for literal in map(int,line[2:].split()):
                if not literal:continue
                v=abs(literal);value=literal>0
                need(v not in model or model[v]==value,"SAT witness contradictory")
                model[v]=value
    need(model,"SAT result has no original model")
    return model

def call(mode,source,cap,seed,parity):
    commands={
      "kissat":[str(KISSAT.resolve()),str(source.resolve())],
      "cadical3":[str(CADICAL3.resolve()),str(source.resolve())],
      "cadical21_default":[str(CADICAL21.resolve()),str(source.resolve()),
                            str(cap),"default",str(parity),str(seed)],
      "r153":[str(R153.resolve()),str(source.resolve()),str(KISSAT.resolve())],
      "r160":[str(R153.resolve()),str(source.resolve()),str(R160.resolve())],
      "r194_dual":[str(CADICAL21.resolve()),str(source.resolve()),
                   str(cap),"dual_keep_default",str(parity),str(seed)],
      "ultimate_r1":[str(R153.resolve()),str(source.resolve()),str(ULTIMATE.resolve())]}
    env=os.environ.copy()
    env.update(ULTIMATE_CAP_S=str(cap),ULTIMATE_SEED=str(seed),
               ULTIMATE_PARITY=str(parity))
    start=time.perf_counter()
    proc=subprocess.Popen(commands[mode],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,env=env,start_new_session=True)
    watchdog=False
    try:
        out,err=proc.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        watchdog=True
        os.killpg(proc.pid,signal.SIGKILL)
        out,err=proc.communicate()
    elapsed=time.perf_counter()-start
    if watchdog or elapsed>=cap:return dict(status="TIMEOUT",elapsed_s=min(cap,elapsed),
        raw=out,stderr=err,returncode=proc.returncode,watchdog=watchdog)
    if proc.returncode==10:status="SAT"
    elif proc.returncode==20:status="UNSAT"
    elif proc.returncode==0 and b"R182_STATUS status=TIMEOUT" in out:
        status="TIMEOUT"
    else:
        need(False,f"{mode} native exit {proc.returncode}: "+err[-300:].decode(errors="replace"))
    if mode in ("cadical21_default","r194_dual"):
        need(b"R182_STATUS status="+status.encode() in out,
             "R194 status/returncode mismatch")
    return dict(status=status,elapsed_s=elapsed,raw=out,stderr=err,
        returncode=proc.returncode,watchdog=False)

def trial(c,rep,mode):
    source=FROZEN/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"source mutated during benchmark")
    cap=c["cap_s"]
    seed=SEEDS[rep]
    parity=int(hashlib.sha256((PROTO+c["sha256"]+str(rep)).encode()).hexdigest()[:2],16)%2
    v=call(mode,source,cap,seed,parity)
    status=v["status"]
    raw=v["raw"];reason="native";proof="CAP"
    route="none";decision_us=None;pilot_s=0.0
    if mode in ("r153","r160","ultimate_r1"):
        route=("gf2_sat" if b"R28_ROUTE certified_pure_xor_sat" in raw else
               "gf2_unsat" if b"R28_ROUTE certified_xor_contradiction" in raw else
               "fallback" if b"R28_ROUTE fallback" in raw else "timeout_or_unknown")
        timer=re.search(rb"c R153_DECISION_US (\d+)",raw)
        if timer:decision_us=int(timer[1])
    sm=re.search(rb"c (?:R160_SELECTOR|ULTIMATE_R1_SELECTOR) route=(\w+)",raw)
    if sm:reason=sm[1].decode()
    r194=re.search(rb"R193_DUAL choice=(default|sat) reason=(\w+) "
          rb"pilot_default_s=([0-9.]+) pilot_sat_s=([0-9.]+)",raw)
    if r194:pilot_s=float(r194[3])+float(r194[4])
    if status=="SAT":
        helper.gf.sat_check(helper.gf.dimacs(source)[1],parse_sat_model(raw))
        proof="SAT_WITNESS_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":
        if route=="gf2_unsat":
            replay_gf2_unsat(source,raw)
            proof="GF2_UNSAT_INDEPENDENT_SOURCE_REPLAY"
        else:proof="NATIVE_UNSAT_NOT_INDEPENDENT_LRAT"
    if c["expected"] in ("SAT","UNSAT") and status!="TIMEOUT":
        need(c["expected"]==status,"known original status contradiction")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
       family=c["family"],structural_cohort=c["structural_cohort"],rep=rep,
       mode=mode,seed=seed,parity=parity,cap_s=cap,status=status,
       elapsed_s=round(v["elapsed_s"],6),
       par2_s=round(2*cap if status=="TIMEOUT" else v["elapsed_s"],6),
       proof=proof,route=route,selector=reason,decision_us=decision_us,
       r194_pilot_s=round(pilot_s,6),watchdog=v["watchdog"],cpu=cpu_model())

def selftest():
    need(len(MODES)==7 and SHARDS==9 and REPS==2,"protocol mismatch")
    need(R194_ID=="20ca08f58828637815d93f46ef60b517","R194 calibration changed")
    ROOT.mkdir(exist_ok=True)
    print("ULTIMATE_SELFTEST_PASS",flush=True)

def shard(index):
    cases=verify()
    need(0<=index<SHARDS,"bad shard")
    pin=load(ROOT/"pin.json")
    for p,digest in pin["binaries"].items():
        need(sha(p)==digest,"binary pin drift "+p)
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode)
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("ULTIMATE_TRIAL",json.dumps({k:row[k] for k in
                 ("id","cohort","mode","rep","status","elapsed_s","par2_s",
                  "route","selector","decision_us","r194_pilot_s")},
                  sort_keys=True),flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(MODES),
         "short shard")
    print("ULTIMATE_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    pin=load(ROOT/"pin.json")
    need(sha(FROZEN/"manifest.json")==pin["manifest_sha"],
         "manifest SHA drift")
    rows=[]
    for i in range(SHARDS):
        data=load(ROOT/f"shard-{i}.json")
        need(len(data)==len(cases[i::SHARDS])*REPS*len(MODES),
             "incomplete shard "+str(i))
        rows+=data
    need(len(rows)==45*REPS*len(MODES),"trial count drift")
    cs={c["sha256"]:c for c in cases}
    grouped=collections.defaultdict(dict)
    for r in rows:
        c=cs.get(r["sha256"])
        need(c and r["id"]==c["id"] and r["cohort"]==c["cohort"],
             "source identity mismatch")
        key=(r["sha256"],r["rep"])
        need(r["mode"] not in grouped[key],"duplicate arm")
        grouped[key][r["mode"]]=r
        expected=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(expected-r["par2_s"])<1e-5,"PAR2 mismatch")
        if r["status"]=="SAT":
            need(r["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA","unchecked SAT")
        if r["route"]=="gf2_unsat" and r["status"]=="UNSAT":
            need(r["proof"]=="GF2_UNSAT_INDEPENDENT_SOURCE_REPLAY",
                 "unchecked GF2 proof")
    for k,arms in grouped.items():
        need(set(arms)==set(MODES),"missing arm in source/rep")
        need(len({r["cpu"] for r in arms.values()})==1,
             "paired run crossed CPU types")
        need(len({r["status"] for r in arms.values()
                  if r["status"]!="TIMEOUT"})<=1,"SAT/UNSAT contradiction")
        need(len({r["seed"] for r in arms.values()})==1,
             "seed pairing error")
    cohorts={"all":cases}
    for cohort in CAPS:cohorts[cohort]=[c for c in cases if c["cohort"]==cohort]
    summary={}
    for cname,subset in cohorts.items():
        summary[cname]={}
        selected={c["sha256"] for c in subset}
        for mode in MODES:
            sample=[r for r in rows if r["mode"]==mode and r["sha256"] in selected]
            summary[cname][mode]=dict(n=len(sample),
                solved=sum(r["status"]!="TIMEOUT" for r in sample),
                sat=sum(r["status"]=="SAT" for r in sample),
                unsat=sum(r["status"]=="UNSAT" for r in sample),
                par2_s=round(sum(r["par2_s"] for r in sample),6),
                gf2_decision_ms=round(sum((r["decision_us"] or 0)/1000 for r in sample),5),
                gf2_sat=sum(r["route"]=="gf2_sat" for r in sample),
                gf2_unsat=sum(r["route"]=="gf2_unsat" for r in sample),
                r194_dual_selected=sum(r["selector"]=="R194_DUAL" for r in sample),
                pilot_s=round(sum(r["r194_pilot_s"] for r in sample),6))
    comparisons={}
    for reference,candidate in (("kissat","r153"),("r153","r160"),
      ("r160","ultimate_r1"),("cadical21_default","r194_dual"),
      ("cadical3","ultimate_r1"),("kissat","ultimate_r1")):
        delta=[(arms[reference]["par2_s"]-arms[candidate]["par2_s"])
               for arms in grouped.values()]
        comparisons[candidate+"_vs_"+reference]=dict(
            reference=reference,candidate=candidate,
            paired_wins=sum(x>0.005 for x in delta),
            paired_losses=sum(x<-.005 for x in delta),
            paired_ties=sum(abs(x)<=.005 for x in delta),
            total_par2_gain_s=round(sum(delta),6))
    report=dict(status="ULTIMATE_R1_AUDIT_PASS_NONBLIND",protocol=PROTO,
       sources=45,paired_blocks=45*REPS,attempts=len(rows),
       original_sha_verified=True,unique_source_sha=True,
       original_CNF_unchanged=True,sat_witness_checked_original=True,
       gf2_unsat_source_replayed=True,native_unsat_lrat_missing=True,
       globally_blind=False,seed_note="R194 CaDiCaL 2.1 arms matched 11/23; "
           "Kissat, CaDiCaL 3.0.1, R153 and R160 use their frozen internal defaults",
       cpu_note="paired arms share each shard CPU; different shard models are not "
           "claimed to be identical",binary_pins=pin["binaries"],
       source_manifest_sha=pin["manifest_sha"],
       results=summary,comparisons=comparisons)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    with (ROOT/"all-trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    lines=["# DRNAS Ultimate R1 — source-paired 45 originals, 630 trials",
           "All original CNF SHA identities verified, **NOT global blind holdout**.",
           "25 historical R153/R195 overlaps counted only once; 12 R195 official "
           "and 8 R197 official 2026 originals. All settings frozen before trials.",
           "","| Cohort | Arm | Solved | PAR2 (s) | GF2 SAT/UNSAT | Dual selected |",
           "|---|---|---:|---:|---:|---:|"]
    for cohort,v in summary.items():
        for mode,s in v.items():
            lines.append(f"| {cohort} | {mode} | {s['solved']}/{s['n']} | "
              f"{s['par2_s']} | {s['gf2_sat']}/{s['gf2_unsat']} | {s['r194_dual_selected']} |")
    lines+=["","## Paired PAR-2 delta (positive favors candidate)","",
            "| Comparison | Wins | Losses | Ties | Net seconds |",
            "|---|---:|---:|---:|---:|"]
    for k,d in comparisons.items():
        lines.append(f"| {k} | {d['paired_wins']} | {d['paired_losses']} | "
                     f"{d['paired_ties']} | {d['total_par2_gain_s']} |")
    lines+=["","SAT models checked on original CNF; certified GF(2) UNSAT "
           "replayed from original source. Other native UNSAT lacks LRAT.",
           "No record or world-wide/general SAT speedup claims."]
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("ULTIMATE_FINAL",json.dumps(dict(status=report["status"],
      results=summary,comparisons=comparisons),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("ULTIMATE_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()

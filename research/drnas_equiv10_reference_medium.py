#!/usr/bin/env python3
"""DRNAS EQUIV10M: reference-conditioned EASY/MEDIUM original CNF benchmark.
Source hash/metadata and baseline Kissat (never Native) select cohort before
comparisons. SHA excludes repository visible GBD IDs and all EQUIV9 registries.
This is NOT a globally blind or uniform SAT Competition sample.
One logical CPU per solver, original SAT witnesses replayed, UNSAT requires
Kissat and CaDiCaL agreement, independently checked LRAT not produced.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,time

import drnas_equiv9_prospective_seed_holdout as e9
import mre7_reference_easy_freeze as fetch
import mre6b_blind_freeze as earlier

ROOT=pathlib.Path("mre_equiv10medium")
PROTO="DRNAS-EQUIV10M-REFERENCE-CONDITIONED-NEW-8SHA-ONECPU-v1"
SALT="DRNAS-EQUIV10M-20261110-SALT-FROZEN-BEFORE-DRNAS"
YEARS=("2024","2025")
ARMS=("native1","native_altseed","native_split4","kissat1","cadical301_default")
CAP=15.0
REPS=2
SHARDS=4
COUNT=8
EASY_MAX=1.0
MEDIUM_MAX=8.0
REFERENCE_MIN=0.04
QUOTA={"easy":4,"medium":4}
MAX_SCREEN=280
MAX_RAW=5*1024*1024
MAX_PLAIN=10*1024*1024

def need(cond,msg):
    if not cond:raise RuntimeError("EQUIV10M_FAIL_CLOSED "+str(msg))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def dump(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def indices():
    txt24=fetch.get(fetch.SRC24,120000).decode()
    txt25=fetch.get(fetch.SRC25,120000).decode()
    ids24=[p[0] for l in txt24.splitlines()[1:] if (p:=l.split()) and re.fullmatch(r"[0-9a-f]{32}",p[0])]
    ids25=[l.strip().rsplit("/",1)[-1] for l in txt25.splitlines() if l.strip()]
    need(len(ids24)>=350 and len(ids25)==400 and
         len(set(ids24))==len(ids24) and len(set(ids25))==len(ids25),
         "official index drift")
    return [(year,g) for year,ids in (("2024",ids24),("2025",ids25)) for g in ids],dict(
         official2024_sha=sha(txt24.encode()),official2025_sha=sha(txt25.encode()))
def reference_screen(path,clauses):
    begin=time.perf_counter()
    try:
        p=subprocess.run([str(e9.KISSAT.resolve()),str(path.resolve())],
              capture_output=True,text=True,timeout=MEDIUM_MAX+.15,check=False)
    except subprocess.TimeoutExpired:return dict(status="TIMEOUT",time_s=MEDIUM_MAX)
    dt=time.perf_counter()-begin
    need(p.returncode in (10,20),"unexpected Kissat reference exit "+str(p.returncode))
    st,verified=e9.x22.solver_result("kissat",p.returncode,p.stdout,clauses,{})
    if st=="UNSAT":
        try:
            q=subprocess.run([str(e9.CAD.resolve()),str(path.resolve())],
                     capture_output=True,text=True,timeout=MEDIUM_MAX+.2,check=False)
        except subprocess.TimeoutExpired:return dict(status="UNSAT_UNCONFIRMED",time_s=round(dt,6))
        if q.returncode!=20 or "s UNSATISFIABLE" not in q.stdout:
            return dict(status="UNSAT_UNCONFIRMED",time_s=round(dt,6))
    return dict(status=st,time_s=round(dt,6),SAT_original_witness_verified=verified,
                UNSAT_cross_solver_reference=(st=="UNSAT"))
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    e9.verify()
    allids,snapshot=indices()
    officialids={g for _,g in allids}
    repo_ids,repo_sha=earlier.inspect_repo_ids(officialids)
    oldsha,oldgbd,_=e9.registries()
    source_registry=json.loads(e9.ROOT.joinpath("manifest.json").read_text())["cases"]
    oldsha.update(c["sha256"] for c in source_registry)
    oldgbd.update(c["gbd"] for c in source_registry)
    exclude=repo_ids|oldgbd
    pool=sorted(((year,g) for year,g in allids if g not in exclude),
        key=lambda v:sha((SALT+"|"+v[0]+"|"+v[1]).encode()))
    trace=[];cases=[];counts=collections.Counter()
    fetch.prior.r32p.CNF_LIMIT=MAX_PLAIN
    for pos,(year,gbd) in enumerate(pool[:MAX_SCREEN]):
        if len(cases)==COUNT:break
        record=dict(rank=pos,year=year,gbd=gbd)
        p=e9.SOURCE/(gbd+".cnf")
        try:
            raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=18)
            plain,_=fetch.prior.r32p.decode(raw)
            need(len(plain)<=MAX_PLAIN,"plain byte budget")
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=20000 and 0<k<=85000,"CNF geometry budget")
            digest=sha(plain)
            need(digest not in oldsha and digest not in repo_sha,"historical original SHA collision")
            p.parent.mkdir(exist_ok=True,parents=True)
            p.write_bytes(plain)
            n2,clauses=e9.x22.read_cnf(p)
            need(n2==n and len(clauses)==k,"DIMACS mismatch")
            ref=reference_screen(p,clauses)
            record.update(sha256=digest,reference=ref)
            sec=ref["time_s"]
            band=("easy" if REFERENCE_MIN<=sec<EASY_MAX else
                  "medium" if EASY_MAX<=sec<=MEDIUM_MAX else "outside")
            if ref["status"] not in ("SAT","UNSAT"):
                record["reason"]="reference_not_confirmed_within_cap"
            elif band=="outside":
                record["reason"]="outside_preregistered_reference_band"
            elif counts[band]>=QUOTA[band]:
                record["reason"]="predeclared_band_quota_full"
            else:
                record["reason"]="READY";counts[band]+=1
                case=dict(year=year,gbd=gbd,filename=p.name,sha256=digest,
                    vars=n,clauses=k,cohort="holdout",reference_band=band,
                    reference_Kissat_s=sec,reference_status=ref["status"],
                    source_index_baseline_selection=True)
                cases.append(case)
                oldsha.add(digest)
        except Exception as e:
            record["reason"]="SOURCE_OR_REFERENCE_ERROR"
            record["detail"]=str(e)[:160]
        if record["reason"]!="READY":p.unlink(missing_ok=True)
        trace.append(record)
        print("EQUIV10M_SCREEN "+json.dumps(record,sort_keys=True),flush=True)
        dump(ROOT/"selection_progress.json",dict(attempted=len(trace),selected=len(cases),
            bands=dict(counts)))
    manifest=dict(protocol=PROTO,original_SAT_years=list(YEARS),
        not_globally_unseen=True,prior_registers_not_exhaustive=True,
        source_selection_is_reference_Kissat_conditioned=True,
        no_native_outcome_selection=True,selection_salt=SALT,
        observed_index_hashes=snapshot,attempted=len(trace),
        original_source_count=len(cases),expected_cases=COUNT,
        reference_bands_s=dict(easy=[REFERENCE_MIN,EASY_MAX],
             medium=[EASY_MAX,MEDIUM_MAX]),band_counts=dict(counts),
        caps_s=CAP,reps=REPS,shards=SHARDS,arms=list(ARMS),
        expected_trials=COUNT*REPS*len(ARMS),
        reference_solver_sha=e9.digest(e9.KISSAT),
        prior_E9_manifest_sha=e9.digest(e9.ROOT/"manifest.json"),
        code_sha=e9.digest(__file__),cases=cases,selection_trace=trace)
    dump(ROOT/"manifest.json",manifest)
    need(len(cases)==COUNT and all(counts[b]==QUOTA[b] for b in QUOTA),
         "insufficient predeclared 4 easy + 4 medium, no fabricated benchmark")
    verify()
    print("EQUIV10M_FREEZE_PASS "+json.dumps(dict(selected=len(cases),
         attempted=len(trace),bands=dict(counts),trials=manifest["expected_trials"]),
         sort_keys=True),flush=True)
def verify():
    e9.verify()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==COUNT and
         m["arms"]==list(ARMS) and m["code_sha"]==e9.digest(__file__) and
         m["prior_E9_manifest_sha"]==e9.digest(e9.ROOT/"manifest.json")
         and m["reference_solver_sha"]==e9.digest(e9.KISSAT),"manifest / binary drift")
    need(len({c["sha256"] for c in m["cases"]})==COUNT,"SHA duplicate")
    for c in m["cases"]:
        need(e9.digest(e9.SOURCE/c["filename"])==c["sha256"],"original CNF SHA drift")
    return m
def selftest():
    need(ARMS==tuple(a for a in ARMS if a in e9.ARMS),"unsupported arm")
    need(QUOTA["easy"]+QUOTA["medium"]==COUNT,"quota mismatch")
    print("EQUIV10M_SELFTEST_PASS",len(ARMS),flush=True)
def shard(idx):
    need(0<=idx<SHARDS,"invalid shard")
    m=verify();rows=[]
    for i,c in enumerate(m["cases"]):
        if i%SHARDS!=idx:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                r=e9.trial(c,rep,arm,CAP)
                need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                     "SAT model invalid original")
                r.update(protocol=PROTO,reference_band=c["reference_band"],shard=idx)
                rows.append(r)
                dump(ROOT/("shard-%d.json"%idx),rows)
                print("EQUIV10M_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==COUNT//SHARDS*REPS*len(ARMS),"incomplete shard")
    print("EQUIV10M_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=verify(); rows=[];per_shard={}
    for idx in range(SHARDS):
        a=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(a)==COUNT//SHARDS*REPS*len(ARMS),"incomplete shard "+str(idx))
        rows.extend(a)
    keys={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    need(len(rows)==len(keys)==len(expected) and keys==expected,
         "SHA matched trial matrix missing/duplicated")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["SAT_original_witness_verified"]==(r["status"]=="SAT")
             and r["status"] in ("SAT","UNSAT","TIMEOUT")
             and r["wall_E2E_s"]<=CAP+.08 and r["child_starts"]<=2,
             "record provenance or SAT verification invalid")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in bysha.items():
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT contradiction "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr) and
            any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT" for r in rr)):
            agreed.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def summarize(group):
        return dict(attempts=len(group),solved=sum(accepted(r) for r in group),
           SAT_original_verified=sum(r["status"]=="SAT" for r in group),
           UNSAT_reference_agreed_no_LRAT=sum(r["status"]=="UNSAT" and r["sha256"] in agreed for r in group),
           UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and r["sha256"] not in agreed for r in group),
           timeouts=sum(r["status"]=="TIMEOUT" for r in group),
           PAR2_s=round(sum(r["wall_E2E_s"] if accepted(r) else 2*CAP for r in group),6),
           child_CPU_s=round(sum(r["child_CPU_s"] for r in group),6),
           second_seed_SAT_solves=sum(r["status"]=="SAT" and len(r["stages"])==2 for r in group))
    scores={a:summarize([r for r in rows if r["arm"]==a]) for a in ARMS}
    base=scores["kissat1"]["PAR2_s"]
    for v in scores.values():v["speedup_vs_kissat_x"]=round(base/v["PAR2_s"],6)
    for idx in range(SHARDS):
        per_shard[str(idx)]={a:summarize([r for r in rows if r["arm"]==a and r["shard"]==idx]) for a in ARMS}
    by={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    paired={}
    for a in ARMS:
        if a=="kissat1":continue
        diffs=[(2*CAP if not accepted(by[(c["sha256"],rep,a)]) else by[(c["sha256"],rep,a)]["wall_E2E_s"])-(
                  2*CAP if not accepted(by[(c["sha256"],rep,"kissat1")]) else by[(c["sha256"],rep,"kissat1")]["wall_E2E_s"])
             for c in m["cases"] for rep in range(REPS)]
        paired[a]=dict(wins=sum(d<-.02 for d in diffs),
                       losses=sum(d>.02 for d in diffs),
                       ties=sum(abs(d)<=.02 for d in diffs),
                       max_regression_s=round(max(diffs),5),
                       max_gain_s=round(min(diffs),5))
    report=dict(protocol=PROTO,source_count=COUNT,year_bands=m["band_counts"],
       reference_only_selection=True,not_globally_blind=True,one_logical_cpu=True,
       independent_UNSAT_LRAT=False,source_SHA_verified=True,
       total_trials=len(rows),cap_s=CAP,reference_UNSAT_agreement_SHA=sorted(agreed),
       no_auto_promotion=True,scores=scores,per_shard=per_shard,paired=paired)
    dump(ROOT/"report.json",report)
    print("EQUIV10M_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("EQUIV10M_VERIFY_PASS",flush=True)

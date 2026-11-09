#!/usr/bin/env python3
"""DRNAS X14B: preregistered dual source-only gates against fresh-to-X14 originals.
24 official SAT 2024/2025 GBD CNFs, SHA-locked before any X14B trial, eight
arms, two paired seeds, original SAT witness checked, UNSAT cross-solver only,
15s full E2E PAR2, child CPU. This is NOT claimed globally unseen: recorded
prior registries are incomplete and the minisat1m label biases source sampling.
No retrospective X14 performance labels enter source eligibility.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,time,urllib.request
import drnas_x14_adaptive_portfolio as x14
import mre_x11_placebo_causal as x11
import mre_x13b_sample_gate as b
import mre7_extended_easy_freeze as pool
import mre6b_blind_freeze as prior

ROOT=pathlib.Path("mre_x14b")
SOURCES=ROOT/"sources"
PROTO="DRNAS-X14B-24-SAT24SAT25-SOURCE-FROZEN-8ARM-2REP-15S-E2E-v1"
SALT="DRNAS-X14B-FROZEN-SOURCE-ONLY-GBD-RANK-20261109-v1"
YEARS=("2024","2025")
YEAR_QUOTA=12
SHARDS,REPS,CAP=8,2,15.0
ARMS=("original","kissat","cadical","front100","parallel2",
      "x14_gate","x14b_cpu","x14b_wall")
EXPECTED=24*REPS*len(ARMS)
MAX_ATTEMPTS_PER_YEAR=105
MAX_RAW=9*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS,MAX_CLAUSES=70000,140000
PAR2_TIMEOUT=2*CAP

def need(v,msg):
    if not v:raise RuntimeError("X14B_FAIL_CLOSED "+str(msg))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(p,obj):
    path=pathlib.Path(p)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def configure():
    # X14 subprocess methods deliberately reuse pinned backends and full
    # original SAT witness replay. Only source root and experiment root change.
    b.CAP=CAP
    b.ROOT=ROOT
    x11.ROOT=SOURCES
    prior.r32p.CNF_LIMIT=MAX_PLAIN

def get(url,limit=MAX_RAW,seconds=20):
    request=urllib.request.Request(
        url,headers={"User-Agent":"DRNAS-X14B-Source-Only-Frozen/1.0"})
    with urllib.request.urlopen(request,timeout=seconds) as f:
        data=f.read(limit+1)
    need(len(data)<=limit,"source compressed download limit")
    return data

def policy(sig,mode):
    """Two preregistered choices independent of any measured X14B solver."""
    dup=int(sig["duplicates"])
    size=int(sig["size_bytes"])
    lines=int(sig["lines"])
    if mode=="x14b_cpu":
        if dup>=2: return "front100","duplicate_signal_cpu"
        if size>=1024*1024 and lines>=300:
            return "parallel2","large_unstructured_cpu"
        return "front100","cheap_cpu_single_core"
    need(mode=="x14b_wall","unknown X14B policy")
    if dup>=4 or size<=65536:
        return "front100","early_duplicate_or_tiny_wall"
    return "parallel2","race_for_uncertain_wall"

def backend_hashes():
    return x14.binary_hashes()

def freeze():
    configure()
    x11.ROOT=pathlib.Path("mre_x11")
    historic=x11.verify()
    x11.ROOT=SOURCES
    need(len(historic["cases"])==32,"historical source registry mismatch")
    old_gbd={c["gbd"] for c in historic["cases"]}
    old_sha={c["sha256"] for c in historic["cases"]}
    SOURCES.mkdir(parents=True,exist_ok=True)
    indexes={}
    candidates={}
    full_set=set()
    for year in YEARS:
        all_ids,all_hash=pool.getids("track=main_"+year)
        easy_ids,easy_hash=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(all_ids)==400 and len(set(all_ids))==400 and
             set(easy_ids)<=set(all_ids),"unexpected official GBD track index")
        full_set.update(all_ids)
        indexes[year]=dict(official_sha256=all_hash,mini_sha256=easy_hash,
                           count=400,mini_count=len(easy_ids))
        candidates[year]=(all_ids,easy_ids)
    known_ids,known_sha=prior.inspect_repo_ids(full_set)
    old_gbd.update(known_ids)
    old_sha.update(known_sha)
    if prior.PRIOR.exists():
        old_gbd.update(x.strip() for x in prior.PRIOR.read_text().splitlines()
                       if re.fullmatch("[0-9a-f]{32}",x.strip()))
    selected=[]
    trace=[]
    counts=collections.Counter()
    for year in YEARS:
        all_ids,mini_ids=candidates[year]
        mini=set(mini_ids)
        rank=lambda g:sha((SALT+"|"+year+"|"+g).encode())
        priority=sorted((g for g in mini if g not in old_gbd),key=rank)
        others=sorted((g for g in all_ids
                       if g not in old_gbd and g not in mini),key=rank)
        for rank_pos,g in enumerate((priority+others)[:MAX_ATTEMPTS_PER_YEAR]):
            if counts[year]>=YEAR_QUOTA:break
            p=SOURCES/(g+".cnf")
            note=dict(year=year,gbd=g,rank=rank_pos,
                      minisat1m_yes=g in mini,
                      chosen_before_benchmark=True)
            try:
                raw=get("https://benchmark-database.de/file/"+g)
                plain,compression=prior.r32p.decode(raw)
                need(len(plain)<=MAX_PLAIN,"plain byte budget")
                n,m=prior.r32p.parse_dimacs_metadata(plain)
                need(n<=MAX_VARS and m<=MAX_CLAUSES,
                     "source geometry outside precommitted limits")
                h=sha(plain)
                need(h not in old_sha,"known historical original source SHA")
                p.write_bytes(plain)
                parsed_n,clauses=x11.x9.x2.parse(p)
                need(parsed_n==n and len(clauses)==m,
                     "original DIMACS parser vs metadata mismatch")
                signal=b.cheap_duplicate_signal(p)
                old_policy,reason=x14.choose(signal)
                cpu_route,cpu_reason=policy(signal,"x14b_cpu")
                wall_route,wall_reason=policy(signal,"x14b_wall")
                c=dict(gbd=g,sha256=h,filename=p.name,cohort="source_only_sat24_25",
                    year=year,vars=n,clauses=m,bytes=len(plain),
                    compression=compression,rank=rank_pos,
                    source_url="https://benchmark-database.de/file/"+g,
                    minisat1m_yes=g in mini,
                    cheap_sample=signal,
                    frozen_gate_route=old_policy,frozen_gate_reason=reason,
                    x14b_cpu_route=cpu_route,x14b_cpu_reason=cpu_reason,
                    x14b_wall_route=wall_route,x14b_wall_reason=wall_reason)
                selected.append(c)
                old_gbd.add(g)
                old_sha.add(h)
                counts[year]+=1
                note.update(action="FROZEN_SOURCE_ONLY",sha256=h,vars=n,
                            clauses=m,size_bytes=len(plain))
            except Exception as exc:
                p.unlink(missing_ok=True)
                note.update(action="REJECTED_SIZE_OR_DOWNLOAD_OR_SHA",
                    error=(type(exc).__name__+": "+str(exc))[:200])
            trace.append(note)
            print("X14B_SOURCE",json.dumps(note,sort_keys=True),flush=True)
        need(counts[year]==YEAR_QUOTA,
             "source-only quota unfilled for "+year+
             " (no post-hoc runtime-based top-up)")
    need(len(selected)==24 and
         len({c["sha256"] for c in selected})==24 and
         len({c["gbd"] for c in selected})==24,"source quota or uniqueness")
    manifest=dict(protocol=PROTO,cases=selected,arms=ARMS,
        year_counts=dict(counts),source_indexes=indexes,
        source_sha_from_original_dimacs=True,
        source_rule="minisat1m=yes priority, fixed salted order, fixed geometry/size only",
        no_solver_or_feature_selection_bias_from_X14B_outcomes=True,
        source_sampling_metadata_conditioned_not_globally_blind=True,
        historical_registry_partial=True,
        prior_X11_source_exclusion=True,
        original_SAT_witness_replay_required=True,
        UNSAT_independent_LRAT=False,
        UNSAT_cross_solver_scoring_required=True,
        binary_sha256=backend_hashes(),
        ivalid_policy_tuning_after_freeze=False,
        no_auto_promotion=True,
        cap_s=CAP,reps=REPS,shards=SHARDS,
        expected_trials=EXPECTED,
        cpu_gate_thresholds=dict(duplicate_min=2,bytes_min=1048576,lines_min=300),
        wall_gate_thresholds=dict(duplicate_min=4,tiny_bytes=65536),
        old_X14_gate=x14.PROTO)
    save(ROOT/"manifest.json",manifest)
    save(ROOT/"selection-trace.json",trace)
    save(ROOT/"source.sha256",[]) if False else None
    (ROOT/"source.sha256").write_text(
        "".join(c["sha256"]+"  sources/"+c["filename"]+"\n" for c in selected))
    verify()
    print("X14B_FROZEN",json.dumps(dict(sources=len(selected),
         trials=EXPECTED,by_year=dict(counts),
         gate_cpu=dict(collections.Counter(c["x14b_cpu_route"] for c in selected)),
         gate_wall=dict(collections.Counter(c["x14b_wall_route"] for c in selected))),
         sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["expected_trials"]==EXPECTED and
         m["reps"]==REPS and len(m["cases"])==24,
         "frozen protocol source count/caps drift")
    need(backend_hashes()==m["binary_sha256"],"backend binary hash drift")
    counts=collections.Counter()
    for c in m["cases"]:
        p=SOURCES/c["filename"]
        need(p.is_file() and b.sha(p)==c["sha256"] and
             p.stat().st_size==c["bytes"],"original bytes/SHA drift")
        sig=b.cheap_duplicate_signal(p)
        need(sig==c["cheap_sample"],"cheap input sample changed")
        old,reason=x14.choose(sig)
        need((old,reason)==(c["frozen_gate_route"],c["frozen_gate_reason"]),
             "frozen X14 gate drift")
        for mode in ("x14b_cpu","x14b_wall"):
            r,reason=policy(sig,mode)
            need((r,reason)==(c[mode+"_route"],c[mode+"_reason"]),
                 "frozen X14B gate drift "+mode)
        counts[c["year"]]+=1
    need(all(counts[y]==YEAR_QUOTA for y in YEARS),"unexpected year balance")
    return m

def trial(c,rep,arm):
    need(arm in ARMS and rep in range(REPS),"bad mode or repeat")
    begin=time.perf_counter()
    sig=None
    reason="reference_arm"
    if arm in x14.ARMS:
        result=x14.trial(c,rep,arm)
    else:
        src=SOURCES/c["filename"]
        sig=b.cheap_duplicate_signal(src)
        need(sig==c["cheap_sample"],"policy source drift")
        route,reason=policy(sig,arm)
        need(route==c[arm+"_route"] and reason==c[arm+"_reason"],
             "precommitted gate route changed")
        sample_s=time.perf_counter()-begin
        result=x14.trial(c,rep,route)
        result["preprocess_s"]=round(result["preprocess_s"]+sample_s,6)
        result["profile_s"]=round(result["profile_s"]+sample_s,6)
        result["arm"]=arm
        result["route"]=route
        result["gate_reason"]=reason
    elapsed=time.perf_counter()-begin
    if elapsed>CAP:
        result["status"]="TIMEOUT"
        result["selected_backend"]=None
        result["SAT_original_witness_verified"]=False
    result.update(protocol=PROTO,year=c["year"],
        elapsed_s=round(elapsed,6),
        PAR2_s=round(elapsed if result["status"] in ("SAT","UNSAT")
                     else PAR2_TIMEOUT,6),
        source_cohort_prospective_to_X14B=True,
        historical_global_exclusion_incomplete=True)
    return result

def selftest():
    configure()
    b.selftest()
    for mode in ("x14b_cpu","x14b_wall"):
        for n in (0,1,2,4,25):
            for size in (20,65536,300000,1048576,3000000):
                for lines in (0,350):
                    route,why=policy(dict(duplicates=n,size_bytes=size,lines=lines),mode)
                    need(route in ("front100","parallel2") and why,"policy invalid")
    need(len(ARMS)==8 and REPS==2 and SHARDS==8 and EXPECTED==384,
         "paired 384 protocol mismatch")
    print("X14B_SELFTEST_PASS",flush=True)

def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"bad shard index")
    cc=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    need(len(cc)==3,"wrong 3 cases per shard")
    rows=[]
    for c in cc:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x11.seed(c,rep)).shuffle(order)
            for arm in order:
                result=trial(c,rep,arm)
                rows.append(result)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("X14B_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    need(len(rows)==48,"incomplete measured shard")
    print("X14B_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    cases={c["sha256"]:c for c in m["cases"]}
    rows=[]
    for idx in range(SHARDS):
        rows+=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
    expected={(s,r,a) for s in cases for r in range(REPS) for a in ARMS}
    actual={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==EXPECTED and actual==expected,
         "incomplete or duplicate original SHA paired trial")
    for s,c in cases.items():
        rr=[r for r in rows if r["original_sha256"]==s]
        statuses={r["status"] for r in rr if r["status"] in ("SAT","UNSAT")}
        need(len(statuses)<=1,"SAT/UNSAT contradiction")
        nat=any(r["status"]=="UNSAT" and r["selected_backend"]=="native" for r in rr)
        kis=any(r["status"]=="UNSAT" and r["selected_backend"]=="kissat" for r in rr)
        cad=any(r["status"]=="UNSAT" and r["selected_backend"]=="cadical" for r in rr)
        cross=(nat and (kis or cad)) or (kis and cad)
        for r in rr:
            need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
                 r["seed"]==x11.seed(c,r["rep"]) and r["cap_s"]==CAP and
                 r["source_SHA_verified"] and r["elapsed_s"]<=CAP+0.2,
                 "incorrect protocol/source/seed/time")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "unverified SAT witness")
            need(r["status"]!="TIMEOUT" or r["PAR2_s"]==PAR2_TIMEOUT,
                 "incorrect timeout penalty")
            need(r["status"]=="TIMEOUT" or
                 r["elapsed_s"]<=CAP and r["PAR2_s"]==r["elapsed_s"],
                 "incorrect solved E2E PAR2")
            r["accepted"]=(r["status"]=="SAT" or
                            r["status"]=="UNSAT" and cross)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else PAR2_TIMEOUT
    scores={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(n=len(rr),
          solved=sum(r["accepted"] for r in rr),
          SAT_verified=sum(r["accepted"] and r["status"]=="SAT" for r in rr),
          UNSAT_crosschecked=sum(r["accepted"] and r["status"]=="UNSAT" for r in rr),
          raw_timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
          PAR2_s=round(sum(r["audited_PAR2_s"] for r in rr),6),
          child_cpu_s=round(sum(r["child_cpu_s"] for r in rr),6),
          preprocessing_s=round(sum(r["preprocess_s"] for r in rr),6))
    for v in scores.values():
        for base in ("kissat","cadical","original","front100","parallel2"):
            v["pct_less_PAR2_vs_"+base]=round(
                100*(1-v["PAR2_s"]/scores[base]["PAR2_s"]),4)
            v["speedup_vs_"+base]=round(
                scores[base]["PAR2_s"]/v["PAR2_s"],5)
        v["CPU_ratio_vs_Kissat"]=round(
            v["child_cpu_s"]/max(1e-6,scores["kissat"]["child_cpu_s"]),4)
    result=dict(protocol=PROTO,trials=len(rows),source_count=len(cases),
       source_selection_not_globally_blind=True,
       X14B_source_only_precommitted=True,
       independent_unsat_LRAT=False,no_auto_promotion=True,
       scores=scores,rows=rows)
    save(ROOT/"report.json",result)
    print("X14B_FINAL",json.dumps({k:v for k,v in result.items()
              if k!="rows"},sort_keys=True),flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":
        verify()
        print("X14B_VERIFY_PASS",flush=True)
    elif args.action=="shard":shard(args.shard)
    else:audit()

if __name__=="__main__":main()

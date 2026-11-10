#!/usr/bin/env python3
"""DRNAS SEARCH6: 12 new SAT2024/25 originals, prespecified STRUCTURE-only strata.

No SAT, UNSAT, runtime or reference-oracle result is used to select a source.
Four strata, three SHA each by original binary-clause ratio:
  sparse [0,.15), medium [.15,.65), rich [.65,.94), dense [.94,1].
Past SHA/GBD registries, including SEARCH5 and SEARCH4, are excluded, but
they are not globally exhaustive: DO NOT claim globally blind.
Pinned same native CaDiCaL3.0.1 engine from SEARCH3. One logical CPU, original
CNF SAT model independently checked; UNSAT is double reference agreement
only, no independent LRAT. Native conflicts, decisions and search propagations
are collected and paired by exact SHA and two repeats. No auto-promotion.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,time
import drnas_search3_selective_e2e as s3
import drnas_search4_router_unseen as s4
import drnas_equiv13_structural_router as e13
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_search6")
SOURCE=ROOT/"cases"
MAN=ROOT/"manifest.json"
DRIVER=pathlib.Path("mre_search3/bin/search3_cadical")
FEATURES=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
PRIOR_S5=pathlib.Path("prior_hist/search5/mre_search5/manifest.json")
PRIOR_S4=pathlib.Path("prior_hist/search4/mre_search4_fresh/manifest.json")
PROTO="DRNAS-SEARCH6-SAT24-25-SOURCE-STRUCTURE-4STRATA-12SHA-9ARMS-2REP-12S-v1"
SALT="DRNAS-SEARCH6-20261110-STRUCTURE-ONLY-NO-SOLVER-SCREENING-v1"
STRATA=("sparse","medium","rich","dense")
COUNT=12
PER_STRATUM=3
SHARDS=6
REPS=2
CAP=12.0
MAX_SCAN=430
MAX_RAW=6*1024*1024
MAX_PLAIN=9*1024*1024
MAX_TOTAL=150*1024*1024
MAX_VARS=12000
MAX_CLAUSES=85000
ARMS=("cadical_unpatched","cadical_orig","cadical_preponly",
      "cadical_vmtf","cadical_evsids","cadical_both",
      "cadical_reverse","cadical_placebo","kissat_orig")
EXPECTED=COUNT*REPS*len(ARMS)
def need(ok,why):
 if not ok:raise RuntimeError("SEARCH6_FAIL_CLOSED "+str(why))
def digest(p):return e9.digest(p)
def save(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def stratum(binary):
 if binary<.15:return "sparse"
 if binary<.65:return "medium"
 if binary<.94:return "rich"
 return "dense"
def inputs_ready():
 for p in (DRIVER,FEATURES,CAD,KISSAT,PRIOR_S5,PRIOR_S4,
           pathlib.Path("mre_equiv6/manifest.json"),
           pathlib.Path("prior_search2/mre_equiv13/manifest.json")):
  need(p.is_file(),"frozen artifact missing "+str(p))
def code_hashes():
 return dict(code=digest(__file__),
  legacy_s3_engine=digest("research/drnas_search3_selective_e2e.py"),
  native_driver_cpp=digest("research/drnas_search3_cadical_driver.cpp"),
  exact_priority_cpp=digest("research/drnas_search1_guided_relabel.cpp"),
  legacy_s3_patch=digest("research/drnas_search3_patch_modes.py"),
  prior_search5=digest(PRIOR_S5),prior_search4=digest(PRIOR_S4),
  binaries={str(p):digest(p) for p in (DRIVER,FEATURES,CAD,KISSAT)})
def history():
 oldsha,oldids,historyreg=s4.old_registry()
 # These 2 cohorts MUST be excluded in full, not only a partial registry.
 for p in (PRIOR_S5,PRIOR_S4):
  m=json.loads(p.read_text())
  rows=m.get("original_cases",m.get("cases"))
  need(isinstance(rows,list) and len(rows)>=12,"historical manifest malformed "+str(p))
  need(all(c["sha256"] in oldsha and c["gbd"] in oldids for c in rows),
       "old SHA/GBD not excluded from registered set "+str(p))
 return oldsha,oldids,historyreg
def source_signals(n,clauses):
 # All SOURCE ONLY: literal binary implication SCC plus complete XOR-3 motifs.
 full=e13.source_signals(n,clauses)
 need(full["vars"]==n and full["clauses"]==len(clauses),
      "source feature geometry mismatch")
 condensed=s4.source_signals(n,clauses)
 need(full["binary_ratio"]==condensed["binary_ratio"],"feature conflict")
 full["reciprocal_binary_edges"]=condensed["reciprocal_binary_edges"]
 return full
def choose_initial():
 inputs_ready()
 ROOT.mkdir(parents=True,exist_ok=True);SOURCE.mkdir(parents=True,exist_ok=True)
 oldsha,oldids,historyreg=history()
 import mre7_extended_easy_freeze as listing
 import mre7_reference_easy_freeze as download
 indexes={};all_candidates=[]
 for year in ("2024","2025"):
  main,mainsha=listing.getids("track=main_"+year)
  easy,easysha=listing.getids("track=main_"+year+" and minisat1m=yes")
  need(len(main)==400 and set(easy)<=set(main),
       "official index changed "+year)
  indexes[year]=dict(main_sha=mainsha,easy_sha=easysha,
                     main_count=len(main),easy_count=len(easy))
  easyset=set(easy)
  all_candidates.extend((0,year,gbd) for gbd in easy if gbd not in oldids)
  all_candidates.extend((1,year,gbd) for gbd in main if gbd not in easyset and gbd not in oldids)
 # Exclude a documented prior R82 2025 selection pool even if individual
 # entries did not yield an archived original CNF.
 idx25,_=listing.getids("track=main_2025")
 R82=set(sorted(idx25,key=lambda g:hashlib.sha256(
  ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/"+g).encode()).hexdigest())[:220])
 all_candidates=[x for x in all_candidates if not(x[1]=="2025" and x[2] in R82)]
 # Selection entropy depends ONLY on frozen source identifiers, not solver.
 all_candidates=sorted(set(all_candidates),key=lambda x:(x[0],
    hashlib.sha256((SALT+"|"+x[1]+"|"+x[2]).encode()).hexdigest()))
 download.prior.r32p.CNF_LIMIT=MAX_PLAIN
 selected=[];trace=[];scanned=set();bucket=collections.Counter()
 year_count=collections.Counter();total=0
 for tier,year,gbd in all_candidates:
  if len(selected)>=COUNT:break
  if gbd in scanned:continue
  scanned.add(gbd)
  need(len(scanned)<=MAX_SCAN,
       "source-only structural candidate scan hit cap before stratification")
  p=SOURCE/(gbd+".cnf")
  record=dict(year=year,gbd=gbd,
              index_tier="minisat1m_yes" if tier==0 else "full_main")
  try:
   raw=download.get("https://benchmark-database.de/file/"+gbd,
                    MAX_RAW,seconds=20)
   plain,encoding=download.prior.r32p.decode(raw)
   need(0<len(plain)<=MAX_PLAIN and total+len(plain)<=MAX_TOTAL,
        "plain bytes cap")
   n,k=download.prior.r32p.parse_dimacs_metadata(plain)
   need(0<n<=MAX_VARS and 0<k<=MAX_CLAUSES,
        "fixed source geometry only, no outcome filter")
   sha=hashlib.sha256(plain).hexdigest()
   need(sha not in oldsha,"already registered historical CNF SHA")
   p.write_bytes(plain)
   pn,cls=x22.read_cnf(p)
   need(n==pn and k==len(cls),"original DIMACS geometry mismatch")
   signals=source_signals(n,cls)
   bucketname=stratum(signals["binary_ratio"])
   # Precommitted 3 per stratum, and <=8 sources from each year.
   need(bucket[bucketname]<PER_STRATUM and year_count[year]<8,
        "source stratum/year capacity already filled")
   selected.append(dict(year=year,gbd=gbd,filename=p.name,
      sha256=sha,bytes=len(plain),encoding=encoding,
      original_source_signals=signals,cohort=bucketname))
   bucket[bucketname]+=1;year_count[year]+=1;total+=len(plain)
   oldsha.add(sha);oldids.add(gbd)
   record.update(result="frozen",sha256=sha,bucket=bucketname,
                 vars=n,clauses=k,binary_ratio=signals["binary_ratio"],
                 scc_nontrivial_literal_nodes=signals["scc_nontrivial_literal_nodes"],
                 xor3_complete_patterns=signals["xor3_complete_patterns"])
  except Exception as e:
   p.unlink(missing_ok=True)
   record.update(result="source_only_excluded",
                 reason=(type(e).__name__+" "+str(e))[:190])
  trace.append(record)
  print("SEARCH6_SOURCE "+json.dumps(record,sort_keys=True),flush=True)
  save(ROOT/"source_progress.json",dict(selected=len(selected),
        buckets=dict(bucket),years=dict(year_count),
        inspected=len(scanned),trace=trace))
 need(len(selected)==COUNT and all(bucket[b]==PER_STRATUM for b in STRATA),
      "12 structurally balanced sources not found")
 need(len({c["sha256"] for c in selected})==COUNT,"duplicate original SHA")
 selected.sort(key=lambda c:c["sha256"])
 manifest=dict(protocol=PROTO,original_SHA_sources=selected,
  source_count=COUNT,arms=list(ARMS),reps=REPS,shards=SHARDS,
  cap_s=CAP,expected_trials=EXPECTED,strata=list(STRATA),
  quota_per_stratum=PER_STRATUM,source_hash_salt=SALT,
  selection_no_solver_or_result_screening=True,
  only_original_CNFs=True,source_only_features="binary ratio, horn, SCC and complete XOR3",
  official_years=dict(year_count),source_indexes=indexes,
  source_trace=trace,source_total_bytes=total,
  registered_history_sha=historyreg,
  not_globally_blind=True,prior_original_sha_excluded=True,
  one_logical_cpu_per_solver=True,all_preprocessing_E2E_charged=True,
  original_SAT_witness_verified=True,UNSAT_reference_agreement_no_LRAT=True,
  original_CNF_unchanged=True,no_auto_promotion=True,
  code_binary_hashes=code_hashes())
 save(MAN,manifest);verify()
 print("SEARCH6_FROZEN "+json.dumps(dict(SHA=COUNT,trials=EXPECTED,
  strata=dict(bucket),years=dict(year_count),
  xor_source_count=sum(c["original_source_signals"]["xor3_complete_patterns"]>0
                       for c in selected),
  SCC_source_count=sum(c["original_source_signals"]["scc_nontrivial_literal_nodes"]>0
                       for c in selected),
  SHA_no_old_registry_overlap=True,unseen_globally_not_claimed=True),
  sort_keys=True),flush=True)
def cases():
 return json.loads(MAN.read_text())["original_SHA_sources"]
def verify():
 inputs_ready()
 m=json.loads(MAN.read_text());cs=cases()
 need(m["protocol"]==PROTO and m["source_count"]==COUNT and
      m["arms"]==list(ARMS) and m["reps"]==REPS and
      m["cap_s"]==CAP and m["shards"]==SHARDS and
      m["expected_trials"]==EXPECTED and
      m["quota_per_stratum"]==PER_STRATUM and
      m["source_hash_salt"]==SALT and
      m["code_binary_hashes"]==code_hashes(),
      "frozen source, code or binary changed")
 oldsha,oldids,_=history()
 for c in cs:
  need(c["sha256"] not in oldsha and c["gbd"] not in oldids,
       "new formula collides with earlier registries")
  p=SOURCE/c["filename"]
  need(digest(p)==c["sha256"],"original SHA mutated")
  n,cl=x22.read_cnf(p)
  need(source_signals(n,cl)==c["original_source_signals"] and
       stratum(c["original_source_signals"]["binary_ratio"])==c["cohort"],
       "source-only structure changed")
 need(len(cs)==COUNT and len({c["sha256"] for c in cs})==COUNT and
      all(sum(c["cohort"]==b for c in cs)==PER_STRATUM for b in STRATA),
      "strata not fully frozen")
 return m
def seed(sha,rep):
 return int(hashlib.sha256((SALT+"|TRIAL|"+sha+"|"+str(rep)).encode()).hexdigest()[:15],16)
def one(c,rep,arm):
 need(arm in ARMS and rep in range(REPS),"unexpected trial arm/rep")
 s3.ROOT=ROOT/"native_temp"
 s3.ROOT.mkdir(exist_ok=True,parents=True)
 s3.SOURCE=SOURCE;s3.DRIVER=DRIVER;s3.PRIORITY=FEATURES
 s3.CAD=CAD;s3.KISSAT=KISSAT
 s3.ARMS=ARMS;s3.seed=seed
 # Reuse SEARCH3 proven arm modes without adding any new experimental logic.
 r=s3.one(dict(c,source_signals=c["original_source_signals"]),rep,arm,CAP)
 r["protocol"]=PROTO
 r["cohort"]=c["cohort"]
 r["SCC_nontrivial"]=c["original_source_signals"]["scc_nontrivial_literal_nodes"]
 r["xor3_patterns"]=c["original_source_signals"]["xor3_complete_patterns"]
 r["source_horn_ratio"]=c["original_source_signals"]["horn_ratio"]
 return r
def shard(i):
 verify();need(0<=i<SHARDS,"invalid shard")
 subset=[c for j,c in enumerate(cases()) if j%SHARDS==i]
 need(len(subset)==2,"shard must contain two originals")
 rows=[]
 for c in subset:
  for rep in range(REPS):
   arms=list(ARMS);random.Random(seed(c["sha256"],rep)).shuffle(arms)
   for arm in arms:
    r=one(c,rep,arm);r["shard"]=i
    need(r["original_sha_verified"] and r["wall_E2E_s"]<=CAP+.15 and
         (r["status"]!="SAT" or r["SAT_original_model_verified"]),
         "original CNF or witness not valid")
    rows.append(r)
    save(ROOT/("shard-%d.json"%i),rows)
    print("SEARCH6_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==2*REPS*len(ARMS),"missing source paired trials")
 print("SEARCH6_SHARD_PASS "+json.dumps(dict(
   shard=i,SHA=2,trials=len(rows),
   strata=sorted({c["cohort"] for c in subset})),sort_keys=True),flush=True)
def audit():
 m=verify()
 rows=[]
 for i in range(SHARDS):
  rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
  need(len(rr)==2*REPS*len(ARMS),"missing shard "+str(i))
  rows.extend(rr)
 expected={(c["sha256"],rep,arm) for c in cases()
           for rep in range(REPS) for arm in ARMS}
 found={(r["sha256"],r["rep"],r["arm"]) for r in rows}
 need(len(rows)==len(expected)==len(found)==EXPECTED and found==expected,
      "trial pairing changed or duplicate original")
 cohort={c["sha256"]:c for c in cases()}
 bysha=collections.defaultdict(list)
 for r in rows:
  c=cohort[r["sha256"]]
  need(r["protocol"]==PROTO and r["cohort"]==c["cohort"] and
    r["original_sha_verified"] and r["original_DIMACS_fed_to_CDCL"] and
    r["no_parallel_children"] and r["cap_s"]==CAP and
    r["wall_E2E_s"]<=CAP+.15 and r["status"] in ("SAT","UNSAT","TIMEOUT")
    and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
    "invalid E2E original SHA, CPU or SAT witness")
  if r["arm"] not in ("kissat_orig","cadical_unpatched"):
   d=r["actual_CDCL_telemetry"]
   need(isinstance(d,dict) and d["source_is_original_DIMACS"] and
        d["priority_mode_mask"]==r["mode_mask"] and
        d["initial_internal_priority_seed_count"]==
          (c["original_source_signals"]["vars"] if r["mode_mask"] else 0)
        and d["conflicts"]>=0 and d["decisions"]>=0 and
        d["search_propagations"]>=0,"native CDCL telemetry not valid")
  bysha[r["sha256"]].append(r)
 agreements=set()
 for sha,rr in bysha.items():
  known={r["status"] for r in rr if r["status"]!="TIMEOUT"}
  need(len(known)<=1,"SAT/UNSAT contradictory solver verdicts "+sha)
  if (any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr)
      and any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr)):
   agreements.add(sha)
 def accepted(r):
  return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreements)
 def p2(r):
  return r["wall_E2E_s"] if accepted(r) else 2*CAP
 def stat(rr):
  valid=[r["actual_CDCL_telemetry"] for r in rr
         if r["actual_CDCL_telemetry"] is not None]
  return dict(trials=len(rr),solved=sum(accepted(r) for r in rr),
   SAT_verified=sum(r["status"]=="SAT" for r in rr),
   UNSAT_cross_solver_no_LRAT=sum(r["status"]=="UNSAT" and accepted(r) for r in rr),
   UNSAT_unverified=sum(r["status"]=="UNSAT" and not accepted(r) for r in rr),
   TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rr),
   PAR2_s=round(sum(p2(r) for r in rr),6),
   E2E_wall_total_s=round(sum(r["wall_E2E_s"] for r in rr),6),
   CPU_solver_s=round(sum(r["child_CPU_s"] for r in rr),6),
   CPU_parent_s=round(sum(r["parent_CPU_s"] for r in rr),6),
   prep_E2E_s=round(sum(r["preparation_E2E_s"] for r in rr),6),
   native_CDCL_conflicts=sum(x["conflicts"] for x in valid),
   native_CDCL_decisions=sum(x["decisions"] for x in valid),
   native_CDCL_search_propagations=sum(x["search_propagations"] for x in valid))
 scores={a:stat([r for r in rows if r["arm"]==a]) for a in ARMS}
 for a in ARMS:
  scores[a]["PAR2_speedup_vs_unpatched_x"]=round(
    scores["cadical_unpatched"]["PAR2_s"]/scores[a]["PAR2_s"],6)
 per_stratum={bucket:{a:stat([r for r in rows if r["arm"]==a and
                                  cohort[r["sha256"]]["cohort"]==bucket])
                          for a in ARMS} for bucket in STRATA}
 paired={}
 for arm in ARMS:
  if arm=="cadical_unpatched":continue
  diffs=[]
  for sha,rr in bysha.items():
   for rep in range(REPS):
    orig=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
    exp=next(r for r in rr if r["arm"]==arm and r["rep"]==rep)
    diffs.append(p2(exp)-p2(orig))
  paired[arm]=dict(wins=sum(v<-.02 for v in diffs),
   ties=sum(abs(v)<=.02 for v in diffs),
   regressions=sum(v>.02 for v in diffs),
   best_gain_s=round(min(diffs),6),
   worst_regression_s=round(max(diffs),6))
 report=dict(protocol=PROTO,orig_SHA=COUNT,trials=EXPECTED,
  source_only_stratification=True,new_SHA_vs_registered_history=True,
  not_proven_globally_unseen=True,original_CNF_not_rewritten=True,
  SAT_original_model_independently_verified=True,
  UNSAT_reference_agreed_without_LRAT=sorted(agreements),
  one_logical_CPU_no_parallel_solver_children=True,
  instrumented_native_CDCL=True,no_automatic_promotion=True,
  score=scores,paired_vs_unpatched=paired,per_stratum=per_stratum,
  per_shard={str(i):{a:stat([r for r in rows if r["shard"]==i and r["arm"]==a])
                     for a in ARMS} for i in range(SHARDS)},
  per_SHA={sha:dict(gbd=cohort[sha]["gbd"],year=cohort[sha]["year"],
    cohort=cohort[sha]["cohort"],
    signals=cohort[sha]["original_source_signals"],
    arms={a:[dict(rep=r["rep"],status=r["status"],
        E2E_s=r["wall_E2E_s"],mode=r["mode_mask"],
        telemetry=r["actual_CDCL_telemetry"])
        for r in rr if r["arm"]==a] for a in ARMS})
       for sha,rr in bysha.items()})
 save(ROOT/"report.json",report)
 print("SEARCH6_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("freeze","verify","shard","audit"))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 if a.action=="freeze":choose_initial()
 elif a.action=="verify":verify();print("SEARCH6_VERIFY_PASS",flush=True)
 elif a.action=="shard":shard(a.shard)
 else:audit()

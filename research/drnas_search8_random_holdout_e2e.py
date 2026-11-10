#!/usr/bin/env python3
"""DRNAS SEARCH8 prospective new original SHA holdout for frozen SEARCH7 r03/r08.

The seed-generation ALGORITHM & labels are exactly SEARCH7's:
 SHA256(SEARCH7_SALT | NEW ORIGINAL SHA256 | random_03/08) first 15 hex;
random_01 is a prespecified negative/random control. Per-source maps are
SHA-locked BEFORE solver testing, and IDENTICAL across three repeats.
This tests transfer of the SEARCH7 family, NOT its old numeric seed on new CNFs.

16 new original SAT2024/25 SHA (4 each source-only binary structural stratum)
selected solely by pre-existing official GBD metadata & CNF geometry.
No reference solver pre-screen or incumbent benchmark outcome selection.
History excludes SEARCH4/5/6/7 and older registered cohorts, though not
every unindexed historical experiment => globally novel NOT established.
Native original CNF, one logical CPU per child, serial executions, 12s E2E.
SAT verified against original; UNSAT accepted only if original Kissat and
original unpatched CaDiCaL agree (no independent LRAT proof).
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,tempfile
import drnas_search2_direct_cdcl_e2e as s2
import drnas_search7_fixed_random_e2e as s7
import drnas_search6_stratified_e2e as s6
import drnas_search4_router_unseen as s4
import drnas_search3_selective_e2e as s3
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_search8")
SOURCE=ROOT/"cases"
MAN=ROOT/"manifest.json"
S6MAN=pathlib.Path("prior_hist/search6/mre_search6/manifest.json")
S4MAN=pathlib.Path("prior_hist/search4/mre_search4_fresh/manifest.json")
S5MAN=pathlib.Path("prior_hist/search5/mre_search5/manifest.json")
CAP=12.
COUNT=16
SHARDS=8
REPS=3
STRATA=("sparse","medium","rich","dense")
EACH=4
RANDOM_ARMS=("random_03","random_08","random_01")
ARMS=("cadical_unpatched","cadical_orig","cadical_preponly",
      "cadical_guided","kissat_orig")+RANDOM_ARMS
EXPECTED=COUNT*REPS*len(ARMS)
PROTO="DRNAS-SEARCH8-2024-25-SOURCE-BLIND-16SHA-R03R08-v1"
SALT="DRNAS-SEARCH8-SOURCEONLY-SHA-DISJOINT-20261110-v1"
MAX_SCAN=650
MAX_RAW=6*1024*1024
MAX_PLAIN=9*1024*1024
MAX_TOTAL=160*1024*1024
MAX_VARS=12000
MAX_CLAUSES=85000
DRIVER=pathlib.Path("mre_search3/bin/search3_cadical")
PRIORITY=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
def need(x,why):
 if not x:raise RuntimeError("SEARCH8_FAIL_CLOSED "+str(why))
def dig(path):return e9.digest(path)
def save(path,obj):
 p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def config_s7():
 # SEARCH7 code, seed salt and VMTF/EVSIDS masks remain untouched.
 s7.ROOT=ROOT
 s7.SOURCE=SOURCE
 s7.MAN=MAN
 s7.DRIVER=DRIVER;s7.FEATURES=PRIORITY;s7.CAD=CAD;s7.KISSAT=KISSAT
 s7.RANDOM_ARMS=RANDOM_ARMS;s7.ARMS=ARMS
 s7.PROTO=PROTO;s7.CAP=CAP;s7.REPS=REPS;s7.SHARDS=SHARDS
 s3.REPS=REPS;s3.CAP=CAP
 need(s7.SALT=="DRNAS-SEARCH7-20261110-10-FIXED-INDEPENDENT-SEEDS-SAME-REPS-v1",
      "SEARCH7 random seed identity changed")
def prereq():
 config_s7()
 for f in (DRIVER,PRIORITY,CAD,KISSAT,S6MAN,S4MAN,S5MAN,
           pathlib.Path("mre_equiv6/manifest.json"),
           pathlib.Path("prior_search2/mre_equiv13/manifest.json")):
  need(f.is_file(),"missing pinned binary / source registry "+str(f))
def hashes():
 return dict(search8_code=dig(__file__),
             original_SEARCH7_algorithm=dig("research/drnas_search7_fixed_random_e2e.py"),
             original_SEARCH6_structure=dig("research/drnas_search6_stratified_e2e.py"),
             original_SEARCH3_executor=dig("research/drnas_search3_selective_e2e.py"),
             native_CaDiCaL_CPP=dig("research/drnas_search3_cadical_driver.cpp"),
             ranking_CXX=dig("research/drnas_search1_guided_relabel.cpp"),
             past_manifests={str(f):dig(f) for f in (S4MAN,S5MAN,S6MAN)},
             native_binary_SHA={str(f):dig(f) for f in (DRIVER,PRIORITY,CAD,KISSAT)})
def history():
 oldsha,oldids,reg=s6.history()
 for p,field,need_count in ((S4MAN,"cases",16),
                            (S5MAN,"original_cases",12),
                            (S6MAN,"original_SHA_sources",12)):
  data=json.loads(p.read_text());cs=data[field]
  need(len(cs)==need_count,"prior source registry length changed "+str(p))
  oldsha.update(c["sha256"] for c in cs)
  oldids.update(c["gbd"] for c in cs)
 return oldsha,oldids,reg
def frozen_cases():
 m=json.loads(MAN.read_text())
 return m["original_SHA_sources"]
def _freeze_indices():
 import mre7_extended_easy_freeze as listing
 oldsha,oldids,oldreg=history()
 idx={};pool=[]
 for yr in ("2024","2025"):
  ids,idxsha=listing.getids("track=main_"+yr)
  easy,easysha=listing.getids("track=main_"+yr+" and minisat1m=yes")
  need(len(ids)==400 and set(easy)<=set(ids),
       "official GBD year index not as expected")
  idx[yr]=dict(main_index_SHA=idxsha,easy_index_SHA=easysha,
               original_count=len(ids),metadata_easy_count=len(easy))
  easyset=set(easy)
  pool.extend((0,yr,g) for g in easy if g not in oldids)
  pool.extend((1,yr,g) for g in ids if g not in easyset and g not in oldids)
 # Exclude older R82 2025 reservation. This is historical leakage
 # protection, NOT a filter using SEARCH8 performance.
 ids25,_=listing.getids("track=main_2025")
 oldR82=set(sorted(ids25,key=lambda g:hashlib.sha256(
   ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/"+g).encode()).hexdigest())[:220])
 pool=[v for v in pool if not(v[1]=="2025" and v[2] in oldR82)]
 pool=sorted(set(pool),key=lambda v:(v[0],hashlib.sha256(
   (SALT+"|"+v[1]+"|"+v[2]).encode()).hexdigest()))
 need(len(pool)>COUNT,"no source index candidates")
 return pool,idx,oldsha,oldids,oldreg
def rank_hashes(c):
 n,cl=x22.read_cnf(SOURCE/c["filename"])
 need(n==c["original_source_signals"]["vars"],
      "original dimension changed before ranking")
 ranks={}
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  for arm in RANDOM_ARMS+("cadical_guided",):
   mode="placebo" if arm in RANDOM_ARMS else "guided"
   fixed_seed=s7.seed(c["sha256"],arm) if arm in RANDOM_ARMS else 0
   path,_=s2.score_file(SOURCE/c["filename"],mode,fixed_seed,tmp,cl)
   ranks[arm]=dig(path)
 need(len(set(ranks.values()))==len(ranks)==4,
      "three fixed random mappings and guided map must all be distinct")
 return ranks
def freeze():
 prereq()
 ROOT.mkdir(parents=True,exist_ok=True);SOURCE.mkdir(parents=True,exist_ok=True)
 import mre7_reference_easy_freeze as grab
 pool,indexes,oldsha,oldids,registry=_freeze_indices()
 grab.prior.r32p.CNF_LIMIT=MAX_PLAIN
 trace=[];cases=[];counts=collections.Counter();peryear=collections.Counter()
 scanned=set();total=0
 for tier,year,gbd in pool:
  if len(cases)==COUNT:break
  if gbd in scanned:continue
  scanned.add(gbd)
  need(len(scanned)<=MAX_SCAN,"source scan cap before 4x4 structural quota")
  f=SOURCE/(gbd+".cnf")
  row=dict(year=year,gbd=gbd,
           index_tier="minisat1m_yes" if tier==0 else "full_main")
  try:
   raw=grab.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=20)
   plain,codec=grab.prior.r32p.decode(raw)
   need(0<len(plain)<=MAX_PLAIN and total+len(plain)<=MAX_TOTAL,
        "source byte geometry")
   n,k=grab.prior.r32p.parse_dimacs_metadata(plain)
   need(0<n<=MAX_VARS and 0<k<=MAX_CLAUSES,"source geometry limits")
   sha=hashlib.sha256(plain).hexdigest()
   need(sha not in oldsha,"SHA collides with prior original CNF")
   f.write_bytes(plain)
   nn,clauses=x22.read_cnf(f)
   need(nn==n and len(clauses)==k,"original DIMACS content parse")
   signals=s6.source_signals(n,clauses)
   bucket=s6.stratum(signals["binary_ratio"])
   need(counts[bucket]<EACH and peryear[year]<12,
        "precommitted structure or source-year quota already filled")
   c=dict(sha256=sha,gbd=gbd,year=year,filename=f.name,
          bytes=len(plain),codec=codec,cohort=bucket,
          original_source_signals=signals,selection_tier=row["index_tier"])
   cases.append(c);oldsha.add(sha);oldids.add(gbd)
   counts[bucket]+=1;peryear[year]+=1;total+=len(plain)
   row.update(result="frozen",sha256=sha,cohort=bucket,
              vars=n,clauses=k,binary_ratio=signals["binary_ratio"])
  except Exception as exc:
   f.unlink(missing_ok=True)
   row.update(result="source_only_excluded",
              reason=(type(exc).__name__+" "+str(exc))[:180])
  trace.append(row)
  print("SEARCH8_SOURCE "+json.dumps(row,sort_keys=True),flush=True)
  save(ROOT/"source_progress.json",dict(scanned=len(scanned),
          selected=len(cases),strata=dict(counts),
          years=dict(peryear),trace=trace))
 need(len(cases)==COUNT and all(counts[b]==EACH for b in STRATA),
      "source-only 4x4 structural cohort incomplete")
 need(len({c["sha256"] for c in cases})==COUNT,"duplicate original SHA")
 cases.sort(key=lambda c:c["sha256"])
 # Freeze and verify rank permutations for ALL new SHA, before any CDCL.
 rank_hashes={}
 for c in cases:
  maps=rank_hashes(c)
  need(len(set(maps[a] for a in RANDOM_ARMS))==3 and
       maps["cadical_guided"] not in {maps[a] for a in RANDOM_ARMS},
       "precommitted random ranking not unique from mathematical ranking")
  rank_hashes[c["sha256"]]=maps
  print("SEARCH8_MAP_FREEZE "+json.dumps(dict(sha256=c["sha256"],
        cohort=c["cohort"],r03=maps["random_03"],
        r08=maps["random_08"],control01=maps["random_01"],
        guided=maps["cadical_guided"],
        unique_rank_SHA=4),sort_keys=True),flush=True)
 m=dict(protocol=PROTO,original_SHA_sources=cases,
  source_count=COUNT,cap_s=CAP,shards=SHARDS,reps=REPS,
  arms=list(ARMS),random_order_arms=list(RANDOM_ARMS),
  expected_trials=EXPECTED,source_SALT=SALT,source_indexes=indexes,
  source_freeze_trace=trace,source_total_bytes=total,years=dict(peryear),
  frozen_structure_quota=dict(counts),
  fixed_permutation_algorithm="UNCHANGED SEARCH7 SHA256(S7_SALT|new_original_SHA|arm) first 15 hex",
  rank_hashes=rank_hashes,all_random_maps_source_only_precomputed=True,
  no_source_solver_screening=True,no_reference_outcome_used_to_select=True,
  SHA_disjoint_from_REGISTERED_history=True,
  history_not_globally_exhaustive=True,
  no_claim_globally_unseen=True,
  SEARCH7_R03_R08_preselected_on_older_SEARCH6_cohort=True,
  r01_random_negative_control=True,
  same_seed_per_original_sha_across_three_repetitions=True,
  one_CPU_sequential_native_CDCL=True,
  original_CNF_unchanged_and_SHA_verified=True,
  original_SAT_witness_verified=True,
  UNSAT_double_reference_agreement_no_LRAT=True,
  no_auto_promotion=True,hash_snapshot=hashes())
 save(MAN,m)
 verify()
 print("SEARCH8_FROZEN "+json.dumps(dict(SHA=len(cases),
      original_sha_exclude_prior_REGISTERED=True,
      strata=dict(counts),years=dict(peryear),
      fixed_random_rank_count=len(rank_hashes)*len(RANDOM_ARMS),
      repeats=REPS,arms=len(ARMS),trials=EXPECTED,
      not_globally_unseen_proven=True),sort_keys=True),flush=True)
def verify():
 prereq()
 m=json.loads(MAN.read_text());cs=frozen_cases()
 need(m["protocol"]==PROTO and m["source_count"]==COUNT
      and m["source_SALT"]==SALT and m["shards"]==SHARDS
      and m["reps"]==REPS and m["cap_s"]==CAP
      and m["arms"]==list(ARMS) and m["random_order_arms"]==list(RANDOM_ARMS)
      and m["expected_trials"]==EXPECTED and m["hash_snapshot"]==hashes(),
      "frozen protocol/binary digest drift")
 oldsha,oldids,_=history()
 need(len(cs)==COUNT and len({c["sha256"] for c in cs})==COUNT,
      "wrong SHA cardinality")
 need(all(sum(c["cohort"]==b for c in cs)==EACH for b in STRATA),
      "structural quota mutated")
 for c in cs:
  need(c["sha256"] not in oldsha and c["gbd"] not in oldids,
       "original SHA/GBD overlaps past registries")
  src=SOURCE/c["filename"]
  need(dig(src)==c["sha256"],"mutated original CNF")
  n,clauses=x22.read_cnf(src)
  need(s6.source_signals(n,clauses)==c["original_source_signals"]
       and s6.stratum(c["original_source_signals"]["binary_ratio"])==c["cohort"],
       "source-only structure mutated")
  ranks=m["rank_hashes"][c["sha256"]]
  need(set(ranks)==set(RANDOM_ARMS)|{"cadical_guided"} and
       len(set(ranks.values()))==4,
       "frozen permutation hashes missing or collide")
 return m
def one(c,rep,arm):
 need(0<=rep<REPS and arm in ARMS,"trial identity")
 config_s7()
 out=s7.one(c,rep,arm)
 need(out["protocol"]==PROTO and out["cap_s"]==CAP and
      out["original_sha_verified"] and
      out["original_DIMACS_fed_to_CDCL"] and
      out["wall_E2E_s"]<=CAP+.2 and out["no_parallel_children"] and
      (out["status"]!="SAT" or out["SAT_original_model_verified"]),
      "native CDCL original SHA E2E validation failed")
 return out
def shard(i):
 verify();need(0<=i<SHARDS,"bad shard index")
 cs=[c for j,c in enumerate(frozen_cases()) if j%SHARDS==i]
 need(len(cs)==2,"expected two SHA per shard")
 rows=[]
 for c in cs:
  for rep in range(REPS):
   order=list(ARMS)
   random.Random(int(hashlib.sha256(
    ("SEARCH8-TRIAL-ARM-ORDER|"+c["sha256"]+"|"+str(rep)).encode()
    ).hexdigest()[:14],16)).shuffle(order)
   for arm in order:
    r=one(c,rep,arm);r["shard"]=i
    rows.append(r);save(ROOT/("shard-%d.json"%i),rows)
    print("SEARCH8_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==2*REPS*len(ARMS),"incomplete shard")
 print("SEARCH8_SHARD_PASS "+json.dumps(dict(shard=i,SHA=2,
           trials=len(rows)),sort_keys=True),flush=True)
def audit():
 m=verify();rows=[]
 for i in range(SHARDS):
  rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
  need(len(rr)==2*REPS*len(ARMS),"incomplete paired shard "+str(i))
  rows.extend(rr)
 exp={(c["sha256"],rep,arm) for c in frozen_cases()
      for rep in range(REPS) for arm in ARMS}
 act={(r["sha256"],r["rep"],r["arm"]) for r in rows}
 need(len(rows)==len(exp)==len(act)==EXPECTED and exp==act,
      "missing SHA-paired trials")
 lookup={c["sha256"]:c for c in frozen_cases()}
 bysha=collections.defaultdict(list)
 for r in rows:
  sha=r["sha256"];arm=r["arm"]
  need(sha in lookup and arm in ARMS
       and r["protocol"]==PROTO and r["cap_s"]==CAP
       and r["original_sha_verified"] and r["original_DIMACS_fed_to_CDCL"]
       and r["no_parallel_children"] and r["one_logical_CPU"] is not None
       and r["wall_E2E_s"]<=CAP+.2
       and r["status"] in ("SAT","UNSAT","TIMEOUT")
       and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
       "bad trial SHA CPU verdict / model")
  if arm in RANDOM_ARMS+("cadical_guided",):
   need(r["fixed_rank_SHA"]==m["rank_hashes"][sha][arm],
        "rank map SHA differs from frozen map")
  if arm in RANDOM_ARMS:
   need(r["fixed_seed"]==s7.seed(sha,arm),
        "seed unexpectedly depends on repeat or new SHA outcome")
  if arm not in ("cadical_unpatched","kissat_orig"):
   t=r["actual_CDCL_telemetry"]
   need(t and t["source_is_original_DIMACS"] and
        t["priority_mode_mask"]==r["mode_mask"] and
        t["initial_internal_priority_seed_count"]==
          (lookup[sha]["original_source_signals"]["vars"] if r["mode_mask"] else 0),
        "not native CDCL actual priority")
  bysha[sha].append(r)
 agreed=set()
 for sha,rr in bysha.items():
  known={r["status"] for r in rr if r["status"]!="TIMEOUT"}
  need(len(known)<=1,"contradictory SAT and UNSAT original CNF verdicts")
  if any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr) and \
     any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr):
   agreed.add(sha)
 def accepted(r):
  return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
 def p2(r):return r["wall_E2E_s"] if accepted(r) else 2*CAP
 def stats(rs):
  m=[r["actual_CDCL_telemetry"] for r in rs if r["actual_CDCL_telemetry"]]
  return dict(trials=len(rs),solved=sum(accepted(r) for r in rs),
    SAT_original_verified=sum(r["status"]=="SAT" for r in rs),
    UNSAT_double_reference_no_LRAT=sum(r["status"]=="UNSAT" and accepted(r) for r in rs),
    UNSAT_no_reference=sum(r["status"]=="UNSAT" and not accepted(r) for r in rs),
    TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rs),
    PAR2_s=round(sum(p2(r) for r in rs),6),
    total_E2E_s=round(sum(r["wall_E2E_s"] for r in rs),6),
    prep_E2E_s=round(sum(r["preparation_E2E_s"] for r in rs),6),
    CDCL_conflicts=sum(t["conflicts"] for t in m),
    CDCL_decisions=sum(t["decisions"] for t in m),
    CDCL_search_propagations=sum(t["search_propagations"] for t in m))
 scores={a:stats([r for r in rows if r["arm"]==a]) for a in ARMS}
 base=scores["cadical_unpatched"]["PAR2_s"]
 for a in ARMS:scores[a]["PAR2_speedup_vs_original_x"]=round(base/scores[a]["PAR2_s"],6)
 paired={}
 for a in ARMS:
  if a=="cadical_unpatched":continue
  diff=[]
  for sha,rr in bysha.items():
   for rep in range(REPS):
    x=next(r for r in rr if r["arm"]==a and r["rep"]==rep)
    y=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
    diff.append(p2(x)-p2(y))
  paired[a]=dict(wins=sum(x<-.02 for x in diff),
     ties=sum(abs(x)<=.02 for x in diff),
     regressions=sum(x>.02 for x in diff),
     best_gain_s=round(min(diff),6),
     worst_regression_s=round(max(diff),6))
 stability={}
 for sha,rr in bysha.items():
  stat={}
  for a in RANDOM_ARMS:
   rs=sorted((r for r in rr if r["arm"]==a),key=lambda r:r["rep"])
   stat[a]=dict(solved_reps=sum(accepted(r) for r in rs),
    all_reps_verified=all(accepted(r) for r in rs),
    statuses=[r["status"] for r in rs],
    times_s=[r["wall_E2E_s"] for r in rs],
    rank_SHA=m["rank_hashes"][sha][a])
  stability[sha]=dict(cohort=lookup[sha]["cohort"],gbd=lookup[sha]["gbd"],
      binary_ratio=lookup[sha]["original_source_signals"]["binary_ratio"],
      seeds=stat)
 report=dict(protocol=PROTO,original_SHA_count=COUNT,
   E2E_trials=EXPECTED,proven_precommitted_r03r08_algorithm=True,
   source_selected_without_solver_outcome=True,
   original_SHA_not_in_REGISTERED_past=True,
   historical_registry_not_globally_exhaustive=True,
   source_structure_balanced_4x4=True,
   original_CNF_unchanged=True,one_logical_CPU=True,
   no_parallel_child_solver=True,
   SAT_independent_original_model_verification=True,
   UNSAT_two_reference_agreement_no_LRAT=sorted(agreed),
   no_promotion_without_further_independent_replication=True,
   scores=scores,paired_vs_original=paired,
   per_shard={str(i):{a:stats([r for r in rows if r["shard"]==i and r["arm"]==a])
                      for a in ARMS} for i in range(SHARDS)},
   per_stratum={b:{a:stats([r for r in rows if r["cohort"]==b and r["arm"]==a])
                    for a in ARMS} for b in STRATA},
   random_03_08_control_01_stability=stability,
   per_SHA={sha:dict(gbd=lookup[sha]["gbd"],
      stratum=lookup[sha]["cohort"],
      arms={a:[dict(rep=r["rep"],status=r["status"],
         E2E_s=r["wall_E2E_s"],CDCL_telemetry=r["actual_CDCL_telemetry"])
              for r in rr if r["arm"]==a] for a in ARMS})
       for sha,rr in bysha.items()})
 save(ROOT/"report.json",report)
 print("SEARCH8_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("freeze","verify","shard","audit"))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 if a.action=="freeze":freeze()
 elif a.action=="verify":verify();print("SEARCH8_VERIFY_PASS",flush=True)
 elif a.action=="shard":shard(a.shard)
 else:audit()

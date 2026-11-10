#!/usr/bin/env python3
"""DRNAS SEARCH7 ten independently preregistered fixed random orderings.

Reuse EXACT same 12 original SAT24/25 CNF SHA frozen in SEARCH6.
This is NOT blind or unseen relative to SEARCH6; it is a paired
follow-up designed to isolate the random-order effect.
Ten distinct mt19937_64 permutations per CNF; same exact permutation in
BOTH repeats; uniqueness proven by permutation SHA on each original.
Compare 10 fixed random priorities (VMTF+EVSIDS), one mathematical
guided order, original unpatched CaDiCaL, native CaDiCaL no guidance,
full feature-prep/no-op, original Kissat. Original CNF unchanged.
One logical CPU per child, no within-trial solver parallelism.
Every SAT model independently checked on original CNF.
UNSAT accepted for PAR2 only with Kissat+unpatched CaDiCaL agreement,
no independent LRAT. Cap fixed 12s; full preprocessing is E2E charged.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,tempfile
import drnas_search3_selective_e2e as s3
import drnas_search2_direct_cdcl_e2e as s2
import drnas_search6_stratified_e2e as s6
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_search7")
SOURCE=pathlib.Path("mre_search6/cases")
S6MAN=pathlib.Path("mre_search6/manifest.json")
MAN=ROOT/"manifest.json"
DRIVER=pathlib.Path("mre_search3/bin/search3_cadical")
FEATURES=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
PROTO="DRNAS-SEARCH7-FIXED-10-RANDOM-PERM-SAME-SHA-12SRC-15ARM-2REP-12S-v1"
SALT="DRNAS-SEARCH7-20261110-10-FIXED-INDEPENDENT-SEEDS-SAME-REPS-v1"
COUNT=12
SHARDS=6
REPS=2
CAP=12.
RANDOM_ARMS=tuple("random_%02d"%i for i in range(10))
ARMS=("cadical_unpatched","cadical_orig","cadical_preponly",
      "cadical_guided","kissat_orig")+RANDOM_ARMS
EXPECTED=COUNT*REPS*len(ARMS)
def need(ok,reason):
 if not ok:raise RuntimeError("SEARCH7_FAIL_CLOSED "+str(reason))
def dig(p):return e9.digest(p)
def save(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def seed(sha,arm):
 need(arm in RANDOM_ARMS,"seed only for random arms")
 # Deterministic on SHA+arm; deliberately does NOT include repeat index.
 return int(hashlib.sha256(
  (SALT+"|"+sha+"|"+arm).encode()).hexdigest()[:15],16)
def hashes():
 return dict(search7=dig(__file__),
   search6_code=dig("research/drnas_search6_stratified_e2e.py"),
   search3_executor=dig("research/drnas_search3_selective_e2e.py"),
   patched_native_cpp=dig("research/drnas_search3_cadical_driver.cpp"),
   permutation_cpp=dig("research/drnas_search1_guided_relabel.cpp"),
   search6_manifest=dig(S6MAN),
   binaries={str(f):dig(f) for f in (DRIVER,FEATURES,CAD,KISSAT)})
def inputs():
 for p in (S6MAN,DRIVER,FEATURES,CAD,KISSAT,
           pathlib.Path("mre_equiv6/manifest.json"),
           pathlib.Path("prior_search2/mre_equiv13/manifest.json"),
           pathlib.Path("prior_hist/search4/mre_search4_fresh/manifest.json"),
           pathlib.Path("prior_hist/search5/mre_search5/manifest.json")):
  need(p.is_file(),"missing historic original frozen artifact "+str(p))
def original_cases():
 data=json.loads(S6MAN.read_text())
 cs=data["original_SHA_sources"]
 need(data["protocol"]==s6.PROTO and len(cs)==COUNT,
      "SEARCH6 original frozen cohort changed")
 need(len({c["sha256"] for c in cs})==COUNT,
      "SEARCH6 source SHA duplicated")
 for c in cs:
  need(dig(SOURCE/c["filename"])==c["sha256"],
       "original SOURCE SHA mismatch before SEARCH7")
 return cs
def rank_hashes(c):
 n,cls=x22.read_cnf(SOURCE/c["filename"])
 need(n==c["original_source_signals"]["vars"],
      "source geometry mismatch")
 result={}
 with tempfile.TemporaryDirectory(dir=ROOT) as td:
  for arm in RANDOM_ARMS+("cadical_guided",):
   mode="placebo" if arm in RANDOM_ARMS else "guided"
   fixed_seed=seed(c["sha256"],arm) if arm in RANDOM_ARMS else 0
   p,_=s2.score_file(SOURCE/c["filename"],mode,fixed_seed,td,cls)
   result[arm]=dig(p)
 # SHA hashes are canonical map output and tested again during measurement.
 need(len(set(result[a] for a in RANDOM_ARMS))==10,
      "two supposedly independent random rankings are identical!")
 need(result["cadical_guided"] not in {result[a] for a in RANDOM_ARMS},
      "mathematical rank collided with random control")
 return result
def freeze():
 inputs();ROOT.mkdir(parents=True,exist_ok=True)
 cs=original_cases()
 permutation_hashes={}
 for c in cs:
  ranks=rank_hashes(c)
  permutation_hashes[c["sha256"]]=ranks
  print("SEARCH7_MAP_FREEZE "+json.dumps(dict(
   sha256=c["sha256"],gbd=c["gbd"],
   distinct_random_permutations=len(set(ranks[a] for a in RANDOM_ARMS)),
   math_rank_not_random=True),sort_keys=True),flush=True)
 m=dict(protocol=PROTO,source_count=COUNT,
   original_SHA_sources=cs,original_SHA_was_SEARCH6_NOT_BLIND=True,
   SHA_disjoint_from_previous_experiments=False,
   exactly_reuse_frozen_SEARCH6_original_SHA=True,
   source_strata=s6.STRATA,
   source_only_structure_frozen_before_SEARCH6_results=True,
   source_SHA_salt=SALT,random_order_arms=list(RANDOM_ARMS),
   random_seed_formula="SHA256(SALT|original_sha|random_arm) first 15 hex",
   same_random_permutation_in_both_repeats=True,
   ten_distinct_random_permutations_by_map_sha=True,
   rank_hashes=permutation_hashes,arms=list(ARMS),
   reps=REPS,shards=SHARDS,cap_s=CAP,expected_trials=EXPECTED,
   original_DIMACS_unchanged=True,
   direct_native_CaDiCaL_VMTF_and_EVSIDS=True,
   one_logical_CPU_each=True,paired_original_SHA=True,
   strict_PAR2_no_LRAT_FOR_UNSAT=True,
   SAT_original_model_verified=True,
   no_parallel_solver_children=True,no_auto_promotion=True,
   hash_snapshot=hashes())
 save(MAN,m)
 verify()
 print("SEARCH7_FROZEN "+json.dumps(dict(
   sources=COUNT,arms=len(ARMS),attempts=EXPECTED,
   ten_unique_per_SHA=True,same_rank_per_repeat=True,
   paired_source="prior_SEARCH6_SHA_12_not_blind",
   cap_s=CAP),sort_keys=True),flush=True)
def verify():
 inputs()
 m=json.loads(MAN.read_text());cs=original_cases()
 need(m["protocol"]==PROTO and m["original_SHA_sources"]==cs
      and m["source_count"]==COUNT and m["source_SHA_salt"]==SALT
      and m["arms"]==list(ARMS) and m["random_order_arms"]==list(RANDOM_ARMS)
      and m["reps"]==REPS and m["shards"]==SHARDS and m["cap_s"]==CAP
      and m["expected_trials"]==EXPECTED and m["hash_snapshot"]==hashes(),
      "frozen manifest changed")
 need(set(m["rank_hashes"])=={c["sha256"] for c in cs},
      "permutation SHA keys missing")
 for sha,r in m["rank_hashes"].items():
  need(set(r)==set(RANDOM_ARMS)|{"cadical_guided"} and
       len({r[a] for a in RANDOM_ARMS})==10 and
       r["cadical_guided"] not in {r[a] for a in RANDOM_ARMS},
       "rank uniqueness checks changed")
 return m
def arm_mode(arm,c):
 if arm in RANDOM_ARMS:return "placebo",3
 if arm=="cadical_guided":return "guided",3
 if arm=="cadical_preponly":return "guided",0
 return None,0
def one(c,rep,arm):
 need(arm in ARMS and rep in range(REPS),"bad trial index")
 # Only one solver child at a time. Wrap tested feature writer to check map SHA.
 s3.ROOT=ROOT/"native_temp";s3.ROOT.mkdir(parents=True,exist_ok=True)
 s3.SOURCE=SOURCE;s3.DRIVER=DRIVER;s3.PRIORITY=FEATURES
 s3.CAD=CAD;s3.KISSAT=KISSAT
 s3.ARMS=ARMS;s3.CAP=CAP;s3.arm_mode=arm_mode
 fixed_seed=seed(c["sha256"],arm) if arm in RANDOM_ARMS else 0
 s3.seed=lambda sha,rep: fixed_seed
 original_score_file=s2.score_file
 rank_observed=[]
 def checked_score_file(source,mode,used_seed,tmp,clauses):
  need(used_seed==fixed_seed,"repeat changed the fixed seed")
  path,summary=original_score_file(source,mode,used_seed,tmp,clauses)
  name=arm if arm in RANDOM_ARMS else "cadical_guided"
  actual=dig(path)
  need(actual==json.loads(MAN.read_text())["rank_hashes"][c["sha256"]][name],
       "permutation SHA differs from preregistered rank")
  rank_observed.append(actual)
  return path,summary
 s2.score_file=checked_score_file
 try:
  r=s3.one(dict(c,source_signals=c["original_source_signals"]),rep,arm,CAP)
 finally:
  s2.score_file=original_score_file
 r["protocol"]=PROTO;r["fixed_rank_SHA"]=rank_observed[0] if rank_observed else None
 r["fixed_seed"]=fixed_seed if arm in RANDOM_ARMS else None
 r["cohort"]=c["cohort"]
 r["mathematical_source_only_rank"]=arm=="cadical_guided"
 r["permutation_is_source_only_random"]=arm in RANDOM_ARMS
 need(arm not in RANDOM_ARMS or r["fixed_rank_SHA"] is not None,
      "random arm did not run verified map")
 return r
def shard(i):
 verify();need(i in range(SHARDS),"shard index")
 sources=[c for idx,c in enumerate(original_cases()) if idx%SHARDS==i]
 need(len(sources)==2,"shard source imbalance")
 rows=[]
 for c in sources:
  for rep in range(REPS):
   order=list(ARMS)
   random.Random(int(hashlib.sha256(
    ("SEARCH7_ORDER|"+c["sha256"]+"|"+str(rep)).encode()).hexdigest()[:14],16)).shuffle(order)
   for arm in order:
    r=one(c,rep,arm);r["shard"]=i
    need(r["original_sha_verified"] and r["original_DIMACS_fed_to_CDCL"]
         and r["wall_E2E_s"]<=CAP+.15
         and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
         "bad trial outcome or original model")
    rows.append(r);save(ROOT/("shard-%d.json"%i),rows)
    print("SEARCH7_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==2*REPS*len(ARMS),"shard incomplete")
 print("SEARCH7_SHARD_PASS "+json.dumps(dict(
  shard=i,SHA=2,trials=len(rows),unique_seed_count=10),sort_keys=True),flush=True)
def audit():
 m=verify();rows=[]
 for i in range(SHARDS):
  rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
  need(len(rr)==2*REPS*len(ARMS),"incomplete shard")
  rows+=rr
 expected={(c["sha256"],rep,a) for c in original_cases()
           for rep in range(REPS) for a in ARMS}
 found={(r["sha256"],r["rep"],r["arm"]) for r in rows}
 need(len(rows)==len(found)==len(expected)==EXPECTED and expected==found,
      "missing/duplicated pairing")
 bysha=collections.defaultdict(list)
 cohort={c["sha256"]:c for c in original_cases()}
 for r in rows:
  need(r["protocol"]==PROTO and r["one_logical_CPU"] is not None
       and r["no_parallel_children"] and r["original_sha_verified"]
       and r["original_DIMACS_fed_to_CDCL"] and r["cap_s"]==CAP
       and r["wall_E2E_s"]<=CAP+.15 and
       r["status"] in ("SAT","UNSAT","TIMEOUT")
       and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
       "invalid solver result")
  sha=r["sha256"];arm=r["arm"]
  if arm in RANDOM_ARMS or arm=="cadical_guided":
   need(r["fixed_rank_SHA"]==m["rank_hashes"][sha][arm],
        "random mathematical permutation changed")
  if arm in RANDOM_ARMS:
   need(r["fixed_seed"]==seed(sha,arm),"fixed seed changed")
  if arm not in ("cadical_unpatched","kissat_orig"):
   t=r["actual_CDCL_telemetry"]
   need(isinstance(t,dict) and t["source_is_original_DIMACS"] and
     t["initial_internal_priority_seed_count"]==
       (cohort[sha]["original_source_signals"]["vars"] if r["mode_mask"] else 0),
       "not a true original CNF native CDCL priority")
  bysha[sha].append(r)
 agreed=set()
 for sha,rr in bysha.items():
  known={r["status"] for r in rr if r["status"]!="TIMEOUT"}
  need(len(known)<=1,"SAT UNSAT contradiction on same original SHA")
  if any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr) and \
     any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr):
   agreed.add(sha)
 def accepted(r):
  return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
 def p2(r):
  return r["wall_E2E_s"] if accepted(r) else 2*CAP
 def stat(rr):
  telemetry=[r["actual_CDCL_telemetry"] for r in rr
             if r["actual_CDCL_telemetry"] is not None]
  return dict(attempts=len(rr),solved=sum(accepted(r) for r in rr),
   SAT_original_verified=sum(r["status"]=="SAT" for r in rr),
   UNSAT_original_ref_agreed_no_LRAT=sum(r["status"]=="UNSAT" and accepted(r) for r in rr),
   UNSAT_unverified=sum(r["status"]=="UNSAT" and not accepted(r) for r in rr),
   timeout=sum(r["status"]=="TIMEOUT" for r in rr),
   PAR2_s=round(sum(p2(r) for r in rr),6),
   E2E_total_s=round(sum(r["wall_E2E_s"] for r in rr),6),
   CPU_child_s=round(sum(r["child_CPU_s"] for r in rr),6),
   CPU_parent_s=round(sum(r["parent_CPU_s"] for r in rr),6),
   prep_s=round(sum(r["preparation_E2E_s"] for r in rr),6),
   CDCL_conflicts=sum(t["conflicts"] for t in telemetry),
   CDCL_decisions=sum(t["decisions"] for t in telemetry),
   CDCL_search_propagations=sum(t["search_propagations"] for t in telemetry))
 scores={arm:stat([r for r in rows if r["arm"]==arm]) for arm in ARMS}
 for arm in ARMS:
  scores[arm]["PAR2_speedup_vs_original_x"]=round(
    scores["cadical_unpatched"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
 paired={}
 for a in ARMS:
  if a=="cadical_unpatched":continue
  diff=[]
  for sha,rr in bysha.items():
   for rep in range(REPS):
    orig=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
    test=next(r for r in rr if r["arm"]==a and r["rep"]==rep)
    diff.append(p2(test)-p2(orig))
  paired[a]=dict(wins=sum(v<-.02 for v in diff),
    ties=sum(abs(v)<=.02 for v in diff),
    regressions=sum(v>.02 for v in diff),
    best_gain_s=round(min(diff),6),
    largest_regression_s=round(max(diff),6))
 # Exploration, not a permissible test-set-optimized solver strategy.
 per_SHA={}
 for sha,rr in bysha.items():
  status={}
  for arm in ARMS:
   a=sorted((r for r in rr if r["arm"]==arm),key=lambda r:r["rep"])
   status[arm]=[dict(rep=r["rep"],status=r["status"],E2E_s=r["wall_E2E_s"],
        rank_SHA=r["fixed_rank_SHA"],CDCL=r["actual_CDCL_telemetry"]) for r in a]
  per_SHA[sha]=dict(cohort=cohort[sha]["cohort"],
     vars=cohort[sha]["original_source_signals"]["vars"],
     binary_ratio=cohort[sha]["original_source_signals"]["binary_ratio"],
     gbd=cohort[sha]["gbd"],arms=status)
 stability={}
 for sha,rr in bysha.items():
  randoms=[r for r in rr if r["arm"] in RANDOM_ARMS]
  rmap={arm:[r for r in randoms if r["arm"]==arm] for arm in RANDOM_ARMS}
  stable=[arm for arm,rs in rmap.items() if len(rs)==REPS and
          all(accepted(r) for r in rs)]
  single=[arm for arm,rs in rmap.items() if sum(accepted(r) for r in rs)==1]
  stability[sha]=dict(random_stable_both_repeats=stable,
      random_only_one_repeat=single,
      random_no_solve=[a for a in RANDOM_ARMS if a not in stable+single],
      random_10_unique_map_SHA_verified=True)
 report=dict(protocol=PROTO,SHA=COUNT,attempts=EXPECTED,
   source_was_SEARCH6_frozen_not_blind=True,
   same_random_order_in_both_repeats=True,
   ten_unique_frozen_permutations_each_original_SHA=True,
   no_test_set_tuned_promotion=True,
   one_logical_CPU_per_solver=True,original_CNF_unchanged=True,
   SAT_original_model_independently_verified=True,
   accepted_UNSAT_original_double_reference_SHA=sorted(agreed),
   no_independent_UNSAT_LRAT=True,
   scores=scores,paired_vs_original=paired,
   per_shard={str(i):{a:stat([r for r in rows if r["shard"]==i and r["arm"]==a])
                      for a in ARMS} for i in range(SHARDS)},
   per_stratum={bucket:{a:stat([r for r in rows if r["cohort"]==bucket and r["arm"]==a])
                        for a in ARMS} for bucket in s6.STRATA},
   per_SHA=per_SHA,random_seed_stability=stability)
 save(ROOT/"report.json",report)
 print("SEARCH7_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("freeze","verify","shard","audit"))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 if a.action=="freeze":freeze()
 elif a.action=="verify":verify();print("SEARCH7_VERIFY_PASS",flush=True)
 elif a.action=="shard":shard(a.shard)
 else:audit()

#!/usr/bin/env python3
"""DRNAS SEARCH5 -- prospective original-CNF native CDCL guidance experiment.

Precommitted route based ONLY on original CNF binary/Horn graph:
dense non-reciprocal Horn-like => VMTF-only, mid sparse Horn => EVSIDS-only,
otherwise untouched CaDiCaL. Rule was selected after SEARCH3/SEARCH4 and is
tested on 12 NEW 2024/2025 SHA relative to available historical registries.
History is not globally exhaustive, so no global-blindness claim.
Pinned original native SEARCH3 driver; no original DIMACS mutation.
All running tests E2E one logical CPU; original-SAT witness verified; UNSAT is
included in strict PAR2 only with original Kissat + CaDiCaL agreement (no LRAT).
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,time
import drnas_search3_selective_e2e as s3
import drnas_search4_router_unseen as s4
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_search5")
SOURCE=ROOT/"cases"
MAN=ROOT/"manifest.json"
DRIVER=pathlib.Path("mre_search3/bin/search3_cadical")
PRIORITY=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
PREVIOUS4=pathlib.Path("prior_hist/mre_search4_fresh/manifest.json")
PROTO="DRNAS-SEARCH5-NATIVE-PROSPECTIVE-SOURCE-GATE-12SHA-10ARMS-2REPS-10S-v1"
SALT="DRNAS-SEARCH5-FRESH-2024-25-20261110-v1"
REPS=2
COUNT=12
SHARDS=6
CAP=10.
PILOT_CAP=5.
PILOT_COUNT=2
MAX_SCAN=320
MAX_RAW=6*1024*1024
MAX_PLAIN=9*1024*1024
MAX_VARS=12000
MAX_CLAUSES=80000
MAX_TOTAL_BYTES=120*1024*1024
ARMS=("cadical_unpatched","cadical_orig","cadical_preponly",
      "cadical_vmtf","cadical_evsids","cadical_both","cadical_reverse",
      "cadical_placebo","cadical_router","kissat_orig")
EXPECTED=COUNT*REPS*len(ARMS)
def need(cond,reason):
 if not cond:raise RuntimeError("SEARCH5_FAIL_CLOSED "+str(reason))
def digest(p):return e9.digest(p)
def dump(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def prerequisites():
 for p in (DRIVER,PRIORITY,CAD,KISSAT,PREVIOUS4,
    pathlib.Path("mre_equiv6/manifest.json"),
    pathlib.Path("prior_search2/mre_equiv13/manifest.json")):
  need(p.is_file(),"missing frozen input: "+str(p))
def rule(c):
 f=c["source_signals"]
 n=f["vars"];b=f["binary_ratio"];h=f["horn_ratio"]
 reciprocal=f["reciprocal_binary_edges"]
 # Regressions seen in SEARCH3/4 motivate the conservative no-seed fallback.
 # NO SEARCH5 outcomes used in making these choices.
 if .88<=b<=.94 and .85<=h and 400<=n<=5000 and reciprocal==0:
  return "vmtf"
 if .10<=b<=.18 and .35<=h<=.75 and 100<=n<=3500 and reciprocal==0:
  return "evsids"
 return "original"
def rulestring():
 return ("if .88<=binary<=.94 & horn>=.85 & 400<=vars<=5000 & reciprocal_edges=0: VMTF;"
         " elif .10<=binary<=.18 & .35<=horn<=.75 & 100<=vars<=3500 & reciprocal_edges=0: EVSIDS;"
         " else original; all thresholds preregistered before SEARCH5 freeze")
def signatures():
 return dict(code=digest(__file__),
             old_engine_code=digest("research/drnas_search3_selective_e2e.py"),
             original_native_driver=digest("research/drnas_search3_cadical_driver.cpp"),
             old_native_patch=digest("research/drnas_search3_patch_modes.py"),
             priority_generator_code=digest("research/drnas_search1_guided_relabel.cpp"),
             historical_source=digest(PREVIOUS4),
             binaries={str(p):digest(p) for p in (DRIVER,PRIORITY,CAD,KISSAT)})
def old_history():
 oldsha,oldids,reg=s4.old_registry()
 previous=json.loads(PREVIOUS4.read_text())
 need(len(previous["cases"])==16,"SEARCH4 previous cohort not 16 originals")
 shas={c["sha256"] for c in previous["cases"]}
 ids={c["gbd"] for c in previous["cases"]}
 need(shas<=oldsha and ids<=oldids,"SEARCH4 previous cohort not excluded")
 return oldsha,oldids,reg
def pilot_sha(cs):
 # Exactly two source-only extremes; no SAT/outcome screening.
 return sorted([min(cs,key=lambda c:(c["source_signals"]["binary_ratio"],c["sha256"]))["sha256"],
                max(cs,key=lambda c:(c["source_signals"]["binary_ratio"],c["sha256"]))["sha256"]])
def fetch_source():
 prerequisites()
 ROOT.mkdir(parents=True,exist_ok=True);SOURCE.mkdir(parents=True,exist_ok=True)
 oldsha,oldids,registry=old_history()
 import mre7_extended_easy_freeze as pool
 import mre7_reference_easy_freeze as fetch
 from collections import Counter
 idx={};candidates=[]
 for yr in ("2024","2025"):
  full,fullhash=pool.getids("track=main_"+yr)
  easy,easyhash=pool.getids("track=main_"+yr+" and minisat1m=yes")
  need(len(full)==400 and set(easy)<=set(full),"official index mismatch "+yr)
  idx[yr]=dict(main_sha=fullhash,easy_sha=easyhash,
                eligible_easy_count=len(easy),all_count=len(full))
  easyset=set(easy)
  candidates.extend((0,yr,gbd) for gbd in easy if gbd not in oldids)
  candidates.extend((1,yr,gbd) for gbd in full if gbd not in easyset and gbd not in oldids)
 # Prior R82 2025 random-220 selection is a historical exclusion, not source screening.
 ids25,_=pool.getids("track=main_2025")
 blocked=set(sorted(ids25,key=lambda g:hashlib.sha256(
   ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/"+g).encode()).hexdigest())[:220])
 candidates=[(t,yr,g) for t,yr,g in candidates if not(yr=="2025" and g in blocked)]
 candidates=sorted(set(candidates),key=lambda x:(x[0],
   hashlib.sha256((SALT+"|"+x[1]+"|"+x[2]).encode()).hexdigest()))
 fetch.prior.r32p.CNF_LIMIT=MAX_PLAIN
 cases=[];selected=Counter();seen=set();trace=[];total=0
 for tier,year,gbd in candidates:
  if len(cases)>=COUNT:break
  if selected[year]>=COUNT//2:continue
  if gbd in seen:continue
  seen.add(gbd);need(len(seen)<=MAX_SCAN,"source-only scan reached MAX_SCAN")
  p=SOURCE/(gbd+".cnf")
  row=dict(year=year,gbd=gbd,tier="minisat1m_yes" if tier==0 else "main_only")
  try:
   raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=20)
   plain,encoding=fetch.prior.r32p.decode(raw)
   need(len(plain)<=MAX_PLAIN and total+len(plain)<=MAX_TOTAL_BYTES,"source byte geometry")
   n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
   need(1<=n<=MAX_VARS and 1<=k<=MAX_CLAUSES,"CNF geometry cap")
   sha=hashlib.sha256(plain).hexdigest()
   need(sha not in oldsha,"original SHA reused from historical registry")
   p.write_bytes(plain)
   nn,cl=x22.read_cnf(p)
   need(nn==n and len(cl)==k,"original DIMACS parsing mismatched")
   signals=s4.source_signals(n,cl)
   c=dict(year=year,gbd=gbd,sha256=sha,filename=p.name,
          bytes=len(plain),encoding=encoding,source_signals=signals,
          source_only_route=rule(dict(source_signals=signals)),
          index_tier=row["tier"])
   cases.append(c);selected[year]+=1
   total+=len(plain);oldsha.add(sha);oldids.add(gbd)
   row.update(result="frozen",sha256=sha,route=c["source_only_route"],
              vars=n,clauses=k,binary_ratio=signals["binary_ratio"])
  except Exception as error:
   p.unlink(missing_ok=True)
   row.update(result="source_only_rejected",reason=str(error)[:180])
  trace.append(row)
  print("SEARCH5_SOURCE "+json.dumps(row,sort_keys=True),flush=True)
  dump(ROOT/"source_progress.json",dict(frozen=len(cases),
    scanned=len(seen),counts=dict(selected),trace=trace))
 need(len(cases)==COUNT and dict(selected)=={"2024":6,"2025":6},
      "could not freeze 6 original 2024 and 6 original 2025 SHA")
 cases.sort(key=lambda c:c["sha256"])
 need(len({c["sha256"] for c in cases})==COUNT and
      len(set(pilot_sha(cases)))==PILOT_COUNT,"duplicate original or pilot SHA")
 m=dict(protocol=PROTO,salt=SALT,original_years=dict(selected),
    original_source_index_sha=idx,
    source_count=COUNT,original_cases=cases,
    pilot_SHA=pilot_sha(cases),pilot_trials=PILOT_COUNT*len(ARMS),
    expected_trials=EXPECTED,cap_s=CAP,pilot_cap_s=PILOT_CAP,
    reps=REPS,shards=SHARDS,arms=list(ARMS),
    frozen_rule=rulestring(),
    source_selection_without_any_solver_outcome=True,
    no_outcome_tuning_after_pilot=True,
    registered_history_not_exhaustive=True,globally_blind=False,
    new_SHA_relative_to_registered_history=True,
    no_original_CNF_rewrite=True,one_logical_cpu_each=True,
    native_VMTF_EVSiDS_direct=True,
    original_SAT_witness_verified=True,
    original_UNSAT_reference_agreement_only_no_LRAT=True,
    no_auto_promotion=True,
    excluded_prior_SHA_count=len(oldsha)-COUNT,
    historical_registries=registry,
    freeze_trace=trace,source_total_bytes=total,
    code_binary_hashes=signatures())
 dump(MAN,m);verify()
 print("SEARCH5_FROZEN "+json.dumps(dict(
    SHA=COUNT,years=dict(selected),pilot_sha=m["pilot_SHA"],
    arms=len(ARMS),trials=EXPECTED,
    selected_modes=dict(collections.Counter(c["source_only_route"] for c in cases)),
    source_only_no_oracle=True,not_globally_blind=True),sort_keys=True),flush=True)
def cases():
 m=json.loads(MAN.read_text());return m["original_cases"]
def verify():
 prerequisites()
 m=json.loads(MAN.read_text());cs=cases()
 need(m["protocol"]==PROTO and m["salt"]==SALT and len(cs)==COUNT
      and m["expected_trials"]==EXPECTED and m["cap_s"]==CAP
      and m["pilot_cap_s"]==PILOT_CAP and m["reps"]==REPS
      and m["shards"]==SHARDS and m["arms"]==list(ARMS)
      and m["frozen_rule"]==rulestring()
      and m["code_binary_hashes"]==signatures()
      and m["pilot_SHA"]==pilot_sha(cs),"frozen SHA and code protocol drift")
 oldsha,oldids,_=old_history()
 for c in cs:
  p=SOURCE/c["filename"]
  need(digest(p)==c["sha256"] and c["sha256"] not in oldsha
       and c["gbd"] not in oldids,"SHA or GBD collision")
  n,clauses=x22.read_cnf(p)
  need(s4.source_signals(n,clauses)==c["source_signals"] and
       rule(c)==c["source_only_route"],"source-only feature mutation")
 return m
def seed(sha,rep):
 return int(hashlib.sha256((SALT+"|TRIAL|"+sha+"|"+str(rep)).encode()).hexdigest()[:16],16)
S3_ARM=s3.arm_mode
def mode(arm,c):
 if arm=="cadical_router":
  selection=rule(c)
  return ("guided",{"original":0,"vmtf":1,"evsids":2}[selection])
 return S3_ARM(arm,c)
def one(c,rep,arm,cap):
 need(arm in ARMS and rep in range(REPS) and cap in (CAP,PILOT_CAP),
      "unregistered arm or timing")
 s3.ROOT=ROOT/"native_temp";s3.ROOT.mkdir(exist_ok=True,parents=True)
 s3.SOURCE=SOURCE;s3.DRIVER=DRIVER;s3.PRIORITY=PRIORITY
 s3.CAD=CAD;s3.KISSAT=KISSAT
 s3.ARMS=ARMS;s3.arm_mode=mode
 r=s3.one(c,rep,arm,cap)
 r["protocol"]=PROTO
 r["source_only_route"]=c["source_only_route"]
 r["sha256"]=c["sha256"]
 return r
def pilot():
 m=verify();cs=[c for c in cases() if c["sha256"] in m["pilot_SHA"]]
 need(len(cs)==PILOT_COUNT,"pilot SHA missing")
 rows=[]
 for c in cs:
  for arm in ARMS:
   r=one(c,0,arm,PILOT_CAP)
   rows.append(r);dump(ROOT/"pilot.json",rows)
   print("SEARCH5_PILOT_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==PILOT_COUNT*len(ARMS),"pilot incomplete")
 print("SEARCH5_PILOT_PASS "+json.dumps(dict(
    SHA=len(cs),trials=len(rows),
    SAT_verified=sum(r["status"]=="SAT" for r in rows)),sort_keys=True),flush=True)
def shard(idx):
 verify();need(idx in range(SHARDS),"shard out of range")
 cs=[c for i,c in enumerate(cases()) if i%SHARDS==idx]
 need(len(cs)==2,"shard not 2 distinct SHA")
 rows=[]
 for c in cs:
  for rep in range(REPS):
   order=list(ARMS);random.Random(seed(c["sha256"],rep)).shuffle(order)
   for arm in order:
    r=one(c,rep,arm,CAP);r["shard"]=idx
    need(r["original_sha_verified"] and r["wall_E2E_s"]<=CAP+.1
         and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
         "invalid original SHA/model verification")
    rows.append(r);dump(ROOT/("shard-%d.json"%idx),rows)
    print("SEARCH5_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==2*REPS*len(ARMS),"missing attempts")
 print("SEARCH5_SHARD_PASS "+json.dumps(dict(
    shard=idx,SHA=len(cs),trials=len(rows)),sort_keys=True),flush=True)
def audit():
 m=verify();rows=[]
 for i in range(SHARDS):
  rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
  need(len(rr)==2*REPS*len(ARMS),"shard %d incomplete"%i)
  rows+=rr
 exp={(c["sha256"],rep,arm) for c in cases() for rep in range(REPS) for arm in ARMS}
 actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
 need(len(rows)==len(actual)==len(exp)==EXPECTED and actual==exp,
      "SHA pairing/duplication failure")
 cohort={c["sha256"]:c for c in cases()}
 bysha=collections.defaultdict(list)
 for r in rows:
  c=cohort[r["sha256"]]
  need(r["protocol"]==PROTO and r["source_only_route"]==rule(c)
       and r["original_sha_verified"] and r["cap_s"]==CAP
       and r["original_DIMACS_fed_to_CDCL"] and r["no_parallel_children"]
       and r["wall_E2E_s"]<=CAP+.1
       and r["status"] in ("SAT","UNSAT","TIMEOUT")
       and (r["status"]!="SAT" or r["SAT_original_model_verified"]),
       "invalid E2E/model/original source result")
  if r["arm"] not in ("kissat_orig","cadical_unpatched"):
   t=r["actual_CDCL_telemetry"]
   need(t and t["source_is_original_DIMACS"]
        and t["priority_mode_mask"]==r["mode_mask"]
        and t["initial_internal_priority_seed_count"]==
          (c["source_signals"]["vars"] if r["mode_mask"] else 0),
        "actual native CDCL activity mask mismatch")
  if r["arm"]=="cadical_router":
   need(r["mode_mask"]=={"original":0,"vmtf":1,"evsids":2}[rule(c)],
        "router not source-only")
  bysha[r["sha256"]].append(r)
 consensus=set()
 for sha,rr in bysha.items():
  valid={r["status"] for r in rr if r["status"]!="TIMEOUT"}
  need(len(valid)<=1,"solver SAT and UNSAT contradiction original SHA "+sha)
  if (any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr)
      and any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr)):
   consensus.add(sha)
 def ok(r):
  return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in consensus)
 def par(r):
  return r["wall_E2E_s"] if ok(r) else 2*CAP
 def summary(rr):
  t=[r["actual_CDCL_telemetry"] for r in rr
     if r["actual_CDCL_telemetry"] is not None]
  return dict(trials=len(rr),solved=sum(ok(r) for r in rr),
   SAT_original_verified=sum(r["status"]=="SAT" for r in rr),
   UNSAT_original_reference_agreement_no_LRAT=sum(r["status"]=="UNSAT" and ok(r) for r in rr),
   UNSAT_unverified=sum(r["status"]=="UNSAT" and not ok(r) for r in rr),
   timeout=sum(r["status"]=="TIMEOUT" for r in rr),
   PAR2_s=round(sum(par(r) for r in rr),6),
   total_wall_E2E_s=round(sum(r["wall_E2E_s"] for r in rr),6),
   total_child_CPU_s=round(sum(r["child_CPU_s"] for r in rr),6),
   total_parent_CPU_s=round(sum(r["parent_CPU_s"] for r in rr),6),
   total_prep_E2E_s=round(sum(r["preparation_E2E_s"] for r in rr),6),
   CDCL_conflicts=sum(x["conflicts"] for x in t),
   CDCL_decisions=sum(x["decisions"] for x in t),
   CDCL_search_propagations=sum(x["search_propagations"] for x in t))
 scores={a:summary([r for r in rows if r["arm"]==a]) for a in ARMS}
 for a in ARMS:
  scores[a]["speedup_vs_unpatched_PAR2_x"]=round(scores["cadical_unpatched"]["PAR2_s"]/scores[a]["PAR2_s"],6)
  scores[a]["speedup_vs_prep_only_PAR2_x"]=round(scores["cadical_preponly"]["PAR2_s"]/scores[a]["PAR2_s"],6)
 paired={}
 for a in ARMS:
  if a=="cadical_unpatched":continue
  diffs=[]
  for sha,rr in bysha.items():
   for rep in range(REPS):
    x=next(r for r in rr if r["arm"]==a and r["rep"]==rep)
    y=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
    diffs.append(par(x)-par(y))
  paired[a]=dict(wins=sum(x<-.02 for x in diffs),
    ties=sum(abs(x)<=.02 for x in diffs),
    regressions=sum(x>.02 for x in diffs),
    best_gain_s=round(min(diffs),6),
    worst_regression_s=round(max(diffs),6))
 result=dict(protocol=PROTO,SHA=COUNT,trials=EXPECTED,
  no_solver_outcome_source_selection=True,
  SHA_new_relative_to_registered_history=True,
  not_globally_blind=True,
  source_only_preregistered_router=True,
  true_native_CaDiCaL_VMTF_EVSIDS=True,
  independent_SAT_original_model_verification=True,
  UNSAT_double_reference_agreement_no_LRAT=True,
  accepted_UNSAT_sha=sorted(consensus),no_auto_promotion=True,
  route_frequencies=dict(collections.Counter(c["source_only_route"] for c in cases())),
  scores=scores,paired=paired,
  shards={str(i):{a:summary([r for r in rows if r["shard"]==i and r["arm"]==a])
     for a in ARMS} for i in range(SHARDS)},
  per_SHA={sha:dict(gbd=cohort[sha]["gbd"],year=cohort[sha]["year"],
   features=cohort[sha]["source_signals"],preregistered_route=rule(cohort[sha]),
   arms={a:[dict(status=r["status"],E2E_s=r["wall_E2E_s"],
           mode=r["mode_mask"],rep=r["rep"],
           CDCL_telemetry=r["actual_CDCL_telemetry"])
      for r in rr if r["arm"]==a] for a in ARMS})
     for sha,rr in bysha.items()})
 dump(ROOT/"report.json",result)
 print("SEARCH5_FINAL "+json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("freeze","verify","pilot","shard","audit"))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 if a.action=="freeze":fetch_source()
 elif a.action=="verify":verify();print("SEARCH5_VERIFY_PASS",flush=True)
 elif a.action=="pilot":pilot()
 elif a.action=="shard":shard(a.shard)
 else:audit()

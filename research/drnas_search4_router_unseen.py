#!/usr/bin/env python3
"""SEARCH4 router + prospective SEARCH3-HOLDOUT on mutually disjoint original CNFs.
Official SAT 2024/25 GBD MAIN source SHA, source-only preselection, no runtime
or solved-status screening. SHA-disjoint from SEARCH2/SEARCH3 and available old
registries, but NEVER claim globally unseen (past registries not exhaustive).
SEARCH3 old arms frozen and untouched; SEARCH4 rule fixed from old SEARCH3
evidence before ANY new SOURCE SAT/UNSAT result. Strict per-source reference
UNSAT cross-agreement (no independent LRAT). SAT witness on ORIGINAL CNF.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,sys,time
import drnas_search3_selective_e2e as s3
import drnas_search2_direct_cdcl_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_x22_parallel_reducer as x22
ROOT=pathlib.Path("mre_search4_fresh")
SOURCE=ROOT/"cases"
BIN=pathlib.Path("mre_search3/bin/search3_cadical")
FEATURES=pathlib.Path("mre_search2/bin/search1_relabel")
CAD=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
MAN=ROOT/"manifest.json"
PROTO="DRNAS-SEARCH4-AND-SEARCH3-HOLDOUT-2024-25-ORIG-SHA-PRESELECTED-v1"
SALT="DRNAS-SEARCH4-SEARCH3HOLDOUT-OFFICIAL2024-25-20261110-precommit-v1"
UPSTREAM="c60730422e758ef1cebe7aeddf2dda31c996bf04"
COUNT=16
SHARD_COUNT=4
REPS=2
CAP=10.0
MAX_SCAN=240
MAX_RAW=6*1024*1024
MAX_PLAIN=9*1024*1024
MAX_TOTAL=125*1024*1024
ARMS={
 "search3_holdout":("cadical_unpatched","cadical_orig","cadical_vmtf",
                    "cadical_evsids","cadical_both","cadical_reverse",
                    "cadical_placebo","kissat_orig"),
 "search4_router":("cadical_unpatched","cadical_orig","cadical_vmtf",
                   "cadical_reverse","cadical_router",
                   "cadical_placebo","kissat_orig")}
EXPECTED={g:COUNT//2*REPS*len(v) for g,v in ARMS.items()}
def need(ok,reason):
 if not ok:raise RuntimeError("SEARCH4_FRESH_FAIL_CLOSED "+str(reason))
def dig(p):return e9.digest(p)
def save(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def route(c):
 f=c["source_signals"]; b=f["binary_ratio"];n=f["vars"]
 # Frozen inference from already-seen SEARCH3 anomalies; no fresh outcomes.
 if b>=.9975 and 400<=n<=1500:return "vmtf"
 if .90<=b<.9975 and 400<=n<=5000:return "reverse"
 if .55<=b<=.75 and 1500<=n<=10000:return "reverse"
 return "original"
def need_mounted():
 for p in (BIN,FEATURES,CAD,KISSAT,
           pathlib.Path("mre_equiv6/manifest.json"),
           pathlib.Path("prior_search2/mre_equiv13/manifest.json")):
  need(p.is_file(),"missing pinned artifact "+str(p))
def old_registry():
 pths=[pathlib.Path("mre_equiv6/manifest.json"),
       pathlib.Path("prior_search2/mre_equiv13/manifest.json")]
 pths+=list(pathlib.Path("prior_hist").rglob("manifest.json"))
 pths=sorted(set(pths),key=str)
 need(len(pths)>=2,"missing historical manifests")
 sha=set();gbd=set();records=[]
 def visit(o):
  if isinstance(o,dict):
   for k,v in o.items():
    if k in ("sha256","original_sha256","source_sha256") and isinstance(v,str) and re.fullmatch("[0-9a-f]{64}",v):sha.add(v)
    if k in ("gbd","gbd_id","source_gbd") and isinstance(v,str) and re.fullmatch("[0-9a-f]{32}",v):gbd.add(v)
    visit(v)
  elif isinstance(o,list):
   for v in o:visit(v)
 for p in pths:
  raw=p.read_bytes();visit(json.loads(raw))
  records.append({"file":str(p),"sha256":hashlib.sha256(raw).hexdigest()})
 # Must explicitly include original SHA sets of SEARCH2 and SEARCH3.
 e6=json.loads(pathlib.Path("mre_equiv6/manifest.json").read_text())
 e13=json.loads(pathlib.Path("prior_search2/mre_equiv13/manifest.json").read_text())
 need(all(c["sha256"] in sha for c in e6["cases"]) and
      all(c["sha256"] in sha for c in e13["cases"]),
      "prior cohorts absent from registry set")
 return sha,gbd,records
def source_signals(n,clauses):
 k=len(clauses);need(n>0 and k>0,"empty original")
 binary=0;horn=0;edges=set()
 for c in clauses:
  horn+=sum(l>0 for l in c)<=1
  if len(c)==2:
   binary+=1;a,b=c
   if a!=b and a!=-b:
    edges.add((-a,b));edges.add((-b,a))
 mutual=sum((b,a) in edges for a,b in edges)//2
 return dict(vars=n,clauses=k,binary_ratio=round(binary/k,6),
             horn_ratio=round(horn/k,6),
             reciprocal_binary_edges=mutual)
def frozen_sources():
 m=json.loads(MAN.read_text())
 need(m["protocol"]==PROTO and len(m["cases"])==COUNT,"manifest drift")
 cs=m["cases"]
 need(len({c["sha256"] for c in cs})==COUNT and
      set(c["cohort"] for c in cs)==set(ARMS),
      "cohort duplicates")
 need(all(sum(c["cohort"]==g for c in cs)==COUNT//2 for g in ARMS),
      "cohort imbalance")
 for c in cs:
  p=SOURCE/c["filename"]
  need(dig(p)==c["sha256"],"original CNF mutated "+c["gbd"])
 return cs
def code_hashes():
 return dict(code=dig(__file__),
  original_driver=dig("research/drnas_search3_cadical_driver.cpp"),
  original_search3_engine=dig("research/drnas_search3_selective_e2e.py"),
  original_patch=dig("research/drnas_search3_patch_modes.py"),
  feature_cpp=dig("research/drnas_search1_guided_relabel.cpp"),
  source_binaries={str(p):dig(p) for p in (BIN,FEATURES,CAD,KISSAT)})
def freeze():
 need_mounted();ROOT.mkdir(parents=True,exist_ok=True)
 SOURCE.mkdir(parents=True,exist_ok=True)
 oldsha,oldids,registries=old_registry()
 import mre7_extended_easy_freeze as pool
 import mre7_reference_easy_freeze as fetch
 # The 2024/25 main index is selected BEFORE any SEARCH3/4 solver run.
 indexes={};candidates=[]
 for year in ("2024","2025"):
  allids,main_digest=pool.getids("track=main_"+year)
  easy,ec=pool.getids("track=main_"+year+" and minisat1m=yes")
  need(len(allids)==400 and set(easy)<=set(allids),
       "unexpected official 2024/25 index geometry "+year)
  indexes[year]=dict(all_SHA=main_digest,easy_SHA=ec,
                     count_all=len(allids),count_easy=len(easy))
  marked=set(easy)
  candidates.extend((0,year,id) for id in easy if id not in oldids)
  candidates.extend((1,year,id) for id in allids if id not in marked and id not in oldids)
 # Exclude historic R82 2025 pool of 220 cases by declared prior salt.
 ids25,_=pool.getids("track=main_2025")
 r82=set(sorted(ids25,key=lambda g:hashlib.sha256(
    ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/"+g).encode()).hexdigest())[:220])
 candidates=[p for p in candidates if not(p[1]=="2025" and p[2] in r82)]
 candidates=sorted(set(candidates),key=lambda x:(x[0],
       hashlib.sha256((SALT+"|"+x[1]+"|"+x[2]).encode()).hexdigest()))
 # No filtering by runtime, SAT/UNSAT, old outcome, or solver success.
 cs=[];trace=[];seen=set();total_bytes=0
 fetch.prior.r32p.CNF_LIMIT=MAX_PLAIN
 for tier,year,gbd in candidates:
  if len(cs)>=COUNT:break
  if gbd in seen:continue
  seen.add(gbd);need(len(seen)<=MAX_SCAN,"source candidate cap exceeded")
  row=dict(gbd=gbd,year=year,tier="minisat1m_yes" if tier==0 else "main_only")
  p=SOURCE/(gbd+".cnf")
  try:
   raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=20)
   plain,encoding=fetch.prior.r32p.decode(raw)
   need(len(plain)<=MAX_PLAIN and total_bytes+len(plain)<=MAX_TOTAL,"source byte budget")
   n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
   need(1<=n<=12000 and 1<=k<=80000,"source geometry too large")
   sha=hashlib.sha256(plain).hexdigest()
   need(sha not in oldsha,"registered historical original SHA")
   p.write_bytes(plain)
   nv,cl=x22.read_cnf(p)
   need(n==nv and k==len(cl),"exact original CNF parser mismatch")
   signals=source_signals(n,cl)
   cs.append(dict(gbd=gbd,year=year,sha256=sha,filename=p.name,
      bytes=len(plain),compression=encoding,index_tier=row["tier"],
      source_signals=signals))
   total_bytes+=len(plain);oldsha.add(sha);oldids.add(gbd)
   row.update(result="frozen",sha256=sha,vars=n,clauses=k)
  except Exception as err:
   p.unlink(missing_ok=True)
   row.update(result="source_only_excluded",reason=str(err)[:180])
  trace.append(row)
  print("SEARCH4_SOURCE "+json.dumps(row,sort_keys=True),flush=True)
  save(ROOT/"freeze_progress.json",dict(selected=len(cs),attempted=len(trace),
                                           candidates_scanned=len(seen),trace=trace))
 need(len(cs)==COUNT,"not enough original SHA sources without solver screening")
 # Pair-by-density then allocate alternately to SOURCE DISJOINT experiments.
 cs.sort(key=lambda c:(c["source_signals"]["binary_ratio"],c["sha256"]))
 for i,c in enumerate(cs):
  c["cohort"]="search3_holdout" if i%2==0 else "search4_router"
  c["preregistered_SEARCH4_route"]=route(c)
 cs.sort(key=lambda c:c["sha256"])
 save(MAN,dict(protocol=PROTO,source_count=COUNT,cases=cs,
    source_indexes=indexes,original_source_freeze_trace=trace,
    historical_sha_registries=registries,
    registered_prior_excluded_not_globally_exhaustive=True,
    no_global_novelty_claim=True,
    official_years=[2024,2025],source_only_index_minisat1m_priority=True,
    source_only_geometry_limit=[MAX_PLAIN,12000,80000],
    older_R82_2025_precommitted_220_excluded=True,
    no_solver_screening_for_selection=True,
    SHA_disjoint_between_cohorts=True,
    historical_search2_search3_sha_excluded=True,
    search4_policy="binary>=.9975 and 400<=vars<=1500 => VMTF; else .90<=binary<.9975 and 400<=vars<=5000 => reverse; else .55<=binary<=.75 and 1500<=vars<=10000 => reverse; else original",
    search3_prior_policies_unchanged=True,
    official_original_CNFs_unmodified=True,
    cap_s=CAP,reps=REPS,shards_each=SHARD_COUNT,
    arms={k:list(v) for k,v in ARMS.items()},
    expected_trials=EXPECTED,source_SHA_derived_before_solver_tests=True,
    original_SAT_witness_checked=True,
    UNSAT_reference_double_agreement_no_LRAT=True,
    one_CPU_no_solver_parallel=True,initial_CDCL_metrics_reported=True,
    no_auto_promotion=True,
    source_shas=[c["sha256"] for c in cs],
    code_hashes=code_hashes()))
 verify()
 print("SEARCH4_FROZEN "+json.dumps(dict(sources=len(cs),SHA_disjoint_groups=True,
    groups={g:sum(c["cohort"]==g for c in cs) for g in ARMS},
    expected_trials=EXPECTED,route_labels=dict(collections.Counter(
      c["preregistered_SEARCH4_route"] for c in cs if c["cohort"]=="search4_router")),
    not_globally_blind=True,original_SHA_checked=True),sort_keys=True),flush=True)
def verify():
 need_mounted()
 m=json.loads(MAN.read_text());cs=frozen_sources()
 need(m["protocol"]==PROTO and m["cap_s"]==CAP and m["reps"]==REPS
      and m["expected_trials"]==EXPECTED and m["shards_each"]==SHARD_COUNT
      and m["arms"]=={k:list(v) for k,v in ARMS}
      and m["code_hashes"]==code_hashes()
      and m["source_shas"]==[c["sha256"] for c in cs],
      "code, binaries, cohort or SHA changed")
 for c in cs:
  n,cls=x22.read_cnf(SOURCE/c["filename"])
  need(source_signals(n,cls)==c["source_signals"] and
       route(c)==c["preregistered_SEARCH4_route"],
       "SOURCE features/routing mutated")
 return m
def seed(sha,rep):return int(hashlib.sha256(
 (SALT+"|TRIAL|"+sha+"|"+str(rep)).encode()).hexdigest()[:15],16)
S3_ORIGINAL_ARM_MODE=s3.arm_mode
def _arm_mode(arm,c):
 if arm=="cadical_router":
  choice=route(c)
  return {"original":("guided",0),"vmtf":("guided",1),
          "reverse":("reverse",3)}[choice]
 return S3_ORIGINAL_ARM_MODE(arm,c)
def solve(c,rep,arm):
 s3.ROOT=ROOT/"native_temp";s3.ROOT.mkdir(parents=True,exist_ok=True)
 s3.SOURCE=SOURCE;s3.DRIVER=BIN;s3.PRIORITY=FEATURES
 s3.CAD=CAD;s3.KISSAT=KISSAT
 s3.ARMS=ARMS[c["cohort"]]
 s3.arm_mode=_arm_mode
 row=s3.one(c,rep,arm,CAP)
 # All original VMTF and EVSIDS modes fixed (SEARCH3 code unchanged).
 row["protocol"]=PROTO
 row["cohort"]=c["cohort"]
 row["search4_rule"]=c["preregistered_SEARCH4_route"]
 row["original_sha256"]=c["sha256"]
 row["actual_native_CDCL"]=arm not in ("cadical_unpatched","kissat_orig")
 row["source_selected_gate"]=(route(c)!="original")
 return row
def shard(group,idx):
 verify();need(group in ARMS and 0<=idx<SHARD_COUNT,"invalid cohort/shard")
 selected=[c for c in frozen_sources() if c["cohort"]==group]
 selected.sort(key=lambda x:x["sha256"])
 cases=[c for i,c in enumerate(selected) if i%SHARD_COUNT==idx]
 need(len(cases)==2,"cohort shard is not two SHA")
 rows=[]
 for c in cases:
  for rep in range(REPS):
   arms=list(ARMS[group])
   random.Random(seed(c["sha256"],rep)).shuffle(arms)
   for arm in arms:
    r=solve(c,rep,arm);r["shard"]=idx
    need(r["original_sha_verified"] and
         r["wall_E2E_s"]<=CAP+.15 and
         (r["status"]!="SAT" or r["SAT_original_model_verified"]),
         "noncertified attempted source result")
    rows.append(r);save(ROOT/group/("shard-%d.json"%idx),rows)
    print("SEARCH4_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
 need(len(rows)==2*REPS*len(ARMS[group]),"missing measured E2E")
 print("SEARCH4_SHARD_PASS "+json.dumps(dict(
   group=group,shard=idx,SHA=len(cases),attempts=len(rows)),sort_keys=True),flush=True)
def audit(group):
 verify();need(group in ARMS,"unknown group")
 rows=[]
 for idx in range(SHARD_COUNT):
  rr=json.loads((ROOT/group/("shard-%d.json"%idx)).read_text())
  need(len(rr)==2*REPS*len(ARMS[group]),"shard missing")
  rows+=rr
 cs=[c for c in frozen_sources() if c["cohort"]==group]
 expected={(c["sha256"],rep,arm) for c in cs
           for rep in range(REPS) for arm in ARMS[group]}
 actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
 need(len(rows)==len(actual)==len(expected)==EXPECTED[group] and
      expected==actual,"paired trial list wrong")
 bysha=collections.defaultdict(list)
 cases={c["sha256"]:c for c in cs}
 for r in rows:
  c=cases[r["sha256"]]
  need(r["protocol"]==PROTO and r["cohort"]==group and
       r["original_sha_verified"] and r["cap_s"]==CAP and
       r["no_parallel_children"] and r["wall_E2E_s"]<=CAP+.15
       and r["status"] in ("SAT","UNSAT","TIMEOUT")
       and r["original_DIMACS_fed_to_CDCL"] and
       r["search4_rule"]==route(c) and
       (r["status"]!="SAT" or r["SAT_original_model_verified"]),
       "bad source verdict or missing original SAT witness")
  if r["actual_native_CDCL"]:
   t=r["actual_CDCL_telemetry"]
   need(t is not None and t["source_is_original_DIMACS"]
        and t["priority_mode_mask"]==r["mode_mask"]
        and t["initial_internal_priority_seed_count"]==
              (c["source_signals"]["vars"] if r["mode_mask"] else 0),
        "not actual direct internal CDCL seed")
  if r["arm"]=="cadical_router":
   need(r["mode_mask"]=={"original":0,"vmtf":1,"reverse":3}[route(c)],
        "SEARCH4 policy leaked outcome")
  bysha[r["sha256"]].append(r)
 original_agreed=set()
 for sha,rr in bysha.items():
  outcomes={r["status"] for r in rr if r["status"]!="TIMEOUT"}
  need(len(outcomes)<=1,"contradictory original SAT/UNSAT")
  if any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr) and \
     any(r["arm"]=="cadical_unpatched" and r["status"]=="UNSAT" for r in rr):
   original_agreed.add(sha)
 def ok(r):return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in original_agreed)
 def p2(r):return r["wall_E2E_s"] if ok(r) else 2*CAP
 def stat(ss):
  tele=[r["actual_CDCL_telemetry"] for r in ss if r["actual_CDCL_telemetry"] is not None]
  return dict(attempts=len(ss),solved=sum(ok(r) for r in ss),
   SAT_original_model_verified=sum(r["status"]=="SAT" for r in ss),
   UNSAT_original_ref_agreed_no_LRAT=sum(r["status"]=="UNSAT" and ok(r) for r in ss),
   UNSAT_without_reference_agreement=sum(r["status"]=="UNSAT" and not ok(r) for r in ss),
   TIMEOUT=sum(r["status"]=="TIMEOUT" for r in ss),
   PAR2_s=round(sum(p2(r) for r in ss),6),
   wall_E2E_total_s=round(sum(r["wall_E2E_s"] for r in ss),6),
   child_CPU_s=round(sum(r["child_CPU_s"] for r in ss),6),
   parent_CPU_s=round(sum(r["parent_CPU_s"] for r in ss),6),
   prep_wall_s=round(sum(r["preparation_E2E_s"] for r in ss),6),
   conflicts=sum(t["conflicts"] for t in tele),
   decisions=sum(t["decisions"] for t in tele),
   search_propagations=sum(t["search_propagations"] for t in tele))
 scores={a:stat([r for r in rows if r["arm"]==a]) for a in ARMS[group]}
 for a,v in scores.items():
  v["PAR2_speedup_vs_unpatched_x"]=round(
    scores["cadical_unpatched"]["PAR2_s"]/v["PAR2_s"],6)
 paired={}
 for a in ARMS[group]:
  if a=="cadical_unpatched":continue
  gains=[]
  for sha,rr in bysha.items():
   for rep in range(REPS):
    orig=next(r for r in rr if r["arm"]=="cadical_unpatched" and r["rep"]==rep)
    arm=next(r for r in rr if r["arm"]==a and r["rep"]==rep)
    gains.append(p2(arm)-p2(orig))
  paired[a]=dict(wins=sum(x<-.02 for x in gains),
   ties=sum(abs(x)<=.02 for x in gains),
   regressions=sum(x>.02 for x in gains),
   best_gain_s=round(min(gains),6),worst_regression_s=round(max(gains),6))
 report=dict(protocol=PROTO,group=group,SHA=len(cs),trials=EXPECTED[group],
  original_SHA_new_relative_to_registered_history=True,
  globally_blind_unproven=True,
  no_outcome_based_selection=True,
  fresh_cohort_sha_disjoint_other_group=True,
  frozen_SOURCE_only_SEARCH4_policy=True,
  proof_independent_UNSAT_LRAT=False,
  accepted_UNSAT_original_cross_reference_SHA=sorted(original_agreed),
  accepted_SAT_original_model_verified=True,no_auto_promotion=True,
  scores=scores,paired_vs_unpatched=paired,
  per_shard={str(i):{a:stat([r for r in rows if r["shard"]==i and r["arm"]==a])
                       for a in ARMS[group]} for i in range(SHARD_COUNT)},
  per_SHA={sha:dict(year=cases[sha]["year"],gbd=cases[sha]["gbd"],
   signals=cases[sha]["source_signals"],
   preregistered_route=route(cases[sha]),
   arms={a:[dict(rep=r["rep"],status=r["status"],wall_E2E_s=r["wall_E2E_s"],
     mode=r["mode_mask"],telemetry=r["actual_CDCL_telemetry"])
     for r in rr if r["arm"]==a] for a in ARMS[group]})
    for sha,rr in bysha.items()})
 save(ROOT/group/"audit.json",report)
 print("SEARCH4_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("freeze","verify","shard","audit"))
 p.add_argument("--group",choices=list(ARMS))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 if a.action=="freeze":freeze()
 elif a.action=="verify":verify();print("SEARCH4_VERIFY_PASS",flush=True)
 elif a.action=="shard":need(a.group is not None,"group required");shard(a.group,a.shard)
 elif a.action=="audit":need(a.group is not None,"group required");audit(a.group)

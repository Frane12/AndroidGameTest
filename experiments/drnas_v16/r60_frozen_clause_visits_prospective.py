#!/usr/bin/env python3
"""R60 frozen clause-visit-saving proxy: truly source-disjoint held-out SAT tests.

Predeclared sole NEW signal: R58's mean sampled unit-propagation clause visits
saved = (base visits - strengthened visits)/number of comparable probes.
Intervene iff ORIGINAL R49 gate holds AND comparable_probes>=1 AND savings>0.
Threshold is exactly zero, fixed prior to all R60 solver runtimes.

No timing data from R60 is used for sourcing/thresholds. Preselect source
formula identities using public SATComp2026 CaDiCaL score strata and frozen
salt; optionally ENRICH deterministic feature-positive/negative categories
WITHOUT inspecting any DRNAS outcomes. That conditional sampling is recorded.
Compare original pinned Kissat, old R49, shadow (cost-only), and R60 gate,
using randomized serial pairs on same CPU core and strict 40s wall budget
INCLUDING preprocessing, UP probe, rewrite, and SAT witness verification.

The clause-visit count is R58's bounded Python UP proxy, NOT Kissat's native
watched-literal propagation statistics. Do not conflate or claim generality.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, random, resource, subprocess, tempfile, time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r52_prospective_2026_toprefs as r52
import r49_pivot_coherence_gate as r49
import r47_partial_links as r47
import r58_implication_graph_propagation as r58

PROTO="DRNAS-R60-FROZEN-CLAUSE-VISITS-20261103-v1"
SALT="R60-UNSEEN-2026-SOURCE-AND-CAT-CLVS-20261103-V1"
THRESHOLD=0.0
MIN_PROBES=1
CAP=40.0
REPS=2
SHARDS=8
MODES=("clean","r49_full40","r60_visits_shadow","r60_visits_gate40")
STRATA=("sat_fast","unsat_fast","sat_mid","unsat_mid")
MAX_CANDIDATES_PER_STRATUM=22
TARGET_COUNTS={"positive":5,"nonpositive":5,"inactive":4}
RAW_CAP=28*1024*1024
CNF_CAP=48*1024*1024
PREVIOUS_RUNS=(41684183452,41691243486,41694594541)

def require(ok, msg):
 if not ok: raise RuntimeError("R60_FROZEN_AUDIT_ERROR: "+str(msg))
def sha(p):return r52.digest(p)
def h(s):return hashlib.sha256((SALT+"|"+s).encode()).hexdigest()

def short_probe(source,plan):
 """Exactly same bounded R58 UP definition. Must run before any solver outcome."""
 n,short,trace=r47.sample_original(source)
 require(n is not None,"R58 short sample disabled for source size")
 derived=[tuple(c) for c in plan["clauses"][:24]]
 probe=r58.propagation_effect(short,derived,derived)
 return dict(
   savings=float(probe["probing_mean_clause_visits_saved"]),
   comparable=int(probe["probing_comparable"]),
   attempted=int(probe["probing_trials"]),
   new_units=float(probe["probing_mean_new_units"]),
   new_conflicts=int(probe["probing_increased_conflicts"]),
   sampled_short=len(short))

def eligible(plan,features):
 return bool(plan["gate"] and features["comparable"]>=MIN_PROBES
             and features["savings"]>THRESHOLD)

def classify(plan,features):
 if not plan["gate"]:return "inactive"
 if eligible(plan,features):return "positive"
 return "nonpositive"

def freeze(args):
 root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
 prior={}
 for key in ("prior52","prior55","prior57"):
  path=Path(getattr(args,key))/"manifest.json"
  prior[key]=json.loads(path.read_text())
 require(len(prior["prior52"]["cases"])==11 and
         len(prior["prior55"]["cases"])==11 and
         len(prior["prior57"]["cases"])==8,"historical source roster changed")
 old=set(g for _,g in r32p.PINS)|set(g for _,g in r32r.PINS)
 require(len(old)==37,"R32 original roster changed")
 for p in prior.values():
  old.update(c["gbd"] for c in p["cases"])
 require(len(old)==67,"historical source roster has duplicate IDs")
 oldsha={c.get("sha256",c.get("source_sha256")) for p in prior.values()
         for c in p["cases"]}
 raw_list=r52.fetch_bytes(r52.URI,100000)
 allids=[line.rsplit("/",1)[-1] for line in raw_list.decode().strip().splitlines()]
 require(len(allids)==400 and len(set(allids))==400,"official 2026 source list changed")
 raw_scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
 scores=[q for q in csv.DictReader(io.StringIO(raw_scores.decode()))
         if q["solverid"]=="biere_cadical3[main]" and q["instanceid"] in allids]
 require(len(scores)==400,"official scores changed")
 pools={s:[] for s in STRATA}
 for e in scores:
  g=e["instanceid"]
  if g in old or e["status"] not in ("sat-verified","unsat-verified"):continue
  t=float(e["runtime"])
  tier="fast" if 0<=t<10 else "mid" if 10<=t<80 else None
  if tier is None:continue
  stratum=("sat" if e["status"]=="sat-verified" else "unsat")+"_"+tier
  pools[stratum].append(dict(gbd=g,
    official_status="SAT" if e["status"]=="sat-verified" else "UNSAT",
    published_cadical_seconds=t,stratum=stratum))
 ordered={s:sorted(pools[s],key=lambda v:h(s+"/"+v["gbd"]))[:MAX_CANDIDATES_PER_STRATUM]
          for s in STRATA}
 # Interleave strata in fully predetermined order, without any DRNAS timing.
 seq=[]
 for i in range(MAX_CANDIDATES_PER_STRATUM):
  for s in STRATA:
   if i<len(ordered[s]):seq.append(ordered[s][i])
 source_limit=88
 output=[];attempts=[];counts={q:0 for q in TARGET_COUNTS}
 r32p.CNF_LIMIT=CNF_CAP
 for c in seq[:source_limit]:
  cat=None
  g=c["gbd"]
  note=dict(gbd=g,stratum=c["stratum"])
  file=root/(g+".cnf")
  try:
   compressed,redirect=r32p.request_url(
    "https://benchmark-database.de/file/"+g,RAW_CAP,seconds=50)
   data,compression=r32p.decode(compressed)
   require(len(data)<=CNF_CAP,"uncompressed source cap")
   n,m=r32p.parse_dimacs_metadata(data)
   file.write_bytes(data)
   fp=sha(file)
   require(fp not in oldsha,"historical source repeated SHA")
   plan=r49.compute_plan(file)
   feature=short_probe(file,plan)
   cat=classify(plan,feature)
   if counts[cat]<TARGET_COUNTS[cat]:
    counts[cat]+=1
    output.append(dict(**c,filename=file.name,sha256=fp,
       original_bytes=len(data),original_variables=n,original_clauses=m,
       r49_gate=bool(plan["gate"]),derived=int(plan["derived"]),
       certificate_sha=plan["certificate_sha256"],
       visits_saved=feature["savings"],probe_comparable=feature["comparable"],
       probe_attempted=feature["attempted"],probe_new_units=feature["new_units"],
       probe_new_conflicts=feature["new_conflicts"],
       sampled_short=feature["sampled_short"],
       category=cat,r60_gate=eligible(plan,feature),
       compression=compression,redirect=redirect))
    note.update(state="READY",cat=cat,visits_saved=feature["savings"],
        comparable=feature["comparable"],r49=plan["gate"],sha256=fp)
   else:
    file.unlink(missing_ok=True)
    note.update(state="EXCLUDED_PRECOMMITTED_CATEGORY_QUOTA",
       cat=cat,visits_saved=feature["savings"],comparable=feature["comparable"])
  except Exception as exc:
   file.unlink(missing_ok=True)
   note.update(state="EXCLUDED_SIZE_FETCH_OR_STRUCTURE",reason=(str(exc))[:270])
  attempts.append(note)
  print("R60_FREEZE_ATTEMPT",json.dumps(note,sort_keys=True),flush=True)
  if all(counts[k]>=TARGET_COUNTS[k] for k in counts):break
 require(len(output)>=8 and len({r["sha256"] for r in output})==len(output),
         "not enough new distinct official sources for test")
 manifest=dict(protocol=PROTO,source_salt=SALT,
   scope="Feature-stratified prospective official SATComp2026 original sources",
   previous_runs=list(PREVIOUS_RUNS),
   disjoint_previous_id_count=len(old),prior_r52_r55b_r57_only_hashes=sorted(oldsha),
   public_2026_index_sha256=hashlib.sha256(raw_list).hexdigest(),
   public_cadical_score_sha256=hashlib.sha256(raw_scores).hexdigest(),
   selection_based_on_DRNAS_solve_times=False,
   selection_uses_only_official_score_strata_and_original_source_features=True,
   eligibility="R49 gate and R58 bounded UP mean clause visits saved > 0 and >=1 comparable probe",
   threshold=THRESHOLD,min_comparable_probes=MIN_PROBES,
   metric_source="R58 original sampled 1..4 CNF clauses, <=60k, 24 deterministic literal probes",
   not_true_native_kissat_clause_visits=True,
   biased_enrichment_on_predictor=True,
   targets=TARGET_COUNTS,actual_group_counts=counts,
   attempts=attempts,cases=output,shards=SHARDS,repeats=REPS,
   cap_seconds=CAP,par2_timeout_seconds=80.0,
   methods=list(MODES),
   no_full_project_history_guarantee=True,
   limitations=[
      "Enriched predictor-positive and predictor-negative sampling biases population prevalence",
      "Freeze uses public official CaDiCaL result/time strata, not DRNAS results",
      "R58 feature is Python bounded unit-propagation clause visits, not in-process Kissat BCP",
      "Selected cases disjoint from recorded R32p R32r R52 R55b R57 ID registry",
      "Unseen by these cohorts, not proven unseen in every historical project run",
      "Two repeated paired attempts, shared 40s cap including feature computation",
      "SAT models checked on unchanged originals; UNSAT not LRAT independently validated",
      "No 2026 winning solver executable compared; not an official contest rank"])
 (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 (root/"source.sha256").write_text("".join(
     r["sha256"]+"  "+r["filename"]+"\n" for r in output))
 print("R60_FREEZE_PASS",len(output),"category_counts",json.dumps(counts),
       "positive",sum(x["r60_gate"] for x in output),
       "source_disjoint_earlier_registry",len(old),flush=True)

def limit_mem():
 resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def single_trial(source,case,kissat,mode):
 start=time.monotonic()
 added=0
 status="TIMEOUT"
 measured=None
 with tempfile.TemporaryDirectory(prefix="r60-up-visit-") as tmp:
  solver_source=source
  if mode in ("r49_full40","r60_visits_shadow","r60_visits_gate40"):
   plan=r49.compute_plan(source)
   require(plan["certificate_sha256"]==case["certificate_sha"] and
       bool(plan["gate"])==case["r49_gate"] and
       int(plan["derived"])==case["derived"],"frozen implication/proof changed")
   active=plan["gate"] if mode=="r49_full40" else False
   if mode!="r49_full40":
    measured=short_probe(source,plan)
    require(measured["savings"]==case["visits_saved"] and
      measured["comparable"]==case["probe_comparable"] and
      measured["sampled_short"]==case["sampled_short"],
      "frozen signal calculation drift")
    if mode=="r60_visits_gate40":active=eligible(plan,measured)
    if mode=="r60_visits_gate40":
     require(active==case["r60_gate"],"precommitted selector drift")
   if active:
    clauses=plan["clauses"]
    if clauses:
     solver_source=Path(tmp)/"strengthened.cnf"
     audit=r49.r48.safe_rewrite(source,solver_source,clauses)
     added=len(clauses)
     require(audit["added"]==added,"rewritten source clause count incorrect")
  preparation=time.monotonic()-start
  if preparation<CAP:
   try:
    p=subprocess.run([str(kissat),str(solver_source)],
      capture_output=True,text=True,errors="replace",
      timeout=CAP-preparation,preexec_fn=limit_mem)
    require(p.returncode in (10,20),
      "solver exited abnormally "+str(p.returncode)+":"+p.stderr[-130:])
    status="SAT" if p.returncode==10 else "UNSAT"
    if status=="SAT":
     r32p.verify_sat_witness(source,p.stdout)
   except subprocess.TimeoutExpired:status="TIMEOUT"
  wall=time.monotonic()-start
 if wall>CAP:status="TIMEOUT"
 wall=min(wall,CAP)
 return dict(status=status,wall_s=round(wall,6),prep_s=round(preparation,6),
     par2_s=round(wall if status!="TIMEOUT" else 80.0,6),
     added=added,signal_savings=measured["savings"] if measured else None)

def measure(a):
 root=Path(a.sources)
 m=json.loads((root/"manifest.json").read_text())
 require(m["protocol"]==PROTO and a.shard in range(SHARDS),"source frozen protocol mismatch")
 kissat=Path(a.kissat).resolve()
 require(kissat.is_file(),"pinned Kissat executable absent")
 if hasattr(os,"sched_setaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
 (dest/"meta.json").write_text(json.dumps(dict(protocol=PROTO,shard=a.shard,
   frozen_manifest_sha=sha(root/"manifest.json"),kissat_sha=sha(kissat),
   affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else []),
   indent=2)+"\n")
 rows=[]
 for case in m["cases"][a.shard::SHARDS]:
  original=root/case["filename"]
  require(sha(original)==case["sha256"],"official original SHA differs")
  for rep in range(REPS):
   order=list(MODES)
   random.Random(int(h(case["sha256"]+"/"+str(rep)),16)).shuffle(order)
   for mode in order:
    result=single_trial(original,case,kissat,mode)
    require(result["status"]=="TIMEOUT" or result["status"]==case["official_status"],
            "solver status disagrees with published original")
    row=dict(gbd=case["gbd"],source_sha=case["sha256"],
      category=case["category"],active_precommitted=case["r60_gate"],
      rep=rep,mode=mode,**result)
    rows.append(row)
    print("R60_MATCHED_TRIAL",case["gbd"],case["category"],"rep",rep,mode,
      result["status"],result["wall_s"],"PAR2",result["par2_s"],
      "prep",result["prep_s"],"added",result["added"],flush=True)
    (dest/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
 require(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
         "incomplete paired shard")

def audit(a):
 root=Path(a.sources)
 m=json.loads((root/"manifest.json").read_text())
 require(m["protocol"]==PROTO,"wrong manifest")
 rows=[];binary_shas=set()
 for shard in range(SHARDS):
  folder=Path(a.combined)/("r60-shard-"+str(shard))/"results"
  meta=json.loads((folder/"meta.json").read_text())
  require(meta["protocol"]==PROTO and meta["shard"]==shard and
          meta["frozen_manifest_sha"]==sha(root/"manifest.json"),
          "source mismatch or missing shard")
  binary_shas.add(meta["kissat_sha"])
  part=json.loads((folder/"rows.json").read_text())
  require(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
          "shard incomplete")
  rows+=part
 require(len(binary_shas)==1 and len(rows)==len(m["cases"])*REPS*len(MODES),
         "binary not pinned or incomplete measurements")
 results={}
 for segment in ("all","positive","nonpositive","inactive"):
  sel=(rows if segment=="all" else [r for r in rows if r["category"]==segment])
  result={}
  for mode in MODES:
   zz=[r for r in sel if r["mode"]==mode]
   result[mode]=dict(attempts=len(zz),
      solved=sum(r["status"]!="TIMEOUT" for r in zz),
      par2_s=round(sum(r["par2_s"] for r in zz),6),
      mean_prep_s=round(sum(r["prep_s"] for r in zz)/max(1,len(zz)),6),
      active_trials=sum(r["added"]>0 for r in zz))
  base=result["clean"]["par2_s"]
  for val in result.values():
   val["delta_vs_clean_pct"]=round(100*(val["par2_s"]/base-1),4) if base else None
  results[segment]=result
 per_case={}
 for c in m["cases"]:
  case=[r for r in rows if r["gbd"]==c["gbd"]]
  require(len(case)==len(MODES)*REPS and
     all(r["source_sha"]==c["sha256"] for r in case),"missing case or wrong SHA")
  for rep in range(REPS):
   rr=[r for r in case if r["rep"]==rep]
   require({r["mode"] for r in rr}==set(MODES),"missing paired method")
   require(all(r["status"]=="TIMEOUT" or r["status"]==c["official_status"] for r in rr),
           "official source result inconsistency")
   require(all(r["added"]==0 for r in rr if r["mode"] in ("clean","r60_visits_shadow")),
           "unexpected clauses in sham condition")
  per_case[c["gbd"]]=dict(category=c["category"],
    feature_savings=c["visits_saved"],gate=c["r49_gate"],
    modes={mode:dict(par2_s=round(sum(r["par2_s"] for r in case if r["mode"]==mode),6),
       times=[r["wall_s"] if r["status"]!="TIMEOUT" else "TO"
       for r in sorted(case,key=lambda z:z["rep"]) if r["mode"]==mode])
       for mode in MODES})
 eligible_count=sum(c["r60_gate"] for c in m["cases"])
 report=dict(protocol=PROTO,cases=len(m["cases"]),attempts=len(rows),
    active_source_count=eligible_count,feature_test_informative=eligible_count>=3,
    metrics=results,per_case=per_case,rows=rows,manifest=m,
    pinned_binary_sha=next(iter(binary_shas)))
 Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
 lines=["# R60 frozen savings-in-clause-visits predictor — held-out 2026 sources",
   "**Frozen BEFORE SAT benchmarking:** R49 gate AND average R58 unit-propagation clause-visits-saved > 0, with at least one nontruncated probe.",
   "This is a sampled Python UP proxy, NOT direct Kissat watched-literal statistics.",
   f"{len(m['cases'])} distinct new official 2026 originals; {len(rows)} matched trials, 40s wall, timeout PAR2=80.",
   "Positive/negative feature strata sampled by frozen quotas without using DRNAS outcomes.",
   "","## PAR2 and total analysis overhead, new source-disjoint formulas"]
 for seg in ("all","positive","nonpositive","inactive"):
  lines+=["",f"### {seg} ({sum(x['category']==seg for x in m['cases'])} source originals)",
    "| Method | Solved | PAR2 s | Δ vs clean | Mean preprocessing s | Active injections |",
    "|---|---:|---:|---:|---:|---:|"]
  for mode in MODES:
   t=results[seg][mode]
   lines.append(f'| {mode} | {t["solved"]}/{t["attempts"]} | {t["par2_s"]:.3f} | {t["delta_vs_clean_pct"]:+.2f}% | {t["mean_prep_s"]:.4f} | {t["active_trials"]} |')
 lines+=["","## Per original, two repetitions PAR2 seconds",
      "| Source | Feature class | Saved clause visits | "+" | ".join(MODES)+" |",
      "|---|---|---:|"+("|---:|"*len(MODES))]
 for c in m["cases"]:
  z=per_case[c["gbd"]]
  lines.append(f'| {c["gbd"][:12]} | {c["category"]} | {z["feature_savings"]:.4f} | '+
      " | ".join(f'{z["modes"][m]["par2_s"]:.3f}' for m in MODES)+" |")
 if eligible_count<3:
  lines+=["","### Inference limit",
      "Fewer than three positive predictor-eligible source originals: the test cannot establish whether savings-in-clause-visits predicts benefit. Abstention and analysis overhead remain measurable."]
 lines+=["","**No threshold retuning on this run.** Even if the predictor fails, retain the failed holdout as scientific evidence.",
    "No world rank claims. Sources selected from public official status/time strata and enriched by untimed features.",
    "SAT results model checked, UNSAT not independently LRAT checked. Only recorded cohorts excluded, not full historical project."]
 Path(a.md).write_text("\n".join(lines)+"\n")
 print("R60_FINAL_AUDIT_PASS",len(rows),json.dumps(results,sort_keys=True),
       "feature_positive_sources",eligible_count,flush=True)

def main():
 p=argparse.ArgumentParser()
 subs=p.add_subparsers(dest="cmd",required=True)
 f=subs.add_parser("freeze")
 for field in ("prior52","prior55","prior57","out"):
  f.add_argument("--"+field,required=True)
 m=subs.add_parser("measure")
 for field in ("sources","shard","kissat","out"):
  m.add_argument("--"+field,required=True)
 a=subs.add_parser("audit")
 for field in ("sources","combined","json","md"):
  a.add_argument("--"+field,required=True)
 x=p.parse_args()
 if x.cmd=="freeze":freeze(x)
 elif x.cmd=="measure":
  x.shard=int(x.shard)
  measure(x)
 else:audit(x)
if __name__=="__main__":main()

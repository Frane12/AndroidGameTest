#!/usr/bin/env python3
"""R56 structural signal diagnosis from 22 already evaluated SATComp2026 originals.

READ-ONLY observational audit: no benchmark data are used to change any SAT
solver or the new-originals selection. Extract candidate structure features
from original CNF and certified two-parent resolvents, correlate with R52 &
R55b full40 effects, and evaluate a one-dimensional leave-one-formula-out
abstention gate. All feature rankings are POST-HOC and NOT independent evidence.

Important: the special R55 pair 17+24 is already found on one source and
cannot be generalized based on clause POSITIONS. The two clauses do not
even have an overlapping literal; shared SAT graph is via the original CNF.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,statistics
from pathlib import Path
import r49_pivot_coherence_gate as r49
import r47_partial_links as r47

PROTO="DRNAS-R56-STRUCTURAL-SIGNAL-OBSERVATIONAL-20261103-v1"
METRICS=(
 "variables","original_clauses","cnf_bytes","sampled_short_clauses",
 "sample_short_density","short_binary_frac","derived_count","pivot_dominance",
 "proof_distinct_parents","proof_avg_parent_span",
 "head24_binary_count","head24_triple_count","head24_unique_variables",
 "head24_repeated_variables","head24_shared_pairs",
 "head24_opposite_polarity_variables",
 "window17_24_binary_count","window17_24_unique_variables",
 "window17_24_shared_pairs","window17_24_shortest",
 "tail16_binary_count","head24_source_support_union",
 "head24_source_pivot_max_frac",
 "head24_max_variable_frequency","sampled_variables_frac",
 "clauses_17_24_overlap",
)
def check(ok,msg):
 if not ok:raise RuntimeError("R56_AUDIT_FAIL "+str(msg))
def sha(path):
 return r49.sha(path)
def derived_features(path,plan):
 n,clauses,trace=r47.sample_original(path)
 check(n is not None,"source cannot be sampled")
 head=plan["clauses"][:24]
 window=plan["clauses"][16:24]
 tail=plan["clauses"][24:]
 parents=plan["proofs"][:24]
 hvars=collections.Counter(abs(x) for c in head for x in c)
 wvars=collections.Counter(abs(x) for c in window for x in c)
 pids=set(i for p in parents for i in p["parent_ids"])
 pairs=lambda group:sum(bool(set(map(abs,group[i])) & set(map(abs,group[j])))
     for i in range(len(group)) for j in range(i+1,len(group)))
 polarity=collections.defaultdict(set)
 for c in head:
  for lit in c:polarity[abs(lit)].add(lit>0)
 sclause=collections.Counter(len(c) for c in clauses)
 pct=lambda a,b:round(a/max(1,b),7)
 totalh=sum(hvars.values())
 f=dict(variables=n,original_clauses=trace["original_clauses"],
       cnf_bytes=Path(path).stat().st_size,
       sampled_short_clauses=len(clauses),
       sample_short_density=pct(len(clauses),trace["original_clauses"]),
       short_binary_frac=pct(sclause[2],len(clauses)),
       derived_count=plan["derived"],pivot_dominance=plan["dominance"],
       proof_distinct_parents=len(set(x for p in plan["proofs"] for x in p["parent_ids"])),
       proof_avg_parent_span=round(statistics.mean(
           [abs(p["parent_ids"][0]-p["parent_ids"][1])
            for p in plan["proofs"]]),4) if plan["proofs"] else 0,
       head24_binary_count=sum(len(c)==2 for c in head),
       head24_triple_count=sum(len(c)==3 for c in head),
       head24_unique_variables=len(hvars),
       head24_repeated_variables=sum(k>1 for k in hvars.values()),
       head24_shared_pairs=pairs(head),
       head24_opposite_polarity_variables=sum(len(s)==2 for s in polarity.values()),
       window17_24_binary_count=sum(len(c)==2 for c in window),
       window17_24_unique_variables=len(wvars),
       window17_24_shared_pairs=pairs(window),
       window17_24_shortest=min(map(len,window)) if window else 0,
       tail16_binary_count=sum(len(c)==2 for c in tail),
       head24_source_support_union=len(set(x for p in parents for x in p["support"])),
       head24_source_pivot_max_frac=pct(max(collections.Counter(
           p["pivot"] for p in parents).values(),default=0),len(parents)),
       head24_max_variable_frequency=max(hvars.values(),default=0),
       sampled_variables_frac=pct(
           len({abs(x) for c in clauses for x in c}),n),
       clauses_17_24_overlap=len(set(map(abs,plan["clauses"][16])) &
           set(map(abs,plan["clauses"][23]))) if len(plan["clauses"])>=24 else 0,
       )
 check(set(f)==set(METRICS),"metrics changed")
 return f

def get_effect(report,gbd,ref_mode,other_mode):
 rows=[r for r in report["rows"] if r["gbd"]==gbd]
 base=[r for r in rows if r["mode"]==ref_mode]
 active=[r for r in rows if r["mode"]==other_mode]
 check(len(base)==len(active) and len(base) in (1,2),
       "missing historical paired results")
 p=lambda r: r["par2_s"]
 b=sum(p(x) for x in base)/len(base)
 a=sum(p(x) for x in active)/len(active)
 return dict(reference_s=round(b,6),active_s=round(a,6),
    delta_s=round(a-b,6),delta_pct=round(100*(a/b-1),4),
    repeats=len(base),solved_reference=sum(
      x.get("answer",x.get("status"))!="TIMEOUT" for x in base),
    solved_active=sum(
      x.get("answer",x.get("status"))!="TIMEOUT" for x in active))

def feature_rule(train,metric,op,thr):
 return lambda r: (r["features"][metric]>thr
            if op==">" else r["features"][metric]<=thr)

def enumerate_rules(rows):
 result=[]
 for metric in METRICS:
  unique=sorted(set(x["features"][metric] for x in rows))
  for val in unique:
   for op in ("<=",">"):
    fn=feature_rule(rows,metric,op,val)
    selected=[x for x in rows if fn(x)]
    if len(selected)<2 or len(selected)>len(rows)-1:
     continue
    loss=sum(x["full40_effect"]["delta_s"] for x in selected)
    winners=sum(x["full40_effect"]["delta_s"]<0 for x in selected)
    losers=len(selected)-winners
    result.append(dict(metric=metric,op=op,threshold=val,
       activated=len(selected),beneficial=winners,regressions=losers,
       net_delta_s=round(loss,6)))
 return sorted(result,key=lambda z:(z["net_delta_s"],z["activated"],z["metric"]))

def train_abstention(rows):
 # Include all-abstain: zero incremental loss. Favor conservative ties.
 best=dict(metric="NONE",net_delta_s=0.0,activated=0)
 for rule in enumerate_rules(rows):
  # At least one selected benefit and at least 1/2 selected are beneficial.
  if rule["net_delta_s"]<-0.25 and rule["beneficial"]>=1 \
       and rule["beneficial"]*2>=rule["activated"] \
       and rule["net_delta_s"]<best["net_delta_s"]:
   best=rule
 return best

def rule_applies(rule,x):
 if rule["metric"]=="NONE":return False
 v=x["features"][rule["metric"]]
 return v>rule["threshold"] if rule["op"]==">" else v<=rule["threshold"]

def main(args):
 roots={"R52":Path(args.r52_sources),"R55b":Path(args.r55b_sources)}
 reports={"R52":json.loads(Path(args.r52_report).read_text()),
          "R55b":json.loads(Path(args.r55b_report).read_text())}
 m52=json.loads((roots["R52"]/"manifest.json").read_text())
 m55=json.loads((roots["R55b"]/"manifest.json").read_text())
 check(len(m52["cases"])==11 and len(m55["cases"])==11,
       "expected 11+11 SHA frozen original sources")
 check(reports["R52"]["protocol"].startswith("DRNAS-R52-") and
       reports["R55b"]["protocol"].startswith("DRNAS-R55B-"),
       "wrong historical reports")
 records=[]
 observed=set()
 for cohort,manifest in [("R52",m52),("R55b",m55)]:
  for case in manifest["cases"]:
   original=roots[cohort]/case.get("name",case.get("filename"))
   expected_sha=case.get("sha256",case.get("source_sha256"))
   check(original.is_file() and sha(original)==expected_sha,
         "original SHA drift "+cohort)
   check(expected_sha not in observed,"repeated source SHA across cohorts")
   observed.add(expected_sha)
   plan=r49.compute_plan(original)
   feat=derived_features(original,plan)
   if cohort=="R52":
    eff=get_effect(reports[cohort],case["gbd"],"kissat_pinned","drnas_r49_gate")
    head24=None
   else:
    eff=get_effect(reports[cohort],case["gbd"],"clean","full40_gate")
    head24=get_effect(reports[cohort],case["gbd"],"clean","head24_gate")
   records.append(dict(cohort=cohort,gbd=case["gbd"],
       source_sha=expected_sha,status=case.get("official_result",case.get("official_status")),
       gate=plan["gate"],derived=plan["derived"],
       binary_front16=[c for c in plan["clauses"][:16] if len(c)==2],
       features=feat,full40_effect=eff,head24_effect=head24))
 check(len(records)==22,"incomplete records")
 active=[x for x in records if x["gate"]]
 check(len(active)==9,"historical activated set changed")
 winners=[x for x in active if x["full40_effect"]["delta_s"]<-.25]
 losses=[x for x in active if x["full40_effect"]["delta_s"]>.25]
 # For source-disjoint exploration, assess LOOCV performance, not training best.
 best=train_abstention(active)
 loo=[]
 for i,x in enumerate(active):
  chosen=train_abstention(active[:i]+active[i+1:])
  applied=rule_applies(chosen,x)
  loo.append(dict(gbd=x["gbd"],cohort=x["cohort"],
         selected=applied,learned_rule=chosen,
         delta_s=round(x["full40_effect"]["delta_s"] if applied else 0,6)))
 best_in_sample={**best,"case_ids":[x["gbd"] for x in active if rule_applies(best,x)]}
 candidate_rules=enumerate_rules(active)[:12]
 out=dict(protocol=PROTO,n_total=len(records),n_activated=len(active),
     n_gain=len(winners),n_regression=len(losses),
     all_active_full40_delta_s=round(
         sum(x["full40_effect"]["delta_s"] for x in active),6),
     post_hoc_best_rule=best_in_sample,ranked_post_hoc_thresholds=candidate_rules,
     leave_one_case_out=dict(n=len(loo),selected=sum(z["selected"] for z in loo),
         net_delta_s=round(sum(z["delta_s"] for z in loo),6),rows=loo),
     records=records,limitations=[
       "Outcome labels are 9 R49 gate-active formulas only, across different protocol cohorts",
       "R52 winner used 1 repeat; R55b used 2 repeats; all normalized per attempt",
       "Feature selection and threshold rankings are retrospective hypothesis generation",
       "No feature from SAT winner can be claimed generalizable until new frozen SHA-disjoint holdout",
       "The two selected R55 clause positions 17 and 24 have no common variables",
       "Ranked rules are complex multiple comparisons over a very small dataset",
       "Do not interpret a perfect in-sample separation as predictive evidence",
       "Preprocessing time and per-instance algorithm choice must be measured end-to-end",
       "Observed gain in R52 is heavily affected by 40s cutoff on one formula"])
 Path(args.json).write_text(json.dumps(out,indent=2)+"\n")
 lines=["# DRNAS R56 — early structural signal forensic comparison",
    "Data: original R52 and R55b frozen official SATComp2026 files and verified historical 2026 trial outputs.",
    "**Retrospective diagnostic, never a new independent benchmark.**",
    f"22 distinct originals, {len(active)} with active R49 structural gate. Full40 improved {len(winners)} and regressed {len(losses)} (strict 0.25s margin).",
    "","## Activated cases and measurable pre-solver structural signals",
    "| GBD | Cohort | Vars | Clauses | Short sampled | Head24 binary | Window 17-24 binary | Head24 shared variable pairs | Full40 effect vs clean (s/attempt) |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
 for x in active:
  f=x["features"]
  lines.append(f'| {x["gbd"][:12]} | {x["cohort"]} | {f["variables"]} | {f["original_clauses"]} | {f["sampled_short_clauses"]} | {f["head24_binary_count"]} | {f["window17_24_binary_count"]} | {f["head24_shared_pairs"]} | {x["full40_effect"]["delta_s"]:+.3f} |')
 lines+=["","## Retrospective threshold analysis",
  "Rules below selected using the same nine labeled instances; do not validate generalization.",
  "| Feature | Condition | Selected | Helpful | Harmful | Net added wall/PAR2 s |",
  "|---|---|---:|---:|---:|---:|"]
 for z in candidate_rules[:10]:
  lines.append(f'| {z["metric"]} | {z["op"]} {z["threshold"]} | {z["activated"]} | {z["beneficial"]} | {z["regressions"]} | {z["net_delta_s"]:+.3f} |')
 lines+=["",f"Best in-sample abstention rule: \`{best['metric']}\` "
    +("" if best["metric"]=="NONE" else f"\`{best['op']} {best['threshold']}\`"),
    f"Leave-one-case-out (frozen training on other eight): selected {out['leave_one_case_out']['selected']}/{len(active)}; net incremental PAR2 {out['leave_one_case_out']['net_delta_s']:+.3f}s.",
    "","## Clause pair finding",
    "R55 pair #17 and #24 do not share any original variable; this suggests a nonlocal CDCL search effect rather than a directly shared variable implication.",
    "Local R49 pivot coherence 1.0 is observed in both gains and regressions, so it is insufficient.",
    "A useful selector must incorporate a cheap hardness/risk estimate or broader implication graph; no general rule is proven.",
    "","## Cautions",
    "All effects from past artifacts; observational and selection-biased.",
    "Do not deploy a post-hoc threshold in production before unseen validation."]
 Path(args.md).write_text("\n".join(lines)+"\n")
 print("R56_FORENSIC_AUDIT_PASS",json.dumps({
   "originals":len(records),"active_gate":len(active),
   "helpful":len(winners),"regressions":len(losses),
   "best_rule":best_in_sample,"leave_one_out":out["leave_one_case_out"],
   "comparisons":[dict(id=x["gbd"],cohort=x["cohort"],
     delta=x["full40_effect"]["delta_s"],
     features={k:x["features"][k] for k in (
       "variables","original_clauses","sampled_short_clauses",
       "head24_binary_count","window17_24_binary_count",
       "head24_shared_pairs","head24_unique_variables",
       "head24_opposite_polarity_variables",
       "head24_source_support_union","proof_avg_parent_span")})
     for x in active]},sort_keys=True),flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser()
 for q in ("r52-sources","r55b-sources","r52-report","r55b-report","json","md"):
  p.add_argument("--"+q,required=True)
 main(p.parse_args())

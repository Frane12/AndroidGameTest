#!/usr/bin/env python3
"""R39: NO SOLVER RUNS. Retrospective pre-intervention signal audit.
Uses frozen R37 120 attempts and R38 5 x 12 original native policy probes.
All gate thresholds are EXPLORATORY except pre-existing v9.1 gate.
"""
import argparse,csv,hashlib,itertools,json,math,statistics
from pathlib import Path
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v94_cautious")
R38_CASES=("ee44c3f464238366729bf2cb16eb412a",
 "12cd0c3196589ac8105653cbfe613fc6",
 "5de866bc7ff4dfde3cd682b5aca75894",
 "0c9da400944b002f90fd385d4fdab385",
 "9ef9243ff051b32795890fccd6c3f6b2")
FEATURES=("binary_frac","clause_var","majority_coverage",
 "polarity_imbalance","avg_width","ternary_frac",
 "four_frac","log_vars","log_clauses")
def rank(xs):
 order=sorted(range(len(xs)),key=lambda i:xs[i]);r=[0.0]*len(xs)
 for j,i in enumerate(order):r[i]=j+1.
 for v in set(xs):
  ix=[i for i,x in enumerate(xs) if x==v]
  a=sum(r[i] for i in ix)/len(ix)
  for i in ix:r[i]=a
 return r
def rho(x,y):
 a,b=rank(x),rank(y);am=statistics.mean(a);bm=statistics.mean(b)
 num=sum((u-am)*(v-bm) for u,v in zip(a,b))
 den=(sum((u-am)**2 for u in a)*sum((v-bm)**2 for v in b))**.5
 return num/den if den else 0.
def pars(rows):
 return statistics.mean(float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 30. for r in rows)
def static_candidate(f):
 # Chosen AFTER seeing R37 outcomes; NOT frozen prospective evidence.
 return (.85<=f["binary_frac"]<=.97
  and .40<=f["majority_coverage"]<=.90
  and 8.<=f["clause_var"]<=40.
  and .20<=f["polarity_imbalance"]<=.55)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--r37-raw",required=True)
 p.add_argument("--r38-root",required=True);p.add_argument("--outdir",required=True)
 a=p.parse_args();o=Path(a.outdir);o.mkdir(parents=True,exist_ok=True)
 manifest=Path(a.manifest);m=json.loads(manifest.read_text())
 lookup={c["id"]:c for c in m["cases"]}
 assert len(lookup)==12 and len(m["cases"])==12
 raw=list(csv.DictReader(open(a.r37_raw,newline="")))
 assert len(raw)==120,len(raw)
 unique=set()
 for r in raw:
  case=r["id"];k=(case,r["mode"],int(r["rep"]))
  assert case in lookup and r["mode"] in MODES and int(r["rep"]) in (0,1)
  assert k not in unique;k0=k;unique.add(k0)
  assert r["sha256"]==lookup[case]["sha256"]
  assert float(r["cap_s"])==15.
  assert r["status"] in ("SAT","UNSAT","TIMEOUT"),r
  if r["status"]!="TIMEOUT":assert r["status"]==lookup[case]["official_label"]
 assert len(unique)==120
 r37=[]
 for item in m["cases"]:
  cid=item["id"];modes={mode:[r for r in raw if r["id"]==cid and r["mode"]==mode] for mode in MODES}
  assert all(len(rows)==2 for rows in modes.values())
  h=pars(modes["orig_v76"]);nh=pars(modes["orig_v76_plain"])
  status="both_solved" if all(x["status"] in ("SAT","UNSAT") for mode in ("orig_v76","orig_v76_plain") for x in modes[mode]) else "censored_or_timeout"
  hint_ratio=h/nh
  category=("benefit_gt_10pct" if status=="both_solved" and hint_ratio<=.90
    else "harm_gt_10pct" if status=="both_solved" and hint_ratio>=1.10
    else "within_10pct" if status=="both_solved" else "censored_or_timeout")
  r37.append(dict(id=cid,label=item["official_label"],features=item["features"],
     hint_par2_s=h,nohint_par2_s=nh,cadical_par2_s=pars(modes["ca_plain"]),
     hint_to_nohint_PAR2_ratio=hint_ratio,comparison=status,category=category,
     static_candidate_selects=static_candidate(item["features"])))
 complete=[x for x in r37 if x["comparison"]=="both_solved"]
 assert len(complete)==6
 yy=[math.log(x["hint_to_nohint_PAR2_ratio"]) for x in complete]
 correlations={}
 for k in FEATURES:
  xx=[x["features"][k] for x in complete];val=rho(xx,yy)
  p_exact=sum(abs(rho(xx,perm))>=abs(val)-1e-12 for perm in itertools.permutations(yy))/math.factorial(6)
  correlations[k]={"spearman_rho":val,"exact_two_sided_permutation_p":p_exact}
 r38=[];probe_hashes=set();kissat_hashes=set();unknown=0
 for i,id in enumerate(R38_CASES):
  path=Path(a.r38_root)/("r38-case-"+str(i))/"results"/"report.json"
  row=json.loads(path.read_text())
  assert row["case_id"]==id and row["sha256"]==lookup[id]["sha256"]
  assert row["features"]==lookup[id]["features"]
  assert row["label"]==lookup[id]["official_label"] and row["selected_retrospectively"]
  assert row["limit_s"]==8.
  probe_hashes.add(row["pinned_probe_sha256"]);kissat_hashes.add(row["pinned_kissat_sha256"])
  by={z["mode"]:z for z in row["single_core_modes"]}
  assert len(by)==12 and len(row["single_core_modes"])==12
  for b in by.values():
   assert b["status"] in ("SAT","UNSAT","TIMEOUT")
   if b["status"]!="TIMEOUT":assert b["status"]==lookup[id]["official_label"]
  no=by["v91_never_late"];yes=by["v91_always_late"]
  assert row["v91_prefix_equal_if_completed"] in (True,None)
  pre=no["stats"]
  if not pre:
   checkpoint=None;unknown+=1
  else:
   L=int(pre["v90_learned_256"]);C=int(pre["v90_conflicts_256"])
   P=int(pre["v90_props_256"]);short=int(pre["v90_lbd2_256"])
   assert L>=0 and C>0 and P>=0 and 0<=short<=L
   assert all(pre[k]==yes["stats"][k] for k in ("v90_learned_256","v90_lbd2_256","v90_props_256","v90_conflicts_256","v90_backtracks_256"))
   assert pre["v91_phase_applied"]=="0"
   q=L>=20 and short*100>=6*L and P>=32*C
   early_no=by["v90_quality_no_hints"];early_yes=by["v90_quality_guided"]
   eager_ratio=(early_yes["wall_s"]/early_no["wall_s"] if early_no["status"]!="TIMEOUT" and early_yes["status"]!="TIMEOUT" else None)
   late_ratio=(yes["wall_s"]/no["wall_s"] if no["status"]!="TIMEOUT" and yes["status"]!="TIMEOUT" else None)
   checkpoint=dict(learned_256=L,conflicts_256=C,propagations_256=P,lbd2_256=short,
    lbd2_fraction=short/L if L else None,propagations_per_conflict=P/C,
    prior_v91_quality_rule=q,
    v91_early_continuation=int(pre["extended"])==1,
    actual_late_intervention=int(yes["stats"]["v91_phase_applied"])==1,
    eager_hints_ratio=eager_ratio,
    late_v91_hints_ratio=late_ratio,
    action_type_warning="Eager hints at t=0 cannot be selected causally using a checkpoint at conflict 256.")
  r38.append(dict(id=id,features=row["features"],checkpoint=checkpoint,
      formula_known_before_selection=True))
 assert len(probe_hashes)==1 and len(kissat_hashes)==1
 assert unknown==1
 nohint_mean=statistics.mean(x["nohint_par2_s"] for x in r37)
 retro_mean=statistics.mean(x["hint_par2_s"] if x["static_candidate_selects"] else x["nohint_par2_s"] for x in r37)
 selected=[x for x in r37 if x["static_candidate_selects"]]
 assert len(selected)==1 and selected[0]["id"]==R38_CASES[1]
 result={"protocol":"R39_OFFLINE_PRECURSOR_20261103",
 "data_sources":{"r37_official_cases":12,"r37_real_trials":120,
   "r38_retrospective_cases":5,"r38_single_core_trials":60,
   "r38_pinned_probe_sha256":next(iter(probe_hashes)),
   "r38_pinned_kissat_sha256":next(iter(kissat_hashes)),
   "manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest()},
 "reexecuted_solver_trials":0,"r37_cases":r37,"r38_cases":r38,
 "single_feature_correlations":correlations,
 "candidate_static_gate":{"description":"Retrospective structural envelope, not validated or deployed",
  "selected_case_ids":[x["id"] for x in selected],
  "in_sample_nohint_mean_PAR2_s":nohint_mean,
  "in_sample_oracle_mixed_mean_PAR2_s":retro_mean,
  "posthoc_delta_pct":100*(nohint_mean-retro_mean)/nohint_mean,
  "warning":"Thresholds fitted after seeing all 12 outcomes; NOT predictive evidence."},
 "study_limitations":["Only six R37 solved formulas have informative paired hint effects",
  "Six additional formulas have all arms timed out, so they cannot be labelled as no-benefit",
  "One strong beneficial example; no prospective validation and no reliable LOOCV recall",
  "Existing V9.1 quality rule already checks LBD2>=6% and propagation>=32/conflict",
  "V9.1 gate only acts in extended continuation; beneficial eager-hint example early-resumes",
  "Checkpoint at 256 cannot select pre-search (eager) hints: temporal leakage if used for that",
  "No causal proof of general prediction or active gate speedup; no new SAT runs"]}
 (o/"r39_report.json").write_text(json.dumps(result,indent=2)+"\n")
 with (o/"r39_r37_pairs.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["id","label","category","comparison","hint_par2_s","nohint_par2_s","cadical_par2_s","hint_to_nohint_PAR2_ratio","static_candidate_selects",*FEATURES]);w.writeheader()
  for x in r37:w.writerow({**{k:v for k,v in x.items() if k!="features"},**x["features"]})
 md=["# DRNAS R39 artifact-only signal audit","",
 "No native SAT solver was executed. R37: 12 genuine official 2026 CNFs, 120 existing attempts, 6 informative paired outcomes. R38: 5 retrospectively selected official CNFs, 60 existing attempts.","",
 "## Complete R37 paired hint responses","",
 "| CNF | Label | guided / no-hints PAR2 | Interpretation |",
 "|---|---|---:|---|"]
 for x in r37:md.append(f'| {x["id"][:8]} | {x["label"]} | {x["hint_to_nohint_PAR2_ratio"]:.3f}x | {x["category"]} |')
 md+=["","## R38 pre-intervention controls","",
 "| CNF | LBD2 share at 256 | Props per conflict | Old V9.1 signal | Continuation | Late hints activated | Early hints effect |",
 "|---|---:|---:|---|---|---|---:|"]
 for x in r38:
  v=x["checkpoint"]
  if v is None:md.append(f'| {x["id"][:8]} | unknown (timeout) | unknown | unknown | unknown | unknown | censored |')
  else:md.append(f'| {x["id"][:8]} | {100*v["lbd2_fraction"]:.2f}% | {v["propagations_per_conflict"]:.1f} | {v["prior_v91_quality_rule"]} | {"extended" if v["v91_early_continuation"] else "early resume"} | {v["actual_late_intervention"]} | {v["eager_hints_ratio"]:.3f}x |')
 md+=["","## Exact permutation correlation, 6 solved cases","",
 "| Static metric | Spearman rho | Unadjusted exact p |",
 "|---|---:|---:|"]
 for k,v in correlations.items():md.append(f'| {k} | {v["spearman_rho"]:.3f} | {v["exact_two_sided_permutation_p"]:.3f} |')
 md+=["","None of the nine static univariate features has an unadjusted p below 0.05; multiple testing only weakens evidence.",
 "","## Exploratory candidate (NOT validated)",
 f'Selects only {selected[0]["id"][:8]} among 12 cases; retrospective simulated mean PAR2 {retro_mean:.4f}s versus frozen no-hint {nohint_mean:.4f}s, apparent {100*(nohint_mean-retro_mean)/nohint_mean:.3f}% improvement. This is post-selection replay, not a new tested solver.',
 "","## Important causal boundary",
 "The large LBD2/propagation precursor at 256 conflicts exists in pre-existing V9.1 source, but in the single beneficial eager-hint case V9.1 takes early-resume and therefore cannot apply delayed hints. The time-256 signal cannot justify a hint decision at time zero. Any new decision at early-resume needs separately implemented prospective native experiment.",
 "","R39 is a diagnostic negative/limited result, not a demonstrated new law or scientific record."]
 (o/"r39_report.md").write_text("\n".join(md)+"\n")
 print("R39_OFFLINE_AUDIT_PASS",json.dumps({"r37":len(r37),"r38":len(r38),"solved_pairs":len(complete),"unknown_early_prefix":unknown,"static_gate_selected":len(selected),"nohint_par2_s":nohint_mean,"posthoc_par2_s":retro_mean,"native_trials_executed":0,"smallest_unadjusted_p":min(x["exact_two_sided_permutation_p"] for x in correlations.values())},sort_keys=True),flush=True)
if __name__=="__main__":main()

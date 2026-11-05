#!/usr/bin/env python3
"""Audit ALL original SAT-Competition 2026 trials and evaluate a frozen train/test
static-feature method selector. Never use official label, instance ID, official
time, or heldout results as prediction input; keep every timeout in PAR2.
A true general-win claim requires a larger independent externally rerun holdout.
"""
import csv,hashlib,json,math,statistics,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-official")
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v92_structural")
CAPS=(2.0,15.0)
FEATURES=("log_vars","log_clauses","clause_var","avg_width","binary_frac",
          "ternary_frac","four_frac","polarity_imbalance","majority_coverage")
def par2(r):
    if r["status"] in ("SAT","UNSAT"):
        return float(r["wall_s"])
    if r["status"]=="TIMEOUT":
        return 2*float(r["cap_s"])
    raise ValueError("Invalid trial "+str(r))
def best_constant(train,loss):
    return min(MODES,key=lambda mode:(sum(loss[id][mode] for id in train),MODES.index(mode)))
def fit_stump(train,loss,features,min_leaf=2):
    fallback=best_constant(train,loss)
    best=None
    for feat in FEATURES:
        sorted_values=sorted({features[id][feat] for id in train})
        for a,b in zip(sorted_values,sorted_values[1:]):
            threshold=(a+b)/2
            left=[id for id in train if features[id][feat]<=threshold]
            right=[id for id in train if features[id][feat]>threshold]
            if min(len(left),len(right))<min_leaf:continue
            m1=best_constant(left,loss);m2=best_constant(right,loss)
            if m1==m2:continue
            score=sum(loss[id][m1] for id in left)+sum(loss[id][m2] for id in right)
            # deterministic simplicity tie-breaking, so reproducible.
            record=(score,FEATURES.index(feat),threshold,MODES.index(m1),MODES.index(m2))
            if best is None or record<best[0]:
                best=(record,dict(kind="stump",feature=feat,threshold=threshold,
                                  low=m1,high=m2,
                                  train_left=len(left),train_right=len(right)))
    return best[1] if best is not None else dict(kind="constant",mode=fallback)
def predict(model,id,features):
    if model["kind"]=="constant":return model["mode"]
    return model["low"] if features[id][model["feature"]]<=model["threshold"] else model["high"]
def main():
    manifest=json.loads(Path("original_manifest/official_shortlong_manifest.json").read_text())
    assert len(manifest["cases"])==18
    items={x["id"]:x for x in manifest["cases"]}
    train=[x["id"] for x in manifest["cases"] if x["split"]=="train"]
    test=[x["id"] for x in manifest["cases"] if x["split"]=="holdout"]
    assert len(train)==9 and len(test)==9
    raw=[]
    for shard in range(6):
        path=ROOT/f"official-shortlong-shard-{shard}"/"results"/"raw.csv"
        with path.open(newline="",encoding="utf8") as f:raw.extend(csv.DictReader(f))
    assert len(raw)==18*2*len(CAPS)*len(MODES)*2,len(raw)
    expected={(id,cap,mode,rep) for id in items for cap in CAPS
              for mode in MODES for rep in (0,1)}
    observed={(r["id"],float(r["cap_s"]),r["mode"],int(r["rep"])) for r in raw}
    assert expected==observed and len(raw)==len(expected)
    for r in raw:
        assert r["sha256"]==items[r["id"]]["sha256"]
        assert r["split"]==items[r["id"]]["split"]
        if r["status"] not in ("SAT","UNSAT","TIMEOUT"):
            raise RuntimeError("Benchmark incomplete; no predictor will be selected: "+str(r))
        if r["status"] in ("SAT","UNSAT"):
            assert r["status"]==items[r["id"]]["official_label"]
    grouped=defaultdict(list)
    for r in raw:grouped[(r["id"],r["mode"],float(r["cap_s"]))].append(r)
    assert all(len(v)==2 for v in grouped.values())
    cost={}
    for id in items:
        cost[id]={}
        for mode in MODES:
            cost[id][mode]={cap:statistics.mean(par2(r) for r in grouped[(id,mode,cap)])
                            for cap in CAPS}
    # Balanced objective across short and long time budgets.
    loss={id:{mode:0.5*(cost[id][mode][2.0]/2.0)+
                   0.5*(cost[id][mode][15.0]/15.0)
              for mode in MODES} for id in items}
    features={id:items[id]["features"] for id in items}
    # A lightweight CV selector. All LOOCV folds are TRAIN only.
    cv={"constant":0.0,"stump":0.0}
    for withheld in train:
        others=[id for id in train if id!=withheld]
        const={"kind":"constant","mode":best_constant(others,loss)}
        stump=fit_stump(others,loss,features,min_leaf=2)
        cv["constant"]+=loss[withheld][predict(const,withheld,features)]
        cv["stump"]+=loss[withheld][predict(stump,withheld,features)]
    # Predeclared modest complexity penalty: require >=3% CV improvement.
    selected="stump" if cv["stump"]<cv["constant"]*0.97 else "constant"
    model=(fit_stump(train,loss,features,min_leaf=3) if selected=="stump" else
           {"kind":"constant","mode":best_constant(train,loss)})
    default=best_constant(train,loss)
    model_prediction={id:predict(model,id,features) for id in items}
    oracle={id:min(MODES,key=lambda m:(loss[id][m],MODES.index(m))) for id in items}
    def split_metrics(cases):
        n=len(cases)
        score=lambda choices:sum(loss[id][choices[id]] for id in cases)
        baseline={id:"ca_plain" for id in cases}
        guided={id:"orig_v76" for id in cases}
        static={id:"v92_structural" for id in cases}
        return {"count":n,"chosen_methods":{id:model_prediction[id] for id in cases},
                "normalized_PAR2_total":{"predictor":round(score(model_prediction),6),
                  "train_constant_baseline":round(score({id:default for id in cases}),6),
                  "plain_CaDiCaL":round(score(baseline),6),
                  "v76_guided":round(score(guided),6),
                  "v92_structural":round(score(static),6),
                  "oracle_lower_bound":round(score(oracle),6)},
                "oracle_matches":sum(model_prediction[id]==oracle[id] for id in cases)}
    summary={}
    for cap in CAPS:
        summary[str(cap)]={}
        for mode in MODES:
            rows=[r for r in raw if r["mode"]==mode and float(r["cap_s"])==cap]
            solved=[float(r["wall_s"]) for r in rows if r["status"] in ("SAT","UNSAT")]
            summary[str(cap)][mode]={
                "solved":len(solved),"trials":len(rows),
                "min_solved_s":round(min(solved),5) if solved else None,
                "max_solved_s":round(max(solved),5) if solved else None,
                "median_solved_s":round(statistics.median(solved),5) if solved else None,
                "timeout_censored":len(rows)-len(solved),
                "PAR2_mean_s":round(statistics.mean(par2(r) for r in rows),5)}
    report={
        "protocol":manifest["protocol"],"official_git_blob":manifest["scores_git_blob"],
        "instance_count":18,"raw_trial_count":len(raw),
        "split":{"train":train,"holdout":test},
        "cv_train_only":cv,"model_selection":selected,"fitted_model":model,
        "train_best_constant":default,"train":split_metrics(train),
        "holdout":split_metrics(test),"time_summary":summary,
        "per_case":[{"id":id,"split":items[id]["split"],
                     "official_stratum":items[id]["stratum"],
                     "features":features[id],"oracle_mode":oracle[id],
                     "predicted_mode":model_prediction[id],
                     "normalized_loss":loss[id],"PAR2_by_cap":cost[id]}
                    for id in items],
        "cautions":["Official results used for stratification only; prior public benchmarks make this not truly blind",
                    "18 instances only; holdout n=9. Could be unrepresentative due to file size screening",
                    "Time-outs right-censored; do not report them as a measured maximum completion time",
                    "All variants share same locally instrumented CaDiCaL build and same runner",
                    "SAT results native-witness-checked, UNSAT agrees with official labels; no independent UNSAT proof",
                    "Some methods and heuristics explored previously: no claim of novelty/world record"]
    }
    Path("official_shortlong_prediction.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    lines=["# DRNAS SAT — official 2026 CNF short / long / static prediction benchmark","",
      "**18 authentic official 2026 CNFs, frozen size-bounded sample; 9 train, 9 holdout.**",
      "All original inputs verified by SHA256. Both 2s and 15s caps, 2 repeats, 5 modes.",
      "All modes share instrumented CaDiCaL 3.0.1 on matched single-core runner per shard.",
      "**This is a size-screened sample, not a blind or representative competition result.**",
      "",
      "## Shortest and longest FINISHED times (seconds); no timeouts disguised as max","",
      "| Wall cap | Solver | Solved / Trials | Min solved | Max solved | Timeouts | Mean PAR2 |",
      "|---|---|---:|---:|---:|---:|---:|"]
    for cap in CAPS:
        for mode in MODES:
            d=summary[str(cap)][mode]
            fmt=lambda x:"n/a" if x is None else f"{x:.4f}"
            lines.append(f"| {cap:g}s | {mode} | {d['solved']}/{d['trials']} | {fmt(d['min_solved_s'])} | {fmt(d['max_solved_s'])} | {d['timeout_censored']} | {d['PAR2_mean_s']:.4f} |")
    lines+=["","## Prediction — trained only on 9 training instances","",
        f"Train-only leave-one-out objective: constant {cv['constant']:.4f}; one-feature tree {cv['stump']:.4f}.",
        f"Selected model: **{selected}**, fitted: **{model}**.",
        f"Best train-only global default: **{default}**.",
        "**Prediction inputs only:** "+", ".join(FEATURES)+".",
        "No instance ID, source baseline time, official SAT/UNSAT label or heldout target is a predictor feature.",
        "",
        "| Split | Predictor score | Plain CaDiCaL | Guided v7.6 | v9.2 Structural | Oracle unattainable |",
        "|---|---:|---:|---:|---:|---:|"]
    for name in ("train","holdout"):
        a=report[name]["normalized_PAR2_total"]
        lines.append(f"| {name} ({report[name]['count']}) | {a['predictor']:.4f} | {a['plain_CaDiCaL']:.4f} | {a['v76_guided']:.4f} | {a['v92_structural']:.4f} | {a['oracle_lower_bound']:.4f} |")
    lines+=["","Holdout selection and measured per-case results are in the attached JSON.",
       "A simple predictor is only accepted if it improves training CV; independent 9-case holdout measures actual generalization.",
       "**Negative outcomes and timeouts retained. No world record / P vs NP claim.**"]
    out="\n".join(lines)+"\n"
    Path("official_shortlong_report.md").write_text(out)
    print(out,flush=True)
if __name__=="__main__":main()

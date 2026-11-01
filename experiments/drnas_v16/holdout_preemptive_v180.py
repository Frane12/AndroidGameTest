#!/usr/bin/env python3
"""V18.0: external prospective blind A/B test of preemptive regression prediction.

New random-3SAT 180100..180123, two repeats, 4 frozen policies = 192 trials.
The five early measurements and the rule are fixed before seeing outcomes.
The riskgate can SKIP before any restart-interval intervention, or apply a
pre-registered SWITCH1024/SWITCH2048. Do not refit on holdout.
"""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path
from preemptive_common_v180 import (CAP,PINNED,ALL_MODES,FIELDS,
    fresh_case,execute,write_csv,write_json,sha_file,is_bad,is_good,rank,bootstrap_cluster)

SEEDS=tuple(range(180100,180124))
REPEATS=2

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--rule",type=Path,required=True)
    p.add_argument("--model",type=Path,required=True)
    a=p.parse_args()
    root=a.root
    root.mkdir(parents=True,exist_ok=True)
    model=json.loads(a.model.read_text())
    assert model["frozen_before_holdout"] is True
    assert model["pin"]==PINNED
    assert model["n_development_formulas"]==42
    line=a.rule.read_text().split()
    assert len(line)==5
    expected=model["rule"]
    assert line[0]==expected["feature"] and line[1]==expected["op"]
    assert int(line[3])==expected["pass_action"]
    assert int(line[4])==expected["fail_action"]
    assert abs(float(line[2])-float(expected["threshold"]))<1e-12
    cases=[fresh_case(root,seed,180100) for seed in SEEDS]
    write_json(root/"manifest.json",{"version":"V18.0","stage":"unseen holdout",
        "pin":PINNED,"seeds":SEEDS,"repeats":REPEATS,"modes":ALL_MODES,
        "cap_seconds":CAP,"rule_sha256":sha_file(a.rule),"model":model,
        "n_trials":len(cases)*len(ALL_MODES)*REPEATS,
        "cases":cases,"training_set_excluded":True,
        "risk_labels":{"severe":"solved->timeout or >=1.5x and >=0.15s slower",
          "helpful":"timeout->solved or >=25pct and >=0.1s faster"}})
    rows=[]
    all_details=[]
    for c in cases:
        for rep in range(REPEATS):
            offset=rep%len(ALL_MODES)
            modes=ALL_MODES[offset:]+ALL_MODES[:offset]
            trial={}
            for mode in modes:
                x=execute(a.solver,c,mode,rep,root,rule_file=a.rule)
                trial[mode]=x
                all_details.append(x)
                flat={key:value for key,value in x.items() if key!="features"}
                flat.update({"feature_"+k:(x["features"][k] if x["features"] else "")
                            for k in FIELDS})
                rows.append(flat)
                print("V180_HOLDOUT_MEASURE",c["seed"],rep,mode,x["status"],
                  f'{x["wall"]:.5f}s',"action",x["action"],
                  "changed",x["switched"],"conflicts",x["final_conflicts"],flush=True)
            logical={v["status"] for v in trial.values() if v["status"] in ("SAT","UNSAT")}
            assert len(logical)<=1,"SAT/UNSAT contradiction"
            base=trial["baseline"]
            if base["features"] is not None:
                for mode in ALL_MODES[1:]:
                    feats=trial[mode]["features"]
                    if feats:
                        for f in FIELDS:
                            if abs(base["features"][f]-feats[f])>1e-4:
                                raise RuntimeError("Different pre-action checkpoint despite same CNF/seed "+str((c["seed"],rep,mode,f)))
            print("V180_COMPLETE_PAIR",c["seed"],rep,
              json.dumps({k:{"status":v["status"],"wall":v["wall"],
                "action":v["action"]} for k,v in trial.items()},separators=(",",":")),
              flush=True)
            write_csv(root/"measurements.partial.csv",rows)
    assert len(rows)==24*2*4
    scores=rank(all_details)
    for s in scores:
        s["95pct_formula_cluster_bootstrap_delta_PAR2_seconds"]=bootstrap_cluster(all_details,s["mode"])
    by={(x["seed"],x["rep"],x["mode"]):x for x in all_details}
    counters={"riskgate_true_skips":0,"riskgate_selected_1024":0,
      "riskgate_selected_2048":0,"regressions_1024_avoided":0,
      "regressions_2048_avoided":0,"helpful_1024_skipped":0,
      "helpful_2048_skipped":0,"riskgate_bad_actions":0,
      "riskgate_good_actions":0}
    detailed=[]
    for seed in SEEDS:
        for rep in range(REPEATS):
            b=by[(seed,rep,"baseline")]
            g=by[(seed,rep,"riskgate")]
            a1024=by[(seed,rep,"switch1024")]
            a2048=by[(seed,rep,"switch2048")]
            chosen=g["action"]
            counters["riskgate_true_skips"]+=int(chosen==0)
            counters["riskgate_selected_1024"]+=int(chosen==1024)
            counters["riskgate_selected_2048"]+=int(chosen==2048)
            counters["regressions_1024_avoided"]+=int(chosen!=1024 and is_bad(b,a1024))
            counters["regressions_2048_avoided"]+=int(chosen!=2048 and is_bad(b,a2048))
            counters["helpful_1024_skipped"]+=int(chosen!=1024 and is_good(b,a1024))
            counters["helpful_2048_skipped"]+=int(chosen!=2048 and is_good(b,a2048))
            counters["riskgate_bad_actions"]+=int(is_bad(b,g))
            counters["riskgate_good_actions"]+=int(is_good(b,g))
            detailed.append({"seed":seed,"repeat":rep,"choice":chosen,
                "base_par2":b["par2"],"gate_par2":g["par2"],
                "regression1024":is_bad(b,a1024),"regression2048":is_bad(b,a2048),
                "helpful1024":is_good(b,a1024),"helpful2048":is_good(b,a2048),
                "observed_features":b["features"]})
    write_csv(root/"measurements.csv",rows)
    write_csv(root/"ranking.csv",scores)
    write_json(root/"risk_decisions.json",detailed)
    summary={"stage":"unseen holdout","n_formulas":len(SEEDS),
        "n_trials":len(rows),"repeats":REPEATS,"rule_sha256":sha_file(a.rule),
        "ranking":scores,"preemptive_decisions":counters,
        "limitations":[
            "A small synthetic random 3SAT distribution; cannot generalize to arbitrary SAT",
            "Two repeats on each formula are not 48 statistically independent formulas",
            "2.5-second timeout makes PAR-2 censored and does not prove UNSAT",
            "Even pre-intervention correlation does not prove causality",
            "Learned policy must not be retuned using this heldout data",
            "Model may abstain entirely if LOOCV risk/benefit evidence is insufficient"]}
    write_json(root/"summary.json",summary)
    print("V180_BLIND_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()

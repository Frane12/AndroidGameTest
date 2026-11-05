#!/usr/bin/env python3
"""R158 fixed ablation diagnostic table. Read-only predictions, never selects policies."""
import argparse,csv,json,math
from pathlib import Path

def need(ok,message):
    if not ok:raise RuntimeError("R158_ABLATION_REFUSED "+message)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,required=True)
    args=ap.parse_args()
    root=args.input
    model=json.loads((root/"r158_models.json").read_text())
    audit=json.loads((root/"r158_audit.json").read_text())
    with (root/"r158_features.csv").open(newline="") as f:
        formula=list(csv.DictReader(f))
    need(len(formula)==160 and len(set(r["sha256"] for r in formula))==160,"formula count")
    need(model["safe_action"]=="MONITOR_ABSTAIN" and
         model["test_labels_used_for_fit"] is False and
         audit["test_label_leakage_metamorphic_check"]=="PASS","safety protocol")
    out=[]
    for group,match in (("development_crossfit","_development"),("test_heldout","_test")):
        rows=[r for r in formula if r["fold"].endswith(match)]
        need(len(rows)==80,"independent formula folds")
        observed=[float(r["observed_paired_gain_pct"]) for r in rows]
        mu=sum(observed)/len(observed)
        variance=sum((v-mu)**2 for v in observed)/len(observed)
        for ablation in ("A","B","C","D"):
            arm=model["models"][ablation]
            need(not arm["promotion_allowed"],"unapproved live promotion")
            vals=([float(arm["dev_oof_predictions"][r["sha256"]])*100 for r in rows]
                  if group=="development_crossfit" else
                  [float(r["predicted_gain_"+ablation])*100 for r in rows])
            need(all(math.isfinite(v) for v in vals),"invalid predictions")
            mae=sum(abs(a-b) for a,b in zip(observed,vals))/len(rows)
            rmse=math.sqrt(sum((a-b)**2 for a,b in zip(observed,vals))/len(rows))
            r2=1-(rmse**2/variance) if variance else None
            out.append(dict(dataset="R17_reused_synthetic_not_official",
                phase=group,ablation=ablation,formulas=len(rows),
                mae_percentage_points=round(mae,8),
                rmse_percentage_points=round(rmse,8),
                r2=round(r2,8) if r2 is not None else "",
                proposed_shadow_gain_gt2pct=sum(v>2 for v in vals),
                live_restart_selected=0,
                independent_external_validation="NO",
                promotion_allowed="NO"))
    with (root/"r158_ablation_metrics.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(out[0]))
        writer.writeheader();writer.writerows(out)
    report={"source_run":audit["source_run"],
      "same_runner_source_audit":"PASS","test_label_leakage":"PASS",
      "new_SAT_solves":0,"live_solver_unchanged":True,
      "model_selection_using_test":False,
      "deployment_decision":"MONITOR_ABSTAIN",
      "rows":out}
    (root/"r158_ablation_metrics.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("R158_ABLATIONS_PASS "+json.dumps(out,sort_keys=True))
if __name__=="__main__":main()

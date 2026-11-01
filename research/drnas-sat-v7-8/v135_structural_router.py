#!/usr/bin/env python3
"""V13.5: transparent, training-only structural router diagnostic.

The only training data are the previously seen 18 official CNFs in the
V13.3 mini calibration. Report feature associations and leave-one-out
estimates, then serialize a completely locked model for later testing.
No new solver run or world-ranking claim.
"""
import argparse, hashlib, json, math, statistics
from pathlib import Path
from collections import Counter

FEATURES=("log_vars","log_clauses","clause_var","avg_width","binary_frac",
          "ternary_frac","four_frac","polarity_imbalance","majority_coverage")
NEAR_FEATURES=("log_vars","clause_var","avg_width","binary_frac","polarity_imbalance")
K=3
MARGIN=1.0
BASE="DRNAS_Legacy"
ALT="Kissat404"
PROTOCOL="DRNAS-V135-TRAIN-ONLY-fixed-K3-20261101"
def check(v,msg):
    if not v: raise RuntimeError(msg)
def avg(xs): return statistics.mean(xs)
def feats(c):
    return [float(c["features"][name]) for name in NEAR_FEATURES]
def predict(train, q):
    # Distance/scale derived only from training samples supplied by caller.
    means=[avg([feats(p)[j] for p in train]) for j in range(len(NEAR_FEATURES))]
    scales=[max(statistics.pstdev([feats(p)[j] for p in train]),0.05)
            for j in range(len(NEAR_FEATURES))]
    def distance(p):
        a=feats(p);b=feats(q)
        return sum(((a[j]-b[j])/scales[j])**2 for j in range(len(a)))
    near=sorted(train,key=lambda p:(distance(p),p["sha256"]))[:K]
    if len(near)<K:return BASE, 0.0, []
    deltas=[float(p["PAR2_by_solver_s"][BASE])-float(p["PAR2_by_solver_s"][ALT])
            for p in near] # Positive means Kissat is faster
    choose=ALT if sum(d>MARGIN for d in deltas)>=2 and statistics.median(deltas)>MARGIN else BASE
    return choose,round(statistics.median(deltas),5),[p["sha256"][:10] for p in near]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True);p.add_argument("--json",required=True)
    p.add_argument("--md",required=True)
    a=p.parse_args()
    z=json.loads(Path(a.source).read_text())
    c=z["cases"]
    check(len(c)==18 and len({r["sha256"] for r in c})==18,"Training set must be 18 unique inputs")
    informative=[r for r in c if r["informative"]]
    check(len(informative)==9,"Expected nine fixed informative training cases")
    for v in c:
        check(all(name in v["features"] for name in FEATURES),"Missing static feature")
        check(BASE in v["PAR2_by_solver_s"] and ALT in v["PAR2_by_solver_s"],"Missing comparator")
    winner=Counter()
    for r in informative:
        d=r["PAR2_by_solver_s"][BASE]-r["PAR2_by_solver_s"][ALT]
        winner[ALT if d>MARGIN else BASE if d< -MARGIN else "tie"]+=1
    # No model or feature choice based on later synthetic solver outcomes.
    rows=[]
    for q in c:
        t=[x for x in informative if x["sha256"]!=q["sha256"]]
        choice,signal,neighbors=predict(t,q)
        x=float(q["PAR2_by_solver_s"][choice])
        rows.append({"sha256":q["sha256"],"informative":q["informative"],
                    "predicted":choice,"median_neighbor_gain_s":signal,
                    "neighbors":neighbors,"chosen_PAR2_s":x,
                    "legacy_PAR2_s":float(q["PAR2_by_solver_s"][BASE]),
                    "kissat_PAR2_s":float(q["PAR2_by_solver_s"][ALT])})
    means={mode:round(avg([r[mode+"_PAR2_s"] if mode=="legacy" else r["kissat_PAR2_s"]
                                  for r in rows]),5)
           for mode in ("legacy","kissat")}
    model={"protocol":PROTOCOL,"features":list(NEAR_FEATURES),"k":K,
           "threshold_seconds":MARGIN,"decision":"Kissat if >=2/3 neighbors favor by >1s and median gain >1s; otherwise DRNAS Legacy",
           "training_sha256":[x["sha256"] for x in c],
           "informative_training":informative,
           "training_only":True,
           "no_validation_claim":True,
           "leave_one_out":{"router_PAR2_s":round(avg([r["chosen_PAR2_s"] for r in rows]),5),
             "DRNAS_Legacy_PAR2_s":round(avg([r["legacy_PAR2_s"] for r in rows]),5),
             "Kissat404_PAR2_s":round(avg([r["kissat_PAR2_s"] for r in rows]),5),
             "kissat_choices":sum(r["predicted"]==ALT for r in rows)},
           "observed_training_winner_counts":dict(winner),"rows":rows}
    # Fix model integrity once at source: all train IDs and features serialized in JSON.
    Path(a.json).write_text(json.dumps(model,sort_keys=True,indent=2)+"\n")
    txt=["# DRNAS V13.5 — training-only structural feature router","",
        "**18 previously observed 2026 CNFs; nine training-informative instances. NOT an independent validation.**",
        "Five static features: "+", ".join(NEAR_FEATURES)+".",
        "K=3 nearest informative neighbors, standardized on training data; fixed 1 s margin.",
        "Output rule chooses Kissat only when 2+ neighbors and median both favor Kissat by >1s.",
        "Each leave-one-out query excludes itself, but all hyperparameters and training set were chosen for exploratory research.","",
        "| Training-only LOOCV policy | PAR-2 (s, lower better) |","|---|---:|"]
    for k,label in (("router_PAR2_s","K3 static router"),("DRNAS_Legacy_PAR2_s","Always DRNAS Legacy"),("Kissat404_PAR2_s","Always Kissat404")):
        txt.append(f"| {label} | {model['leave_one_out'][k]:.5f} |")
    txt += ["",f"Kissat predictions: {model['leave_one_out']['kissat_choices']}/18.",
            "Winner labels among informative training formulas: "+str(dict(winner))+".",
            "","**LOOCV on 18 preselected formulas is not prospective evidence.**",
            "Any synthetic holdout analysis must be disclosed as separate, out-of-distribution and exploratory."]
    Path(a.md).write_text("\n".join(txt)+"\n")
    print("\n".join(txt),flush=True)
    print("V135_TRAIN_ONLY_PASS",len(c),len(informative),flush=True)
if __name__=="__main__":main()

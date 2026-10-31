#!/usr/bin/env python3
"""Static, label-blind structural feature extractor and tiny interpretable SAT selector.

Training is ONLY from completed v8.5 manifests/raw measurements.
No solver internals, family names, SAT/UNSAT labels or holdout timings are used
as predictive features. The predictor never alters CaDiCaL or its clauses.
"""
import hashlib
import itertools
import json
import math
import statistics
from collections import Counter
from pathlib import Path

MODES = ("ca_plain", "orig_v76_plain", "orig_v76")
FEATURES = (
    "log_vars", "density", "avg_width", "binary_fraction",
    "ternary_fraction", "width4_fraction", "degree_cv",
    "polarity_imbalance", "hint_fraction", "sample_pair_reuse",
)
MIN_LEAF = 5
MIN_RELATIVE_GAIN = 0.05

def get_features(cnf):
    cnf = Path(cnf)
    n = 0
    advertised = None
    clauses = []
    cur = []
    for line in cnf.read_text().splitlines():
        if not line or line[0] == "c":
            continue
        if line[0] == "p":
            tokens = line.split()
            assert tokens[1] == "cnf" and len(tokens) == 4
            n = int(tokens[2])
            advertised = int(tokens[3])
            continue
        for token in line.split():
            lit = int(token)
            if not lit:
                clauses.append(cur)
                cur = []
            else:
                cur.append(lit)
    assert not cur and len(clauses) == advertised
    assert n > 0 and all(0 < abs(lit) <= n for clause in clauses for lit in clause)
    pos = [0] * (n + 1)
    neg = [0] * (n + 1)
    length = Counter()
    for clause in clauses:
        length[len(clause)] += 1
        for lit in clause:
            (pos if lit > 0 else neg)[abs(lit)] += 1
    degrees = [pos[i] + neg[i] for i in range(1, n + 1)]
    avg = sum(degrees) / n
    degree_cv = math.sqrt(sum((d-avg)**2 for d in degrees)/n)/max(avg,1)
    imbalances = [abs(pos[i]-neg[i])/max(1,degrees[i-1]) for i in range(1,n+1)]
    hints = sum(degrees[i-1] >= 6 and imbalances[i-1]>=0.15 and pos[i]!=neg[i]
                for i in range(1,n+1))
    selected = [clauses[k*len(clauses)//min(128,len(clauses))]
                for k in range(min(128,len(clauses)))]
    edges = set()
    total = 0
    for clause in selected:
        for lit1,lit2 in itertools.combinations(clause,2):
            a,b=sorted((abs(lit1),abs(lit2)))
            if a != b:
                total += 1
                edges.add((a,b))
    features = {
        "log_vars": math.log1p(n),
        "density": len(clauses)/n,
        "avg_width": sum(i*v for i,v in length.items())/max(1,len(clauses)),
        "binary_fraction": length[2]/max(1,len(clauses)),
        "ternary_fraction": length[3]/max(1,len(clauses)),
        "width4_fraction": length[4]/max(1,len(clauses)),
        "degree_cv": degree_cv,
        "polarity_imbalance": sum(imbalances)/n,
        "hint_fraction": hints/n,
        "sample_pair_reuse": (total-len(edges))/max(1,total),
    }
    return {k:round(float(features[k]),8) for k in FEATURES}

def predict(model,features):
    if model["kind"]=="constant":
        return model["mode"]
    feature=model["feature"]
    return model["left"] if features[feature]<=model["threshold"] else model["right"]

def learn(samples):
    """One shallow decision stump using only informative v8.5 trials.

    Formulas where ALL modes timed out give no comparison signal and are
    omitted from training loss only. All test formulas still count in
    out-of-sample PAR2. Mode-specific timeouts remain penalized at 6s.
    """
    assert len(samples)==40
    eligible=[item for item in samples if min(item[1].values())<6.0]
    assert len(eligible)>=12
    baseline=sum(costs["ca_plain"] for _,costs in eligible)
    def choose(group):
        usable=[(f,c) for f,c in group if min(c.values())<6.0]
        if len(usable)<5:
            return "ca_plain",sum(c["ca_plain"] for _,c in usable)
        base=sum(c["ca_plain"] for _,c in usable)
        options=sorted((sum(c[m] for _,c in usable),m) for m in MODES)
        best_cost,best_mode=options[0]
        if best_mode!="ca_plain" and (base-best_cost)/max(base,1e-9)<MIN_RELATIVE_GAIN:
            return "ca_plain",base
        return best_mode,best_cost
    constant_mode,constant_loss=choose(eligible)
    best={"kind":"constant","mode":constant_mode,"loss":constant_loss}
    complexity_penalty=0.01*baseline
    for feature in FEATURES:
        ordered=sorted(set(f[feature] for f,_ in eligible))
        for lo,hi in zip(ordered,ordered[1:]):
            threshold=round((lo+hi)/2,10)
            left=[item for item in eligible if item[0][feature]<=threshold]
            right=[item for item in eligible if item[0][feature]>threshold]
            if min(len(left),len(right))<MIN_LEAF:
                continue
            left_mode,left_loss=choose(left)
            right_mode,right_loss=choose(right)
            loss=left_loss+right_loss+complexity_penalty
            if loss < best["loss"]-1e-9:
                best={"kind":"stump","feature":feature,"threshold":threshold,
                      "left":left_mode,"right":right_mode,
                      "left_size":len(left),"right_size":len(right),"loss":loss}
    best["training_case_count"]=len(samples)
    best["training_informative_count"]=len(eligible)
    best["training_baseline_par2_sum"]=round(baseline,6)
    best["training_selected_par2_sum"]=round(best["loss"],6)
    best["training_relative_gain"]=round((baseline-best["loss"])/max(baseline,1e-9),6)
    best["min_leaf"]=MIN_LEAF
    best["min_relative_leaf_gain"]=MIN_RELATIVE_GAIN
    best["complexity_penalty_fraction"]=0.01
    best["features"]=list(FEATURES)
    best["all_timeout_exclusion"]="training only; full held-out result still includes them"
    return best

def train(root,output):
    import csv
    root=Path(root); out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    samples=[]
    digests=[]
    for shard in range(5):
        folder=root/("shard-"+str(shard))
        manifest=json.loads((folder/"manifest.json").read_text())
        assert manifest["version"]=="drnas-blind-v85-20261031-fresh-40-seeds-v1"
        with (folder/"raw.csv").open(newline="") as fh:
            rows=list(csv.DictReader(fh))
        for case in manifest["cases"]:
            name=case["family"]+"-"+str(case["size"])
            cnf=folder/(name+".cnf")
            assert hashlib.sha256(cnf.read_bytes()).hexdigest()==case["sha256"]
            per_mode={}
            for mode in MODES:
                vals=[r for r in rows if r["case"]==name and r["mode"]==mode]
                assert len(vals)==3
                assert {int(v["repeat"]) for v in vals}=={0,1,2}
                assert all(v["status"] in ("SAT","UNSAT","TIMEOUT") for v in vals)
                costs=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT")
                       else 6.0 for r in vals]
                per_mode[mode]=statistics.median(costs)
            samples.append((get_features(cnf),per_mode))
            digests.append(case["sha256"])
    assert len(samples)==40 and len(set(digests))==40
    model=learn(samples)
    model["train_source_run"]=41224588277
    model["train_source_aggregate_run"]=41224873765
    model["training_hashes_sha256"]=hashlib.sha256(
        "\n".join(sorted(digests)).encode()).hexdigest()
    (out/"model.json").write_text(json.dumps(model,indent=2,sort_keys=True)+"\n")
    report="# DRNAS v8.7 frozen static selector training\n\n"
    report+="Trained on v8.5 only, 40 already measured formulas, no holdout included.\n"
    report+="Features exclude family and SAT/UNSAT labels, with approximate permutation-invariant structural counts.\n"
    report+="Depth 1, minimum 5 informative cases/leaf, 5% minimum leaf improvement, 1% complexity penalty.\n"
    report+="Fully timed-out v8.5 cases are excluded only from fitting cost; all fresh test rows still enter final PAR2. No generalization claimed until evaluation.\n\n"
    report+=json.dumps(model,indent=2,sort_keys=True)+"\n"
    (out/"training_report.md").write_text(report)
    print(report,flush=True)

if __name__=="__main__":
    import sys
    if len(sys.argv)!=3:
        raise SystemExit("Usage: selector_v86.py OLD_V85_DIR OUTPUT_DIR")
    train(sys.argv[1],sys.argv[2])

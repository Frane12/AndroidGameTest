#!/usr/bin/env python3
"""Train transparent 1-split selector from V17.6 DEV only.

Supervision is frozen in v177_training_labels_176dev.csv: 20 known development
formulas, baseline vs switch1024 vs switch2048. At conflict 512 observe only
real in-process Kissat signals; never see new 177xxx formulas during fitting.
"""
import argparse,csv,json,os,re,subprocess,statistics,hashlib
from pathlib import Path
from shock_filter_v171 import generate,valid_model

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
FIELDS=("r","d","p","g","l")
MODES=("baseline","switch1024","switch2048")
CAP=2.5
EARLY=re.compile(r"^c DRNAS_V177_EARLY r=([\d.]+) d=([\d.]+) p=([\d.]+) g=([\d.]+) l=([\d.]+) conflict=(\d+) restarts=(\d+)$",re.M)

def read_labels(path):
    with open(path,newline="") as f:rows=list(csv.DictReader(f))
    assert len(rows)==60,"Need exactly 20 x 3 V17.6 DEV records"
    out={}
    for x in rows:
        seed=int(x["seed"])
        assert 176000<=seed<176020 and x["mode"] in MODES
        assert x["status"] in ("SAT","UNSAT","TIMEOUT")
        assert (seed,x["mode"]) not in out
        out[(seed,x["mode"])]=float(x["seconds"]) if x["status"]!="TIMEOUT" else 5.0
    assert len(out)==60
    return out

def collect(solver,root,labels):
    results=[]
    for seed in range(176000,176020):
        n=(260,340,420)[(seed-176000)%3]
        path=root/"cnf"/f"{seed}.cnf"
        h=generate(path,n,4.26,seed)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==h
        env=os.environ.copy();env["DRNAS_V177_MODE"]="observe"
        try:
            p=subprocess.run([solver,"-s",str(path)],text=True,errors="replace",
                env=env,capture_output=True,timeout=CAP,check=False)
            output=p.stdout+"\n"+p.stderr
            assert p.returncode in (0,10,20)
            if p.returncode==10:assert valid_model(path,output)
        except subprocess.TimeoutExpired as e:
            a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
            b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
            output=a+"\n"+b
        m=EARLY.search(output)
        if not m:
            print("V177_FEATURE_MISSING",seed,flush=True)
            continue
        feats={k:float(v) for k,v in zip(FIELDS,m.groups()[:5])}
        assert int(m.group(6))>=512
        row={"seed":seed,"nvars":n,**feats,
            **{mode:labels[(seed,mode)] for mode in MODES}}
        results.append(row)
        print("V177_DEV_FEATURE",seed,json.dumps(feats,separators=(",",":")),flush=True)
    assert len(results)>=17,"Inadequate early feature coverage; don't guess classifier"
    return results

def cost(row,rule):
    feature,op,threshold,action=rule
    pred=row[feature]<threshold if op=="lt" else row[feature]>=threshold
    return row["switch"+str(action)] if pred and action else row["baseline"]

def eval_rule(rows,rule):
    base=sum(r["baseline"] for r in rows)
    out=sum(cost(r,rule) for r in rows)
    sel=[r for r in rows if cost(r,rule)!=r["baseline"]]  # selection count computed independently below
    selected=[r for r in rows if (r[rule[0]]<rule[2] if rule[1]=="lt" else r[rule[0]]>=rule[2])] if rule[3] else []
    regressions=sum(r["baseline"]<5 and r["switch"+str(rule[3])]==5 for r in selected)
    rescues=sum(r["baseline"]==5 and r["switch"+str(rule[3])]<5 for r in selected)
    return {"baseline_total":base,"policy_total":out,"gain_total":base-out,
        "selected":len(selected),"regressions":regressions,"rescues":rescues}

def fit(rows):
    candidates=[]
    for feature in FIELDS:
        distinct=sorted(set(r[feature] for r in rows))
        boundaries=[(a+b)/2 for a,b in zip(distinct,distinct[1:])]
        for direction in ("lt","ge"):
            for threshold in boundaries:
                for action in (1024,2048):
                    rule=(feature,direction,threshold,action)
                    m=eval_rule(rows,rule)
                    if not (4<=m["selected"]<=len(rows)-3):continue
                    if m["regressions"]>0:continue
                    # discourage memorizing tiny fast instances
                    candidates.append((m["gain_total"],m["rescues"],-m["selected"],rule,m))
    candidates.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3][0],x[3][1],x[3][2],x[3][3]))
    if not candidates or candidates[0][0]<=0.0:
        return ("g","ge",1e12,1024),None
    best=candidates[0]
    return best[3],best[4]

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--labels",type=Path,required=True)
    p.add_argument("--root",type=Path,default=Path("drnas-v177-train"))
    a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True)
    label=read_labels(a.labels)
    rows=collect(a.solver,a.root,label)
    rule,metrics=fit(rows)
    loo=[]
    for i,x in enumerate(rows):
        trained,_=fit(rows[:i]+rows[i+1:])
        loo.append({"seed":x["seed"],"rule":trained,
                    "base":x["baseline"],"pred":cost(x,trained)})
    base=sum(x["base"] for x in loo)
    pred=sum(x["pred"] for x in loo)
    loo_reg=sum(x["base"]<5 and x["pred"]==5 for x in loo)
    loo_resc=sum(x["base"]==5 and x["pred"]<5 for x in loo)
    model={"rule":{"feature":rule[0],"operator":rule[1],
        "threshold":rule[2],"action":rule[3]},
        "training":{"n":len(rows),"metrics":metrics,
            "PAR2_baseline":statistics.mean(x["baseline"] for x in rows),
            "PAR2_rule":statistics.mean(cost(x,rule) for x in rows)},
        "leave_one_formula_out":{"n":len(loo),
            "PAR2_baseline":base/len(loo),"PAR2_selector":pred/len(loo),
            "regressions":loo_reg,"rescues":loo_resc},
        "provenance":"V17.6 development labels only 176000..176019",
        "policy_frozen_before_177_holdout":True,
        "limitations":["20 training formulas; small sample",
          "Stump is hypothesis generating, not proven generalizable",
          "LOO prediction selection is internal validation, not external",
          "Training UNSAT proof not independently verified"]}
    (a.root/"rule.txt").write_text(f"{rule[0]} {rule[1]} {rule[2]:.17g} {rule[3]}\n")
    (a.root/"model.json").write_text(json.dumps(model,indent=2)+"\n")
    with (a.root/"training_features.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (a.root/"loocv.json").write_text(json.dumps(loo,indent=2))
    print("V177_FROZEN_RULE",json.dumps(model,sort_keys=True),flush=True)

if __name__=="__main__":run()

#!/usr/bin/env python3
"""DRNAS Medical R17: PRE-SOLVE prediction of LP-oracle call counts.

Primary hypothesis: pre-solve GPR structural features improve forecasting of
R9's exact search effort beyond gene count N alone.

Training: R9 certified run 42239472392, five original nested 24..384 gene
cohorts. Prospective test: two independently chosen DISJOINT gene families
on the same SHA-locked genome-scale iML1515 network, with sizes
24/48/96/192/384 in each (10 prospective tests). No test outcome or FBA
knockout phenotype is used for feature calculation or model fitting.

Before solving any prospective case, print and persist hashed predictions,
training-only fit coefficients and immutable cohort IDs. A distinct CI job
then executes the ORIGINAL frozen R9 solver with a 120s per-trial cap, two
repetitions and independent per-solution gene-vs-reaction GLPK FBA checks.

Caveats: predicting LP work is not proving asymptotic complexity. Models
trained on a single bacterium; target sets are not independent organisms.
The tested SAT engine is PySAT CaDiCaL, not native DRNAS SAT.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, math, pathlib, random
import statistics, subprocess, sys, time
import numpy as np

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9

PROTO="DRNAS-MEDICAL-R17-PRESOLVE-LP-FORECAST-v1"
R9_RUN=42239472392
R9_COMMIT="7ffccc4293cf5071810b41034d6fd9ddf27b555c"
SOURCE_SHA="9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
SIZES=(24,48,96,192,384)
FAMILIES=("sha_disjoint","degree_disjoint")
CAP=120.0
REPS=2
PAIR_SAMPLES=96
SEED="DRNAS-R17-FROZEN-GENE-PREDICTION-NO-LP-OUTCOMES"

def need(x,msg):
    if not x:raise RuntimeError("R17_FAIL_CLOSED "+str(msg))
def put(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+"\n")
def get(path):return json.loads(pathlib.Path(path).read_text())
def h(v):return hashlib.sha256(v.encode()).hexdigest()
def sha(p):return r8.sha(p)
def gene_sha(g):return h("\n".join(g))
def ncomb(n):return r9.ncomb(n)
def model_no_LP(source):
    from cobra.io import read_sbml_model
    source=pathlib.Path(source)
    reference=r8.verify(source)
    need(reference["SBML_sha256"]==SOURCE_SHA,"wrong original iML1515 SBML")
    model=read_sbml_model(str(source/"iML1515.xml"))
    model.solver="glpk"
    need(r8.dims(model)==r8.EXPECTED_DIMS,"model dimension changed")
    return model,reference

def features(model,genes,rules):
    """Only graph, GPR and source-model metadata; NO FBA/LP solve and no
    knockout biomass query. Deterministic 96-pair GPR-only interaction probe.
    """
    byid={g.id:g for g in model.genes}
    need(len(genes)==len(set(genes)) and all(g in byid for g in genes),
         "gene cohort not in source")
    local={g:set(r.id for r in byid[g].reactions if r.id in rules)
           for g in genes}
    direct={}
    for gid in genes:
        knocked=frozenset((gid,))
        direct[gid]={rid for rid in local[gid]
                     if not rules[rid][2](knocked)}
    degs=[len(local[g]) for g in genes]
    ds=[len(direct[g]) for g in genes]
    affected=set().union(*(local[g] for g in genes))
    singles=set().union(*(direct[g] for g in genes))
    rng=random.Random(h(SEED+":PAIR:"+gene_sha(genes)))
    total=len(genes)*(len(genes)-1)//2
    target=min(PAIR_SAMPLES,total)
    chosen=set()
    while len(chosen)<target:
        a,b=rng.sample(range(len(genes)),2)
        chosen.add((min(a,b),max(a,b)))
    pair_extra=0
    pair_union=0
    pair_shared=0
    for a,b in sorted(chosen):
        x,y=genes[a],genes[b]
        ko=frozenset((x,y))
        candidate=local[x]|local[y]
        disabled={rid for rid in candidate if not rules[rid][2](ko)}
        known=direct[x]|direct[y]
        need(known.issubset(disabled),"non-monotone GPR detected")
        pair_extra+=len(disabled-known)
        pair_union+=len(disabled)
        pair_shared+=len(local[x]&local[y])
    n=len(genes)
    # pre-registered graph-based one-dimensional structural pressure:
    # number of gene-reaction edges + 2* interaction-only GPR effects scaled N.
    pair_synergy=pair_extra/max(1,target)
    graph_pressure=1.0+sum(degs)+2.0*n*pair_synergy
    return {
       "N":n,"candidate_count":ncomb(n),
       "mean_gene_reaction_degree":round(statistics.mean(degs),8),
       "max_gene_reaction_degree":max(degs),
       "reaction_gene_edges":sum(degs),
       "single_gene_reaction_disables":sum(ds),
       "genes_with_singleton_effect":sum(x>0 for x in ds),
       "distinct_GPR_reaction_targets":len(affected),
       "distinct_singleton_disabled_reactions":len(singles),
       "pair_samples":target,
       "mean_pair_synergy_reactions":round(pair_synergy,8),
       "mean_pair_disabled_reactions":round(pair_union/max(1,target),8),
       "mean_pair_reaction_overlap":round(pair_shared/max(1,target),8),
       "graph_pressure_proxy":round(graph_pressure,8),
       "model_reactions":len(model.reactions),
       "model_metabolites":len(model.metabolites),
       "model_genes":len(model.genes),
       "FBA_or_LP_calls_for_features":0,
    }

def fit_ols_1d(train_values,ys):
    xs=np.array([math.log(max(1e-9,x)) for x in train_values],float)
    yy=np.array([math.log(y) for y in ys],float)
    need(float(np.var(xs))>1e-12,"constant predictor")
    beta=float(np.dot(xs-xs.mean(),yy-yy.mean())/
               np.dot(xs-xs.mean(),xs-xs.mean()))
    intercept=float(yy.mean()-beta*xs.mean())
    return {"intercept":intercept,"coefficient":beta}
def predict_ols(coeff,x):
    return float(math.exp(coeff["intercept"]+
                          coeff["coefficient"]*math.log(max(1e-9,x))))

def fit_models(training):
    need([r["N"] for r in training]==list(SIZES),"missing R9 sizes")
    y=[r["LP_calls"] for r in training]
    need(all(v>0 for v in y),"invalid LP count")
    nmodel=fit_ols_1d([r["N"] for r in training],y)
    proxy=fit_ols_1d([r["features"]["graph_pressure_proxy"] for r in training],y)
    # Joint, preregistered ridge (lambda fixed, NO tuning on test cohort).
    # z-normalize the two features, leave intercept unregularized.
    xx=np.array([[math.log(r["N"]),
                  math.log(r["features"]["graph_pressure_proxy"])]
                 for r in training])
    means=np.mean(xx,axis=0)
    scales=np.std(xx,axis=0)
    need(all(scales>1e-10),"degenerate structural training input")
    standardized=(xx-means)/scales
    A=np.column_stack([np.ones(len(training)),standardized])
    yy=np.log(np.array(y,float))
    reg=np.diag([0.,0.75,0.75])
    beta=np.linalg.solve(A.T@A+reg,A.T@yy)
    joint={"intercept":float(beta[0]),
           "coefficients":[float(beta[1]),float(beta[2])],
           "log_means":[float(x) for x in means],
           "log_stds":[float(x) for x in scales],
           "ridge_lambda":0.75}
    # Time model uses only measured training LP/time, not the future counts.
    L=np.array(y,float);T=np.array([r["wall_s"] for r in training],float)
    slope=float(np.dot(L-L.mean(),T-T.mean())/
                np.dot(L-L.mean(),L-L.mean()))
    offset=float(T.mean()-slope*L.mean())
    need(slope>0,"per LP time cost nonpositive")
    return {
      "N_only_power":nmodel,
      "graph_only_power":proxy,
      "N_plus_graph_ridge":joint,
      "time_from_LP":{"intercept_s":offset,"s_per_LP":slope},
      "primary_model":"N_plus_graph_ridge",
      "primary_control":"N_only_power",
      "selection_precommitted":True,
    }

def predict(models,features):
    n=features["N"];graph=features["graph_pressure_proxy"]
    joint=models["N_plus_graph_ridge"]
    z=[(math.log(n)-joint["log_means"][0])/joint["log_stds"][0],
       (math.log(graph)-joint["log_means"][1])/joint["log_stds"][1]]
    q=math.exp(joint["intercept"]+sum(a*b
        for a,b in zip(z,joint["coefficients"])))
    counts={
      "N_only_power":predict_ols(models["N_only_power"],n),
      "graph_only_power":predict_ols(models["graph_only_power"],graph),
      "N_plus_graph_ridge":float(q),
    }
    time_model=models["time_from_LP"]
    sec={name:max(.0001,time_model["intercept_s"]+
          time_model["s_per_LP"]*v) for name,v in counts.items()}
    return {"predicted_LP_calls":{k:round(v,4) for k,v in counts.items()},
            "predicted_solver_s":{k:round(v,4) for k,v in sec.items()}}

def freeze(source,r9_frozen,audit_path,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    training_doc=get(audit_path)
    need(training_doc["status"]=="PASS_COMPLETION_AUDIT" and
         training_doc["source_model_sha256"]==SOURCE_SHA,
         "R9 certified run source/complete audit missing")
    c=training_doc["cohorts"]
    need([x["n"] for x in c]==list(SIZES) and
         all(x["complete"] and x["LP_median"]>0 for x in c),
         "R9 audit incomplete")
    model,m=model_no_LP(source)
    original=r9.check_manifest(source,r9_frozen)
    need(original["source_model_SHA256"]==SOURCE_SHA,
         "R9 frozen original gene pool changed")
    eligible={g.id:g for g in model.genes if len(g.id)==5
              and g.id.startswith("b") and g.id[1:].isdigit() and g.reactions}
    original384=original["cohorts"]["384"]
    remaining=set(eligible)-set(original384)
    need(len(remaining)>=768,"not enough disjoint true locus genes")
    sha_family=sorted(remaining,
        key=lambda s:h(SEED+":SHA:"+s))[:384]
    degree_left=remaining-set(sha_family)
    high_degree=sorted(degree_left,
        key=lambda s:(-len(eligible[s].reactions),
                      h(SEED+":DEGREE:"+s)))[:384]
    need(len(high_degree)==384 and
         not(set(sha_family)&set(high_degree)) and
         not(set(high_degree)&set(original384)) and
         not(set(sha_family)&set(original384)),
         "prospective families leaked into original R9")
    cohorts={FAMILIES[0]:{str(n):sha_family[:n] for n in SIZES},
             FAMILIES[1]:{str(n):high_degree[:n] for n in SIZES}}
    rules=r8.all_rules(model)
    training=[{"N":n,"genes_sha":gene_sha(original["cohorts"][str(n)]),
          "LP_calls":int(c[i]["LP_median"]),
          "wall_s":float(c[i]["wall_median_s"]),
          "features":features(model,original["cohorts"][str(n)],rules)}
          for i,n in enumerate(SIZES)]
    models=fit_models(training)
    predictions=[]
    for fam in FAMILIES:
        for n in SIZES:
            genes=cohorts[fam][str(n)]
            ff=features(model,genes,rules)
            predictions.append({"family":fam,"N":n,
                "gene_ids_SHA256":gene_sha(genes),
                "genes":genes,"features":ff,**predict(models,ff)})
    package={"protocol":PROTO,"source_model_SHA256":SOURCE_SHA,
       "training_gitHub_run":R9_RUN,"training_commit":R9_COMMIT,
       "training_audit_artifact_sha256":sha(audit_path),
       "training_only_R9":training,
       "models_frozen":models,
       "prospective_cohorts":cohorts,
       "predictions":predictions,
       "prospective_outcomes_seen_during_training":False,
       "features_include_growth_or_knockout_phenotype":False,
       "prospective_gene_sets_disjoint_from_R9_and_each_other":True,
       "FBA_LP_calls_to_freeze_features":0,
       "time_cap_per_trial_s":CAP,"repetitions":REPS,
       "not_a_new_complexity_proof":True}
    put(out/"preregistered.json",package)
    digest=sha(out/"preregistered.json")
    (out/"sha256.txt").write_text(digest+"  preregistered.json\n")
    print("R17_PRECOMMITTED",json.dumps({
        "SHA256":digest,"source_SHA256":SOURCE_SHA,
        "train":{str(x["N"]):x["LP_calls"] for x in training},
        "predictions":[{"family":x["family"],"N":x["N"],
            "LP_N_only":x["predicted_LP_calls"]["N_only_power"],
            "LP_graph":x["predicted_LP_calls"]["N_plus_graph_ridge"]}
            for x in predictions]},sort_keys=True),flush=True)

def check_freeze(source,pre,original_r9):
    pre=pathlib.Path(pre)
    p=get(pre/"preregistered.json")
    check=pre/"sha256.txt"
    need(check.exists() and check.read_text().split()[0]==sha(pre/"preregistered.json"),
         "precommitted predictions changed")
    need(p["protocol"]==PROTO and p["source_model_SHA256"]==SOURCE_SHA and
         p["training_gitHub_run"]==R9_RUN and
         p["training_commit"]==R9_COMMIT,
         "wrong training source provenance")
    model,m=model_no_LP(source)
    existing=r9.check_manifest(source,original_r9)
    need(p["training_only_R9"][0]["genes_sha"]==
         gene_sha(existing["cohorts"]["24"]),
         "original R9 reference changed")
    need(len(p["predictions"])==len(SIZES)*len(FAMILIES),"missing precommitted predictions")
    for z in p["predictions"]:
        f,n=z["family"],z["N"];g=p["prospective_cohorts"][f][str(n)]
        need(g==z["genes"] and gene_sha(g)==z["gene_ids_SHA256"],
             "prediction gene cohort mismatched")
    return p

def internal(config,out):
    cfg=get(config);n=cfg["n"];fam=cfg["family"]
    need(cfg["protocol"]==PROTO and
         n in SIZES and fam in FAMILIES and
         cfg["rep"] in range(REPS),"trial arguments invalid")
    p=check_freeze(cfg["source"],cfg["freeze"],cfg["original_r9"])
    genes=p["prospective_cohorts"][fam][str(n)]
    need(gene_sha(genes)==cfg["genes_sha"],"target cohort SHA drift")
    model,m=r8.load_frozen(cfg["source"])
    rules=r8.all_rules(model)
    t0=time.perf_counter()
    result=r9.solve(model,genes,rules,m["wildtype_biomass"]*.01,CAP)
    need(result["status"]=="SOLVED" and result["SAT_UNSAT_stages"]==3,
         "solver did not exhaust three cardinality stages")
    validation=r9.verify_sets(model,genes,rules,m["wildtype_biomass"]*.01,
                               result["minimal_sets"])
    need(validation["sound_minimal"],"independent FBA audit false")
    row={"protocol":PROTO,"source_model_SHA256":SOURCE_SHA,
         "precommit_sha256":sha(pathlib.Path(cfg["freeze"])/"preregistered.json"),
         "family":fam,"N":n,"rep":cfg["rep"],
         "genes_sha":cfg["genes_sha"],
         "status":"SOLVED","wall_s":result["wall_s"],
         "LP_calls":result["lp_calls"],
         "flux_cuts":result["flux_cuts"],
         "solutions":result["minimal_sets"],
         "stage_unsat_certifications":result["SAT_UNSAT_stages"],
         "independent_validation":validation,
         "validator_and_model_time_outside_solver_s":round(
             time.perf_counter()-t0-result["wall_s"],6),
         "algorithm": "R9 frozen exact SAT/LP solver with sound fallback",
         "outer_model_loading_excluded_from_solver_wall":True}
    put(out,row)
    print("R17_TRIAL",json.dumps({"family":fam,"N":n,"rep":cfg["rep"],
        "LP_calls":row["LP_calls"],"wall_s":row["wall_s"],
        "minimal":len(row["solutions"]),
        "flux_cuts":row["flux_cuts"]},sort_keys=True),flush=True)

def spawn(cfg,target):
    target=pathlib.Path(target);cpath=target.with_suffix(".config.json")
    put(cpath,cfg)
    start=time.perf_counter()
    try:
        out=subprocess.run([sys.executable,__file__,"internal",
            "--config",str(cpath),"--out",str(target)],
            text=True,capture_output=True,timeout=CAP+60)
        duration=time.perf_counter()-start
        target.with_suffix(".stdout.txt").write_text(out.stdout[-15000:])
        target.with_suffix(".stderr.txt").write_text(out.stderr[-15000:])
        if out.returncode:
            return {"status":"ERROR","error":out.stderr[-1400:],
                    "outer_wall_s":round(duration,6)}
        x=get(target)
        need(x["wall_s"]<=CAP,"reported time exceeded cap")
        x["outer_wall_s"]=round(duration,6)
        return x
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","outer_wall_s":round(
            time.perf_counter()-start,6)}
    except Exception as e:
        return {"status":"ERROR","error":str(e)}

def test(source,original_r9,freeze_dir,family,n,out):
    need(family in FAMILIES and n in SIZES,"invalid prospective cohort")
    p=check_freeze(source,freeze_dir,original_r9)
    prediction=next(x for x in p["predictions"]
                    if x["family"]==family and x["N"]==n)
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    report={"protocol":PROTO,"source_model_SHA256":SOURCE_SHA,
        "prediction_freeze_SHA256":sha(pathlib.Path(freeze_dir)/"preregistered.json"),
        "family":family,"N":n,
        "prospective_genes_sha":prediction["gene_ids_SHA256"],
        "predictions_frozen_before_solver":prediction,
        "repetitions":REPS,"cap_s":CAP,"trials":[]}
    for rep in range(REPS):
        cfg={"protocol":PROTO,"source":str(pathlib.Path(source).resolve()),
             "original_r9":str(pathlib.Path(original_r9).resolve()),
             "freeze":str(pathlib.Path(freeze_dir).resolve()),
             "family":family,"n":n,"rep":rep,
             "genes_sha":prediction["gene_ids_SHA256"]}
        r=spawn(cfg,out/f"trial-{rep}.json")
        r["rep"]=rep
        report["trials"].append(r)
        put(out/"summary.json",report)
        print("R17_RESULT",json.dumps({"family":family,"N":n,
            "rep":rep,"status":r["status"],
            "actual_LP":r.get("LP_calls"),
            "predicted_primary_LP":
               prediction["predicted_LP_calls"]["N_plus_graph_ridge"],
            "wall_s":r.get("wall_s"),
            "error":r.get("error","")[-150:]},sort_keys=True),flush=True)
    completed=[r for r in report["trials"] if r["status"]=="SOLVED"]
    same=(len(completed)==REPS and len({r["LP_calls"] for r in completed})==1
      and len({tuple(sorted(tuple(v) for v in r["solutions"]))
               for r in completed})==1)
    report["complete"]=same
    report["actual_LP"]=(completed[0]["LP_calls"] if same else None)
    report["time_median_s"]=(round(statistics.median(r["wall_s"]
                    for r in completed),6) if same else None)
    report["found_minimal"]=(len(completed[0]["solutions"]) if same else None)
    put(out/"summary.json",report)
    print("R17_COHORT_FINAL",json.dumps({"family":family,"N":n,
       "complete":same,"actual_LP":report["actual_LP"],
       "time_s":report["time_median_s"],
       "found":report["found_minimal"],
       "prediction_primary_LP":
           prediction["predicted_LP_calls"]["N_plus_graph_ridge"]},
           sort_keys=True),flush=True)

def errors(cases,model):
    rr=[c for c in cases if c["complete"]]
    if not rr:return {"n":0,"MAPE":None,"median_APE":None,
                        "MAE_LP":None,"mean_ratio_pred_true":None}
    a=np.array([c["actual_LP"] for c in rr],float)
    p=np.array([c["predictions_frozen_before_solver"]["predicted_LP_calls"][model]
                for c in rr],float)
    percentage=abs(p-a)/a
    return {"n":len(rr),"MAPE":round(float(percentage.mean()),6),
            "median_APE":round(float(np.median(percentage)),6),
            "MAE_LP":round(float(abs(p-a).mean()),5),
            "mean_ratio_pred_true":round(float(np.mean(p/a)),5)}

def audit(files,freeze_dir,out):
    need(len(files)==10,"ten prospective cases required")
    p=get(pathlib.Path(freeze_dir)/"preregistered.json")
    rows=[get(f) for f in files]
    expected=[(fam,n) for fam in FAMILIES for n in SIZES]
    need([(r["family"],r["N"]) for r in rows]==expected,
         "missing or misordered prospective controls")
    digest=sha(pathlib.Path(freeze_dir)/"preregistered.json")
    for r in rows:
        need(r["protocol"]==PROTO and r["source_model_SHA256"]==SOURCE_SHA and
             r["prediction_freeze_SHA256"]==digest and len(r["trials"])==REPS,
             "source or repeated trial drift")
        prediction=next(x for x in p["predictions"] if
                        x["family"]==r["family"] and x["N"]==r["N"])
        need(r["predictions_frozen_before_solver"]==prediction,
             "prediction changed after seeing answers")
        need({a["rep"] for a in r["trials"]}==set(range(REPS)),
             "trial repetitions missing")
        for x in r["trials"]:
            if x["status"]=="SOLVED":
                need(x["source_model_SHA256"]==SOURCE_SHA and
                     x["precommit_sha256"]==digest and
                     x["independent_validation"]["sound_minimal"] and
                     x["stage_unsat_certifications"]==3 and
                     x["wall_s"]<=CAP and x["LP_calls"]>0,
                     "unverified solver trial")
        if r["complete"]:
            need(r["actual_LP"]>0 and all(x["status"]=="SOLVED"
                  and x["LP_calls"]==r["actual_LP"] for x in r["trials"]),
                  "completion claim invalid")
        else:need(r["actual_LP"] is None,"incomplete given LP estimate")
    models=("N_only_power","graph_only_power","N_plus_graph_ridge")
    score={mode:errors(rows,mode) for mode in models}
    family_scores={fam:{mode:errors([r for r in rows if
             r["family"]==fam],mode) for mode in models} for fam in FAMILIES}
    summary={"protocol":PROTO,"status":"PASS_FROZEN_PROSPECTIVE_AUDIT",
      "source_model_SHA256":SOURCE_SHA,"prereg_sha256":digest,
      "training_gitHub_R9_run":R9_RUN,
      "family_definitions":"two disjoint gene sets selected without phenotypes or solver runtime",
      "pre_solve_features_use_LP_calls":0,
      "prospective_cases":len(rows),
      "completed":sum(r["complete"] for r in rows),
      "timeouts":sum(sum(x["status"]=="TIMEOUT" for x in r["trials"])
          for r in rows),
      "models":score,"families":family_scores,
      "primary":"N_plus_graph_ridge",
      "control":"N_only_power",
      "primary_beats_control_on_completed_cases":(
          score["N_plus_graph_ridge"]["MAPE"]<
          score["N_only_power"]["MAPE"]
          if score["N_only_power"]["MAPE"] is not None else None),
      "cohorts":[{"family":r["family"],"N":r["N"],
         "complete":r["complete"],
         "pred_N":r["predictions_frozen_before_solver"][
                    "predicted_LP_calls"]["N_only_power"],
         "pred_graph":r["predictions_frozen_before_solver"][
                    "predicted_LP_calls"]["N_plus_graph_ridge"],
         "actual_LP":r["actual_LP"],
         "wall_s":r["time_median_s"],
         "solutions":r["found_minimal"]} for r in rows],
      "not_a_complexity_proof":True,
      "no_external_metabolic_model_holdout":True,
      "original_R9_methods_exact_unmodified":True,
      "failure_cases_not_scored":True}
    put(out,summary)
    print("R17_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    need(len(FAMILIES)==2 and len(SIZES)==5,"cohort plan mismatch")
    for n in SIZES:need(ncomb(n)=={
        24:2324,48:18472,96:147536,192:1179808,384:9437504}[n],
        "gene intervention counts")
    for n in SIZES:
        ff={"N":n,"graph_pressure_proxy":n*n*.5+1}
        models=fit_models([{"N":k,"LP_calls":round(k*.5+9),
            "wall_s":k*.15,"features":{"graph_pressure_proxy":k*k*.5+1}}
             for k in SIZES])
        q=predict(models,ff)
        need(all(v>0 for v in q["predicted_LP_calls"].values()),
             "invalid positive forecast")
    print("R17_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    q=argparse.ArgumentParser()
    q.add_argument("action",choices=("selftest","freeze","verify","test","internal","audit"))
    q.add_argument("--source",default="r17/source")
    q.add_argument("--original-r9",default="r17/r9-frozen")
    q.add_argument("--training-audit")
    q.add_argument("--freeze",default="r17/frozen")
    q.add_argument("--family",choices=FAMILIES)
    q.add_argument("--n",type=int,choices=SIZES)
    q.add_argument("--config")
    q.add_argument("--inputs",nargs="*")
    q.add_argument("--out",default="r17/outputs")
    a=q.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":
        need(bool(a.training_audit),"certified R9 audit required")
        freeze(a.source,a.original_r9,a.training_audit,a.freeze)
    elif a.action=="verify":
        p=check_freeze(a.source,a.freeze,a.original_r9)
        print("R17_VERIFY_PASS",sha(pathlib.Path(a.freeze)/"preregistered.json"),
              len(p["predictions"]),flush=True)
    elif a.action=="test":
        need(a.family and a.n,"family and n required")
        test(a.source,a.original_r9,a.freeze,a.family,a.n,a.out)
    elif a.action=="internal":
        need(bool(a.config),"internal config missing")
        internal(a.config,a.out)
    else:audit(a.inputs,a.freeze,a.out)

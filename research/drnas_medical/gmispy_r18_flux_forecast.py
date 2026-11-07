#!/usr/bin/env python3
"""DRNAS MEDICAL R18: PRE-SOLVE primal-flux-feature prediction on 9 unseen
gene cohorts of iML1515. Genuine preregistration before heldout runs.

Prior training: source-pinned certified R9 run 42239472392 (5 cohorts) and
R17 run 42344188975 + independent recovered audit 42344466528 (10 cohorts).
Prospective target genes: disjoint from all 1,152 prior genes. 192
SHA-ranked and 144 topology-ranked genes, nested within family.

Aim: Does measured WILDTYPE viable metabolic flux support, from ONE charged
pre-solve GLPK call, predict R9 LP workload more reliably than gene count or
source-only GPR topology? Models fitted on 15 PRIOR cases only, coefficients
and prospect predictions SHA frozen before testing. Symmetric log errors
are PRE-REGISTERED primary criterion; MAPE remains secondary diagnostic.

Source-only model: log LP on log N and source GPR graph pressure.
Flux model: log LP on log N, graph pressure and flux-sensitive GPR pressure,
with lambda 2.0 fixed ridge penalty, no tuning after outcomes.
Physical constraint: all LP predictions positive, though fractional
estimates are still models not literal calls. No therapeutic conclusions;
no proof of asymptotic complexity; one bacterial source network only.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, random, statistics
import subprocess, sys, time
import numpy as np

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r17_structural_forecast as r17

PROTOCOL="DRNAS-MEDICAL-R18-WILDTYPE-FLUX-PRESOLVE-v1"
SOURCE_SHA="9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
PRIOR_R17_SHA="f4af4391321af37d8faa26097b26182d97090a83252c21c14f8d63366ff946dd"
PRIOR_R9_RUN=42239472392
PRIOR_R17_RUN=42344188975
PRIOR_R17_AUDIT_RUN=42344466528
FAMILIES=("new_sha_192","new_degree_144")
SIZES={"new_sha_192":(24,48,96,144,192),
       "new_degree_144":(24,48,96,144)}
MAX_K=3
REPEATS=2
CAP=120.
LAM=2.0
PAIR_SAMPLE=96
SEED="DRNAS-MEDICAL-R18-PROSPECTIVE-NO-PHENOTYPE-20261107"
MODELS=("N_only","N_graph","N_graph_flux")

def need(x,msg):
    if not x:raise RuntimeError("R18_FAIL_CLOSED "+str(msg))
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n")
def sha(p):return r8.sha(p)
def sig(g):return r9.hgenes(g)
def ord_hash(x):return hashlib.sha256((SEED+":"+x).encode()).hexdigest()
def ncomb(n):return r9.ncomb(n)

def input_model(root):
    from cobra.io import read_sbml_model
    root=pathlib.Path(root)
    m=r8.verify(root)
    need(m["SBML_sha256"]==SOURCE_SHA,"iML1515 original SBML SHA changed")
    model=read_sbml_model(str(root/"iML1515.xml"))
    model.solver="glpk"
    need(r8.dims(model)==r8.EXPECTED_DIMS,"source model has wrong dimensions")
    return model,m

def wildtype_flux(model,source_manifest):
    """The ONE additional LP solve charged to predictor feature acquisition.
    The original r8.load_frozen would also call GLPK to check wildtype, so
    deliberately use direct SBML read and only one explicit optimize() here.
    """
    from cobra.util.array import create_stoichiometric_matrix
    start=time.perf_counter()
    sol=model.optimize()
    elapsed=time.perf_counter()-start
    need(sol.status=="optimal" and math.isfinite(float(sol.objective_value)),
         "failed to acquire wildtype flux vector")
    need(abs(float(sol.objective_value)-
             source_manifest["wildtype_biomass"])<=1e-6,
         "wildtype biomass drift")
    rxns=list(model.reactions)
    vec=np.array([float(sol.fluxes.get(r.id,0.0)) for r in rxns])
    need(np.isfinite(vec).all(),"nonfinite flux predictor")
    matrix=create_stoichiometric_matrix(model,array_type="lil")
    need(float(np.max(np.abs(matrix@vec)))<1e-6,
         "mass-balance certificate of wildtype LP invalid")
    for rxn,v in zip(rxns,vec):
        need(rxn.lower_bound-1e-6<=v<=rxn.upper_bound+1e-6,
             "wildtype LP source bounds failed: "+rxn.id)
    return sol.fluxes,{
        "wildtype_LP_calls_for_feature_acquisition":1,
        "wildtype_flux_solve_s":round(elapsed,7),
        "wildtype_flux_nonzero_reactions_eps1e-8":int(
            np.count_nonzero(np.abs(vec)>1e-8)),
        "wildtype_growth":float(sol.objective_value),
        "feature_flux_epsilon":1e-8,
        "source_SHA256":SOURCE_SHA,
        "single_shared_wildtype_flux_for_all_cohorts":True,
        "per_independent_cohort_wildtype_LP_cost":1}

def structural_flux_features(model,genes,rules,flux):
    """Pre-solve GPR interaction count applied ONLY to currently carrying
    wildtype reactions. No gene KO, no candidate LP or phenotype results.
    This feature is for prediction ONLY, never injected as learned clause.
    """
    base=r17.features(model,genes,rules)
    eligible_flux={rid for rid in rules
                   if abs(float(flux.get(rid,0.0)))>1e-8}
    local={}
    disabled={}
    byid={g.id:g for g in model.genes}
    for g in genes:
        local[g]={r.id for r in byid[g].reactions
                  if r.id in eligible_flux}
        hit=frozenset((g,))
        disabled[g]={rid for rid in local[g]
                     if not rules[rid][2](hit)}
    rng=random.Random(r17.h(SEED+":FLUX_PAIR:"+sig(genes)))
    count=min(PAIR_SAMPLE,len(genes)*(len(genes)-1)//2)
    pairs=set()
    while len(pairs)<count:
        a,b=rng.sample(range(len(genes)),2)
        pairs.add((min(a,b),max(a,b)))
    extra=0
    for a,b in sorted(pairs):
        ga,gb=genes[a],genes[b]
        kk=frozenset((ga,gb))
        dis={rid for rid in local[ga]|local[gb]
             if not rules[rid][2](kk)}
        known=disabled[ga]|disabled[gb]
        need(known.issubset(dis),"GPR knockout monotonicity failed")
        extra+=len(dis-known)
    width=sum(1 for g in genes if disabled[g])
    unique_disabled=len(set().union(*(disabled[g] for g in genes)))
    total_singles=sum(len(disabled[g]) for g in genes)
    synergy=extra/max(count,1)
    pressure=1.0+width+total_singles+unique_disabled+2*len(genes)*synergy
    output={
        "N":len(genes),
        "graph_pressure_proxy":base["graph_pressure_proxy"],
        "wildtype_carried_GPR_reaction_target_edges":sum(len(local[g]) for g in genes),
        "genes_can_disable_nonzero_wildtype_flux":width,
        "distinct_nonzero_flux_reactions_disabled_by_single_gene":unique_disabled,
        "total_single_gene_nonzero_flux_reaction_effects":total_singles,
        "sampled_pair_activated_flux_knockouts":extra,
        "pair_sample_count":count,
        "mean_pair_flux_synergy":round(synergy,8),
        "wildtype_flux_pressure_proxy":round(pressure,8),
        "physical_model_genes":len(model.genes),
        "candidate_KO_FBA_calls_for_feature_acquisition":0,
        "additional_wildtype_LP_calls_per_standalone_cohort":1,
        "full_graph_static_features":base,
    }
    need(pressure>=1 and math.isfinite(pressure),"invalid flux features")
    return output

def ridge_fit(train,keys,lam):
    X=np.array([[math.log(float(r["features"][k])) for k in keys]
                 for r in train],float)
    y=np.log(np.array([r["actual_LP"] for r in train],float))
    mean=X.mean(axis=0);scale=X.std(axis=0)
    need(bool(np.all(scale>1e-10)),"nonidentifiable predictor")
    Z=(X-mean)/scale
    A=np.column_stack([np.ones(len(y)),Z])
    reg=np.diag([0.0]+[lam]*len(keys))
    beta=np.linalg.solve(A.T@A+reg,A.T@y)
    return {"features":list(keys),
       "coefficients":[float(v) for v in beta],
       "means":[float(v) for v in mean],
       "stds":[float(v) for v in scale],
       "ridge_lambda":lam,
       "trained_cases":len(train)}

def model_predictions(models,feat):
    prediction={}
    for name in MODELS:
        coeff=models[name]
        z=[(math.log(float(feat[k]))-av)/dv
           for k,av,dv in zip(coeff["features"],coeff["means"],coeff["stds"])]
        pred=math.exp(coeff["coefficients"][0]+sum(a*b for a,b
             in zip(coeff["coefficients"][1:],z)))
        need(pred>0 and math.isfinite(pred),"nonfinite prediction")
        prediction[name]=round(pred,6)
    return prediction

def lock_before_solver(source,old_r17,r17_audit,r9_frozen,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    prior=load(pathlib.Path(old_r17)/"preregistered.json")
    audit=load(r17_audit)
    need(prior["protocol"]==r17.PROTO and
         sha(pathlib.Path(old_r17)/"preregistered.json")==PRIOR_R17_SHA,
         "old R17 predictions not original immutable training precommit")
    need(audit["status"]=="PASS_FROZEN_PROSPECTIVE_AUDIT" and
         audit["prereg_sha256"]==PRIOR_R17_SHA and
         audit["completed"]==10 and audit["prospective_cases"]==10 and
         audit["training_gitHub_R9_run"]==PRIOR_R9_RUN,
         "R17 certified outcomes missing or drifted")
    model,source_meta=input_model(source)
    r9meta=r9.check_manifest(source,r9_frozen)
    all_past=set(r9meta["cohorts"]["384"])
    for family in ("sha_disjoint","degree_disjoint"):
        all_past.update(prior["prospective_cohorts"][family]["384"])
    need(len(all_past)==1152,"not all original R9 and R17 genes disjoint")
    usable={g.id:g for g in model.genes
            if g.id.startswith("b") and len(g.id)==5
            and g.id[1:].isdigit() and g.reactions}
    remaining=set(usable)-all_past
    need(len(remaining)>=336,
         "insufficient unseen genes for disjoint 192+144 R18 test")
    first=sorted(remaining,key=lambda g:ord_hash("SHA:"+g))[:192]
    second=sorted(remaining-set(first),
         key=lambda g:(-len(usable[g].reactions),ord_hash("DEGREE:"+g)))[:144]
    need(len(first)==192 and len(second)==144 and
         not(set(first)&set(second)) and
         not((set(first)|set(second))&all_past),
         "test gene selection must be previously unused")
    families={
      "new_sha_192":{str(n):first[:n] for n in SIZES["new_sha_192"]},
      "new_degree_144":{str(n):second[:n] for n in SIZES["new_degree_144"]}}
    rules=r8.all_rules(model)
    flux,flux_charge=wildtype_flux(model,source_meta)
    training=[]
    for x in prior["training_only_R9"]:
        n=x["N"];g=r9meta["cohorts"][str(n)]
        need(sig(g)==x["genes_sha"],"R9 original genes mismatch")
        training.append({"source":"certified_R9","family":"original",
             "N":n,"actual_LP":int(x["LP_calls"]),
             "actual_solver_s":float(x["wall_s"]),
             "gene_sha":sig(g),"features":
               structural_flux_features(model,g,rules,flux)})
    known_prior={(x["family"],x["N"]):x for x in audit["cohorts"]}
    need(len(known_prior)==10,"R17 certified prior rows missing")
    for fam in ("sha_disjoint","degree_disjoint"):
        for n in (24,48,96,192,384):
            priorrow=known_prior[(fam,n)]
            need(priorrow["complete"] and priorrow["actual_LP"]>0,
                 "R17 incomplete original train outcome")
            genes=prior["prospective_cohorts"][fam][str(n)]
            training.append({"source":"certified_R17","family":fam,
                "N":n,"actual_LP":int(priorrow["actual_LP"]),
                "actual_solver_s":float(priorrow["wall_s"]),
                "gene_sha":sig(genes),"features":
                  structural_flux_features(model,genes,rules,flux)})
    need(len(training)==15,"training must be precisely 15 source-cert cases")
    models={
      "N_only":ridge_fit(training,["N"],LAM),
      "N_graph":ridge_fit(training,["N","graph_pressure_proxy"],LAM),
      "N_graph_flux":ridge_fit(training,
          ["N","graph_pressure_proxy","wildtype_flux_pressure_proxy"],LAM),
    }
    # In-sample residuals are a diagnostic only, not a metric for model choice.
    prospective=[]
    for fam in FAMILIES:
        for n in SIZES[fam]:
            genes=families[fam][str(n)]
            feat=structural_flux_features(model,genes,rules,flux)
            pred=model_predictions(models,feat)
            prospective.append({"family":fam,"N":n,"genes":genes,
                "gene_sha256":sig(genes),"features":feat,
                "forecast_LP":pred,
                "wildtype_feature_acquisition_s":flux_charge["wildtype_flux_solve_s"],
                "independent_cohort_LP_cost":1})
    dataset={"protocol":PROTOCOL,
      "source_SHA256":SOURCE_SHA,
      "source_dimensions":list(r8.EXPECTED_DIMS),
      "prior_R9_run":PRIOR_R9_RUN,"prior_R17_run":PRIOR_R17_RUN,
      "prior_R17_independent_audit_run":PRIOR_R17_AUDIT_RUN,
      "prior_R17_frozen_forecast_SHA256":PRIOR_R17_SHA,
      "original_R9_genes_total":384,"original_R17_genes_total":768,
      "prior_used_distinct_genes":len(all_past),
      "unseen_eligible_before_selection":len(remaining),
      "prospective_selected_genes":336,
      "model_biological_source":"BiGG iML1515 original source",
      "prior_train":training,"trained_models":models,
      "prospective_nested_families":families,
      "prospective_predictions":prospective,
      "features_WT_LP_charge":flux_charge,
      "fitness_scores_chosen_before_test":
          ["RMS_log_error","median_multiplicative_error","MAPE_secondary"],
      "PRIMARY_SCORE":"RMS_log_error_on_complete_cases",
      "PRIMARY_HYPOTHESIS":"N_graph_flux RMS_log < N_only RMS_log",
      "ridge_lambda_selected_a_priori":LAM,
      "total_train_cohorts":15,
      "total_prospective_cohorts":len(prospective),
      "max_gene_knockout_size":MAX_K,
      "prospective_repeats":REPEATS,
      "trial_wall_cap_s":CAP,
      "censor_incomplete_cases_without_imputing_LP":True,
      "no_human_cancer_data":True,"not_native_DRNAS":True,
      "do_not_claim_complexity_improvement":True,
      "prospective_solve_outcomes_seen":False}
    save(out/"precommitted.json",dataset)
    digest=sha(out/"precommitted.json")
    (out/"sha256.txt").write_text(digest+"  precommitted.json\n")
    print("R18_PRECOMMITTED",json.dumps({
       "SHA256":digest,
       "train":len(training),
       "prospective":len(prospective),
       "wildtype_LP_feature_seconds":flux_charge["wildtype_flux_solve_s"],
       "source_SHA256":SOURCE_SHA,
       "models":{x:models[x]["coefficients"] for x in MODELS},
       "predictions":[{"family":x["family"],"N":x["N"],
             "N_only":x["forecast_LP"]["N_only"],
             "N_graph":x["forecast_LP"]["N_graph"],
             "N_graph_flux":x["forecast_LP"]["N_graph_flux"]}
                for x in prospective]},sort_keys=True),flush=True)

def verify_lock(root,source):
    root=pathlib.Path(root)
    p=root/"precommitted.json"
    d=load(p)
    need(root.joinpath("sha256.txt").read_text().split()[0]==sha(p),
         "prospective predictions altered")
    need(d["protocol"]==PROTOCOL and d["source_SHA256"]==SOURCE_SHA
         and d["prior_R17_frozen_forecast_SHA256"]==PRIOR_R17_SHA,
         "pre-registration source drift")
    need(r8.verify(source)["SBML_sha256"]==SOURCE_SHA,"source model bytes drift")
    need(len(d["prior_train"])==15 and
         len(d["prospective_predictions"])==9 and
         d["prospective_solve_outcomes_seen"] is False,
         "invalid training/prospective split")
    for x in d["prospective_predictions"]:
        need(sig(x["genes"])==x["gene_sha256"] and
             len(x["genes"])==x["N"],"cohort gene hash invalid")
    return d

def solve_internal(cfg,out):
    c=load(cfg)
    need(c["protocol"]==PROTOCOL and c["rep"] in (0,1),
         "invalid trial protocol")
    prior=verify_lock(c["freeze"],c["source"])
    x=next(x for x in prior["prospective_predictions"]
         if x["family"]==c["family"] and x["N"]==c["N"])
    need(c["gene_sha"]==x["gene_sha256"],"heldout cohort SHA mismatch")
    model,meta=r8.load_frozen(c["source"])
    rules=r8.all_rules(model)
    result=r9.solve(model,x["genes"],rules,meta["wildtype_biomass"]*0.01,CAP)
    need(result["status"]=="SOLVED" and
         result["SAT_UNSAT_stages"]==3 and result["lp_calls"]>=1,
         "original R9 exact solve not complete")
    v=r9.verify_sets(model,x["genes"],rules,meta["wildtype_biomass"]*.01,
                     result["minimal_sets"])
    need(v["sound_minimal"],"independent biophysical FBA check failed")
    line={"protocol":PROTOCOL,"source_SHA256":SOURCE_SHA,
         "freeze_SHA256":sha(pathlib.Path(c["freeze"])/"precommitted.json"),
         "family":c["family"],"N":c["N"],"rep":c["rep"],
         "genes_SHA256":x["gene_sha256"],
         "status":"SOLVED","LP_calls":result["lp_calls"],
         "time_s":result["wall_s"],
         "flux_cuts":result["flux_cuts"],
         "solutions":result["minimal_sets"],
         "SAT_UNSAT_stages":result["SAT_UNSAT_stages"],
         "independent_FBA_verification":v,
         "r9_source_algo_unchanged":True}
    save(out,line)
    print("R18_TRIAL",json.dumps({"family":line["family"],"N":line["N"],
         "rep":line["rep"],"LP":line["LP_calls"],"time_s":line["time_s"],
         "minimal":len(line["solutions"])},sort_keys=True),flush=True)

def spawn(cfg,target):
    target=pathlib.Path(target);config=target.with_suffix(".config.json")
    save(config,cfg)
    t=time.perf_counter()
    try:
        p=subprocess.run([sys.executable,__file__,"internal",
            "--config",str(config),"--out",str(target)],
            capture_output=True,text=True,timeout=CAP+75)
        target.with_suffix(".stdout.txt").write_text(p.stdout[-12000:])
        target.with_suffix(".stderr.txt").write_text(p.stderr[-16000:])
        if p.returncode:
            return {"status":"ERROR","error":p.stderr[-1600:],
                    "outer_time_s":round(time.perf_counter()-t,5)}
        data=load(target)
        return data
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","outer_time_s":round(time.perf_counter()-t,5)}

def measure_one(source,freeze,family,n,out):
    need(family in FAMILIES and n in SIZES[family],
         "invalid prospective measurement requested")
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    frozen=verify_lock(freeze,source)
    x=next(x for x in frozen["prospective_predictions"]
           if x["family"]==family and x["N"]==n)
    report={"protocol":PROTOCOL,
       "freeze_sha256":sha(pathlib.Path(freeze)/"precommitted.json"),
       "source_SHA256":SOURCE_SHA,"family":family,"N":n,
       "gene_sha256":x["gene_sha256"],"prediction_frozen_before_test":x,
       "repeats":REPEATS,"max_k":3,"cap_s":CAP,"trials":[]}
    for rep in range(REPEATS):
        c={"protocol":PROTOCOL,"rep":rep,"family":family,"N":n,
           "freeze":str(pathlib.Path(freeze).resolve()),
           "source":str(pathlib.Path(source).resolve()),
           "gene_sha":x["gene_sha256"]}
        row=spawn(c,out/f"trial-{rep}.json")
        row["rep"]=rep
        report["trials"].append(row)
        save(out/"summary.json",report)
        print("R18_RESULT",json.dumps({"family":family,"N":n,
           "rep":rep,"status":row["status"],
           "LP":row.get("LP_calls"),"time_s":row.get("time_s"),
           "err":row.get("error","")[-150:]},sort_keys=True),flush=True)
    successful=[r for r in report["trials"] if r["status"]=="SOLVED"]
    complete=(len(successful)==REPEATS and
         successful[0]["LP_calls"]==successful[1]["LP_calls"] and
         {tuple(v) for v in successful[0]["solutions"]}==
         {tuple(v) for v in successful[1]["solutions"]})
    report["complete"]=complete
    report["actual_LP"]=successful[0]["LP_calls"] if complete else None
    report["time_median_s"]=round(statistics.median(r["time_s"]
                            for r in successful),6) if complete else None
    report["minimal_sets"]=len(successful[0]["solutions"]) if complete else None
    save(out/"summary.json",report)
    print("R18_COHORT_FINAL",json.dumps({"family":family,"N":n,
       "complete":complete,"actual_LP":report["actual_LP"],
       "time_s":report["time_median_s"],
       "minimal":report["minimal_sets"]},sort_keys=True),flush=True)

def metrics(rows,model):
    complete=[x for x in rows if x["complete"]]
    if not complete:return {"n":0,"RMS_log_error":None,
      "median_multiplicative_error":None,"MAPE":None}
    log=[math.log(x["prediction_frozen_before_test"]["forecast_LP"][model]/
                   x["actual_LP"]) for x in complete]
    med=statistics.median(abs(x) for x in log)
    mape=statistics.mean(abs(math.exp(v)-1) for v in log)
    return {"n":len(complete),
       "RMS_log_error":round(math.sqrt(statistics.mean(v*v for v in log)),6),
       "median_multiplicative_error":round(math.exp(med),6),
       "geometric_mean_multiplicative_error":round(math.exp(
                   statistics.mean(abs(v) for v in log)),6),
       "MAPE":round(mape,6),
       "MAE_LP":round(statistics.mean(abs(
          x["prediction_frozen_before_test"]["forecast_LP"][model]-
          x["actual_LP"]) for x in complete),5)}

def audit(freeze,files,out):
    frozen=load(pathlib.Path(freeze)/"precommitted.json")
    digest=sha(pathlib.Path(freeze)/"precommitted.json")
    need(digest==pathlib.Path(freeze,"sha256.txt").read_text().split()[0],
         "pre-commit SHA mismatch")
    expect=[(fam,n) for fam in FAMILIES for n in SIZES[fam]]
    need(len(files)==len(expect)==9,"9 prospective cases mandatory")
    rows=[load(p) for p in files]
    need([(r["family"],r["N"]) for r in rows]==expect,
         "missing preregistered heldout result")
    for row in rows:
        need(row["protocol"]==PROTOCOL and row["freeze_sha256"]==digest and
             row["source_SHA256"]==SOURCE_SHA and row["repeats"]==REPEATS,
             "audit source identity drift")
        pr=next(z for z in frozen["prospective_predictions"]
                 if z["family"]==row["family"] and z["N"]==row["N"])
        need(row["prediction_frozen_before_test"]==pr,
             "forecast changed after actual result")
        need(len(row["trials"])==2 and
             {z["rep"] for z in row["trials"]}=={0,1},
             "missing repeated trial")
        for r in row["trials"]:
            if r["status"]=="SOLVED":
                need(r["protocol"]==PROTOCOL and
                  r["source_SHA256"]==SOURCE_SHA and
                  r["freeze_SHA256"]==digest and
                  r["independent_FBA_verification"]["sound_minimal"] and
                  r["SAT_UNSAT_stages"]==3 and r["time_s"]<=CAP,
                  "invalid exact solution certificate")
        if row["complete"]:
            need(row["actual_LP"]>0 and
                 all(x["status"]=="SOLVED" and
                     x["LP_calls"]==row["actual_LP"] for x in row["trials"]),
                 "missing complete LP evidence")
        else:
            need(row["actual_LP"] is None and row["time_median_s"] is None,
                 "incomplete result must not claim speed")
    totals={k:metrics(rows,k) for k in MODELS}
    subset={fam:{k:metrics([r for r in rows if r["family"]==fam],k)
                 for k in MODELS} for fam in FAMILIES}
    n_metric=totals["N_only"]["RMS_log_error"]
    flux_metric=totals["N_graph_flux"]["RMS_log_error"]
    report={"protocol":PROTOCOL,"status":"PASS_FROZEN_PROSPECTIVE_AUDIT",
       "source_model_SHA256":SOURCE_SHA,"frozen_forecasts_SHA256":digest,
       "prior_R9_run":PRIOR_R9_RUN,"prior_R17_run":PRIOR_R17_RUN,
       "original_source_genes":1516,
       "original_training_cases":15,
       "new_disjoint_prospective_cases":len(rows),
       "completed":sum(r["complete"] for r in rows),
       "timeouts":sum(x["status"]=="TIMEOUT" for r in rows for x in r["trials"]),
       "failed_trials":sum(x["status"]=="ERROR" for r in rows for x in r["trials"]),
       "models":totals,"families":subset,
       "primary":"N_graph_flux","control":"N_only",
       "primary_hypothesis_confirmed":(flux_metric<n_metric
             if flux_metric is not None and n_metric is not None else None),
       "source_cost_for_flux":{"wildtype_lp_calls":1,
         "precommit_feature_seconds":
             frozen["features_WT_LP_charge"]["wildtype_flux_solve_s"],
         "this_cost_is_not_free":True},
       "outcomes":[{"family":r["family"],"N":r["N"],
         "complete":r["complete"],"actual_LP":r["actual_LP"],
         "pred_N":r["prediction_frozen_before_test"]["forecast_LP"]["N_only"],
         "pred_N_graph":r["prediction_frozen_before_test"]["forecast_LP"]["N_graph"],
         "pred_N_flux":r["prediction_frozen_before_test"]["forecast_LP"]["N_graph_flux"],
         "time_median_s":r["time_median_s"],
         "minimal_sets":r["minimal_sets"]} for r in rows],
       "no_external_organism_holdout":True,
       "no_cancer_data":True,"not_native_DRNAS":True,
       "no_asymptotic_complexity_proof":True,
       "no_posthoc_model_refitting":True,
       "incomplete_not_scored":True}
    save(out,report)
    print("R18_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    need(sum(len(SIZES[x]) for x in FAMILIES)==9,"9 cases preregistered")
    for n in (24,48,96,144,192):need(ncomb(n)>0,"bad combos")
    t=[]
    for n in (24,48,96,144,192):
        t.append({"actual_LP":n/2+1,"features":{
          "N":n,"graph_pressure_proxy":1+n*n,
          "wildtype_flux_pressure_proxy":1+n**1.5}})
    models={
      "N_only":ridge_fit(t,["N"],LAM),
      "N_graph":ridge_fit(t,["N","graph_pressure_proxy"],LAM),
      "N_graph_flux":ridge_fit(t,
           ["N","graph_pressure_proxy","wildtype_flux_pressure_proxy"],LAM),
    }
    p=model_predictions(models,t[0]["features"])
    need(len(p)==3 and all(v>0 for v in p.values()),"regression ill-defined")
    print("R18_SELFTEST_PASS",json.dumps(p,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","run","internal","audit"))
    p.add_argument("--source",default="r18/training/source")
    p.add_argument("--prior-r17",default="r18/training/frozen")
    p.add_argument("--prior-r17-audit")
    p.add_argument("--prior-r9",default="r18/training/r9-frozen")
    p.add_argument("--freeze",default="r18/frozen")
    p.add_argument("--family",choices=FAMILIES)
    p.add_argument("--n",type=int)
    p.add_argument("--config")
    p.add_argument("--inputs",nargs="*")
    p.add_argument("--out",default="r18/results")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":
        need(bool(a.prior_r17_audit),"certified R17 results required")
        lock_before_solver(a.source,a.prior_r17,a.prior_r17_audit,a.prior_r9,a.freeze)
    elif a.action=="verify":
        x=verify_lock(a.freeze,a.source)
        print("R18_VERIFY_PASS",sha(pathlib.Path(a.freeze)/"precommitted.json"),
              len(x["prospective_predictions"]),flush=True)
    elif a.action=="run":
        need(a.family and a.n is not None,"required cohort family/N")
        measure_one(a.source,a.freeze,a.family,a.n,a.out)
    elif a.action=="internal":
        need(bool(a.config),"required trial config")
        solve_internal(a.config,a.out)
    else:
        audit(a.freeze,a.inputs,a.out)

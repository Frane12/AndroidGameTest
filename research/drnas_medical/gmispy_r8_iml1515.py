#!/usr/bin/env python3
"""DRNAS Medical R8: genome-scale iML1515 model transfer, original gMCSpy vs
R7 GPR-exact primal flux-witness SAT. Separate certificate for exhaustive
24-gene control and limited 48-gene scale-up. This is NOT a cancer model,
not a native DRNAS SAT solver, and not proof of general solver superiority.

Model and genes are frozen BEFORE benchmarking, selected from biological
priors/topology only, without runtime or knockout-phenotype optimization.
The complete iML1515 SBML bytes are shared between all solvers with SHA256.
"""
from __future__ import annotations
import argparse, ast, collections, hashlib, itertools, json, math
import pathlib, random, re, statistics, subprocess, sys, time, warnings

ROOT=pathlib.Path("medical-results/r8")
PROTOCOL="DRNAS-MEDICAL-R8-IML1515-GPR-CEGAR-v1"
GMCSPY_SHA="4567a6d14bd2e5517e7a86b17aebefb0f285544c"
EXPECTED_DIMS=(2712,1877,1516)
MODEL_NAME="iML1515"
CAP=120.0
REPEATS=3
ARMS=("r8_flux_witness_sat","published_gMCSpy_staged_lazy")
SEED_GENES=("b2926","b1779","b2779","b1136","b0720","b2415",
            "b3919","b0767","b1852","b2029","b4025","b1818",
            "b2417","b1101","b3738","b3736")

def need(condition,why):
    if not condition:raise RuntimeError("R8_FAIL_CLOSED "+str(why))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def dims(model):
    return (len(model.reactions),len(model.metabolites),len(model.genes))

def select_genes(model):
    """Pre-registered model-transfer selection; NEVER use knockout phenotype
    or solver runtime. First 16 are R7 e_coli_core priors, rest by graph degree
    and SHA ranking of raw gene IDs. 24-gene group is subset of 48-gene group.
    """
    eligible={g.id:g for g in model.genes if re.fullmatch(r"b[0-9]{4}",g.id)
              and len(g.reactions)>0}
    need(set(SEED_GENES).issubset(eligible),"core-source genes absent from iML1515")
    need(len(eligible)>=100,"invalid iML1515 locus gene selection")
    genes=list(SEED_GENES);used=set(genes)
    ranked=sorted(eligible,key=lambda x:(-len(eligible[x].reactions),x))
    def take(candidates,n):
        for gene in candidates:
            if len(genes)>=n:break
            if gene not in used:used.add(gene);genes.append(gene)
        need(len(genes)>=n,"not enough distinct genes")
    take(ranked,20)
    sha_rank=sorted(eligible,key=lambda x:hashlib.sha256(
        ("DRNAS-R8-IML1515-NO-PHENOTYPE-SELECTION:"+x).encode()).hexdigest())
    take(sha_rank,24)
    first24=tuple(genes)
    take(ranked,40)
    take(sha_rank,48)
    return {24:list(first24),48:list(genes)}

def freeze(root):
    from cobra.io import load_model,write_sbml_model
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
    source=root/"iML1515.xml"
    model=load_model(MODEL_NAME)
    model.solver="glpk"
    need(dims(model)==EXPECTED_DIMS,f"BiGG model dimensional drift {dims(model)}")
    wild=float(model.slim_optimize(error_value=float("nan")))
    need(math.isfinite(wild) and wild>0.05,"unexpected wildtype biomass")
    groups=select_genes(model)
    write_sbml_model(model,str(source))
    manifest={"protocol":PROTOCOL,"model_id":MODEL_NAME,
       "model_source":"COBRApy 0.30.0 BiGG load_model(iML1515)",
       "SBML_sha256":sha(source),
       "reactions":dims(model)[0],"metabolites":dims(model)[1],"genes_total":dims(model)[2],
       "wildtype_biomass":wild,"biomass_fraction":0.01,
       "max_knockouts":3,"cohorts":groups,
       "selection":"16 fixed E. coli core prior genes, 4 topology, 4 SHA; expand with 16 topology + 8 SHA",
       "selection_without_new_model_KO_phenotype_or_solver_runtime":True,
       "gene_subset_SHA":{str(n):hashlib.sha256(
         "\n".join(group).encode()).hexdigest() for n,group in groups.items()},
       "source_not_patients":True,"no_cancer_data":True}
    save(root/"manifest.json",manifest)
    verify(root)
    print("DRNAS_MEDICAL_R8_FREEZE",json.dumps(manifest,sort_keys=True),flush=True)

def verify(root):
    root=pathlib.Path(root)
    p=root/"manifest.json"
    m=read(p)
    need(m["protocol"]==PROTOCOL and m["model_id"]==MODEL_NAME,
         "model protocol drift")
    need((m["reactions"],m["metabolites"],m["genes_total"])==EXPECTED_DIMS,
         "source dimensions drift")
    need(sha(root/"iML1515.xml")==m["SBML_sha256"],"model SBML SHA changed")
    need([int(k) for k in sorted(m["cohorts"],key=int)]==[24,48],
         "model selection cohorts drift")
    need(m["cohorts"]["24"]==m["cohorts"]["48"][:24],
         "cohorts not nested")
    for n in ("24","48"):
        genes=m["cohorts"][n]
        need(len(genes)==int(n) and len(set(genes))==int(n),
             "selected genes invalid")
        need(hashlib.sha256("\n".join(genes).encode()).hexdigest()==
             m["gene_subset_SHA"][n],"gene subset SHA changed")
    return m

def load_frozen(root):
    from cobra.io import read_sbml_model
    root=pathlib.Path(root)
    m=verify(root)
    model=read_sbml_model(str(root/"iML1515.xml"))
    model.solver="glpk"
    need(dims(model)==EXPECTED_DIMS,"parsed model dimensions drift")
    wild=float(model.slim_optimize(error_value=float("nan")))
    need(math.isfinite(wild) and abs(wild-m["wildtype_biomass"])<1e-6,
         "model medium, biomass objective or bounds changed")
    return model,m

def all_rules(model):
    # Build exactly the R7 reified GPR representation from all model genes.
    from gmispy_r3 import parse_rule
    available={g.id for g in model.genes}
    rules={}
    for rxn in model.reactions:
        gpr=rxn.gene_reaction_rule.strip()
        if not gpr:continue
        tree,fn=parse_rule(gpr,available)
        need(fn(frozenset()),"GPR inactive in model wild type: "+rxn.id)
        rules[rxn.id]=(gpr,tree,fn)
    need(len(rules)>1000,"expected thousands of genuine genome-scale GPRs")
    return rules

def growth(model,genes,indices,rules,route):
    from gmispy_r3 import disabled_reactions
    with model:
        if route=="gene":
            for i in indices:model.genes.get_by_id(genes[i]).knock_out()
        elif route=="reaction":
            affected=disabled_reactions(rules,(genes[i] for i in indices))
            for rid in affected:model.reactions.get_by_id(rid).knock_out()
        else:raise ValueError(route)
        val=float(model.slim_optimize(error_value=float("nan")))
        return val if math.isfinite(val) else 0.0

def exhaustive_24(model,genes,rules,threshold,out):
    """Independent gene KO vs GPR-derived reaction KO, all C(24,1..3)=2324."""
    need(len(genes)==24,"exhaustive source cohort must be 24")
    started=time.perf_counter()
    minima=[]
    combos=0
    counts=collections.Counter()
    for k in (1,2,3):
        for inds in itertools.combinations(range(24),k):
            gene_val=growth(model,genes,inds,rules,"gene")
            react_val=growth(model,genes,inds,rules,"reaction")
            need(abs(gene_val-react_val)<=1e-6,
                 "independent GPR-vs-gene FBA mismatch "+str(inds)+
                 " "+str((gene_val,react_val)))
            lethal=gene_val<threshold
            combos+=1
            counts["lethal" if lethal else "viable"]+=1
            if lethal and not any(set(prev).issubset(inds) for prev in minima):
                minima.append(inds)
        print("DRNAS_MEDICAL_R8_ORACLE_PROGRESS",json.dumps({
            "k":k,"checked":combos,"minimal":len(minima),
            "wall_s":round(time.perf_counter()-started,3)},sort_keys=True),flush=True)
    need(combos==2324,"exhaustive 24-gene combinatorial count drift")
    truth=sorted((sorted(genes[i] for i in inds) for inds in minima),
                 key=lambda x:(len(x),x))
    report={"cohort":24,"model":"iML1515","candidates":combos,
      "independent_gene_and_reaction_FBA":2*combos,
      "all_gene_level_KOs_1_to_3_checked":True,
      "minimal_sets":truth,
      "minimal_count":len(truth),
      "lethal_candidates":counts["lethal"],
      "viable_candidates":counts["viable"],
      "wall_s":round(time.perf_counter()-started,5)}
    save(out,report)
    print("DRNAS_MEDICAL_R8_ORACLE_PASS",json.dumps({
        "candidates":combos,"minimal":len(truth),
        "wall_s":report["wall_s"]},sort_keys=True),flush=True)
    return report

def flux_witness(model,genes,rules,threshold):
    import gmispy_r7_witness as r7
    import numpy as np
    from cobra.util.array import create_stoichiometric_matrix
    matrix=create_stoichiometric_matrix(model,array_type="csc")
    original=r7.lp_flux
    ordered=[r.id for r in model.reactions]
    tested=0;worst_balance=0.
    # Re-verify every viable primal flux before allowing a learned SAT witness.
    def audited_lp(m,names,indices):
        nonlocal tested,worst_balance
        value,flux=original(m,names,indices)
        if value>=threshold:
            vals=np.array([float(flux.get(k,0.)) for k in ordered])
            need(np.isfinite(vals).all(),"nonfinite LP fluxes")
            bal=float(np.max(np.abs(matrix@vals)))
            worst_balance=max(worst_balance,bal)
            need(bal<=1e-6,"stoichiometric primal mass-balance certificate failed")
            from gmispy_r3 import disabled_reactions
            inactive=disabled_reactions(rules,(names[i] for i in indices))
            need(all(abs(float(flux.get(r,0.)))<=1e-6 for r in inactive),
                 "viable flux violates genetic knockout reaction constraints")
            tested+=1
        return value,flux
    r7.lp_flux=audited_lp
    try:row=r7.witness_sat(model,genes,rules,threshold)
    finally:r7.lp_flux=original
    need(row["lp_calls"]>0 and row["complete"] and
         row["lp_calls"]==row["viable_lp"]+row["lethal_lp"],
         "R7 candidate accounting failed")
    row["method"]=ARMS[0]
    row["primal_flux_certificates_checked"]=tested
    row["worst_stoichiometry_residual"]=round(worst_balance,10)
    return row

def upstream(model,genes,cap):
    from gMCSpy import calculateGeneMCS
    t0=time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result=calculateGeneMCS(
          cobraModel=model,geneSubset=genes,maxKOLength=3,
          maxNumberGMCS=50000,solver="gurobi",timeLimit=cap,
          numWorkers=1,forceLength=False,earlyStop=True,
          removeRelated=False,checkSolutions=False,
          saveSolutions=False,verbose=0,enumeration="staged-lazy")
    elapsed=time.perf_counter()-t0
    need(isinstance(result,dict),"gMCSpy unexpected output type")
    sets=[]
    for item in result.values():
        need(isinstance(item,dict) and "solution" in item,
             "gMCSpy malformed returned solution")
        sets.append(sorted(str(x) for x in item["solution"]))
    return {"method":ARMS[1],"status":"returned","wall_s":round(elapsed,7),
            "solutions":sets,"warnings":[str(w.message) for w in caught],
            "upstream_commit":GMCSPY_SHA,"enumeration":"staged-lazy"}

def normalize(solutions,genes):
    seen=set();pool=set(genes)
    for line in solutions:
        item=frozenset(line)
        need(bool(item) and item.issubset(pool) and len(item)<=3,
             "not a valid intervention")
        need(item not in seen,"duplicate genetic minimal cuts")
        seen.add(item)
    return seen

def check_solution_soundness(model,genes,rules,threshold,sets):
    """Check EVERY reported intervention via independent gene- and reaction-KO
    FBA, and each deletion-of-one-gene subset to establish minimality.
    Does NOT by itself prove there aren't more solutions for the 48-gene cohort.
    """
    cache={}
    def test(ids,how):
        key=(frozenset(ids),how)
        if key not in cache:
            inds=tuple(sorted(genes.index(g) for g in ids))
            cache[key]=growth(model,genes,inds,rules,how)
        return cache[key]
    for item in sets:
        tested=(test(item,"gene"),test(item,"reaction"))
        need(abs(tested[0]-tested[1])<=1e-6 and tested[0]<threshold,
             "reported gene cut is not lethally valid in independent FBA")
        for g in item:
            smaller=item-{g}
            a=test(smaller,"gene")
            b=test(smaller,"reaction")
            need(abs(a-b)<=1e-6 and a>=threshold,
                 "reported cut not inclusion minimal by independent FBA")
    return {"unique_KO_checks":len({k[0] for k in cache}),
            "independent_FBA_calls":len(cache),
            "sound_and_inclusion_minimal":True}

def trial_internal(config,target):
    cfg=read(config)
    need(cfg["protocol"]==PROTOCOL and cfg["cohort"] in (24,48)
         and cfg["mode"] in ARMS,"bad run configuration")
    model,m=load_frozen(cfg["freeze"])
    genes=m["cohorts"][str(cfg["cohort"])]
    need(cfg["genes"]==genes and cfg["SBML_sha256"]==m["SBML_sha256"],
         "arm source model / gene SHA changed")
    rules=all_rules(model)
    threshold=m["wildtype_biomass"]*.01
    row=(flux_witness(model,genes,rules,threshold)
         if cfg["mode"]==ARMS[0] else upstream(model,genes,cfg["cap"]))
    found=normalize(row["solutions"],genes)
    # The independent validation on completed outcomes is charged separately
    # to avoid making two precomputed source models affect one arm differently.
    verification=check_solution_soundness(model,genes,rules,threshold,found)
    row.update({"source_model_sha256":m["SBML_sha256"],
                "protocol":PROTOCOL,"cohort":cfg["cohort"],
                "gene_subset_sha256":m["gene_subset_SHA"][str(cfg["cohort"])],
                "numerically_independent_validation":verification,
                "repeat":cfg["repeat"],
                "status":row.get("status","returned")})
    save(target,row)
    print("DRNAS_MEDICAL_R8_INTERNAL",json.dumps({
        "cohort":cfg["cohort"],"arm":cfg["mode"],
        "wall_s":row["wall_s"],"solutions":len(row["solutions"]),
        "LP_calls":row.get("lp_calls"),"flux_cuts":row.get("flux_cuts"),
        "validation":verification},sort_keys=True),flush=True)

def spawn(cfg,target):
    target=pathlib.Path(target)
    config=target.with_suffix(".config.json")
    save(config,cfg)
    start=time.perf_counter()
    try:
        p=subprocess.run([sys.executable,__file__,"internal",
             "--config",str(config),"--out",str(target)],
             capture_output=True,text=True,timeout=cfg["cap"]+90)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","outer_wall_s":round(time.perf_counter()-start,7)}
    total=time.perf_counter()-start
    target.with_suffix(".stdout.txt").write_text(p.stdout[-16000:])
    target.with_suffix(".stderr.txt").write_text(p.stderr[-16000:])
    if p.returncode:
        return {"status":"ERROR","error":p.stderr[-1500:],
                "exit_code":p.returncode,"outer_wall_s":round(total,7)}
    obj=read(target);obj["outer_wall_s"]=round(total,7)
    if obj["wall_s"]>cfg["cap"]:obj["status"]="TIMEOUT"
    return obj

def benchmark(frozen,cohort,out,reps,cap,with_exhaustive):
    need(cohort in (24,48) and reps==REPEATS and cap==CAP,
         "benchmark frozen protocol drift")
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    model,m=load_frozen(frozen)
    genes=m["cohorts"][str(cohort)]
    rules=all_rules(model)
    threshold=m["wildtype_biomass"]*.01
    truth=None
    if with_exhaustive:
        need(cohort==24,"full exhaustive reference only frozen for 24 gene cohort")
        truth=exhaustive_24(model,genes,rules,threshold,out/"exhaustive.json")
    else:need(cohort==48,"48-gene scaling cohort")
    expected=set(map(frozenset,truth["minimal_sets"])) if truth else None
    result={"protocol":PROTOCOL,"cohort":cohort,
        "source_model_sha256":m["SBML_sha256"],
        "gene_subset_sha256":m["gene_subset_SHA"][str(cohort)],
        "genes":genes,"target_genes":cohort,"max_k":3,
        "possible_gene_KO_sets":sum(math.comb(cohort,k) for k in (1,2,3)),
        "biomass_threshold":threshold,"wildtype":m["wildtype_biomass"],
        "reference_exhaustive":truth,
        "all_complete":False,
        "independent_full_reference_only_24_genes":True,
        "repetitions":REPEATS,"time_cap_s":CAP,"trials":[]}
    for rep in range(reps):
        order=list(ARMS)
        random.Random(PROTOCOL+str(cohort)+"/"+str(rep)).shuffle(order)
        for mode in order:
            cfg={"protocol":PROTOCOL,"cohort":cohort,"mode":mode,"repeat":rep,
                 "freeze":str(pathlib.Path(frozen).resolve()),
                 "genes":genes,"cap":cap,
                 "SBML_sha256":m["SBML_sha256"]}
            row=spawn(cfg,out/f"trial-{rep}-{mode}.json")
            row["method"]=mode;row["repeat"]=rep
            if row["status"]=="returned":
                try:
                    found=normalize(row["solutions"],genes)
                    warnings_list=row.get("warnings",[])
                    timed_out=any("time limit" in x.lower() or
                         "lower bound" in x.lower() or "incomplete" in x.lower()
                         for x in warnings_list)
                    row["complete"]=not timed_out
                    if expected is not None:
                        row["correct_and_complete"]=(
                            row["complete"] and found==expected)
                        row["missing_from_full_reference"]=[
                           sorted(x) for x in expected-found]
                        row["extra_vs_full_reference"]=[
                           sorted(x) for x in found-expected]
                    else:
                        row["correct_and_complete"]=row["complete"] and row[
                          "numerically_independent_validation"]["sound_and_inclusion_minimal"]
                except Exception as e:
                    row["complete"]=False;row["correct_and_complete"]=False
                    row["validation_error"]=str(e)
            else:
                row["complete"]=False;row["correct_and_complete"]=False
            result["trials"].append(row)
            save(out/"summary.json",result)
            print("DRNAS_MEDICAL_R8_TRIAL",json.dumps({
                "cohort":cohort,"rep":rep,"method":mode,
                "status":row["status"],"seconds":row.get("wall_s"),
                "LP_calls":row.get("lp_calls"),"flux_cuts":row.get("flux_cuts"),
                "solutions":len(row.get("solutions",[])),
                "complete":row["complete"],
                "correct":row["correct_and_complete"],
                "error":row.get("error","")[:220]},sort_keys=True),flush=True)
    by={name:[r for r in result["trials"] if r["method"]==name] for name in ARMS}
    eligible=all(len(a)==REPEATS and
                 all(r["status"]=="returned" and r["correct_and_complete"]
                     for r in a) for a in by.values())
    if eligible:
        f={frozenset(x) for x in by[ARMS[0]][0]["solutions"]}
        g={frozenset(x) for x in by[ARMS[1]][0]["solutions"]}
        same=all({frozenset(x) for x in r["solutions"]}==f
                  for r in by[ARMS[0]]) and all(
                 {frozenset(x) for x in r["solutions"]}==g
                 for r in by[ARMS[1]])
        eligible=same and f==g and (expected is None or f==expected)
    medians={name:statistics.median(r["wall_s"] for r in aa)
             if eligible else None for name,aa in by.items()}
    result["complete_both_arms"]=eligible
    result["median_wall_s"]=medians
    result["speedup_vs_published_gMCSpy"]=(
      round(medians[ARMS[1]]/medians[ARMS[0]],6) if eligible else None)
    result["all_complete"]=eligible
    result["performance_claim_allowed"]=eligible and bool(
        by[ARMS[0]][0].get("solutions"))
    save(out/"summary.json",result)
    print("DRNAS_MEDICAL_R8_SUMMARY",json.dumps({
      "cohort":cohort,"status":"BOTH_COMPLETE" if eligible else "INCOMPLETE",
      "medians":medians,
      "speedup":result["speedup_vs_published_gMCSpy"],
      "solutions":len(by[ARMS[0]][0].get("solutions",[])),
      "reference":"full_genetic_and_reaction_FBA" if truth else
          "per_solution_two_FBA_and_solver_agreement_only"},sort_keys=True),flush=True)

def audit(p24,p48,out):
    s24=read(p24);s48=read(p48)
    need(s24["cohort"]==24 and s48["cohort"]==48 and
         s24["source_model_sha256"]==s48["source_model_sha256"],
         "cross-shard source model identity mismatch")
    for s in (s24,s48):
        need(s["protocol"]==PROTOCOL and s["max_k"]==3 and
             len(s["trials"])==6,"incomplete frozen experiment manifest")
        for arm in ARMS:
            a=[r for r in s["trials"] if r["method"]==arm]
            need(len(a)==REPEATS and {r["repeat"] for r in a}=={0,1,2},
                 "repeat mismatch")
            for t in a:
                if t["status"]=="returned":
                    need(t["source_model_sha256"]==s["source_model_sha256"] and
                         t["gene_subset_sha256"]==s["gene_subset_sha256"],
                         "source model/genes changed across arms")
                    if t["correct_and_complete"]:
                        need(t["numerically_independent_validation"][
                            "sound_and_inclusion_minimal"],"missing independent validation")
        if s["cohort"]==24:
            oracle=s["reference_exhaustive"]
            need(oracle and oracle["all_gene_level_KOs_1_to_3_checked"] and
                 oracle["candidates"]==2324 and
                 oracle["independent_gene_and_reaction_FBA"]==4648,
                 "full source-independent 24-gene reference missing")
    result={"status":"PASS_R8_SOURCE_AND_COMPLETION_AUDIT",
      "protocol":PROTOCOL,"model_sha256":s24["source_model_sha256"],
      "model":"iML1515","dimensions":EXPECTED_DIMS,
      "cohorts":[{"n":x["cohort"],"complete":x["complete_both_arms"],
         "solutions":len(x["trials"][0].get("solutions",[])),
         "median_s":x["median_wall_s"],
         "performance_claim_allowed":x["performance_claim_allowed"],
         "speedup":x["speedup_vs_published_gMCSpy"],
         "full_exhaustive":x["reference_exhaustive"] is not None}
         for x in (s24,s48)],
      "native_drnas":False,
      "human_cancer_model":False,
      "scope":"one newly transferred E coli genome scale network; nested cohorts",
      "incomplete_arms_not_speedup_claims":True}
    save(out,result)
    print("DRNAS_MEDICAL_R8_AUDIT",json.dumps(result,sort_keys=True),flush=True)

def selftest():
    need(len(SEED_GENES)==len(set(SEED_GENES))==16,"core prior drift")
    need(sum(math.comb(24,k) for k in (1,2,3))==2324,
         "combinatorial oracle count")
    need(sum(math.comb(48,k) for k in (1,2,3))==18472,
         "scaled cohort count")
    from gmispy_r7_audit import unit_test
    u=unit_test()
    need(u["GPR_truth_table"]=="PASS","R7 GPR logic tests failed")
    print("DRNAS_MEDICAL_R8_SELFTEST_PASS",json.dumps(u,sort_keys=True),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","freeze","verify","benchmark","internal","audit"))
    a.add_argument("--freeze",default="medical-results/r8-frozen")
    a.add_argument("--cohort",type=int,choices=(24,48),default=24)
    a.add_argument("--reference-exhaustive",action="store_true")
    a.add_argument("--out",default="medical-results/r8")
    a.add_argument("--config")
    a.add_argument("--cohort24")
    a.add_argument("--cohort48")
    a.add_argument("--repeats",type=int,default=REPEATS)
    a.add_argument("--cap",type=float,default=CAP)
    z=a.parse_args()
    if z.action=="selftest":selftest()
    elif z.action=="freeze":freeze(z.freeze)
    elif z.action=="verify":
        m=verify(z.freeze);print("DRNAS_MEDICAL_R8_VERIFY_PASS",
           m["SBML_sha256"],m["cohorts"],flush=True)
    elif z.action=="benchmark":
        benchmark(z.freeze,z.cohort,z.out,z.repeats,z.cap,z.reference_exhaustive)
    elif z.action=="internal":
        need(bool(z.config),"trial config required")
        trial_internal(z.config,z.out)
    else:
        need(z.cohort24 and z.cohort48,"both cohort summary paths required")
        audit(z.cohort24,z.cohort48,z.out)

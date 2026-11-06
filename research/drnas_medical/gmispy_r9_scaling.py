#!/usr/bin/env python3
"""DRNAS Medical R9: controlled scaling of GPR-exact SAT + primal flux cuts
on SHA-pinned published iML1515: 24, 48, 96, 192, 384 target genes;
knockout cardinality k <= 3, 3 repeats, 120 s cap each.

24 and 48: independently exhaustive gene KO + GPR-derived reaction KO FBA
of all C(n,1)+C(n,2)+C(n,3) combos.
96/192/384: every found intervention and one-gene deletions independently
validated, plus SAT termination with sound reified-GPR and flux constraints.
This cannot replace an independent exhaustive completeness certificate for
large cohorts. Incomplete/timeouts NEVER included in speed or scaling claims.

Fixed first 48 R8 genes; new ones ranked solely by SHA of gene IDs.
iML1515 SBML SHA256 pinned, no new phenotype-based selection.
PySAT CaDiCaL + GLPK, not native DRNAS and not a cancer model.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, pathlib, random
import statistics, subprocess, sys, time

import gmispy_r8_iml1515 as r8
import gmispy_r7_witness as r7

PROTO="DRNAS-MEDICAL-R9-SCALING-IML1515-K3-20261106-v1"
SOURCE_SHA="9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
SIZE=(24,48,96,192,384)
CAP=120.0
REPS=3
MAX_K=3
SELECT_SEED="DRNAS_MEDICAL_R9_IML1515_SHA_ORDER_NOT_PHENOTYPE_v1"

def need(ok,why):
    if not ok:raise RuntimeError("R9_FAIL_CLOSED "+str(why))
def save(path,x):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def load(path):return json.loads(pathlib.Path(path).read_text())
def hashfile(path):return r8.sha(path)
def hgenes(g):
    return hashlib.sha256("\n".join(g).encode()).hexdigest()
def ncomb(n):return sum(math.comb(n,k) for k in (1,2,3))

def freeze(source,dest):
    source=pathlib.Path(source);dest=pathlib.Path(dest)
    m=r8.verify(source)
    need(m["SBML_sha256"]==SOURCE_SHA,"source SHA not pinned R8 iML1515")
    model,actual=r8.load_frozen(source)
    eligible=sorted(g.id for g in model.genes
           if g.id.startswith("b") and len(g.id)==5 and g.id[1:].isdigit()
           and g.reactions)
    original=m["cohorts"]["48"]
    need(len(original)==48 and len(set(original))==48
         and set(original).issubset(eligible),"R8 original 48 genes drift")
    others=sorted(set(eligible)-set(original),
        key=lambda g:hashlib.sha256((SELECT_SEED+":"+g).encode()).hexdigest())
    selected=original+others[:384-48]
    need(len(selected)==384 and len(set(selected))==384,"not enough genes")
    cohorts={str(n):selected[:n] for n in SIZE}
    need(cohorts["24"]==m["cohorts"]["24"],"R8 nested 24 changed")
    manifest={"protocol":PROTO,"model_id":"iML1515",
       "source_model_SHA256":SOURCE_SHA,"source_manifest_SHA256":hashfile(source/"manifest.json"),
       "source_bytes_SHA256":hashfile(source/"iML1515.xml"),
       "sizes":SIZE,"max_k":MAX_K,"wall_cap_per_trial_s":CAP,"repetitions":REPS,
       "gene_selection":"48 R8 frozen genes + 336 SHA-ranked new locus genes, no phenotype",
       "gene_selection_seed":SELECT_SEED,"cohorts":cohorts,
       "gene_cohort_SHA256":{str(n):hgenes(cohorts[str(n)]) for n in SIZE},
       "possible_interventions":{str(n):ncomb(n) for n in SIZE},
       "exhaustive_FBA_cohorts":[24,48],
       "full_exhaustive_larger_cohorts":False,
       "native_drnas":False,"human_cancer_model":False}
    dest.mkdir(parents=True,exist_ok=True)
    save(dest/"r9-manifest.json",manifest)
    check_manifest(source,dest)
    print("R9_FREEZE",json.dumps({k:manifest[k] for k in
         ("source_model_SHA256","gene_cohort_SHA256","possible_interventions","sizes")},
         sort_keys=True),flush=True)

def check_manifest(source,metadata):
    m=load(pathlib.Path(metadata)/"r9-manifest.json")
    p=r8.verify(source)
    need(p["SBML_sha256"]==SOURCE_SHA and
         hashfile(pathlib.Path(source)/"iML1515.xml")==SOURCE_SHA,
         "R9 model content drift")
    need(m["protocol"]==PROTO and m["source_model_SHA256"]==SOURCE_SHA and
         m["max_k"]==3 and m["repetitions"]==3 and m["wall_cap_per_trial_s"]==CAP,
         "R9 frozen configuration drift")
    need(m["sizes"]==list(SIZE) and
         m["cohorts"]["48"]==p["cohorts"]["48"] and
         m["cohorts"]["24"]==p["cohorts"]["24"],"prior cohorts drift")
    for n in SIZE:
        g=m["cohorts"][str(n)]
        need(len(g)==n and len(set(g))==n and
             m["gene_cohort_SHA256"][str(n)]==hgenes(g) and
             m["possible_interventions"][str(n)]==ncomb(n),
             "cohort SHA / combination count drift")
        if n!=SIZE[0]:
            prev=SIZE[SIZE.index(n)-1]
            need(g[:prev]==m["cohorts"][str(prev)],"not nested cohorts")
    return m

def growth(model,genes,combo,rules,how):
    return r8.growth(model,genes,combo,rules,how)

def independent_oracle(model,genes,rules,target,path):
    n=len(genes)
    need(n in (24,48),"only frozen smaller cohorts exhaustive")
    started=time.perf_counter()
    minima=[]
    checked=0
    if target<=0:raise RuntimeError("wildtype target invalid")
    for k in (1,2,3):
        for combo in itertools.combinations(range(n),k):
            val=growth(model,genes,combo,rules,"gene")
            val2=growth(model,genes,combo,rules,"reaction")
            need(abs(val-val2)<=1e-6,"two FBA paths disagree "+str(combo))
            if val<target and not any(set(old).issubset(combo) for old in minima):
                minima.append(combo)
            checked+=1
        print("R9_ORACLE_PROGRESS",json.dumps({"n":n,"k":k,
             "checked":checked,"minima":len(minima),
             "elapsed_s":round(time.perf_counter()-started,4)}),flush=True)
    need(checked==ncomb(n),"exhaustive count incorrect")
    result={"cohort":n,"source_SHA256":SOURCE_SHA,"candidates":checked,
        "two_independent_FBA_calls":2*checked,
        "minimal_interventions":sorted([sorted(genes[i] for i in c)
            for c in minima],key=lambda a:(len(a),a)),
        "elapsed_s":round(time.perf_counter()-started,5),
        "exhaustively_verified":True}
    save(path,result)
    print("R9_ORACLE_PASS",json.dumps({"n":n,"cases":checked,
         "minima":len(minima),"seconds":result["elapsed_s"]}),flush=True)
    return result

def certified_flux(model,genes,ko,rules,matrix,rxns,threshold):
    """Viable flux must obey S*v=0, gene KO, original bounds and positive
    biomass; no pruning of near-zero flux support is allowed."""
    import numpy as np
    with model:
        for ix in ko:model.genes.get_by_id(genes[ix]).knock_out()
        sol=model.optimize()
        if sol.status=="infeasible":return 0.0,{},False
        need(sol.status=="optimal" and math.isfinite(float(sol.objective_value)),
             "LP nonoptimal or failed")
        growth=float(sol.objective_value)
        flux=sol.fluxes
        vals=np.array([float(flux.get(r.id,0.0)) for r in rxns])
        need(np.isfinite(vals).all(),"invalid flux entries")
        if growth>=threshold:
            need(float(np.max(np.abs(matrix@vals)))<=1e-6,
                 "primal stoichiometric balance invalid")
            for r,val in zip(rxns,vals):
                need(r.lower_bound-1e-6<=val<=r.upper_bound+1e-6,
                     "primal flux violates model reaction bounds "+r.id)
            # Do not allow a gene KO to disable any nonzero-flux reaction.
            from gmispy_r3 import disabled_reactions
            disabled=disabled_reactions(rules,(genes[i] for i in ko))
            need(all(abs(float(flux.get(r,0)))<=1e-6 for r in disabled),
                 "witness uses disabled metabolic reaction")
            return growth,flux,True
        return growth,flux,False

def solve(model,genes,rules,threshold,cap):
    from pysat.card import CardEnc,EncType
    from pysat.solvers import Solver
    from cobra.util.array import create_stoichiometric_matrix
    start=time.perf_counter()
    deadline=start+cap
    logic=r7.GPRCNF(genes,rules)
    matrix=create_stoichiometric_matrix(model,array_type="lil")
    rxns=list(model.reactions)
    minima=set();learned=[];known=set()
    stats=collections.Counter()
    stages=[]
    def check():
        if time.perf_counter()>deadline:raise TimeoutError("R9 hard deadline in algorithm")
    def add_flux(flux,solver=None,ko=None):
        check()
        clause=logic.witness_clause(flux)
        # A flux returned by a floating-point LP solver can carry tiny
        # non-zero numerical residues on a nominally knocked-out reaction.
        # Such a flux cannot certify a GLOBAL witness cut in exact arithmetic.
        # Likewise an already-learned cut does not exclude the current KO.
        # The safe CEGAR fallback is to exclude ONLY this independently
        # LP-verified viable gene assignment, never its supersets.
        ambiguous=False
        if solver is not None:
            need(ko is not None,"candidate K required for a learned cut")
            from gmispy_r3 import disabled_reactions
            disabled=set(disabled_reactions(rules,(genes[i] for i in ko)))
            support={rid for rid in logic.disabled
                     if float(flux.get(rid,0.0))!=0.0}
            ambiguous=bool(disabled & support)
        if clause in known or ambiguous:
            need(solver is not None and ko is not None,
                 "wildtype witness unexpectedly duplicated")
            chosen=set(ko)
            exclusive=[-(i+1) if i in chosen else (i+1)
                       for i in range(len(genes))]
            solver.add_clause(exclusive)
            stats["candidate_only_safe_fallbacks"]+=1
            if ambiguous:stats["numerically_ambiguous_flux_support"]+=1
            if clause in known:stats["duplicate_flux_clause_suppressed"]+=1
            return
        known.add(clause)
        learned.append(list(clause))
        stats["flux_cuts"]+=1
        if solver is not None:solver.add_clause(list(clause))
    check()
    start_growth,flux,_=certified_flux(model,genes,(),rules,matrix,rxns,threshold)
    stats["lp_calls"]+=1
    stats["viable_lp"]+=1
    need(start_growth>=threshold,"original model growth below threshold")
    add_flux(flux)
    for k in (1,2,3):
        check()
        card=CardEnc.equals(lits=list(range(1,len(genes)+1)),bound=k,
            encoding=EncType.seqcounter,top_id=logic.top)
        with Solver(name="cadical195",
                    bootstrap_with=logic.clauses+card.clauses+learned) as sat:
            for old in minima:
                sat.add_clause([-(i+1) for i in old])
            while True:
                check()
                stats["sat_calls"]+=1
                if not sat.solve():
                    stats["unsat_termination_stages"]+=1
                    break
                positive=set(sat.get_model())
                ko=tuple(i for i in range(len(genes)) if i+1 in positive)
                need(len(ko)==k,"cardinality violation")
                check()
                val,flx,is_viable=certified_flux(
                    model,genes,ko,rules,matrix,rxns,threshold)
                stats["lp_calls"]+=1
                if is_viable:
                    stats["viable_lp"]+=1
                    add_flux(flx,sat,ko)
                else:
                    stats["lethal_lp"]+=1
                    need(not any(set(m).issubset(ko) for m in minima),
                         "nonminimal KO unexpectedly encountered")
                    minima.add(ko)
                    sat.add_clause([-(i+1) for i in ko])
        stages.append({"k":k,"solutions":sum(len(x)==k for x in minima),
             "lp_calls_total":stats["lp_calls"],"flux_cuts_total":stats["flux_cuts"],
             "wall_elapsed_s":round(time.perf_counter()-start,6)})
        print("R9_STAGE",json.dumps({"cohort":len(genes),**stages[-1]},
              sort_keys=True),flush=True)
    elapsed=time.perf_counter()-start
    if elapsed>cap:raise TimeoutError("R9 trial exceeded full solver wall cap")
    need(stats["unsat_termination_stages"]==3,
         "SAT solver did not exhaust all 3 cardinalities")
    need(stats["lp_calls"]==stats["viable_lp"]+stats["lethal_lp"],
         "LP accounting mismatch")
    result={"status":"SOLVED","wall_s":round(elapsed,6),
            "minimal_sets":sorted([sorted(genes[i] for i in x) for x in minima],
                                  key=lambda a:(len(a),a)),
            "SAT_UNSAT_stages":stats["unsat_termination_stages"],
            "GPR_cnf_clauses":len(logic.clauses),
            "reified_reactions":len(logic.disabled),
            "stages":stages,**dict(stats)}
    return result

def verify_sets(model,genes,rules,threshold,sols):
    pool=set(genes);seen=set()
    cache={}
    def check(combo,how):
        key=(tuple(sorted(combo)),how)
        if key not in cache:
            indexes=tuple(sorted(genes.index(g) for g in combo))
            cache[key]=growth(model,genes,indexes,rules,how)
        return cache[key]
    for sol in sols:
        ko=frozenset(sol)
        need(len(ko)==len(sol) and 1<=len(ko)<=3 and ko.issubset(pool),
             "invalid returned gene cut")
        need(ko not in seen,"duplicate returned gene cut")
        seen.add(ko)
        a,b=check(ko,"gene"),check(ko,"reaction")
        need(abs(a-b)<=1e-6 and a<threshold,"candidate not lethally valid")
        for gene in ko:
            sub=ko-{gene}
            a,b=check(sub,"gene"),check(sub,"reaction")
            need(abs(a-b)<=1e-6 and a>=threshold,"candidate not minimal")
    return {"sound_minimal":True,"independent_checks":len(cache),
            "FBA_calls":len(cache),
            "exhaustive_complete":False}

def trial_internal(config,output):
    cfg=load(config)
    n=cfg["n"]
    need(cfg["protocol"]==PROTO and n in SIZE and
         cfg["cap"]==CAP and cfg["rep"] in range(REPS),"trial protocol changed")
    m=check_manifest(cfg["source"],cfg["freeze"])
    genes=m["cohorts"][str(n)]
    need(hgenes(genes)==cfg["gene_sha"],"trial gene SHA mismatch")
    model,r8manifest=r8.load_frozen(cfg["source"])
    rules=r8.all_rules(model)
    threshold=float(r8manifest["wildtype_biomass"])*.01
    # Exact solver time does not include shared SBML load; includes GPR
    # encoding, all candidate LP, SAT calls, and learnt witness construction.
    result=solve(model,genes,rules,threshold,cfg["cap"])
    # The validator uses an independent gene-versus-reaction KO route; charge
    # validation separately and never hide it in solver wall-clock.
    t=time.perf_counter()
    v=verify_sets(model,genes,rules,threshold,result["minimal_sets"])
    result["validation_s"]=round(time.perf_counter()-t,6)
    result["independent_validation"]=v
    result.update({"protocol":PROTO,"n":n,"rep":cfg["rep"],
                   "source_SHA256":SOURCE_SHA,"gene_SHA256":cfg["gene_sha"]})
    save(output,result)
    print("R9_TRIAL",json.dumps({k:result[k] for k in
        ("n","rep","wall_s","lp_calls","flux_cuts","SAT_UNSAT_stages")}|{
        "minimal_count":len(result["minimal_sets"])},sort_keys=True),flush=True)

def spawn(config,target):
    cfg=pathlib.Path(target).with_suffix(".config.json")
    save(cfg,config)
    output=pathlib.Path(target)
    start=time.perf_counter()
    # Hard outer watchdog, including Python startup, frozen model reload
    # and independent validation. A 120-s solver cap is separately enforced.
    try:
        p=subprocess.run([sys.executable,__file__,"internal",
              "--config",str(cfg),"--out",str(output)],
              capture_output=True,text=True,timeout=CAP+45)
        total=time.perf_counter()-start
        output.with_suffix(".stdout.log").write_text(p.stdout[-25000:])
        output.with_suffix(".stderr.log").write_text(p.stderr[-25000:])
        if p.returncode:return {"status":"ERROR",
           "error":p.stderr[-3000:],"outer_wall_s":round(total,6)}
        data=load(output)
        data["outer_wall_s"]=round(total,6)
        if data["wall_s"]>CAP:return {"status":"TIMEOUT",
             "outer_wall_s":round(total,6),"invalid_elapsed_s":data["wall_s"]}
        return data
    except subprocess.TimeoutExpired:return {"status":"TIMEOUT",
        "reason":"outer hard watchdog cap+45 seconds","outer_wall_s":round(
           time.perf_counter()-start,6)}

def cohort_benchmark(source,freeze_path,n,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    m=check_manifest(source,freeze_path)
    genes=m["cohorts"][str(n)]
    model,r8m=r8.load_frozen(source)
    rules=r8.all_rules(model)
    threshold=r8m["wildtype_biomass"]*.01
    oracle=None
    if n in (24,48):
        oracle=independent_oracle(model,genes,rules,threshold,out/"oracle.json")
    record={"protocol":PROTO,"n":n,"repetitions":REPS,
        "cap_s":CAP,"max_k":MAX_K,
        "source_SHA256":SOURCE_SHA,"gene_SHA256":hgenes(genes),
        "possible_interventions":ncomb(n),
        "genes":genes,"oracle":oracle,"trials":[]}
    for rep in range(REPS):
        cfg={"protocol":PROTO,"source":str(pathlib.Path(source).resolve()),
            "freeze":str(pathlib.Path(freeze_path).resolve()),"n":n,
            "rep":rep,"cap":CAP,"gene_sha":hgenes(genes)}
        row=spawn(cfg,out/f"trial-{rep}.json")
        row["rep"]=rep
        if row["status"]=="SOLVED":
            actual={frozenset(x) for x in row["minimal_sets"]}
            row["correct"]=row["independent_validation"]["sound_minimal"]
            row["independent_exhaustive_match"]=(
                actual=={frozenset(x) for x in oracle["minimal_interventions"]}
                if oracle else None)
            if oracle:row["correct"] &= row["independent_exhaustive_match"]
        else:
            row["correct"]=False
            row["independent_exhaustive_match"]=False if oracle else None
        record["trials"].append(row)
        save(out/"summary.json",record)
        print("R9_RESULT",json.dumps({"n":n,"rep":rep,
            "status":row["status"],"seconds":row.get("wall_s"),
            "LP":row.get("lp_calls"),"flux_cuts":row.get("flux_cuts"),
            "found":len(row.get("minimal_sets",[])),"valid":row["correct"],
            "error":row.get("error","")[-200:]},sort_keys=True),flush=True)
    good=[r for r in record["trials"] if r["status"]=="SOLVED" and r["correct"]]
    complete=len(good)==REPS and len({
        tuple(sorted(tuple(sorted(x)) for x in r["minimal_sets"])) for r in good
        })==1
    record["complete"]=complete
    record["wall_median_s"]=(round(statistics.median(r["wall_s"] for r in good),6)
                             if complete else None)
    record["LP_median"]=(statistics.median(r["lp_calls"] for r in good)
                         if complete else None)
    record["witness_median"]=(statistics.median(r["flux_cuts"] for r in good)
                              if complete else None)
    record["solutions_count"]=(len(good[0]["minimal_sets"]) if complete else None)
    record["exhaustively_independent"]=(oracle is not None and complete)
    save(out/"summary.json",record)
    print("R9_COHORT_FINAL",json.dumps({k:record[k] for k in
        ("n","complete","possible_interventions","wall_median_s",
         "LP_median","witness_median","solutions_count",
         "exhaustively_independent")},sort_keys=True),flush=True)

def final_audit(inputs,out):
    need(len(inputs)==5,"five separate cohorts required")
    cases=[load(p) for p in inputs]
    need([c["n"] for c in cases]==list(SIZE),"case order drift")
    for c in cases:
        n=c["n"]
        need(c["protocol"]==PROTO and c["source_SHA256"]==SOURCE_SHA and
             c["max_k"]==3 and c["cap_s"]==CAP and
             c["possible_interventions"]==ncomb(n),"source/protocol drift")
        need(len(c["trials"])==REPS and {r["rep"] for r in c["trials"]}==
             {0,1,2},"three repeats missing")
        need(hgenes(c["genes"])==c["gene_SHA256"],"cohort genes drift")
        if n in (24,48):
            oracle=c["oracle"]
            need(oracle is not None and oracle["exhaustively_verified"] and
                 oracle["candidates"]==ncomb(n) and
                 oracle["two_independent_FBA_calls"]==2*ncomb(n),
                 "exhaustive oracle missing")
        else:need(c["oracle"] is None,"large unsupported exhaustive claim")
        for r in c["trials"]:
            if r["status"]=="SOLVED":
                need(r["protocol"]==PROTO and r["source_SHA256"]==SOURCE_SHA
                     and r["gene_SHA256"]==c["gene_SHA256"] and
                     r["SAT_UNSAT_stages"]==3 and
                     r["independent_validation"]["sound_minimal"] and
                     r["wall_s"]<=CAP,"invalid solved certificate")
                if n in (24,48):
                    need(r["independent_exhaustive_match"],
                         "incomplete independent solution set")
        if c["complete"]:
            need(all(r["status"]=="SOLVED" and r["correct"]
                     for r in c["trials"]) and
                 c["wall_median_s"] is not None,"complete flag unjustified")
        else:need(c["wall_median_s"] is None,"incomplete included in fit")
    complete=[c for c in cases if c["complete"]]
    # Fit log time = alpha * log n + intercept on completed cohorts only.
    fit=None
    if len(complete)>=3:
        xs=[math.log(c["n"]) for c in complete]
        ys=[math.log(c["wall_median_s"]) for c in complete]
        mx=statistics.mean(xs);my=statistics.mean(ys)
        den=sum((v-mx)**2 for v in xs)
        alpha=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den
        intercept=my-alpha*mx
        total=sum((y-my)**2 for y in ys)
        err=sum((y-(intercept+alpha*x))**2 for x,y in zip(xs,ys))
        fit={"model":"log(t)=alpha*log(n)+intercept",
             "alpha":round(alpha,5),"intercept":round(intercept,5),
             "R2":round(1-err/total,5) if total else None,
             "n_used":[c["n"] for c in complete],
             "NOT_general_complexity_proof":True}
    result={"protocol":PROTO,"source_model_sha256":SOURCE_SHA,
      "status":"PASS_COMPLETION_AUDIT",
      "sizes":list(SIZE),"cap_s":CAP,"repetitions":REPS,
      "cohorts":[{k:c[k] for k in ("n","possible_interventions","complete",
          "wall_median_s","LP_median","witness_median","solutions_count",
          "exhaustively_independent")} for c in cases],
      "scaling_fit":fit,
      "no_exponential_complexity_claim":True,
      "not_native_drnas":True,"no_cancer_model":True,
      "gMCSpy_comparison_not_attempted_R9_due_Gurobi_license":True,
      "cohorts_96_192_384_lack_independent_exhaustive_completeness":True}
    save(out,result)
    print("R9_FINAL",json.dumps(result,sort_keys=True),flush=True)

def selftest():
    expected={24:2324,48:18472,96:147536,192:1179808,384:9437504}
    for n,v in expected.items():
        need(ncomb(n)==v,f"C(n,1..3) count mismatch {n} {ncomb(n)} expected{v}")
    from gmispy_r7_audit import unit_test
    u=unit_test()
    need(u["GPR_truth_table"]=="PASS","GPR Tseitin check")
    print("R9_SELFTEST_PASS",json.dumps(expected,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","cohort","internal","audit"))
    p.add_argument("--source",default="r9/source")
    p.add_argument("--freeze",default="r9/frozen")
    p.add_argument("--n",type=int,default=24)
    p.add_argument("--out",default="r9/results")
    p.add_argument("--config")
    p.add_argument("--inputs",nargs="*")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze(a.source,a.freeze)
    elif a.action=="verify":
        m=check_manifest(a.source,a.freeze)
        print("R9_VERIFY_PASS",m["gene_cohort_SHA256"],flush=True)
    elif a.action=="cohort":
        need(a.n in SIZE,"invalid n")
        cohort_benchmark(a.source,a.freeze,a.n,a.out)
    elif a.action=="internal":
        need(bool(a.config),"missing internal subprocess config")
        trial_internal(a.config,a.out)
    else:final_audit(a.inputs,a.out)

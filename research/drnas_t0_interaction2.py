#!/usr/bin/env python3
"""T0-INTERACTION2: preregistered second-order Boolean interactions at first branch.

Experiment only. An original-CNF-only diagnostic is run AFTER two identical
X5 baseline/first-polarity-flipped executions and is not fed to the solver.
First-branch state identities are checked. Outcome and benchmark labels never
enter the direction score. Original SAT models and UNSAT DRAT are verified.
One logical CPU per solver. No changes to native main or frozen references.
"""
from __future__ import annotations
import collections, hashlib, io, json, os, random, tarfile, time, urllib.request
from pathlib import Path
import drnas_t0_frontier1 as F

ROOT=Path("t0_interaction2")
ROOT.mkdir(exist_ok=True)
FAMILIES=F.SETS
START=6
PER_FAMILY=8
NEIGHBORS=6

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def new_sources(family):
    url=F.BASE_URL+family+".tar.gz"
    with urllib.request.urlopen(url,timeout=60) as resp:
        raw=resp.read(32*1024*1024+1)
    assert len(raw)<32*1024*1024,("ARCHIVE_TOO_BIG",family)
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as archive:
        members=sorted(
            (m for m in archive.getmembers()
             if m.isfile() and m.name.lower().endswith(".cnf")),
            key=lambda m:F.sha((family+"|"+Path(m.name).name).encode()))
        assert len(members)>=START+PER_FAMILY
        rows=[]
        for member in members[START:START+PER_FAMILY]:
            original=archive.extractfile(member).read()
            n,clauses=F.parse(original)
            data=F.canonical(n,clauses)
            name=family+"_"+Path(member.name).name
            path=ROOT/name
            path.write_bytes(data)
            rows.append({"family":family,"name":name,"path":str(path),
                         "sha256":F.sha(data),"archive_sha256":F.sha(raw),
                         "member":member.name,"n":n,"clauses":len(clauses),
                         "label":("UNSAT" if family.startswith("uuf") else "SAT")})
    return rows

def choose_neighbors(n,clauses,first,root_values):
    # Same original-CNF co-occurrence-based candidates for both polarities.
    # No SAT labels, solver results, or solver learned clauses.
    v=abs(first)
    freq=collections.Counter()
    for clause in clauses:
        variables=set(abs(x) for x in clause)
        if v not in variables:continue
        for u in variables:
            if u!=v and u not in root_values:freq[u]+=1
    return [u for u,_ in sorted(freq.items(),key=lambda kv:(-kv[1],kv[0]))[:NEIGHBORS]]

def direction_score(n,clauses,lit,root_values,singles,neighbors):
    assigned=F.bcp(clauses,[lit])
    if assigned is None:
        # Failed literal is a certified consequence of unit propagation;
        # no heuristic ranking can override its logical status.
        return {"conflict":True}
    direct=max(0,len(assigned)-len(root_values)-1)
    total_synergy=0
    max_synergy=0
    failed_pairs=0
    examined=0
    for u in neighbors:
        for sign in (1,-1):
            b=singles[(u,sign)]
            if b is None:continue
            examined+=1
            joint=F.bcp(clauses,[lit,u*sign])
            if joint is None:
                failed_pairs+=1
                continue
            # Discrete mixed finite difference in forced assignment COUNT.
            # Not a theorem about differential equations or continuous curvature.
            kappa=len(joint)-len(assigned)-len(b)+len(root_values)
            if kappa>0:
                total_synergy+=kappa
                max_synergy=max(max_synergy,kappa)
    # Exactly the same fixed terms, weights and threshold on new CNFs;
    # cannot be modified based on held-out solver outcomes.
    avg_synergy=total_synergy/max(1,examined)
    avg_fail=failed_pairs/max(1,examined)
    # Primary pre-registered quality hypothesis: more local constraint
    # interaction and contradictory second-level choices is helpful.
    score=float(direct)+avg_synergy+2.0*avg_fail
    return {"conflict":False,"direct_forced":direct,
            "synergy_total":total_synergy,"synergy_max":max_synergy,
            "synergy_per_pair":avg_synergy,"failed_pairs":failed_pairs,
            "pairs_examined":examined,"score":score}

def signal(n,clauses,first):
    baseline=F.bcp(clauses,[])
    if baseline is None:return {"eligible":False,"reason":"root_conflict","recommendation":0}
    neighbors=choose_neighbors(n,clauses,first,baseline)
    if not neighbors:return {"eligible":False,"reason":"no_neighbor","recommendation":0}
    singles={(u,sign):F.bcp(clauses,[u*sign]) for u in neighbors for sign in (1,-1)}
    a=direction_score(n,clauses,first,baseline,singles,neighbors)
    b=direction_score(n,clauses,-first,baseline,singles,neighbors)
    if a["conflict"] or b["conflict"]:
        return {"eligible":False,"reason":"first_level_failed_literal",
                "recommendation":0,"base":a,"flip":b}
    delta=b["score"]-a["score"]
    pred=1 if delta>0.01 else -1 if delta< -0.01 else 0
    return {"eligible":True,"recommendation":pred,"delta_flip_minus_base":delta,
            "base":a,"flip":b,"neighbors":neighbors}

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    assert F.BIN.is_file() and F.DRAT.is_file()
    sources=[]
    for family in FAMILIES:sources.extend(new_sources(family))
    assert len(sources)==6*PER_FAMILY
    assert len({s["sha256"] for s in sources})==len(sources)
    manifest={
        "status":"FROZEN_BEFORE_SOLVER",
        "count":len(sources),"families":list(FAMILIES),
        "cohort_selection":"SHA-sorted archive entries 6..13, disjoint from T0-FRONTIER1 0..5",
        "source_kind":"retrospective_published_SATLIB_random_3SAT",
        "score":"direct_forced + mean_positive_mixed_BCP_difference + 2*failed_pairs_fraction",
        "direction":"higher_score_better","margin":0.01,"max_original_CNF_neighbors":NEIGHBORS,
        "no_fitted_threshold":True,"no_model_training":True,
        "one_cpu":True,"same_X5_first_variable_and_state":True,
        "source_proof_and_original_sat_verification":True,
        "not_realworld_blind_holdout":True,
        "references_unchanged":True,"source_rows":sources
    }
    manifest_path=ROOT/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    emit("T0_INTERACTION2_FROZEN",{"count":len(sources),"sha256":F.sha(manifest_path.read_bytes()),
         "families":list(FAMILIES),"disjoint_from_frontier1":True,
         "score_fixed_before_results":True})
    random.Random(141126).shuffle(sources)
    data=[]
    for src in sources:
        raw=Path(src["path"]).read_bytes()
        assert F.sha(raw)==src["sha256"]
        n,clauses=F.parse(raw)
        order=[False,True]
        random.Random(int(src["sha256"][:10],16)).shuffle(order)
        trials={}
        for flip in order:trials[flip]=F.native(src,flip,n,clauses)
        base,flip=trials[False],trials[True]
        assert base["verified"] and flip["verified"],("UNVERIFIED_RESULT",src["name"])
        assert base["reached_first_branch"] and flip["reached_first_branch"],(
            "NO_FIRST_BRANCH",src["name"])
        assert base["pre_state_digest"]==flip["pre_state_digest"],(
            "DIFFERENT_INITIAL_SNAPSHOT",src["name"])
        assert base["baseline_literal"]==flip["baseline_literal"]!=0,(
            "DIFFERENT_FIRST_VARIABLE",src["name"])
        assert base["actual_literal"]==base["baseline_literal"] and (
            flip["actual_literal"]==-base["actual_literal"]),(
            "NOT_EXACT_POLARITY_FLIP",src["name"])
        begin=time.perf_counter()
        pred=signal(n,clauses,base["baseline_literal"])
        score_ms=(time.perf_counter()-begin)*1000.
        actual=F.compare(base,flip)
        row={"name":src["name"],"family":src["family"],
             "sha256":src["sha256"],"first_literal":base["baseline_literal"],
             "baseline":base,"flip":flip,"predictor":pred,
             "predicted":pred["recommendation"],"observed_better":actual,
             "feature_python_ms":score_ms}
        data.append(row)
        emit("T0_INTERACTION2_PAIR",{"name":src["name"],"family":src["family"],
             "predicted":pred["recommendation"],"actual":actual,
             "score_flip_minus_base":pred.get("delta_flip_minus_base"),
             "base_conflicts":base["conflicts"],"flip_conflicts":flip["conflicts"],
             "feature_python_ms":round(score_ms,3)})
    predictions=[r for r in data if r["predicted"]]
    evaluated=[r for r in predictions if r["observed_better"]]
    flips=[r for r in data if r["predicted"]==1]
    passivity=[r for r in data if r["predicted"]==0]
    totals={"base_conflicts":sum(r["baseline"]["conflicts"] for r in data),
            "flip_conflicts":sum(r["flip"]["conflicts"] for r in data),
            "base_decisions":sum(r["baseline"]["decisions"] for r in data),
            "flip_decisions":sum(r["flip"]["decisions"] for r in data)}
    final={
        "status":"COMPLETE","sources":len(data),"verified_both":len(data),
        "same_t0_state_pairs":len(data),
        "predicted_non_ties":len(predictions),"predicted_abstain":len(passivity),
        "decisive_prediction_pairs":len(evaluated),
        "correct":sum(r["predicted"]==r["observed_better"] for r in evaluated),
        "wrong":sum(r["predicted"]!=r["observed_better"] for r in evaluated),
        "predicted_flip_wins":sum(r["observed_better"]==1 for r in flips),
        "predicted_flip_losses":sum(r["observed_better"]==-1 for r in flips),
        "predicted_flip_neutral":sum(r["observed_better"]==0 for r in flips),
        "observed_flip_better":sum(r["observed_better"]==1 for r in data),
        "observed_base_better":sum(r["observed_better"]==-1 for r in data),
        "observed_neutral":sum(r["observed_better"]==0 for r in data),
        "second_order_nonzero_pairs":sum(
            (r["predictor"].get("base",{}).get("synergy_total",0) or
             r["predictor"].get("flip",{}).get("synergy_total",0))>0 for r in data),
        "second_order_failed_pair_sources":sum(
            (r["predictor"].get("base",{}).get("failed_pairs",0) or
             r["predictor"].get("flip",{}).get("failed_pairs",0))>0 for r in data),
        "median_python_feature_ms":sorted(r["feature_python_ms"] for r in data)[len(data)//2],
        "totals":totals,"one_logical_cpu":True,"no_training":True,
        "original_models_or_drat_verified":True,"not_general_speedup_evidence":True,
        "not_realworld_holdout":True,"main_modified":False,"solver_promoted":False,
        "manifest_sha256":F.sha(manifest_path.read_bytes())
    }
    (ROOT/"rows.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in data))
    (ROOT/"report.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    emit("T0_INTERACTION2_FINAL",final)

if __name__=="__main__":main()

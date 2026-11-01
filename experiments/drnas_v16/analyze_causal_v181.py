#!/usr/bin/env python3
"""DRNAS V18.1: formula-cluster evaluation, 1-UIP cut analysis, divergence DAG.

Diagnostic stage is retrospective (NOT validation).
Holdout is a fixed unseen set. No policy is chosen using holdout outcomes.
Measured graph cuts = 1-UIP learned clause cut proxies (size/LBD/jump span),
NOT graph-theoretical global minimum cuts.
"""
from __future__ import annotations
import collections,csv,json,math,random,statistics
from pathlib import Path
from official_causal_v181 import ROOT,POLICIES,PINNED_KISSAT,CAP

FEATURE_KEYS=("r512","g512","prop_per_conflict","decisions_per_conflict",
              "cut_size_mean","cut_glue_mean","cut_span_mean",
              "cut_low_glue_fraction","focused_conflict_share")

def read_csv(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))

def average(items):
    return statistics.mean(items) if items else float("nan")

def rank(items):
    ordering=sorted(range(len(items)),key=lambda i:items[i])
    ranks=[0.0]*len(items);index=0
    while index<len(ordering):
        end=index+1
        while end<len(ordering) and items[ordering[end]]==items[ordering[index]]:
            end+=1
        val=(index+end+1)/2
        for t in ordering[index:end]:ranks[t]=val
        index=end
    return ranks

def pearson(x,y):
    if len(x)<4:return None
    mx,my=average(x),average(y)
    cross=sum((a-mx)*(b-my) for a,b in zip(x,y))
    divisor=math.sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
    return cross/divisor if divisor>1e-12 else None

def spearman(x,y):return pearson(rank(x),rank(y))

def percentile_ci(values,seed,draws=1500):
    if not values:return [None,None]
    gen=random.Random(seed)
    n=len(values)
    dist=sorted(average([values[gen.randrange(n)] for _ in range(n)])
                for _ in range(draws))
    return [round(dist[37],6),round(dist[1461],6)]

def permutation_test(x,y,seed,n=1499):
    observed=spearman(x,y)
    if observed is None:return None,None
    gen=random.Random(seed)
    count=0
    for _ in range(n):
        shuffled=list(y);gen.shuffle(shuffled)
        alt=spearman(x,shuffled)
        if alt is not None and abs(alt)>=abs(observed)-1e-12:
            count+=1
    return round(observed,5),round((count+1)/(n+1),5)

def cut_metrics(t):
    def n(key):
        return float(t.get(key,"0") or 0)
    count=max(1,n("cut_n"))
    conflicts=max(1,n("conflicts"))
    return {"cut_size_mean":n("cut_size")/count,
            "cut_glue_mean":n("cut_glue")/count,
            "cut_span_mean":n("cut_span")/count,
            "cut_low_glue_fraction":n("cut_low")/count,
            "cut_short_fraction":n("cut_short")/count,
            "cut_per_conflict":n("cut_n")/conflicts,
            "prop_per_conflict":n("propagations")/conflicts,
            "decisions_per_conflict":n("decisions")/conflicts,
            "focused_conflict_share":n("focused_conflicts")/conflicts,
            "restart_rate":n("restarts")/conflicts}

def stage_report(stage):
    measures=[];snapshots=[];manifests=[]
    for batch in range(4):
        folder=ROOT/f"{stage}_{batch}"
        measures+=read_csv(folder/"measurements.csv")
        snapshots+=read_csv(folder/"checkpoints.csv")
        manifests.append(json.loads((folder/"manifest.json").read_text()))
    if len(measures)==0:raise RuntimeError("No completed paired cases")
    group=collections.defaultdict(dict)
    for row in measures:
        key=(int(row["official_index"]),int(row["repeat"]))
        if row["mode"] in group[key]:raise RuntimeError("Duplicate policy")
        group[key][row["mode"]]=row
    if not all(set(modes)==set(POLICIES) for modes in group.values()):
        raise RuntimeError("Missing policy from paired trial")
    case_group=collections.defaultdict(lambda:collections.defaultdict(list))
    for (index,rep),modes in group.items():
        for mode,row in modes.items():
            case_group[index][mode].append(row)
    baselines={index:average([float(r["par2"]) for r in modes["trace"]])
               for index,modes in case_group.items()}
    ranking=[];deltas=[]
    for mode in POLICIES:
        sub={index:average([float(r["par2"]) for r in modes[mode]])
             for index,modes in case_group.items()}
        gain=[baselines[i]-sub[i] for i in sorted(case_group)]
        old=average(list(baselines.values()))
        new=average(list(sub.values()))
        ranking.append(dict(mode=mode,formula_count=len(case_group),
                 attempts=sum(len(modes[mode]) for modes in case_group.values()),
                 solved=sum(x["status"] in ("SAT","UNSAT")
                            for modes in case_group.values() for x in modes[mode]),
                 mean_par2=round(new,6),
                 baseline_trace_par2=round(old,6),
                 advantage_seconds=round(average(gain),6),
                 advantage_pct=round(100*(1-new/old),3),
                 ci95_advantage_seconds=percentile_ci(gain,181000+len(mode)),
                 wins=sum(g>0.001 for g in gain),
                 losses=sum(g< -0.001 for g in gain),
                 ties=sum(abs(g)<=0.001 for g in gain)))
        for index in sorted(case_group):
            deltas.append(dict(stage=stage,official_index=index,
                       mode=mode,baseline=round(baselines[index],6),
                       candidate=round(sub[index],6),
                       advantage=round(baselines[index]-sub[index],6)))
    ranking.sort(key=lambda r:r["mean_par2"])
    ticks=collections.defaultdict(dict)
    for row in snapshots:
        key=(int(row["official_index"]),int(row["repeat"]),row["mode"])
        time=int(row["at"])
        ticks[key][time]=row
    features_by_formula=collections.defaultdict(list)
    first_divergence=[];causal_after=[]
    for (index,rep),modes in group.items():
        base=ticks.get((index,rep,"trace"),{})
        early=base.get(512)
        if early:
            features= cut_metrics(early)
            features.update(stage=stage,official_index=index,repeat=rep,
                            r512=float(early["restarts"]),
                            g512=float(early["ratio"]),
                            response=float(modes["trace"]["par2"]) -
                                     float(modes["switch2048_i25"]["par2"]))
            features_by_formula[index].append(features)
        for mode in POLICIES:
            if mode in ("trace","plain"):continue
            alternate=ticks.get((index,rep,mode),{})
            split=None
            deltas_at=[]
            for at in sorted(set(base)&set(alternate)):
                old,new=base[at],alternate[at]
                fields=("restarts","decisions","propagations","learned",
                        "cut_n","cut_size","cut_glue","cut_span","cut_low",
                        "focused_conflicts","stable_conflicts")
                if split is None and any(old.get(k)!=new.get(k) for k in fields):
                    split=at
                if at>=1024:
                    first=cut_metrics(old);second=cut_metrics(new)
                    deltas_at.append(dict(stage=stage,official_index=index,
                         repeat=rep,mode=mode,checkpoint=at,
                         delta_restarts=float(new["restarts"])-float(old["restarts"]),
                         delta_propagations=float(new["propagations"])-float(old["propagations"]),
                         delta_learned=float(new["learned"])-float(old["learned"]),
                         delta_mean_cut_glue=round(second["cut_glue_mean"]-first["cut_glue_mean"],6),
                         delta_mean_cut_span=round(second["cut_span_mean"]-first["cut_span_mean"],6),
                         delta_low_glue_fraction=round(second["cut_low_glue_fraction"]-first["cut_low_glue_fraction"],6),
                         delta_focused_share=round(second["focused_conflict_share"]-first["focused_conflict_share"],6)))
            first_divergence.append(dict(stage=stage,official_index=index,
                 repeat=rep,mode=mode,
                 first_divergence_at=split if split is not None else "not_observed",
                 baseline_par2=modes["trace"]["par2"],
                 experimental_par2=modes[mode]["par2"]))
            causal_after+=deltas_at
    features=[]
    for index,rows in sorted(features_by_formula.items()):
        keys=("r512","g512","prop_per_conflict","decisions_per_conflict",
             "cut_size_mean","cut_glue_mean","cut_span_mean",
             "cut_low_glue_fraction","focused_conflict_share",
             "cut_short_fraction","restart_rate","response")
        features.append({"official_index":index,**{
           k:average([r[k] for r in rows]) for k in keys}})
    correlations=[]
    for i,key in enumerate(FEATURE_KEYS):
        x=[f[key] for f in features]
        y=[f["response"] for f in features]
        rho,p=permutation_test(x,y,181+i)
        correlations.append(dict(stage=stage,feature=key,formula_count=len(x),
                                 spearman_rho=rho,permutation_p_unadjusted=p,
                                 note="Exploratory multi-feature search, no independent significance"))
    # Holm step-down p correction for multiple comparisons of inspected features.
    valid=sorted([(j,r["permutation_p_unadjusted"]) for j,r in enumerate(correlations)
                  if r["permutation_p_unadjusted"] is not None],
                 key=lambda t:t[1])
    max_adjusted=0.0
    for i,(j,p) in enumerate(valid):
        max_adjusted=max(max_adjusted,min(1.0,p*(len(valid)-i)))
        correlations[j]["holm_adjusted_p"]=round(max_adjusted,6)
    outcome=dict(stage=stage,retrospective=stage=="diagnostic",
                 holdout_precommitted=stage=="holdout",
                 formula_count=len(case_group),attempts=len(measures),
                 cap_seconds=CAP,
                 policies_precommitted=True,
                 source_kissat=PINNED_KISSAT,
                 ranking=ranking,early_cut_correlations=correlations,
                 first_divergence_pairs=len(first_divergence),
                 post_checkpoint_comparisons=len(causal_after),
                 locally_verified_unsat_proofs=0,
                 caveat=("Measurements on official 2026 competition formulas, "
                    "but not official competition score. Prior diagnostic "
                    "observations were not a held-out proof. Cut metrics are "
                    "1-UIP clause-boundary proxies, not literal minimum graph cuts."))
    dest=ROOT/f"aggregate_{stage}"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"summary.json").write_text(json.dumps(outcome,indent=2))
    (dest/"features.json").write_text(json.dumps(features,indent=2))
    def output_csv(name,rows):
        with (dest/name).open("w",newline="") as file:
            writer=csv.DictWriter(file,fieldnames=list(rows[0]) if rows else ["empty"])
            writer.writeheader();writer.writerows(rows)
    output_csv("paired_deltas.csv",deltas)
    output_csv("first_divergence.csv",first_divergence)
    output_csv("causal_after_intervention.csv",causal_after)
    output_csv("correlations.csv",correlations)
    graph={
      "nodes":[
        {"id":"C","label":"CNF structural features, no outcome"},
        {"id":"U","label":"1-UIP implication graph cut: LBD/size/backjump"},
        {"id":"E","label":"Early 512 conflict statistics: LBD ratio/restarts/propagation"},
        {"id":"I","label":"Randomized-order forced restart interval intervention"},
        {"id":"D","label":"Post-switch graph-cut and search-state divergence"},
        {"id":"Y","label":"Wall-time and PAR-2 outcome"}],
      "edges":[
        {"from":"C","to":"U","status":"hypothesis"},
        {"from":"U","to":"E","status":"observable temporal relationship"},
        {"from":"E","to":"I","status":"only for fixed gate policies"},
        {"from":"I","to":"D","status":"experimentally manipulated"},
        {"from":"D","to":"Y","status":"mechanism hypothesis"}],
      "design_note":"Forced action differs only after identical preintervention states, subject to execution-order and instrumentation audit."
    }
    (dest/"causal_graph_hypothesis.json").write_text(json.dumps(graph,indent=2))
    print("V181_AGGREGATE_"+stage.upper(),json.dumps(outcome,separators=(",",":")),flush=True)
    return outcome

if __name__=="__main__":
    dev=stage_report("diagnostic")
    holdout=stage_report("holdout")
    final=dict(diagnostic=dev,holdout=holdout,
       "experiment_completeness":"Only successfully fetched complete cases",
       "no_strategy_promoted":True)
    (ROOT/"combined.json").write_text(json.dumps(final,indent=2))
    print("V181_FINAL",json.dumps({
       "diagnostic_cases":dev["formula_count"],
       "holdout_cases":holdout["formula_count"],
       "diagnostic_top":dev["ranking"][0],
       "holdout_top":holdout["ranking"][0]},separators=(",",":")),flush=True)

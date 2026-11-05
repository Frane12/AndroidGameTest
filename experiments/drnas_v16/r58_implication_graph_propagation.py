#!/usr/bin/env python3
"""DRNAS R58: audit the binary implication graph and bounded unit propagation.

Research-only: matched original SATComp2026 SHA-locked R52/R55b cases and their
previously published timing labels. No new solver binary or policy change.
We use *only original* sampled clauses of length 1..4 (R47's first 60k sample);
binary (a v b) gives ~a -> b and ~b -> a. Ternary clauses DO NOT create
unconditional arcs; their conditional unit propagation is measured by a separate
bounded UP experiment. Extract the same frozen R47 resolution proofs.

All predictive comparisons are POST-HOC and diagnostic, NOT new blind evidence.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import statistics
from pathlib import Path

import r47_partial_links as r47
import r49_pivot_coherence_gate as r49

PROTO="DRNAS-R58-IMPLICATION-GRAPH-UNITPROP-20261103-v1"
R52="DRNAS-R52-PROSPECTIVE-2026-TOPREFS-20261103-v1"
METRICS=("graph_edges","graph_nodes","original_binary_clauses",
         "original_binary_ratio","head24_binary_count","head24_new_arcs",
         "head24_existing_arcs","head24_reachable_arcs_depth8",
         "head24_shortcut_arcs_depth8","head24_weak_component_bridges",
         "head24_max_binary_node_degree","head24_derived_share_variables",
         "head24_source_polarity_overlap","probing_trials",
         "probing_comparable","probing_increased_units",
         "probing_increased_conflicts","probing_mean_new_units",
         "probing_mean_clause_visits_saved",
         "head24_min_source_component_size",
         "window_binary_clauses","target_pair_graph_distance",
         "target_pair_variable_overlap")
MAX_BFS_DEPTH=8
MAX_BFS_NODES=2500
MAX_UNIT_ASSIGNED=2500
MAX_UNIT_VISITS=30000
MAX_PROBES=24

def ck(v,msg):
    if not v: raise RuntimeError("R58_SOURCE_OR_FEATURE_AUDIT_FAIL "+str(msg))

def sha(path):
    return r49.sha(path)

def arcs(clause):
    ck(len(clause)==2,"binary arcs for non-binary clause")
    a,b=clause
    return ((-a,b),(-b,a))

def graph_for(clauses):
    graph=collections.defaultdict(set)
    parent={}
    ranks={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb:
            if ra>rb:ra,rb=rb,ra
            parent[rb]=ra
    binary_count=0
    for c in clauses:
        if len(c)!=2:continue
        binary_count+=1
        for u,v in arcs(c):
            graph[u].add(v)
            graph.setdefault(v,set())
            union(u,v)
    counts=collections.Counter(find(x) for x in graph)
    return graph,find,counts,binary_count

def reach(graph,a,b,maxdepth=MAX_BFS_DEPTH,cap=MAX_BFS_NODES):
    if a==b:return 0
    seen={a}
    queue=collections.deque([(a,0)])
    while queue and len(seen)<cap:
        u,d=queue.popleft()
        if d>=maxdepth:continue
        for v in graph.get(u,()):
            if v==b:return d+1
            if v not in seen:
                seen.add(v)
                queue.append((v,d+1))
                if len(seen)>=cap:break
    return None

def binary_effect(original,added):
    graph,find,count,n_binary=graph_for(original)
    pre_edges=sum(map(len,graph.values()))
    new=existing=reachable=shortcuts=bridges=0
    deg=[]
    original_arcs=set((u,v) for u,outs in graph.items() for v in outs)
    # Do not update the original graph between new clauses: all metrics
    # refer to the same pre-intervention baseline.
    for c in added:
        if len(c)!=2:continue
        for u,v in arcs(c):
            deg.append(len(graph.get(u,()))+len(graph.get(v,())))
            if (u,v) in original_arcs:
                existing+=1
                continue
            new+=1
            dist=reach(graph,u,v)
            if dist is not None:
                reachable+=1
                if dist>=2:shortcuts+=1
            if find(u)!=find(v):bridges+=1
    return dict(graph=graph,component_of=find,compcounts=count,
         original_binary_clauses=n_binary,graph_edges=pre_edges,
         graph_nodes=len(graph),
         head24_new_arcs=new,head24_existing_arcs=existing,
         head24_reachable_arcs_depth8=reachable,
         head24_shortcut_arcs_depth8=shortcuts,
         head24_weak_component_bridges=bridges,
         head24_max_binary_node_degree=max(deg,default=0))

def postings_for(clauses):
    occurrence=collections.defaultdict(list)
    units=[]
    for i,c in enumerate(clauses):
        if len(c)==1:units.append(c[0])
        for lit in c:
            occurrence[lit].append(i)
    return occurrence,units

def unit_propagate(clauses,postings,units,assumptions):
    """Exact UP on sampled clauses unless bound hit; no false binary arcs."""
    assigned={}
    todo=collections.deque([*units,*assumptions])
    visits=0
    while todo:
        literal=todo.popleft()
        v=abs(literal)
        sign=1 if literal>0 else -1
        prior=assigned.get(v)
        if prior is not None:
            if prior!=sign:
                return dict(conflict=True,assigned=len(assigned),
                            visits=visits,truncated=False)
            continue
        assigned[v]=sign
        if len(assigned)>MAX_UNIT_ASSIGNED:
            return dict(conflict=False,assigned=len(assigned),
                        visits=visits,truncated=True)
        # Only clauses containing the newly falsified literal can become unit.
        for index in postings.get(-literal,()):
            visits+=1
            if visits>MAX_UNIT_VISITS:
                return dict(conflict=False,assigned=len(assigned),
                            visits=visits,truncated=True)
            clause=clauses[index]
            remaining=0
            unit=None
            satisfied=False
            for lit in clause:
                z=assigned.get(abs(lit))
                if z is None:
                    remaining+=1
                    unit=lit
                elif z==(1 if lit>0 else -1):
                    satisfied=True
                    break
            if satisfied:continue
            if remaining==0:
                return dict(conflict=True,assigned=len(assigned),
                            visits=visits,truncated=False)
            if remaining==1:todo.append(unit)
    return dict(conflict=False,assigned=len(assigned),
                visits=visits,truncated=False)

def probing_seeds(new):
    # Apply false assignments to each literal (binary) or each pair of
    # literals (ternary), so the derived resolvent is locally relevant.
    unique=set()
    for c in new:
        if len(c)==2:
            for literal in c:unique.add((-literal,))
        elif len(c)==3:
            for i in range(3):
                for j in range(i+1,3):
                    pair=(-c[i],-c[j])
                    if abs(pair[0])!=abs(pair[1]):
                        unique.add(tuple(sorted(pair,key=lambda z:(abs(z),z))))
    # Deterministically pick 24 distinct probes (not using time labels).
    return sorted(unique,key=lambda t:hashlib.sha256(
        (PROTO+"/"+",".join(map(str,t))).encode()).hexdigest())[:MAX_PROBES]

def propagation_effect(original,derived,alternative):
    original_post,original_units=postings_for(original)
    augmented=original+[tuple(c) for c in alternative]
    after_post,after_units=postings_for(augmented)
    seeds=probing_seeds(derived)
    comparable=increased=conflicts=0
    diff_units=0
    saved_visits=0
    observed=[]
    for assumptions in seeds:
        before=unit_propagate(original,original_post,original_units,assumptions)
        after=unit_propagate(augmented,after_post,after_units,assumptions)
        if before["truncated"] or after["truncated"]:continue
        if before["conflict"]:continue
        comparable+=1
        extra=max(0,after["assigned"]-before["assigned"])
        conflict_new=after["conflict"] and not before["conflict"]
        increased+=int(extra>0)
        conflicts+=int(conflict_new)
        diff_units+=extra
        saved_visits+=before["visits"]-after["visits"]
        if len(observed)<8:
            observed.append(dict(assumptions=list(assumptions),
              original_assigned=before["assigned"],after_assigned=after["assigned"],
              new_conflict=bool(conflict_new),
              original_visits=before["visits"],after_visits=after["visits"]))
    return dict(probing_trials=len(seeds),probing_comparable=comparable,
         probing_increased_units=increased,
         probing_increased_conflicts=conflicts,
         probing_mean_new_units=round(diff_units/max(comparable,1),5),
         probing_mean_clause_visits_saved=round(saved_visits/max(comparable,1),5),
         probing_examples=observed)

def feature(original):
    n,short,trace=r47.sample_original(original)
    ck(n is not None,"short CNF sampling disabled by bound")
    plan=r49.compute_plan(original)
    new=[tuple(c) for c in plan["clauses"]]
    h=new[:24]
    window=new[16:24]
    graph_info=binary_effect(short,h)
    deg=collections.Counter(abs(x) for c in h for x in c)
    comp=graph_info["component_of"]
    comps=graph_info["compcounts"]
    scope=[comp(lit) for c in h for lit in c]
    unit=propagation_effect(short,h,h)
    pair=None
    if len(new)>=24:
        a,b=new[16],new[23]
        pair_graph_distances=[reach(graph_info["graph"],u,v)
            for u in a for v in b]
        good=[x for x in pair_graph_distances if x is not None]
        pair=dict(clause17=list(a),clause24=list(b),
           variable_overlap=len(set(map(abs,a))&set(map(abs,b))),
           directed_min_distance=min(good) if good else None,
           two_clauses_up=propagation_effect(short,h,[a,b]),
           head16_plus_pair_up=propagation_effect(short,h,new[:16]+[a,b]),
           head16_up=propagation_effect(short,h,new[:16]))
    # A parent resolution witness is always independently checked by R47/R46.
    source_polarity=collections.defaultdict(set)
    for c in h:
        for lit in c:source_polarity[abs(lit)].add(lit>0)
    features={
      "graph_edges":graph_info["graph_edges"],
      "graph_nodes":graph_info["graph_nodes"],
      "original_binary_clauses":graph_info["original_binary_clauses"],
      "original_binary_ratio":round(graph_info["original_binary_clauses"]/max(1,len(short)),6),
      "head24_binary_count":sum(len(c)==2 for c in h),
      "head24_new_arcs":graph_info["head24_new_arcs"],
      "head24_existing_arcs":graph_info["head24_existing_arcs"],
      "head24_reachable_arcs_depth8":graph_info["head24_reachable_arcs_depth8"],
      "head24_shortcut_arcs_depth8":graph_info["head24_shortcut_arcs_depth8"],
      "head24_weak_component_bridges":graph_info["head24_weak_component_bridges"],
      "head24_max_binary_node_degree":graph_info["head24_max_binary_node_degree"],
      "head24_derived_share_variables":sum(z>=2 for z in deg.values()),
      "head24_source_polarity_overlap":sum(len(v)==2 for v in source_polarity.values()),
      "probing_trials":unit["probing_trials"],
      "probing_comparable":unit["probing_comparable"],
      "probing_increased_units":unit["probing_increased_units"],
      "probing_increased_conflicts":unit["probing_increased_conflicts"],
      "probing_mean_new_units":unit["probing_mean_new_units"],
      "probing_mean_clause_visits_saved":unit["probing_mean_clause_visits_saved"],
      "head24_min_source_component_size":min(
          (comps.get(x,1) for x in scope),default=0),
      "window_binary_clauses":sum(len(c)==2 for c in window),
      "target_pair_graph_distance":pair["directed_min_distance"] if pair else None,
      "target_pair_variable_overlap":pair["variable_overlap"] if pair else None,
    }
    ck(set(features)==set(METRICS),"schema mismatch")
    return dict(features=features,gate=plan["gate"],source_sha=sha(original),
       original_vars=n,sampled_short_clauses=len(short),
       original_clauses=trace["original_clauses"],
       cert=plan["certificate_sha256"],
       up_probes=unit["probing_examples"],special_pair=pair)

def selftest():
    binary=[(1,2),(-2,3)]
    g,_,_,_=graph_for(binary)
    ck(reach(g,-1,3)==2,"binary implication path missing")
    ck(reach(g,-3,1)==2,"contrapositive path missing")
    e=binary_effect(binary,[(1,3)])
    ck(e["head24_new_arcs"]==2 and e["head24_shortcut_arcs_depth8"]==2,
        "new shortcut path count wrong")
    # Unit propagation: (1 v 2), not(1) => 2; ternary needs TWO falsified inputs.
    po,units=postings_for([(1,2),(3,4,5)])
    z=unit_propagate([(1,2),(3,4,5)],po,units,(-1,))
    ck(z["assigned"]==2 and not z["conflict"],"binary UP failed")
    a=unit_propagate([(1,2),(3,4,5)],po,units,(-3,-4))
    ck(a["assigned"]==3 and not a["conflict"],"ternary conditional UP failed")
    print("R58_SELFTEST_GRAPH_UP_PASS",flush=True)

def effect(rows,cohort,gbd):
    if cohort=="R52":
        b,a="kissat_pinned","drnas_r49_gate"
    else:b,a="clean","full40_gate"
    base=[r for r in rows if r["gbd"]==gbd and r["mode"]==b]
    active=[r for r in rows if r["gbd"]==gbd and r["mode"]==a]
    ck(len(base)==len(active) and len(base) in (1,2),"historical result missing")
    bb=sum(r["par2_s"] for r in base)/len(base)
    aa=sum(r["par2_s"] for r in active)/len(active)
    return dict(baseline=round(bb,5),enhanced=round(aa,5),
       difference_s=round(aa-bb,5),
       percent=round(100*(aa/bb-1),4) if bb else None,
       repetitions=len(base))

def measure(args):
    a=Path(args.r52sources)
    b=Path(args.r55sources)
    reports={"R52":json.loads(Path(args.r52report).read_text()),
             "R55b":json.loads(Path(args.r55report).read_text())}
    origins={"R52":a,"R55b":b}
    ck(reports["R52"]["protocol"]==R52 and
       reports["R55b"]["protocol"].startswith("DRNAS-R55B-"),
       "historical protocol drift")
    cases=[]
    for cohort,root in origins.items():
        manifest=json.loads((root/"manifest.json").read_text())
        ck(len(manifest["cases"])==11,"not archived 11 source freeze "+cohort)
        for case in manifest["cases"]:
            cases.append((cohort,root,case))
    ck(args.shard in range(4),"unknown shard")
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for cohort,root,case in cases[args.shard::4]:
        name=case.get("name",case.get("filename"))
        source=root/name
        expected_sha=case.get("sha256",case.get("source_sha256"))
        ck(source.is_file() and sha(source)==expected_sha,
           "historical original source SHA mismatch")
        f=feature(source)
        ck(f["source_sha"]==expected_sha,"calculated SHA mismatch")
        r=dict(gbd=case["gbd"],cohort=cohort,
            **f,
            actual=effect(reports[cohort]["rows"],cohort,case["gbd"]))
        rows.append(r)
        print("R58_GRAPH_RESULT",case["gbd"],cohort,
          "gate",r["gate"],"PAR2_delta",r["actual"]["difference_s"],
          "binary",r["features"]["original_binary_ratio"],
          "new_arcs",r["features"]["head24_new_arcs"],
          "shortcut_arcs",r["features"]["head24_shortcut_arcs_depth8"],
          "UP_new_units",r["features"]["probing_mean_new_units"],
          "UP_new_conflicts",r["features"]["probing_increased_conflicts"],flush=True)
        (output/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    (output/"meta.json").write_text(json.dumps(
        dict(protocol=PROTO,shard=args.shard,n=len(rows),
             r52manifestsha=sha(a/"manifest.json"),
             r55manifestsha=sha(b/"manifest.json")),indent=2)+"\n")
    ck(len(rows)==len(cases[args.shard::4]),"incomplete shard")

def audit(args):
    rows=[];seen=set()
    first_manifest=None
    for shard in range(4):
        root=Path(args.combined)/f"r58-shard-{shard}"/"results"
        meta=json.loads((root/"meta.json").read_text())
        ck(meta["protocol"]==PROTO and meta["shard"]==shard,
            "missing original shard")
        frozen=(meta["r52manifestsha"],meta["r55manifestsha"])
        if first_manifest is None:first_manifest=frozen
        ck(frozen==first_manifest,"mixed frozen source lists")
        group=json.loads((root/"rows.json").read_text())
        ck(len(group)==meta["n"],"shard loss")
        for r in group:
            ck(r["source_sha"] not in seen,"duplicate source SHA")
            seen.add(r["source_sha"])
            rows.append(r)
    ck(len(rows)==22,"22 source historical cohort incomplete")
    active=[r for r in rows if r["gate"]]
    ck(len(active)==9,"R56 active cohort unexpectedly changed")
    ranking=[]
    for key in METRICS:
        valid=[r for r in active if r["features"][key] is not None]
        if len(valid)<5:continue
        # Rank features against observed PAR2 delta only (post-hoc).
        values=[float(r["features"][key]) for r in valid]
        y=[r["actual"]["difference_s"] for r in valid]
        if len(set(values))<2:continue
        def ranks(v):
            idx=sorted(range(len(v)),key=lambda i:v[i])
            out=[0.0]*len(v)
            for rank,i in enumerate(idx):out[i]=rank+1.0
            # Standard midranks for ties.
            for same in set(v):
                ii=[i for i,t in enumerate(v) if t==same]
                mean=sum(out[i] for i in ii)/len(ii)
                for i in ii:out[i]=mean
            return out
        x=ranks(values);yy=ranks(y)
        ax=sum(x)/len(x);ay=sum(yy)/len(yy)
        den=math.sqrt(sum((t-ax)**2 for t in x)*sum((t-ay)**2 for t in yy))
        corr=sum((u-ax)*(v-ay) for u,v in zip(x,yy))/den if den else 0
        ranking.append(dict(name=key,rank_correlation_delta=round(corr,5),
                            n=len(valid)))
    ranking.sort(key=lambda x:abs(x["rank_correlation_delta"]),reverse=True)
    winner=next(r for r in rows if r["gbd"].startswith("2b35377a"))
    p=winner["special_pair"]
    ck(p is not None and p["variable_overlap"]==0,
        "R55 clause 17+24 source changed")
    audit=dict(protocol=PROTO,total_originals=len(rows),active_gate=len(active),
       results=rows,feature_associations=ranking,
       r55_special_pair=p,
       limitations=[
        "Purely retrospective, using original R52/R55b timing labels",
        "No new prospective source or experiment was timed",
        "Graph includes sampled short ORIGINAL clauses only, not the full original CNF",
        "Binary clause arcs are unconditional, ternaries only in bounded unit propagation",
        "Bounded 8-hop reach and UP caps are approximations, not logical completeness",
        "Associations across only nine gate-active formulas are exploratory and overfit-prone",
        "SAT progress is not determined solely by Boolean unit propagation",
        "R55 pair 17+24 is a selected positive example and must not form universal rule",
        "Historical labels are 40s PAR2, censored at 40s and different source cohorts",
       ])
    Path(args.json).write_text(json.dumps(audit,indent=2)+"\n")
    lines=[
      "# DRNAS R58 — source implication graph and bounded unit propagation",
      "**OBSERVATIONAL, no newly timed SAT solver**. Official 2026 original SHA files.",
      "Each binary (a ∨ b) becomes ¬a→b and ¬b→a. Ternary/4-literal clauses do not make unconditional graph arcs.",
      "22 source SHA distinct originals (11 R52 and 11 R55b), nine R49-active cases.",
      "",
      "## R49-active sources: structural graph vs historical end-to-end PAR2",
      "| Source GBD | Cohort | Original binaries | New binary arcs | Shortcuts ≤8 hops | Extra UP forced | Extra UP conflicts | Historic delta s/attempt |",
      "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in active:
        f=r["features"]
        lines.append(f'| {r["gbd"][:12]} | {r["cohort"]} | {f["original_binary_clauses"]} | {f["head24_new_arcs"]} | {f["head24_shortcut_arcs_depth8"]} | {f["probing_mean_new_units"]:.3f} | {f["probing_increased_conflicts"]} | {r["actual"]["difference_s"]:+.3f} |')
    lines+=["","## Nine-case descriptive Spearman feature associations to historic PAR2 delta",
            "Associations are discovery-only and require independent verification.",
            "| Feature | Spearman rho | n |",
            "|---|---:|---:|"]
    for z in ranking[:15]:
        lines.append(f'| {z["name"]} | {z["rank_correlation_delta"]:+.3f} | {z["n"]} |')
    lines+=["","## Selected R55 positive formula, clause 17 plus clause 24",
            f'Clause 17: {p["clause17"]}',
            f'Clause 24: {p["clause24"]}',
            f'Variable overlap: {p["variable_overlap"]}',
            f'Bounded directed graph distance between their literal sets: {p["directed_min_distance"]}',
            f'UP mean new forced literals when both clauses are added: {p["two_clauses_up"]["probing_mean_new_units"]}',
            f'UP mean new forced literals adding selected pair on first16: {p["head16_plus_pair_up"]["probing_mean_new_units"]}',
            f'UP mean new forced literals with first16 alone: {p["head16_up"]["probing_mean_new_units"]}',
            "","No absolute causal or predictor claim from these features.",
            "Next: freeze at most one feature before a SHA-disjoint matched SAT benchmark."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R58_GRAPH_AUDIT_PASS",json.dumps({
      "originals":len(rows),"active_gate":len(active),
      "top_features":ranking[:8],
      "target_pair":dict(clause17=p["clause17"],clause24=p["clause24"],
          distance=p["directed_min_distance"],
          overlap=p["variable_overlap"],
          probe_pair_added=p["head16_plus_pair_up"]["probing_mean_new_units"]),
      "active_cases":[dict(gbd=r["gbd"],cohort=r["cohort"],
         delta=r["actual"]["difference_s"],
         binary=r["features"]["original_binary_clauses"],
         new_arcs=r["features"]["head24_new_arcs"],
         shortcuts=r["features"]["head24_shortcut_arcs_depth8"],
         new_units=r["features"]["probing_mean_new_units"])
         for r in active]},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="task",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for x in ("r52sources","r55sources","r52report","r55report","shard","out"):
        m.add_argument("--"+x,required=True)
    a=sub.add_parser("audit")
    for x in ("combined","json","md"):a.add_argument("--"+x,required=True)
    args=p.parse_args()
    if args.task=="selftest":selftest()
    elif args.task=="measure":
        args.shard=int(args.shard)
        measure(args)
    else:audit(args)

if __name__=="__main__":main()

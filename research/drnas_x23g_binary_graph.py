#!/usr/bin/env python3
"""DRNAS X23G: follow the binary implication GRAPH, not raw clause counts.

Four progressive source-window snapshots construct actual signed-literal
implication edges, SCCs, signed aliases, and reachable propagation chains.
The graph only SELECTS whether frozen X22's proof-replayed reducer runs.
No new inference is added to the solver; all original SAT models are checked.
This is X21/X22 source replay, NOT a new blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import time

import drnas_x22_parallel_reducer as x22
import drnas_x23_adaptive_gate as x23

ROOT=pathlib.Path("mre_x23g")
PROTO="DRNAS-X23G-SIGNED-BINARY-GRAPH-24SHA-6ARM-2REP-15S-20261109-v1"
ARMS=("race_original","race_quotient","gate_strict","gate_liberal",
      "graph_scc","graph_frontier")
SHARDS=8
REPS=2
CAP=15.0
EXPECTED=24*REPS*len(ARMS)
WINDOW=65536
MAX_WINDOW_BYTES=4*WINDOW
MAX_GRAPH_PROBE_S=0.45
MAX_EDGES=85000

def need(condition,message):
    if not condition:raise RuntimeError("X23G_FAIL_CLOSED "+str(message))

def digest(path):return x22.digest(path)
def save(path,value):return x22.save(path,value)

def windows(path):
    """Four physically distinct positions, keeping complete DIMACS lines.

    This is intentionally incomplete: false negatives route to the ORIGINAL
    two-solver race. Full reduction always goes through X22 proof replay.
    """
    path=pathlib.Path(path)
    size=path.stat().st_size
    if size<=MAX_WINDOW_BYTES:
        return [(0,path.read_bytes())]
    offsets=[0,max(0,size//3-WINDOW//2),
             max(0,(2*size)//3-WINDOW//2),max(0,size-WINDOW)]
    out=[]
    seen=set()
    with path.open("rb") as f:
        for start in offsets:
            start=min(start,size-WINDOW)
            if start in seen:continue
            seen.add(start)
            f.seek(start)
            chunk=f.read(WINDOW)
            if start>0:
                split=chunk.find(b"\n")
                chunk=chunk[split+1:] if split>=0 else b""
            if start+WINDOW<size:
                split=chunk.rfind(b"\n")
                chunk=chunk[:split+1] if split>=0 else b""
            out.append((start,chunk))
    return out

def parse_window_binary(block):
    clauses=0; binary=0; duplicates=0; tautologies=0
    seen=set(); edges=[]
    for line in block.splitlines():
        data=line.strip()
        if not data or data[:1] in (b"c",b"p",b"%"):continue
        fields=data.split()
        if len(fields)<2 or fields[-1]!=b"0":continue
        try: values=tuple(int(x) for x in fields[:-1])
        except ValueError:continue
        if not values or 0 in values:continue
        clauses+=1
        canonical=tuple(sorted(set(values)))
        if canonical in seen:duplicates+=1
        seen.add(canonical)
        if any(-lit in canonical for lit in canonical):
            tautologies+=1
            continue
        if len(canonical)==2:
            a,b=canonical
            if a==b or a==-b:continue
            binary+=1
            edges.append((-a,b))
            edges.append((-b,a))
    return dict(clauses=clauses,binaries=binary,duplicates=duplicates,
                tautologies=tautologies,edges=edges)

def graph_snapshot(adj,reverse,edges):
    """Iterative Kosaraju SCC plus bounded propagation from real hub vertices."""
    vertices=sorted(set(adj)|set(reverse))
    neighbors={v:sorted(adj.get(v,())) for v in vertices}
    back={v:sorted(reverse.get(v,())) for v in vertices}
    visited=set();finish=[]
    for root in vertices:
        if root in visited:continue
        visited.add(root);stack=[(root,0)]
        while stack:
            v,index=stack[-1]
            if index==len(neighbors[v]):
                finish.append(v);stack.pop();continue
            to=neighbors[v][index]
            stack[-1]=(v,index+1)
            if to not in visited:
                visited.add(to);stack.append((to,0))
    component={};groups=[]
    for root in reversed(finish):
        if root in component:continue
        cid=len(groups);component[root]=cid;group=[];stack=[root]
        while stack:
            v=stack.pop();group.append(v)
            for to in back[v]:
                if to not in component:
                    component[to]=cid;stack.append(to)
        groups.append(group)
    contradictions=0
    for v in vertices:
        if v>0 and component.get(v)==component.get(-v):
            contradictions+=1
    min_lit={i:min(group,key=lambda x:(abs(x),x<0))
             for i,group in enumerate(groups)}
    aliases=[]
    if not contradictions:
        for v in vertices:
            if v<=0:continue
            target=min_lit[component[v]]
            if abs(target)<v and component.get(-v)==component.get(-target):
                aliases.append((v,target))
    nontrivial=sum(len(g)>1 for g in groups)
    cycle_nodes=sum(len(g) for g in groups if len(g)>1)
    largest=max((len(g) for g in groups),default=0)
    seeds=sorted(vertices,key=lambda v:(-len(neighbors[v]),v))[:12]
    maximal_depth=0;maximal_reach=0;branching_paths=0
    for root in seeds:
        seen={root};queue=collections.deque([(root,0)])
        local_depth=0
        while queue and len(seen)<=2500:
            v,depth=queue.popleft();local_depth=max(local_depth,depth)
            if depth>=6:continue
            if len(neighbors[v])>=2:branching_paths+=1
            for to in neighbors[v]:
                if to not in seen:
                    seen.add(to);queue.append((to,depth+1))
        maximal_depth=max(maximal_depth,local_depth)
        maximal_reach=max(maximal_reach,len(seen)-1)
    return dict(nodes=len(vertices),edges=edges,
          scc_nontrivial=nontrivial,scc_cycle_nodes=cycle_nodes,
          scc_largest=largest,signed_aliases=len(aliases),
          alias_examples=aliases[:6],
          contradictory_scc=contradictions,
          max_chain_depth=maximal_depth,
          max_bounded_reachable=maximal_reach,
          branching_paths=branching_paths)

def follow_binary_graph(path):
    """Progressively add original binary edges and record each stage."""
    t0=time.perf_counter()
    adj=collections.defaultdict(set)
    reverse=collections.defaultdict(set)
    stages=[];edges=0
    clauses=0;binaries=0;duplicates=0;tautologies=0
    reason="complete"
    parts=windows(path)
    for index,(offset,block) in enumerate(parts):
        if time.perf_counter()-t0>MAX_GRAPH_PROBE_S:
            reason="budget_abstain";break
        parsed=parse_window_binary(block)
        clauses+=parsed["clauses"];binaries+=parsed["binaries"]
        duplicates+=parsed["duplicates"];tautologies+=parsed["tautologies"]
        for a,b in parsed["edges"]:
            if b not in adj[a]:
                adj[a].add(b);reverse[b].add(a);edges+=1
                if edges>MAX_EDGES:break
        if edges>MAX_EDGES:
            reason="edge_guard_abstain";break
        if time.perf_counter()-t0>MAX_GRAPH_PROBE_S:
            reason="budget_abstain";break
        snapshot=graph_snapshot(adj,reverse,edges)
        snapshot.update(window_index=index,byte_offset=offset,
                        clauses_seen=clauses,binary_clauses_seen=binaries)
        stages.append(snapshot)
    elapsed=time.perf_counter()-t0
    result=dict(
        reason=reason,graph_ready=(reason=="complete" and len(stages)==len(parts)),
        probe_s=round(elapsed,6),
        sampled_bytes=sum(len(x[1]) for x in parts),
        windows_expected=len(parts),
        windows_traversed=len(stages),
        source_bytes=pathlib.Path(path).stat().st_size,
        clauses_seen=clauses,binary_clauses_seen=binaries,
        duplicates_seen=duplicates,tautologies_seen=tautologies,
        snapshots=stages)
    if stages:
        last=stages[-1]
        result.update({name:last[name] for name in
            ("nodes","edges","scc_nontrivial","scc_cycle_nodes","scc_largest",
             "signed_aliases","alias_examples","contradictory_scc",
             "max_chain_depth","max_bounded_reachable","branching_paths")})
    else:
        result.update(nodes=0,edges=0,scc_nontrivial=0,scc_cycle_nodes=0,
            scc_largest=0,signed_aliases=0,alias_examples=[],
            contradictory_scc=0,max_chain_depth=0,
            max_bounded_reachable=0,branching_paths=0)
    return result

def decide(info,arm):
    need(arm in ("graph_scc","graph_frontier"),"invalid graph policy")
    if not info["graph_ready"] or info["contradictory_scc"]:
        return "race_original","graph_abstain"
    # These are real, sampled implication-graph paths, not a count of clauses.
    if info["signed_aliases"]>=1:
        return "race_quotient","sampled_signed_SCC_equivalence"
    if arm=="graph_frontier" and (
        (info["scc_nontrivial"]>=1 and info["max_chain_depth"]>=4) or
        (info["max_chain_depth"]>=5 and info["max_bounded_reachable"]>=20)):
        return "race_quotient","graph_reachability_frontier"
    return "race_original","no_graph_reduction_signal"

def verify():
    earlier=x22.verify_frozen()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["expected_trials"]==EXPECTED and len(m["cases"])==24,
         "manifest drift")
    need(m["code_sha256"]==digest(__file__) and
         m["x22_manifest_sha256"]==digest(x22.ROOT/"manifest.json"),
         "code/source manifest drift")
    need(m["x22_reference_report_sha256"]==digest("prior_x22/report.json"),
         "prior-X22 original-solver reference report changed")
    need([c["sha256"] for c in m["cases"]]==
         [c["sha256"] for c in earlier["cases"]],"source roster drift")
    return m

def freeze():
    prior=x22.verify_frozen()
    ROOT.mkdir(parents=True,exist_ok=True)
    m=dict(protocol=PROTO,arms=ARMS,source_count=24,
        expected_trials=EXPECTED,cap_s=CAP,reps=REPS,shards=SHARDS,
        cases=[{k:c[k] for k in ("filename","gbd","sha256","year")}
               for c in prior["cases"]],
        parent_x23_run=42593899719,parent_x22_run=42591977333,
        x22_manifest_sha256=digest(x22.ROOT/"manifest.json"),
        x22_reference_report_sha256=digest("prior_x22/report.json"),
        code_sha256=digest(__file__),
        policy_frozen_before_trails=True,
        windows=4,max_sample_bytes=MAX_WINDOW_BYTES,
        graph_probe_budget_s=MAX_GRAPH_PROBE_S,
        strict="run certified reducer only when sampled SCC has signed variable equality",
        frontier="run when signed SCC or graph cycle plus depth>=4, or depth>=5 and >=20 reachable",
        sampled_GRAPH_is_only_a_selector_not_a_proof=True,
        source_sha_unchanged=True,
        no_auto_promotion=True,not_new_blind_holdout=True,
        independent_UNSAT_LRAT=False,allowed_logical_cpus=2)
    save(ROOT/"manifest.json",m)
    verify()
    print("X23G_FROZEN",json.dumps(dict(sources=24,shards=SHARDS,
          trials=EXPECTED,arms=ARMS),sort_keys=True),flush=True)

def trial(case,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid trial")
    begun=time.perf_counter();cpu_before=x22.child_cpu()
    source=x22.ROOT/"cases"/case["filename"]
    need(digest(source)==case["sha256"],"original SHA mismatch")
    graph={};decision="control";route=arm
    if arm in ("graph_scc","graph_frontier"):
        graph=follow_binary_graph(source)
        route,decision=decide(graph,arm)
    elif arm in ("gate_strict","gate_liberal"):
        # Reuse X23 unchanged so count-only and graph selectors are causal controls.
        pass
    need(time.perf_counter()-begun<CAP,"graph probe exhausted cap")
    residual=CAP-(time.perf_counter()-begun)
    if arm in ("gate_strict","gate_liberal"):
        old=x23.CAP
        try:
            x23.CAP=residual
            result=x23.trial(case,rep,arm)
        finally:x23.CAP=old
        route=result["route"]
    else:
        old=x22.CAP
        try:
            x22.CAP=residual
            result=x22.trial(case,rep,route)
        finally:x22.CAP=old
    total=time.perf_counter()-begun
    status=result["status"] if total<=CAP else "TIMEOUT"
    return dict(protocol=PROTO,arm=arm,route=route,graph_decision=decision,
        original_sha256=case["sha256"],gbd=case["gbd"],rep=rep,
        seed=x22.seed(case,rep),status=status,
        SAT_original_witness_verified=(status=="SAT" and
                result.get("SAT_original_witness_verified",False)),
        UNSAT_independent_LRAT=False,
        winner=result.get("winner") if status!="TIMEOUT" else None,
        reducer=result.get("reducer",{}),
        aliases_replayed=result.get("aliases_replayed",0),
        graph=graph,
        graph_probe_s=graph.get("probe_s",0),
        E2E_s=round(total,6),
        child_cpu_s=round(x22.child_cpu()-cpu_before,6),
        PAR2_provisional_s=round(total if status in ("SAT","UNSAT") else 2*CAP,6),
        cap_s=CAP)

def shard(index):
    m=verify();need(0<=index<SHARDS,"shard")
    rows=[]
    for case in m["cases"][index::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(x22.seed(case,rep)).shuffle(arms)
            for arm in arms:
                row=trial(case,rep,arm);rows.append(row)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X23G_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==36,"shard incomplete")
    print("X23G_SHARD_PASS",index,len(rows),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        src=ROOT/("shard-%d.json"%i)
        need(src.exists(),"missing shard "+str(i))
        part=json.loads(src.read_text())
        need(len(part)==36,"shard row count")
        rows.extend(part)
    need(len(rows)==EXPECTED,"missing measurements")
    seen=set();by_sha=collections.defaultdict(list)
    for r in rows:
        k=(r["original_sha256"],r["rep"],r["arm"])
        need(k not in seen and r["protocol"]==PROTO and
             r["cap_s"]==CAP,"duplicate or invalid row")
        seen.add(k);by_sha[r["original_sha256"]].append(r)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"missing original witness")
    reference=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    originals=reference["confirmed_original_UNSAT"]
    need(set(originals)==set(by_sha),
         "X22 original-reference coverage incomplete")
    for sha,part in by_sha.items():
        statuses={r["status"] for r in part if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"solver SAT/UNSAT disagreement")
        if "SAT" in statuses:
            need(not originals[sha],"SAT contradicts X22 original UNSAT")
    scores={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and originals[r["original_sha256"]])]
        total=sum(r["E2E_s"] if r in accepted else 2*CAP for r in subset)
        scores[arm]=dict(n=len(subset),verified_sat=len(accepted),
          UNSAT_original_Kissat_CaDiCaL_agreement_no_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
          unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted for r in subset),
          PAR2_agreement_s=round(total,5),
          CPU_s=round(sum(r["child_cpu_s"] for r in subset),5),
          reducer_runs=sum(r["route"]=="race_quotient" for r in subset),
          early_fallbacks=sum(r["route"]=="race_original" for r in subset),
          graph_detected_aliases=sum(r["graph"].get("signed_aliases",0) for r in subset),
          actual_replayed_aliases=sum(r["aliases_replayed"] for r in subset),
          graph_probe_total_s=round(sum(r["graph_probe_s"] for r in subset),5))
    baseline=scores["race_original"]["PAR2_agreement_s"]
    for score in scores.values():
        score["delta_PAR2_vs_race_pct"]=round(
            100*(score["PAR2_agreement_s"]/baseline-1),4)
    report=dict(protocol=PROTO,source_count=24,total_trials=EXPECTED,
        scores=scores,source_sha_unchanged=True,not_blind=True,
        independent_UNSAT_LRAT=False,
        PAR2_accounting="SAT original-witness verified; UNSAT accepted only with pinned X22 original Kissat+CaDiCaL agreement, not LRAT",
        precursor_X23=42593899719,precursor_X22=42591977333)
    save(ROOT/"report.json",report)
    print("X23G_FINAL",json.dumps(scores,sort_keys=True),flush=True)

def selftest():
    import tempfile
    examples=[
      (2,[(-1,2),(1,-2)],1,True),
      (2,[(1,2),(-1,-2)],1,True),
      (3,[(-1,2),(-2,3),(-3,1)],2,True),
      (3,[(-1,2),(-2,3)],0,False),
      (3,[(1,2,3)],0,False),
      (2,[(1,2),(-1,-2),(1,-2),(-1,2)],0,False)]
    with tempfile.TemporaryDirectory() as tmp:
        file=pathlib.Path(tmp)/"test.cnf"
        for n,clauses,minimum,ready in examples:
            file.write_text("p cnf %d %d\n"%(n,len(clauses))+
              "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            before=digest(file);feature=follow_binary_graph(file)
            need(feature["graph_ready"],"toy graph budget")
            if minimum:
                need(feature["signed_aliases"]>=minimum,
                     "missed graph equivalence in toy test")
            else:
                need(feature["signed_aliases"]==0,"false graph equality")
            if ready:need(decide(feature,"graph_scc")[0]=="race_quotient",
                          "strict gate missed graph")
            need(digest(file)==before,"graph probe mutated CNF")
    print("X23G_SELFTEST_PASS",len(examples),
          "binary graph SCC and implication-chain cases",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    a=parser.parse_args()
    if a.action=="shard":shard(a.shard)
    else:globals()[a.action]()

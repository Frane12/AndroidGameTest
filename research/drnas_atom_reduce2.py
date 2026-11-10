#!/usr/bin/env python3
"""Offline diagnostic: actual implication reason-graph overlap and RUP validation.
Reason closure is NOT a proof that a shorter pre-CDCL derivation exists.
"""
import json
from collections import Counter,defaultdict
from pathlib import Path
from drnas_atom_reduce1 import rup

def audit(stderr, original_cnf, trace_file, output):
    graph=defaultdict(lambda:dict(nodes={},edges=[]))
    for line in stderr.splitlines():
        if line.startswith("REDUCE2_NODE "):
            x=dict(p.split("=",1) for p in line.split()[1:])
            number=int(x["conflict"]);cid=int(x["cid"])
            graph[number]["nodes"][cid]=dict(cid=cid,learned=bool(int(x["learned"])),
                                              lits=[int(v) for v in x["clause"].split(",")])
        elif line.startswith("REDUCE2_EDGE "):
            x=dict(p.split("=",1) for p in line.split()[1:])
            graph[int(x["conflict"])]["edges"].append(dict(
                from_cid=int(x["from"]),to_cid=int(x["to"]),variable=int(x["var"])))
    assert graph,"no reason graphs recorded"
    original=[]
    for line in Path(original_cnf).read_text().splitlines():
        if not line or line.startswith(("p","c","%")):continue
        lits=[int(v) for v in line.split()];assert lits[-1]==0
        original.append(lits[:-1])
    learn=[]
    for line in Path(trace_file).read_text().splitlines():
        if "kind=learn " in line:
            x=dict(p.split("=",1) for p in line.split()[1:])
            learn.append([int(v) for v in x["clause"].split(",")])
    windows=[]
    for number,record in sorted(graph.items()):
        nodes=record["nodes"]
        origins=sorted(cid for cid,v in nodes.items() if not v["learned"])
        learned_ids=sorted(cid for cid,v in nodes.items() if v["learned"])
        variables=sorted({e["variable"] for e in record["edges"]})
        # Index IDs in original CNF can differ due to tautology/duplicate normalization.
        windows.append(dict(conflict=number,reason_nodes=len(nodes),reason_edges=len(record["edges"]),
            original_cids=origins,learned_cids=learned_ids,reason_variables=variables))
    focus=[x for x in windows if 16<=x["conflict"]<=20]
    if len(learn)>=20:assert len(focus)==5,"missing complete 16-20 window"
    original_sets=[set(x["original_cids"]) for x in focus]
    common=sorted(set.intersection(*original_sets)) if original_sets else []
    count=Counter(cid for x in focus for cid in x["original_cids"])
    common_variables=sorted(set.intersection(*(set(x["reason_variables"]) for x in focus))) if focus else []
    # Independently verify learned assertions by UP from ORIGINAL plus earlier learned clauses.
    # This is stronger evidence than simply assuming the instrumented trail is correct.
    rup_rows=[]
    for i,cl in enumerate(learn):
        valid=rup(original+learn[:i],cl)
        rup_rows.append(dict(conflict=i+1,width=len(cl),rup_original_plus_prefix=valid))
    result=dict(
        source_trace=str(trace_file),graph_count=len(windows),
        conflict_windows=windows,focus_16_20=dict(
            count=len(focus),shared_original_cids=common,
            frequent_original_cids=sorted(count.items(),key=lambda a:(-a[1],a[0]))[:20],
            shared_reason_variables=common_variables,
            original_reason_union=len(set.union(*original_sets)) if original_sets else 0),
        learned_rup=dict(checked=len(rup_rows),verified=sum(x["rup_original_plus_prefix"] for x in rup_rows),
                         failures=[x for x in rup_rows if not x["rup_original_plus_prefix"]]),
        learned_rows=rup_rows,
        note="Graph overlap is descriptive only; no earlier implication or reduced search is claimed.")
    Path(output).write_text(json.dumps(result,sort_keys=True,indent=2))
    return result

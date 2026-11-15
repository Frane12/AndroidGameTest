#!/usr/bin/env python3
"""Input-only structural autopsy of frozen original SAT2026 CNFs.

No labels, original solving, or SAT/UNSAT conclusions are used in detection.
Counts are exact where so marked; mutex clique examples are only heuristic.
"""
import collections
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MAX_CLAUSES = 2_500_000
MAX_CNF_BYTES = 60_000_000
MAX_CANDIDATES = 150_000
MAX_CANDIDATE_WIDTH = 128

def read_stats(path):
    started = time.perf_counter()
    raw_size = path.stat().st_size
    if raw_size > MAX_CNF_BYTES:
        return dict(status="FILE_GATE", bytes=raw_size)
    total_vars = clause_target = None
    nclauses = 0
    widths = collections.Counter()
    shapes = collections.Counter()
    unit_pos = unit_neg = 0
    signs = collections.Counter()
    occ = collections.Counter()
    negative_binary = set()
    positive_groups = set()
    possible_amo_more = collections.Counter()
    allnegative_long = 0
    nonhorn = 0
    largest = 0
    multi_line_clauses = 0
    pending = []
    hash256 = hashlib.sha256()
    # Read in binary so the exact source hash is preserved.
    with path.open("rb") as fd:
        for raw in fd:
            hash256.update(raw)
            line = raw.strip()
            if not line or line.startswith(b"c") or line.startswith(b"%"):
                continue
            if line.startswith(b"p"):
                header=line.split()
                if len(header)!=4 or header[1]!=b"cnf" or total_vars is not None:
                    raise ValueError("invalid_DIMACS_header")
                total_vars=int(header[2]);clause_target=int(header[3])
                if clause_target > MAX_CLAUSES:
                    return dict(status="CLAUSE_GATE", bytes=raw_size,
                                variables=total_vars, declared_clauses=clause_target)
                continue
            if total_vars is None:
                raise ValueError("DIMACS_clauses_precede_header")
            for piece in line.split():
                lit=int(piece)
                if lit:
                    if abs(lit)>total_vars:raise ValueError("out_of_range")
                    pending.append(lit)
                else:
                    if not pending:
                        widths[0]+=1
                    else:
                        c=pending
                        pending=[]
                        nclauses+=1
                        if nclauses>MAX_CLAUSES:raise ValueError("too_many_clauses")
                        n=len(c);largest=max(n,largest)
                        widths[n if n<=12 else "13+"]+=1
                        pos=sum(x>0 for x in c)
                        neg=n-pos
                        nonhorn+=(pos>1)
                        key = ("P" if pos else "N" if neg else "E", n) if pos in (0,n) else ("M",n,pos)
                        if n<=3:shapes[str(key)]+=1
                        if n==1:
                            if pos:unit_pos+=1
                            else:unit_neg+=1
                        if n==2:
                            signs[("pospos" if pos==2 else "negneg" if pos==0 else "mixed")]+=1
                            if pos==0 and c[0]!=c[1]:
                                a,b=sorted((-c[0],-c[1]))
                                negative_binary.add((a,b))
                        if pos==n and 2<=n<=MAX_CANDIDATE_WIDTH and len(set(c))==n:
                            if len(positive_groups)<MAX_CANDIDATES:
                                positive_groups.add(tuple(sorted(c)))
                        if pos==0 and n>=3:allnegative_long+=1
                        if n==3:
                            possible_amo_more[("three_neg" if pos==0 else
                                               "horn3" if pos==1 else
                                               "atleast2pos3" if pos==2 else
                                               "positive3")]+=1
                        for lit in c:occ[abs(lit)]+=1
        if pending:raise ValueError("unterminated_dimacs_clause")
    if total_vars is None or clause_target is None or nclauses!=clause_target:
        raise ValueError("header_clause_count_mismatch")
    # Original positive clauses are At-Least-One. We only infer an Exactly-One
    # group when ALL corresponding pairwise negative binary clauses exist.
    exact_one=[]
    partial=[]
    by_size=collections.Counter()
    for group in sorted(positive_groups,key=lambda a:(-len(a),a)):
        by_size[len(group)]+=1
        pairs=len(group)*(len(group)-1)//2
        covered=sum((group[i],group[j]) in negative_binary
                    for i in range(len(group))
                    for j in range(i+1,len(group)))
        if covered==pairs:
            exact_one.append(group)
        elif covered:
            partial.append((len(group),covered,pairs))
    covered_vars=set(x for grp in exact_one for x in grp)
    group_members=collections.Counter(v for grp in exact_one for v in grp)
    overlaps=sum(val>1 for val in group_members.values())
    # Greedy mutex cliques: descriptive only; not a validity witness.
    graph=collections.defaultdict(set)
    for a,b in negative_binary:
        graph[a].add(b);graph[b].add(a)
    seeds=sorted(graph,key=lambda a:(-len(graph[a]),a))[:min(200,len(graph))]
    clique_samples=set()
    for seed in seeds:
        clique=[seed]
        remaining=set(graph[seed])
        while remaining:
            chosen=max(remaining,key=lambda v:(len(graph[v]&remaining),-v))
            clique.append(chosen)
            remaining.intersection_update(graph[chosen])
            if len(clique)>=128:break
        if len(clique)>=3:
            clique_samples.add(tuple(sorted(clique)))
    cliques=sorted(clique_samples,key=lambda a:(-len(a),a))
    top_var=occ.most_common(8)
    return dict(
        status="ANALYZED",bytes=raw_size,sha256=hash256.hexdigest(),
        variables=total_vars,clauses=nclauses,max_clause_width=largest,
        widths={str(k):v for k,v in widths.items()},
        n_positive_units=unit_pos,n_negative_units=unit_neg,
        n_nonhorn_clauses=nonhorn,
        binary_types=dict(signs),
        neg_binary_mutex_pairs=len(negative_binary),
        n_allnegative_clauses_width_ge3=allnegative_long,
        n_all_positive_alo_candidates=len(positive_groups),
        alo_group_size_hist={str(k):v for k,v in by_size.items()},
        fully_pairwise_amo_supported_alo_count=len(exact_one),
        exactly_one_group_size_hist=dict(collections.Counter(map(str,map(len,exact_one)))),
        exactly_one_covered_vars=len(covered_vars),
        exactly_one_overlap_variables=overlaps,
        exact_one_examples=[list(x) for x in exact_one[:5]],
        partial_mutex_candidate_count=len(partial),
        partial_mutex_examples=[list(x) for x in sorted(partial,reverse=True)[:5]],
        detected_mutex_clique_count_heuristic=len(cliques),
        mutex_clique_largest=len(cliques[0]) if cliques else 0,
        mutex_clique_samples_heuristic=[list(x[:20]) for x in cliques[:5]],
        ternary_shapes=dict(possible_amo_more),
        highest_occurrence_vars=top_var,
        scan_s=round(time.perf_counter()-started,4))

def main():
    if len(sys.argv)!=3:
        raise SystemExit("usage: structural_autopsy_real26.py ARTIFACT_DIR OUTPUT_DIR")
    root=Path(sys.argv[1])
    output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    reports=list(root.rglob("summary.json"))
    if len(reports)!=4:
        raise SystemExit("Expected 4 original frozen report manifests, got "+str(len(reports)))
    for report in sorted(reports):
        data=json.loads(report.read_text())
        for case in data["cases"]:
            key=case["md5"]
            candidates=list(report.parent.rglob("*"+key+".cnf"))
            if case["input_status"]!="RETRIEVED":
                row=dict(md5=key,status="SOURCE_FAILED",family=case["family"])
            elif not candidates:
                row=dict(md5=key,status="SOURCE_NOT_ARCHIVED",family=case["family"],
                         original_variables=case.get("variables"),
                         original_clauses=case.get("clauses"))
            else:
                assert len(candidates)==1,(key,candidates)
                path=candidates[0]
                try:
                    features=read_stats(path)
                    if features["status"]=="ANALYZED":
                        if features["sha256"]!=case["source_sha256"]:
                            raise AssertionError("SOURCE_SHA256_MISMATCH")
                        assert features["variables"]==case["variables"]
                        assert features["clauses"]==case["clauses"]
                    row=dict(md5=key,family=case["family"],label_for_reporting=case["label"],
                             **features)
                except Exception as err:
                    row=dict(md5=key,family=case["family"],status="ANALYSIS_ERROR",error=str(err))
            rows.append(row)
            print("AUTOPSY_CASE "+json.dumps({k:row.get(k) for k in
                   ("md5","family","status","variables","clauses",
                    "neg_binary_mutex_pairs","n_all_positive_alo_candidates",
                    "fully_pairwise_amo_supported_alo_count","mutex_clique_largest",
                    "n_nonhorn_clauses")},sort_keys=True),flush=True)
    rows.sort(key=lambda r:r["md5"])
    (output/"results.json").write_text(json.dumps(rows,indent=2)+"\n")
    summary={
        "total_originals":len(rows),
        "analyzed":sum(x["status"]=="ANALYZED" for x in rows),
        "not_archived":sum(x["status"]=="SOURCE_NOT_ARCHIVED" for x in rows),
        "source_failed":sum(x["status"]=="SOURCE_FAILED" for x in rows),
        "errors":sum(x["status"]=="ANALYSIS_ERROR" for x in rows),
        "with_alo":sum(x.get("n_all_positive_alo_candidates",0)>0 for x in rows),
        "with_pairwise_exactone":sum(x.get("fully_pairwise_amo_supported_alo_count",0)>0 for x in rows)
    }
    (output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("AUTOPSY_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)
    if summary["errors"] or summary["source_failed"] or summary["total_originals"]!=16:
        raise SystemExit("Input or autopsy audit failed")

if __name__=="__main__":main()

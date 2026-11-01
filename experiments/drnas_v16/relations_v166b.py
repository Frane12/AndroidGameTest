#!/usr/bin/env python3
"""DRNAS SAT V16.6b: CNF relation extractor and FROZEN exploratory policy.

No solver calls, filenames, seed identifiers, labels, runtime, or answer
information are inputs to the selector. All features use original DIMACS.

Signed 4-cycle: two clauses both contain a pair of variables. Each occurrence
induces a parity bit from their literal signs; opposite bits are called
"frustrated" for this graph statistic only (NOT a logical contradiction).
This is a diagnostic/topological descriptor, not a proof of SAT/UNSAT.

The thresholds below were chosen by observing the earlier V16.5 seed
165000/165001/165004/165005 results. These examples are DEVELOPMENT data,
not blind evidence. Do not update thresholds after V16.6b blind results.
"""
from collections import defaultdict
from pathlib import Path
import math

FROZEN_POLICY = "v166b-signed-cycles-20261101-pre-holdout"

def features(path):
    nvars = declared = None
    clauses = 0
    tri = 0
    binary = 0
    pos = neg = 0
    degrees = []
    positive = []
    negative = []
    pairs = defaultdict(lambda: [0, 0])
    current = []
    with Path(path).open(encoding="ascii") as source:
        for line in source:
            line = line.strip()
            if not line or line.startswith("c") or line.startswith("%"):
                continue
            if line.startswith("p "):
                parts = line.split()
                if nvars is not None or len(parts)!=4 or parts[1]!="cnf":
                    raise ValueError("invalid DIMACS header")
                nvars, declared = int(parts[2]), int(parts[3])
                if nvars<1 or declared<0 or nvars>1000000:
                    raise ValueError("invalid DIMACS size")
                degrees=[0]*(nvars+1)
                positive=[0]*(nvars+1)
                negative=[0]*(nvars+1)
                continue
            if nvars is None:raise ValueError("missing header")
            for item in line.split():
                x=int(item)
                if x:
                    if abs(x)>nvars:raise ValueError("literal out of range")
                    current.append(x)
                else:
                    clauses+=1
                    tri+=len(current)==3
                    binary+=len(current)==2
                    for lit in current:
                        v=abs(lit)
                        degrees[v]+=1
                        if lit>0:
                            positive[v]+=1;pos+=1
                        else:
                            negative[v]+=1;neg+=1
                    # Count signed repeated pairs on clauses of width 2..5.
                    # Larger clauses are ignored to bound cost.
                    if 2<=len(current)<=5:
                        for i in range(len(current)):
                            a=current[i]
                            for j in range(i+1,len(current)):
                                b=current[j]
                                if abs(a)==abs(b):continue
                                lo,hi=sorted((abs(a),abs(b)))
                                parity=int((a<0) != (b<0))
                                pairs[(lo,hi)][parity]+=1
                    current=[]
                    if clauses>declared:raise ValueError("too many clauses")
    if nvars is None or current or clauses!=declared:
        raise ValueError("invalid DIMACS clause count")
    m=sum(degrees[1:])/nvars
    cv=math.sqrt(sum((x-m)**2 for x in degrees[1:])/nvars)/m if m else 0.
    imbalance=sum(abs(positive[i]-negative[i]) for i in range(1,nvars+1))
    local_skew=sum((abs(positive[i]-negative[i])/degrees[i] if degrees[i] else 0.)
                   for i in range(1,nvars+1))/nvars
    repeated=0
    frustrated=0
    same=0
    for even,odd in pairs.values():
        if even+odd<2:continue
        repeated+=1
        same+=even*(even-1)//2+odd*(odd-1)//2
        frustrated+=even*odd
    total=frustrated+same
    return {
        "nvars":nvars,"nclauses":clauses,
        "density":clauses/nvars,
        "three_fraction":tri/max(1,clauses),
        "binary_fraction":binary/max(1,clauses),
        "degree_cv":cv,
        "polarity_balance":1.0-abs(pos-neg)/max(1,pos+neg),
        "local_polarity_skew":local_skew,
        "signed_cycle_frustration":frustrated/total if total else 0.,
        "signed_cycle_count":total,
        "repeated_pair_rate":repeated/max(1,clauses),
        "repeated_pairs":repeated,
        "frustrated_cycles":frustrated,
        "consistent_cycles":same,
    }

def choose(f):
    # Scientific baseline: do not classify satisfiable or UNSAT.
    # A signal only selects an upstream Kissat configuration.
    if not (f["nvars"]>=320 and f["nclauses"]>=1000
            and 4.10<=f["density"]<=4.42
            and f["three_fraction"]>=.995
            and f["degree_cv"]<=.50
            and f["polarity_balance"]>=.90
            and f["signed_cycle_count"]>=40):
        return ()
    high_frustration=(
        f["signed_cycle_frustration"]>=.515
        and f["local_polarity_skew"]<=.232
        and f["repeated_pair_rate"]>=.050
    )
    low_frustration_sparse_repetition=(
        f["signed_cycle_frustration"]<=.49
        and .065<=f["repeated_pair_rate"]<=.080
    )
    return ("--sat",) if high_frustration or low_frustration_sparse_repetition else ()

def report(f):
    return {
      "density":round(f["density"],6),
      "degree_cv":round(f["degree_cv"],6),
      "signed_cycle_frustration":round(f["signed_cycle_frustration"],6),
      "local_polarity_skew":round(f["local_polarity_skew"],6),
      "repeated_pair_rate":round(f["repeated_pair_rate"],6),
      "signed_cycle_count":f["signed_cycle_count"],
    }

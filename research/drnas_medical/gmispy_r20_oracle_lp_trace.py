#!/usr/bin/env python3
"""R20: identify exact independent FBA oracle LP responsible for R19 384 stall.

Instrumentation only. All frozen source, R16 solver arms and biological
reference, gene/reaction knockout operations are unchanged.
"""
from __future__ import annotations
import json
import pathlib
import sys
import time
from unittest.mock import patch

import gmispy_r9_scaling as r9
import gmispy_r19_postsolve_trace as r19

ORIGINAL_GROWTH = r9.growth
TOTAL = 0
TRACE_PATH = None
LAST = []


def mark(phase, **values):
    event = {"phase":phase, "seq":TOTAL, "when_s":round(time.perf_counter(),6), **values}
    print("R20_LP " + json.dumps(event,sort_keys=True),flush=True)
    LAST.append(event)
    if len(LAST)>20:
        del LAST[:-20]
    if TRACE_PATH is not None:
        pathlib.Path(TRACE_PATH).write_text(
            json.dumps({"protocol":"R20-INDEPENDENT-ORACLE-PER-LP-v1",
                        "last":LAST,"latest":event},indent=2,sort_keys=True)+"\n")


def traced_growth(model,genes,combo,rules,how):
    global TOTAL
    TOTAL += 1
    chosen=tuple(genes[i] for i in combo)
    mark("enter",how=how,ko=list(chosen),n=len(genes))
    tick=time.perf_counter()
    try:
        value=ORIGINAL_GROWTH(model,genes,combo,rules,how)
    except BaseException as exc:
        mark("exception",how=how,ko=list(chosen),error=repr(exc))
        raise
    mark("exit",how=how,ko=list(chosen),seconds=round(time.perf_counter()-tick,6),
         value=round(float(value),9))
    return value


if __name__=="__main__":
    # Reuse R19's fully auditable setup and exact R16 trial, adding per-LP
    # instrumentation solely inside R9's independent biological verifier.
    global_args = __import__("argparse").ArgumentParser()
    for field in ("source","frozen","reference","arm","out"):
        global_args.add_argument("--"+field,required=True)
    global_args.add_argument("--n",type=int,choices=(384,),required=True)
    args=global_args.parse_args()
    if args.arm not in ("r9_baseline","share_12_control","share_12_memo_k3"):
        raise ValueError("unsupported arm")
    TRACE_PATH = args.out.replace(".json","-lp.json")
    pathlib.Path(TRACE_PATH).parent.mkdir(parents=True,exist_ok=True)
    with patch.object(r9,"growth",traced_growth):
        r19.run(args)
    print("R20_COMPLETE "+json.dumps({"arm":args.arm,"n":args.n,
                                     "independent_lp_checks":TOTAL}),flush=True)

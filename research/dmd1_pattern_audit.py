#!/usr/bin/env python3
"""Diagnostic-only histogram of degree-2 ANF basis patterns from frozen DMD1
original CNFs, without performing any SAT benchmark or modifying DMD1.
Counts are LOCAL BASIS VECTORS, not unique global equations.
"""
from __future__ import annotations
import collections
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, "research")
import dmd1_bench as dmd
ROOT=pathlib.Path("mre_dmd1pattern")
SOURCE=pathlib.Path("mre_equiv7")
BIN=ROOT/"bin/dmd1_pattern_profile"
BUDGET_MS=200
GROUPS=48

def need(ok,reason):
    if not ok:raise RuntimeError("DMD1_PATTERN_AUDIT_FAIL "+str(reason))
def sha(file):
    return hashlib.sha256(pathlib.Path(file).read_bytes()).hexdigest()
def main():
    m=json.loads((SOURCE/"manifest.json").read_text())
    need(len(m["cases"])==48 and m["sample_policy"].startswith("SHA-salted official"),
         "frozen EQUIV7 source registry changed")
    samples=sorted(m["cases"],key=lambda x:x["sha256"])[:24]
    need(len(samples)==24 and len({c["sha256"] for c in samples})==24,
         "training cohort drift")
    need(BIN.is_file(),"profile executable missing")
    shape2=collections.Counter()
    shape1=collections.Counter()
    coverage2=collections.Counter()
    length=collections.Counter()
    example={}
    per_source=[]
    total=collections.Counter()
    for case in samples:
        source=SOURCE/"cases"/case["filename"]
        need(source.is_file() and sha(source)==case["sha256"],
             "original SHA mismatch")
        with tempfile.TemporaryDirectory(prefix="dmd1pattern-") as td:
            t=pathlib.Path(td)
            r=subprocess.run([str(BIN),str(source),str(t/"aug.cnf"),str(t/"proof.json"),
                        str(BUDGET_MS),str(GROUPS)],capture_output=True,text=True,
                        timeout=30)
            need(r.returncode==0,"native profile failed "+r.stderr[-500:])
            line=next((x[len("DMD1_PATTERN "):]
                 for x in r.stdout.splitlines() if x.startswith("DMD1_PATTERN ")),None)
            need(line is not None,"pattern payload missing")
            z=json.loads(line)
            proof=json.loads((t/"proof.json").read_text())
            dmd.proof_replay(source,t/"aug.cnf",proof)
            need(z["groups"]==proof["groups"] and
                 z["nonlinear_relations"]==proof["nonlinear_relations"],"counter mismatch")
            need(sum(z["degree2_shapes"].values())==z["nonlinear_relations"],
                 "degree2 sum not equal nonlinear counter")
            need(sum(z["lemma_length"].values())==len(proof["lemmas"]),
                 "lemma length mismatch")
            shape2.update(z["degree2_shapes"])
            shape1.update(z["degree1_shapes"])
            coverage2.update(k for k,v in z["degree2_shapes"].items() if v>0)
            length.update(z["lemma_length"])
            for k,v in z["examples"].items():
                example.setdefault(k,v)
            for k in ("n2_linear_terms","n2_quadratic_terms","n2_constant_terms",
                      "implied_units_false","implied_units_true","implied_equalities",
                      "implied_inequalities","groups","nonlinear_relations"):
                total[k]+=z[k]
            per_source.append(dict(original_file=case["filename"],sha256=case["sha256"],
               groups=z["groups"],nonlinear=z["nonlinear_relations"],
               lemmas=len(proof["lemmas"]),degree2_shape_count=len(z["degree2_shapes"]),
               degree2_shapes=z["degree2_shapes"],degree1_shapes=z["degree1_shapes"],
               lemma_lengths=z["lemma_length"],
               budget_exhausted=bool(proof["timed_out"]),
               source_only=True))
            print("DMD1_PATTERN_SOURCE",json.dumps(dict(file=case["filename"],
                 shapes=z["degree2_shapes"],lemmas=len(proof["lemmas"]),
                 linear_shapes=z["degree1_shapes"]),sort_keys=True),flush=True)
    most=shape2.most_common(25)
    report=dict(protocol="DRNAS-DMD1-STRUCTURAL-BASIS-HISTOGRAM-24-OLD-CNF-v1",
       original_sources=24,source_cohort="reused_equiv7_original",
       diagnostic_only_no_backend_solve=True,
       not_blind=True,
       soft_budget_ms=BUDGET_MS,max_groups=GROUPS,
       original_CNF_SHA_verified=True,
       local_implication_proof_replayed=True,
       caveat="counts are sampled local GF2 nullspace BASIS vectors; basis depends on monomial ordering; they are not globally unique identities, are not direct solver speedups",
       degree2_total=sum(shape2.values()),
       degree2_shapes=dict(shape2.most_common()),
       degree1_total=sum(shape1.values()),
       degree1_shapes=dict(shape1.most_common()),
       degree2_source_coverage=dict(coverage2),
       example_equation_by_shape=example,
       lemma_length=dict(length),
       total=dict(total),
       per_source=per_source)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"profile_report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    summary={k:v for k,v in report.items() if k!="per_source"}
    summary["degree2_shapes"]=dict(most)
    print("DMD1_PATTERN_FINAL",json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":
    main()

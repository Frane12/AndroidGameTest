#!/usr/bin/env python3
"""Source-only argumentation CNF fingerprint audit (NO solver, NO outcomes).
Uses SAME frozen 11 original SAT2025 GBD source files; counts clause shapes.
"""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"arg3_realarg_inputs"
OUT=ROOT/"arg3_shape_results"
FROZEN_SHA="8fe5ccfb1a05557bdbf43b8b801d8cbdb5160aff988d0956ded3904c1d8a70d8"
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def main():
    m=SOURCE/"manifest.json"
    assert digest(m)==FROZEN_SHA
    manifest=json.loads(m.read_text())
    assert manifest["ready_count"]==11
    rows=[]
    for s in manifest["ready_sources"]:
        path=ROOT/s["path"]
        assert digest(path)==s["sha256"]
        widths=collections.Counter()
        positive3=units=negativebinary=mixedbinary=0
        clauses=0
        with path.open() as f:
            for line in f:
                a=line.split()
                if not a or a[0] in ("c","p","%"):continue
                literals=[int(x) for x in a if x!="0"]
                width=len(literals)
                clauses+=1;widths[width]+=1
                if width==1:units+=1
                if width==3 and all(l>0 for l in literals):positive3+=1
                if width==2:
                    if all(l<0 for l in literals):negativebinary+=1
                    elif (literals[0]>0)!=(literals[1]>0):mixedbinary+=1
        assert clauses==s["clauses"]
        n=s["vars"]
        triples=n//3 if n%3==0 else None
        gate512=n%3==0 and n>=24 and n<=1536 and clauses>=2*n and clauses<=110000
        gate1024=n%3==0 and n>=24 and n<=3072 and clauses>=2*n and clauses<=110000
        same_source_triple_pattern=(triples is not None and positive3==triples
                                    and units==0)
        rows.append(dict(gbd=s["gbd"],source_sha256=s["sha256"],
            vars=n,clauses=clauses,unit_clauses=units,
            positive_exactone_triples=positive3,
            argument_triples_expected=triples,
            missing_triples=None if triples is None else triples-positive3,
            negative_binary=negativebinary,mixed_binary=mixedbinary,
            width_profile=dict(widths),size_gate512=gate512,
            size_gate1024=gate1024,exact_unsimplified_ARG3_pattern=same_source_triple_pattern))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"shape.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    summary=dict(sources=len(rows),eligible_by_512_size=sum(r["size_gate512"] for r in rows),
         eligible_by_1024_size=sum(r["size_gate1024"] for r in rows),
         unsimplified_ARG3_schema_hits=sum(r["exact_unsimplified_ARG3_pattern"] for r in rows),
         with_root_units=sum(r["unit_clauses"]>0 for r in rows),
         zero_false_verdicts_by_construction=True,
         limitations="Static shape is not SAT/UNSAT result. Incomplete ALO may reflect preprocessing or different encoding.")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("ARG3_SOURCE_SHAPE_AUDIT "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()

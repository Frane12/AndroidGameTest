#!/usr/bin/env python3
"""R50 audit: source-order sensitivity of R47 certified resolution candidates.

Original SATComp26 CNFs remain byte-identical. The R47 extractor chooses
the FIRST 60k eligible clauses; compare that choice against the LAST 60k
and a deterministically seeded UNIFORM reservoir of 60k without altering
any solver binary or formula. For EVERY proposed alternative clause,
re-run the existing independent exhaustive original-clause certificate.
No benchmarking or blind generalization claims.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, random
from pathlib import Path
import r47_partial_links as r47
import r46_local_certified_links as r46
import r49_pivot_coherence_gate as r49
import r48_causal_clause_dose as r48

PROTO="DRNAS-R50-CERTIFIED-SAMPLE-ORDER-INVARIANCE-20261103-v1"
SEED_TAG="R50-frozen-uniform-sampler-v1"
SAMPLE_SIZE=60000

def check(condition,msg):
    if not condition: raise RuntimeError("R50_AUDIT_FAIL "+str(msg))
def sha_bytes(blob):
    return hashlib.sha256(blob).hexdigest()
def sha_file(p):
    return r48.sha(p)

def three_samples(path,case):
    # Exactly matches original R47 eligibility and line continuation rules.
    maxsize=r47.MAX_FILE_BYTES
    check(path.stat().st_size<=maxsize,"source exceeds R47 safety bound")
    seed=int(sha_bytes((case["sha256"]+SEED_TAG).encode()),16)
    rng=random.Random(seed)
    first=[];reservoir=[];last=collections.deque(maxlen=SAMPLE_SIZE)
    header=None;current=[];wide=False;clause_count=0;eligible=0
    with path.open("r",encoding="ascii",errors="strict") as stream:
        for raw in stream:
            line=raw.strip()
            if not line or line.startswith(("c","%")): continue
            if line.startswith("p "):
                fields=line.split()
                check(header is None and len(fields)==4 and
                      fields[:2]==["p","cnf"],"bad DIMACS source header")
                header=(int(fields[2]),int(fields[3]))
                continue
            check(header is not None,"clause before header")
            for token in line.split():
                lit=int(token)
                if lit:
                    check(abs(lit)<=header[0],"out-of-bound variable")
                    if len(current)<4:current.append(lit)
                    else:wide=True
                else:
                    clause_count+=1
                    if not wide and 1<=len(current)<=4 and (
                       len({abs(v) for v in current})==len(current)):
                        item=(eligible,tuple(current))
                        if len(first)<SAMPLE_SIZE:first.append(item)
                        if len(reservoir)<SAMPLE_SIZE:reservoir.append(item)
                        else:
                            draw=rng.randrange(eligible+1)
                            if draw<SAMPLE_SIZE:reservoir[draw]=item
                        last.append(item)
                        eligible+=1
                    current=[];wide=False
    check(header is not None and clause_count==header[1]
          and not current and not wide,"source clause count mismatch")
    samples={
        "first":first,
        "uniform":sorted(reservoir,key=lambda x:x[0]),
        "last":list(last)
    }
    return header,eligible,samples,seed

def derive_and_certify(path,source,mode,selected):
    # Only the sampling stage is replaced. The candidate extraction
    # and mathematical proof code is the UNMODIFIED R47 implementation.
    old=r47.sample_original
    sampled=[item[1] for item in selected]
    try:
        r47.sample_original=lambda _: (
            source[0],sampled,dict(reason=mode,sampled=len(sampled),
                original_clauses=source[1],original_vars=source[0]))
        new,proofs,trace=r47.derive_partial(path)
    finally:
        r47.sample_original=old
    check(len(new)==len(proofs),"candidate vs witness count")
    for clause,proof in zip(new,proofs):
        parents=[sampled[i] for i in proof["parent_ids"]]
        check(tuple(clause)==tuple(proof["clause"])
          and r46.certifies(parents,clause,proof["support"]),
          "candidate fails independent exhaustive original-clause certificate")
    pivot=collections.Counter(p["pivot"] for p in proofs)
    dominant=pivot.most_common(1)[0] if pivot else (None,0)
    gate=(len(new)>=r49.GATE_MIN_DERIVED and
          dominant[1]/len(new)>=r49.GATE_MIN_DOMINANCE) if new else False
    return dict(derived=len(new),certified=len(proofs),
      top_pivot=dominant[0],top_count=dominant[1],
      pivot_count=len(pivot),
      dominance=round(dominant[1]/len(new),8) if new else 0.,
      gate=gate,proof_source="original_CNF_clause_subset_exhaustive",
      sample_clause_count=len(sampled),
      sample_sha256=sha_bytes(json.dumps(sampled,separators=(",",":")).encode()),
      candidate_clause_sha256=r48.canon_clauses(new),
      sampled_index_first=selected[0][0] if selected else None,
      sampled_index_last=selected[-1][0] if selected else None,
      trace=trace)

def main(args):
    root=Path(args.frozen)
    m=r49.cases(root)
    design=json.loads(Path(args.design).read_text())
    check(design["protocol"]==r49.PROTO
      and design["manifest_sha256"]==sha_file(root/"manifest.json"),
      "R49 precommitted design mismatch")
    records=[]
    for c in m["cases"]:
        path=root/c["name"]
        check(sha_file(path)==c["sha256"],"original CNF SHA changed")
        header,eligible,samples,seed=three_samples(path,c)
        frozen=design["cases"][c["name"]]
        for mode in ("first","uniform","last"):
            result=derive_and_certify(path,header,mode,samples[mode])
            if mode=="first":
                check(result["derived"]==frozen["derived"]
                  and result["pivot_count"]==len(frozen["pivots"])
                  and result["top_count"]==frozen["top_count"]
                  and result["gate"]==frozen["gate"]
                  and result["candidate_clause_sha256"]==frozen["certificate_sha256"],
                  "R50 first sampler does not reproduce the frozen R49 evidence")
            row=dict(source_name=c["name"],source_sha256=c["sha256"],
                gbd=c["gbd"],cohort=frozen["cohort"],
                original_variables=header[0],
                original_clauses=header[1],eligible_short_clauses=eligible,
                sample=mode,seed=str(seed),
                eligible_coverage=round(min(SAMPLE_SIZE,eligible)/eligible,8)
                    if eligible else 0.,**result)
            records.append(row)
            print("R50_CERTIFIED_SAMPLER",c["gbd"],mode,
                  "certified",result["derived"],"top",
                  result["top_count"],"pivot_fraction",
                  result["dominance"],"gate",result["gate"],flush=True)
    check(len(records)==24
       and all(r["derived"]==r["certified"] for r in records),
       "incomplete candidate certificate audit")
    by=collections.defaultdict(dict)
    for r in records:by[r["gbd"]][r["sample"]]=r
    sensitive=[gbd for gbd,v in by.items()
        if len({(r["derived"],r["dominance"],r["gate"],
                 r["candidate_clause_sha256"]) for r in v.values()})>1]
    gate_changed=[gbd for gbd,v in by.items()
       if len({r["gate"] for r in v.values()})>1]
    report=dict(protocol=PROTO,source_run=41669951007,
      preregistered_R49_run=41676249421,
      source_manifest_sha256=sha_file(root/"manifest.json"),
      frozen_R49_design_sha256=sha_file(args.design),
      formula_count=len(by),sampled_evidence_rows=len(records),
      independently_certified_candidate_count=sum(r["certified"] for r in records),
      sensitive_source_count=len(sensitive),
      sensitive_original_gbd=sensitive,
      changed_gate_count=len(gate_changed),
      changed_gate_gbd=gate_changed,
      records=records,
      warnings=[
       "Same 8 previously seen SATComp26 CNFs, no novel official holdout",
       "Changing sampling changes mathematical candidate discovery but not original CNF",
       "Uniform reservoir is not globally complete structure discovery",
       "No actual solver speed measurements; do not claim any speedup",
       "First sample agrees exactly with the previously frozen R49 design",
       "All accepted alternative candidates have original-clause certificates",
       "The method is not globally invariant to original DIMACS clause order"])
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    with open(args.csv,"w",newline="") as f:
        fields=["gbd","cohort","source_sha256","sample",
           "original_clauses","eligible_short_clauses",
           "eligible_coverage","derived","certified",
           "top_pivot","top_count","pivot_count","dominance",
           "gate","candidate_clause_sha256"]
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(records)
    lines=["# R50 certified sampling sensitivity audit",
      "Eight SHA-pinned previously seen SATComp26 sources; 3 clause samples each.",
      "24 full original-clause proof audits; NO solver runtime or blind speedup.",
      "", "| GBD prefix | Eligible short clauses | First: (derived, dominance, gate) | Uniform | Last |",
      "|---|---:|---|---|---|"]
    for gbd,v in by.items():
        def fmt(x):
            return str(x["derived"])+", "+str(x["dominance"])+", "+str(x["gate"])
        lines.append("| "+gbd[:8]+" | "+str(v["first"]["eligible_short_clauses"])+
          " | "+fmt(v["first"])+" | "+fmt(v["uniform"])+" | "+fmt(v["last"])+" |")
    lines+=["","Sampling-sensitive originals: "+str(len(sensitive))+"/8.",
       "Originals with changed binary gate: "+str(len(gate_changed))+"/8.",
       "Important: finite clause sampling and limited 16k candidate scans can",
       "create selection artifacts even if the complete formula is invariant.",
       "No modification of any solver binary, heuristic or historical SQLite."]
    Path(args.markdown).write_text("\n".join(lines)+"\n")
    print("R50_AUDIT_PASS",len(records),"certified rows;",
          len(sensitive),"sensitive formulas;",
          len(gate_changed),"changed gates")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("frozen","design","output","csv","markdown"):
        p.add_argument("--"+name,required=True)
    main(p.parse_args())

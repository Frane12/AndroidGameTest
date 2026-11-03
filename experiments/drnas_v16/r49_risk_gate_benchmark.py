#!/usr/bin/env python3
"""DRNAS SAT R49: pre-registered conservative risk gate for certified R47 clauses.

R49 is a hypothesis test, not an established learned policy:
- Based ONLY on the two known R48 examples, choose a conservative structural
  filter using original DIMACS metadata, never a source hash or solver outcome.
- Reuse the R47 two-parent proof-checked resolution algorithm unchanged.
- Compare original Kissat, gated last-16, ungated full-40, and shadow.
- Analyze an older eight-source cohort separately from a disjoint 17-source
  SATComp2026 cohort not used to choose the thresholds.
- Every subprocess has one strict overall wall budget including analysis,
  CNF rewriting and original-source SAT witness verification.
No causal performance or general-world claim is justified by two training cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import tempfile
import time

import r47_partial_links as r47
import r48_causal_clause_dose as r48
import r32p_real_satcomp26_benchmark as proof

PROTOCOL = "DRNAS-R49-FROZEN-STRUCTURAL-RISK-GATE-20261103-v1"
KNOWN = ("benefit", "regress")
SHARDS = 4
KNOWN_REPEATS = 2
EXTERNAL_REPEATS = 1
KNOWN_MODES = ("clean", "shadow", "gate_tail16", "all40")
EXTERNAL_MODES = ("clean", "gate_tail16")
KNOWN_CAP = 30.0
EXTERNAL_CAP = 45.0

# This is an IN-SAMPLE candidate selected using the two R48 cases:
# benefited: 83,188 vars, 1,909,831 clauses; regressed: 248,213 vars,
# 803,227 clauses. The threshold values themselves are NOT a scientific
# discovery or a trained classifier. Freeze them before external evaluation.
GATE = dict(min_clauses=1_000_000, max_variables=150_000,
            min_clause_var_ratio=10.0, source_bytes_cap=65*1024*1024,
            min_certified_resolvents=16, number_to_add=16)


def check(condition, message):
    if not condition:
        raise RuntimeError("R49_AUDIT_FAILURE " + str(message))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path):
    with open(path, "rt", encoding="ascii", errors="strict") as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            fields = line.split()
            check(len(fields) == 4 and fields[:2] == ["p", "cnf"],
                  "unexpected DIMACS header")
            n, m = map(int, fields[2:])
            check(n > 0 and m >= 0, "invalid DIMACS dimensions")
            return n, m
    raise RuntimeError("R49_AUDIT_FAILURE missing DIMACS header")


def gate_features(path, case):
    n, m = read_header(path)
    check(n == case["vars"] and m == case["clauses"],
          "source metadata differs from original DIMACS")
    ratio = m / max(n, 1)
    features = dict(n=n, m=m, ratio=round(ratio, 7),
                    file_bytes=Path(path).stat().st_size)
    admit = bool(m >= GATE["min_clauses"] and
                 n <= GATE["max_variables"] and
                 ratio >= GATE["min_clause_var_ratio"] and
                 features["file_bytes"] <= GATE["source_bytes_cap"])
    return admit, features


def freeze(args):
    roots = {"known": Path(args.known), "external": Path(args.external)}
    manifest = {}
    for cohort, root in roots.items():
        m = json.loads((root / "manifest.json").read_text())
        prefix = ("DRNAS-R32P-REAL-SATCOMP2026" if cohort == "known"
                  else "DRNAS-R32R-PROSPECTIVE-REAL2026")
        check(m["protocol"].startswith(prefix), "wrong official source protocol")
        check(len(m["cases"]) == (8 if cohort == "known" else 17),
              "frozen official sample not as audited")
        cases = []
        for case in m["cases"]:
            source = root / case["name"]
            check(source.is_file() and sha(source) == case["sha256"],
                  "source has changed")
            admit, features = gate_features(source, case)
            cases.append(dict(name=case["name"], gbd=case["gbd"],
                 vars=case["vars"], clauses=case["clauses"],
                 source_sha=case["sha256"], gate_metadata_admit=admit,
                 features=features))
        manifest[cohort] = cases
    s1 = {x["source_sha"] for x in manifest["known"]}
    s2 = {x["source_sha"] for x in manifest["external"]}
    check(len(s1) == 8 and len(s2) == 17 and not (s1 & s2),
          "external cohort must be SHA-disjoint from calibration cohort")
    known_ids = {x["gbd"] for x in manifest["known"]}
    check(set(r48.TARGETS.values()) <= known_ids, "missing calibration case")
    binary = Path(args.clean)
    check(binary.is_file(), "pinned Kissat missing")
    design = dict(protocol=PROTOCOL, gate=GATE, manifest=manifest,
                  original_manifest_sha={k:sha(v/"manifest.json") for k,v in roots.items()},
                  binary_sha=sha(binary), cap={"known":KNOWN_CAP,"external":EXTERNAL_CAP},
                  modes={"known":KNOWN_MODES,"external":EXTERNAL_MODES},
                  repeats={"known":KNOWN_REPEATS,"external":EXTERNAL_REPEATS},
                  decision_basis=["precommitted syntactic source metadata",
                   "thresholds chosen after observing two R48 calibration outcomes",
                   "no solver timing or outcome of external 17 cases used"],
                  limitations=[
                   "These 17 official external cases were previously tested in R32r; they are not newly downloaded.",
                   "Their hashes are disjoint from the R47/R48 eight-source cohort.",
                   "This is validation of a fixed *experimental gate*, not proof of generalization.",
                   "Known eight cases were previously measured and cannot be called blind.",
                   "R47 derivations are ordinary short resolution consequences, not detected partial XOR.",
                   "Witness checking is against original CNF; UNSAT requires further LRAT checking.",
                   "PAR-2 reports timeout penalties, not true runtimes of unsolved formulas."])
    Path(args.output).write_text(json.dumps(design, indent=2)+"\n")
    print("R49_FROZEN_GATE_PASS",json.dumps({
        "known":len(manifest["known"]),"external":len(manifest["external"]),
        "known_gate_admit":sum(c["gate_metadata_admit"] for c in manifest["known"]),
        "external_gate_admit":sum(c["gate_metadata_admit"] for c in manifest["external"]),
        "gate":GATE},sort_keys=True),flush=True)


def prove_derived(source, new, certificates):
    check(len(new) == len(certificates) <= 40, "certificate count mismatch")
    # R47 derive_partial independently validates each resolution proof by
    # enumerating assignments over at most five original variables.
    # Re-check the recorded clauses and proof schema here. Never accept an
    # unsound heuristic guess as solver input.
    for clause, p in zip(new, certificates):
        check(list(clause) == p["clause"] and len(p["parent_ids"]) == 2
              and len(p["support"]) <= 5, "R47 proof schema violation")
    return hashlib.sha256(json.dumps([list(c) for c in new],
                                  separators=(",",":")).encode()).hexdigest()


def trial(source, case, binary, mode, cap):
    start = time.monotonic()
    trace = dict(route="clean", metadata_gate=False, derived=0, added=0,
                 reason=None, features=None, prep_s=0.0, witness_s=0.0)
    prepared = source
    with tempfile.TemporaryDirectory(prefix="drnas_r49_") as tmp:
        if mode != "clean":
            admit, features = gate_features(source, case)
            trace["metadata_gate"] = admit
            trace["features"] = features
            # Crucial: if not admitted, do not parse source or change solver
            # settings or copy the file. This is a real abstention.
            should_derive = mode in ("shadow","all40") or admit
            if should_derive:
                new, certificates, analysis = r47.derive_partial(source)
                fp = prove_derived(source, new, certificates)
                trace.update(derived=len(new), reason=analysis["reason"],
                             proof_sha=fp, analysis=analysis)
                if mode == "shadow":
                    trace["route"] = "shadow_only"
                elif mode == "all40":
                    chosen = new
                    trace["route"] = "ungated_full40"
                elif len(new) >= GATE["min_certified_resolvents"]:
                    chosen = new[-GATE["number_to_add"]:]
                    trace["route"] = "gated_tail16"
                else:
                    chosen = []
                    trace["route"] = "abstain_insufficient_proofs"
                if mode != "shadow" and chosen:
                    prepared = Path(tmp)/"verified_augmented.cnf"
                    trace["rewrite"] = r48.safe_rewrite(source, prepared, chosen)
                    trace["added"] = len(chosen)
                elif mode != "shadow" and not chosen:
                    trace["route"] = "abstain_no_provable_clause"
            else:
                trace["route"] = "abstain_structural_gate"
                trace["reason"] = "metadata_outside_training_region"
        trace["prep_s"] = round(time.monotonic()-start,6)
        remaining = cap - (time.monotonic()-start)
        if remaining <= 0:
            trace["route"] += "_preprocess_exceeded_budget"
            return dict(answer="TIMEOUT",time_s=round(time.monotonic()-start,6),
                        par2_s=cap*2, trace=trace)
        try:
            p = subprocess.run([str(binary),str(prepared)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,errors="replace",timeout=remaining)
        except subprocess.TimeoutExpired:
            return dict(answer="TIMEOUT",time_s=round(time.monotonic()-start,6),
                        par2_s=cap*2,trace=trace)
        solver_elapsed = time.monotonic()-start
        check(p.returncode in (10,20),
              "solver failure "+str(p.returncode)+" "+p.stderr[-350:])
        verdict = "SAT" if p.returncode == 10 else "UNSAT"
        if verdict=="SAT":
            vs = time.monotonic()
            proof.verify_sat_witness(source,p.stdout)
            trace["witness_s"] = round(time.monotonic()-vs,6)
        elapsed = time.monotonic()-start
        trace["solver_return_within_cap"] = bool(solver_elapsed <= cap)
        if elapsed > cap:
            # Strict accounting fixes the R48 shadow >30s anomaly:
            # a late SAT witness never counts as a solved trial.
            trace["late_verdict"] = verdict
            trace["route"] += "_witness_or_overhead_exceeded_budget"
            return dict(answer="TIMEOUT",time_s=round(elapsed,6),
                        par2_s=cap*2,trace=trace)
        return dict(answer=verdict,time_s=round(elapsed,6),
                    par2_s=round(elapsed,6),trace=trace)


def measure(args):
    design = json.loads(Path(args.design).read_text())
    check(design["protocol"]==PROTOCOL and design["gate"]==GATE,
          "modified R49 pre-registered gate")
    cohort=args.cohort
    check(cohort in ("known","external") and args.shard in range(SHARDS),
          "bad precommitted arm")
    root=Path(args.inputs)
    check(sha(root/"manifest.json")==design["original_manifest_sha"][cohort],
          "original source manifest changed")
    binary=Path(args.clean).resolve()
    check(sha(binary)==design["binary_sha"],"Kissat binary changed")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=design["manifest"][cohort][args.shard::SHARDS]
    modes=tuple(design["modes"][cohort])
    repeats=int(design["repeats"][cohort])
    cap=float(design["cap"][cohort])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(cohort=cohort,shard=args.shard,
         protocol=PROTOCOL,design_sha=sha(args.design),binary_sha=sha(binary)),indent=2)+"\n")
    rows=[]
    for case in cases:
        original=root/case["name"]
        check(sha(original)==case["source_sha"],"source CNF hash changed")
        for rep in range(repeats):
            ordered=list(modes)
            seed=int(hashlib.sha256((case["source_sha"]+str(rep)+PROTOCOL)
                                    .encode()).hexdigest(),16)
            random.Random(seed).shuffle(ordered)
            for mode in ordered:
                r=trial(original,case,binary,mode,cap)
                rows.append(dict(cohort=cohort,gbd=case["gbd"],
                                 source_sha=case["source_sha"],
                                 repeat=rep,mode=mode,**r))
                print("R49_TRIAL",cohort,case["gbd"],rep,mode,
                      r["answer"],r["time_s"],r["trace"]["route"],
                      "new",r["trace"]["added"],flush=True)
            (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R49_SHARD_PASS",cohort,args.shard,len(rows),flush=True)


def aggregate(args):
    design=json.loads(Path(args.design).read_text())
    check(design["protocol"]==PROTOCOL and design["gate"]==GATE,
          "final audit protocol/gate mismatch")
    rows=[]
    solver_hash=set()
    for cohort in ("known","external"):
        for shard in range(SHARDS):
            root=Path(args.combined)/f"r49-{cohort}-{shard}"/"results"
            meta=json.loads((root/"meta.json").read_text())
            check(meta["protocol"]==PROTOCOL and meta["cohort"]==cohort
                  and meta["shard"]==shard
                  and meta["design_sha"]==sha(args.design),
                  "partial run not from frozen design")
            solver_hash.add(meta["binary_sha"])
            part=json.loads((root/"rows.json").read_text())
            expected=len(design["manifest"][cohort][shard::SHARDS])*int(
              design["repeats"][cohort])*len(design["modes"][cohort])
            check(len(part)==expected,"incomplete paired measurements")
            rows.extend(part)
    check(solver_hash=={design["binary_sha"]},
          "different Kissat executable across shards")
    cohorts={}
    for cohort in ("known","external"):
        modes=tuple(design["modes"][cohort])
        cap=float(design["cap"][cohort])
        repeats=int(design["repeats"][cohort])
        cases=design["manifest"][cohort]
        for case in cases:
            for rep in range(repeats):
                group=[r for r in rows if r["cohort"]==cohort
                       and r["source_sha"]==case["source_sha"] and r["repeat"]==rep]
                check({r["mode"] for r in group}==set(modes),
                      "missing paired solver arm")
                ans={r["answer"] for r in group}-{"TIMEOUT"}
                check(len(ans)<=1,"SAT and UNSAT disagree on one source")
                for r in group:
                    if r["answer"]=="TIMEOUT":
                        check(r["par2_s"]==2*cap,
                              "timeout missing PAR2 penalty")
                    else:
                        check(r["time_s"]<=cap and r["par2_s"]==r["time_s"],
                              "late result incorrectly counted as solved")
        summaries={}
        for mode in modes:
            trial_rows=[r for r in rows if r["cohort"]==cohort and r["mode"]==mode]
            summaries[mode]=dict(
              attempts=len(trial_rows),
              solved_attempts=sum(r["answer"]!="TIMEOUT" for r in trial_rows),
              par2_s=round(sum(r["par2_s"] for r in trial_rows),6),
              active_derived_attempts=sum(r["trace"]["added"]>0 for r in trial_rows),
              derived_clauses_sum=sum(r["trace"]["added"] for r in trial_rows),
              abstentions=sum(str(r["trace"]["route"]).startswith("abstain")
                              for r in trial_rows))
        cohorts[cohort]=summaries
    result=dict(protocol=PROTOCOL,design=design,summary=cohorts,rows=rows)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    lines=["# DRNAS R49 — frozen risk gate versus pinned Kissat","",
      "A deliberately conservative candidate rule trained from exactly TWO known cases.",
      "No source hash in the decision; no changes to Kissat search, phases, or restarts.",
      "Strict wall-clock cap includes derivation, file rewriting and SAT witness checking.",
      "Clean and abstaining routes run the UNMODIFIED source on the SAME solver.",
      "Never treat the previously benchmarked R32r sources as entirely unseen to the project.",
      "",
      "| Cohort | Mode | Solved attempts | Total PAR-2 sec | Actively modified trials | Abstentions |",
      "|---|---|---:|---:|---:|---:|"]
    for cohort in ("known","external"):
        for mode,info in cohorts[cohort].items():
            lines.append(f'| {cohort} | {mode} | {info["solved_attempts"]}/{info["attempts"]}'
                         f' | {info["par2_s"]:.4f} | {info["active_derived_attempts"]}'
                         f' | {info["abstentions"]} |')
    lines+=["","## Individual source outcomes",
      "| Cohort | GBD | Rep | Clean PAR2 | R49 gate PAR2 | Clauses added | Gate/abstain |",
      "|---|---|---:|---:|---:|---:|---|"]
    for cohort in ("known","external"):
        for case in design["manifest"][cohort]:
            for rep in range(int(design["repeats"][cohort])):
                group={r["mode"]:r for r in rows if
                       r["source_sha"]==case["source_sha"] and r["repeat"]==rep}
                if not group:raise AssertionError("missing source rows")
                a=group["clean"];b=group["gate_tail16"]
                lines.append(f'| {cohort} | {case["gbd"]} | {rep} | '
                             f'{a["par2_s"]:.4f} | {b["par2_s"]:.4f} | '
                             f'{b["trace"]["added"]} | {b["trace"]["route"]} |')
    lines+=["","## Limitations"]+["- "+v for v in design["limitations"]]
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R49_FINAL_AUDIT_PASS",len(rows),
          json.dumps(cohorts,sort_keys=True),flush=True)


def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        p=Path(tmp)/"probe.cnf"
        p.write_text("c R49\np cnf 3 2\n1 2 0\n-1 3 0\n")
        c=dict(vars=3,clauses=2)
        admit,features=gate_features(p,c)
        check(not admit and features["ratio"]>0,
              "tiny unrelated CNF incorrectly admitted")
        t=dict(vars=83188,clauses=1909831)
        u=dict(vars=248213,clauses=803227)
        def h(c):
            n,m=c["vars"],c["clauses"]
            return m>=GATE["min_clauses"] and n<=GATE["max_variables"] and (
                   m/n)>=GATE["min_clause_var_ratio"]
        check(h(t) and not h(u),"calibration classifier incorrect")
        r48.safe_rewrite(p,Path(tmp)/"copy.cnf",[(2,3)])
        check("p cnf 3 3" in (Path(tmp)/"copy.cnf").read_text(),
              "safe rewrite not valid")
    print("R49_FROZEN_GATE_STRICT_CAP_AND_REWRITE_SELFTEST_PASS",flush=True)


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for k in ("known","external","clean","output"):
        f.add_argument("--"+k,required=True)
    m=sub.add_parser("measure")
    for k in ("cohort","inputs","design","clean","out"):
        m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("aggregate")
    for k in ("design","combined","output","report"):
        a.add_argument("--"+k,required=True)
    args=p.parse_args()
    {"selftest":lambda:selftest(),
     "freeze":lambda:freeze(args),
     "measure":lambda:measure(args),
     "aggregate":lambda:aggregate(args)}[args.cmd]()

if __name__=="__main__":
    main()

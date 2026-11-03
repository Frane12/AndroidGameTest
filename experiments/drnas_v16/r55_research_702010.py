#!/usr/bin/env python3
"""R55 70/20/10 research: guarded R49, certified XOR and passive early telemetry.

70/20/10 describes research priorities, NOT optimized numeric mixing weights.
Retrospective R53 diagnostic cohort, NOT a fresh blind validation. No Kissat
binary modifications, in-process intervention, or unproved CNF additions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import tempfile
import time

import r49_pivot_coherence_gate as r49
import r32t_certified_short_xor as xor
import r32p_real_satcomp26_benchmark as verify

PROTO = "DRNAS-R55-702010-R53-DIAGNOSTIC-20261103-v1"
SALT = "R55-702010-RESEARCH-FROZEN-20261103"
MODES = ("kissat_clean", "r49_frozen", "structural_guard", "xor_guard", "combo_702010")
CAP = 40.0
REPS = 2
SHARDS = 4
COHORT = 12
# Thresholds fixed BEFORE R55 trial scores; no tuning against the measured set.
STRUCT_MIN_BYTES = 128 * 1024
STRUCT_MAX_BYTES = 16 * 1024 * 1024
STRUCT_PIVOT_MIN = .80
STRUCT_DERIVED_MIN = 24
STRUCT_CLAUSES_MAX = 16
XOR_MIN_BYTES = 16 * 1024
XOR_MAX_BYTES = 1024 * 1024
XOR_ADDITIONS_MAX = 128

def check(v, message):
    if not v:
        raise RuntimeError("R55_FAIL_CLOSED " + str(message))

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()

def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def load(path):
    return json.loads(Path(path).read_text())

def rank(value):
    return hashlib.sha256((SALT + "/" + value).encode()).hexdigest()

def freeze(a):
    root = Path(a.sources)
    manifest = load(root / "manifest.json")
    final = load(a.r53_final)
    check(manifest["protocol"].startswith("DRNAS-R53-50-FRESH-TRIPLE")
          and len(manifest["cases"]) == 50, "R53 sources not original 50")
    check(final["protocol"] == manifest["protocol"], "R53 final does not match source protocol")
    check(len(final["per_instance"]) == 50, "incomplete R53 final")
    eligible = [c for c in manifest["cases"]
                if final["per_instance"][c["gbd"]]["kissat_pinned"]["solved"] > 0]
    timeout = [c for c in manifest["cases"]
               if final["per_instance"][c["gbd"]]["kissat_pinned"]["solved"] == 0]
    check(len(eligible) >= 8 and len(timeout) >= 4, "unexpected R53 solved/timeouts cohort")
    chosen = sorted(eligible, key=lambda c: rank(c["sha256"]))[:8]
    chosen += sorted(timeout, key=lambda c: rank(c["sha256"]))[:4]
    check(len(chosen) == COHORT and len({c["sha256"] for c in chosen}) == COHORT,
          "duplicate or incomplete selection")
    for c in chosen:
        check(digest(root / c["name"]) == c["sha256"], "source SHA mismatch")
    report = dict(protocol=PROTO,source_protocol=manifest["protocol"],
                  manifest_sha=digest(root / "manifest.json"),
                  r53_final_sha=digest(a.r53_final),
                  selection="Retrospective: eight R53-Kissat-solvable and four R53-timeout formulas, salted SHA within strata",
                  blind_holdout=False, sources_seen_in_R53=True,
                  allocation={"structural_percent":70,"xor_percent":20,"early_telemetry_percent":10},
                  modes=list(MODES),cap_s=CAP,reps=REPS,shards=SHARDS,
                  thresholds=dict(struct_min_bytes=STRUCT_MIN_BYTES,
                     struct_max_bytes=STRUCT_MAX_BYTES,pivot_min=STRUCT_PIVOT_MIN,
                     derived_min=STRUCT_DERIVED_MIN,struct_additions_max=STRUCT_CLAUSES_MAX,
                     xor_min_bytes=XOR_MIN_BYTES,xor_max_bytes=XOR_MAX_BYTES,
                     xor_additions_max=XOR_ADDITIONS_MAX),
                  cases=[dict(**c,cohort="solvable" if c in eligible else "timeout") for c in chosen],
                  limitations=[
                    "R53 outcomes used to stratify the development cohort; NOT blind or independent",
                    "70/20/10 are research-priority percentages, not fitted solver coefficients",
                    "XOR additions must pass independent GF(2) proof audit",
                    "Early telemetry is process liveness at 0.2s/1s, NOT conflict-count prediction",
                    "UNSAT without external LRAT proof; SAT witness checked against original",
                    "All preprocessing and rewrites included in inclusive 40s wall cap",
                    "Do not claim SAT Competition world ranking from this test"])
    dump(a.out, report)
    print("R55_FROZEN_PASS", COHORT, "R53 source SHA audit", flush=True)

def certified_structural(original, tempdir, strict):
    size = original.stat().st_size
    if strict and not STRUCT_MIN_BYTES <= size <= STRUCT_MAX_BYTES:
        return original, 0, "size_abstain"
    plan = r49.compute_plan(original)
    if strict:
        if plan["derived"] < STRUCT_DERIVED_MIN or plan["dominance"] < STRUCT_PIVOT_MIN:
            return original, 0, "pivot_abstain"
        clauses = plan["single_pivot_16"][:STRUCT_CLAUSES_MAX]
    else:
        clauses = r49.selection("gate", plan)
    if not clauses:
        return original, 0, "r49_gate_abstain"
    # Recheck R47 two-parent local resolvent certificate for every emitted clause.
    _, original_snippets, _ = r49.r47.sample_original(original)
    proof_by_clause = {tuple(c): p for c, p in zip(plan["clauses"], plan["proofs"])}
    for c in clauses:
        p = proof_by_clause[tuple(c)]
        parents = [original_snippets[i] for i in p["parent_ids"]]
        check(len(parents) == 2 and r49.r46.certifies(parents, c, p["support"]),
              "uncertified structural implication")
    output = Path(tempdir) / "structural.cnf"
    rw = r49.r48.safe_rewrite(original, output, clauses)
    check(rw["added"] == len(clauses), "structural DIMACS rewrite failed")
    return output, len(clauses), "r49_frozen" if not strict else "pivot16"

def certified_xor(original, tempdir):
    size = original.stat().st_size
    if not XOR_MIN_BYTES <= size <= XOR_MAX_BYTES:
        return original, 0, "xor_size_abstain"
    output = Path(tempdir) / "xor.cnf"
    proof = Path(tempdir) / "xor.json"
    info = xor.build(original, output, proof)
    xor.audit(original, output, proof)
    added = info["added_clauses"]
    if not added or added > XOR_ADDITIONS_MAX:
        return original, 0, "xor_no_short_proof_or_budget"
    return output, added, "xor_certified"

def memory_cap():
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024 ** 3, 3 * 1024 ** 3))

def solve(binary, candidate, original, max_wall):
    started = time.monotonic()
    if max_wall <= 0:
        return "TIMEOUT", {"alive_200ms": False, "alive_1s": False}
    p = subprocess.Popen([str(binary), str(candidate)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, errors="replace",
                         preexec_fn=memory_cap)
    telemetry = {"alive_200ms": False, "alive_1s": False}
    stdout = stderr = ""
    try:
        # Observe the running subprocess without changing its search policy.
        for mark, key in ((.2, "alive_200ms"), (1.0, "alive_1s")):
            remaining = max_wall - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(p.args, max_wall)
            try:
                stdout, stderr = p.communicate(timeout=min(max(0.001, mark -
                                      (time.monotonic() - started)), remaining))
                break
            except subprocess.TimeoutExpired:
                telemetry[key] = p.poll() is None
        if p.poll() is None:
            remaining = max_wall - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(p.args, max_wall)
            stdout, stderr = p.communicate(timeout=remaining)
        check(p.returncode in (10, 20), "solver exit " + str(p.returncode) + ": " + stderr[-150:])
        result = "SAT" if p.returncode == 10 else "UNSAT"
        if result == "SAT":
            verify.verify_sat_witness(original, stdout)
        return result, telemetry
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return "TIMEOUT", telemetry
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate()

def trial(original, binary, mode):
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="drnas-r55-") as tmp:
        candidate, added, path = original, 0, "clean"
        if mode == "r49_frozen":
            candidate, added, path = certified_structural(original, tmp, strict=False)
        elif mode in ("structural_guard", "combo_702010"):
            candidate, added, path = certified_structural(original, tmp, strict=True)
            if not added and mode == "combo_702010":
                candidate, added, path = certified_xor(original, tmp)
        elif mode == "xor_guard":
            candidate, added, path = certified_xor(original, tmp)
        check(mode in MODES, "unregistered arm")
        prep = time.monotonic() - began
        if prep >= CAP:
            answer, telemetry = "TIMEOUT", {"alive_200ms": False, "alive_1s": False}
        else:
            answer, telemetry = solve(binary, candidate, original, CAP-prep)
        elapsed = time.monotonic() - began
    if elapsed > CAP:
        answer = "TIMEOUT"
    wall = min(elapsed, CAP)
    return dict(answer=answer,wall_s=round(wall,6),par2_s=round(
                wall if answer != "TIMEOUT" else CAP*2,6),
                prep_s=round(prep,6),added_clauses=added,route=path,
                early=telemetry)

def measure(a):
    design = load(a.design);root=Path(a.sources)
    check(design["protocol"] == PROTO and digest(root / "manifest.json") ==
          design["manifest_sha"], "wrong R53 freeze")
    shard=int(a.shard)
    check(0 <= shard < SHARDS, "bad shard")
    binary=Path(a.kissat).resolve()
    check(binary.is_file(), "pinned Kissat missing")
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    dump(dest / "meta.json", dict(protocol=PROTO, shard=shard,
         manifest_sha=design["manifest_sha"],design_sha=digest(a.design),
         binary_sha=digest(binary),run_sha=os.getenv("GITHUB_SHA","local")))
    rows=[]
    for case in design["cases"][shard::SHARDS]:
        src=root/case["name"]
        check(digest(src)==case["sha256"], "changed original source")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(rank(case["sha256"]+":"+str(rep)),16)).shuffle(order)
            for mode in order:
                record=trial(src,binary,mode)
                if record["answer"] != "TIMEOUT":
                    check(record["answer"] in ("SAT","UNSAT"),"invalid verdict")
                row=dict(gbd=case["gbd"],source_sha=case["sha256"],rep=rep,
                         mode=mode,**record)
                rows.append(row)
                dump(dest/"rows.json",rows)
                print("R55_TRIAL",case["gbd"],rep,mode,row["answer"],
                      row["wall_s"],"PAR2",row["par2_s"],
                      "route",row["route"],"added",row["added_clauses"],flush=True)
    check(len(rows)==len(design["cases"][shard::SHARDS])*REPS*len(MODES),
          "incomplete measurements")

def audit(a):
    design=load(a.design)
    check(design["protocol"] == PROTO and len(design["cases"]) == COHORT,
          "wrong final cohort")
    rows=[];binsha=set();keys=set()
    for shard in range(SHARDS):
        base=Path(a.combined)/("r55-shard-"+str(shard))/"results"
        meta=load(base/"meta.json")
        check(meta["protocol"]==PROTO and meta["shard"]==shard and
              meta["design_sha"]==digest(a.design) and
              meta["manifest_sha"]==design["manifest_sha"],"mixed shard")
        binsha.add(meta["binary_sha"])
        part=load(base/"rows.json")
        check(len(part)==len(design["cases"][shard::SHARDS])*REPS*len(MODES),
              "missing rows")
        for r in part:
            key=(r["source_sha"],r["rep"],r["mode"])
            check(key not in keys,"duplicate row")
            keys.add(key);rows.append(r)
    check(len(binsha)==1 and len(rows)==COHORT*REPS*len(MODES),
          "incomplete 120-trial experiment")
    stats={}
    for mode in MODES:
        part=[r for r in rows if r["mode"]==mode]
        check(len(part)==COHORT*REPS,"incomplete mode")
        stats[mode]=dict(n=len(part),
          solved=sum(r["answer"]!="TIMEOUT" for r in part),
          par2_s=round(sum(r["par2_s"] for r in part),6),
          prep_s=round(sum(r["prep_s"] for r in part),6),
          added=sum(r["added_clauses"] for r in part))
    base=stats["kissat_clean"]["par2_s"]
    for record in stats.values():
        record["gain_vs_clean_pct"]=round(100*(1-record["par2_s"]/base),4)
    for c in design["cases"]:
        for rep in range(REPS):
            paired=[r for r in rows if r["source_sha"]==c["sha256"] and r["rep"]==rep]
            check({r["mode"] for r in paired}==set(MODES),"not paired")
            check(len({r["answer"] for r in paired if r["answer"]!="TIMEOUT"})<=1,
                  "SAT UNSAT disagreement")
            for r in paired:
                check(abs(r["par2_s"] -
                    (CAP*2 if r["answer"]=="TIMEOUT" else r["wall_s"]))<.002,
                    "PAR2 mismatch")
    dump(a.json,dict(protocol=PROTO,aggregate=stats,design=design,rows=rows,
                     binary_sha=next(iter(binsha))))
    lines=["# R55 70/20/10 research prototype — R53 retrospective diagnostic",
      "", "**NOT blinded generalization; R53 outcomes used to stratify the cohort.**",
      "70/20/10 denotes research emphasis; early telemetry is passive only.",
      "12 original 2026 formulas, 2 paired repeats, one CPU core, 40s inclusive cap.",
      "", "| Mode | Solved /24 | PAR2 total s | Gain vs clean | Added clauses |",
      "|---|---:|---:|---:|---:|"]
    for mode,rec in stats.items():
        lines.append("| "+mode+" | "+str(rec["solved"])+"/24 | "+
          f'{rec["par2_s"]:.3f} | {rec["gain_vs_clean_pct"]:+.3f}% | '+
          str(rec["added"])+" |")
    lines+=["","Original per-trial times, preprocessing cost, route and 0.2s/1s liveness in JSON.",
            "Next required step: freeze rule and independently validate on SHA-disjoint formulas."]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R55_FINAL_AUDIT_PASS",len(rows),json.dumps(stats),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    f=sub.add_parser("freeze")
    f.add_argument("--sources",required=True)
    f.add_argument("--r53-final",required=True)
    f.add_argument("--out",required=True)
    m=sub.add_parser("measure")
    for k in ("sources","design","kissat","shard","out"):
        m.add_argument("--"+k,required=True)
    a=sub.add_parser("audit")
    for k in ("design","combined","json","md"):
        a.add_argument("--"+k,required=True)
    v=p.parse_args()
    if v.action=="freeze":freeze(v)
    elif v.action=="measure":measure(v)
    else:audit(v)

if __name__=="__main__":
    main()

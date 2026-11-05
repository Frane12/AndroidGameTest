#!/usr/bin/env python3
"""V13.11: read-only, certified local 3-XOR extraction from arbitrary mixed CNF.

Strict four-clause groups imply parity equations. Small independent connected
components are solved over GF(2) for contradictions and forced literals ONLY.
A consistent XOR subset does not imply SAT for a mixed CNF. All derivations
are verified by independently XORing source equations; no solver is changed.
"""
import argparse
import collections
import hashlib
import itertools
import json
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

import official_shortlong_select as source

PROTOCOL = "DRNAS-V1311-CERTIFIED-LOCAL-XOR-20261101-v1"
V139_RUN = 41261415700
MAX_GROUPS = 180000
MAX_COMPONENT_EQS = 128
MAX_COMPONENT_VARS = 128
MAX_ANALYZED_EQS = 8000
MAX_PROOFS = 64
source.RAW_CAP = 96 * 1024**2
source.CNF_CAP = 96 * 1024**2
source.VARIABLE_CAP = 1000000
source.CLAUSE_CAP = 4000000
PARITY_MASKS = (sum(1 << m for m in range(8) if m.bit_count() % 2 == 0),
                sum(1 << m for m in range(8) if m.bit_count() % 2 == 1))

def require(test, message):
    if not test:
        raise ValueError(message)

def load(path):
    return json.loads(Path(path).read_text())

def save(path, obj):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def clauses(path):
    """DIMACS clause reader; standard comments, multiline clauses and exact header."""
    n = expected = count = None
    pending = []
    with Path(path).open("rb") as inp:
        for line in inp:
            line = line.strip()
            if not line or line.startswith(b"c") or line.startswith(b"%"):
                continue
            if line.startswith(b"p "):
                require(n is None, "duplicate header")
                fields = line.split()
                require(len(fields) == 4 and fields[1] == b"cnf", "bad header")
                n, expected = int(fields[2]), int(fields[3])
                count = 0
                require(n > 0 and expected >= 0, "invalid header bounds")
                yield ("header", n, expected)
                continue
            require(n is not None, "clause before header")
            for word in line.split():
                lit = int(word)
                if lit == 0:
                    count += 1
                    require(count <= expected, "excess clause")
                    yield ("clause", tuple(pending))
                    pending.clear()
                else:
                    require(abs(lit) <= n, "literal exceeds header")
                    pending.append(lit)
    require(n is not None and not pending and count == expected, "incomplete DIMACS")

def extract(path):
    """Conservative, complete parity blocks only; no labels/timings consulted."""
    start = time.monotonic()
    groups = {}  # variable triple -> (mask bitset, total multiplicity)
    n = m = clause_count = 0
    overflow = 0
    for rec in clauses(path):
        if rec[0] == "header":
            n, m = rec[1:]
            continue
        clause_count += 1
        clause = rec[1]
        if len(clause) != 3 or len({abs(lit) for lit in clause}) != 3:
            continue
        arranged = sorted(clause, key=abs)
        support = tuple(abs(lit) for lit in arranged)
        mask = sum(1 << idx for idx, lit in enumerate(arranged) if lit < 0)
        if support not in groups:
            if len(groups) >= MAX_GROUPS:
                overflow += 1
                continue
            groups[support] = (1 << mask, 1)
        else:
            bitset, cnt = groups[support]
            groups[support] = (bitset | (1 << mask), cnt + 1)
    require(clause_count == m, "clause count mismatch")
    equations = []
    for support, (masks, count) in groups.items():
        if count == 4 and masks in PARITY_MASKS:
            bad = 0 if masks == PARITY_MASKS[0] else 1
            equations.append((support, 1 - bad))
    equations.sort()
    return n, m, equations, {
        "candidate_triples": len(groups), "candidate_overflow_clauses": overflow,
        "extraction_complete": overflow == 0,
        "complete_local_3xor_equations": len(equations),
        "complete_local_3xor_clauses": len(equations) * 4,
        "fraction_clauses_in_xor": round(4 * len(equations) / max(m, 1), 8),
        "extraction_wall_s": round(time.monotonic() - start, 6)
    }

def components(equations):
    """Components of parity hypergraph using union-find, not original CNF graph."""
    parent = {}
    ranks = {}
    def find(x):
        if x not in parent:
            parent[x] = x
            ranks[x] = 0
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def join(a, b):
        a, b = find(a), find(b)
        if a == b:
            return
        if ranks[a] < ranks[b]:
            a, b = b, a
        parent[b] = a
        if ranks[a] == ranks[b]:
            ranks[a] += 1
    for support, _ in equations:
        join(support[0], support[1])
        join(support[0], support[2])
    groups = collections.defaultdict(list)
    for idx, (support, _) in enumerate(equations):
        groups[find(support[0])].append(idx)
    return sorted(groups.values(), key=lambda ids: (len(ids), ids[0]))

def proof_valid(eq, indices, expected_support, expected_rhs):
    """Independently replay each original parity equation, never trust elimination."""
    combined = set()
    rhs = 0
    for k in indices:
        support, bit = eq[k]
        for v in support:
            if v in combined:
                combined.remove(v)
            else:
                combined.add(v)
        rhs ^= bit
    return combined == set(expected_support) and rhs == expected_rhs

def solve_component(eq, ids):
    """Exact GF2 elimination, all row combinations trace original equation IDs."""
    variables = sorted(set(itertools.chain.from_iterable(eq[k][0] for k in ids)))
    require(len(variables) <= MAX_COMPONENT_VARS and
            len(ids) <= MAX_COMPONENT_EQS, "component too large for bounded audit")
    offsets = {v: i for i, v in enumerate(variables)}
    pivots = {}  # bit index -> (row, RHS, row-combination provenance)
    rank = 0
    for local, index in enumerate(ids):
        support, rhs = eq[index]
        bits = sum(1 << offsets[v] for v in support)
        combo = 1 << local
        while bits:
            pivot = bits.bit_length() - 1
            if pivot in pivots:
                old_bits, old_rhs, old_combo = pivots[pivot]
                bits ^= old_bits
                rhs ^= old_rhs
                combo ^= old_combo
            else:
                pivots[pivot] = (bits, rhs, combo)
                rank += 1
                break
        if not bits and rhs:
            source_ids = [ids[j] for j in range(len(ids)) if combo >> j & 1]
            require(proof_valid(eq, source_ids, (), 1), "bad UNSAT proof")
            return {"status": "CERTIFIED_XOR_CONTRADICTION", "rank": rank,
                    "variables": len(variables), "equations": len(ids),
                    "proof_equation_indices": source_ids,
                    "proof_verified": True, "forced": []}

    # Reduced row echelon form. Each row keeps provenance for the proof.
    # Eliminating low pivots from all higher rows is exact, O(128^2) max.
    for low in sorted(pivots):
        low_row, low_rhs, low_combo = pivots[low]
        for high in sorted(pivots):
            if high <= low:
                continue
            row, rhs, combo = pivots[high]
            if (row >> low) & 1:
                pivots[high] = (row ^ low_row, rhs ^ low_rhs,
                                combo ^ low_combo)
    forced = []
    for row, rhs, combo in pivots.values():
        if row.bit_count() != 1:
            continue
        local_var = row.bit_length() - 1
        variable = variables[local_var]
        source_ids = [ids[j] for j in range(len(ids)) if combo >> j & 1]
        require(proof_valid(eq, source_ids, (variable,), rhs),
                "bad implied literal proof")
        forced.append({"variable": variable, "value": rhs,
                       "proof_equation_indices": source_ids,
                       "proof_verified": True})
    return {"status": "CONSISTENT_SUBSYSTEM_NOT_GLOBAL_SAT", "rank": rank,
            "variables": len(variables), "equations": len(ids),
            "nullity": len(variables)-rank, "forced": forced}

def analyze(path):
    n, m, equations, info = extract(path)
    start = time.monotonic()
    comps = components(equations)
    budget = MAX_ANALYZED_EQS
    checked = skipped = skipped_eqs = certified = forced_count = 0
    verified_proofs = []
    size_hist = collections.Counter()
    max_vars_seen = 0
    for ids in comps:
        vars_here = len(set(itertools.chain.from_iterable(equations[i][0] for i in ids)))
        max_vars_seen = max(max_vars_seen, vars_here)
        size_hist["1" if len(ids) == 1 else "2-8" if len(ids) <= 8 else
                  "9-32" if len(ids) <= 32 else "33-128" if len(ids) <= 128 else ">128"] += 1
        if len(ids) > MAX_COMPONENT_EQS or vars_here > MAX_COMPONENT_VARS or len(ids) > budget:
            skipped += 1
            skipped_eqs += len(ids)
            continue
        budget -= len(ids)
        checked += 1
        result = solve_component(equations, ids)
        if result["status"] == "CERTIFIED_XOR_CONTRADICTION":
            certified += 1
            if len(verified_proofs) < MAX_PROOFS:
                verified_proofs.append(result)
        for unit in result["forced"]:
            forced_count += 1
            if len(verified_proofs) < MAX_PROOFS:
                verified_proofs.append({"status": "CERTIFIED_IMPLIED_LITERAL", **unit})
    info.update({
        "variables": n, "clauses": m, "xor_components": len(comps),
        "xor_component_sizes": dict(size_hist),
        "largest_component_variables": max_vars_seen,
        "examined_components": checked, "skipped_components": skipped,
        "skipped_equations": skipped_eqs,
        "examined_equations": MAX_ANALYZED_EQS - budget,
        "certified_xor_contradictions": certified,
        "certified_forced_literals": forced_count,
        "proofs_stored": len(verified_proofs),
        "verified_proofs": verified_proofs,
        "certification_is_complete": skipped == 0 and info["extraction_complete"],
        "component_analysis_wall_s": round(time.monotonic()-start, 6),
        "scope": ("CONTRADICTION_IS_GLOBAL_UNSAT_PROOF_IF_VERIFIED; "
                  "FORCED_LITERALS_ARE_REDUNDANT_IMPLICATIONS; "
                  "NO_POSITIVE_SAT_CLAIM")
    })
    return info

def synthetic(equations, extras=()):
    """Encode XOR equations with exactly the four forbidden assignments."""
    cs = []
    for support, rhs in equations:
        for mask in range(8):
            if mask.bit_count() % 2 != rhs:
                cs.append(tuple(-v if mask >> i & 1 else v
                                for i, v in enumerate(support)))
    cs.extend(extras)
    n = max(abs(x) for c in cs for x in c)
    return b"c verified synthetic regression\n" + (
        f"p cnf {n} {len(cs)}\n").encode() + b"".join(
            (" ".join(map(str, c)) + " 0\n").encode() for c in cs)

def brute_models(raw):
    text = raw.decode().splitlines()
    head = next(x.split() for x in text if x.startswith("p "))
    n = int(head[2])
    cs = [[int(l) for l in ln.split()[:-1]]
          for ln in text if ln and ln[0] not in "cp"]
    results = []
    for bits in range(1 << n):
        if all(any(bool((bits >> (abs(l)-1)) & 1) == (l > 0)
                   for l in clause) for clause in cs):
            results.append(bits)
    return results

def selftest():
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp) / "test.cnf"
        # Four degree-three equations; every variable occurs twice.
        edges = [(1,2,3),(1,4,5),(2,4,6),(3,5,6)]
        eq = [(e, int(i == 3)) for i,e in enumerate(edges)]
        tmp.write_bytes(synthetic(eq, extras=[(1, -2)]))
        out = analyze(tmp)
        require(out["certified_xor_contradictions"] == 1 and
                all(p["proof_verified"] for p in out["verified_proofs"]),
                "unverified UNSAT subset")
        require(not brute_models(tmp.read_bytes()), "wrong UNSAT proof")

        # XOR alone derives x1=1; an unrelated mixed clause must not affect soundness.
        eq = [((1,2,3),0), ((1,2,4),0), ((1,3,4),1)]
        tmp.write_bytes(synthetic(eq, extras=[(5,)]))
        out = analyze(tmp)
        units = [p for p in out["verified_proofs"] if
                 p["status"] == "CERTIFIED_IMPLIED_LITERAL"]
        require(any(p["variable"] == 1 and p["value"] == 1 for p in units),
                "missing verified implied literal")
        models = brute_models(tmp.read_bytes())
        require(models and all((x & 1) == 1 for x in models),
                "implied literal invalid")

        # Deterministic differential proof checker over random small mixed CNFs.
        rng = random.Random(1311)
        for test in range(60):
            choices = list(itertools.combinations(range(1, 7), 3))
            rng.shuffle(choices)
            eq = [(choice, rng.randrange(2)) for choice in choices[:rng.randrange(2, 8)]]
            tmp.write_bytes(synthetic(eq, extras=[(1, -2), (3, 4)]))
            result = analyze(tmp)
            models = brute_models(tmp.read_bytes())
            if result["certified_xor_contradictions"]:
                require(not models, "unsound contradiction")
            for item in result["verified_proofs"]:
                if item["status"] == "CERTIFIED_IMPLIED_LITERAL":
                    v, val = item["variable"], item["value"]
                    require(all(((bits >> (v-1)) & 1) == val for bits in models),
                            "unsound forced literal")
                else:
                    require(item["proof_verified"], "missing verified cert")
        # Extra duplicate makes the strict four-clause group ineligible.
        tmp.write_bytes(synthetic([((1,2,3),0)]) +
                        b"1 2 3 0\n")  # intentionally malformed header count
        try:
            analyze(tmp)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed CNF accepted")
    print("V1311_SELFTEST_PASS: 60 differential mixed-CNF trials; GF2 certificates", flush=True)

def run(args):
    manifest = load(args.manifest)
    require(manifest["protocol"] == "DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101",
            "wrong V13.9 protocol")
    require(len(manifest["cases"]) == 12, "not frozen 12-case set")
    require(0 <= args.shard < 6, "invalid shard")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in manifest["cases"][args.shard::6]:
        path = out / (item["id"] + ".cnf")
        t = time.monotonic()
        got = source.download_and_features(item["id"], path)
        require(got["sha256"] == item["sha256"] and
                got["features"] == item["features"], "CNF hash or features changed")
        try:
            metrics = analyze(path)
        finally:
            path.unlink(missing_ok=True)
        require(metrics["variables"] == item["variables"] and
                metrics["clauses"] == item["clauses"], "header differs")
        row = {"id":item["id"],"sha256":item["sha256"],
               "official_label_audit_only":item["official_label"],
               "metrics":metrics, "download_and_preflight_s":
                   round(time.monotonic()-t, 6)}
        rows.append(row)
        save(out / "rows.json", rows)
        print("V1311_CASE",args.shard,item["id"][:10],
              "xor",metrics["complete_local_3xor_equations"],
              "components",metrics["xor_components"],
              "tested",metrics["examined_components"],
              "skipped",metrics["skipped_components"],
              "contradictions",metrics["certified_xor_contradictions"],
              "units",metrics["certified_forced_literals"],flush=True)
    require(len(rows) == 2, "incomplete shard")
    print("V1311_SHARD_PASS",args.shard,flush=True)

def audit(args):
    manifest = load(args.manifest)
    require(len(manifest["cases"]) == 12, "wrong frozen manifest")
    rows=[]
    for shard in range(6):
        folder = Path(args.combined) / f"v1311-xor-shard-{shard}"
        sub = load(folder / "rows.json")
        expected = manifest["cases"][shard::6]
        require(len(sub) == 2 and [r["sha256"] for r in sub] ==
                [r["sha256"] for r in expected], "unmatched shard case identities")
        rows.extend(sub)
    totals = collections.Counter()
    for row in rows:
        m = row["metrics"]
        for key in ("complete_local_3xor_equations", "complete_local_3xor_clauses",
                    "xor_components","examined_components","skipped_components",
                    "skipped_equations","certified_xor_contradictions",
                    "certified_forced_literals"):
            totals[key] += m[key]
        totals["formulas_with_local_xor"] += bool(m["complete_local_3xor_equations"])
        totals["formulas_with_certified_contradictions"] += bool(m["certified_xor_contradictions"])
        totals["formulas_with_forced_literals"] += bool(m["certified_forced_literals"])
        totals["overflow_cases"] += not m["extraction_complete"]
        totals["incomplete_cases"] += not m["certification_is_complete"]
        require(all(p["proof_verified"] for p in m["verified_proofs"]),
                "unverified certificate saved")
    report = {"protocol":PROTOCOL, "frozen_v139_run":V139_RUN,
              "n_formulas":len(rows),"totals":dict(totals),"rows":rows,
              "limits":{
                  "max_groups":MAX_GROUPS,"max_equations_per_component":MAX_COMPONENT_EQS,
                  "max_variables_per_component":MAX_COMPONENT_VARS,
                  "max_analyzed_equations_per_formula":MAX_ANALYZED_EQS
              },
              "warnings":[
                  "Frozen 12 real 2024 CNFs are not representative; no holdout performance result.",
                  "A locally recognized XOR subsystem is a necessary logical constraint, NOT sufficient to solve mixed CNF.",
                  "Only verified contradictions can imply global UNSAT; extracted units are implications only.",
                  "Components exceeding caps are skipped, never assumed consistent or solved.",
                  "No DRNAS/Kissat timing comparison or new world-record claim; diagnostic only."
              ]}
    save(args.json,report)
    lines=["# DRNAS V13.11 — verified local parity subsystem diagnostics","",
           "Same 12 SHA-frozen SAT Competition 2024 CNFs from V13.9.",
           "No change to solver. No SAT/UNSAT prediction from labels.","",
           "## Results", "", "| Metric | Count |", "|---|---:|"]
    for key,value in totals.items():
        lines.append(f"| {key.replace('_',' ')} | {value} |")
    lines.extend(["", "## Bounds",
                  f"- Max candidate supports: {MAX_GROUPS}",
                  f"- GF2 component <= {MAX_COMPONENT_EQS} equations and {MAX_COMPONENT_VARS} variables",
                  f"- Max {MAX_ANALYZED_EQS} analyzed equations per formula", "",
                  "## Caution"])
    lines.extend("- " + x for x in report["warnings"])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1311_AUDIT_PASS",len(rows),json.dumps(dict(totals)),flush=True)

def main():
    parser=argparse.ArgumentParser()
    subs=parser.add_subparsers(dest="command",required=True)
    subs.add_parser("selftest")
    p=subs.add_parser("run")
    for item in ("manifest","out"): p.add_argument("--"+item,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=subs.add_parser("audit")
    for item in ("manifest","combined","json","md"):
        p.add_argument("--"+item,required=True)
    args=parser.parse_args()
    if args.command=="selftest": selftest()
    elif args.command=="run": run(args)
    else: audit(args)

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""V13.10 observational diagnostics on the exact V13.9 frozen public 2024 CNFs.

No solver training, solver modifications, SAT predictions, or label-informed routing.
All input identities and official labels are inherited from V13.9, not selected here.
Local XOR-block detection is a structural feature, NOT a global SAT/UNSAT certificate.
"""
import argparse
import collections
import hashlib
import json
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import official_shortlong_select as source
import v137_fastpath as v137

PROTOCOL = "DRNAS-V1310-DIAGNOSTIC-20261101-v1"
V139_RUN = 41261415700
CHILD_SECONDS = 8
MAX_GROUPS = 80000
source.RAW_CAP = 96 * 1024**2
source.CNF_CAP = 96 * 1024**2
source.VARIABLE_CAP = 1000000
source.CLAUSE_CAP = 4000000

def insist(cond, message):
    if not cond:
        raise RuntimeError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def read(path):
    return json.loads(Path(path).read_text())

def scan(path):
    """Bounded-memory DIMACS stream analysis; no solving; may scan mixed encodings."""
    start = time.monotonic()
    groups = {}
    xor_scanned = 0
    clipped = False
    n = m = None
    count = total_lits = maxwidth = comment_lines = empty = 0
    kinds = collections.Counter()
    pending = []
    first_data = None

    def record(cl):
        nonlocal count, total_lits, maxwidth, empty, xor_scanned, clipped
        count += 1
        width = len(cl)
        total_lits += width
        maxwidth = max(maxwidth, width)
        if width == 0:
            empty += 1
        kinds[str(width if width <= 5 else "6+")] += 1
        if width == 3 and len({abs(x) for x in cl}) == 3:
            ordered = sorted(cl, key=abs)
            key = tuple(abs(x) for x in ordered)
            mask = sum(1 << i for i, x in enumerate(ordered) if x < 0)
            if key in groups:
                masks, occurrences = groups[key]
                masks.add(mask)
                groups[key] = (masks, occurrences + 1)
                xor_scanned += 1
            elif len(groups) < MAX_GROUPS:
                groups[key] = ({mask}, 1)
                xor_scanned += 1
            else:
                clipped = True

    with Path(path).open("rb") as inp:
        for raw in inp:
            s = raw.strip()
            if not s:
                continue
            if s.startswith(b"c") or s.startswith(b"%"):
                comment_lines += 1
                continue
            if s.startswith(b"p "):
                insist(n is None, "Duplicate DIMACS header")
                parts = s.split()
                insist(len(parts) >= 4 and parts[1] == b"cnf", "Not DIMACS CNF")
                n, m = int(parts[2]), int(parts[3])
                if first_data is None:
                    first_data = "header"
                continue
            insist(n is not None, "Clause before header")
            if first_data is None:
                first_data = "clause"
            for word in s.split():
                lit = int(word)
                if lit:
                    insist(abs(lit) <= n, "Variable out of header bounds")
                    pending.append(lit)
                else:
                    record(pending)
                    pending = []
                    insist(count <= m, "Excess DIMACS clauses")
    insist(n is not None and not pending and count == m, "Incomplete DIMACS")
    possible = [((0,3,5,6), (1,2,4,7)), ((1,2,4,7), (0,3,5,6))]
    parity = [set(t) for a in possible for t in a][:2]
    # Both complete four-mask parity classes: {0,3,5,6} and {1,2,4,7}.
    blocks = sum(1 for masks, occurrences in groups.values()
                 if occurrences == 4 and masks in parity)
    covered = 4 * blocks
    bytesize = Path(path).stat().st_size
    blockers = []
    if bytesize > v137.MAX_BYTES: blockers.append("over_32MiB")
    if n > v137.MAX_VARIABLES: blockers.append("over_100k_variables")
    if m > v137.MAX_CLAUSES: blockers.append("over_100k_clauses")
    if total_lits > v137.MAX_LITERALS: blockers.append("over_2M_literals")
    if empty: blockers.append("empty_clause")
    if not blockers and (not m % 4 and kinds.get("3", 0) == m and covered == m):
        structure = "globally_pure_3xor"
    elif blocks:
        structure = "local_complete_3xor_blocks_only"
    else:
        structure = "no_complete_3xor_blocks_found"
    return {
        "bytes": bytesize, "variables": n, "clauses": m, "total_literals": total_lits,
        "comments": comment_lines, "max_width": maxwidth,
        "widths": dict(kinds), "complete_xor_blocks": blocks,
        "complete_xor_clause_coverage": covered,
        "xor_clause_fraction_lower_bound": round(covered / max(1, m), 8),
        "groups_capped": clipped, "groups_recorded": len(groups),
        "v137_hard_limit_blockers": blockers,
        "prior_classifier_first_line_compatible": Path(path).open("rb").readline().strip().startswith(b"p cnf "),
        "structure_hint": structure, "scan_wall_s": round(time.monotonic()-start, 6)
    }

def exact_child(path):
    """Stage timings of unchanged V13.7 code, in an isolated child process."""
    import v136_symbolic as prior
    out = {"status": "UNKNOWN"}
    t = time.monotonic()
    raw = Path(path).read_bytes()
    out["read_wall_s"] = round(time.monotonic()-t, 6)
    start = time.monotonic()
    try:
        n, clauses = v137.read_dimacs(raw)
        out["parser_status"] = "OK"
    except Exception as exc:
        out["parser_status"] = type(exc).__name__
        out["parser_reason"] = str(exc)[:180]
        out["parse_wall_s"] = round(time.monotonic()-start, 6)
        out["status"] = "UNSUPPORTED"
        return out
    out["parse_wall_s"] = round(time.monotonic()-start, 6)
    start = time.monotonic()
    eq = v137.xor_equations(n, clauses)
    out["xor_detect_wall_s"] = round(time.monotonic()-start, 6)
    if eq is not None:
        start = time.monotonic()
        result = v137.solve_affine(n, eq)
        v137.verify(n, clauses, result)
        out["exact_proof_and_verify_wall_s"] = round(time.monotonic()-start, 6)
        out["status"] = result["status"]
        out["selection"] = result["path"]
        return out
    start = time.monotonic()
    try:
        route, why = prior.classify(raw)
        out["selection"] = route
        out["reason"] = why
        out["status"] = "FALLBACK" if why != "complete_pigeonhole" else "UNSAT"
        # Verify certificate if claiming UNSAT.
        if out["status"] == "UNSAT":
            v137.verify(n, clauses, {"path":"pigeonhole_exact","status":"UNSAT"})
    except Exception as exc:
        out["status"] = "UNSUPPORTED"
        out["classifier_exception"] = type(exc).__name__
        out["classifier_reason"] = str(exc)[:180]
    out["classifier_wall_s"] = round(time.monotonic()-start, 6)
    return out

def child_limits():
    limit = 2 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

def profile(path):
    t = time.monotonic()
    try:
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "exact",
                            "--file", str(Path(path).resolve())],
                            text=True, capture_output=True, timeout=CHILD_SECONDS,
                            preexec_fn=child_limits)
        wall = time.monotonic()-t
        if p.returncode:
            return {"status": "CHILD_ERROR", "returncode": p.returncode,
                    "stderr": p.stderr[-350:], "wall_s": round(wall, 6)}
        obj = json.loads(p.stdout)
        obj["wall_s"] = round(wall, 6)
        return obj
    except subprocess.TimeoutExpired:
        return {"status": "PROFILE_TIMEOUT", "wall_s": CHILD_SECONDS}

def run(args):
    manifest = read(args.manifest)
    insist(manifest["protocol"] == "DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101",
           "Wrong frozen V13.9 identity")
    insist(len(manifest["cases"]) == 12, "Expected exactly 12 frozen cases")
    insist(0 <= args.shard < 6, "Shard must be 0...5")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in manifest["cases"][args.shard::6]:
        filepath = out / (case["id"] + ".cnf")
        start = time.monotonic()
        got = source.download_and_features(case["id"], filepath)
        download_s = round(time.monotonic()-start, 6)
        insist(got["sha256"] == case["sha256"] and
               got["features"] == case["features"], "Frozen identity/features mismatch")
        try:
            structural = scan(filepath)
            metrics = profile(filepath)
        finally:
            filepath.unlink(missing_ok=True)
        record = {"id": case["id"], "sha256": case["sha256"],
                  "cohort": case["cohort"], "label": case["official_label"],
                  "download_and_preflight_s": download_s,
                  "structural": structural, "v137_stages": metrics}
        rows.append(record)
        dump(out / "rows.json", rows)
        print("V1310_DIAG", args.shard, case["id"][:10],
              structural["structure_hint"],
              structural["v137_hard_limit_blockers"],
              metrics["status"], flush=True)
    insist(len(rows) == 2, "Incomplete shard")
    print("V1310_SHARD_PASS", args.shard, len(rows), flush=True)

def audit(args):
    manifest = read(args.manifest)
    prior = read(args.prior)
    insist(len(manifest["cases"]) == 12 and prior["n_formulas"] == 12,
           "Wrong V13.9 evidence")
    known = {c["id"]: c for c in manifest["cases"]}
    old = {c["id"]: c for c in prior["cases"]}
    insist(set(known) == set(old), "V13.9 case IDs differ")
    rows = []
    for shard in range(6):
        folder = Path(args.combined) / ("v1310-diagnostic-shard-" + str(shard))
        part = read(folder / "rows.json")
        expected = manifest["cases"][shard::6]
        insist(len(part) == 2 and [x["id"] for x in part] ==
               [x["id"] for x in expected], "Missing/out-of-order shard")
        rows.extend(part)
    counts = collections.Counter()
    reasons = collections.Counter()
    statuses = collections.Counter()
    xor_total = 0
    for r in rows:
        c = known[r["id"]]
        insist(r["sha256"] == c["sha256"] == old[r["id"]]["sha256"],
               "Case SHA mismatch")
        s = r["structural"]; p = r["v137_stages"]
        insist(s["variables"] == c["variables"] and s["clauses"] == c["clauses"],
               "DIMACS header mismatch")
        statuses[p["status"]] += 1
        counts[s["structure_hint"]] += 1
        xor_total += s["complete_xor_blocks"]
        for reason in s["v137_hard_limit_blockers"]:
            reasons[reason] += 1
        if not s["prior_classifier_first_line_compatible"]:
            reasons["first_line_not_header"] += 1
    report = {"protocol": PROTOCOL, "base_run": V139_RUN,
              "formulas": 12, "case_ids": list(known), "v139_summaries": prior["summaries"],
              "v137_profile_statuses": dict(statuses),
              "structure_hints": dict(counts),
              "v137_blocker_counts": dict(reasons),
              "complete_3xor_blocks_in_mixed_cnf": xor_total,
              "rows": rows,
              "caveats": [
                  "This is a diagnosis of the frozen nonrepresentative 12-formula V13.9 sample.",
                  "No new SAT solver runtimes, rankings, or general SAT improvements.",
                  "Complete XOR blocks within a mixed CNF are NOT sufficient to solve the whole CNF.",
                  "Profile stage timings are diagnostic, not a fair solver wall-clock comparison.",
                  "Unsupported parser inputs are recorded, never labeled as SAT/UNSAT.",
                  "V13.9 baseline results are reused unchanged; original solver binaries untouched."
              ]}
    dump(args.json, report)
    lines = ["# DRNAS V13.10 — diagnostic audit (same frozen 12 real 2024 CNFs)", "",
             "**Read-only diagnostic; unchanged V13.7 and V13.9 baseline evidence.**", "",
             "## Exact-parser profile outcomes"]
    lines += [f"- {key}: {num}/12" for key,num in sorted(statuses.items())]
    lines += ["", "## Boundaries and input layout"]
    lines += [f"- {key}: {num}/12" for key,num in sorted(reasons.items())]
    lines += ["", "## Read-only structural hints"]
    lines += [f"- {key}: {num}/12" for key,num in sorted(counts.items())]
    lines += ["", f"Complete XOR four-clause blocks: {xor_total} (not a SAT proof)", "",
              "## Frozen V13.9 solved counts"]
    for solver,m in prior["summaries"]["all"]["methods"].items():
        lines.append(f"- {solver}: {m['solved']}/{m['attempts']} attempts, PAR-2 {m['PAR2_s']:.6f} s")
    lines += ["", "## Limits"] + ["- "+x for x in report["caveats"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines), flush=True)
    print("V1310_AUDIT_PASS", len(rows), flush=True)

def selftest():
    with tempfile.TemporaryDirectory() as temp:
        p = Path(temp) / "xor.cnf"
        p.write_bytes(b"c real header comment\np cnf 3 4\n1 2 3 0\n-1 -2 3 0\n-1 2 -3 0\n1 -2 -3 0\n")
        s = scan(p)
        insist(s["complete_xor_blocks"] == 1 and
               s["structure_hint"] == "globally_pure_3xor", "XOR block undetected")
        insist(not s["prior_classifier_first_line_compatible"], "Comment issue not detected")
        x = profile(p)
        insist(x["status"] == "SAT" and x["selection"] == "affine_exact",
               "Exact XOR proof failed")
        q = Path(temp) / "mixed.cnf"
        q.write_bytes(p.read_bytes().replace(b"p cnf 3 4", b"p cnf 4 5") + b"4 0\n")
        s = scan(q)
        insist(s["complete_xor_blocks"] == 1 and
               s["structure_hint"] == "local_complete_3xor_blocks_only",
               "Mixed exact XOR subset undetected")
        r = profile(q)
        insist(r["status"] in ("UNSUPPORTED", "FALLBACK"), "Mixed CNF wrongly solved")
        print("V1310_SELFTEST_PASS", s["structure_hint"], r["status"], flush=True)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("selftest")
    p = sp.add_parser("exact")
    p.add_argument("--file", required=True)
    p = sp.add_parser("run")
    for field in ("manifest","out"):
        p.add_argument("--"+field, required=True)
    p.add_argument("--shard", type=int, required=True)
    p = sp.add_parser("audit")
    for field in ("manifest","prior","combined","json","md"):
        p.add_argument("--"+field, required=True)
    args = ap.parse_args()
    if args.cmd == "selftest": selftest()
    elif args.cmd == "exact": print(json.dumps(exact_child(args.file), sort_keys=True))
    elif args.cmd == "run": run(args)
    elif args.cmd == "audit": audit(args)

if __name__ == "__main__":
    main()

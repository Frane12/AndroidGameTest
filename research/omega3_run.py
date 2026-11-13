#!/usr/bin/env python3
"""DRNAS MATH Ω3: frozen external CNF, proof-only detector + fair paired baselines.

No training; no modifications to SAT solvers. MATH engine can ONLY assert
source-verified UNSAT, never guess SAT. Non-hits fall back to frozen Kissat.
SAT model validated on ORIGINAL CNF. Baseline UNSAT is labelled unverified
without original-CNF LRAT/DRAT. One logical CPU per solver.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import lzma
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from omega3_verify import parse_cnf, verify_sat, verify_unsat, verify_source_preserving_sat_view


def source_xor3(clauses):
    masks = collections.defaultdict(set)
    for clause in clauses:
        if len(clause) != 3:
            continue
        vars_ = tuple(sorted(abs(z) for z in clause))
        if len(set(vars_)) != 3:
            continue
        signs = sum(1 << vars_.index(-z) for z in clause if z < 0)
        masks[vars_].add(signs)
    rows = []
    for vars_, observed in masks.items():
        for parity in (0, 1):
            forbidden = [i for i in range(8) if i.bit_count() % 2 != parity]
            if all(i in observed for i in forbidden):
                premises = [[(-v if i >> pos & 1 else v)
                             for pos, v in enumerate(vars_)] for i in forbidden]
                rows.append({"vars": list(vars_), "rhs": parity,
                             "premises": premises, "origin": "XOR3"})
    for clause in clauses:
        if len(clause) == 1:
            lit = clause[0]
            rows.append({"vars": [abs(lit)], "rhs": int(lit > 0),
                         "premises": [[lit]], "origin": "UNIT"})
    return rows


def certified_exact_k(clauses, max_candidates=15000, max_overlap=30000):
    """Complete CNF cardinality encodings, width 2..4; never infer from hints."""
    def signed_key(c):
        return tuple(sorted(c, key=lambda v: (abs(v), v)))
    present = {signed_key(c) for c in clauses}
    candidates = set()
    triples = []
    for c in present:
        if len(c) not in (2, 3, 4) or len({abs(x) for x in c}) != len(c):
            continue
        candidates.add((c, 1))
        candidates.add((signed_key([-x for x in c]), len(c) - 1))
        if len(c) == 3:
            triples.append(c)
        if len(candidates) >= max_candidates:
            break
    overlaps = collections.defaultdict(list)
    for c in triples:
        for p in itertools.combinations(c, 2):
            overlaps[signed_key(p)].append(c)
    attempts = 0
    for group in overlaps.values():
        for a, b in itertools.combinations(group, 2):
            attempts += 1
            if attempts >= max_overlap or len(candidates) >= max_candidates:
                break
            terms = set(a) | set(b)
            if len(terms) == 4 and len({abs(x) for x in terms}) == 4:
                candidates.add((signed_key(terms), 2))
        if attempts >= max_overlap or len(candidates) >= max_candidates:
            break
    rows = []
    for terms, k in sorted(candidates):
        n = len(terms)
        if not 1 <= k < n:
            continue
        source = [signed_key(combo) for combo in itertools.combinations(terms, n - k + 1)]
        source += [signed_key(-v for v in combo)
                   for combo in itertools.combinations(terms, k + 1)]
        if all(p in present for p in source):
            rows.append({"vars": sorted(abs(v) for v in terms),
                         "rhs": (k + sum(v < 0 for v in terms)) % 2,
                         "premises": [list(p) for p in source], "origin": "EXACT_K"})
    return rows


def cut_proof(xor_rows, cards):
    """Source-derived 2-incidence GF(2) row space, linear-time graph cut."""
    if not xor_rows or not cards:
        return None
    incidence = collections.defaultdict(list)
    for i, row in enumerate(xor_rows):
        for var in row["vars"]:
            incidence[var].append(i)
    if any(len(rows) != 2 or rows[0] == rows[1] for rows in incidence.values()):
        return None
    graph = [[] for _ in xor_rows]
    for var, (a, b) in incidence.items():
        graph[a].append((b, var))
        graph[b].append((a, var))
    components = []
    visited = set()
    for start in range(len(xor_rows)):
        if start in visited:
            continue
        visited.add(start)
        component = [start]
        for current in component:
            for nxt, _ in graph[current]:
                if nxt not in visited:
                    visited.add(nxt)
                    component.append(nxt)
        components.append(component)
    for comp in components:
        if sum(xor_rows[i]["rhs"] for i in comp) % 2 == 1:
            return [xor_rows[i] for i in comp]
    for row in cards:
        target = set(row["vars"])
        if not target.issubset(incidence):
            continue
        labels = {}
        selected = []
        valid = True
        for comp in components:
            labels[comp[0]] = 0
            walk = [comp[0]]
            for current in walk:
                for nxt, var in graph[current]:
                    desired = labels[current] ^ (var in target)
                    if nxt not in labels:
                        labels[nxt] = desired
                        walk.append(nxt)
                    elif labels[nxt] != desired:
                        valid = False
                        break
                if not valid:
                    break
            if not valid:
                break
            yes = [i for i in comp if labels[i]]
            no = [i for i in comp if not labels[i]]
            selected.extend(yes if len(yes) < len(no) else no)
        if valid and sum(xor_rows[i]["rhs"] for i in selected) % 2 != row["rhs"]:
            return [xor_rows[i] for i in selected] + [row]
    return None


def gaussian_contradiction(rows, limit=800):
    """GF(2) elimination with exact XOR ancestry, not a SAT completeness claim."""
    if len(rows) > limit:
        return None
    pivot = {}
    for idx, row in enumerate(rows):
        mask = 0
        for v in row["vars"]:
            mask ^= (1 << (v - 1))
        rhs = row["rhs"]
        ancestry = {idx}
        while mask:
            leading = mask & -mask
            if leading not in pivot:
                pivot[leading] = mask, rhs, ancestry.copy()
                break
            old_mask, old_rhs, old_anc = pivot[leading]
            mask ^= old_mask
            rhs ^= old_rhs
            ancestry.symmetric_difference_update(old_anc)
        if mask == 0 and rhs:
            return [rows[i] for i in sorted(ancestry)]
    return None


def detector(raw):
    begin = time.perf_counter()
    n, clauses = parse_cnf(raw)
    t0 = time.perf_counter()
    xr = source_xor3(clauses)
    t1 = time.perf_counter()
    cr = certified_exact_k(clauses)
    t2 = time.perf_counter()
    proof = cut_proof(xr, cr)
    mode = "CUT" if proof else "GAUSS"
    if not proof:
        proof = gaussian_contradiction(xr + cr)
    return {"status": "UNSAT" if proof else "UNKNOWN",
            "mode": mode if proof else "NO_PROOF", "proof": proof,
            "nvars": n, "clauses": len(clauses), "xor_rows": len(xr),
            "card_rows": len(cr), "scan_s": t1 - t0,
            "card_s": t2 - t1, "math_s": time.perf_counter() - begin}


def _proof_worker(raw, sender):
    """Isolated detector process; parent can enforce a real wall-time cap."""
    try:
        sender.send(detector(raw))
    except BaseException as e:
        try:
            sender.send({"status": "UNKNOWN", "mode": "DETECTOR_ERROR",
                         "error": str(e), "proof": None})
        except Exception:
            pass
    finally:
        sender.close()


def bounded_detector(raw, budget):
    """No async SIGALRM races: fork isolated worker, include fork in cost."""
    import multiprocessing
    begin = time.perf_counter()
    ctx = multiprocessing.get_context("fork")  # GitHub Ubuntu x86_64
    reader, writer = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_proof_worker, args=(raw, writer), daemon=True)
    try:
        process.start()
        writer.close()
        if reader.poll(max(0.01, budget)):
            try:
                row = reader.recv()
            except EOFError:
                row = {"status": "UNKNOWN", "mode": "WORKER_EOF", "proof": None}
        else:
            row = {"status": "UNKNOWN", "mode": "PROOF_TIMEOUT", "proof": None}
    except (OSError, ValueError) as e:
        row = {"status": "UNKNOWN", "mode": "WORKER_ERROR", "error": str(e), "proof": None}
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join(timeout=.10)
        reader.close()
        writer.close()
    row["wall_s"] = time.perf_counter() - begin
    return row


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def github_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def download_source(entry, commit, dest):
    path = entry["path"]
    if "/../" in "/" + path or path.startswith("/"):
        raise ValueError("Unsafe source path")
    url = "https://raw.githubusercontent.com/Tractables/cnfs/" + commit + "/" + path
    request = urllib.request.Request(url, headers={"User-Agent": "DRNAS-OMEGA3/1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                compressed = response.read(1100000)
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)
    if github_blob_sha(compressed) != entry["git_blob_sha"]:
        raise ValueError("Git blob SHA mismatch")
    if path.endswith(".cnf.xz"):
        decoder = lzma.LZMADecompressor()
        raw = decoder.decompress(compressed, max_length=10000001)
        if not decoder.eof or len(raw) > 10000000:
            raise ValueError("Decompressed input exceeds 10 MB")
    else:
        raw = compressed
    if len(raw) > 10000000:
        raise ValueError("Input exceeds 10 MB")
    # MCC/PMC sources may carry projection/weight annotations and SATLIB
    # '%' trailers. No variables, literal signs, clauses or formula order
    # are changed; only formatting/annotation lines are removed for a
    # common strict-DIMACS SAT interface for ALL three solver arms.
    source_lines = []
    stripped = 0
    for line in raw.decode("ascii").splitlines():
        line = line.strip()
        if line.startswith("%"):
            stripped += 1
            break
        if line.startswith("c") or (line.startswith("w ") or line.startswith("w\t")) or not line:
            stripped += 1
            continue
        source_lines.append(line)
    sanitized = ("\n".join(source_lines) + "\n").encode("ascii")
    n, clauses = parse_cnf(sanitized)
    sat_view = (f"p cnf {n} {len(clauses)}\n" +
                "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)).encode("ascii")
    verify_source_preserving_sat_view(raw, sat_view)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sat_view)
    return sat_view, {"raw_source_sha256": sha256(raw),
                      "raw_source_bytes": len(raw),
                      "sat_view_sha256": sha256(sat_view),
                      "stripped_metadata_lines": stripped,
                      "normalization": "clause-preserving SAT base (original source SHA retained)"}


def one_solver(bin_path, path, raw, cap):
    start = time.perf_counter()
    try:
        run = subprocess.run([bin_path, str(path)], text=True,
                             capture_output=True, timeout=max(.02, cap))
        log = run.stdout + "\n" + run.stderr
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "verified": False,
                "e2e_s": time.perf_counter() - start}
    duration = time.perf_counter() - start
    if "s UNSATISFIABLE" in log:
        return {"status": "UNSAT_UNVERIFIED", "verified": False, "e2e_s": duration}
    if "s SATISFIABLE" in log:
        try:
            verify_sat(raw, log)
            return {"status": "SAT_VERIFIED", "verified": True, "e2e_s": duration}
        except Exception as exc:
            return {"status": "SAT_INVALID", "verified": False,
                    "error": str(exc), "e2e_s": duration}
    return {"status": "UNKNOWN", "verified": False,
            "e2e_s": duration, "returncode": run.returncode, "tail": log[-150:]}


def measure(arm, raw, source_path, cap, proof_cap, kissat, cms):
    if arm != "OMEGA3":
        return one_solver(kissat if arm == "KISSAT" else cms, source_path, raw, cap)
    start = time.perf_counter()
    result = bounded_detector(raw, min(proof_cap, cap * .35))
    if result["status"] == "UNSAT":
        try:
            independent = verify_unsat(raw, result["proof"])
            return {"status": "UNSAT_VERIFIED", "verified": True,
                    "e2e_s": time.perf_counter() - start,
                    "proof_rows": independent["rows"],
                    "proof_method": result["mode"],
                    "xor_rows": result["xor_rows"], "card_rows": result["card_rows"]}
        except Exception as exc:
            result["mode"] = "PROOF_REJECTED"
            result["error"] = str(exc)
    elapsed = time.perf_counter() - start
    if elapsed >= cap - .02:
        return {"status": "TIMEOUT", "verified": False, "e2e_s": elapsed,
                "proof_method": result["mode"]}
    back = one_solver(kissat, source_path, raw, max(.02, cap - elapsed))
    back["e2e_s"] += elapsed
    back["fallback"] = True
    back["proof_method"] = result["mode"]
    back["xor_rows"] = result.get("xor_rows", 0)
    back["card_rows"] = result.get("card_rows", 0)
    if "error" in result:
        back["proof_error"] = result["error"]
    return back


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--out", default="omega3_result")
    parser.add_argument("--cap", type=float, default=2.)
    parser.add_argument("--proof-cap", type=float, default=.20)
    parser.add_argument("--kissat", required=True)
    parser.add_argument("--cms", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "DRNAS-OMEGA3-v1"
    assert len(manifest["entries"]) == 300
    assert args.shards == 6 and 0 <= args.shard < args.shards
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    root = Path(args.out)
    cases = root / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    entries = [x for i, x in enumerate(manifest["entries"]) if i % args.shards == args.shard]
    attempts = []
    seen_sha = set()
    begin = time.perf_counter()
    versions = {}
    for label, binary in (("kissat", args.kissat), ("cms", args.cms)):
        versions[label] = {"path": binary, "sha256": sha256(Path(binary).read_bytes())}
    (root / "binaries.json").write_text(json.dumps(versions, indent=2))
    for idx, entry in enumerate(entries):
        record = {k: entry[k] for k in ("family", "path", "split", "git_blob_sha")}
        record["origin_commit"] = manifest["commit"]
        record["shard"] = args.shard
        dest = cases / (str(idx).zfill(3) + ".cnf")
        try:
            raw, conversion = download_source(entry, manifest["commit"], dest)
            record.update(conversion)
            record["sha256"] = sha256(raw)
            record["source_bytes"] = len(raw)
            if record["sha256"] in seen_sha:
                raise ValueError("Duplicate source SHA within shard")
            seen_sha.add(record["sha256"])
        except Exception as e:
            record["skip"] = "SOURCE_FETCH_PARSE_OR_DUPLICATE"
            record["error"] = str(e)
            attempts.append(record)
            print("OMEGA3_SOURCE_SKIP", json.dumps(record), flush=True)
            continue
        arms = ("OMEGA3", "CMS", "KISSAT") if int(record["sha256"][:2], 16) % 2 == 0 else ("KISSAT", "CMS", "OMEGA3")
        record["arms"] = {}
        for arm in arms:
            result = measure(arm, raw, dest, args.cap, args.proof_cap, args.kissat, args.cms)
            result["par2_reported"] = result["e2e_s"] if result["status"] in (
                "SAT_VERIFIED", "UNSAT_VERIFIED", "UNSAT_UNVERIFIED") else 2 * args.cap
            result["par2_verified"] = result["e2e_s"] if result["verified"] else 2 * args.cap
            record["arms"][arm] = result
        attempts.append(record)
        (root / "results.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in attempts))
        print("OMEGA3_TRIAL", json.dumps({
            "shard": args.shard, "index": idx, "family": record["family"],
            "sha256": record["sha256"],
            "arms": {a: {"status": v["status"], "par2_reported": v["par2_reported"],
                         "par2_verified": v["par2_verified"]}
                     for a, v in record["arms"].items()}}, sort_keys=True), flush=True)
    valid = [r for r in attempts if "arms" in r]
    result = {"shard": args.shard, "planned": len(entries), "valid": len(valid),
              "skipped": len(attempts) - len(valid), "cap_s": args.cap,
              "proof_cap_s": args.proof_cap, "elapsed_s": time.perf_counter() - begin,
              "source_manifest_sha256": sha256(manifest_path.read_bytes()),
              "counts": {arm: dict(collections.Counter(x["arms"][arm]["status"] for x in valid))
                         for arm in ("OMEGA3", "KISSAT", "CMS")},
              "par2_reported": {arm: sum(x["arms"][arm]["par2_reported"] for x in valid)
                                for arm in ("OMEGA3", "KISSAT", "CMS")},
              "par2_verified": {arm: sum(x["arms"][arm]["par2_verified"] for x in valid)
                                for arm in ("OMEGA3", "KISSAT", "CMS")},
              "note": "No original-CNF UNSAT proof from Kissat/CMS; mark UNSAT_UNVERIFIED. No native standalone solver claim."}
    (root / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("OMEGA3_FINAL", json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""TD diagnostic: exact, bounded-memory source-XOR partition scan vs T2 streaming.

This is NOT a SAT solver, does not inject any clause or parity row and cannot
claim a speedup. Only full-clause source XOR hints of widths 2..6 are checked.
The separate source-certificate/replay pipeline remains mandatory for CDCL.
"""
import argparse
import hashlib
import json
import pathlib
import tempfile
import time

from ultimate_t2_probe import cheap_probe, MAX_BYTES

BUCKETS = 8
MAX_GROUPS_PER_BUCKET = 5000
MAX_WIDTH = 6
OUT = pathlib.Path("ultimate_td_probe")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()


def pairs(path):
    clause = []
    with pathlib.Path(path).open("r", errors="replace") as f:
        for line in f:
            if line.lstrip().startswith(("c", "p", "%")):
                continue
            for token in line.split():
                lit = int(token)
                if lit:
                    if len(clause) <= MAX_WIDTH:
                        clause.append(lit)
                    continue
                if 2 <= len(clause) <= MAX_WIDTH and len({abs(v) for v in clause}) == len(clause):
                    ordered = sorted(clause, key=abs)
                    key = tuple(abs(v) for v in ordered)
                    mask = sum(1 << i for i, v in enumerate(ordered) if v < 0)
                    yield key, mask
                clause = []
    if clause:
        raise ValueError("unterminated DIMACS clause")


def bucket(key, count):
    # Python hash is salted; do not use it for frozen deterministic partitioning.
    canonical = ",".join(map(str, key)).encode("ascii")
    return int.from_bytes(hashlib.blake2s(canonical, digest_size=4).digest(), "big") % count


def exact_partitioned_probe(source, buckets=BUCKETS, max_groups=MAX_GROUPS_PER_BUCKET):
    """Repeated whole-file pass, exact masks per hashed partition.

    Complete whenever none of the partitions overflows the bounded group map.
    If overflow occurs, return INCONCLUSIVE rather than a false negative.
    """
    source = pathlib.Path(source)
    if source.stat().st_size > MAX_BYTES or source.stat().st_size < 300:
        return dict(complete=False, reason="size_gate", hits=[], groups=0,
                    overflow_buckets=[], buckets=buckets, clauses_examined=0)
    found = set()
    total_groups = 0
    overflow = []
    examined = 0
    for b in range(buckets):
        groups = {}
        bad = False
        for key, mask in pairs(source):
            examined += 1
            if bucket(key, buckets) != b:
                continue
            if key not in groups:
                if len(groups) >= max_groups:
                    bad = True
                    break
                groups[key] = 0
            groups[key] |= 1 << mask
        if bad:
            overflow.append(b)
            continue
        total_groups += len(groups)
        for key, masks in groups.items():
            width = len(key)
            for parity in (0, 1):
                required = sum(1 << x for x in range(1 << width)
                               if x.bit_count() % 2 == parity)
                if masks & required == required:
                    found.add((key, parity))
    hits = sorted(found)
    return dict(complete=not overflow,
                reason="complete_partitioned_scan" if not overflow else "group_bound_inconclusive",
                hits=[dict(variables=list(key), forbidden_mask_parity=parity)
                      for key, parity in hits[:12]],
                total_hits=len(hits),
                groups=total_groups, overflow_buckets=overflow,
                buckets=buckets, clauses_examined=examined)


def measure(source, expected_sha=None, buckets=BUCKETS):
    if expected_sha is not None and sha(source) != expected_sha:
        raise RuntimeError("TD_SOURCE_SHA_MISMATCH: " + str(source))
    tic = time.perf_counter()
    streamed, reason, old_stats = cheap_probe(source)
    stream_s = time.perf_counter() - tic
    tic = time.perf_counter()
    exact = exact_partitioned_probe(source, buckets=buckets)
    exact_s = time.perf_counter() - tic
    if streamed and exact["complete"] and exact["total_hits"] == 0:
        raise RuntimeError("TD_DETECTOR_CONTRADICTION")
    return dict(stream_hit=streamed, stream_reason=reason, stream_s=round(stream_s, 6),
                stream_probe=old_stats, exact=exact, exact_s=round(exact_s, 6))


def selftest():
    with tempfile.TemporaryDirectory() as d:
        base = pathlib.Path(d)
        # Distributed masks of the SAME XOR source variable group. The T2
        # streaming cache evicts singleton groups before the next mask arrives.
        clauses = [f"{i} {i+10000} 0" for i in range(1, 6100)]
        v = (25001, 25002, 25003)
        for mask in (0, 3, 5, 6):
            clauses.append(" ".join(str(-x if mask & (1 << j) else x)
                                    for j, x in enumerate(v)) + " 0")
            clauses.extend(f"{i} {i+30000} 0" for i in range(1, 6100))
        target = base/"distributed.cnf"
        target.write_text("p cnf 36100 " + str(len(clauses)) + "\n" +
                          "\n".join(clauses) + "\n")
        result = measure(target)
        assert not result["stream_hit"], result["stream_reason"]
        assert result["exact"]["complete"] and result["exact"]["total_hits"] >= 1, result
        assert any(x["variables"] == list(v) for x in result["exact"]["hits"]), result
        negative = base/"negative.cnf"
        neg = [f"{i} {i+10000} 0" for i in range(1, 6100)]
        negative.write_text("p cnf 20000 " + str(len(neg)) + "\n" +
                            "\n".join(neg) + "\n")
        n = measure(negative)
        assert n["exact"]["complete"] and n["exact"]["total_hits"] == 0, n
        assert not n["stream_hit"], n
        print("TD_BUCKETED_SELFTEST_PASS", json.dumps({
            "distributed_stream_hit":result["stream_hit"],
            "distributed_exact_hits":result["exact"]["total_hits"],
            "negative_exact_hits":n["exact"]["total_hits"]},sort_keys=True),flush=True)


def run():
    # Only the immutable source manifest and SHA-checked original CNFs from
    # the already completed T2 audit may enter this diagnostic.
    import ultimate_t2_benchmark as t2
    cases = t2.cases()
    if len(cases) != 20:
        raise RuntimeError("TD_INVALID_FROZEN_SET")
    rows = []
    for c in cases:
        p = t2.FROZEN/(c["id"] + ".cnf")
        d = measure(p, c["sha256"])
        rows.append(dict(id=c["id"], sha256=c["sha256"], cohort=c["cohort"],
                         family=c.get("family"), stream_hit=d["stream_hit"],
                         stream_reason=d["stream_reason"],
                         stream_s=d["stream_s"], stream_probe=d["stream_probe"],
                         exact=d["exact"], exact_s=d["exact_s"]))
        print("TD_PROBE_CASE", json.dumps(rows[-1],sort_keys=True),flush=True)
    if len({r["sha256"] for r in rows}) != 20:
        raise RuntimeError("TD_DUPLICATE_SOURCE_SHA")
    manifest = sha(t2.MANIFEST)
    if manifest != "2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2":
        raise RuntimeError("TD_MANIFEST_SHA_DRIFT")
    summary = dict(status="TD_BUCKETED_DIAGNOSTIC_AUDIT_PASS", run_source_T2=42352823564,
                   same_frozen_20=True, original_manifest_sha=manifest, source_count=len(rows),
                   old_hits=sum(bool(r["stream_hit"]) for r in rows),
                   exact_hits=sum(r["exact"].get("total_hits",0) for r in rows),
                   new_source_cases=sum(bool(r["exact"].get("total_hits",0)) and not r["stream_hit"]
                                        for r in rows),
                   inconclusive_cases=sum(not r["exact"]["complete"] for r in rows),
                   old_total_s=round(sum(r["stream_s"] for r in rows),6),
                   exact_total_s=round(sum(r["exact_s"] for r in rows),6),
                   independent_unsat_proof=False, solver_unchanged=True, solver_par2_measured=False,
                   note="Detection-only diagnostic. Full source replay and SAT/UNSAT causal ablation required before solver use.")
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    (OUT/"cases.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    print("TD_BUCKETED_FINAL",json.dumps(summary,sort_keys=True),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("selftest","run"))
    args=parser.parse_args()
    if args.command=="selftest":
        selftest()
    else:
        run()

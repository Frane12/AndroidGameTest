#!/usr/bin/env python3
"""T2 bounded streaming full-file XOR hint; NEVER a proof or eligibility certificate.

Unlike R2's first-5000-groups veto, this scan continues across the original
DIMACS. It drops low-information groups at deterministic memory boundaries,
so its negative result is INCONCLUSIVE, not evidence of no XOR in the CNF.
The exact source re-extraction and independent proof replay are still required.
"""
import hashlib
from pathlib import Path

MAX_BYTES = 8_000_000
MAX_LIVE_GROUPS = 5000
RETAIN_PARTIAL = 512

def cheap_probe(source, max_live=MAX_LIVE_GROUPS, retain=RETAIN_PARTIAL):
    source = Path(source)
    nbytes = source.stat().st_size
    info = dict(clauses_scanned=0, groups_seen=0, evictions=0,
                retained_groups=0, hit_clause=0, size_bytes=nbytes,
                incomplete_scan=False, qualified_masks=0)
    if nbytes > MAX_BYTES or nbytes < 300:
        return False, "size_gate", info
    groups = {}
    clause = []
    with source.open("r", errors="replace") as stream:
        for line in stream:
            if line.lstrip().startswith(("c", "p", "%")):
                continue
            for tok in line.split():
                try:
                    lit = int(tok)
                except ValueError:
                    return False, "invalid_dimacs_token", info
                if lit != 0:
                    if len(clause) <= 6:
                        clause.append(lit)
                    continue
                info["clauses_scanned"] += 1
                if 2 <= len(clause) <= 6 and len({abs(v) for v in clause}) == len(clause):
                    ordered = sorted(clause, key=abs)
                    key = tuple(abs(v) for v in ordered)
                    bitmask = sum((1 << i) for i, v in enumerate(ordered) if v < 0)
                    if key not in groups:
                        info["groups_seen"] += 1
                    masks = groups.setdefault(key, set())
                    masks.add(bitmask)
                    width = len(key)
                    half = 1 << (width - 1)
                    if len(masks) >= half:
                        for parity in (0, 1):
                            if all(x in masks for x in range(1 << width)
                                   if (x.bit_count() & 1) == parity):
                                info["hit_clause"] = info["clauses_scanned"]
                                info["qualified_masks"] = len(masks)
                                return True, "source_complete_xor_streamed_hint", info
                    if len(groups) >= max_live:
                        # Keep repeated-mask candidates across a boundary.
                        # A deterministic partial-group eviction is safe because
                        # this probe can only authorise the proof stage, not infer a fact.
                        keep = sorted(
                            ((key, masks) for key, masks in groups.items() if len(masks) >= 2),
                            key=lambda z: (-len(z[1]), z[0]))[:retain]
                        groups = {key: masks for key, masks in keep}
                        info["evictions"] += 1
                        info["retained_groups"] += len(keep)
                        info["incomplete_scan"] = True
                clause = []
    return False, ("no_complete_xor_in_bounded_stream"
                   if info["incomplete_scan"] else "no_source_complete_xor"), info

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "late.cnf"
        clauses = [f"{i} {i+10000} 0" for i in range(1, 6100)]
        # All four forbidden assignments of a three-variable XOR parity.
        for mask in (0, 3, 5, 6):
            clauses.append(" ".join(str(-v if mask & (1 << j) else v)
                                    for j, v in enumerate((25001, 25002, 25003))) + " 0")
        p.write_text("p cnf 25003 " + str(len(clauses)) + "\n" + "\n".join(clauses) + "\n")
        yes, reason, stats = cheap_probe(p)
        assert yes and stats["evictions"] >= 1 and stats["hit_clause"] >= 6100, (reason,stats)
        q = Path(d) / "without.cnf"
        q.write_text("p cnf 25003 " + str(len(clauses)-4) + "\n" + "\n".join(clauses[:-4]) + "\n")
        no, reason2, info = cheap_probe(q)
        assert not no and info["evictions"] >= 1, (reason2,info)
        print("ULTIMATE_T2_STREAMING_PROBE_SELFTEST_PASS", stats, flush=True)

if __name__ == "__main__":
    selftest()

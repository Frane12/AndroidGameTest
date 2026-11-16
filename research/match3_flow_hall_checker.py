#!/usr/bin/env python3
"""Independent MATCH3 proof checker: only ORIGINAL DIMACS and the Hall witness.

Rebuilds source capacity premises; does not import the producer, max-flow
code, learned classifications, or generated fixture metadata. Not DRAT,
LRAT or VeriPB; certification is limited to this explicit source logic.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

FORMAT = "DRNAS-MATCH3-FLOW-HALL-SOURCE-V1"
MAX_CHECKS = 200000

def parse_original(raw):
    if len(raw) > 6000000:
        raise ValueError("input_budget")
    nv = nc = None
    clauses, unfinished = [], []
    for line in raw.decode("ascii").splitlines():
        row = line.split()
        if not row or row[0] == "c":
            continue
        if row[0] == "p":
            if nv is not None or len(row) != 4 or row[1] != "cnf":
                raise ValueError("DIMACS_header")
            nv, nc = int(row[2]), int(row[3])
            if not (0 <= nv <= 100000 and 0 <= nc <= 100000):
                raise ValueError("DIMACS_limits")
            continue
        if nv is None:
            raise ValueError("DIMACS_missing_header")
        for token in row:
            lit = int(token)
            if abs(lit) > nv:
                raise ValueError("DIMACS_literal_range")
            if lit:
                unfinished.append(lit)
                if len(unfinished) > 2400:
                    raise ValueError("DIMACS_clause_length")
            else:
                clauses.append(frozenset(unfinished))
                unfinished = []
    if nv is None or unfinished or len(clauses) != nc:
        raise ValueError("DIMACS_incomplete")
    return nv, nc, set(clauses)

def verify(raw, cert):
    if (cert.get("format") != FORMAT or cert.get("method") != "MATCH3-FLOW-HALL"
            or cert.get("status") != "UNSAT_UNCHECKED"):
        raise ValueError("claim_format")
    if cert.get("source_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("source_hash")
    nv, nc, source = parse_original(raw)
    groups, resources, caps = (cert.get(k) for k in ("groups", "resources", "capacities"))
    S = cert.get("hall_jobs")
    if not isinstance(groups, list) or not 2 <= len(groups) <= 200:
        raise ValueError("bad_groups")
    if not isinstance(resources, list) or not 1 <= len(resources) <= 1000:
        raise ValueError("bad_resources")
    if not isinstance(caps, list) or len(caps) != len(resources):
        raise ValueError("bad_capacities")
    if (not isinstance(S, list) or not S or
            any(type(j) != int or not 0 <= j < len(groups) for j in S) or
            len(S) != len(set(S))):
        raise ValueError("bad_hall_subset")
    if cert.get("source_variables") != nv or cert.get("source_clauses") != nc:
        raise ValueError("source_counts")
    if cert.get("jobs") != len(groups) or cert.get("resource_count") != len(resources):
        raise ValueError("structure_counts")
    owner = {}
    for j, group in enumerate(groups):
        if not isinstance(group, list) or not 2 <= len(group) <= 16:
            raise ValueError("group_width")
        if any(type(v) != int or not 1 <= v <= nv for v in group):
            raise ValueError("selector_type")
        if len(set(group)) != len(group) or frozenset(group) not in source:
            raise ValueError("source_ALO_absent")
        for v in group:
            if v in owner:
                raise ValueError("selector_reuse")
            owner[v] = j
    if len(owner) > 2400:
        raise ValueError("selector_budget")
    active = {v for v in owner if frozenset((-v,)) not in source}
    seen, neighbors = set(), set()
    subset = set(S)
    total_checks = 0
    bound = 0
    for r, (resource, cap) in enumerate(zip(resources, caps)):
        if (not isinstance(resource, list) or not resource or
                any(type(v) != int or v not in owner for v in resource) or
                len(set(resource)) != len(resource)):
            raise ValueError("bad_resource_selectors")
        if seen.intersection(resource):
            raise ValueError("resource_overlap")
        seen.update(resource)
        avail = [v for v in resource if v in active]
        eligible = {owner[v] for v in avail}
        if type(cap) != int or not 0 <= cap <= len(eligible):
            raise ValueError("bad_resource_capacity")
        if cap < len(eligible):
            if cap == 0:
                raise ValueError("zero_cap_with_active_selectors")
            possible = math.comb(len(avail), cap + 1)
            if possible > MAX_CHECKS - total_checks:
                raise ValueError("verification_budget")
            for selected in itertools.combinations(avail, cap + 1):
                if len({owner[v] for v in selected}) != cap + 1:
                    continue
                total_checks += 1
                if frozenset(-v for v in selected) not in source:
                    raise ValueError("unjustified_source_capacity")
        if eligible.intersection(subset):
            neighbors.add(r)
            bound += cap
    if seen != set(owner):
        raise ValueError("unmapped_ALO_selector")
    if bound >= len(subset):
        raise ValueError("no_Hall_deficiency")
    if cert.get("capacity_bound") != bound or cert.get("deficiency") != len(subset) - bound:
        raise ValueError("altered_Hall_arithmetic")
    return {"status": "MATCH3_SOURCE_HALL_UNSAT_VERIFIED",
            "jobs": len(groups), "resources": len(resources),
            "hall_jobs": len(subset), "neighbor_resources": len(neighbors),
            "capacity_bound": bound, "deficiency": len(subset) - bound,
            "source_tuple_checks": total_checks,
            "source_sha256": hashlib.sha256(raw).hexdigest()}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cnf", type=Path)
    ap.add_argument("certificate", type=Path)
    a = ap.parse_args()
    try:
        result = verify(a.cnf.read_bytes(), json.loads(a.certificate.read_text()))
        print("MATCH3_FLOW_VERIFIED " + json.dumps(result, sort_keys=True), flush=True)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, UnicodeError) as exc:
        print("MATCH3_FLOW_REJECT " + str(exc), flush=True)
        raise SystemExit(1)

#!/usr/bin/env python3
"""MATCH3-FLOW-HALL: original-CNF, polynomial Hall/min-cut detector.

This proves UNSAT only after source clauses establish disjoint ALO job
groups and direct resource capacity upper bounds. A Dinic max-flow exposes
a violating Hall set. This is NOT a general SAT algorithm, not a PCMAX
decoder, and not a standardized UNSAT proof format.
"""
import argparse
import hashlib
import itertools
import json
import math
from collections import defaultdict, deque
from pathlib import Path

FORMAT = "DRNAS-MATCH3-FLOW-HALL-SOURCE-V1"
MAX_JOBS = 200
MAX_SELECTORS = 2400
MAX_CLAUSES = 100000
MAX_TUPLES = 150000

def parse(raw):
    if len(raw) > 6000000:
        raise ValueError("byte_budget")
    nv = nc = None
    clauses, pending = [], []
    for line in raw.decode("ascii").splitlines():
        bits = line.split()
        if not bits or bits[0] == "c":
            continue
        if bits[0] == "p":
            if nv is not None or len(bits) != 4 or bits[1] != "cnf":
                raise ValueError("header")
            nv, nc = map(int, bits[2:])
            if not (0 <= nv <= 100000 and 0 <= nc <= MAX_CLAUSES):
                raise ValueError("header_limits")
            continue
        if nv is None:
            raise ValueError("missing_header")
        for item in bits:
            x = int(item)
            if abs(x) > nv:
                raise ValueError("out_of_range")
            if x:
                pending.append(x)
                if len(pending) > 2400:
                    raise ValueError("large_clause")
            else:
                clauses.append(tuple(pending))
                pending = []
    if nv is None or pending or len(clauses) != nc:
        raise ValueError("incomplete_source")
    return nv, clauses

def groups_from_source(clauses):
    groups = [list(c) for c in clauses
              if 2 <= len(c) <= 16 and all(v > 0 for v in c)
              and len(set(c)) == len(c)]
    if not (2 <= len(groups) <= MAX_JOBS):
        return None
    used = set()
    for g in groups:
        if not used.isdisjoint(g):
            return None
        used.update(g)
    if len(used) > MAX_SELECTORS:
        return None
    return groups

def infer_resources(groups, clauses):
    owner = {v: j for j, g in enumerate(groups) for v in g}
    parent = {v: v for v in owner}
    def root(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    def union(a, b):
        a, b = root(a), root(b)
        if a != b:
            parent[max(a, b)] = min(a, b)
    for c in clauses:
        if not (2 <= len(c) <= 4 and all(v < 0 and -v in owner for v in c)):
            continue
        if len({owner[-v] for v in c}) != len(c):
            continue
        for v in c[1:]:
            union(-c[0], -v)
    resources = defaultdict(list)
    for v in sorted(owner):
        resources[root(v)].append(v)
    return sorted(resources.values(), key=lambda r: r[0])

def derive_caps(groups, resources, clauses):
    owner = {v: j for j, g in enumerate(groups) for v in g}
    src = {frozenset(c) for c in clauses}
    active = {v for v in owner if frozenset((-v,)) not in src}
    caps, checked = [], 0
    for r in resources:
        vs = [v for v in r if v in active]
        upper = len({owner[v] for v in vs})
        cap = upper  # Always a safe but potentially uninformative bound.
        for q in (1, 2, 3):
            if q >= upper:
                break
            combinations = math.comb(len(vs), q + 1)
            if checked + combinations > MAX_TUPLES:
                break
            complete = True
            for tup in itertools.combinations(vs, q + 1):
                checked += 1
                if len({owner[v] for v in tup}) < q + 1:
                    continue
                if frozenset(-v for v in tup) not in src:
                    complete = False
                    break
            if complete:
                cap = q
                break
        caps.append(cap)
    return caps, active, checked

class Dinic:
    def __init__(self, nodes):
        self.graph = [[] for _ in range(nodes)]
    def edge(self, a, b, cap):
        self.graph[a].append([b, cap, len(self.graph[b])])
        self.graph[b].append([a, 0, len(self.graph[a]) - 1])
    def flow(self, s, t):
        total = 0
        while True:
            level = [-1] * len(self.graph)
            level[s] = 0
            queue = deque([s])
            while queue:
                u = queue.popleft()
                for v, cap, _ in self.graph[u]:
                    if cap and level[v] < 0:
                        level[v] = level[u] + 1
                        queue.append(v)
            if level[t] < 0:
                break
            ptr = [0] * len(self.graph)
            def push(u, amt):
                if u == t:
                    return amt
                while ptr[u] < len(self.graph[u]):
                    eid = ptr[u]
                    v, cap, rev = self.graph[u][eid]
                    if cap and level[v] == level[u] + 1:
                        got = push(v, min(amt, cap))
                        if got:
                            self.graph[u][eid][1] -= got
                            self.graph[v][rev][1] += got
                            return got
                    ptr[u] += 1
                return 0
            while True:
                inc = push(s, MAX_JOBS + 1)
                if not inc:
                    break
                total += inc
        return total
    def reachable(self, start):
        seen = {start}
        todo = [start]
        while todo:
            u = todo.pop()
            for v, cap, _ in self.graph[u]:
                if cap and v not in seen:
                    seen.add(v)
                    todo.append(v)
        return seen

def hall_cut(groups, resources, caps, active):
    n, m = len(groups), len(resources)
    owner = {v: j for j, g in enumerate(groups) for v in g}
    allowed = [set() for _ in range(n)]
    for r, vals in enumerate(resources):
        for v in vals:
            if v in active:
                allowed[owner[v]].add(r)
    src, sink = 0, 1 + n + m
    g = Dinic(sink + 1)
    for j in range(n):
        g.edge(src, 1 + j, 1)
        for r in sorted(allowed[j]):
            g.edge(1 + j, 1 + n + r, 1)
    for r, c in enumerate(caps):
        g.edge(1 + n + r, sink, c)
    maxflow = g.flow(src, sink)
    if maxflow == n:
        return None, maxflow
    reach = g.reachable(src)
    S = [j for j in range(n) if 1 + j in reach]
    neigh = {r for j in S for r in allowed[j]}
    bound = sum(caps[r] for r in neigh)
    # This also guards against implementation mistakes in the flow routine.
    if not S or bound >= len(S):
        return None, maxflow
    return (S, bound), maxflow

def prove(raw):
    out = {"format": FORMAT, "source_sha256": hashlib.sha256(raw).hexdigest(),
           "status": "UNKNOWN", "method": "NONE"}
    try:
        nv, clauses = parse(raw)
        groups = groups_from_source(clauses)
        if groups is None:
            out["reason"] = "no_disjoint_source_ALO"
            return out
        resources = infer_resources(groups, clauses)
        if len(resources) > 1000:
            out["reason"] = "resource_budget"
            return out
        caps, active, checked = derive_caps(groups, resources, clauses)
        cut, maxflow = hall_cut(groups, resources, caps, active)
        out.update({"jobs": len(groups), "resource_count": len(resources),
                    "source_variables": nv, "source_clauses": len(clauses),
                    "maxflow": maxflow, "capacity_tuple_checks": checked})
        if cut is not None:
            subset, bound = cut
            out.update({"status": "UNSAT_UNCHECKED", "method": "MATCH3-FLOW-HALL",
                        "groups": groups, "resources": resources,
                        "capacities": caps, "hall_jobs": subset,
                        "capacity_bound": bound,
                        "deficiency": len(subset) - bound})
        else:
            out["reason"] = "flow_relaxation_feasible_or_unknown"
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        out["reason"] = type(exc).__name__
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cnf", type=Path)
    ap.add_argument("--certificate", required=True, type=Path)
    a = ap.parse_args()
    proof = prove(a.cnf.read_bytes())
    a.certificate.parent.mkdir(parents=True, exist_ok=True)
    a.certificate.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print("MATCH3_FLOW_PRODUCER " + json.dumps(
        {k: v for k, v in proof.items() if k not in ("groups", "resources")}, sort_keys=True),
        flush=True)

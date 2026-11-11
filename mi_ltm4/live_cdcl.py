"""LTM4.1 passive CDCL trajectory mining from real native DRNAS MICRO_EVENT logs.

This module is observational. The C++ solver's existing DRNAS_MICRO_TRACE
compile-time switch logs decisions, assignments, conflicts, 1-UIP learning,
and a bounded subset of *actual* reason-graph edges. No solver decisions,
clauses, branching rules, or SAT/UNSAT statuses are changed.

A "trajectory" is a time-ordered event *episode*, not a formal proof; only
REDUCE2_EDGE records reflect native reason dependencies. Pattern keys strip
variable/clause IDs to compare episodes across disjoint formulas.
"""
from collections import Counter, defaultdict
import hashlib
import json
import re

MAX_EVENTS = 10000
MAX_EPISODES = 128
MAX_REASON_NODES = 256


def kv(line):
    return dict(re.findall(r"([a-zA-Z_]+)=([^\s]+)", line))


def bucket(n):
    n = max(0, int(n))
    return "0" if n == 0 else "1" if n == 1 else "2-3" if n < 4 else (
        "4-7" if n < 8 else "8-15" if n < 16 else "16+")


def _motif(data):
    # The learner NEVER sees literal IDs, SHA, clause IDs or SAT outcome.
    fields = {
        "version": 1,
        "stage": "native_cdcl_observed",
        "decision_depth": bucket(data["level"]),
        "bcp_since_decision": bucket(data["bcp"]),
        "decision_seen": bool(data["decision_seen"]),
        "learned_width": bucket(data["width"]),
        "backjump_distance": bucket(data["jump"]),
        "reason_original": bucket(data["original_nodes"]),
        "reason_learned": bucket(data["learned_nodes"]),
        "reason_edges": bucket(data["reason_edges"]),
    }
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return "cdcl4:" + hashlib.sha256(payload.encode()).hexdigest()[:24], fields


def parse_native_log(stderr, *, max_episodes=MAX_EPISODES):
    """Bounded event parser, groups a conflict and its subsequent 1-UIP learn.

    The observed BCP burst is counted after the most recent decision event.
    The reason subgraph is real only when REDUCE2_NODE/EDGE occurs. Any
    unobserved reason graph gets zeros and reason_available=False.
    """
    if max_episodes <= 0 or max_episodes > 10000:
        raise ValueError("Bad episode bound")
    episodes = []
    reasons = defaultdict(lambda: dict(nodes={}, edges=set()))
    event_count = 0
    saturated = False
    last_seq = 0
    bcp = 0
    decision_seen = False
    pending = None
    decisions = 0
    conflicts = 0
    learns = 0
    assignments = 0
    for raw in stderr.splitlines():
        if raw.startswith("REDUCE2_NODE "):
            p = kv(raw)
            try:
                conflict = int(p["conflict"])
                cid = int(p["cid"])
                learned = int(p["learned"])
                width = len(p.get("clause", "").split(",")) if p.get("clause") else 0
            except (KeyError, ValueError):
                continue
            if len(reasons[conflict]["nodes"]) < MAX_REASON_NODES:
                reasons[conflict]["nodes"][cid] = (learned, width)
        elif raw.startswith("REDUCE2_EDGE "):
            p = kv(raw)
            try:
                conflict = int(p["conflict"])
                a, b = int(p["from"]), int(p["to"])
            except (KeyError, ValueError):
                continue
            if len(reasons[conflict]["edges"]) < MAX_REASON_NODES*2:
                reasons[conflict]["edges"].add((a,b))
        elif raw.startswith("MICRO_EVENT "):
            p = kv(raw)
            try:
                seq = int(p["seq"])
            except (KeyError, ValueError):
                continue
            if seq <= last_seq:
                raise AssertionError("Nonmonotone native trace sequence")
            last_seq = seq
            event_count += 1
            # Native tracing stops writing after the first 10,000 events.
            if event_count >= MAX_EVENTS:
                saturated = True
            kind = p.get("kind")
            if kind == "decision":
                decisions += 1
                decision_seen = True
                bcp = 0
            elif kind == "assign":
                assignments += 1
                if p.get("reason") != "-1":
                    bcp += 1
            elif kind == "conflict":
                conflicts += 1
                pending = {
                    "number": int(p.get("number", -1)),
                    "level": int(p.get("level", 0)),
                    "bcp": bcp,
                    "decision_seen": decision_seen,
                }
            elif kind == "learn":
                learns += 1
                if pending is None:
                    continue
                if len(episodes) >= max_episodes:
                    saturated = True
                    pending = None
                    continue
                number = pending["number"]
                graph = reasons.pop(number, {"nodes":{}, "edges":set()})
                width = int(p.get("width", 0))
                jump = max(0, int(p.get("from", 0))-int(p.get("backjump", 0)))
                counts = Counter(learned for learned,_ in graph["nodes"].values())
                candidate = dict(
                    level=pending["level"],
                    bcp=pending["bcp"],
                    decision_seen=pending["decision_seen"],
                    width=width,
                    jump=jump,
                    original_nodes=counts[0],
                    learned_nodes=counts[1],
                    reason_edges=len(graph["edges"]))
                key,features = _motif(candidate)
                episodes.append({
                    "key":key, "features":features,
                    "outcome":"observed_1UIP_learn",
                    "native_conflict_index":number,
                    "reason_graph_available":bool(graph["nodes"]),
                    "reason_nodes":len(graph["nodes"]),
                    "reason_edges":len(graph["edges"]),
                    "reason_graph_type":"native_dependency" if graph["edges"]
                                        else "not_captured",
                    "observational_only":True})
                pending = None
    return dict(
        kind="passive_native_cdcl_trace",
        episodes=episodes,
        total_native_micro_events=event_count,
        observed_decisions=decisions,
        observed_assignments=assignments,
        observed_conflicts=conflicts,
        observed_learns=learns,
        reason_graph_conflicts=sum(e["reason_graph_available"] for e in episodes),
        trace_saturated=saturated,
        note="Temporal patterns are NOT causal proofs; only explicit REDUCE2_EDGE data are reason dependencies.")


def aggregate_by_formula(formula_traces):
    """Count each motif once per distinct original SHA, not per seed/event."""
    seen = defaultdict(set)
    events = Counter()
    for item in formula_traces:
        sha = item["sha256"]
        for episode in item["trace"]["episodes"]:
            seen[episode["key"]].add(sha)
            events[episode["key"]] += 1
    return dict(distinct_formulas=len({x["sha256"] for x in formula_traces}),
                unique_native_motifs=len(seen),
                support_formulas={k:len(v) for k,v in seen.items()},
                episode_counts=dict(events))

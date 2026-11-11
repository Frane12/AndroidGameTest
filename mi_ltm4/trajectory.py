"""DRNAS MI-LTM4: bounded, proof-audited relational *trajectory* extraction.

Diagnostic only. Every source XOR must be implied by the CURRENT original CNF.
Every endpoint is independently checked as a GF(2) sum of those source rows.
Motif keys ignore variable names and source row order. They are not proofs.
This first adapter captures XOR algebraic trajectories, NOT native CDCL trails.
"""
from collections import Counter
from itertools import permutations
from pathlib import Path
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mi_ltm1"))
sys.path.insert(0, str(ROOT / "mi_ltm3"))
from probe import parse_dimacs, probe_cnf
from xor_multistep import closure, audit_provenance


def _audit_source(equation, source):
    """Verify the full parity-forbidding CNF encoding is present."""
    vs = tuple(equation["variables"])
    rhs = equation["rhs"]
    if not (2 <= len(vs) <= 3 and len(vs) == len(set(vs)) and
            all(isinstance(v, int) and v > 0 for v in vs) and rhs in (0, 1)):
        return False
    for mask in range(1 << len(vs)):
        if mask.bit_count() % 2 == rhs:
            continue
        clause = frozenset(-v if mask & (1 << i) else v
                           for i, v in enumerate(vs))
        if clause not in source:
            return False
    return True


def canonical_trajectory(equations, outcome):
    """Exact renaming-invariant fingerprint for 2..4 XOR source equations.

    Iterate up to 4! source-row orders. Variable membership bit-vectors
    fully encode the local XOR hypergraph up to variable relabeling.
    Choosing a minimum-peak elimination path is a deterministic mathematical
    *description*, not evidence the CDCL solver followed that path.
    """
    if not 2 <= len(equations) <= 4:
        raise ValueError("Expected 2..4 source rows")
    rows = [(frozenset(int(v) for v in eq["variables"]), int(eq["rhs"]))
            for eq in equations]
    if any(not vs or rhs not in (0, 1) for vs, rhs in rows):
        raise ValueError("Invalid source rows")
    candidates = []
    for order in permutations(range(len(rows))):
        chosen = [rows[i] for i in order]
        universe = set().union(*(vs for vs, _ in chosen))
        memberships = tuple(sorted(
            tuple(int(v in chosen[i][0]) for i in range(len(chosen)))
            for v in universe))
        prefix = set(chosen[0][0])
        widths = [len(prefix)]
        rhs = chosen[0][1]
        for vs, parity in chosen[1:]:
            prefix.symmetric_difference_update(vs)
            rhs ^= parity
            widths.append(len(prefix))
        structural = (tuple((len(vs), parity) for vs, parity in chosen),
                      memberships, tuple(widths),
                      (len(prefix), rhs, outcome))
        candidates.append((max(widths), sum(widths), structural, order))
    _, _, structure, order = min(candidates)
    encoded = json.dumps(structure, separators=(",", ":"))
    key = "traj4:" + hashlib.sha256(encoded.encode()).hexdigest()[:24]
    return key, list(order), list(structure[2])


def episode_from_proof(source_equations, consequence):
    """Return a small, replayable DAG description or abstain."""
    indices = consequence.get("source_equations", [])
    if (not isinstance(indices, list) or not 2 <= len(indices) <= 4 or
            len(set(indices)) != len(indices) or
            not audit_provenance(source_equations, consequence)):
        return None
    rows = [source_equations[i] for i in indices]
    key, order, widths = canonical_trajectory(rows, consequence["kind"])
    ordered_sources = [indices[i] for i in order]
    nodes = []
    edges = []
    for idx, source_id in enumerate(ordered_sources):
        eq = source_equations[source_id]
        nodes.append({"id": idx, "kind": "certified_xor",
                      "arity": len(eq["variables"]), "rhs": eq["rhs"]})
    previous = 0
    for step in range(1, len(rows)):
        node_id = len(nodes)
        nodes.append({"id": node_id, "kind": "gf2_combine",
                      "result_width": widths[step]})
        edges.extend([[previous, node_id], [step, node_id]])
        previous = node_id
    endpoint_id = len(nodes)
    nodes.append({"id": endpoint_id, "kind": consequence["kind"],
                  "arity": len(consequence["variables"]),
                  "rhs": consequence["rhs"]})
    edges.append([previous, endpoint_id])
    return {
        "key": key, "kind": consequence["kind"],
        "source_count": len(rows), "elimination_steps": len(rows)-1,
        "intermediate_widths": widths, "peak_width": max(widths),
        "nodes": nodes, "edges": edges,
        # Provenance remains local to this original CNF only:
        "source_equation_indices": sorted(indices),
        "verified": True
    }


def extract(raw, *, max_clauses=10000, max_rows=96, max_motifs=48,
            max_steps=12000, max_chain_s=0.012):
    """Build source-audited XOR trajectories; never inject any deductions."""
    started = time.perf_counter()
    report = probe_cnf(raw, max_clauses=max_clauses, max_rows=max_rows)
    if report["status"] != "diagnostic_only":
        return {"status": "abstain", "reason": report.get("reason", "probe"),
                "episodes": [], "elapsed_s": time.perf_counter()-started}
    source = set(frozenset(cl) for cl in parse_dimacs(raw))
    equations = report["xor_equations"][:max_rows]
    if any(not _audit_source(eq, source) for eq in equations):
        raise AssertionError("Uncertified XOR in original CNF")
    derived = closure(equations, max_rows=max_rows, max_steps=max_steps,
                      max_output=max_motifs*3, budget_s=max_chain_s)
    episodes = {}
    for consequence in derived["consequences"]:
        ep = episode_from_proof(equations, consequence)
        if ep is None:
            continue
        # A formula contributes at most one vote per motif.
        if ep["key"] not in episodes:
            episodes[ep["key"]] = ep
        if len(episodes) >= max_motifs:
            break
    return {"status": "diagnostic_only", "episodes": list(episodes.values()),
            "source_equations": len(equations),
            "closure_operations": derived["elimination_ops"],
            "closure_truncated": derived["truncated"],
            "elapsed_s": time.perf_counter()-started,
            "note": "Offline XOR proof trajectories only; no CDCL path or causal benefit claimed."}


def episode_counts(report):
    return Counter(e["kind"] for e in report["episodes"])

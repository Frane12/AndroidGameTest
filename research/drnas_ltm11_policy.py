#!/usr/bin/env python3
"""LTM11 experimental structural router with censored-progress diagnostics.

Only verified original-CNF solutions affect the gate that enables a new policy.
Timeout progress is diagnostic/tie-breaking ONLY; no claim of a solved formula.
The frozen policy stores no filename, label or SHA as a routing feature.
"""
import collections
import hashlib
import json
import math
import pathlib
import statistics
import tempfile
import time

SCHEMA = "ltm11-structural-v1"
BASE = "LTM9_FAST"
ARMS = ("LTM9_FAST", "LTM8_FAST", "LTM8_CHAOS")
FEATURES = ("log_vars", "log_clauses", "binary", "ternary", "unit", "long",
            "positive", "mean_width", "mixed_polarity", "hub_ratio",
            "duplicate_sample", "binary_degree")
SAMPLE_BYTES = 192 * 1024
SAMPLE_CLAUSES = 2048

def extract(path):
    """Bounded prefix sample, O(192 KiB), not full-CNF parsing or full graph."""
    start = time.monotonic()
    n = m = None
    clause = []
    widths = collections.Counter()
    positive = negative = lit_count = 0
    pos = collections.Counter()
    neg = collections.Counter()
    degrees = collections.Counter()
    seen_clauses = set()
    dup = binary_edges = total = bytes_read = 0
    with open(path, "rb") as fd:
        while bytes_read < SAMPLE_BYTES and total < SAMPLE_CLAUSES:
            line = fd.readline(min(8192, SAMPLE_BYTES - bytes_read))
            if not line:
                break
            bytes_read += len(line)
            if not line.endswith(b"\n") and bytes_read >= SAMPLE_BYTES:
                break  # Do not use a truncated clause or comment.
            stripped = line.strip()
            if not stripped or stripped.startswith((b"c", b"%")):
                continue
            if stripped.startswith(b"p "):
                header = stripped.split()
                if len(header) != 4 or header[1] != b"cnf" or n is not None:
                    raise ValueError("bad DIMACS header")
                n, m = int(header[2]), int(header[3])
                if not (0 < n <= 10_000_000 and m >= 0):
                    raise ValueError("unsafe DIMACS header")
                continue
            if n is None:
                raise ValueError("missing DIMACS header")
            for token in stripped.split():
                v = int(token)
                if v:
                    if abs(v) > n:
                        raise ValueError("literal outside DIMACS variables")
                    clause.append(v)
                    continue
                # Completed clause.
                k = len(clause)
                widths["unit"] += (k == 1)
                widths["binary"] += (k == 2)
                widths["ternary"] += (k == 3)
                widths["long"] += (k >= 8)
                lit_count += k
                positive += sum(x > 0 for x in clause)
                negative += sum(x < 0 for x in clause)
                for x in clause:
                    a = abs(x)
                    degrees[a] += 1
                    if x > 0:
                        pos[a] += 1
                    else:
                        neg[a] += 1
                binary_edges += (k == 2)
                key = tuple(sorted(set(clause)))
                if key in seen_clauses:
                    dup += 1
                else:
                    seen_clauses.add(key)
                total += 1
                clause = []
                if total >= SAMPLE_CLAUSES:
                    break
    if n is None:
        raise ValueError("no DIMACS header")
    d = max(total, 1)
    active = max(len(degrees), 1)
    balanced = sum(1 for x in degrees if pos[x] and neg[x])
    avg = sum(degrees.values()) / active
    feature = dict(
        log_vars=math.log1p(n), log_clauses=math.log1p(m),
        binary=widths["binary"] / d, ternary=widths["ternary"] / d,
        unit=widths["unit"] / d, long=widths["long"] / d,
        positive=positive / max(1, lit_count),
        mean_width=lit_count / d,
        mixed_polarity=balanced / active,
        hub_ratio=max(degrees.values(), default=0) / max(avg, 1e-8),
        duplicate_sample=dup / d,
        binary_degree=2 * binary_edges / active)
    return feature, time.monotonic() - start

def progress(row):
    """A diagnostic for observable native counters; missing is NOT zero."""
    conflicts, decisions = row.get("conflicts"), row.get("decisions")
    if conflicts is None or decisions is None:
        return None
    if conflicts < 0 or decisions < 0:
        return None
    return math.log1p(conflicts) / (1 + math.log1p(decisions))

def verified_cost(row):
    return float(row["PAR2_verified_s"])

def blank(status="fallback"):
    return dict(schema=SCHEMA, enabled=False, default=BASE,
                predicates=[], alternate=None, status=status)

def pick(model, feature):
    if model["schema"] != SCHEMA:
        raise ValueError("policy version mismatch")
    if not model["enabled"]:
        return BASE
    for item in model["predicates"]:
        if item["feature"] not in FEATURES:
            raise ValueError("invalid feature")
        matched = feature[item["feature"]] <= item["threshold"]
        if bool(matched) != bool(item["less_equal"]):
            return BASE
    if model["alternate"] not in ARMS or model["alternate"] == BASE:
        raise ValueError("invalid alternate")
    return model["alternate"]

def evaluate(model, pairs):
    gain = 0.0
    improvements = regressions = switched = 0
    progress_delta = 0.0
    progress_pairs = 0
    for feature, rows in pairs:
        chosen = pick(model, feature)
        if chosen == BASE:
            continue
        switched += 1
        a, b = rows[BASE], rows[chosen]
        delta = verified_cost(a) - verified_cost(b)
        gain += delta
        if delta > 0.05:
            improvements += 1
        if delta < -0.10:
            regressions += 1
        ap, bp = progress(a), progress(b)
        if ap is not None and bp is not None:
            progress_delta += bp - ap
            progress_pairs += 1
    return dict(gain_s=round(gain, 6), improvements=improvements,
                regressions=regressions, switched=switched,
                progress_pairs=progress_pairs,
                diagnostic_progress_delta=round(progress_delta, 6))

def fit(train, validation):
    """All candidate thresholds and rankings use TRAIN only.

    VALIDATION tests exactly the highest training-ranked hypothesis.
    Unverified UNSAT and timeout progress cannot activate a policy.
    """
    if len(train) < 15 or len(validation) < 5:
        raise ValueError("insufficient disjoint training and validation")
    atoms = []
    for name in FEATURES:
        values = sorted(set(float(f[name]) for f, _ in train))
        if len(values) < 3:
            continue
        for fraction in (0.25, 0.50, 0.75):
            threshold = values[min(len(values) - 2, int(fraction * (len(values)-1)))]
            for leq in (True, False):
                atom = dict(feature=name, threshold=round(threshold, 8),
                            less_equal=leq)
                if atom not in atoms:
                    atoms.append(atom)
    candidates = []
    for i, a in enumerate(atoms):
        predicates = [[a]]
        # Two-feature conjunctive patterns; same-feature pairings are excluded.
        predicates += [[a, b] for b in atoms[i+1:] if b["feature"] != a["feature"]]
        for pred in predicates:
            for alternate in ARMS:
                if alternate == BASE:
                    continue
                model = dict(blank("candidate"), enabled=True,
                             predicates=pred, alternate=alternate)
                stat = evaluate(model, train)
                if not (5 <= stat["switched"] <= len(train)-3):
                    continue
                # Positive verified gain and at least two genuinely solved wins.
                if stat["improvements"] < 2 or stat["gain_s"] <= 0.50:
                    continue
                if stat["regressions"] > 0:
                    continue
                candidates.append((stat["gain_s"],
                                   stat["diagnostic_progress_delta"],
                                   -len(pred), json.dumps(model,sort_keys=True),
                                   model, stat))
    candidates.sort(key=lambda v:(-v[0],-v[1],-v[2],v[3]))
    if not candidates:
        outcome = blank("no-certified-training-benefit")
        outcome["candidate_count"] = 0
        return outcome
    *_, best, train_stat = candidates[0]
    validation_stat = evaluate(best, validation)
    # Two distinct new wins; no meaningful observed regressions.
    approved = (validation_stat["switched"] >= 2
                and validation_stat["improvements"] >= 2
                and validation_stat["regressions"] == 0
                and validation_stat["gain_s"] > 1.0)
    answer = dict(best) if approved else blank("validation-rejected")
    answer.update(status="validated" if approved else "validation-rejected",
                  candidate_count=len(candidates),
                  train_metrics=train_stat, validation_metrics=validation_stat,
                  selected_training_hypothesis=dict(
                      predicates=best["predicates"], alternate=best["alternate"]),
                  train_examples=len(train), validation_examples=len(validation),
                  uses_timeout_counters_for_gate=False)
    return answer

def save(model, path, train_sources, validation_sources):
    m = dict(model, training_hash=hashlib.sha256(
                 json.dumps(sorted(train_sources)).encode()).hexdigest(),
             validation_hash=hashlib.sha256(
                 json.dumps(sorted(validation_sources)).encode()).hexdigest(),
             holdout_used_for_fit=False, source_features="bounded_prefix_cnf",
             progress_metric="diagnostic_only_with_observable_counters")
    pathlib.Path(path).write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    return m

def load(path):
    m = json.loads(pathlib.Path(path).read_text())
    if m.get("schema") != SCHEMA or m.get("default") != BASE:
        raise ValueError("invalid memory version")
    # Enforce schema and predicates through pick(), including enabled rules.
    pick(m, {f:0.0 for f in FEATURES})
    return m

def selftest():
    with tempfile.TemporaryDirectory() as folder:
        p = pathlib.Path(folder)/"a.cnf"
        p.write_text("c tiny\np cnf 4 4\n1 -2 0\n2 3 0\n-3 0\n1 2 0\n")
        f, seconds = extract(p)
        assert seconds >= 0 and f["binary"] == 0.75
        assert f["mixed_polarity"] > 0
        model = blank()
        assert pick(model, f) == BASE
        m = save(model,pathlib.Path(folder)/"memory.json",["train"],["valid"])
        assert load(pathlib.Path(folder)/"memory.json")==m
        progress_row = dict(conflicts=None, decisions=None)
        assert progress(progress_row) is None
        assert verified_cost(dict(PAR2_verified_s=6.0))==6.0
    print("LTM11_POLICY_SELFTEST_PASS feature_limit=192KiB",flush=True)

if __name__ == "__main__":
    selftest()

"""Relational placeholder memory, not a cross-formula clause cache.

Records only structural *patterns* of source-CNF-certified XOR equations,
including a bounded pairwise derivation. A match is diagnostic; any active
consequence must be re-derived from the NEW original CNF and verified.
"""
from collections import Counter
from itertools import combinations

try:
    from .probe import probe_cnf
except ImportError:
    from probe import probe_cnf

SCHEMA = """
CREATE TABLE IF NOT EXISTS xor_templates (
  formula_sha TEXT NOT NULL,
  template_key TEXT NOT NULL,
  relation_kind TEXT NOT NULL,
  PRIMARY KEY(formula_sha, template_key)
);
CREATE INDEX IF NOT EXISTS xor_templates_key ON xor_templates(template_key);
"""


def extract_patterns(original_dimacs):
    report = probe_cnf(original_dimacs)
    if report["status"] != "diagnostic_only":
        return {}
    eqs = report["xor_equations"]
    patterns = {}
    for eq in eqs:
        # Literal renaming does not change arity or the XOR parity.
        key = "source:%d:%d" % (len(eq["variables"]), eq["rhs"])
        patterns[key] = "source_xor"
    for first, second in combinations(eqs, 2):
        a, b = set(first["variables"]), set(second["variables"])
        if len(a) > len(b):
            a, b = b, a
        remaining = a ^ b
        rhs = first["rhs"] ^ second["rhs"]
        if len(remaining) > 2:
            continue
        key = "pair:%d:%d:shared%d:out%d:rhs%d" % (
            len(a), len(b), len(a & b), len(remaining), rhs)
        kind = ("conflict" if len(remaining)==0 and rhs else
                "tautology" if len(remaining)==0 else
                "unit" if len(remaining)==1 else "binary_xor")
        patterns[key] = kind
    return patterns


def init(db):
    db.executescript(SCHEMA)


def remember(db, formula_sha, original_dimacs):
    """Mutates ONLY during training; excludes every holdout formula."""
    patterns = extract_patterns(original_dimacs)
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO xor_templates "
            "(formula_sha,template_key,relation_kind) VALUES (?,?,?)",
            [(formula_sha, key, kind) for key,kind in patterns.items()])
    return patterns


def trained_catalog(db, *, excluded_sha=()):
    forbidden = set(excluded_sha)
    by_key = {}
    for sha,key,kind in db.execute(
            "SELECT formula_sha,template_key,relation_kind FROM xor_templates"):
        if sha in forbidden:
            continue
        info = by_key.setdefault(key, dict(kind=kind, examples=set()))
        if info["kind"] != kind:
            raise AssertionError("Inconsistent stored relation kind")
        info["examples"].add(sha)
    return {key: {"kind": x["kind"], "training_formulas": len(x["examples"])}
            for key,x in by_key.items()}


def diagnose_holdout(holdout_cases, training_catalog):
    seen = Counter()
    by_family = {}
    total_patterns = 0
    for row in holdout_cases:
        observed = extract_patterns(row["raw"])
        total_patterns += len(observed)
        matches = {k:v for k,v in observed.items() if
                   k in training_catalog and training_catalog[k]["kind"] == v}
        if matches:
            seen.update(matches)
        fam = by_family.setdefault(row["family"],dict(
            formulas=0,recognized=0,source_patterns=0,matched_patterns=0))
        fam["formulas"] += 1
        fam["recognized"] += bool(matches)
        fam["source_patterns"] += len(observed)
        fam["matched_patterns"] += len(matches)
    return dict(
        training_template_types=len(training_catalog),
        holdout_formulas=len(holdout_cases),
        holdout_recognized=sum(x["recognized"] for x in by_family.values()),
        holdout_pattern_occurrences=total_patterns,
        matched_pattern_occurrences=sum(seen.values()),
        matched_pattern_types=dict(seen),by_family=by_family)


def forbidden_sha_check(db, forbidden_sha):
    bad = db.execute(
        "SELECT formula_sha FROM xor_templates WHERE formula_sha=? LIMIT 1",
        (forbidden_sha,)).fetchone()
    if bad:
        raise AssertionError("Holdout formula entered training template memory")

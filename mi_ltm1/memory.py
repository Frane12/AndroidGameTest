"""DRNAS MI-LTM1: bounded, advisory long-term intervention memory.

This module NEVER injects clauses or changes SAT/UNSAT conclusions.
A frozen snapshot is required for blind evaluation.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY,
 cohort TEXT NOT NULL,
 formula_sha TEXT NOT NULL,
 signature TEXT NOT NULL,
 arm TEXT NOT NULL,
 baseline_e2e REAL NOT NULL,
 candidate_e2e REAL NOT NULL,
 baseline_solved INTEGER NOT NULL,
 candidate_solved INTEGER NOT NULL,
 cap_s REAL NOT NULL,
 verified INTEGER NOT NULL,
 probe_s REAL NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(cohort,formula_sha,arm)
);
CREATE INDEX IF NOT EXISTS obs_signature ON observations(signature,arm);
"""

def signature(clauses, limit=128):
    """Cheap renaming-invariant *coarse* signature; not a proof of isomorphism.

    Uses clause length, positive/negative literal counts, and occurrence-degree
    distribution. Collisions are expected and must not authorize deductions.
    """
    selected = list(clauses)[:limit]
    degrees = {}
    profiles = []
    for clause in selected:
        lits = [int(x) for x in clause if int(x) != 0]
        profiles.append((len(lits), sum(x > 0 for x in lits)))
        for x in lits:
            degrees[abs(x)] = degrees.get(abs(x), 0) + 1
    obj = {"profiles": sorted(profiles),
           "degrees": sorted(degrees.values()),
           "sampled": len(selected)}
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:24]

class Memory:
    def __init__(self, path, readonly=False):
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect("file:" + str(Path(path).resolve()) + "?mode=ro", uri=True)
        else:
            self.db = sqlite3.connect(str(path))
            self.db.executescript(SCHEMA)

    def record(self, *, cohort, formula_sha, signature, arm, baseline_e2e,
               candidate_e2e, baseline_solved, candidate_solved, cap_s,
               verified, probe_s):
        if self.readonly:
            raise PermissionError("Frozen evaluation memory cannot be modified")
        if min(baseline_e2e, candidate_e2e, probe_s) < 0 or cap_s <= 0:
            raise ValueError("Invalid timing")
        if not (0 <= probe_s <= candidate_e2e):
            raise ValueError("Probe time exceeds candidate E2E time")
        with self.db:
            self.db.execute("""INSERT OR REPLACE INTO observations
              (cohort,formula_sha,signature,arm,baseline_e2e,candidate_e2e,
               baseline_solved,candidate_solved,cap_s,verified,probe_s)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
               (cohort,formula_sha,signature,arm,baseline_e2e,candidate_e2e,
                int(baseline_solved),int(candidate_solved),cap_s,
                int(verified),probe_s))

    def recommend(self, sig, *, min_cases=5, max_probe_s=0.05,
                  excluded_cohort=None):
        """Conservative policy: require >=min_cases distinct verified formulas,
        positive average paired PAR2 saving and no solved-count regression.
        Returns None for insufficient evidence (fallback to BASE).
        """
        sql = """SELECT arm,formula_sha,baseline_e2e,candidate_e2e,
                        baseline_solved,candidate_solved,cap_s,probe_s
                 FROM observations WHERE signature=? AND verified=1"""
        args = [sig]
        if excluded_cohort is not None:
            sql += " AND cohort<>?"
            args.append(excluded_cohort)
        rows = self.db.execute(sql, args).fetchall()
        by_arm = {}
        for arm, sha, base, cand, bs, cs, cap, probe in rows:
            if probe > max_probe_s:
                continue
            by_arm.setdefault(arm, {})[sha] = (base,cand,bs,cs,cap)
        choices = []
        for arm, formulas in by_arm.items():
            if len(formulas) < min_cases:
                continue
            values = list(formulas.values())
            if sum(v[3] for v in values) < sum(v[2] for v in values):
                continue
            savings = [((v[0] if v[2] else 2*v[4]) -
                        (v[1] if v[3] else 2*v[4])) for v in values]
            avg = sum(savings)/len(savings)
            if avg > 0:
                choices.append((avg,arm,len(formulas)))
        if not choices:
            return None
        avg,arm,n = max(choices)
        return {"arm":arm,"mean_par2_saving_s":avg,"matched_cases":n}

    def close(self):
        self.db.close()

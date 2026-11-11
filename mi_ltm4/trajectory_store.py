"""LTM4 training-only trajectory memory: motifs are advice, never clauses.

Separate structure sightings from paired native-CDCL evidence. Each distinct
training SHA is one sample; repeated seeds contribute a within-SHA median.
The frozen policy is never updated with holdout data.
"""
import hashlib
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS motifs(
 formula_sha TEXT NOT NULL,
 motif_key TEXT NOT NULL,
 kind TEXT NOT NULL,
 source_count INTEGER NOT NULL,
 peak_width INTEGER NOT NULL,
 PRIMARY KEY(formula_sha,motif_key)
);
CREATE INDEX IF NOT EXISTS motifs_lookup ON motifs(motif_key);
CREATE TABLE IF NOT EXISTS pairs(
 formula_sha TEXT NOT NULL,
 rep INTEGER NOT NULL,
 base_par2_s REAL NOT NULL,
 chain_par2_s REAL NOT NULL,
 base_solved INTEGER NOT NULL,
 chain_solved INTEGER NOT NULL,
 PRIMARY KEY(formula_sha,rep)
);
"""

class TrajectoryMemory:
    def __init__(self, path, *, readonly=False):
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect(
                "file:" + str(Path(path).resolve()) + "?mode=ro", uri=True)
        else:
            self.db = sqlite3.connect(str(path))
            self.db.executescript(SCHEMA)

    def remember(self, formula_sha, episodes):
        if self.readonly:
            raise PermissionError("Frozen trajectory memory is read-only")
        if not formula_sha:
            raise ValueError("Missing original formula SHA")
        rows = []
        for ep in episodes:
            if not ep.get("verified") or not ep["key"].startswith("traj4:"):
                raise ValueError("Only audited structural motifs are accepted")
            rows.append((formula_sha, ep["key"], ep["kind"],
                         ep["source_count"], ep["peak_width"]))
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO motifs VALUES (?,?,?,?,?)", rows)

    def record_pair(self, sha, rep, base, chain):
        if self.readonly:
            raise PermissionError("Frozen trajectory memory is read-only")
        if not (base.get("trial_audited") and chain.get("trial_audited")):
            raise ValueError("Only audited native paired trials are accepted")
        if base["sha256"] != sha or chain["sha256"] != sha:
            raise ValueError("Mismatched original CNF SHAs")
        if base["rep"] != rep or chain["rep"] != rep:
            raise ValueError("Mismatched paired seeds")
        if base["arm"] != "BASE" or chain["arm"] != "MI_CHAIN":
            raise ValueError("Expected BASE vs MI_CHAIN")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO pairs VALUES (?,?,?,?,?,?)",
                (sha, rep, base["par2_s"], chain["par2_s"],
                 int(base["solved"]), int(chain["solved"])))

    def freeze(self, forbidden_shas, *, min_cases=8, min_win_fraction=.7,
               min_gain_s=.0015):
        forbidden = set(forbidden_shas)
        for table in ("motifs", "pairs"):
            entries = self.db.execute(
                "SELECT DISTINCT formula_sha FROM " + table).fetchall()
            if forbidden.intersection(sha for (sha,) in entries):
                raise AssertionError("Holdout formula leaked to training memory")
        sightings = defaultdict(set)
        kinds = {}
        for sha, key, kind in self.db.execute(
                "SELECT formula_sha,motif_key,kind FROM motifs"):
            sightings[key].add(sha)
            if key in kinds and kinds[key] != kind:
                raise AssertionError("Inconsistent motif kind")
            kinds[key] = kind
        per_sha = defaultdict(list)
        for sha, rep, base, chain, bs, cs in self.db.execute(
                "SELECT * FROM pairs"):
            per_sha[sha].append((base-chain, bool(bs), bool(cs)))
        entries = {}
        positive = {}
        for key, shas in sorted(sightings.items()):
            effects = []
            regressions = 0
            for sha in shas:
                if sha not in per_sha:
                    continue
                values = per_sha[sha]
                effects.append(statistics.median(x[0] for x in values))
                regressions += int(any(bs and not cs for _, bs, cs in values))
            evidence = dict(
                kind=kinds[key], seen_formulas=len(shas),
                paired_formulas=len(effects), solved_regressions=regressions,
                wins=sum(x>0 for x in effects),
                losses=sum(x<0 for x in effects))
            if effects:
                evidence["median_PAR2_saving_s"] = round(
                    statistics.median(effects), 7)
                evidence["mean_PAR2_saving_s"] = round(
                    statistics.mean(effects), 7)
                evidence["win_fraction"] = round(
                    evidence["wins"]/len(effects), 4)
            else:
                evidence.update(median_PAR2_saving_s=None,
                                mean_PAR2_saving_s=None, win_fraction=None)
            entries[key] = evidence
            if (len(effects) >= min_cases and regressions == 0 and
                    evidence["wins"]/len(effects) >= min_win_fraction and
                    evidence["median_PAR2_saving_s"] >= min_gain_s and
                    evidence["mean_PAR2_saving_s"] >= min_gain_s):
                positive[key] = evidence
        result = dict(
            version="LTM4-trajectories-prototype",
            training_formulas=len(set().union(*sightings.values()))
                              if sightings else 0,
            motifs=entries, positive_motifs=positive,
            thresholds=dict(min_cases=min_cases,
                            min_win_fraction=min_win_fraction,
                            min_gain_s=min_gain_s),
            guarantee="No motifs carry source variables, clauses, or SAT verdicts.")
        result["sha256"] = hashlib.sha256(
            json.dumps(result, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()
        return result

    def close(self):
        self.db.close()


def recommend(policy, episodes):
    """Advisory route only. Never produces a SAT/UNSAT deduction."""
    if not episodes:
        return "BASE", "no_motif"
    candidates = [(policy["positive_motifs"][ep["key"]], ep["key"])
                  for ep in episodes
                  if ep["key"] in policy["positive_motifs"]]
    if not candidates:
        return "BASE", "no_positive_evidence"
    best = max(candidates, key=lambda x: (
        x[0]["median_PAR2_saving_s"], x[0]["paired_formulas"]))
    return "MI_CHAIN", "matched_qualified_motif:" + best[1]

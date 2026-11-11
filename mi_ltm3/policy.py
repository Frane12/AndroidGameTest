"""MI-LTM3 persistent *advisory* memory and frozen cost-aware policy.

Never imports a learned clause, model, UNSAT verdict or XOR equation from
another formula. Only stores renaming-invariant opportunity classes and
aggregated, paired performance evidence. The policy may opt in or abstain.
"""
import hashlib
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs(
 formula_sha TEXT NOT NULL,
 rep INTEGER NOT NULL,
 generation INTEGER NOT NULL,
 family TEXT NOT NULL,
 feature_key TEXT NOT NULL,
 base_par2_s REAL NOT NULL,
 force_par2_s REAL NOT NULL,
 base_solved INTEGER NOT NULL,
 force_solved INTEGER NOT NULL,
 base_conflicts INTEGER NOT NULL,
 force_conflicts INTEGER NOT NULL,
 probe_s REAL NOT NULL,
 PRIMARY KEY(formula_sha,rep)
);
CREATE INDEX IF NOT EXISTS pairs_key ON pairs(feature_key);
CREATE TABLE IF NOT EXISTS patterns(
 formula_sha TEXT NOT NULL,
 pattern TEXT NOT NULL,
 relation_kind TEXT NOT NULL,
 PRIMARY KEY(formula_sha,pattern)
);
CREATE INDEX IF NOT EXISTS patterns_key ON patterns(pattern);
"""


class TrainingMemory:
    def __init__(self, path, *, readonly=False):
        self.readonly=readonly
        if readonly:
            self.db=sqlite3.connect("file:"+str(Path(path).resolve())+"?mode=ro",
                                    uri=True)
        else:
            self.db=sqlite3.connect(str(path))
            self.db.executescript(SCHEMA)

    def insert_pair(self, *, sha, rep, generation, family, key, base, force):
        if self.readonly:
            raise PermissionError("Holdout has read-only memory")
        if not (base.get("trial_audited") and force.get("trial_audited")):
            raise ValueError("Unaudited trial cannot enter training")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (sha,rep,generation,family,key,
                 float(base["par2_s"]),float(force["par2_s"]),
                 int(base["solved"]),int(force["solved"]),
                 int(base["conflicts"]),int(force["conflicts"]),
                 float(force["probe_s"])))

    def insert_patterns(self, sha, patterns):
        if self.readonly:
            raise PermissionError("Holdout has read-only memory")
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO patterns VALUES (?,?,?)",
                [(sha,key,kind) for key,kind in patterns.items()])

    def freeze(self, forbidden_holdout_shas, *, min_cases=8,
               min_win_fraction=.7, min_gain_s=.0015, candidate_action="MI_CHAIN"):
        if candidate_action not in ("MI_CHAIN", "LTM_NATIVE"):
            raise ValueError("Unsupported candidate action")
        forbidden=set(forbidden_holdout_shas)
        seen_shas=set()
        aggregates=defaultdict(lambda:defaultdict(list))
        for sha,rep,key,b,f,bs,fs,bc,fc,probe in self.db.execute(
            "SELECT formula_sha,rep,feature_key,base_par2_s,force_par2_s,"
            "base_solved,force_solved,base_conflicts,force_conflicts,probe_s "
            "FROM pairs"):
            if sha in forbidden:
                raise AssertionError("Holdout SHA leaked into training pairs")
            seen_shas.add(sha)
            aggregates[key][sha].append(dict(rep=rep,saving=b-f,
                                               base_solved=bool(bs),
                                               force_solved=bool(fs),
                                               conflicts_saved=bc-fc,
                                               probe_s=probe))
        pattern_index=defaultdict(lambda:dict(kind=None,formulas=set()))
        for sha,pattern,kind in self.db.execute(
            "SELECT formula_sha,pattern,relation_kind FROM patterns"):
            if sha in forbidden:
                raise AssertionError("Holdout SHA leaked into learned templates")
            obj=pattern_index[pattern]
            if obj["kind"] not in (None,kind):
                raise AssertionError("Pattern kind inconsistent")
            obj["kind"]=kind
            obj["formulas"].add(sha)
        classes={}
        positives={}
        for key,by_sha in sorted(aggregates.items()):
            if len(by_sha)<min_cases:
                continue
            # Each distinct original formula counts once; repeated seeds
            # improve measurement, not training sample count.
            savings=[statistics.median([p["saving"] for p in reps])
                     for reps in by_sha.values()]
            wins=sum(x>0 for x in savings)
            losses=sum(x<0 for x in savings)
            regressions=sum(any(p["base_solved"] and not p["force_solved"]
                                for p in reps) for reps in by_sha.values())
            mean=statistics.mean(savings)
            median=statistics.median(savings)
            entry=dict(formulas=len(by_sha),wins=wins,losses=losses,
                       solved_regressions=regressions,
                       mean_PAR2_saving_s=round(mean,7),
                       median_PAR2_saving_s=round(median,7),
                       win_fraction=round(wins/len(by_sha),4))
            classes[key]=entry
            if (regressions==0 and wins/len(by_sha)>=min_win_fraction and
                    median>=min_gain_s and mean>=min_gain_s):
                positives[key]=dict(entry,decision=candidate_action)
        patterns={key:dict(kind=value["kind"],
                           training_formulas=len(value["formulas"]))
                  for key,value in sorted(pattern_index.items())}
        policy=dict(version="MI-LTM3-v1",train_formula_count=len(seen_shas),
                    feature_classes=classes,positive_classes=positives,
                    known_patterns=patterns,
                    thresholds=dict(min_cases=min_cases,
                                    min_win_fraction=min_win_fraction,
                                    min_gain_s=min_gain_s),
                    rule="No source conclusion is reusable; only strategy selection.")
        policy["sha256"]=hashlib.sha256(
            json.dumps(policy,sort_keys=True,separators=(",",":")).encode()
        ).hexdigest()
        return policy

    def close(self):
        self.db.close()


def action(policy,key):
    """No optimistic default: unproven classes always fall back to BASE."""
    if key in policy["positive_classes"]:
        return policy["positive_classes"][key]["decision"],"positive_evidence"
    if key in policy["feature_classes"]:
        return "BASE","negative_or_insufficient_evidence"
    return "BASE","unseen_structure"

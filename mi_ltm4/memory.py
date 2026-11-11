"""LTM4 positive AND negative structural-memory outcomes with holdout isolation.

Train on independently measured paired PAR2 only; shadow candidates remain
diagnostics and can never be treated as demonstrated performance improvements.
"""
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

SCHEMA="""
CREATE TABLE IF NOT EXISTS experiences(
 formula_sha TEXT NOT NULL,
 rep INTEGER NOT NULL,
 cohort TEXT NOT NULL CHECK(cohort='train'),
 motif TEXT NOT NULL,
 candidate_events INTEGER NOT NULL,
 bcp_confirmed_new INTEGER NOT NULL,
 bcp_already_known INTEGER NOT NULL,
 intervention_cost_s REAL NOT NULL,
 base_par2_s REAL NOT NULL,
 trial_par2_s REAL NOT NULL,
 base_solved INTEGER NOT NULL,
 trial_solved INTEGER NOT NULL,
 label TEXT NOT NULL,
 PRIMARY KEY(formula_sha,rep,motif)
);
CREATE INDEX IF NOT EXISTS experience_motif ON experiences(motif);
"""


class StructuralMemory:
    def __init__(self,path,*,readonly=False):
        self.readonly=readonly
        if readonly:
            self.db=sqlite3.connect("file:"+str(Path(path).resolve())+"?mode=ro",uri=True)
        else:
            self.db=sqlite3.connect(str(path))
            self.db.executescript(SCHEMA)

    def record(self,*,formula_sha,rep,motif,observed,base,trial,
               intervention_cost_s,cohort="train"):
        if self.readonly:
            raise PermissionError("Frozen memory is read only")
        if cohort!="train":
            raise ValueError("Holdout must never enter memory")
        if not observed.get("native_bcp_closure_confirmed",False):
            raise ValueError("Synthetic/shadow-only observations cannot train usefulness")
        if not (base.get("audited") and trial.get("audited")):
            raise ValueError("Both paired outcomes must be independently audited")
        if intervention_cost_s<0:
            raise ValueError("Negative intervention cost")
        gain=base["par2_s"]-trial["par2_s"]
        if base["solved"] and not trial["solved"]:
            label="regression"
        elif gain>0:
            label="positive"
        elif gain<0:
            label="negative"
        else:
            label="neutral"
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO experiences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (formula_sha,rep,cohort,motif,
                 int(observed["candidate_events"]),
                 int(observed["bcp_confirmed_new"]),
                 int(observed["bcp_already_known"]),
                 float(intervention_cost_s),
                 float(base["par2_s"]),float(trial["par2_s"]),
                 int(base["solved"]),int(trial["solved"]),label))
        return label

    def freeze(self,holdout_shas=(),*,min_formulas=8,min_win_fraction=.7):
        forbidden=set(holdout_shas)
        grouped=defaultdict(lambda:defaultdict(list))
        for sha,rep,motif,b,t,bs,ts,label in self.db.execute(
            "SELECT formula_sha,rep,motif,base_par2_s,trial_par2_s,"
            "base_solved,trial_solved,label FROM experiences"):
            if sha in forbidden:
                raise AssertionError("Holdout leakage detected")
            grouped[motif][sha].append(dict(gain=b-t,label=label,base=bs,trial=ts))
        summary={}
        for motif,bysha in grouped.items():
            values=[statistics.median([r["gain"] for r in runs])
                    for runs in bysha.values()]
            n=len(values)
            regressions=sum(any(r["base"] and not r["trial"] for r in runs)
                            for runs in bysha.values())
            positive=sum(v>0 for v in values)
            negative=sum(v<0 for v in values)
            eligible=(n>=min_formulas and positive/n>=min_win_fraction and
                      regressions==0 and statistics.median(values)>0)
            summary[motif]=dict(formulas=n,positive=positive,negative=negative,
                                regressions=regressions,
                                median_PAR2_gain_s=statistics.median(values),
                                permit_intervention=eligible)
        return summary

    def close(self):
        self.db.close()

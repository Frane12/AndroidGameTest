#!/usr/bin/env python3
"""MAP2-L prospective disjoint-source test: train vs frozen holdout.

Deliberately constructed planted-SAT mixed CNF is a STRUCTURAL test,
NOT original SAT competition data. 6 train + 6 never-trained holdout
sources, three independent native arms, three repeats, same one CPU.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

sys.path.insert(0,"research")
import drnas_atlasmap2_learn as learner

OUT=Path("mre_atlasmap2_learning")
OUT.mkdir(exist_ok=True)
BIN=Path("mre_atlasmap2/bin/drnas_atlasmap2").resolve()
MEM=OUT/"train_memory.json"
CAP=2
REPS=3
SEED=20261111

def formula(index):
    rng=random.Random(SEED+index*997)
    n=24
    truth={v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
    clauses=[]
    # Seven chained certified parity relations on the ORIGINAL variables.
    for x in range(1,9):
        y=x+1
        rhs=int(truth[x]^truth[y])
        if rhs==0:clauses.extend(([-x,y],[x,-y]))
        else:clauses.extend(([x,y],[-x,-y]))
    # Couple parity variables to other variables with planted 3-CNF.
    for _ in range(90):
        variables=rng.sample(range(1,n+1),3)
        clause=[v if rng.getrandbits(1) else -v for v in variables]
        if not any(truth[abs(l)]==(l>0) for l in clause):
            v=variables[0];clause[0]=v if truth[v] else -v
        clauses.append(clause)
    # Force a genuine trail anchor, while preserving the planted model.
    clauses.append([1 if truth[1] else -1])
    rng.shuffle(clauses)
    raw=(f"p cnf {n} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    path=OUT/(f"mixed_{index:02d}.cnf")
    path.write_text(raw)
    return path,hashlib.sha256(raw.encode()).hexdigest()

def run(path,arm):
    _,n,cs=learner.read_cnf(path)
    return learner.solve(BIN,path,arm,CAP,n,cs)

def summarise(rows,cohort):
    summary={}
    for arm in ("A","SHADOW","LIVE"):
        trials=[r for r in rows if r["arm"]==arm]
        summary[arm]={
            "solved":sum(r["status"]=="SAT" for r in trials),
            "trials":len(trials),
            "PAR2_s":round(sum(r["PAR2_s"] for r in trials),6),
            "E2E_s":round(sum(r["E2E_s"] for r in trials),6),
            "live_implications":sum(r["live_implications"] for r in trials),
            "shadow_opportunities":sum(r["shadow_opportunities"] for r in trials),
            "decisions":sum(r["decisions"] for r in trials),
            "conflicts":sum(r["conflicts"] for r in trials),
        }
    print("ATLASMAP2_LEARN_PAR2 "+json.dumps({"cohort":cohort,"summary":summary},sort_keys=True),flush=True)
    return summary

def main():
    MEM.unlink(missing_ok=True)
    train_paths=[formula(i) for i in range(6)]
    hold_paths=[formula(i) for i in range(6,12)]
    train_sha={sha for _,sha in train_paths}
    hold_sha={sha for _,sha in hold_paths}
    assert not train_sha&hold_sha
    train_rows=[];hold_rows=[]
    learning_reports=[]
    for path,sha in train_paths:
        cmd=[sys.executable,"research/drnas_atlasmap2_learn.py",
             str(path),"--binary",str(BIN),"--memory",str(MEM),
             "--phase","train","--cap",str(CAP),
             "--report",str(OUT/(path.stem+"_train.json"))]
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=20)
        record=json.loads((OUT/(path.stem+"_train.json")).read_text())
        assert record["updated"] and record["sha256"]==sha
        assert record["attempts"]["A"]["status"]=="SAT",record
        assert record["attempts"]["LIVE"]["status"]=="SAT",record
        assert record["attempts"]["SHADOW"]["status"]=="SAT",record
        assert record["attempts"]["LIVE"]["live_implications"]>0,record
        assert record["attempts"]["SHADOW"]["shadow_opportunities"]>0,record
        assert record["explanation"]["method"].startswith("exact_original_XOR2"),record
        learning_reports.append(record)
        # Independent repeats to measure variance beyond the training sample.
        for rep in range(REPS):
            for arm in ("A","SHADOW","LIVE"):
                trial=run(path,arm)
                assert trial["status"]=="SAT",(path,arm,trial)
                trial.update({"sha256":sha,"rep":rep,"cohort":"train"})
                train_rows.append(trial)
    before=MEM.read_bytes()
    # Duplicate source cannot inflate evidence.
    path,sha=train_paths[0]
    cmd=[sys.executable,"research/drnas_atlasmap2_learn.py",
         str(path),"--binary",str(BIN),"--memory",str(MEM),
         "--phase","train","--cap",str(CAP),
         "--report",str(OUT/"duplicate.json")]
    subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=20)
    assert json.loads((OUT/"duplicate.json").read_text())["duplicate"]
    assert MEM.read_bytes()==before,"duplicate mutated training memory"
    hold_decisions=[]
    for path,sha in hold_paths:
        cmd=[sys.executable,"research/drnas_atlasmap2_learn.py",
             str(path),"--binary",str(BIN),"--memory",str(MEM),
             "--phase","eval","--cap",str(CAP),
             "--report",str(OUT/(path.stem+"_eval.json"))]
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=20)
        rec=json.loads((OUT/(path.stem+"_eval.json")).read_text())
        assert rec["memory_frozen"] and not rec["updated"]
        assert rec["attempt"]["status"]=="SAT"
        assert rec["sha256"]==sha
        assert MEM.read_bytes()==before,"evaluation leaked into training memory"
        hold_decisions.append({"sha256":sha,"signature":rec["features"]["signature"],
                               "selected":rec["selected"],"why":rec["decision"]["why"]})
        for rep in range(REPS):
            for arm in ("A","SHADOW","LIVE"):
                trial=run(path,arm)
                assert trial["status"]=="SAT",(path,arm,trial)
                trial.update({"sha256":sha,"rep":rep,"cohort":"holdout"})
                hold_rows.append(trial)
    data=json.loads(MEM.read_text())
    assert len(data["samples"])==6
    assert set(data["samples"])==train_sha
    assert not set(data["samples"])&hold_sha
    train_summary=summarise(train_rows,"train")
    hold_summary=summarise(hold_rows,"holdout")
    report={
        "experiment":"MAP2-L-disjoint-planted-mixed-CNF-6train-6holdout-3reps-2s-1CPU",
        "limitations":"constructed satisfiable mixed CNF; not untouched real SAT benchmark; no independently checked UNSAT",
        "cap_s":CAP,"reps":REPS,
        "train_sha256":sorted(train_sha),"holdout_sha256":sorted(hold_sha),
        "train_summary":train_summary,"holdout_summary":hold_summary,
        "selection_decisions":hold_decisions,
        "learning_reports":learning_reports,
        "train_rows":train_rows,"holdout_rows":hold_rows,
        "memory_frozen_verified":True,"duplicate_not_counted":True,
    }
    (OUT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True))
    print("ATLASMAP2_LEARN_FINAL "+json.dumps({
        "train":train_summary,"holdout":hold_summary,
        "selected":[d["selected"] for d in hold_decisions],
        "distinct_train":len(train_sha),"distinct_holdout":len(hold_sha),
        "memory_frozen":True
    },sort_keys=True),flush=True)

if __name__=="__main__":
    main()

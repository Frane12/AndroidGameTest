#!/usr/bin/env python3
"""DRNAS Global Memory: controlled native X4.7 continual learning.

Uses only explicitly assigned train rows from the persistent memory,
collects fresh verified paired TRAIN-only experiences, selects a candidate
on old validation without reading historic holdout rows, then evaluates on
fresh unexposed source SHA/families before optionally updating the champion.

No benchmark report, validation or holdout row becomes a training example.
A completed training cycle is useful even when NO candidate is promoted.
This does not modify a production executable.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import numpy as np

MODEL_NAMESPACE="DRNAS-GLOBAL-LIVE-X47"
ENGINE_SHA256="9c78f45aa54a2556fb9f22e490a200b77e70a4360245d998c4dc96bd0b684ab3"
MIN_TRAIN=400
MIN_VALID=100
FRESH_CYCLE_LABEL="DRNAS-GLOBAL-X47-CONTINUAL-v1"

def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sha_file(path):
    return sha_bytes(Path(path).read_bytes())

def out(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def input_rows(db, table, where, fields):
    # Input table is a static application constant, not user-provided.
    for item, in db.execute("SELECT "+fields+" FROM "+table+" WHERE "+where):
        try:
            x=json.loads(item)
        except ValueError:
            continue
        if isinstance(x,dict) and isinstance(x.get("base"),dict) and isinstance(x.get("flip"),dict):
            if isinstance(x.get("sha256"),str) and len(x["sha256"])==64:
                yield x

def check_row(r):
    if r.get("features") is not None and len(r["features"]) != 24:
        raise AssertionError("24 feature contract violated")
    for name in ("base","flip"):
        item=r[name]
        if item.get("verified") is True and item.get("work_cost") is None:
            raise AssertionError("Missing verified deterministic cost")
    if r.get("label") is not None:
        if not (r["base"].get("verified") and r["flip"].get("verified")):
            raise AssertionError("Training label must come from paired verified runs")
    return r

def inspect_splits(db):
    overlaps=db.execute("""
        SELECT COUNT(*) FROM legacy_experiences AS a
        JOIN observations AS b ON a.source_sha=b.source_sha
        WHERE a.split='train' AND b.role!='train'
    """).fetchone()[0]
    if overlaps:
        raise RuntimeError("Legacy training SHA overlaps holdout evidence")
    overlap2=db.execute("""
        SELECT COUNT(*) FROM continual_experiences c
        JOIN legacy_experiences e ON c.source_sha=e.source_sha
        WHERE e.split!='train'
    """).fetchone()[0]
    if overlap2:
        raise RuntimeError("New training SHA overlaps legacy validation")
    overlap3=db.execute("""
        SELECT COUNT(*) FROM continual_experiences c
        JOIN sealed_global_sources s ON c.source_sha=s.source_sha
    """).fetchone()[0]
    if overlap3:
        raise RuntimeError("New training SHA overlaps sealed global holdout")
    return True

def init_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS continual_experiences (
            source_sha TEXT PRIMARY KEY, namespace TEXT NOT NULL,
            family TEXT NOT NULL, payload TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sealed_global_sources (
            source_sha TEXT PRIMARY KEY, namespace TEXT NOT NULL,
            family TEXT NOT NULL, audit_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS global_learning_events (
            namespace TEXT PRIMARY KEY, started_at TEXT NOT NULL,
            model_sha TEXT, promoted INTEGER NOT NULL,
            summary_json TEXT NOT NULL
        );
    """)

def strict_bootstrap(core, candidate, draws=3000, seed=471319):
    if not core or len(core)!=len(candidate):
        raise ValueError("Paired source arrays required")
    if any(not math.isfinite(x) or x<0 for x in core+candidate):
        raise ValueError("Non-finite or negative PAR2")
    a=sum(core);b=sum(candidate)
    if a<=0:
        return dict(reduction=0.,lower95=0.,upper95=0.)
    rng=random.Random(seed)
    vals=[]
    n=len(core)
    for _ in range(draws):
        ix=[rng.randrange(n) for _ in range(n)]
        left=sum(core[i] for i in ix)
        right=sum(candidate[i] for i in ix)
        vals.append((left-right)/left if left else 0.)
    vals.sort()
    return dict(reduction=(a-b)/a,
                lower95=vals[int(.025*(draws-1))],
                upper95=vals[int(.975*(draws-1))])

def candidate_gate(metrics):
    """Gate uses predeclared 95% CI, solved parity, tail and val-audit."""
    reasons=[]
    if metrics.get("input_overlap",True):
        reasons.append("split_contamination")
    if metrics["validation"]["labelled"]<MIN_VALID:
        reasons.append("insufficient_validation")
    if metrics["validation"]["audit_reduction"]<0.01:
        reasons.append("validation_audit_not_better_by_1pct")
    if metrics["holdout"]["sources"]<60 or metrics["holdout"]["families"]<5:
        reasons.append("insufficient_fresh_cross_family_holdout")
    if metrics["holdout"]["candidate_verified"]<metrics["holdout"]["incumbent_verified"]:
        reasons.append("fewer_verified_sat")
    if metrics["holdout"]["candidate_verified"]<metrics["holdout"]["core_verified"]:
        reasons.append("fewer_verified_sat_than_core")
    p=metrics["holdout"]["vs_incumbent"]
    if p["reduction"]<0.05 or p["lower95"]<=0.02:
        reasons.append("paired_PAR2_gain_not_confident_5pct")
    q=metrics["holdout"]["vs_core"]
    if q["reduction"]<0.03 or q["lower95"]<=0.:
        reasons.append("no_confident_improvement_over_core")
    if metrics["holdout"]["severe_regressions"]>int(.1*metrics["holdout"]["sources"]):
        reasons.append("too_many_source_regressions")
    if metrics["holdout"]["families_regressed_10pct"]>0:
        reasons.append("family_regression_over_10pct")
    if metrics["holdout"].get("incorrect_outputs",0)>0:
        reasons.append("incorrect_output")
    return not reasons,reasons

def quantile_sample(rows, per_family=200):
    """Bound fit complexity while keeping source-family coverage deterministic."""
    buckets=defaultdict(list)
    for r in rows:
        buckets[r["family"]].append(r)
    chosen=[]
    for family in sorted(buckets):
        rr=sorted(buckets[family],key=lambda x:x["sha256"])
        n=min(per_family,len(rr))
        if n:
            chosen.extend(rr[min(len(rr)-1,int((i+.5)*len(rr)/n))]
                          for i in range(n))
    return chosen

def compatible_rows(db):
    train=[]
    for r in input_rows(db,"legacy_experiences","split='train' AND source_sha IN (SELECT source_sha FROM eligible_training)","payload"):
        train.append(check_row(r))
    for r in input_rows(db,"continual_experiences","1=1","payload"):
        train.append(check_row(r))
    validation=[check_row(r) for r in
                input_rows(db,"legacy_experiences","split='validation'","payload")]
    forbidden={x[0] for x in db.execute(
        "SELECT source_sha FROM observations UNION SELECT source_sha FROM sealed_global_sources")}
    train=[r for r in train if r["sha256"] not in forbidden]
    trainsha={r["sha256"] for r in train}
    valsha={r["sha256"] for r in validation}
    if trainsha & valsha:
        raise AssertionError("Training and validation CNF SHA collision")
    if len(trainsha)!=len(train) or len(valsha)!=len(validation):
        raise AssertionError("Duplicate original SHA in source collection")
    if len(train)<MIN_TRAIN or len(validation)<MIN_VALID*2:
        raise RuntimeError("Insufficient independent train / validation source SHA")
    return train,validation,forbidden | trainsha | valsha

def collect_fresh_training(db, engine, X, run_id, existing, per_family):
    if not run_id.isdigit():
        raise ValueError("Numeric GitHub run ID required")
    namespace=FRESH_CYCLE_LABEL+":train:"+run_id
    cnf=Path("global_continual_train.cnf")
    count=labels=0
    families=X.TRAIN
    try:
        for family in families:
            for index in range(per_family):
                case=X.make_case(family,index,namespace)
                sha=case["sha256"]
                if sha in existing:
                    raise RuntimeError("New training source overlaps protected SHA")
                cnf.write_text(case["source"])
                r=X.pair(engine,cnf,case)
                r["meta"]={"namespace":namespace,"split":"train",
                           "family":family,"index":index,"run_id":run_id}
                check_row(r)
                if r["label"] is not None:labels+=1
                db.execute("""
                    INSERT INTO continual_experiences
                      (source_sha,namespace,family,payload,imported_at)
                    VALUES (?,?,?,?,?)
                """,(sha,namespace,family,json.dumps(r,sort_keys=True),now()))
                existing.add(sha)
                count+=1
    finally:
        cnf.unlink(missing_ok=True)
    return {"source_count":count,"labelled":labels,"families":len(families),
            "namespace":namespace}

def eval_validation(M, baseline, cand, rows):
    labelled=[r for r in rows if r.get("label") is not None and r.get("features") is not None]
    if len(labelled)<MIN_VALID:
        raise RuntimeError("Insufficient labeled validation cohort")
    # Deterministic source-SHA split, never selected using model outcomes.
    ordered=sorted(labelled,key=lambda r:r["sha256"])
    tune=[r for i,r in enumerate(ordered) if i%4 != 0]
    audit=[r for i,r in enumerate(ordered) if i%4 == 0]
    if len(audit)<MIN_VALID:
        raise RuntimeError("Too few validation audit sources")
    c=M.calibrate(cand,tune)
    c,retired,active=M.prune(c,tune,periodic=True)
    c=M.calibrate(c,tune)
    core_audit=sum(r["base"]["work_cost"] for r in audit)
    incumbent_audit=M.cost(baseline,audit) if baseline is not None else core_audit
    candidate_audit=M.cost(c,audit)
    audit_gain=(incumbent_audit-candidate_audit)/incumbent_audit if incumbent_audit else 0.
    return c,{
        "labelled":len(labelled),"tune":len(tune),"audit":len(audit),
        "core_audit_work":core_audit,"incumbent_audit_work":incumbent_audit,
        "candidate_audit_work":candidate_audit,"audit_reduction":audit_gain,
        "retired_trees":len(retired),"active_features":len(active)}

def run_fresh_holdout(db, engine, X, candidate_path, champion_path, run_id,
                      forbidden, per_family, cap):
    namespace=FRESH_CYCLE_LABEL+":sealed:"+run_id
    names=["core","candidate"]+ (["incumbent"] if champion_path else [])
    rvals=defaultdict(lambda:defaultdict(list))
    fkeys={}
    cases=[]
    for fam in X.HOLDOUT:
        for i in range(per_family):
            case=X.make_case(fam,i,namespace)
            if case["sha256"] in forbidden:
                raise AssertionError("Holdout reused a known train/evaluation formula")
            forbidden.add(case["sha256"])
            cases.append(case)
    cnf=Path("global_continual_holdout.cnf")
    wrong=0
    try:
        for i,case in enumerate(cases):
            cnf.write_text(case["source"])
            sha=case["sha256"]
            fkeys[sha]=case["family"]
            # Order rotates reproducibly to control order-related thermal bias.
            for rep in range(2):
                armorder=names[:]
                random.Random(471300+i*19+rep).shuffle(armorder)
                one={}
                for name in armorder:
                    policy="core" if name=="core" else "tree"
                    path=None if name=="core" else candidate_path if name=="candidate" else champion_path
                    got=X.run(engine,cnf,case,policy,cap,model=path)
                    if got["status"] not in ("SAT_VERIFIED","UNKNOWN","TIMEOUT"):
                        raise AssertionError("Unexpected solver status")
                    if got["status"]=="SAT_VERIFIED" and not got["verified"]:
                        wrong+=1
                    one[name]=got
                for name in names:
                    rvals[sha][name].append(one[name])
            db.execute("""
                INSERT INTO sealed_global_sources VALUES (?,?,?,?)
                """,(sha,namespace,case["family"],"new_nonreusable_sealed_holdout"))
    finally:
        cnf.unlink(missing_ok=True)
    bysha=sorted(fkeys)
    def result(name):
        return [sum(x["PAR2"] for x in rvals[sha][name]) for sha in bysha]
    c=result("core")
    cand=result("candidate")
    incumbent=result("incumbent") if "incumbent" in names else c
    severe=sum(v>2*u and v-u>.01 for u,v in zip(incumbent,cand))
    byfam=defaultdict(lambda:defaultdict(float))
    for i,sha in enumerate(bysha):
        f=fkeys[sha]
        byfam[f]["incumbent"]+=incumbent[i]
        byfam[f]["candidate"]+=cand[i]
        byfam[f]["core"]+=c[i]
    families_bad=sum(y["candidate"]>1.10*y["incumbent"] for y in byfam.values())
    solved=lambda name:sum(r["verified"] for sha in bysha for r in rvals[sha][name])
    return {
        "namespace":namespace,"sources":len(bysha),"families":len(byfam),
        "repeats":2,"cap_s":cap,"core_PAR2_s":round(sum(c),6),
        "incumbent_PAR2_s":round(sum(incumbent),6),
        "candidate_PAR2_s":round(sum(cand),6),
        "vs_incumbent":strict_bootstrap(incumbent,cand),
        "vs_core":strict_bootstrap(c,cand,seed=471320),
        "core_verified":solved("core"),
        "incumbent_verified":solved("incumbent") if "incumbent" in names else solved("core"),
        "candidate_verified":solved("candidate"),
        "severe_regressions":severe,"families_regressed_10pct":families_bad,
        "incorrect_outputs":wrong,
        "family_costs":dict(byfam),
        "sha_digest":sha_bytes("".join(bysha).encode()),
        "independent_unit":"Original CNF SHA; two correlated repetitions",
        "claims":"All positive SAT results independently witness-checked; planted SAT only",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--store",required=True,type=Path)
    p.add_argument("--legacy-source",required=True,type=Path)
    p.add_argument("--legacy-latest",required=True,type=Path)
    p.add_argument("--binary",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--run-id",required=True)
    p.add_argument("--fresh-train-per-family",type=int,default=6)
    p.add_argument("--fresh-holdout-per-family",type=int,default=16)
    p.add_argument("--cap",type=float,default=.35)
    args=p.parse_args()
    if args.fresh_train_per_family<2 or args.fresh_holdout_per_family<12 or not .1<=args.cap<=2.:
        p.error("Unsafe training or holdout budget")
    if not args.run_id.isdigit():p.error("GitHub run ID must be numeric")
    if sha_file(args.legacy_source/"src/drnas_x47.cpp")!=ENGINE_SHA256:
        raise RuntimeError("Untrusted native engine source differs from frozen X47")
    args.out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str((args.legacy_source/"research").resolve()))
    import drnas_x47 as X
    import x47_long_models as M
    from x47_models import write_model
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    X.WORK_LIMIT=50000
    engine=args.binary.resolve()
    if not engine.exists():raise FileNotFoundError(engine)
    frozen_model=json.loads(args.legacy_latest.read_text())["model"]
    if frozen_model.get("kind")!="tree" or len(frozen_model["centers"])!=24:
        raise RuntimeError("Legacy X47 model schema changed")
    prior_sha=sha_file(args.store)
    with tempfile.TemporaryDirectory(prefix="drnas-global-learn-") as td:
        db_path=Path(td)/"global.sqlite"
        db_path.write_bytes(gzip.decompress(args.store.read_bytes()))
        db=sqlite3.connect(db_path)
        init_tables(db)
        if db.execute("SELECT 1 FROM global_learning_events WHERE namespace=?",
                      (args.run_id,)).fetchone():
            raise RuntimeError("This exact run has already opened its sealed holdout")
        inspect_splits(db)
        train,validation,known=compatible_rows(db)
        fresh=collect_fresh_training(db,engine,X,args.run_id,known,args.fresh_train_per_family)
        db.commit()
        train,validation,known=compatible_rows(db)
        archive_model=frozen_model
        champion_json=args.store.parent/"champion_x47.json"
        champion_path=None
        incumbent=None
        if champion_json.exists():
            note=json.loads(champion_json.read_text())
            if note.get("engine_source_sha256")!=ENGINE_SHA256 or not note.get("gate_passed"):
                raise RuntimeError("Invalid previous champion provenance")
            incumbent=note["model"]
            champion_path=args.out/"incumbent.txt"
            write_model(champion_path,incumbent)
            if sha_file(champion_path)!=note["model_txt_sha256"]:
                raise AssertionError("Champion file SHA mismatch")
        baseline=incumbent
        fit_rows=quantile_sample(train,per_family=230)
        c=M.grow(incumbent if incumbent is not None else archive_model,fit_rows,
                 set(range(24)),add_trees=6)
        cand,val=eval_validation(M,baseline,c,validation)
        candidate_path=args.out/"candidate_x47.txt"
        write_model(candidate_path,cand)
        model_sha=sha_file(candidate_path)
        # Split audit precedes reading any fresh holdout source.
        inspect_splits(db)
        locked=run_fresh_holdout(db,engine,X,candidate_path,champion_path,
                                args.run_id,known,args.fresh_holdout_per_family,args.cap)
        metrics={"input_overlap":False,"validation":val,"holdout":locked}
        passed,reasons=candidate_gate(metrics)
        report={
            "cycle":args.run_id,"protocol":FRESH_CYCLE_LABEL,"state":"finished",
            "generated_at":now(),"engine_source_sha256":ENGINE_SHA256,
            "input_memory_sha256":prior_sha,
            "candidate_txt_sha256":model_sha,"historical_train":len(train)-fresh["source_count"],
            "historical_validation":len(validation),
            "training_used":len(fit_rows),"fresh_train":fresh,"candidate_trees":len(cand["weights"]),
            "validation":val,"holdout":locked,"promoted":passed,
            "reasons":reasons,
            "scope":"X47 native tree model only; other solver build evidence remains archive-only",
            "no_deployment":"A passing model is a frozen champion file, not a silent rewrite of any solver binary",
        }
        db.execute("""
            INSERT INTO global_learning_events(namespace,started_at,model_sha,promoted,summary_json)
            VALUES (?,?,?,?,?)
        """,(args.run_id,report["generated_at"],model_sha,int(passed),
             json.dumps(report,sort_keys=True)))
        db.execute("""
            INSERT INTO model_registry(namespace,run_id,source_commit,stage,model_hash,
                                       model_json,claimed_deployment_allowed,promotion_status,reason)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(namespace) DO UPDATE SET
              run_id=excluded.run_id,source_commit=excluded.source_commit,
              stage=excluded.stage,model_hash=excluded.model_hash,
              model_json=excluded.model_json,
              claimed_deployment_allowed=excluded.claimed_deployment_allowed,
              promotion_status=excluded.promotion_status,reason=excluded.reason
        """,(MODEL_NAMESPACE,args.run_id,os.environ.get("GITHUB_SHA",""),
             "sealed-fresh-holdout",model_sha,json.dumps(cand,sort_keys=True),
             int(passed),"champion" if passed else "candidate_rejected",
             json.dumps(reasons)))
        db.commit()
        (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        (args.out/"candidate_x47.json").write_text(json.dumps(cand,indent=2,sort_keys=True)+"\n")
        status=(args.store.parent/"latest_learning.json")
        status.write_text(json.dumps({
            "last_cycle":args.run_id,"updated_at":now(),"candidate_model_sha":model_sha,
            "promoted":passed,"reasons":reasons,"validation_gain":val["audit_reduction"],
            "holdout_gain":locked["vs_incumbent"],"new_training_sources":fresh["source_count"],
            "new_training_labelled":fresh["labelled"],"holdout_sources":locked["sources"],
            "champion_sha":model_sha if passed else
                (sha_file(champion_path) if champion_path is not None else None)
        },indent=2,sort_keys=True)+"\n")
        if passed:
            (args.store.parent/"champion_x47.json").write_text(json.dumps({
                "protocol":FRESH_CYCLE_LABEL,"run":args.run_id,"gate_passed":True,
                "engine_source_sha256":ENGINE_SHA256,"model_txt_sha256":model_sha,
                "model":cand,"validation":val,"holdout":{"vs_core":locked["vs_core"],
                "vs_incumbent":locked["vs_incumbent"],"sources":locked["sources"],
                "families":locked["families"]},
            },indent=2,sort_keys=True)+"\n")
        db.close()
        with (args.store).open("wb") as fh:
            with gzip.GzipFile(fileobj=fh,mode="wb",mtime=0,compresslevel=7) as gz:
                with db_path.open("rb") as inp:shutil.copyfileobj(inp,gz)
    out("DRNAS_GLOBAL_LEARNING_FINAL",{
        "cycle":args.run_id,"fresh_train":fresh,"trained_sources":len(fit_rows),
        "validation":val,"fresh_holdout":locked,"promoted":passed,
        "reasons":reasons,"candidate_sha":model_sha,
    })

if __name__=="__main__":
    main()

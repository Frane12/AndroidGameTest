#!/usr/bin/env python3
"""Safe bridge between native X4.6 COST1 learner and global persistent SQLite.

Only new, independently checked matched-prefix TRAIN pairs are eligible.
Existing X47 (24-feature) examples and historical benchmark holdouts are
incompatible and NEVER used for X46 training. Store contains an experimental
frozen X46COST1 model, not an automatically deployed champion.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

def digest(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()

def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def emit(tag: str, obj: dict) -> None:
    print(tag+" "+json.dumps(obj, sort_keys=True, separators=(",",":")), flush=True)

def snapshot(store: Path, mutable: bool):
    if not store.is_file():
        raise FileNotFoundError("global SQLite snapshot is required: "+str(store))
    data=gzip.decompress(store.read_bytes())
    tmp=tempfile.TemporaryDirectory(prefix="x46-global-sqlite-")
    p=Path(tmp.name)/"global.sqlite"
    p.write_bytes(data)
    db=sqlite3.connect(p)
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise RuntimeError("global database integrity check failed")
    if mutable:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS x46_training_events (
            source_sha TEXT NOT NULL, checkpoint INTEGER NOT NULL, rep INTEGER NOT NULL,
            family TEXT NOT NULL, source_id INTEGER NOT NULL,
            event_json TEXT NOT NULL, inserted_at TEXT NOT NULL,
            PRIMARY KEY(source_sha,checkpoint,rep)
          );
          CREATE TABLE IF NOT EXISTS x46_validation_sources (
            source_sha TEXT PRIMARY KEY, candidate_sha TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS x46_frozen_cost_models (
            model_sha TEXT PRIMARY KEY, model_version TEXT NOT NULL,
            frozen_text TEXT NOT NULL, train_sources INTEGER NOT NULL,
            validation_sources INTEGER NOT NULL, selected_at TEXT NOT NULL,
            evaluation_status TEXT NOT NULL, provenance_json TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS x46_sealed_holdout_sources (
            source_sha TEXT PRIMARY KEY, model_sha TEXT NOT NULL,
            family TEXT NOT NULL, split TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS x46_sealed_holdout_trials (
            model_sha TEXT NOT NULL, source_sha TEXT NOT NULL, checkpoint INTEGER NOT NULL,
            rep INTEGER NOT NULL, arm TEXT NOT NULL, status TEXT NOT NULL,
            verified INTEGER NOT NULL, par2_s REAL NOT NULL,
            PRIMARY KEY(model_sha,source_sha,checkpoint,rep,arm)
          );
        """)
    return tmp,p,db

def commit(store: Path, db: sqlite3.Connection, path: Path):
    db.commit()
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise RuntimeError("corrupted global SQLite after write")
    db.close()
    blob=gzip.compress(path.read_bytes(), compresslevel=6, mtime=0)
    tmp=store.with_name(store.name+".x46.tmp")
    tmp.write_bytes(blob)
    os.replace(tmp,store)

def protected(db: sqlite3.Connection) -> set[str]:
    # All historical evaluated SHA, X47 train+validation, already sealed X46
    # and other explicitly sealed source identities are protected.
    result=set()
    for table,column in (
        ("observations","source_sha"),
        ("legacy_experiences","source_sha"),
        ("continual_experiences","source_sha"),
        ("sealed_global_sources","source_sha"),
        ("x46_training_events","source_sha"),
        ("x46_validation_sources","source_sha"),
        ("x46_sealed_holdout_sources","source_sha"),
    ):
        if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            result.update(x[0] for x in db.execute(f"SELECT {column} FROM {table}"))
    return result

def load_records(path: Path) -> list[dict]:
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]

def check_sha(sha) -> None:
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("noncanonical SHA256")

def stage(args):
    import drnas_x46_cost_train as learner
    man=json.loads(args.manifest.read_text())
    report=json.loads(args.learn_report.read_text())
    if not (man["actual_distinct_originals"]==84 and man["repeats"]==2 and
            report["heldout_formula_outcomes_not_seen"] and report["train_sources"]>=50
            and report["validation_sources"]>=15 and report["validation_score"]["nonflat_rows"]>30):
        raise RuntimeError("X46 training protocol audit failed")
    if man["source_generation_index_offset"]!=1500000:
        raise RuntimeError("X46 source namespace drift")
    if man["frozen_learned_model_sha256"] is not None:
        raise RuntimeError("X46 training must not load another candidate on this first cycle")
    frozen=args.model.read_bytes()
    sha=digest(frozen)
    if sha!=report["frozen_file_sha256"] or not frozen.startswith(b"X46COST1 12\n"):
        raise RuntimeError("incompatible or modified X46COST1 model")
    rows=load_records(args.trials)
    samples,ids=learner.extract(args.trials)
    manifest_sha={v["sha256"] for v in man["sources"]}
    if len(manifest_sha)!=84 or set(ids)!=manifest_sha:
        raise RuntimeError("training SHA identity does not match manifest")
    if not all(row["verified"] for row in rows) or len(rows)!=len(man["arms"])*len(samples):
        raise RuntimeError("unverified full continuation, missing matched pair, or duplicated arm")
    train={sha for sha in ids if ids[sha][0]%4!=0}
    val=manifest_sha-train
    if (len(train)!=report["train_sources"] or len(val)!=report["validation_sources"] or
        digest("\n".join(sorted(train)).encode())!=report["train_source_hashes_sha256"] or
        digest("\n".join(sorted(val)).encode())!=report["validation_source_hashes_sha256"]):
        raise RuntimeError("training/validation disjoint hash audit failed")
    t,p,db=snapshot(args.store,mutable=True)
    try:
        excluded=protected(db)
        if excluded & manifest_sha:
            raise RuntimeError("X46 new train/validation source SHA overlaps global memory")
        for item in samples:
            if item["source"] not in train:
                continue
            check_sha(item["source"])
            db.execute("INSERT INTO x46_training_events VALUES(?,?,?,?,?,?,?)",(
                item["source"],item["checkpoint"],item["rep"],item["family"],
                item["source_id"],json.dumps(item,sort_keys=True),stamp()))
        for source in val:
            db.execute("INSERT INTO x46_validation_sources VALUES(?,?)",(source,sha))
        provenance={
            "dataset":"native X46 matched-state full-continuation labels",
            "train_namespace":str(man["source_generation_index_offset"]),
            "source_shas_digest":digest("\n".join(sorted(manifest_sha)).encode()),
            "model":sha,"model_protocol":report["protocol"],
            "train_source_count":len(train),"validation_source_count":len(val),
            "excludes_X47_24_feature_rows":True,
            "not_trained_on_Gate30_holdouts":True,
            "candidate_not_automatically_promoted":True
        }
        db.execute("INSERT INTO x46_frozen_cost_models VALUES(?,?,?,?,?,?,?,?)",(
            sha,"X46COST1",frozen.decode("ascii"),len(train),len(val),
            stamp(),"frozen_unpromoted",json.dumps(provenance,sort_keys=True)))
        count=db.execute("SELECT COUNT(*) FROM x46_training_events").fetchone()[0]
        commit(args.store,db,p)
    finally:
        t.cleanup()
    emit("X46_GLOBAL_MEMORY_STAGE",{
        "model_sha":sha,"global_training_events":count,"train_sources":len(train),
        "validation_sources":len(val),"legacy_X47_used_as_X46_training":False,
        "stage":"frozen_unpromoted"})
    args.summary.write_text(json.dumps({**provenance,"global_training_events":count,
       "stage":"frozen_unpromoted"},indent=2,sort_keys=True)+"\n")

def export(args):
    t,p,db=snapshot(args.store,mutable=False)
    try:
        found=db.execute(
          "SELECT frozen_text,model_version,evaluation_status FROM x46_frozen_cost_models WHERE model_sha=?",
          (args.model_sha,)).fetchone()
        if not found or found[1]!="X46COST1":
            raise RuntimeError("X46 model absent or schema-incompatible in global table")
        data=found[0].encode("ascii")
        if digest(data)!=args.model_sha:
            raise RuntimeError("frozen model content SHA corruption")
        if found[2]!="promoted" and not args.experimental:
            raise RuntimeError("X46 model not promoted; experimental flag required")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes(data)
        emit("X46_GLOBAL_MEMORY_LOADED",{"sha":args.model_sha,
             "state":found[2],"source":"global.SQLite.x46_frozen_cost_models",
             "experimental":args.experimental})
    finally:
        db.close()
        t.cleanup()

def finalize(args):
    report=json.loads(args.report.read_text())
    man=json.loads(args.manifest.read_text())
    if (not report["all_continuations_verified"] or
        report["distinct_original_sources"]!=112 or
        report["matched_checkpoint_pairs"]<300 or
        man["frozen_learned_model_sha256"]!=args.model_sha or
        man["source_generation_index_offset"]!=1600000 or
        len({s["sha256"] for s in man["sources"]})!=112):
        raise RuntimeError("sealed X46 holdout validation failed")
    trials=load_records(args.trials)
    if not all(r["verified"] and r["pre_hash"] for r in trials):
        raise RuntimeError("X46 matched-state verification failure")
    if len(trials)!=report["matched_checkpoint_pairs"]*len(man["arms"]):
        raise RuntimeError("X46 trials not complete")
    if not all(r.get("learned_model") for r in trials if
               r["arm"]=="X46_LEARNED_8" and r.get("probe_triggered")):
        raise RuntimeError("X46 learned model not actually used by controller")
    baseline=report["by_arm"]["X46_8"]
    core=report["by_arm"]["CORE"]
    candidate=report["by_arm"]["X46_LEARNED_8"]
    vs_base=report["comparisons_vs_CORE"]["X46_LEARNED_8"]
    # Gate against both CORE and native X46_8 rather than a surrogate metric.
    promote=(candidate["verified"]>=baseline["verified"] and
             candidate["verified"]>=core["verified"] and
             candidate["PAR2_verified_e2e_s"]<=.95*baseline["PAR2_verified_e2e_s"] and
             candidate["PAR2_verified_e2e_s"]<=.97*core["PAR2_verified_e2e_s"] and
             vs_base["formula_cluster_95pct"][0]>0.0)
    t,p,db=snapshot(args.store,mutable=True)
    try:
        record=db.execute("SELECT model_version FROM x46_frozen_cost_models WHERE model_sha=?",
                          (args.model_sha,)).fetchone()
        if not record or record[0]!="X46COST1":
            raise RuntimeError("unrecognized global model at final holdout")
        fresh={s["sha256"] for s in man["sources"]}
        if fresh & protected(db):
            raise RuntimeError("fresh sealed holdout overlaps train, valid or prior evaluations")
        for s in man["sources"]:
            db.execute("INSERT INTO x46_sealed_holdout_sources VALUES(?,?,?,?)",
                       (s["sha256"],args.model_sha,s["family"],"holdout"))
        for row in trials:
            if row["sha256"] not in fresh:raise RuntimeError("unknown result SHA")
            db.execute("INSERT INTO x46_sealed_holdout_trials VALUES(?,?,?,?,?,?,?,?)",(
                args.model_sha,row["sha256"],int(row["checkpoint"]),int(row["rep"]),
                row["arm"],row["status"],int(row["verified"]),float(row["PAR2"])))
        state="promoted" if promote else "rejected_benchmark_not_better_than_CORE"
        db.execute("UPDATE x46_frozen_cost_models SET evaluation_status=? WHERE model_sha=?",
                   (state,args.model_sha))
        commit(args.store,db,p)
    finally:t.cleanup()
    summary={"stage":state,"promoted":promote,"model_sha":args.model_sha,
             "holdout_sources":112,"paired_checkpoint_rows":report["matched_checkpoint_pairs"],
             "trials":len(trials),"legacy_X47_training_used":False,
             "arms":{name:{"PAR2_s":v["PAR2_verified_e2e_s"],
                            "verified":v["verified"],
                            "continuation_conflicts":v["continuation_conflicts"]}
                     for name,v in report["by_arm"].items()},
             "learned_vs_CORE":vs_base,
             "gate_rule":"5% less PAR2 than X46_8 and 3% less than CORE; paired 95% lower>0; solved parity",
             "caveat":"Microsecond-scale synthetics and bounded checkpoint continuations; not proof of faster full industrial SAT."}
    args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    emit("X46_GLOBAL_MEMORY_FINAL",summary)

def main():
    a=argparse.ArgumentParser()
    sub=a.add_subparsers(dest="cmd",required=True)
    for name in ("stage","export","finalize"):
        s=sub.add_parser(name)
        s.add_argument("--store",type=Path,required=True)
        if name=="stage":
            for key in ("manifest","trials","model","learn-report","summary"):
                s.add_argument("--"+key,type=Path,required=True)
        elif name=="export":
            s.add_argument("--model-sha",required=True)
            s.add_argument("--output",type=Path,required=True)
            s.add_argument("--experimental",action="store_true")
        else:
            for key in ("manifest","trials","report","summary"):
                s.add_argument("--"+key,type=Path,required=True)
            s.add_argument("--model-sha",required=True)
    args=a.parse_args()
    {"stage":stage,"export":export,"finalize":finalize}[args.cmd](args)

if __name__=="__main__":
    main()

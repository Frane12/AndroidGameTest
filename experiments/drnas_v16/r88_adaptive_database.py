#!/usr/bin/env python3
"""R88 audited append-only adaptive research warehouse (SQLite + CSV + Markdown).

Rows and frozen original-source SHA are validated before learning. Historic
rows may inform development hypotheses, but do not select the current cohort
or alter this run's solver policy. No claim of blind holdout or LRAT validity.
"""
from __future__ import annotations
import argparse, collections, csv, json, shutil, sqlite3, statistics, sys
from pathlib import Path
import r88_cooperative as core
from r88_bulk_import import PROTO as IMPORT_PROTO

SCHEMA="""
CREATE TABLE IF NOT EXISTS observations (
 source_sha TEXT NOT NULL, source_id TEXT NOT NULL, year INTEGER NOT NULL,
 run_id TEXT NOT NULL, git_commit TEXT NOT NULL, mode TEXT NOT NULL, rep INTEGER NOT NULL,
 structure TEXT NOT NULL, nvars INTEGER, nclauses INTEGER, components INTEGER,
 horn_fraction REAL, binary_fraction REAL, bridge_variables INTEGER,
 certified_lemmas INTEGER, broadcasts INTEGER, lemmas_after_prior_sharing INTEGER,
 preparation_seconds REAL, wall_seconds REAL, total_par2_seconds REAL,
 answer TEXT NOT NULL, prior_tested TEXT, inserted_utc TEXT DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(source_sha,run_id,mode,rep)
);
CREATE INDEX IF NOT EXISTS observations_structure ON observations(structure);
CREATE INDEX IF NOT EXISTS observations_source ON observations(source_id);
CREATE TABLE IF NOT EXISTS source_registry(
 source_id TEXT PRIMARY KEY, source_sha TEXT NOT NULL, year INTEGER NOT NULL,
 structure TEXT NOT NULL, first_run TEXT NOT NULL,
 source_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_audits (
 run_id TEXT PRIMARY KEY, git_commit TEXT NOT NULL,
 cases INTEGER NOT NULL, trials INTEGER NOT NULL,
 status TEXT NOT NULL, audit_utc TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def checkpoint(root):
    manifests=[]
    for m in sorted(root.rglob("manifest.json")):
        if "r88-sources" not in str(m):continue
        obj=json.loads(m.read_text())
        core.require(obj["protocol"]==IMPORT_PROTO,"source protocol mismatch")
        core.require(0<=obj["shard"]<4 and obj["year"] in (0,2025,2026),"unexpected shard")
        manifests.append((m,obj))
    core.require(len(manifests)==12,"exactly twelve real import shard manifests required")
    core.require(len({(x["year"],x["shard"]) for _,x in manifests})==12,
                 "source shards missing/duplicated")
    sources={}
    for path,m in manifests:
        for c in m["cases"]:
            source=path.parent/c["filename"]
            core.require(source.is_file() and core.sha(source)==c["sha256"],
                         "original source SHA mismatch")
            core.require(c["gbd"] not in sources,"GBD repeated across sources")
            sources[c["gbd"]]=c
    core.require(len(sources)>=12,"too few real originals")
    return manifests,sources

def audit(args):
    root=Path(args.combined)
    manifests,sources=checkpoint(root)
    result_files=sorted(p for p in root.rglob("rows.json")
                        if "r88-results" in str(p))
    core.require(len(result_files)==12,"twelve matched result shards required")
    rows=[]
    for f in result_files:
        r=json.loads(f.read_text())
        core.require(isinstance(r,list),"malformed results")
        rows.extend(r)
    require=core.require
    require(len(rows)==len(sources)*core.REPS*len(core.MODES),
            "incomplete trials or mismatched sources")
    groups=collections.defaultdict(list)
    for row in rows:
        require(row["source_id"] in sources,"result source not in frozen manifest")
        c=sources[row["source_id"]]
        require(row["source_sha"]==c["sha256"] and row["year"]==c["year"],
                "wrong source SHA/year")
        require(row["index_sha"] in {m["index_sha256"] for _,m in manifests},
                "index SHA missing from frozen cohort")
        require(row["mode"] in core.MODES and row["rep"] in range(core.REPS),
                "unknown mode/repetition")
        require(row["answer"] in ("SAT","UNSAT","TIMEOUT"),"bad answer")
        require(0<=row["certified_lemmas"]<=48,"invalid certified count")
        groups[row["source_sha"]].append(row)
    for key, rr in groups.items():
        combos={(x["mode"],x["rep"]) for x in rr}
        require(combos=={(m,r) for m in core.MODES for r in range(core.REPS)},
                "missing/duplicated paired arm")
        verdict={x["answer"] for x in rr if x["answer"]!="TIMEOUT"}
        require(len(verdict)<=1,"conflicting SAT/UNSAT verdicts")
    require(len(groups)==len(sources),"wrong unique source count")
    run_ids={r["run_id"] for r in rows}
    commits={r["commit"] for r in rows}
    require(len(run_ids)==len(commits)==1,"mixed run/commit provenance")
    run_id=next(iter(run_ids));commit=next(iter(commits))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    db=out/"drnas_r88_knowledge.sqlite"
    if args.prior and Path(args.prior).is_file():
        shutil.copyfile(args.prior,db)
    con=sqlite3.connect(db)
    con.executescript(SCHEMA)
    con.execute("BEGIN")
    for c in sources.values():
        con.execute("INSERT OR IGNORE INTO source_registry VALUES(?,?,?,?,?,?)",
            (c["gbd"],c["sha256"],c["year"],c["structure"],run_id,
            c["source_url"]))
    for r in rows:
        con.execute("""INSERT OR IGNORE INTO observations(
        source_sha,source_id,year,run_id,git_commit,mode,rep,structure,
        nvars,nclauses,components,horn_fraction,binary_fraction,bridge_variables,
        certified_lemmas,broadcasts,lemmas_after_prior_sharing,preparation_seconds,
        wall_seconds,total_par2_seconds,answer,prior_tested)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (r["source_sha"],r["source_id"],r["year"],run_id,commit,
        r["mode"],r["rep"],r["structure"],r["variables"],r["clauses"],
        r["components"],r["horn_fraction"],r["binary_fraction"],
        r["bridge_variables"],r["certified_lemmas"],r["broadcasts"],
        r["lemmas_after_prior_sharing"],r["prep_s"],r["wall_s"],
        r["total_par2_s"],r["answer"],str(r["prior_tested"])))
    con.execute("INSERT OR REPLACE INTO run_audits(run_id,git_commit,cases,trials,status) VALUES(?,?,?,?,?)",
                (run_id,commit,len(groups),len(rows),"AUDITED_PAIRS"))
    con.commit()
    total_cases=con.execute("SELECT count(*) FROM source_registry").fetchone()[0]
    total_trials=con.execute("SELECT count(*) FROM observations").fetchone()[0]
    decisions=[]
    for structure, in con.execute("SELECT DISTINCT structure FROM observations"):
        clean=collections.defaultdict(dict)
        for s,mode,rep,score in con.execute(
            "SELECT source_sha,mode,rep,total_par2_seconds FROM observations WHERE structure=?",
            (structure,)):
            clean[(s,rep)][mode]=score
        for candidate,reference in [("cooperative","clean"),
                                    ("cooperative_native","native_r87")]:
            improvements=[v[reference]-v[candidate] for v in clean.values()
                           if reference in v and candidate in v]
            if improvements:
                unique_cases=len({s for s,rep in clean if
                    candidate in clean[(s,rep)] and reference in clean[(s,rep)]})
                median=statistics.median(improvements)
                wins=sum(x>0 for x in improvements)
                # Conservative descriptive gate, NOT a trained final policy.
                status=("HYPOTHESIS_ONLY" if unique_cases<20 else
                        "PROSPECTIVE_HOLDOUT_REQUIRED")
                decisions.append(dict(structure=structure,
                    candidate=candidate,baseline=reference,
                    paired_repeats=len(improvements),unique_formulas=unique_cases,
                    median_saved_s=round(median,6),wins=wins,
                    losses=sum(x<0 for x in improvements),
                    status=status))
    con.close()
    (out/"observations.json").write_text(json.dumps(rows,indent=2)+"\n")
    with (out/"observations.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    (out/"adaptive_indications.json").write_text(
        json.dumps(dict(source_count=total_cases,trials=total_trials,
            hypotheses=decisions),indent=2)+"\n")
    (out/"history_ids.json").write_text(json.dumps(dict(
        previous_ids=sorted(sources.keys())),indent=2)+"\n")
    md=["# DRNAS R88 audited cooperative SAT laboratory","",
       f"Real original CNFs in this run: **{len(groups)}**",
       "Cohorts: archival 2002-2024 (year=0 marker), 2025, 2026.",
       f"Paired run trials: **{len(rows)}**",
       f"Accumulated distinct original IDs: **{total_cases}**",
       f"Accumulated observation rows: **{total_trials}**","",
       "Methods: clean Kissat, cooperative source-certified preprocessing, ",
       "R87 native, and cooperative + R87. Preparation is INCLUDED in total PAR-2.",
       "SAT model is checked on original DIMACS; UNSAT has no LRAT proof.",
       "These are exploratory observations, not evidence of a world record.","",
       "| Structure | Candidate vs baseline | Unique cases | Median saved seconds | Wins / losses |",
       "|---|---|---:|---:|---:|"]
    for d in sorted(decisions,key=lambda x:(x["structure"],x["candidate"])):
        md.append(f'| {d["structure"]} | {d["candidate"]} vs {d["baseline"]} | {d["unique_formulas"]} | {d["median_saved_s"]:+.4f} | {d["wins"]} / {d["losses"]} |')
    md+=["","Hypotheses require fresh, future, source-disjoint validation.",
         "Cron operates only after workflow is merged onto repository default branch."]
    (out/"R88_ADAPTIVE_REPORT.md").write_text("\n".join(md)+"\n")
    print("R88_AUDIT_PASS",len(groups),len(rows),total_cases,total_trials,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--combined",required=True);p.add_argument("--out",required=True)
    p.add_argument("--prior")
    a=p.parse_args();audit(a)
if __name__=="__main__":main()

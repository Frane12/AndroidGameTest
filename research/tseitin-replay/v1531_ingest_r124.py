#!/usr/bin/env python3
"""Strict additive R124 evidence warehouse. Never mutate V15.3.1 or historical core tables.

R124 is a shadow XOR discovery probe that delegates decisions to R118/Kissat.
UNSAT outcomes without independent proofs are explicitly *unverified*; their
measured PAR-2 is retained as a benchmark observation, never proof of correctness.
Previously tested R115 is kept separate from 90 new externally sourced cases.
"""
import argparse, csv, hashlib, json, math, sqlite3
from pathlib import Path
from collections import defaultdict

RUN="42018077150"
COMMIT="849b4543eec29b14c0a1a15243714b435fde0e0e"
PROTO="DRNAS-R124-FROZEN-EXTERNAL-MIXED-20261105-v1"
CONTROL_SHA="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
MODES=("r124","r118","kissat","cryptominisat")
SHARDS=8
REPS=2
CAP=15.0
NFORMULAS=91
BASE=(231,2979,53330)

def check(ok,reason):
    if not ok: raise RuntimeError("R124_INGEST_REFUSED: "+reason)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def readjson(path):return json.loads(Path(path).read_text())
def export(path,rows,fields):
    with Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def check_baseline(db):
    check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    counts=tuple(db.execute("SELECT COUNT(*) FROM "+x).fetchone()[0] for x in ("datasets","formulas","attempts"))
    check(counts==BASE,"immutable core record count changed "+str(counts))
    return counts

def schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS r124_sources(
      source_run TEXT PRIMARY KEY, git_commit TEXT NOT NULL, aggregate_sha256 TEXT NOT NULL,
      frozen_manifest_sha256 TEXT NOT NULL, source_artifact_id INTEGER NOT NULL,
      frozen_artifact_id INTEGER NOT NULL, source_zip_sha256 TEXT NOT NULL,
      frozen_zip_sha256 TEXT NOT NULL, protocol TEXT NOT NULL, runner_models_json TEXT NOT NULL,
      correct_scope TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS r124_formula_evidence(
      source_run TEXT NOT NULL, formula_sha256 TEXT NOT NULL, case_name TEXT NOT NULL,
      cohort TEXT NOT NULL, novelty TEXT NOT NULL, source_url TEXT NOT NULL,
      source_id TEXT NOT NULL, original_raw_sha256 TEXT, variables INTEGER,
      clauses INTEGER, selection_seed TEXT, frozen_manifest_sha256 TEXT NOT NULL,
      PRIMARY KEY(source_run,formula_sha256), UNIQUE(source_run,case_name));
    CREATE TABLE IF NOT EXISTS r124_attempt_evidence(
      source_run TEXT NOT NULL, formula_sha256 TEXT NOT NULL,
      solver TEXT NOT NULL, repetition INTEGER NOT NULL,
      status TEXT NOT NULL, seconds REAL NOT NULL, par2_seconds REAL NOT NULL,
      route TEXT NOT NULL, verification_tier TEXT NOT NULL, correct INTEGER,
      sat_model_checked INTEGER, unsat_proof_checked INTEGER,
      exact_xor INTEGER, resolution_xor INTEGER, partial_xor_candidates INTEGER,
      probe_skipped INTEGER, runner TEXT NOT NULL, runner_cpu_model TEXT NOT NULL,
      source_commit TEXT NOT NULL, formula_seed TEXT NOT NULL,
      source_artifact_id INTEGER NOT NULL, artifact_zip_sha256 TEXT NOT NULL,
      raw_row_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
      PRIMARY KEY(source_run,formula_sha256,solver,repetition));
    CREATE TABLE IF NOT EXISTS r124_shard_lineage(
      source_run TEXT NOT NULL, shard INTEGER NOT NULL, artifact_id INTEGER NOT NULL,
      artifact_zip_sha256 TEXT NOT NULL, raw_json_sha256 TEXT NOT NULL,
      commit_sha TEXT NOT NULL, cpu_model TEXT NOT NULL,
      solver_binary_pins_sha256 TEXT NOT NULL,
      PRIMARY KEY(source_run,shard));
    """)
def artifact_index(path):
    result={}
    for l in Path(path).read_text().splitlines():
        parts=l.split("\t")
        check(len(parts)>=4,"artifact line format")
        name,aid,expired,digest=parts[:4]
        check(name not in result and expired=="false" and digest.startswith("sha256:"),"artifact expired/digest/duplicate "+name)
        check(len(digest)==71,"malformed artifact digest")
        result[name]=(int(aid),digest.removeprefix("sha256:"))
    expected={"R124-EXTERNAL-MIXED-SELECTIVE-PAR2-AUDIT","r124-frozen-external-mixed"}|{"r124-shard-"+str(i) for i in range(SHARDS)}
    check(set(result)==expected,"not exactly 10 expected source artifacts")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--input",type=Path)
    p.add_argument("--verify-existing",action="store_true")
    args=p.parse_args()
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(args.db)
    try:
        core_before=check_baseline(db)
        schema(db)
        existing=db.execute("SELECT aggregate_sha256 FROM r124_sources WHERE source_run=?",(RUN,)).fetchone()
        if args.verify_existing:
            check(existing is not None,"R124 missing, cannot verify")
            check(db.execute("SELECT COUNT(*) FROM r124_formula_evidence WHERE source_run=?",(RUN,)).fetchone()[0]==NFORMULAS,"existing formula count")
            check(db.execute("SELECT COUNT(*) FROM r124_attempt_evidence WHERE source_run=?",(RUN,)).fetchone()[0]==NFORMULAS*REPS*len(MODES),"existing attempts count")
            check(db.execute("SELECT COUNT(*) FROM r124_shard_lineage WHERE source_run=?",(RUN,)).fetchone()[0]==SHARDS,"existing shard count")
            check_baseline(db)
            print("R124_IDEMPOTENT_VERIFIED_NO_NEW_INSERT",RUN)
            return
        check(existing is None,"run already ingested, refusing duplicate")
        check(args.input is not None,"input required for new ingest")
        root=args.input
        artifacts=artifact_index(root/"artifact_index.tsv")
        ar=root/"aggregate";frozen=root/"frozen"
        report=readjson(ar/"results.json");manifest=readjson(frozen/"manifest.json")
        check(report["protocol"]==PROTO and manifest["protocol"]==PROTO,"protocol identity")
        check((report["formula_count"],report["attempts"],report["shards"],report["limit_seconds"])==(91,728,8,15.0),"aggregate dimensions")
        check(tuple(manifest["modes"])==MODES and manifest["reps"]==REPS and manifest["shards"]==SHARDS,"manifest solver modes/reps/shards")
        check(len(manifest["cases"])==NFORMULAS and len({c["sha256"] for c in manifest["cases"]})==NFORMULAS,"source SHA duplicates")
        check(len([c for c in manifest["cases"] if c["cohort"]=="miter"])==40,"miter sample size")
        check(len([c for c in manifest["cases"] if c["cohort"]=="official2026"])==50,"official2026 source sample size")
        check(len([c for c in manifest["cases"] if c["cohort"]=="r115_control"])==1,"R115 control size")
        check(manifest.get("cap_seconds")==CAP,"manifest cap")
        check(set(report["by_cohort"])=={"miter","official2026","r115_control","all"},"aggregate cohort labels")
        check(sum(report["by_cohort"][c]["formulas"] for c in ("miter","official2026","r115_control"))==NFORMULAS,"aggregate cohorts")
        check(report["source_commits"]==[COMMIT],"aggregate source commit changed")
        check(len(report["cpu_models"])>=1,"missing source CPU models")
        check(len(report["binary_set_sha256"])==64,"missing solver binary pin")
        frozen_sha=sha(frozen/"manifest.json");agg_sha=sha(ar/"results.json")
        prior={x for (x,) in db.execute("SELECT formula_sha256 FROM formulas") if x}
        seen=set();cases={};new_count=0;historical_count=0
        for c in manifest["cases"]:
            h=c["sha256"];cohort=c["cohort"];name=c["id"]
            check(len(h)==64 and h not in seen,"invalid/duplicate formula SHA")
            seen.add(h);cases[name]=c
            f=frozen/name
            check(f.is_file() and sha(f)==h,"original CNF SHA mismatch "+name)
            check(len(c.get("raw_sha256",""))==64,"raw-download SHA absent "+name)
            check(c["variables"]>0 and c["clauses"]>0 and c["bytes"]==f.stat().st_size,"CNF metadata "+name)
            check(c["url"].startswith(("https://benchmark-database.de/","https://","http://")),"source URL "+name)
            if cohort=="r115_control":
                check(h==CONTROL_SHA and c["gbd"]=="75429ff7acb5acb597abe01aa745c2a6","R115 identity")
                novelty="historical_R115_control";historical_count+=1
            elif h in prior:
                novelty="external_previously_seen";historical_count+=1
            else:
                novelty="external_new_relative_to_sqlite";new_count+=1
            db.execute("INSERT INTO r124_formula_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              (RUN,h,name,cohort,novelty,c["url"],c["gbd"],c.get("raw_sha256"),c["variables"],c["clauses"],
               PROTO+"-"+cohort,frozen_sha))
        check(new_count+historical_count==NFORMULAS,"formula count/novelty")
        rrows=[];per_case=defaultdict(dict);pins=set();commits=set();cpu_models=set()
        for shard in range(SHARDS):
            path=root/"shards"/str(shard)
            raw=path/("shard-"+str(shard)+".json")
            cp=path/("commit-"+str(shard)+".txt")
            cpu=path/("cpu-"+str(shard)+".txt")
            pin=path/("solver-sha256-"+str(shard)+".txt")
            for f in (raw,cp,cpu,pin):check(f.is_file(),"missing raw lineage "+str(f))
            commit=cp.read_text().strip();check(commit==COMMIT,"shard SHA pin "+str(shard))
            hardware=next((x.strip() for x in cpu.read_text().splitlines() if x.strip().startswith("Model name:")),"")
            check(hardware,"missing CPU model "+str(shard))
            binary_pin=pin.read_text().strip()
            check(len(binary_pin)>100 and "r124_probe" in binary_pin and "r118" in binary_pin,"solver pin "+str(shard))
            pins.add(binary_pin);commits.add(commit);cpu_models.add(hardware)
            rows=readjson(raw)
            check(isinstance(rows,list) and len(rows)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),"shard incomplete "+str(shard))
            artifact=artifacts["r124-shard-"+str(shard)]
            db.execute("INSERT INTO r124_shard_lineage VALUES(?,?,?,?,?,?,?)",
              (RUN,shard,artifact[0],artifact[1],sha(raw),commit,hardware,hashlib.sha256(binary_pin.encode()).hexdigest()))
            keys=set()
            for row in rows:
                key=(row["id"],int(row["rep"]),row["mode"])
                check(key not in keys,"duplicate within shard "+str(key));keys.add(key)
                check(row["id"] in cases and list(cases).index(row["id"])%SHARDS==shard,"incorrect shard allocation")
                c=cases[row["id"]];h=c["sha256"];mode=row["mode"];rep=int(row["rep"])
                check(row["sha256"]==h and row["cohort"]==c["cohort"],"source SHA/cohort row mismatch")
                check(mode in MODES and rep in range(REPS),"invalid mode/repetition")
                status=row["status"];proof=row["proof"];route=row["route"]
                check(status in ("SAT","UNSAT","TIMEOUT"),"unknown status")
                seconds=float(row["seconds"]);par2=float(row["par2"])
                check(math.isfinite(seconds) and 0<=seconds<=CAP+.05,"time range")
                check(math.isfinite(par2) and abs(par2-(CAP*2 if status=="TIMEOUT" else seconds))<1e-5,"PAR-2 calculation")
                check(proof in ("source_SAT_witness_verified","source_XOR_UNSAT_cert_verified","independent_source_gate_truth_table_verified","UNSAT_not_independently_verified","UNVERIFIED_gate_gt12_inputs","timeout"),"unexpected proof label")
                if status=="SAT":check(proof=="source_SAT_witness_verified","SAT witness missing")
                if status=="TIMEOUT":check(proof=="timeout","timeout verification mislabeled")
                if status=="UNSAT":check(proof in ("source_XOR_UNSAT_cert_verified","independent_source_gate_truth_table_verified","UNSAT_not_independently_verified","UNVERIFIED_gate_gt12_inputs"),"UNSAT proof tier")
                verified=1 if proof in ("source_SAT_witness_verified","source_XOR_UNSAT_cert_verified","independent_source_gate_truth_table_verified") else None
                sat=1 if status=="SAT" and verified==1 else None
                unsat=1 if status=="UNSAT" and verified==1 else None
                if mode=="r124":
                    check(row.get("xor_exact") is not None or status=="TIMEOUT","missing XOR telemetry")
                if mode!="r124":
                    check(row.get("xor_exact") is None,"baseline has probe telemetry")
                raw_json=json.dumps(row,sort_keys=True,separators=(",",":"))
                db.execute("INSERT INTO r124_attempt_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (RUN,h,mode,rep,status,seconds,par2,route,proof,verified,sat,unsat,
                    row.get("xor_exact"),row.get("xor_resolved"),row.get("xor_partial_hypotheses"),
                    row.get("probe_skipped"),"github-hosted-ubuntu-24.04",hardware,commit,
                    PROTO+h+str(rep),artifact[0],artifact[1],
                    hashlib.sha256(raw_json.encode()).hexdigest(),raw_json))
                per_case[h,rep][mode]=row
                rrows.append((c,hardware,row))
        check(len(commits)==1 and len(pins)==1,"mixed binary source SHA across runners")
        check(len(rrows)==NFORMULAS*REPS*len(MODES),"total rows")
        check(len(per_case)==NFORMULAS*REPS,"paired sample count")
        for key,g in per_case.items():
            check(set(g)==set(MODES),"incomplete pairs "+str(key))
            answers={v["status"] for v in g.values()}-{"TIMEOUT"}
            check(len(answers)<=1,"SAT/UNSAT disagreement "+str(key))
        # Compare independently recomputed grouped PAR-2 against the final report.
        for cohort in ("miter","official2026","r115_control","all"):
            selected=[r for c,hw,r in rrows if cohort=="all" or c["cohort"]==cohort]
            for mode in MODES:
                rs=[r for r in selected if r["mode"]==mode]
                agg=report["by_cohort"][cohort]["solvers"][mode]
                check(agg["attempts"]==len(rs),"summary attempt mismatch "+cohort+"/"+mode)
                check(agg["solved"]==sum(r["status"]!="TIMEOUT" for r in rs),"summary solved mismatch "+cohort+"/"+mode)
                check(abs(agg["par2_s"]-sum(r["par2"] for r in rs))<.0001,"PAR2 differs from report "+cohort+"/"+mode)
        db.execute("INSERT INTO r124_sources VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          (RUN,COMMIT,agg_sha,frozen_sha,artifacts["R124-EXTERNAL-MIXED-SELECTIVE-PAR2-AUDIT"][0],
           artifacts["r124-frozen-external-mixed"][0],
           artifacts["R124-EXTERNAL-MIXED-SELECTIVE-PAR2-AUDIT"][1],
           artifacts["r124-frozen-external-mixed"][1],
           PROTO,json.dumps(sorted(cpu_models)),
           "R124 shadow XOR only; no live acceleration. SAT witness verified; uncertified UNSAT remains NULL. Historical R115 separate."))
        check(db.execute("SELECT COUNT(*) FROM r124_formula_evidence WHERE source_run=?",(RUN,)).fetchone()[0]==NFORMULAS,"post-insert formulas")
        check(db.execute("SELECT COUNT(*) FROM r124_attempt_evidence WHERE source_run=?",(RUN,)).fetchone()[0]==728,"post-insert attempts")
        check(db.execute("SELECT COUNT(*) FROM r124_shard_lineage WHERE source_run=?",(RUN,)).fetchone()[0]==8,"post-insert shard lineage")
        check_baseline(db)
        db.commit()
    finally:db.close()
    db=sqlite3.connect(args.db)
    try:
        fcols=["cohort","novelty","formula_sha256","case_name","source_id","source_url","variables","clauses"]
        formulas=[dict(zip(fcols,x)) for x in db.execute(
          "SELECT cohort,novelty,formula_sha256,case_name,source_id,source_url,variables,clauses FROM r124_formula_evidence WHERE source_run=? ORDER BY cohort,case_name",(RUN,))]
        export(out/"r124_source_audit.csv",formulas,fcols)
        acols=["cohort","novelty","formula_sha256","solver","repetition","status","seconds","par2_seconds","route","verification_tier","correct","exact_xor","resolution_xor","partial_xor_candidates","runner","runner_cpu_model","source_commit","formula_seed","source_artifact_id","artifact_zip_sha256"]
        rows=[dict(zip(acols,x)) for x in db.execute("""SELECT f.cohort,f.novelty,a.formula_sha256,a.solver,a.repetition,
          a.status,a.seconds,a.par2_seconds,a.route,a.verification_tier,a.correct,a.exact_xor,
          a.resolution_xor,a.partial_xor_candidates,a.runner,a.runner_cpu_model,a.source_commit,
          a.formula_seed,a.source_artifact_id,a.artifact_zip_sha256
          FROM r124_attempt_evidence a JOIN r124_formula_evidence f
          ON a.source_run=f.source_run AND a.formula_sha256=f.formula_sha256
          WHERE a.source_run=? ORDER BY f.cohort,f.case_name,a.repetition,a.solver""",(RUN,))]
        export(out/"r124_attempts.csv",rows,acols)
        pair=[]
        groups=defaultdict(dict)
        for r in rows:groups[(r["cohort"],r["novelty"],r["formula_sha256"],r["repetition"])][r["solver"]]=r
        for (cohort,novelty,h,rep),g in sorted(groups.items()):
            pair.append({"cohort":cohort,"novelty":novelty,"formula_sha256":h,"repetition":rep,
              "r124_PAR2":g["r124"]["par2_seconds"],"r118_PAR2":g["r118"]["par2_seconds"],
              "kissat_PAR2":g["kissat"]["par2_seconds"],"cryptominisat_PAR2":g["cryptominisat"]["par2_seconds"],
              "resolved_xor":g["r124"]["resolution_xor"],"exact_xor":g["r124"]["exact_xor"]})
        export(out/"r124_paired.csv",pair,list(pair[0]))
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for cohort in ("miter","official2026","r115_control"):
            p=[x for x in pair if x["cohort"]==cohort]
            fig,ax=plt.subplots(figsize=(7,5))
            ax.scatter([x["kissat_PAR2"] for x in p],[x["r124_PAR2"] for x in p],s=18,alpha=.7)
            ax.plot([0,30],[0,30],"k--",linewidth=1)
            ax.set(xlabel="Kissat PAR-2 seconds",ylabel="R124 PAR-2 seconds",
                   title="R124 shadow XOR vs Kissat | "+cohort+" | verified source, UNSAT labels may be unproven")
            fig.tight_layout();fig.savefig(out/("scatter_r124_"+cohort+".png"),dpi=140);plt.close(fig)
        n_unchecked=sum(x["status"]=="UNSAT" and x["correct"] is None for x in rows)
        n_sat=sum(x["status"]=="SAT" and x["correct"]==1 for x in rows)
        audit={"status":"R124_ADDITIVE_EVIDENCE_INGEST_WITH_UNVERIFIED_UNSAT_LABELS",
          "source_run":RUN,"source_commit":COMMIT,"historical_core_before_and_after":BASE,
          "source_formulas":len(formulas),"measurement_rows":len(rows),"paired_cases":len(pair),
          "source_sha_unique":len({x["formula_sha256"] for x in formulas}),
          "previously_seen_or_control":sum(x["novelty"]!="external_new_relative_to_sqlite" for x in formulas),
          "new_relative_to_cumulative_sqlite":sum(x["novelty"]=="external_new_relative_to_sqlite" for x in formulas),
          "SAT_verified_attempts":n_sat,"UNSAT_without_independent_proof":n_unchecked,
          "no_live_speedup_claim":True,
          "R115_historical_control_excluded_from_new_external_statistics":True,
          "no_changes_to_core_dataset_formula_attempt_tables":True}
        (out/"r124_ingest_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        summary=out/"summary.json"
        data=json.loads(summary.read_text()) if summary.is_file() else {}
        data["r124_shadow_source_evidence"]=audit
        summary.write_text(json.dumps(data,indent=2)+"\n")
        print("R124_SQLITE_ADD_SUCCESS",json.dumps(audit,sort_keys=True))
    finally:db.close()

if __name__=="__main__":main()

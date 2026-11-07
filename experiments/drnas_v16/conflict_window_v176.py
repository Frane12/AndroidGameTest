#!/usr/bin/env python3
"""DRNAS V17.6 — conflict-window A/B, exact pinned Kissat 4.0.4.

Exploratory intervention: start with default restartint=1, then change in-place
to 25 after 256/512/1024/2048 conflicts. This is *not* guaranteed to improve.
No subprocess reset: learned clauses are retained. Compare against untouched
baseline, fixed25 and fixed50. Independent 175xxx set is frozen before tests.

The experiment tests *timing*, not an adaptive rule selected from holdout.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODES=("baseline","fixed25","fixed50","switch256","switch512","switch1024","switch2048")
DEV=tuple(range(176000,176020))  # 20 new development formulas
HOLDOUT=tuple(range(176100,176120))  # 20 untouched prospective formulas
CAP=2.5
MARK=re.compile(r"^c DRNAS_V176 stage=(\w+) threshold=(\d+) conflicts=(\d+) restarts=(\d+) "
    r"learned_before=(\d+) learned_after=(\d+) decisions=(\d+) propagations=(\d+) "
    r"glue_fast=([0-9.]+) glue_slow=([0-9.]+) restart_before=(\d+) restart_after=(\d+)$",re.M)

def patch(src):
    """Exact-anchor patch, fails closed on upstream layout mismatch."""
    if "DRNAS_V176" in src:raise ValueError("already patched")
    def once(a,b):
        nonlocal src
        if src.count(a)!=1:raise ValueError(f"Expected exact upstream anchor: {a[:70]} got {src.count(a)}")
        src=src.replace(a,b,1)
    once("#include <inttypes.h>\n",
         "#include <inttypes.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n")
    once("int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
"""int kissat_search (kissat *solver) {
  const char *drnas_policy = getenv("DRNAS_V176_POLICY");
  const bool drnas_audit = drnas_policy && *drnas_policy;
  uint64_t drnas_conflict_start = 0;
  uint64_t drnas_switch_at = 0;
  bool drnas_switched = false;
  if (drnas_policy && !strncmp(drnas_policy, "switch", 6))
    drnas_switch_at = (uint64_t)strtoull(drnas_policy + 6, NULL, 10);
  REPORT (0, '*');""")
    once("    start_search (solver);\n    while (!res) {",
"""    start_search (solver);
    drnas_conflict_start = CONFLICTS;
    while (!res) {""")
    once("      if (conflict)\n        res = kissat_analyze (solver, conflict);\n      else if (solver->iterating)",
"""      if (conflict) {
        res = kissat_analyze (solver, conflict);
        if (drnas_audit && !res && !drnas_switched && drnas_switch_at &&
            CONFLICTS - drnas_conflict_start >= drnas_switch_at) {
          const uint64_t learned_before = solver->statistics.clauses_learned;
          const int restart_before = GET_OPTION(restartint);
          kissat_set_option(solver, "restartint", 25);
          if (!solver->stable)
            kissat_update_focused_restart_limit(solver);
          const uint64_t learned_after = solver->statistics.clauses_learned;
          fprintf(stdout,
            "c DRNAS_V176 stage=switch threshold=%" PRIu64
            " conflicts=%" PRIu64 " restarts=%" PRIu64
            " learned_before=%" PRIu64 " learned_after=%" PRIu64
            " decisions=%" PRIu64 " propagations=%" PRIu64
            " glue_fast=%.6f glue_slow=%.6f restart_before=%d restart_after=%d\\n",
            drnas_switch_at, CONFLICTS, solver->statistics.restarts,
            learned_before, learned_after, DECISIONS,
            solver->statistics.propagations,
            AVERAGE(fast_glue), AVERAGE(slow_glue),
            restart_before, GET_OPTION(restartint));
          fflush(stdout);
          drnas_switched=true;
        }
      } else if (solver->iterating)""")
    once("    stop_search (solver);\n  }\n  report_search_result (solver, res);",
"""    stop_search (solver);
    if (drnas_audit) {
      const uint64_t learned_final = solver->statistics.clauses_learned;
      fprintf(stdout,
        "c DRNAS_V176 stage=final threshold=%" PRIu64
        " conflicts=%" PRIu64 " restarts=%" PRIu64
        " learned_before=%" PRIu64 " learned_after=%" PRIu64
        " decisions=%" PRIu64 " propagations=%" PRIu64
        " glue_fast=%.6f glue_slow=%.6f restart_before=%d restart_after=%d\\n",
        drnas_switch_at, CONFLICTS, solver->statistics.restarts,
        learned_final, learned_final, DECISIONS,
        solver->statistics.propagations,
        AVERAGE(fast_glue), AVERAGE(slow_glue),
        GET_OPTION(restartint), GET_OPTION(restartint));
      fflush(stdout);
    }
  }
  report_search_result (solver, res);""")
    return src

def fresh_case(root,seed,stage):
    base=(176000 if stage=="dev" else 176100)
    n=(260,340,420)[(seed-base)%3]
    path=root/"cnf"/f"{seed}.cnf"
    h=generate(path,n,4.26,seed)
    return {"stage":stage,"seed":seed,"nvars":n,"density":4.26,
        "sha256":h,"path":str(path),**corrected_core(path)}

def command(solver,mode,path):
    flag=("--restartint=25",) if mode=="fixed25" else ("--restartint=50",) if mode=="fixed50" else ()
    return [solver,*flag,"-s",str(path)]

def attempt(solver,c,mode):
    env=os.environ.copy();env["DRNAS_V176_POLICY"]=mode
    started=time.perf_counter()
    path=Path(c["path"])
    try:
        p=subprocess.run(command(solver,mode,path),capture_output=True,text=True,
            errors="replace",env=env,check=False,timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        output=p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
        output=a+"\n"+b
    elapsed=round(time.perf_counter()-started,6)
    if status=="ERROR":raise RuntimeError(f"Solver error {mode}/{c['seed']}: {output[-1500:]}")
    if status=="SAT" and not valid_model(path,output):
        raise RuntimeError(f"Bad SAT assignment on {mode}/{c['seed']}")
    snapshots=[]
    for m in MARK.finditer(output):
        stage,threshold,conflicts,restarts,before,after,decisions,props,fast,slow,r0,r1=m.groups()
        snap={"stage":stage,"threshold":int(threshold),"conflicts":int(conflicts),
              "restarts":int(restarts),"learned_before":int(before),"learned_after":int(after),
              "decisions":int(decisions),"propagations":int(props),"glue_fast":float(fast),
              "glue_slow":float(slow),"restart_before":int(r0),"restart_after":int(r1)}
        assert snap["learned_before"]==snap["learned_after"],"Learned clauses lost at switch"
        snapshots.append(snap)
    switches=[x for x in snapshots if x["stage"]=="switch"]
    assert len(switches)<=1
    if mode.startswith("switch"):
        assert len(switches)==(1 if snapshots and snapshots[-1]["conflicts"]>=int(mode[6:]) else 0),(
            f"Switch checkpoint missed {mode}/{c['seed']} {snapshots[-1:]}")
        if switches:
            assert switches[0]["restart_before"]==1 and switches[0]["restart_after"]==25
    else:assert not switches
    return status,elapsed,snapshots

def write_csv(path,rows):
    if rows:
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path)
    p.add_argument("--solver")
    p.add_argument("--stage",choices=("dev","holdout"))
    p.add_argument("--root",type=Path,default=Path("drnas-v176-results"))
    a=p.parse_args()
    if a.kissat_root:
        path=a.kissat_root/"src"/"search.c"
        before=path.read_text();after=patch(before);path.write_text(after)
        print("V176_PINNED_PATCH_PASS",PINNED,hashlib.sha256(after.encode()).hexdigest(),flush=True)
        return
    if not a.solver or not a.stage:p.error("--solver and --stage required")
    a.root.mkdir(parents=True,exist_ok=True)
    seeds=DEV if a.stage=="dev" else HOLDOUT
    cases=[fresh_case(a.root,seed,a.stage) for seed in seeds]
    manifest={"version":"V17.6","protocol":"Frozen conflict-window timing, preserves learned clauses",
       "pin":PINNED,"stage":a.stage,"development_only":a.stage=="dev",
       "sample_design":"20 development plus 20 previously unseen, fixed random 3SAT at 4.26 density; same 7 policies",
       "primary_metric":"PAR-2, timeout = 5.0 s; rank only after complete stage",
       "cap":CAP,"repeats":1,"modes":MODES,"seeds":seeds,
       "no_holdout_selection":True,"cases":cases}
    (a.root/"manifest.json").write_text(json.dumps(manifest,indent=2))
    rows=[];snaprows=[]
    print("V176_START",a.stage,len(cases)*len(MODES),"paired measurements",flush=True)
    for c in cases:
        assert hashlib.sha256(Path(c["path"]).read_bytes()).hexdigest()==c["sha256"]
        for mode in MODES:
            status,elapsed,snaps=attempt(a.solver,c,mode)
            row={"stage":a.stage,"seed":c["seed"],"nvars":c["nvars"],
                 "mean_core":round(c["mean_core_corrected"],5),
                 "mode":mode,"status":status,"seconds":elapsed,
                 "switches":sum(s["stage"]=="switch" for s in snaps),
                 "final_conflicts":snaps[-1]["conflicts"] if snaps else "",
                 "final_restarts":snaps[-1]["restarts"] if snaps else ""}
            rows.append(row)
            for s in snaps:snaprows.append({"seed":c["seed"],"mode":mode,**s})
            print("V176_MEASURE",a.stage,c["seed"],mode,status,
                  f"{elapsed:.5f}s","switches",row["switches"],
                  "conflicts",row["final_conflicts"],flush=True)
        write_csv(a.root/"measurements.partial.csv",rows)
        write_csv(a.root/"snapshots.partial.csv",snaprows)
        pair_rows=[r for r in rows if r["seed"]==c["seed"]]
        paired_rank=sorted(pair_rows,key=lambda r:(
            r["seconds"] if r["status"] in ("SAT","UNSAT") else 2*CAP,
            r["mode"]))
        pair_summary={
            "stage":a.stage,
            "seed":c["seed"],"nvars":c["nvars"],
            "complete":len(pair_rows),
            "fastest":paired_rank[0]["mode"] if paired_rank[0]["status"] in ("SAT","UNSAT") else "NONE",
            "modes":[{"name":r["mode"],"status":r["status"],
                      "seconds":r["seconds"],
                      "conflicts":r["final_conflicts"],
                      "switches":r["switches"]} for r in paired_rank],
            "completed_cases":sum(1 for x in seeds if x<=c["seed"]),
            "total_cases":len(seeds)
        }
        print("V176_PAIR_SUMMARY",json.dumps(pair_summary,separators=(",",":")),flush=True)
    assert len(rows)==len(seeds)*len(MODES)
    for seed in seeds:
        answers={r["status"] for r in rows if r["seed"]==seed and r["status"] in ("SAT","UNSAT")}
        assert len(answers)<=1,"Solver SAT/UNSAT disagreement"
    ranking=[]
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        par2=statistics.mean([r["seconds"] if r["status"] in ("SAT","UNSAT") else 2*CAP for r in subset])
        ranking.append({"mode":mode,"solved":sum(r["status"] in ("SAT","UNSAT") for r in subset),
                        "attempts":len(subset),"PAR2":round(par2,6),
                        "switches":sum(r["switches"] for r in subset)})
    ranking.sort(key=lambda r:(r["PAR2"],-r["solved"],r["mode"]))
    baseline={r["seed"]:r for r in rows if r["mode"]=="baseline"}
    for item in ranking:
        candidate={r["seed"]:r for r in rows if r["mode"]==item["mode"]}
        item["rescues"]=sum(
            baseline[k]["status"]=="TIMEOUT" and
            candidate[k]["status"] in ("SAT","UNSAT") for k in baseline)
        item["regressions"]=sum(
            baseline[k]["status"] in ("SAT","UNSAT") and
            candidate[k]["status"]=="TIMEOUT" for k in baseline)
    write_csv(a.root/"measurements.csv",rows)
    write_csv(a.root/"snapshots.csv",snaprows)
    write_csv(a.root/"ranking.csv",ranking)
    summary={"stage":a.stage,"pin":PINNED,"cap":CAP,"rank":ranking,
             "limits":["One generator of random 3-SAT, only 1 repeat",
                "Development formulas are previously used",
                "Unseen 175xxx stage is independent but very small",
                "Timeout PAR-2 = 5 seconds",
                "A time switch changes a solver parameter; no cold restart"]}
    (a.root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V176_AUDIT_PASS",a.stage,len(rows),json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()

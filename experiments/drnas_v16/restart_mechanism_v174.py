#!/usr/bin/env python3
"""V17.4 short causal *mechanism* audit on ALREADY-USED seeds.

This is explicitly exploratory, NOT a blind benchmark or new record claim.
Compare exactly pinned upstream Kissat with runtime-only telemetry:
  baseline (-), restartint 25, restartint 50, target=2.
Observe restarts, conflicts, decisions, propagations and learned clauses at
fixed conflict checkpoints, plus SAT/UNSAT result and charged wall time.
"""
import argparse,csv,hashlib,json,os,re,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS=(172007,172010,172014,173000,173001,173003,173004)
MODES={"baseline":(),"restart25":("--restartint=25",),
       "restart50":("--restartint=50",),"target2":("--target=2",)}
CAP=3.0
MARK=re.compile(
 r'^c DRNAS_V174 mark=(1024|4096|16384|final) conflicts=(\d+)'
 r' restarts=(\d+) learned=(\d+) decisions=(\d+) props=(\d+)'
 r' fast_glue=(\S+) slow_glue=(\S+)$',re.M)

def patch(src):
    if "DRNAS_V174" in src:raise RuntimeError("Already patched")
    def once(old,new,reason):
        nonlocal src
        if src.count(old)!=1:raise ValueError(f"Upstream source mismatch at {reason}: {src.count(old)}")
        src=src.replace(old,new,1)
    once("#include <inttypes.h>\n",
         "#include <inttypes.h>\n#include <stdio.h>\n#include <stdlib.h>\n","includes")
    once("int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
"""int kissat_search (kissat *solver) {
  // Observational telemetry ONLY. The solver policy is untouched.
  const bool drnas_audit = getenv ("DRNAS_V174_AUDIT") != 0;
  uint64_t drnas_origin_conflicts = 0;
  unsigned drnas_index = 0;
  const uint64_t drnas_thresholds[] = {1024,4096,16384};
  REPORT (0, '*');""","entry")
    once("    start_search (solver);\n    while (!res) {",
"""    start_search (solver);
    drnas_origin_conflicts = CONFLICTS;
    while (!res) {""","search begin")
    once("      if (conflict)\n        res = kissat_analyze (solver, conflict);\n      else if (solver->iterating)",
"""      if (conflict) {
        res = kissat_analyze (solver, conflict);
        if (drnas_audit && drnas_index < 3 &&
            CONFLICTS - drnas_origin_conflicts >=
              drnas_thresholds[drnas_index]) {
          fprintf(stdout,
            "c DRNAS_V174 mark=%" PRIu64
            " conflicts=%" PRIu64 " restarts=%" PRIu64
            " learned=%" PRIu64 " decisions=%" PRIu64
            " props=%" PRIu64 " fast_glue=%.6f slow_glue=%.6f\\n",
            drnas_thresholds[drnas_index], CONFLICTS,
            solver->statistics.restarts,
            solver->statistics.clauses_learned,
            DECISIONS, solver->statistics.propagations,
            AVERAGE(fast_glue), AVERAGE(slow_glue));
          fflush(stdout);
          drnas_index++;
        }
      } else if (solver->iterating)""","analyze")
    once("    stop_search (solver);\n  }\n  report_search_result (solver, res);",
"""    stop_search (solver);
    if (drnas_audit) {
      fprintf(stdout,
        "c DRNAS_V174 mark=final conflicts=%" PRIu64
        " restarts=%" PRIu64 " learned=%" PRIu64
        " decisions=%" PRIu64 " props=%" PRIu64
        " fast_glue=%.6f slow_glue=%.6f\\n",
        CONFLICTS, solver->statistics.restarts,
        solver->statistics.clauses_learned,
        DECISIONS, solver->statistics.propagations,
        AVERAGE(fast_glue), AVERAGE(slow_glue));
      fflush(stdout);
    }
  }
  report_search_result (solver, res);""","final")
    return src

def work_case(root,seed):
    n=(260,340,420)[(seed-(173000 if seed>=173000 else 172000))%3]
    path=root/"cnf"/f"{seed}.cnf"
    sha=generate(path,n,4.26,seed)
    return {"seed":seed,"nvars":n,"sha256":sha,
            "path":str(path),**corrected_core(path)}

def run(solver,case,mode):
    env=os.environ.copy();env["DRNAS_V174_AUDIT"]="1"
    path=Path(case["path"])
    start=time.perf_counter()
    try:
        p=subprocess.run([solver,*MODES[mode],"-s",str(path)],
            capture_output=True,text=True,errors="replace",env=env,
            timeout=CAP,check=False)
        output=p.stdout+"\n"+p.stderr
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
        output=a+"\n"+b;status="TIMEOUT"
    seconds=time.perf_counter()-start
    if status=="ERROR":raise RuntimeError(f"Kissat failed {case['seed']} {mode}: {output[-2000:]}")
    if status=="SAT" and not valid_model(path,output):
        raise RuntimeError(f"Invalid witness for {case['seed']} {mode}")
    marks=[]
    for m in MARK.finditer(output):
        tag,conflicts,restarts,learned,decisions,props,fast,slow=m.groups()
        marks.append({"mark":tag,"conflicts":int(conflicts),"restarts":int(restarts),
                      "learned":int(learned),"decisions":int(decisions),
                      "propagations":int(props),"fast_glue":fast,"slow_glue":slow})
    assert len(marks)==len({m["mark"] for m in marks}),"duplicate checkpoint"
    if status in ("SAT","UNSAT"):assert marks and marks[-1]["mark"]=="final","Missing final audit"
    return status,round(seconds,6),marks

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path)
    p.add_argument("--solver")
    p.add_argument("--root",type=Path,default=Path("drnas-v174-audit"))
    args=p.parse_args()
    if args.kissat_root:
        f=args.kissat_root/"src"/"search.c"
        before=f.read_text()
        after=patch(before)
        f.write_text(after)
        print("V174_OBSERVATIONAL_PATCH",PINNED,hashlib.sha256(after.encode()).hexdigest(),flush=True)
        return
    if not args.solver:p.error("--solver required for audit")
    args.root.mkdir(parents=True,exist_ok=True)
    cases=[work_case(args.root,seed) for seed in SEEDS]
    (args.root/"manifest.json").write_text(json.dumps({
        "protocol":"V17.4 exploratory mechanism audit: reused V17.3 seeds",
        "NOT_BLIND":True,"pin":PINNED,"cap_seconds":CAP,
        "seeds":list(SEEDS),"modes":list(MODES),"cases":cases},indent=2))
    rows=[];markrows=[]
    for case in cases:
        assert hashlib.sha256(Path(case["path"]).read_bytes()).hexdigest()==case["sha256"]
        for mode in MODES:
            status,seconds,marks=run(args.solver,case,mode)
            rows.append({"seed":case["seed"],"nvars":case["nvars"],
                         "mean_core":round(case["mean_core_corrected"],4),
                         "mode":mode,"status":status,"seconds":seconds,
                         "checkpoints":len(marks)})
            for a in marks:
                markrows.append({"seed":case["seed"],"mode":mode,**a})
            print("V174_RESULT",case["seed"],mode,status,seconds,
                  json.dumps(marks,separators=(",",":")),flush=True)
        print("V174_PAIR_COMPLETE",case["seed"],flush=True)
    def csvout(file,lines):
        with (args.root/file).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(lines[0]))
            w.writeheader();w.writerows(lines)
    csvout("outcomes.csv",rows)
    csvout("checkpoints.csv",markrows)
    assert len(rows)==len(SEEDS)*len(MODES)
    groups={}
    for mode in MODES:
        ss=[r for r in rows if r["mode"]==mode]
        par2=sum(r["seconds"] if r["status"]!="TIMEOUT" else CAP*2 for r in ss)/len(ss)
        groups[mode]={"solved":sum(r["status"] in ("SAT","UNSAT") for r in ss),
                      "PAR2":round(par2,6)}
    (args.root/"summary.json").write_text(json.dumps(groups,indent=2))
    print("V174_AUDIT_PASS",len(rows),json.dumps(groups,sort_keys=True),flush=True)

if __name__=="__main__":main()

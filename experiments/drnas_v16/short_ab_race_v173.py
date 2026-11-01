#!/usr/bin/env python3
"""DRNAS V17.3 short A/B successive-halving race.

Development uses 172xxx formulas (NOT blind). Freeze once, then check 173xxx
formulas. Equal per-mode wall cap and paired instance/repeat; never optimize on
holdout. Optimization here means selecting a tested configuration, not a new
mathematical algorithm. Results are per-stage and available via Actions artifacts.
"""
import argparse,csv,hashlib,json,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODES={
 "baseline":(),
 "target2":("--target=2",),
 "restart25":("--restartint=25",),
 "restart50":("--restartint=50",),
 "restart100":("--restartint=100",),
 "satfixed":("--sat",),
}
# Deliberate, small separate cohorts. The first two are developmental.
SEEDS={
 "screen": (172000,172002,172005,172007,172010,172011),
 "refine": (172012,172013,172014,172015,172016),
 "holdout":(173000,173001,173002,173003,173004),
}
CAPS={"screen":1.5,"refine":2.5,"holdout":3.0}
REPEATS={"screen":1,"refine":1,"holdout":2}
CONTROLS=("baseline","restart50")

def case(root,seed,stage):
    base=172000 if stage!="holdout" else 173000
    n=(260,340,420)[(seed-base)%3]
    density=4.26
    path=root/"cnf"/f"{seed}.cnf"
    digest=generate(path,n,density,seed)
    return {"seed":seed,"nvars":n,"density":density,
            "sha256":digest,"path":str(path),**corrected_core(path)}

def call(solver,case,mode,cap):
    path=Path(case["path"])
    started=time.perf_counter()
    try:
        p=subprocess.run([solver,*MODES[mode],"-s",str(path)],
            capture_output=True,text=True,errors="replace",check=False,timeout=cap)
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        output=p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT";output=""
    elapsed=time.perf_counter()-started
    if status=="ERROR":
        raise RuntimeError(f"Unexpected Kissat result {mode}, seed {case['seed']}: {output[-800:]}")
    if status=="SAT" and not valid_model(path,output):
        raise RuntimeError(f"Invalid SAT assignment for seed {case['seed']} mode {mode}")
    return status,round(elapsed,6)

def score(rows,modes,cap):
    out=[]
    for mode in modes:
        a=[r for r in rows if r["mode"]==mode]
        if not a: continue
        par2=[r["seconds"] if r["status"] in ("SAT","UNSAT") else 2*cap for r in a]
        out.append({"mode":mode,"attempts":len(a),
            "solved":sum(r["status"] in ("SAT","UNSAT") for r in a),
            "PAR2_seconds":round(statistics.mean(par2),6),
            "median_wall_seconds":round(statistics.median(r["seconds"] for r in a),6)})
    return sorted(out,key=lambda r:(r["PAR2_seconds"],-r["solved"],r["mode"]))

def csvout(path,rows):
    if not rows:return
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def verify(rows,stage,modes):
    pairs={}
    for r in rows:
        k=(r["seed"],r["repeat"])
        pairs.setdefault(k,{})[r["mode"]]=r
        if r["seconds"]>CAPS[stage]+0.25:
            raise AssertionError(f"Wall cap breached: {r}")
    assert len(pairs)==len(SEEDS[stage])*REPEATS[stage]
    for k,p in pairs.items():
        assert set(p)==set(modes),f"Incomplete paired case {k}"
        answers={r["status"] for r in p.values() if r["status"] in ("SAT","UNSAT")}
        assert len(answers)<=1,f"Solver disagreement: {k}"
    return len(pairs)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--stage",choices=tuple(SEEDS),required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--previous",type=Path)
    a=p.parse_args()
    if a.stage!="screen" and not a.previous:
        p.error("Refine/holdout require a prior frozen decision JSON")
    previous=None
    if a.previous:
        previous=json.loads(a.previous.read_text())
        assert previous["pin"]==PINNED
        expected="screen" if a.stage=="refine" else "refine"
        assert previous["stage"]==expected,"Wrong decision sequence"
    if a.stage=="screen":
        modes=tuple(MODES)
    elif a.stage=="refine":
        # Two best developmental modes plus protected baselines.
        modes=tuple(dict.fromkeys((*CONTROLS,*previous["shortlist"])))
    else:
        # No refitting after the freeze: the entire holdout is confirmatory.
        modes=tuple(dict.fromkeys((*CONTROLS,previous["frozen_best"])))
    cap=CAPS[a.stage]
    a.root.mkdir(parents=True,exist_ok=True)
    prepared=[case(a.root,seed,a.stage) for seed in SEEDS[a.stage]]
    manifest={"stage":a.stage,"kind":"development" if a.stage!="holdout" else "prospective_unseen",
       "pin":PINNED,"cap":cap,"repeats":REPEATS[a.stage],
       "modes":modes,"seeds":SEEDS[a.stage],"input_decision":previous,
       "cases":prepared}
    (a.root/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("V173_STAGE_START",a.stage,"modes",",".join(modes),
          "paired_cases",len(SEEDS[a.stage])*REPEATS[a.stage],
          "cap",cap,"seconds",flush=True)
    rows=[]
    for c in prepared:
        path=Path(c["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"]
        for rep in range(REPEATS[a.stage]):
            # Rotate mode order to counter thermal / CI order bias.
            ordered=modes[rep%len(modes):]+modes[:rep%len(modes)]
            for mode in ordered:
                status,seconds=call(a.solver,c,mode,cap)
                rows.append({"stage":a.stage,"seed":c["seed"],"nvars":c["nvars"],
                    "mean_core_corrected":round(c["mean_core_corrected"],6),
                    "repeat":rep,"mode":mode,"status":status,"seconds":seconds})
                print("V173_MEASURE",a.stage,c["seed"],rep,mode,status,
                      f"{seconds:.5f}s",flush=True)
            # Emit a fresh partial scoreboard after every *complete* paired case.
            leaderboard=score(rows,modes,cap)
            csvout(a.root/"measurements.partial.csv",rows)
            csvout(a.root/"leaderboard.partial.csv",leaderboard)
            print("V173_LIVE_PAIR",a.stage,c["seed"],rep,
                  json.dumps(leaderboard,separators=(",",":")),flush=True)
    n=verify(rows,a.stage,modes)
    board=score(rows,modes,cap)
    csvout(a.root/"measurements.csv",rows)
    csvout(a.root/"leaderboard.csv",board)
    decision={"stage":a.stage,"pin":PINNED,"complete_pairs":n,
              "development_only":a.stage!="holdout",
              "leaderboard":board}
    if a.stage=="screen":
        # Never eliminate the controls; select two other contenders.
        alternatives=[r["mode"] for r in board if r["mode"] not in CONTROLS]
        decision["eliminated"]=[r for r in alternatives[2:]]
        decision["shortlist"]=alternatives[:2]
    elif a.stage=="refine":
        decision["frozen_best"]=board[0]["mode"]
        decision["eliminated"]=[r["mode"] for r in board[1:] if r["mode"] not in CONTROLS]
    else:
        decision["frozen_best"]=previous["frozen_best"]
        decision["holdout_only"]=True
        if "baseline" in modes and previous["frozen_best"] in modes:
            b=next(r for r in board if r["mode"]=="baseline")
            t=next(r for r in board if r["mode"]==previous["frozen_best"])
            decision["PAR2_improvement_vs_baseline_percent"]=round(
                100*(b["PAR2_seconds"]-t["PAR2_seconds"])/b["PAR2_seconds"],3)
    (a.root/"decision.json").write_text(json.dumps(decision,indent=2))
    print("V173_STAGE_PASS",a.stage,json.dumps(decision,sort_keys=True),flush=True)

if __name__=="__main__":main()

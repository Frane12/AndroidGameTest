#!/usr/bin/env python3
"""DRNAS V17.7 pre-registered independent prospective paired benchmark.

20 unseen 177100..177119 random 3SAT formulas x3 repeats x4 modes = 240.
All modes share 2.5s cap, identical CNF SHA, pinned Kissat and hardware.
Compare baseline, restart25, switch2048, and frozen early-conflict predictor.
Never select/update the rule from these results.
"""
import argparse,csv,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS=tuple(range(177100,177120))
MODES=("baseline","fixed25","switch2048","predict")
CAP=2.5
REPEATS=3
EARLY=re.compile(r'^c DRNAS_V177_EARLY ',re.M)
CHOICE=re.compile(r'^c DRNAS_V177_CHOICE action=(0|1024|2048) ',re.M)
SWITCH=re.compile(r'^c DRNAS_V177_SWITCH at=(\d+) before=(\d+) after=(\d+) restart_before=(\d+) restart_after=(\d+)$',re.M)
FINAL=re.compile(r'^c DRNAS_V177_FINAL conflicts=(\d+) restarts=(\d+) learned=(\d+)$',re.M)

def csvout(path,rows):
    if rows:
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)

def run_one(solver,path,mode,rule):
    env=os.environ.copy()
    if mode=="baseline" or mode=="fixed25":
        env.pop("DRNAS_V177_MODE",None)
    else:
        env["DRNAS_V177_MODE"]=mode
        env["DRNAS_V177_RULE_FILE"]=str(rule.resolve())
    flags=["--restartint=25"] if mode=="fixed25" else []
    start=time.perf_counter()
    try:
        p=subprocess.run([solver,*flags,"-s",str(path)],capture_output=True,
            text=True,errors="replace",timeout=CAP,env=env,check=False)
        stdout=p.stdout+"\n"+p.stderr
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
        stdout=a+"\n"+b
    elapsed=round(time.perf_counter()-start,6)
    if status=="ERROR":
        raise RuntimeError(f"kissat error {path.name} {mode}: {stdout[-1400:]}")
    if status=="SAT" and not valid_model(path,stdout):
        raise RuntimeError(f"Incorrect satisfying assignment {path.name} {mode}")
    actions=[int(x) for x in CHOICE.findall(stdout)]
    changes=[tuple(int(y) for y in z) for z in SWITCH.findall(stdout)]
    assert len(actions)<=1 and len(changes)<=1
    if mode=="predict" and (EARLY.search(stdout) is not None):
        assert len(actions)==1,("Early checkpoint without policy choice",path.name)
    if mode in ("baseline","fixed25"):
        assert not actions and not changes
    if mode=="switch2048" and changes:
        assert changes[0][0]>=2048
    if mode=="predict":
        if changes:
            assert actions and actions[0] in (1024,2048)
            assert changes[0][0]>=actions[0]
        else:
            assert not actions or actions[0]==0 or status=="TIMEOUT" or status in ("SAT","UNSAT")
    for change in changes:
        assert change[1]==change[2] and change[3]==1 and change[4]==25
    final=FINAL.findall(stdout)
    return {"status":status,"seconds":elapsed,
        "PAR2":elapsed if status in ("SAT","UNSAT") else 2*CAP,
        "action":actions[0] if actions else 0,"switches":len(changes),
        "conflicts":int(final[-1][0]) if final else "",
        "restarts":int(final[-1][1]) if final else "",
        "early_seen":int(bool(EARLY.search(stdout)))}

def bootstrap_pair_gap(bycase,mode):
    # Bootstrap whole *formulas*, not individual repeated runs, to respect clusters.
    items=[]
    for seed,group in sorted(bycase.items()):
        base=statistics.mean(r["PAR2"] for r in group if r["mode"]=="baseline")
        current=statistics.mean(r["PAR2"] for r in group if r["mode"]==mode)
        items.append(base-current)
    rnd=random.Random(17701)
    n=len(items)
    out=sorted(statistics.mean(items[rnd.randrange(n)] for _ in range(n))
               for _ in range(1000))
    return [round(out[25],6),round(out[974],6)]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--rule",type=Path,required=True)
    p.add_argument("--model",type=Path,required=True)
    p.add_argument("--root",type=Path,default=Path("drnas-v177-holdout"))
    a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=True)
    model=json.loads(a.model.read_text())
    assert model["policy_frozen_before_177_holdout"]
    assert "176000" in model["provenance"]
    assert a.rule.read_text().strip().split()[0] in ("r","d","p","g","l")
    pinned_sha=hashlib.sha256(a.rule.read_bytes()).hexdigest()
    cases=[]
    for seed in SEEDS:
        n=(260,340,420)[(seed-177100)%3]
        path=a.root/"cnf"/f"{seed}.cnf"
        h=generate(path,n,4.26,seed)
        cases.append({"seed":seed,"nvars":n,"path":str(path),
                      "sha256":h,**corrected_core(path)})
    (a.root/"manifest.json").write_text(json.dumps({
        "version":"V17.7","purpose":"independent evaluation",
        "pin":PINNED,"seed_range":[177100,177119],
        "development_seed_range":[176000,176019],
        "rule_sha256":pinned_sha,"frozen_model":model,
        "modes":MODES,"cap_seconds":CAP,"repeats":REPEATS,"cases":cases,
        "selected_without_holdout":True},indent=2))
    rows=[]
    print("V177_HOLDOUT_START",len(cases),REPEATS,len(MODES),
          "planned measurements",len(cases)*REPEATS*len(MODES),flush=True)
    for c in cases:
        path=Path(c["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"]
        for rep in range(REPEATS):
            ordered=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            block=[]
            for mode in ordered:
                x=run_one(a.solver,path,mode,a.rule)
                row={"seed":c["seed"],"nvars":c["nvars"],
                     "mean_core":round(c["mean_core_corrected"],5),
                     "repeat":rep,"mode":mode,**x}
                rows.append(row);block.append(row)
                print("V177_MEASURE",c["seed"],rep,mode,x["status"],
                      f'{x["seconds"]:.5f}s',"chosen",x["action"],
                      "changed",x["switches"],"conflicts",x["conflicts"],flush=True)
            assert len(block)==4
            assert len({x["mode"] for x in block})==4
            answers={x["status"] for x in block if x["status"] in ("SAT","UNSAT")}
            assert len(answers)<=1,"SAT/UNSAT disagreement across strategies"
            print("V177_COMPLETE_PAIR",c["seed"],rep,
               json.dumps({x["mode"]:{"status":x["status"],
                 "seconds":x["seconds"],"PAR2":x["PAR2"],
                 "action":x["action"]} for x in block},separators=(",",":")),
               flush=True)
            csvout(a.root/"measurements.partial.csv",rows)
    assert len(rows)==20*3*4
    bycase={seed:[r for r in rows if r["seed"]==seed] for seed in SEEDS}
    scores=[]
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        base={ (r["seed"],r["repeat"]):r for r in rows if r["mode"]=="baseline"}
        scores.append({"mode":mode,"attempts":len(subset),
             "solved":sum(r["status"] in ("SAT","UNSAT") for r in subset),
             "PAR2":round(statistics.mean(r["PAR2"] for r in subset),6),
             "median_wall":round(statistics.median(r["seconds"] for r in subset),6),
             "rescues":sum(base[(r["seed"],r["repeat"])]["status"]=="TIMEOUT" and
               r["status"] in ("SAT","UNSAT") for r in subset),
             "regressions":sum(base[(r["seed"],r["repeat"])]["status"] in ("SAT","UNSAT") and
               r["status"]=="TIMEOUT" for r in subset),
             "policy_switches":sum(r["switches"] for r in subset),
             "policy_1024":sum(r["action"]==1024 for r in subset),
             "policy_2048":sum(r["action"]==2048 for r in subset),
             "95percent_formula_cluster_bootstrap_delta_PAR2_seconds":
                 bootstrap_pair_gap(bycase,mode)})
    scores.sort(key=lambda s:(s["PAR2"],-s["solved"]))
    csvout(a.root/"measurements.csv",rows)
    csvout(a.root/"leaderboard.csv",scores)
    summary={"pin":PINNED,"rule_sha256":pinned_sha,
      "total_measurements":len(rows),"n_formulas":20,
      "repeats":3,"cap":CAP,"scores":scores,
      "limitations":["One random-3SAT distribution; no general SAT conclusion",
        "20 distinct formulas; repeats are not independent cases",
        "UNSAT results not independently certified",
        "No statistical superiority claim until confidence interval excludes zero",
        "All candidate modes run on identical CNF instances, serialized within a runner"]}
    (a.root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V177_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()

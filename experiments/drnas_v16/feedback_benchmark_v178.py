#!/usr/bin/env python3
"""DRNAS SAT V17.8: live STOP/CONTINUE feedback on Kissat restart interventions.

Deterministic A/B development cohort from prior V17.7 holdout, plus a
prospectively frozen, distinct 178xxx cohort. Frozen V17.7 predictor rule is
read-only. 6 strategies; every formula/mode gets same cap and input SHA.
STOP means reverting restartint only; it NEVER cancels the solver,
forgets learned clauses, or restores its earlier search state.
"""
import argparse,csv,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS={"development":tuple(range(177100,177112)),
       "holdout":tuple(range(178100,178120))}
REPEATS={"development":1,"holdout":2}
MODES=("baseline","fixed25","predict","feedback","switch2048","switch2048-feedback")
CAP=2.5
EARLY=re.compile(r"^c DRNAS_V178_EARLY ",re.M)
CHOICE=re.compile(r"^c DRNAS_V178_CHOICE action=(0|1024|2048) ",re.M)
SWITCH=re.compile(r"^c DRNAS_V178_SWITCH at=(\d+) before=(\d+) after=(\d+) restart_before=(\d+) restart_after=(\d+)$",re.M)
FEEDBACK=re.compile(r"^c DRNAS_V178_FEEDBACK check=(256|512) signal=(CONTINUE|ROLLBACK) votes=([0-3]) pre_p=([\d.]+) post_p=([\d.]+) pre_d=([\d.]+) post_d=([\d.]+) pre_g=([\d.]+) post_g=([\d.]+) learned_before=(\d+) learned_after=(\d+) restart_option=(\d+)$",re.M)
FINAL=re.compile(r"^c DRNAS_V178_FINAL conflicts=(\d+) restarts=(\d+) learned=(\d+) checks=(\d+) rollback=(0|1)$",re.M)

def csvout(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def test(solver,path,mode,rule):
    env=os.environ.copy()
    env.pop("DRNAS_V178_MODE",None)
    if mode not in ("baseline","fixed25"):
        env["DRNAS_V178_MODE"]=mode
        env["DRNAS_V178_RULE_FILE"]=str(rule.resolve())
    flags=["--restartint=25"] if mode=="fixed25" else []
    start=time.perf_counter()
    try:
        p=subprocess.run([solver,*flags,"-s",str(path)],text=True,
            capture_output=True,errors="replace",timeout=CAP,env=env,check=False)
        output=p.stdout+"\n"+p.stderr
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
        output=a+"\n"+b
    wall=time.perf_counter()-start
    if status=="ERROR":
        raise RuntimeError(f"Unexpected solver exit {path}/{mode}: {output[-2000:]}")
    if status=="SAT" and not valid_model(path,output):
        raise RuntimeError(f"Invalid SAT witness {path}/{mode}")
    choices=list(map(int,CHOICE.findall(output)))
    changes=[tuple(map(int,m)) for m in SWITCH.findall(output)]
    checks=FEEDBACK.findall(output)
    final=FINAL.findall(output)
    assert len(choices)<=1 and len(changes)<=1
    assert len(checks)<=2
    assert all(int(x[9])==int(x[10]) for x in checks),"Learned clauses changed on feedback"
    assert all(a[1]==a[2] and a[3]==1 and a[4]==25 for a in changes),"Unsafe in-process switch"
    if mode in ("baseline","fixed25"):
        assert not choices and not changes and not checks
    if mode in ("predict","feedback") and EARLY.search(output):
        assert len(choices)==1,"Missed frozen prediction"
    if mode in ("predict","switch2048"):
        assert not checks,"Unplanned feedback in control"
    if mode in ("feedback","switch2048-feedback"):
        assert all(x[1] in ("CONTINUE","ROLLBACK") for x in checks)
        if any(x[1]=="ROLLBACK" for x in checks):
            assert sum(x[1]=="ROLLBACK" for x in checks)==1
            assert checks[-1][1]=="ROLLBACK"
            assert int(checks[-1][-1])==1,"Rollback must restore restartint=1"
    if mode=="predict" and choices and choices[0]==0:
        assert not changes
    if mode=="feedback" and choices and choices[0]==0:
        assert not changes and not checks
    if status in ("SAT","UNSAT") and mode not in ("baseline","fixed25"):
        assert len(final)==1,"Completed run must expose final telemetry"
    return {"status":status,"wall":round(wall,6),
            "PAR2":round(wall if status in ("SAT","UNSAT") else 2*CAP,6),
            "choice":choices[0] if choices else 0,
            "switches":len(changes),"feedback_checks":len(checks),
            "continues":sum(x[1]=="CONTINUE" for x in checks),
            "rollbacks":sum(x[1]=="ROLLBACK" for x in checks),
            "early_seen":int(bool(EARLY.search(output))),
            "final_conflicts":int(final[0][0]) if final else "",
            "restart_setting_after_feedback":int(checks[-1][-1]) if checks else ""}

def interval_by_formula(byseed,mode):
    diffs=[]
    for seed,cases in sorted(byseed.items()):
        base=statistics.mean(x["PAR2"] for x in cases if x["mode"]=="baseline")
        trial=statistics.mean(x["PAR2"] for x in cases if x["mode"]==mode)
        diffs.append(base-trial)
    rng=random.Random(178001)
    sims=sorted(statistics.mean(diffs[rng.randrange(len(diffs))] for _ in diffs)
                for _ in range(1000))
    return [round(sims[25],6),round(sims[974],6)]

def summarize(rows):
    modes=[]
    byseed={seed:[r for r in rows if r["seed"]==seed] for seed in sorted(set(r["seed"] for r in rows))}
    baseline={(r["seed"],r["rep"]):r for r in rows if r["mode"]=="baseline"}
    for mode in MODES:
        chosen=[r for r in rows if r["mode"]==mode]
        rescues=regressions=slowdowns=0
        for r in chosen:
            b=baseline[(r["seed"],r["rep"])]
            if b["status"]=="TIMEOUT" and r["status"] in ("SAT","UNSAT"):rescues+=1
            if b["status"] in ("SAT","UNSAT") and r["status"]=="TIMEOUT":regressions+=1
            if b["status"] in ("SAT","UNSAT") and r["status"] in ("SAT","UNSAT") and (
                 r["wall"]>1.5*b["wall"] and r["wall"]-b["wall"]>=0.15):
                slowdowns+=1
        modes.append({"mode":mode,"n":len(chosen),
            "solved":sum(r["status"] in ("SAT","UNSAT") for r in chosen),
            "PAR2":round(statistics.mean(r["PAR2"] for r in chosen),6),
            "rescues":rescues,"timeout_regressions":regressions,
            "severe_slowdowns":slowdowns,
            "switches":sum(r["switches"] for r in chosen),
            "feedback_continue":sum(r["continues"] for r in chosen),
            "feedback_rollback":sum(r["rollbacks"] for r in chosen),
            "formula_bootstrap_95pct_delta_PAR2":
               interval_by_formula(byseed,mode)})
    modes.sort(key=lambda x:(x["PAR2"],-x["solved"]))
    return modes

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--rule",type=Path,required=True)
    p.add_argument("--stage",choices=tuple(SEEDS),required=True)
    p.add_argument("--root",type=Path,required=True)
    a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=True)
    fields=a.rule.read_text().split()
    assert len(fields)==4 and fields[0] in "rdpgl" and fields[1] in ("lt","ge")
    assert int(fields[3]) in (0,1024,2048)
    rule_sha=hashlib.sha256(a.rule.read_bytes()).hexdigest()
    seeds=SEEDS[a.stage]
    root=a.root
    cases=[]
    for seed in seeds:
        base=177100 if a.stage=="development" else 178100
        n=(260,340,420)[(seed-base)%3]
        path=root/"cnf"/f"{seed}.cnf"
        digest=generate(path,n,4.26,seed)
        cases.append({"seed":seed,"nvars":n,"sha256":digest,
                      "path":str(path),**corrected_core(path)})
    (root/"manifest.json").write_text(json.dumps({
        "stage":a.stage,"pin":PINNED,"rule_sha256":rule_sha,
        "rule_text":a.rule.read_text().strip(),
        "seeds":seeds,"cases":cases,"modes":MODES,
        "cap_seconds":CAP,"repeats":REPEATS[a.stage],
        "feedback_frozen":["post256", "post512","2-of-3 deterioration",
           "propagations/conflict>1.25x","decisions/conflict>1.25x",
           "fast/slow glue ratio>1.10x"],
        "no_tuning_on_holdout":True,
        "caution":"Rollback restores only restartint option, NOT prior search trajectory."},indent=2))
    rows=[]
    expected=len(seeds)*REPEATS[a.stage]*len(MODES)
    print("V178_PLAN",a.stage,"pairs",len(seeds)*REPEATS[a.stage],
          "attempts",expected,flush=True)
    for c in cases:
        assert hashlib.sha256(Path(c["path"]).read_bytes()).hexdigest()==c["sha256"]
        for rep in range(REPEATS[a.stage]):
            order=MODES[rep:]+MODES[:rep]
            current=[]
            for mode in order:
                x=test(a.solver,Path(c["path"]),mode,a.rule)
                r={"stage":a.stage,"seed":c["seed"],"nvars":c["nvars"],
                    "rep":rep,"mode":mode,**x}
                rows.append(r);current.append(r)
                print("V178_MEASURE",a.stage,c["seed"],rep,mode,x["status"],
                    f'{x["wall"]:.5f}s',"action",x["choice"],
                    "switch",x["switches"],"continue",x["continues"],
                    "rollback",x["rollbacks"],flush=True)
            solved={r["status"] for r in current if r["status"] in ("SAT","UNSAT")}
            assert len(current)==len(MODES) and len(solved)<=1,"Unpaired/incorrect answers"
            csvout(root/"measurements.partial.csv",rows)
            print("V178_COMPLETE_PAIR",c["seed"],rep,
                json.dumps({x["mode"]:{"status":x["status"],"wall":x["wall"],
                   "continue":x["continues"],"rollback":x["rollbacks"]}
                   for x in current},separators=(",",":")),flush=True)
    assert len(rows)==expected
    scores=summarize(rows)
    csvout(root/"measurements.csv",rows)
    csvout(root/"leaderboard.csv",scores)
    summary={"stage":a.stage,"n_measurements":len(rows),
       "n_distinct_formulas":len(cases),"repeats":REPEATS[a.stage],
       "rank":scores,
       "limits":["Only random 3SAT density 4.26, not industrial SAT",
                 "One seed per distinct formula; repeats share formula",
                 "UNSAT not independently proof-certified",
                 "Restoring restartint is not restoring previous solver state",
                 "Early feedback metrics are engineering hypotheses, not causal proof"]}
    (root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V178_AUDIT_PASS",a.stage,json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()

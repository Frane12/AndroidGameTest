#!/usr/bin/env python3
"""DRNAS v17.9: run frozen A/B actions and audit state/action/outcome consistency.

12 entirely new random-3SAT formulas x 2 repeats x 6 modes = 144 measurements.
Exact Kissat build, CNF hashes, frozen V17.7 rule, full raw solver stdout per run.
The V17.8 instrument supports 'observe' without any policy intervention,
so even baseline/fixed25 report an identical early-conflict checkpoint.
Never call different wall time a mathematical contradiction.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,re,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model
from live_guard_v172 import corrected_core
from state_action_ledger_v179 import append_jsonl,audit,canonical,make_record,read_jsonl

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS=tuple(range(179100,179112))
MODES=("baseline","fixed25","predict","feedback","switch2048","switch2048-feedback")
REPEATS=2
CAP=2.5
EARLY=re.compile(r"^c DRNAS_V178_EARLY r=([\d.]+) d=([\d.]+) p=([\d.]+) g=([\d.]+) l=([\d.]+) conflict=(\d+) restarts=(\d+)$",re.M)
CHOICE=re.compile(r"^c DRNAS_V178_CHOICE action=(0|1024|2048) feature=([rdpgl]) value=([\d.]+) op=(lt|ge) threshold=([\d.]+)$",re.M)
SWITCH=re.compile(r"^c DRNAS_V178_SWITCH at=(\d+) before=(\d+) after=(\d+) restart_before=(\d+) restart_after=(\d+)$",re.M)
FEEDBACK=re.compile(r"^c DRNAS_V178_FEEDBACK check=(256|512) signal=(CONTINUE|ROLLBACK) votes=([0-3]) pre_p=([\d.]+) post_p=([\d.]+) pre_d=([\d.]+) post_d=([\d.]+) pre_g=([\d.]+) post_g=([\d.]+) learned_before=(\d+) learned_after=(\d+) restart_option=(\d+)$",re.M)
FINAL=re.compile(r"^c DRNAS_V178_FINAL conflicts=(\d+) restarts=(\d+) learned=(\d+) checks=(\d+) rollback=(0|1)$",re.M)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def csvout(path,rows):
    if rows:
        with Path(path).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader();w.writerows(rows)

def execute(solver,case,mode,rep,rule,root,environment):
    env=os.environ.copy()
    env["DRNAS_V178_MODE"]="observe" if mode in ("baseline","fixed25") else mode
    env["DRNAS_V178_RULE_FILE"]=str(rule.resolve())
    command=[str(solver.resolve())]
    if mode=="fixed25":command.append("--restartint=25")
    command+=["-s",str(Path(case["path"]).resolve())]
    start=time.perf_counter()
    try:
        p=subprocess.run(command,env=env,check=False,capture_output=True,
                         text=True,errors="replace",timeout=CAP)
        raw=p.stdout+"\n"+p.stderr
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else (e.stderr or "")
        raw=a+"\n"+b
    seconds=round(time.perf_counter()-start,6)
    if status=="ERROR":raise RuntimeError(f"Unexpected solver result {case['seed']}/{mode}: {raw[-1600:]}")
    verified=status=="SAT" and valid_model(Path(case["path"]),raw)
    if status=="SAT" and not verified:raise RuntimeError(f"Incorrect SAT witness {case['seed']}/{mode}")
    logfile=root/"raw_logs"/f"{case['seed']}_r{rep}_{mode}.log"
    logfile.parent.mkdir(parents=True,exist_ok=True)
    logfile.write_text(raw,encoding="utf8")
    early=[]
    for m in EARLY.finditer(raw):
        g=m.groups()
        early.append({"restarts_per_conflict":float(g[0]),
          "decisions_per_conflict":float(g[1]),
          "propagations_per_conflict":float(g[2]),
          "fast_over_slow_glue":float(g[3]),
          "learned_per_conflict":float(g[4]),
          "conflicts":int(g[5]),"restarts":int(g[6])})
    choices=[{"action":int(m[0]),"feature":m[1],"feature_value":float(m[2]),
              "operator":m[3],"threshold":float(m[4])} for m in CHOICE.findall(raw)]
    switches=[{"conflicts":int(a),"learned_before":int(b),
       "learned_after":int(c),"restart_before":int(d),
       "restart_after":int(e)} for a,b,c,d,e in SWITCH.findall(raw)]
    feedback=[]
    for m in FEEDBACK.findall(raw):
        feedback.append({"checkpoint_after_switch":int(m[0]),
          "signal":m[1],"deterioration_votes":int(m[2]),
          "pre_propagations":float(m[3]),"post_propagations":float(m[4]),
          "pre_decisions":float(m[5]),"post_decisions":float(m[6]),
          "pre_glue":float(m[7]),"post_glue":float(m[8]),
          "learned_before":int(m[9]),"learned_after":int(m[10]),
          "restart_after":int(m[11])})
    finals=[{"conflicts":int(m[0]),"restarts":int(m[1]),
      "learned":int(m[2]),"checks":int(m[3]),
      "rolled_back":bool(int(m[4]))} for m in FINAL.findall(raw)]
    assert len(early)<=1 and len(choices)<=1 and len(switches)<=1 and len(finals)<=1
    if mode in ("baseline","fixed25"):assert not choices and not switches and not feedback
    if mode in ("predict","feedback") and early:assert len(choices)==1
    if mode in ("predict","switch2048"):assert not feedback
    for x in switches:
        assert x["learned_before"]==x["learned_after"]
        assert x["restart_before"]==1 and x["restart_after"]==25
    for x in feedback:assert x["learned_before"]==x["learned_after"]
    if any(f["signal"]=="ROLLBACK" for f in feedback):
        assert feedback[-1]["signal"]=="ROLLBACK" and feedback[-1]["restart_after"]==1
    if status!="TIMEOUT":assert len(finals)==1
    if mode in ("feedback","switch2048-feedback"):assert len(feedback)<=2
    observation={"checkpoint_conflict512":early[0] if early else None,
       "choice":choices,"interventions":switches,
       "final":finals[0] if finals else None}
    action={"mode":mode,
       "initial_restartint":25 if mode=="fixed25" else 1,
       "optional_target":2048 if mode.startswith("switch2048") else None,
       "frozen_predictor_sha256":digest(rule),
       "feedback_logic":"2-of-3 post256/post512, revert restartint only"
                        if mode.endswith("feedback") or mode=="feedback" else "none"}
    result={"status":status,"seconds":seconds,
       "PAR2":seconds if status in ("SAT","UNSAT") else 2*CAP,
       "witness_verified":verified,"proof_verified":False,
       "final_conflicts":finals[0]["conflicts"] if finals else None,
       "final_restarts":finals[0]["restarts"] if finals else None,
       "stdout_sha256":digest(logfile),
       "stdout_path":str(logfile.relative_to(root))}
    rec=make_record(
      run={"seed":case["seed"],"repeat":rep,"mode":mode},
      case={"seed":case["seed"],"cnf_sha256":case["sha256"],
            "nvars":case["nvars"],"density":4.26},
      environment=environment,action=action,observation=observation,
      feedback=feedback,outcome=result,
      extensions={"telemetry.v178":{"checkpoints":len(early),
        "changes":len(switches),"feedback_events":len(feedback),
        "rollbacks":sum(f["signal"]=="ROLLBACK" for f in feedback)}},
      hypothesis={"prediction":"Equivalent complete solver state and deterministic action imply the same logical result",
        "falsified_when":"Identical CNF yields validated SAT and independently certified UNSAT; compare complete states before asserting logical inconsistency"})
    return rec,{"seed":case["seed"],"repeat":rep,"mode":mode,
        "status":status,"seconds":seconds,"PAR2":result["PAR2"],
        "action":choices[0]["action"] if choices else 0,
        "interventions":len(switches),"continues":sum(f["signal"]=="CONTINUE" for f in feedback),
        "rollbacks":sum(f["signal"]=="ROLLBACK" for f in feedback),
        "final_conflicts":result["final_conflicts"] if result["final_conflicts"] is not None else ""}

def paired_audit(rows):
    by={(x["seed"],x["repeat"],x["mode"]):x for x in rows}
    differences=[]
    for seed in SEEDS:
        for rep in range(REPEATS):
            baseline=by[(seed,rep,"baseline")]
            for mode in MODES[1:]:
                row=by[(seed,rep,mode)]
                result={"seed":seed,"rep":rep,"mode":mode,
                        "base_s":baseline["seconds"],"candidate_s":row["seconds"]}
                if baseline["status"] in ("SAT","UNSAT") and row["status"]=="TIMEOUT":
                    result["kind"]="solved_to_timeout"
                elif baseline["status"]=="TIMEOUT" and row["status"] in ("SAT","UNSAT"):
                    result["kind"]="timeout_to_solved"
                elif baseline["status"] in ("SAT","UNSAT") and row["status"] in ("SAT","UNSAT") and \
                     row["seconds"]>=baseline["seconds"]*1.5 and \
                     row["seconds"]-baseline["seconds"]>=.15:
                    result["kind"]="severe_slowdown"
                else:continue
                differences.append(result)
    return differences

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",type=Path,required=True)
    p.add_argument("--rule",type=Path,required=True)
    p.add_argument("--root",type=Path,default=Path("drnas-v179-results"))
    a=p.parse_args()
    root=a.root;root.mkdir(parents=True,exist_ok=True)
    assert a.rule.read_text().strip()=="g lt 0.8692513215 1024", "Do not refit rule on new cases"
    environment={
        "solver_sha256":digest(a.solver),
        "upstream_commit":PINNED,"solver_version":"kissat-4.0.4-instrumented-v178",
        "host_os":platform.platform(),
        "machine":platform.machine(),"python":platform.python_version(),
        "cap_seconds":CAP,"rules_sha256":digest(a.rule),
        "job_sha":os.environ.get("GITHUB_SHA","local")}
    cases=[]
    for seed in SEEDS:
        n=(260,340,420)[(seed-SEEDS[0])%3]
        cnf=root/"cnf"/f"{seed}.cnf"
        digest_from_generator=generate(cnf,n,4.26,seed)
        assert digest(cnf)==digest_from_generator
        cases.append({"seed":seed,"nvars":n,"sha256":digest(cnf),
            "path":str(cnf),**corrected_core(cnf)})
    (root/"manifest.json").write_text(json.dumps({
        "version":"V17.9","protocol":"versioned state-action-outcome ledger",
        "hypothesis_status":"exploratory","fixed_12_new_seeds":SEEDS,
        "modes":MODES,"repeats":REPEATS,"cap_seconds":CAP,
        "environment":environment,"cases":cases,
        "expected_trials":len(cases)*REPEATS*len(MODES),
        "interpretation":"Match observed states, not presumed complete internal solver state."},indent=2))
    ledger=root/"state_action_events.jsonl"
    ledger.write_text("")
    rows=[]
    for case in cases:
        for rep in range(REPEATS):
            modes=MODES[rep:]+MODES[:rep]
            for mode in modes:
                rec,row=execute(a.solver,case,mode,rep,a.rule,root,environment)
                append_jsonl(ledger,rec);rows.append(row)
                print("V179_MEASURE",case["seed"],rep,mode,row["status"],
                      f'{row["seconds"]:.5f}s',"conflicts",row["final_conflicts"],
                      "feedback_continue",row["continues"],"feedback_rollback",row["rollbacks"],flush=True)
            csvout(root/"measurements.partial.csv",rows)
            print("V179_PAIRED_COMPLETE",case["seed"],rep,flush=True)
    assert len(rows)==12*2*6
    observed=audit(read_jsonl(ledger))
    paired=paired_audit(rows)
    rank=[]
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        rank.append({"mode":mode,"n":len(rr),
            "solved":sum(r["status"] in ("SAT","UNSAT") for r in rr),
            "PAR2":round(statistics.mean(r["PAR2"] for r in rr),6),
            "rollbacks":sum(r["rollbacks"] for r in rr),
            "severe_slowdowns":sum(x["mode"]==mode and x["kind"]=="severe_slowdown" for x in paired),
            "solved_to_timeout":sum(x["mode"]==mode and x["kind"]=="solved_to_timeout" for x in paired)})
    rank.sort(key=lambda x:(x["PAR2"],-x["solved"]))
    summary={"version":"V17.9","observed_reproducibility":observed,
             "paired_intervention_findings":paired,"ranking":rank,
             "limitations":["12 distinct synthetic 3SAT formulas; repeats are not independent",
                "TIMEOUT is inconclusive, not UNSAT",
                "UNSAT is not independently proof certified",
                "Observed checkpoint is not complete solver state",
                "Interventions create divergent search paths; restartint rollback does not undo state",
                "Wall time measurements include OS scheduling jitter"]}
    (root/"consistency_audit.json").write_text(json.dumps(summary,indent=2))
    csvout(root/"measurements.csv",rows)
    csvout(root/"ranking.csv",rank)
    print("V179_AUDIT_PASS",json.dumps({"measurements":len(rows),
       "ranking":rank,"replay_issues":observed["findings_by_kind"],
       "paired_issues":len(paired)},sort_keys=True),flush=True)

if __name__=="__main__":main()

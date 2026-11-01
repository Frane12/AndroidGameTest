#!/usr/bin/env python3
"""Shared V18.0 blind paired SAT protocol; exact 512-conflict pre-action features."""
from __future__ import annotations
import csv,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
from shock_filter_v171 import generate,valid_model

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP=2.5
BASE_MODES=("baseline","switch1024","switch2048")
ALL_MODES=BASE_MODES+("riskgate",)
FIELDS=("r","d","p","g","l")
EARLY=re.compile(r"^c DRNAS_V178_EARLY r=([\d.]+) d=([\d.]+) p=([\d.]+) g=([\d.]+) l=([\d.]+) conflict=(\d+) restarts=(\d+)$",re.M)
GUARD=re.compile(r"^c DRNAS_V180_GUARD action=(0|1024|2048) feature=([rdpgl]) value=([\d.]+) op=(lt|ge) threshold=([\d.]+) decision=(SWITCH|SKIP)$",re.M)
SWITCH=re.compile(r"^c DRNAS_V178_SWITCH at=(\d+) before=(\d+) after=(\d+) restart_before=(\d+) restart_after=(\d+)$",re.M)
FINAL=re.compile(r"^c DRNAS_V178_FINAL conflicts=(\d+) restarts=(\d+) learned=(\d+) checks=(\d+) rollback=(0|1)$",re.M)

def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def write_csv(path,rows):
    if rows:
        with Path(path).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

def fresh_case(root,seed,base):
    n=(260,340,420)[(seed-base)%3]
    path=Path(root)/"cnf"/f"{seed}.cnf"
    path.parent.mkdir(parents=True,exist_ok=True)
    h=generate(path,n,4.26,seed)
    assert sha_file(path)==h
    return {"seed":seed,"nvars":n,"density":4.26,"path":str(path),
            "sha256":h}

def execute(solver,case,mode,rep,root,rule_file=None):
    assert mode in ALL_MODES
    env=os.environ.copy()
    env["DRNAS_V178_MODE"]="observe" if mode=="baseline" else mode
    if mode=="riskgate":
        assert rule_file is not None and Path(rule_file).is_file()
        env["DRNAS_V180_RULE_FILE"]=str(Path(rule_file).resolve())
    start=time.perf_counter()
    try:
        proc=subprocess.run([str(Path(solver).resolve()),"-s",
                  str(Path(case["path"]).resolve())],
                  text=True,errors="replace",capture_output=True,
                  timeout=CAP,check=False,env=env)
        output=proc.stdout+"\n"+proc.stderr
        status={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else (e.stderr or "")
        output=a+"\n"+b
    elapsed=round(time.perf_counter()-start,6)
    if status=="ERROR":
        raise RuntimeError(f"Solver failed seed={case['seed']} mode={mode} output={output[-1500:]}")
    if status=="SAT" and not valid_model(Path(case["path"]),output):
        raise RuntimeError(f"Invalid SAT witness {case['seed']}/{mode}")
    raw=Path(root)/"raw"/f'{case["seed"]}-r{rep}-{mode}.log'
    raw.parent.mkdir(parents=True,exist_ok=True)
    raw.write_text(output,encoding="utf8")
    early=EARLY.findall(output)
    gates=GUARD.findall(output)
    switches=SWITCH.findall(output)
    final=FINAL.findall(output)
    assert len(early)<=1 and len(gates)<=1 and len(switches)<=1 and len(final)<=1
    if status in ("SAT","UNSAT"):
        assert len(final)==1,"Solver completed but did not report final counters"
    if mode=="baseline":assert not gates and not switches
    if mode=="riskgate":
        assert len(gates)==len(early),"Risk rule must be evaluated on checkpoint"
        if gates and gates[0][0]=="0":assert not switches
        if switches:
            assert gates and int(gates[0][0]) in (1024,2048)
            assert int(switches[0][0])>=int(gates[0][0])
    else:assert not gates
    for s in switches:
        assert s[1]==s[2] and s[3]=="1" and s[4]=="25", "Learned clause or restart option invariant failed"
    feats=dict(zip(FIELDS,map(float,early[0][:5]))) if early else None
    action=int(gates[0][0]) if gates else 0
    return {"seed":case["seed"],"rep":rep,"mode":mode,"status":status,
      "wall":elapsed,"par2":elapsed if status in ("SAT","UNSAT") else 2*CAP,
      "early":int(feats is not None),"features":feats,
      "action":action,"switched":int(bool(switches)),
      "final_conflicts":int(final[0][0]) if final else None,
      "final_restarts":int(final[0][1]) if final else None,
      "raw_sha256":sha_file(raw),"raw_file":str(raw.relative_to(root))}

def is_bad(baseline,candidate):
    return ((baseline["status"] in ("SAT","UNSAT") and candidate["status"]=="TIMEOUT") or
         (baseline["status"] in ("SAT","UNSAT") and candidate["status"] in ("SAT","UNSAT")
          and candidate["wall"]-baseline["wall"]>=0.15
          and candidate["wall"]>=1.5*baseline["wall"]))

def is_good(baseline,candidate):
    return ((baseline["status"]=="TIMEOUT" and candidate["status"] in ("SAT","UNSAT")) or
         (baseline["status"] in ("SAT","UNSAT") and candidate["status"] in ("SAT","UNSAT")
          and baseline["wall"]-candidate["wall"]>=0.10
          and candidate["wall"]<=0.75*baseline["wall"]))

def rank(rows):
    names=sorted({r["mode"] for r in rows})
    base={(r["seed"],r["rep"]):r for r in rows if r["mode"]=="baseline"}
    ranked=[]
    for mode in names:
        rr=[r for r in rows if r["mode"]==mode]
        ranked.append({"mode":mode,"attempts":len(rr),
             "solved":sum(r["status"] in ("SAT","UNSAT") for r in rr),
             "PAR2":round(statistics.mean(r["par2"] for r in rr),6),
             "severe_regressions":sum(is_bad(base[(r["seed"],r["rep"])],r) for r in rr),
             "useful_interventions":sum(is_good(base[(r["seed"],r["rep"])],r) for r in rr),
             "switched":sum(r["switched"] for r in rr),
             "skipped":sum(r["mode"]=="riskgate" and r["early"] and not r["action"] for r in rr)})
    return sorted(ranked,key=lambda x:(x["PAR2"],-x["solved"]))

def bootstrap_cluster(rows,target):
    by={}
    for row in rows:
        by.setdefault(row["seed"],{})[(row["rep"],row["mode"])]=row
    differences=[]
    for seed,v in sorted(by.items()):
        reps={k[0] for k in v}
        diffs=[v[(rep,"baseline")]["par2"]-v[(rep,target)]["par2"] for rep in reps]
        differences.append(statistics.mean(diffs))
    rnd=random.Random(180018)
    n=len(differences)
    sims=sorted(statistics.mean(differences[rnd.randrange(n)] for _ in range(n))
         for _ in range(1000))
    return [round(sims[25],6),round(sims[974],6)]

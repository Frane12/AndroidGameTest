#!/usr/bin/env python3
"""V17.2: frozen 172xxx prospective live conflict guard, paired 6s trials.

Upstream Kissat 4.0.4, one persistent search, early samples at 1024/4096
conflicts, online change of focused restart interval only after TWO
deterioration signals. Features are observational; no test-set optimization.
"""
import argparse,csv,hashlib,json,os,re,statistics,subprocess,time,heapq
from collections import defaultdict
from pathlib import Path
from shock_filter_v171 import generate,parse_dimacs,valid_model

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP=6.0
REPEATS=2
HOLDOUT=tuple(range(172000,172030))
CONTROLS=tuple(range(172030,172036))
MODES=("baseline","target-only","restart-only","live-observe","live-adapt")
FLAGS={"baseline":(),"target-only":("--target=2",),
       "restart-only":("--restartint=50",),"live-observe":(),"live-adapt":()}
LIVE=re.compile(
    r"^c DRNAS_LIVE seen=(\d+) early_prop=([\d.]+) late_prop=([\d.]+) "
    r"early_dec=([\d.]+) late_dec=([\d.]+) stagnant=([01]) changed=([01]) "
    r"restart_before=(\d+) restart_after=(\d+) learned_before=(\d+) learned_after=(\d+)$",re.M)

def corrected_core(path):
    """Correct k-core numbers: nondecreasing degeneracy during min-degree peeling."""
    n,clauses=parse_dimacs(path)
    adj=[set() for _ in range(n+1)]
    for clause in clauses:
        vs=set(map(abs,clause))
        for v in vs: adj[v].update(vs-{v})
    deg=[len(adj[v]) for v in range(n+1)]
    queue=[(deg[v],v) for v in range(1,n+1)]
    heapq.heapify(queue)
    removed=set()
    cores=[0]*(n+1)
    current=0
    while queue:
        d,v=heapq.heappop(queue)
        if v in removed or deg[v]!=d: continue
        removed.add(v)
        current=max(current,d)
        cores[v]=current
        for w in adj[v]:
            if w not in removed and deg[w]>d:
                deg[w]-=1
                heapq.heappush(queue,(deg[w],w))
    assert len(removed)==n
    return {"nvars":n,"nclauses":len(clauses),
            "mean_core_corrected":statistics.mean(cores[1:]),
            "max_core_corrected":max(cores[1:])}

def cases(root):
    out=[]
    for index,seed in enumerate(HOLDOUT+CONTROLS):
        group="holdout" if seed in HOLDOUT else "control"
        n=(260,340,420)[index%3]
        density=4.26 if group=="holdout" else (3.8 if seed<172033 else 4.7)
        path=root/"cnf"/group/f"{seed}.cnf"
        sha=generate(path,n,density,seed)
        out.append({"seed":seed,"group":group,"density":density,"path":str(path),
                    "sha256":sha,**corrected_core(path)})
    return out

def telemetry(output,mode,group):
    matches=list(LIVE.finditer(output))
    assert len(matches)<=1, "duplicate live check"
    if mode in ("baseline","target-only","restart-only"):
        assert not matches, "fixed mode unexpectedly instrumented"
    empty=dict(checkpoint=0,changed=0,stagnant=0,
               early_prop="",late_prop="",early_dec="",late_dec="")
    if not matches: return empty
    seen,p0,p1,d0,d1,stall,change,before,after,old,new=matches[0].groups()
    assert int(seen)>=4096 and int(old)==int(new), "lost learned-clause counter"
    assert not int(change) or (mode=="live-adapt" and group=="holdout"
                                and int(stall)==1 and int(after)==50
                                and int(before)!=int(after)), "invalid switch"
    if mode=="live-observe" or group=="control": assert change=="0"
    return dict(checkpoint=int(seen),changed=int(change),stagnant=int(stall),
                early_prop=float(p0),late_prop=float(p1),
                early_dec=float(d0),late_dec=float(d1))

def attempt(solver,case,mode):
    env=os.environ.copy()
    env.pop("DRNAS_LIVE_MODE",None)
    if mode.startswith("live-"):
        env["DRNAS_LIVE_MODE"]=("adapt" if mode=="live-adapt"
                                and case["group"]=="holdout" else "observe")
    start=time.perf_counter()
    path=Path(case["path"])
    try:
        result=subprocess.run([solver,*FLAGS[mode],"-s",str(path)],
            capture_output=True,text=True,errors="replace",env=env,
            check=False,timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(result.returncode,"ERROR")
        output=result.stdout+"\n"+result.stderr
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        a=e.stdout.decode("utf8","replace") if isinstance(e.stdout,bytes) else e.stdout or ""
        b=e.stderr.decode("utf8","replace") if isinstance(e.stderr,bytes) else e.stderr or ""
        output=a+"\n"+b
    elapsed=round(time.perf_counter()-start,6)
    if status=="ERROR":
        raise RuntimeError(f"Unexpected solver code on {mode} {case['seed']}: {output[-1400:]}")
    if status=="SAT" and not valid_model(path,output):
        raise RuntimeError(f"SAT witness rejected on {case['seed']}")
    return {"status":status,"total_seconds":elapsed,**telemetry(output,mode,case["group"])}

def csvout(path,rows):
    if not rows: return
    with path.open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def par2(row):
    return row["total_seconds"] if row["status"] in ("SAT","UNSAT") else 12.0

def audit(rows,prepared):
    assert len(rows)==36*2*len(MODES),"incomplete trials"
    assert len(prepared)==36 and len({p["sha256"] for p in prepared})==36
    paired=defaultdict(dict)
    for row in rows:
        assert row["status"] in ("SAT","UNSAT","TIMEOUT")
        assert row["total_seconds"]<=CAP+.25
        if row["group"]=="control" or row["mode"]!="live-adapt":
            assert row["changed"]==0
        paired[(row["seed"],row["repeat"])][row["mode"]]=row
    assert len(paired)==72 and all(set(p)==set(MODES) for p in paired.values())
    for p in paired.values():
        answers={x["status"] for x in p.values() if x["status"] in ("SAT","UNSAT")}
        assert len(answers)<=1,"SAT/UNSAT disagreement"
    return len(paired)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--solver",required=True)
    parser.add_argument("--root",type=Path,default=Path("drnas-v172-results"))
    parser.add_argument("--timeout",type=float,default=CAP)
    parser.add_argument("--repeats",type=int,default=REPEATS)
    a=parser.parse_args()
    if a.timeout!=CAP or a.repeats!=REPEATS:
        parser.error("frozen limits: timeout 6; repeats 2")
    a.root.mkdir(parents=True,exist_ok=True)
    prepared=cases(a.root)
    manifest={"protocol":"DRNAS V17.2 frozen prospective live guard",
       "pin":PINNED,"budget_seconds":CAP,"repeats":REPEATS,
       "holdout":[HOLDOUT[0],HOLDOUT[-1]],"density_controls":[CONTROLS[0],CONTROLS[-1]],
       "checkpoint_conflicts":[1024,4096],"min_prop_decrease":0.25,
       "min_decisions_increase":0.05,"modes":list(MODES),
       "no_holdout_tuning":True,"cases":prepared}
    (a.root/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("V172_PROTOCOL_FROZEN_BEFORE_TESTS",len(prepared),"CNFs",flush=True)
    rows=[]
    for case in prepared:
        path=Path(case["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==case["sha256"]
        for rep in range(REPEATS):
            order=MODES[rep:]+MODES[:rep]
            for mode in order:
                details=attempt(a.solver,case,mode)
                row={key:case[key] for key in
                     ("group","seed","nvars","density","mean_core_corrected","max_core_corrected")}
                row.update({"repeat":rep,"mode":mode,**details})
                rows.append(row)
                print("V172_MEASURE",case["group"],case["seed"],rep,mode,
                      details["status"],f'{details["total_seconds"]:.5f}s',
                      "checkpoint",details["checkpoint"],"switch",details["changed"],
                      "prop",details["early_prop"],details["late_prop"],flush=True)
            csvout(a.root/"measurements.partial.csv",rows)
    complete=audit(rows,prepared)
    csvout(a.root/"measurements.csv",rows)
    summary={"pin":PINNED,"cap_seconds":CAP,"repeats":REPEATS,"groups":{},
             "limitations":["Only synthetic random-3SAT, no general SAT claim",
               "UNSAT has no independently checked proof certificate",
               "Selection policy frozen before new 172xxx CNFs",
               "All times wall-clock, all strategies share six-second budget"]}
    for group in ("holdout","control"):
        summary["groups"][group]={}
        for mode in MODES:
            subset=[r for r in rows if r["group"]==group and r["mode"]==mode]
            summary["groups"][group][mode]={
                "attempts":len(subset),
                "solved":sum(r["status"] in ("SAT","UNSAT") for r in subset),
                "PAR2_seconds":round(statistics.mean(map(par2,subset)),6),
                "median_seconds":round(statistics.median(r["total_seconds"] for r in subset),6),
                "checkpoints":sum(r["checkpoint"]>0 for r in subset),
                "switches":sum(r["changed"] for r in subset)}
    (a.root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V172_SUMMARY",json.dumps(summary,sort_keys=True),flush=True)
    print("V172_AUDIT_PASS",len(rows),"measurements",complete,"paired trials",flush=True)

if __name__=="__main__": main()

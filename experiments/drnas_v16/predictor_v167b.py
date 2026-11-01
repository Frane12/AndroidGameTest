#!/usr/bin/env python3
"""DRNAS V16.7b: frozen, conservative early-CDCL diagnostic policy.

Research experiment, NOT proof of general SAT acceleration. The early
probes are separate Kissat invocations, so their elapsed wall time counts
against the full 6-second budget. All policy constants were frozen before
prospective seeds 167800..167829 were benchmarked.

Selection uses only original CNF and statistics of 64/256 conflict probes.
Never inspect filenames, seed, expected answer or full solve times.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time,re
from pathlib import Path
from generate_v165_blind import make_cnf
from relations_v166b import features

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS=tuple(range(167800,167830))
MODES=("baseline","sat-fixed","adaptive")
BUDGET=6.0

def run(solver,flags,path,timeout):
    start=time.perf_counter()
    try:
        p=subprocess.run([solver,*flags,str(path)],capture_output=True,text=True,
                         timeout=max(.001,timeout),check=False)
        result={0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        out=p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired as e:
        result="TIMEOUT"
        out=(e.stdout.decode("utf-8","replace") if isinstance(e.stdout,bytes) else (e.stdout or ""))
        out+="\n"+(e.stderr.decode("utf-8","replace") if isinstance(e.stderr,bytes) else (e.stderr or ""))
    elapsed=time.perf_counter()-start
    stats={}
    for k in ("conflicts","decisions","propagations","restarts"):
        match=re.search(r"(?m)^c\s+"+k+r"\s*:?\s+([0-9][0-9,]*)\b",out)
        stats[k]=int(match.group(1).replace(",","")) if match else None
    return result,elapsed,stats,out

def witness_ok(path,out):
    a={}
    for line in out.splitlines():
        if line.startswith("v "):
            for tok in line.split()[1:]:
                lit=int(tok)
                if not lit:continue
                if abs(lit) in a and a[abs(lit)]!=(lit>0):return False
                a[abs(lit)]=lit>0
    n=None;pending=[];count=0
    with path.open() as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                n=int(line.split()[2]);continue
            for tok in line.split():
                lit=int(tok)
                if lit:pending.append(lit)
                else:
                    count+=1
                    if not any(a.get(abs(x))==(x>0) for x in pending):return False
                    pending=[]
    return bool(n and count and len(a)==n and not pending)

def select(probes,static):
    # Exploratory frozen mechanistic hypothesis:
    # a SAT profile that increases propagations per decision while reducing
    # decision count may be advantageous; avoid marginal signals.
    if static["density"]<4.1 or static["density"]>4.42:
        return ()
    if static["nvars"]<260 or static["three_fraction"]<.995:
        return ()
    if any(r["status"] not in ("UNKNOWN","SAT","UNSAT") for r in probes.values()):
        return ()
    b=probes["baseline"];s=probes["sat"]
    for v in (b,s):
        if not v["stats"]["decisions"] or not v["stats"]["propagations"]:
            return ()
    eff_b=b["stats"]["propagations"]/b["stats"]["decisions"]
    eff_s=s["stats"]["propagations"]/s["stats"]["decisions"]
    decision_ratio=s["stats"]["decisions"]/b["stats"]["decisions"]
    return ("--sat",) if eff_s/eff_b>=1.20 and decision_ratio<=.90 else ()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--root",type=Path,default=Path("v167b-results"))
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--timeout",type=float,default=BUDGET)
    a=p.parse_args()
    assert a.repeats==2 and a.timeout>1
    a.root.mkdir(parents=True,exist_ok=True)
    inputs=a.root/"cnf";inputs.mkdir(exist_ok=True)
    manifest=[]
    for i,seed in enumerate(SEEDS):
        n=(260,340,420)[i%3]
        path=inputs/f"random3_n{n}_seed{seed}.cnf"
        make_cnf(path,n,4.26,seed)
        manifest.append({"seed":seed,"n":n,"path":str(path),
                         "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    (a.root/"manifest.json").write_text(json.dumps({"pin":PIN,"seeds":manifest,
        "frozen":"No threshold changes after test"},indent=2))
    print("V167B_FROZEN",len(manifest),"independent CNFs",flush=True)
    rows=[]
    for item in manifest:
        path=Path(item["path"]);static=features(path)
        for rep in range(a.repeats):
            order=MODES[rep:]+MODES[:rep]
            for mode in order:
                probe_sec=0.
                flags=() if mode=="baseline" else ("--sat",)
                evidence={}
                if mode=="adaptive":
                    for profile,probe_flags in (("baseline",()),("sat",("--sat",))):
                        result,sec,stats,_=run(a.solver,(*probe_flags,"--conflicts=256","-s"),path,1.)
                        probe_sec+=sec
                        evidence[profile]={"status":result,"stats":stats}
                    flags=select(evidence,static)
                available=max(.001,a.timeout-probe_sec)
                status,solve_sec,_,out=run(a.solver,flags,path,available)
                if status=="SAT" and not witness_ok(path,out):
                    raise ValueError(f"invalid witness {item['seed']} {mode}")
                if status=="ERROR":raise RuntimeError(f"solver error {item['seed']} {mode}")
                elapsed=probe_sec+solve_sec
                row={"seed":item["seed"],"nvars":item["n"],"rep":rep,"mode":mode,
                     "selected":" ".join(flags) or "default",
                     "status":status,"probe_s":round(probe_sec,6),
                     "solve_s":round(solve_sec,6),"total_s":round(elapsed,6),
                     "probe_data":json.dumps(evidence,sort_keys=True)}
                rows.append(row)
                print("V167B_RUN",item["seed"],rep,mode,row["selected"],status,
                      f"{elapsed:.5f}s",flush=True)
    with (a.root/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    scores={}
    for mode in MODES:
        r=[x for x in rows if x["mode"]==mode]
        scores[mode]={"solved":sum(x["status"] in ("SAT","UNSAT") for x in r),
            "attempts":len(r),
            "par2_s":round(statistics.mean(x["total_s"] if x["status"] in ("SAT","UNSAT")
                         else 2*a.timeout for x in r),6),
            "selected_sat":sum(x["selected"]=="--sat" for x in r),
            "probe_overhead_s":round(statistics.mean(x["probe_s"] for x in r),6)}
    pairs={}
    for x in rows:
        key=(x["seed"],x["rep"])
        pairs.setdefault(key,{})[x["mode"]]=x
    assert len(pairs)==len(SEEDS)*a.repeats
    for k,m in pairs.items():
        assert set(m)==set(MODES)
        answers={v["status"] for v in m.values() if v["status"] in ("SAT","UNSAT")}
        assert len(answers)<=1,(k,answers)
    report={"pin":PIN,"policy":"frozen propagations-per-decision ratio >=1.20, decision ratio <=.90",
       "scores":scores,"timeout":a.timeout,"n_formulas":len(SEEDS),
       "limitations":["Probe runs are separate and cannot resume; all overhead counted",
                      "Same synthetic random3 generator, not official SAT Competition",
                      "Early probe statistics are correlational, not causal"]}
    (a.root/"summary.json").write_text(json.dumps(report,indent=2))
    print("V167B_SUMMARY",json.dumps(scores,sort_keys=True),flush=True)
    print("V167B_AUDIT_PASS",len(rows),"runs on",len(SEEDS),"new formulas",flush=True)
if __name__=="__main__":main()

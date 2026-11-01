#!/usr/bin/env python3
"""DRNAS SAT V16.8 — frozen, guarded early-divergence test.

Experiment; thresholds derived from V16.7b DEV results (seeds 167800..167829),
not from prospective 168000..168035. This code neither claims causality nor
claims general-SAT performance. All overhead, including static extraction,
pilot runs, decision and process starts, counts toward the fixed wall budget.

Four modes: upstream default, upstream --sat, frozen V16.7b policy, guarded
V16.8 policy. Thirty new random-3SAT CNFs plus six density controls; exactly
two repeats per mode and SHA256 manifest written before first solver call.
"""
import argparse,csv,hashlib,json,random,re,statistics,subprocess,time
from pathlib import Path
from generate_v165_blind import make_cnf
from relations_v166b import features

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SEEDS=tuple(range(168000,168030))
CONTROL=tuple(range(168030,168036))
MODES=("baseline","sat-fixed","v167b","v168")
CAP=6.0

def parse_stats(out):
    stats={}
    for k in ("conflicts","decisions","propagations","restarts","reductions","search_ticks"):
        m=re.search(r"(?mi)^c\s+"+k+r"\s*:?\s+([0-9][0-9,]*)\b",out)
        stats[k]=int(m.group(1).replace(",","")) if m else None
    return stats

def verified_model(path,out):
    assignment={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for item in line.split()[1:]:
            lit=int(item)
            if not lit:continue
            v=abs(lit);b=lit>0
            if v in assignment and assignment[v]!=b:return False
            assignment[v]=b
    n=None;clauses=0;pending=[]
    with path.open() as source:
        for line in source:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                n=int(line.split()[2]);continue
            for t in line.split():
                lit=int(t)
                if lit:pending.append(lit)
                else:
                    clauses+=1
                    if not pending or not any(assignment.get(abs(x))==(x>0) for x in pending):
                        return False
                    pending=[]
    return n is not None and clauses>0 and len(assignment)==n and not pending

def run(solver,path,flags,timeout):
    start=time.perf_counter()
    try:
        q=subprocess.run([solver,*flags,str(path)],text=True,capture_output=True,
            errors="replace",timeout=max(0.001,timeout),check=False)
        status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(q.returncode,"ERROR")
        out=q.stdout+"\n"+q.stderr
    except subprocess.TimeoutExpired as e:
        status="TIMEOUT"
        out=(e.stdout.decode("utf-8","replace") if isinstance(e.stdout,bytes)
             else (e.stdout or ""))
        out+="\n"+(e.stderr.decode("utf-8","replace") if isinstance(e.stderr,bytes)
                    else (e.stderr or ""))
    elapsed=time.perf_counter()-start
    if status=="SAT" and not verified_model(path,out):
        raise RuntimeError("SAT assignment is incomplete or does not satisfy original CNF")
    if status=="ERROR":raise RuntimeError("unexpected upstream Kissat exit")
    return {"status":status,"seconds":elapsed,"stats":parse_stats(out)}

def valid_static(f):
    return (f["nvars"]>=260 and 4.10<=f["density"]<=4.42 and
            f["three_fraction"]>=.995)

def ratios(b,s):
    db,ds=b.get("decisions"),s.get("decisions")
    pb,ps=b.get("propagations"),s.get("propagations")
    if not (db and ds and pb and ps):return None
    return {
      "decision_ratio":ds/db,
      "propagations_per_decision_ratio":(ps/ds)/(pb/db),
      "baseline_restarts":b.get("restarts"),
      "sat_restarts":s.get("restarts")
    }

def old_policy(f,db,ds):
    if not valid_static(f):return False
    z=ratios(db,ds)
    return bool(z and z["propagations_per_decision_ratio"]>=1.20 and
                z["decision_ratio"]<=.90)

def guard256(f,db,ds):
    if not old_policy(f,db,ds):return False
    z=ratios(db,ds)
    rb,rs=z["baseline_restarts"],z["sat_restarts"]
    # Historical dev failures: harmful 167817 had SAT restarts=4.
    # Beneficial 167801 and 167827 had SAT restarts=2/1.
    return bool(rb is not None and rs is not None and
                rb>=6 and rs<=2 and rb-rs>=4)

def guard1024(db,ds):
    z=ratios(db,ds)
    if not z:return False
    rb,rs=z["baseline_restarts"],z["sat_restarts"]
    return bool(z["propagations_per_decision_ratio"]>=1.05 and
                z["decision_ratio"]<=.95 and rb is not None and
                rs is not None and rs<rb)

def cases(root):
    result=[]
    for i,seed in enumerate(SEEDS+CONTROL):
        n=(260,340,420)[i%3]
        density=4.26 if seed in SEEDS else (3.8 if (seed-168030)<3 else 4.7)
        group="holdout" if seed in SEEDS else "control"
        path=root/"cnf"/group/f"random3_n{n}_density{density}_seed{seed}.cnf"
        path.parent.mkdir(parents=True,exist_ok=True)
        make_cnf(path,n,density,seed)
        result.append({"seed":seed,"nvars":n,"density":density,"group":group,
             "path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(result)==36
    manifest={"kissat_commit":PIN,"frozen_policy":"V16.8 stage-256 guarded restart discrepancy; stage-1024 confirmation",
      "development_seeds":"167800..167829, not scored",
      "prospective_seeds":"168000..168035, untouched",
      "cases":result}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("V168_FROZEN_SHA256",len(result),"CNFs 30 unseen+6 density controls",flush=True)
    return result

def mode_run(solver,path,mode,cap):
    started=time.perf_counter()
    trace=[];selection="default";reason="plain_upstream"
    static=None
    def remaining():return max(.001,cap-(time.perf_counter()-started))
    def probe(profile,budget):
        flags=("--sat",) if profile=="sat" else ()
        q=run(solver,path,(*flags,f"--conflicts={budget}","-s"),
              min(1.0,remaining()))
        trace.append({"profile":profile,"budget":budget,
            "status":q["status"],"seconds":round(q["seconds"],6),"stats":q["stats"]})
        return q
    if mode in ("v167b","v168"):
        static=features(path)
        if mode=="v168" and not valid_static(static):
            reason="out_of_distribution_static_skip"
        elif mode=="v167b":
            b=probe("baseline",256)
            s=probe("sat",256)
            if b["status"] in ("SAT","UNSAT") or s["status"] in ("SAT","UNSAT"):
                # Preserve the original V16.7b semantics: no early return.
                pass
            if old_policy(static,b["stats"],s["stats"]) and all(
                x["status"] in ("UNKNOWN","SAT","UNSAT") for x in (b,s)):
                selection="--sat";reason="old256_positive"
            else:reason="old256_negative"
        else:
            b=probe("baseline",256)
            if b["status"] in ("SAT","UNSAT"):
                return dict(selection="default",reason="baseline_pilot_solved",
                  status=b["status"],total_seconds=time.perf_counter()-started,
                  probe_seconds=sum(x["seconds"] for x in trace),
                  solve_seconds=0.0,trace=trace)
            if b["status"]=="TIMEOUT":
                reason="baseline_pilot_timeout"
            else:
                s=probe("sat",256)
                if s["status"] in ("SAT","UNSAT"):
                    return dict(selection="--sat",reason="sat_pilot_solved",
                        status=s["status"],total_seconds=time.perf_counter()-started,
                        probe_seconds=sum(x["seconds"] for x in trace),
                        solve_seconds=0.0,trace=trace)
                if b["status"]=="UNKNOWN" and s["status"]=="UNKNOWN" and guard256(static,b["stats"],s["stats"]):
                    b1024=probe("baseline",1024)
                    if b1024["status"] in ("SAT","UNSAT"):
                        return dict(selection="default",reason="baseline_1024_solved",
                          status=b1024["status"],total_seconds=time.perf_counter()-started,
                          probe_seconds=sum(x["seconds"] for x in trace),
                          solve_seconds=0.0,trace=trace)
                    s1024=probe("sat",1024)
                    if s1024["status"] in ("SAT","UNSAT"):
                        return dict(selection="--sat",reason="sat_1024_solved",
                          status=s1024["status"],total_seconds=time.perf_counter()-started,
                          probe_seconds=sum(x["seconds"] for x in trace),
                          solve_seconds=0.0,trace=trace)
                    if b1024["status"]=="UNKNOWN" and s1024["status"]=="UNKNOWN" and guard1024(b1024["stats"],s1024["stats"]):
                        selection="--sat";reason="confirmed_256_to_1024"
                    else:reason="rejected_at_1024"
                else:reason="rejected_at_256"
    elif mode=="sat-fixed":
        selection="--sat";reason="fixed_sat"
    flags=("--sat",) if selection=="--sat" else ()
    if remaining()<=.002:
        status="TIMEOUT";solve_sec=0
    else:
        q=run(solver,path,flags,remaining())
        status=q["status"];solve_sec=q["seconds"]
    total=time.perf_counter()-started
    return dict(selection=selection,reason=reason,status=status,
      total_seconds=total,probe_seconds=sum(x["seconds"] for x in trace),
      solve_seconds=solve_sec,trace=trace)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--solver",required=True)
    parser.add_argument("--root",type=Path,default=Path("v168-results"))
    parser.add_argument("--timeout",type=float,default=CAP)
    parser.add_argument("--repeats",type=int,default=2)
    a=parser.parse_args()
    assert a.timeout==CAP and a.repeats==2
    a.root.mkdir(parents=True,exist_ok=True)
    data=cases(a.root)
    rows=[]
    for c in data:
        path=Path(c["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"]
        for repeat in range(a.repeats):
            order=MODES[repeat:]+MODES[:repeat]
            for mode in order:
                out=mode_run(a.solver,path,mode,a.timeout)
                row={**{k:v for k,v in c.items() if k not in ("path",)},
                     "repeat":repeat,"mode":mode,
                     "selection":out["selection"],"reason":out["reason"],
                     "status":out["status"],
                     "total_seconds":round(out["total_seconds"],6),
                     "probe_seconds":round(out["probe_seconds"],6),
                     "solve_seconds":round(out["solve_seconds"],6),
                     "trace_json":json.dumps(out["trace"],sort_keys=True)}
                rows.append(row)
                print("V168_MEASURE",c["group"],c["seed"],repeat,mode,
                      row["selection"],row["reason"],row["status"],
                      f"{row['total_seconds']:.5f}s",flush=True)
    with (a.root/"measurements.csv").open("w",newline="",encoding="utf-8") as dst:
        writer=csv.DictWriter(dst,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    totals={}
    for group in ("holdout","control"):
        totals[group]={}
        for mode in MODES:
            v=[r for r in rows if r["mode"]==mode and r["group"]==group]
            totals[group][mode]={"attempts":len(v),
             "solved":sum(r["status"] in ("SAT","UNSAT") for r in v),
             "PAR2_seconds":round(statistics.mean(
                r["total_seconds"] if r["status"] in ("SAT","UNSAT")
                    else 2*a.timeout for r in v),6),
             "median_seconds":round(statistics.median(r["total_seconds"] for r in v),6),
             "sat_selected":sum(r["selection"]=="--sat" for r in v),
             "avg_probe_seconds":round(statistics.mean(r["probe_seconds"] for r in v),6)}
        print("V168_SUMMARY",group,json.dumps(totals[group],sort_keys=True),flush=True)
    groupby={}
    for r in rows:groupby.setdefault((r["seed"],r["repeat"]),{})[r["mode"]]=r
    assert len(groupby)==len(data)*a.repeats
    for key,m in groupby.items():
        assert set(m)==set(MODES),(key,m)
        answers={x["status"] for x in m.values() if x["status"] in ("SAT","UNSAT")}
        assert len(answers)<=1,(key,answers)
        assert all(x["status"] in ("SAT","UNSAT","TIMEOUT","UNKNOWN") for x in m.values())
    for c in data:
        rr=[r for r in rows if r["seed"]==c["seed"]]
        per={m:{"mean_s":round(statistics.mean(x["total_seconds"] for x in rr if x["mode"]==m),5),
            "solved":sum(x["status"] in ("SAT","UNSAT") for x in rr if x["mode"]==m)}
            for m in MODES}
        print("V168_CASE",c["seed"],json.dumps(per,sort_keys=True),flush=True)
    summary={"pin":PIN,"budget":a.timeout,"repeats":a.repeats,"cases":len(data),
      "totals":totals,"limitations":[
       "Single random3 CNF generator family; not SAT Competition diverse portfolio",
       "Safety gate was chosen using V16.7b development observations, no independent guarantee",
       "All probes are independent process starts; no saved learned clauses",
       "SAT assignments validated on original CNF; UNSAT has no independent proof checker",
       "PAR-2 counts timeout as 12 seconds; source of the solver pinned"]}
    (a.root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V168_AUDIT_PASS",len(rows),"measurements",len(data),
          "formulas; all SAT assignments validated",flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""V16.6b prospective benchmark: same pinned upstream Kissat executable.

V16.6b is a frozen exploratory policy derived from V16.5 development seeds.
The *new* v166b_test seeds are generated before solver timing; no adaptive
retuning. Include full selector scan time in adaptive measurements. No
SAT/UNSAT label is ever given to the selector or solver.
"""
import argparse,csv,math,statistics,subprocess,time,json
from collections import defaultdict
from pathlib import Path
from portfolio_v165 import select_profile as old_policy
from relations_v166b import features, choose, report, FROZEN_POLICY

MODES=("baseline","sat-fixed","v165-policy","v166b-policy")

def check_model(path,text):
    assignments={}
    for line in text.splitlines():
        if line.startswith("v "):
            for raw in line.split()[1:]:
                lit=int(raw)
                if not lit:continue
                v=abs(lit)
                if v in assignments and assignments[v]!=(lit>0):return False
                assignments[v]=lit>0
    if not assignments:return False
    n=None;pending=[];number=0
    with Path(path).open(encoding="ascii") as file:
        for line in file:
            line=line.strip()
            if not line or line.startswith("c") or line.startswith("%"):continue
            if line.startswith("p "):
                n=int(line.split()[2]);continue
            for token in line.split():
                lit=int(token)
                if lit:pending.append(lit)
                else:
                    number+=1
                    if not any(assignments.get(abs(v))==(v>0) for v in pending):
                        return False
                    pending=[]
    return bool(n and len(assignments)==n and not pending and number>0)

def execute(solver,flags,path,deadline):
    t=time.perf_counter()
    try:
        proc=subprocess.run([solver,*flags,str(path)],capture_output=True,
                            text=True,timeout=deadline,check=False)
        elapsed=time.perf_counter()-t
        result={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
        if result=="SAT" and not check_model(path,proc.stdout):
            raise ValueError(f"invalid SAT witness for {path}")
        if result=="ERROR":
            raise RuntimeError(f"solver rc={proc.returncode} stdout={proc.stdout[-400:]} stderr={proc.stderr[-400:]}")
        return result,elapsed
    except subprocess.TimeoutExpired:
        return "TIMEOUT",time.perf_counter()-t

def summary(rows,deadline,out):
    groups=sorted(set(r["group"] for r in rows))
    scores={}
    for g in groups:
        scores[g]={}
        subset=[x for x in rows if x["group"]==g]
        for mode in MODES:
            chosen=[x for x in subset if x["mode"]==mode]
            assert len(chosen)==len(subset)//len(MODES)
            solved=sum(x["result"] in ("SAT","UNSAT") for x in chosen)
            par2=sum(x["total_s"] if x["result"] in ("SAT","UNSAT") else 2*deadline
                     for x in chosen)/len(chosen)
            scores[g][mode]={"solved":solved,"attempts":len(chosen),
                "par2_s":round(par2,6),
                "median_s":round(statistics.median(x["total_s"] for x in chosen),6)}
    paired=defaultdict(dict)
    for x in rows:
        paired[(x["group"],x["file"],x["rep"])][x["mode"]]=x
    for key,dict_ in paired.items():
        assert set(dict_)==set(MODES),(key,dict_)
        answers={v["result"] for v in dict_.values() if v["result"] in ("SAT","UNSAT")}
        assert len(answers)<=1,(key,answers)
    by_file=[]
    for g in groups:
        for name in sorted(set(x["file"] for x in rows if x["group"]==g)):
            rset=[x for x in rows if x["file"]==name and x["group"]==g]
            times={}
            for mode in MODES:
                v=[x for x in rset if x["mode"]==mode]
                times[mode]=round(statistics.median(x["total_s"] for x in v),6)
            by_file.append({"group":g,"file":name,"median_s":times,
                            "selected":next(x["profile"] for x in rset if x["mode"]=="v166b-policy")})
    result={
       "selector":FROZEN_POLICY,"timeout_seconds":deadline,
       "modes":MODES,"groups":scores,"per_formula":by_file,
       "limitations":["V16.5 development seed selection prompted the frozen thresholds",
          "Only test group is a prospective untouched holdout",
          "Upstream Kissat 4.0.4 profiles, not a new solver implementation",
          "UNSAT outputs use the same pinned upstream Kissat, no separate DRAT/LRAT proof",
          "Timeouts scored as PAR-2; solve-only ratios exclude censored cases"]}
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for group in groups:
        print("V166B_SUMMARY",group,json.dumps(scores[group],sort_keys=True),flush=True)
    for file in by_file:
        print("V166B_FORMULA",json.dumps(file,sort_keys=True),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf-dir",type=Path,required=True)
    p.add_argument("--solver",required=True)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--timeout",type=float,default=10.)
    p.add_argument("--output",type=Path,default=Path("v166b_results"))
    args=p.parse_args()
    assert args.repeats>=1 and args.timeout>0
    files=sorted(args.cnf_dir.rglob("*.cnf"))
    assert files
    rows=[]
    for path in files:
        # Classification pre-computation is just for audits, not timed solver.
        f=features(path)
        f_old={k:f[k] for k in ("nvars","nclauses","density","three_fraction",
             "binary_fraction","degree_cv","polarity_balance")}
        a=choose(f)
        b=old_policy(f_old)
        print("V166B_CLASSIFY",path.parent.name,path.name,
              "v165",(" ".join(b) or "default"),
              "v166b",(" ".join(a) or "default"),
              json.dumps(report(f),sort_keys=True),flush=True)
        for rep in range(args.repeats):
            rotated=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            for mode in rotated:
                start=time.perf_counter()
                if mode=="baseline":flags=();gate=0.
                elif mode=="sat-fixed":flags=("--sat",);gate=0.
                elif mode=="v165-policy":
                    f2=features(path)
                    flags=old_policy(f2)
                    gate=time.perf_counter()-start
                else:
                    f2=features(path)
                    flags=choose(f2)
                    gate=time.perf_counter()-start
                result,elapsed=execute(args.solver,flags,path,args.timeout)
                r={"group":path.parent.name,"file":path.name,"rep":rep,
                   "mode":mode,"profile":" ".join(flags) or "default",
                   "result":result,"gate_s":round(gate,7),
                   "solve_s":round(elapsed,7),
                   "total_s":round(elapsed+gate,7)}
                rows.append(r)
                print("V166B_MEASURE",r["group"],r["file"],rep,mode,r["profile"],
                      result,f"{r['total_s']:.6f}s",flush=True)
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/"runs.csv").open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    summary(rows,args.timeout,args.output/"summary.json")
    print("V166B_AUDIT_PASS",len(rows),"trials",len(files),"formulas",flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""DRNAS SAT V16.7 early-CDCL-dynamics investigation, not a learned selector.

Preregistered complete seed slate: 4 OLD development, 8 NEW prospective,
2 off-distribution density controls. Original CNF hashes are frozen before
any solver invocation. Pinned upstream Kissat 4.0.4 is used unchanged.

Probes: 64, 256 conflicts under default/--sat, with -s statistics captured.
Final solves: 2 repetitions of baseline/--sat on all CNFs, plus isolated
target-only/restart-only on the old development CNFs. Separate probe runs are
not resumed or warm-started: their time MUST be added to any practical
selection proposal. No online profile policy is trained from the holdout.
"""
import argparse,csv,hashlib,json,math,random,re,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict
from generate_v165_blind import make_cnf
from relations_v166b import features as structural_features, report as structural_report

DEV=((165000,640),(165001,640),(165004,480),(165005,480))
NEW=tuple((167700+i,260 if i<4 else 340) for i in range(8))
CONTROL=((167708,260,3.8),(167709,260,4.7))
PROBE_BUDGETS=(64,256)
PROBE_MODES={"default":(),"sat":("--sat",)}
FULL_MODES={"default":(),"sat":("--sat",),"target_only":("--target=2",),
            "restart_only":("--restartint=50",)}
STAT_NAMES=("conflicts","decisions","restarts","propagations","learned",
            "reductions","rephases","search_ticks","clauses","variables")
PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def gen(root):
    manifest=[]
    for group,specs in (
        ("development",((seed,n,4.26) for seed,n in DEV)),
        ("holdout",((seed,n,4.26) for seed,n in NEW)),
        ("control",CONTROL)):
        for seed,n,ratio in specs:
            path=root/"cnf"/group/f"random3_n{n}_seed{seed}.cnf"
            make_cnf(path,n,ratio,seed)
            f=structural_features(path)
            manifest.append({"group":group,"seed":seed,"nvars":n,
                 "ratio":ratio,"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                 "static":structural_report(f)})
    assert len(manifest)==14
    assert len({x["sha256"] for x in manifest})==14
    (root/"frozen-manifest.json").write_text(json.dumps(
        {"protocol":"v167-fixed-before-early-diagnostics-or-solves","cases":manifest,
         "new_holdout_seeds":list(range(167700,167708)),
         "kissat_commit":PIN},indent=2))
    print("V167_FROZEN",len(manifest),"originals 8 independent new seeds",flush=True)
    return manifest

def check_model(path,output):
    assignment={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for token in line.split()[1:]:
            lit=int(token)
            if lit==0:continue
            if abs(lit) in assignment and assignment[abs(lit)]!=(lit>0):return False
            assignment[abs(lit)]=lit>0
    n=None;pending=[];clauses=0
    with path.open() as fd:
        for line in fd:
            line=line.strip()
            if not line or line.startswith("c") or line.startswith("%"):continue
            if line.startswith("p "):
                n=int(line.split()[2]);continue
            for tok in line.split():
                lit=int(tok)
                if lit:pending.append(lit)
                else:
                    clauses+=1
                    if not any(assignment.get(abs(x))==(x>0) for x in pending):return False
                    pending=[]
    return bool(n and clauses and len(assignment)==n and not pending)

def stats(txt):
    result={}
    for key in STAT_NAMES:
        # Kissat's human readable counters have changed across releases.
        # Record missing fields as null, never fake zeros.
        candidates=(rf"(?m)^c\s+{re.escape(key)}\s*:?\s+([\d,]+)\b",
                    rf"(?m)^c\s+([\d,]+)\s+{re.escape(key)}\b")
        found=None
        for p in candidates:
            m=re.search(p,txt,re.IGNORECASE)
            if m:
                found=int(m.group(1).replace(",",""));break
        result[key]=found
    return result

def invoke(solver,args,path,timeout,record_path=None):
    cmd=[solver,*args,str(path.resolve())]
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                         errors="replace",timeout=timeout,check=False)
        sec=time.perf_counter()-t
        rc=p.returncode
        out=p.stdout;err=p.stderr
        result={10:"SAT",20:"UNSAT",0:"UNKNOWN"}.get(rc,"ERROR")
        if result=="SAT" and not check_model(path,out):
            result="INVALID_SAT_MODEL"
    except subprocess.TimeoutExpired as e:
        sec=time.perf_counter()-t
        rc=-1;result="TIMEOUT"
        out=e.stdout.decode("utf-8","replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
        err=e.stderr.decode("utf-8","replace") if isinstance(e.stderr,bytes) else (e.stderr or "")
    txt=out+"\n"+err
    if record_path:
        record_path.parent.mkdir(parents=True,exist_ok=True)
        record_path.write_text("COMMAND "+" ".join(cmd)+"\nRETURN "+str(rc)+
           "\nELAPSED "+str(round(sec,6))+"\n"+txt,encoding="utf-8")
    return {"status":result,"elapsed_s":round(sec,6),"returncode":rc,
            "stats":stats(txt) if record_path else None}

def report(root,manifest,probe,full,timeout):
    d={}
    for row in full:
        d.setdefault((row["group"],row["seed"],row["mode"]),[]).append(row)
    for x in manifest:
        g=x["group"];seed=x["seed"]
        for mode in ("default","sat"):
            assert len(d[g,seed,mode])==2,(g,seed,mode)
    results={}
    for group in ("development","holdout","control"):
        results[group]={}
        for mode in ("default","sat","target_only","restart_only"):
            rr=[x for x in full if x["group"]==group and x["mode"]==mode]
            if not rr:continue
            score=sum(x["elapsed_s"] if x["status"] in ("SAT","UNSAT")
                      else 2*timeout for x in rr)/len(rr)
            results[group][mode]={"attempts":len(rr),"solved":sum(x["status"] in ("SAT","UNSAT") for x in rr),
              "PAR2_seconds":round(score,6),
              "median_seconds":round(statistics.median(x["elapsed_s"] for x in rr),6)}
        print("V167_SUMMARY",group,json.dumps(results[group],sort_keys=True),flush=True)
    percase=[]
    probedict=defaultdict(dict)
    for x in probe:probedict[x["group"],x["seed"]][x["mode"],x["budget"]]=x
    for x in manifest:
        g=x["group"];seed=x["seed"]
        obj={"group":g,"seed":seed,"static":x["static"]}
        for mode in ("default","sat"):
            rr=d[g,seed,mode]
            obj[mode]={"median_seconds":round(statistics.median(y["elapsed_s"] for y in rr),6),
                "solved":sum(y["status"] in ("SAT","UNSAT") for y in rr)}
        for mode in ("default","sat"):
            for limit in PROBE_BUDGETS:
                row=probedict[g,seed][mode,limit]
                obj[f"probe_{mode}_{limit}"]={"elapsed_s":row["elapsed_s"],
                   "status":row["status"],"stats":row["stats"]}
        if obj["sat"]["solved"]==2 and obj["default"]["solved"]==2:
            obj["paired_speed_ratio"]=round(obj["default"]["median_seconds"]/obj["sat"]["median_seconds"],5)
        else:obj["paired_speed_ratio"]=None
        percase.append(obj)
        print("V167_CASE",json.dumps({k:v for k,v in obj.items()
            if k not in ("static","probe_default_64","probe_default_256","probe_sat_64","probe_sat_256")},sort_keys=True),flush=True)
    # Early-default probes are potentially useful features, but do not
    # select a live profile here or tune a threshold after seeing holdout.
    by_id=defaultdict(dict)
    for row in full:
        key=(row["group"],row["seed"],row["repeat"])
        by_id[key][row["mode"]]=row
    for key,modes in by_id.items():
        expected=set(FULL_MODES) if key[0]=="development" else {"default","sat"}
        assert set(modes)==expected,(key,modes)
        ans={r["status"] for r in modes.values() if r["status"] in ("SAT","UNSAT")}
        assert len(ans)<=1,(key,ans)
        assert all(r["status"] not in ("ERROR","INVALID_SAT_MODEL") for r in modes.values()),key
    result={"kissat_commit":PIN,"probe_conflict_budgets":PROBE_BUDGETS,
       "repeats":2,"timeout_s":timeout,"group_summaries":results,"cases":percase,
       "limitations":["No method here changes Kissat internals or establishes causal inference",
          "Independent probes restart the solver and incur extra time; not a free online classifier",
          "UNSAT outcomes are upstream Kissat solver claims, not separately proof-checked",
          "The eight fresh seeds share the random3 family with development data",
          "All timeouts count as double the full solve cap in PAR-2"]}
    (root/"summary.json").write_text(json.dumps(result,indent=2))
    print("V167_AUDIT_PASS",len(probe),"preflight probes",len(full),"full solves",
          "all original-CNF SAT witnesses checked",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--root",type=Path,default=Path("v167-investigation"))
    p.add_argument("--probe-timeout",type=float,default=2.0)
    p.add_argument("--solve-timeout",type=float,default=6.0)
    a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=True)
    manifest=gen(a.root)
    prob=[]
    # Probe order and budgets fixed before observing any answer or timings.
    for c in manifest:
        path=Path(c["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"]
        for mode,flags in PROBE_MODES.items():
            for budget in PROBE_BUDGETS:
                opt=("--conflicts="+str(budget),"-s")
                record=a.root/"probe_logs"/f"{c['group']}_{c['seed']}_{mode}_{budget}.txt"
                ans=invoke(a.solver,(*flags,*opt),path,a.probe_timeout,record)
                if ans["status"] in ("ERROR","INVALID_SAT_MODEL"):raise RuntimeError(f"probe error {c} {ans}")
                prob.append({"group":c["group"],"seed":c["seed"],"mode":mode,
                             "budget":budget,**ans})
                print("V167_PROBE",c["group"],c["seed"],mode,budget,ans["status"],
                      "sec",ans["elapsed_s"],"counts",json.dumps(ans["stats"],sort_keys=True),flush=True)
    full=[]
    for c in manifest:
        path=Path(c["path"])
        modes=FULL_MODES if c["group"]=="development" else {
            k:FULL_MODES[k] for k in ("default","sat")}
        for rep in range(2):
            order=list(modes)
            order=order[rep%len(order):]+order[:rep%len(order)]
            for mode in order:
                ans=invoke(a.solver,modes[mode],path,a.solve_timeout)
                ans.pop("stats")
                full.append({"group":c["group"],"seed":c["seed"],"mode":mode,
                    "repeat":rep,**ans})
                print("V167_SOLVE",c["group"],c["seed"],mode,rep,ans["status"],
                      ans["elapsed_s"],flush=True)
    with (a.root/"probe.csv").open("w",newline="") as file:
        # flatten counters to separate columns
        flat=[{**{k:v for k,v in r.items() if k!="stats"},
             **{("stat_"+k):v for k,v in r["stats"].items()}} for r in prob]
        w=csv.DictWriter(file,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    with (a.root/"solve.csv").open("w",newline="") as file:
        w=csv.DictWriter(file,fieldnames=list(full[0]));w.writeheader();w.writerows(full)
    report(a.root,manifest,prob,full,a.solve_timeout)
if __name__=="__main__":main()

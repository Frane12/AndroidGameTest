#!/usr/bin/env python3
"""DRNAS v9.7 official-submission same-CPU 5 candidates + 2 UNSAT controls.

Every solver runs in the SAME GitHub Actions runner and inherited CPU
affinity, fixed external 15s wall cap, three randomized-order repetitions.
No per-case selection by benchmark results (five candidates were previously
selected, so this is a CONFIRMATORY comparison on handpicked, seen cases).
"""
import argparse,csv,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
from official_shortlong_select import download_and_features
CANDIDATE_PREFIXES=(
    "ee44c3f46423", "2b35377a7b95",
    "8d0d8518a438", "2b8cac8e1f5c", "3ed56242f55e"
)
MODE_PATHS={
 "drnas_single96":"./v97_comparison",
 "drnas_single128":"./v97_comparison",
 "ca_plain":"./v97_comparison",
 "mergesat-l":"official_bins/bins/mergesat-l",
 "mergesat":"official_bins/bins/mergesat",
 "kissat-mab-eae2":"official_bins/bins/kissat-mab-eae2",
 "kissat-lr-ds":"official_bins/bins/kissat-lr-ds",
 "cadical3":"official_bins/bins/cadical3",
}
REPEATS=3
CAP=15.0
def classify(stdout,code):
    # The SAT Competition submission wrappers may suppress or reformat
    # the status line. Standard SAT solver exit code SAT=10, UNSAT=20.
    if code==10:return "SAT"
    if code==20:return "UNSAT"
    for ln in stdout.splitlines():
        q=ln.strip().lower()
        if q.startswith("s unsatisfiable"):return "UNSAT"
        if q.startswith("s satisfiable"):return "SAT"
    return "ERROR"
def plan(old,new):
    prior={x["id"]:dict(x,cohort="prior-v94") for x in old["cases"]}
    prior.update({x["id"]:dict(x,cohort="new-v96") for x in new["cases"]})
    chosen=[]
    for prefix in CANDIDATE_PREFIXES:
        matching=[c for id,c in prior.items() if id.startswith(prefix)]
        assert len(matching)==1,(prefix,len(matching))
        assert matching[0]["official_label"]=="SAT"
        chosen.append(matching[0])
    # Add two fixed, not cherry-picked UNSAT controls to characterize
    # regressions: historical known UNSAT and new 2026 disjoint sample.
    oldunsat=sorted((x for x in old["cases"] if x["official_label"]=="UNSAT"),
                    key=lambda x:x["id"])
    newunsat=sorted((x for x in new["cases"] if x["official_label"]=="UNSAT"),
                    key=lambda x:x["id"])
    assert oldunsat and newunsat
    chosen += [dict(oldunsat[0],cohort="prior-v94"),
               dict(newunsat[0],cohort="new-v96")]
    assert len(chosen)==7 and len({x["id"] for x in chosen})==7
    return chosen

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int,required=True)
    ap.add_argument("--output",default="results")
    args=ap.parse_args()
    assert 0<=args.shard<3
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    old=json.loads(Path("manifests/old/official_v94_manifest.json").read_text())
    new=json.loads(Path("manifests/new/official_v96_manifest.json").read_text())
    selection=plan(old,new)
    shard_cases=selection[args.shard::3]
    assert len(shard_cases)>0
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    for mode,exe in MODE_PATHS.items():
        if not Path(exe).is_file():
            raise RuntimeError("Missing actual official submission binary "+mode+": "+exe)
    (root/"meta.json").write_text(json.dumps({
        "shard":args.shard,"cpu_core":core,"cases":shard_cases,
        "mode_binary":MODE_PATHS,"repeat":REPEATS,"wall_cap":CAP,
        "qualification":"five prior record candidates + two UNSAT controls, not random or representative"},indent=2))
    fields=("case","prefix","truth","cohort","sha256","mode","rep","status",
           "wall_s","error","binary_sha256","cpu_core","exit_code")
    binarysha={mode:hashlib.sha256(Path(path).read_bytes()).hexdigest()
               for mode,path in MODE_PATHS.items()}
    rows=[]
    with (root/"raw.csv").open("w",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for case in shard_cases:
            id=case["id"]
            dest=root/(id+".cnf")
            check=download_and_features(id,dest)
            if check["sha256"]!=case["sha256"] or check["features"]!=case["features"]:
                raise RuntimeError("Source CNF changed: "+id)
            print("V97_VERIFIED_CNF",id,case["official_label"],check["sha256"],flush=True)
            for rep in range(REPEATS):
                order=list(MODE_PATHS)
                random.Random(int(id[:12],16)+rep*104729).shuffle(order)
                for mode in order:
                    if mode=="drnas_single96":
                        command=["./v97_comparison","v96_96",str(dest),str(1249+rep)]
                    elif mode=="drnas_single128":
                        command=["./v97_comparison","v96_128",str(dest),str(1249+rep)]
                    elif mode=="ca_plain":
                        command=["./v97_comparison","ca_plain",str(dest),str(1249+rep)]
                    else:
                        command=[str(Path(MODE_PATHS[mode]).resolve()),str(dest)]
                    started=time.perf_counter()
                    status="ERROR";error="";exit_code=""
                    try:
                        p=subprocess.run(command,capture_output=True,text=True,
                                          timeout=CAP,check=False)
                        sec=time.perf_counter()-started
                        exit_code=p.returncode
                        if mode.startswith("drnas_") or mode=="ca_plain":
                            matches=[l for l in p.stdout.splitlines()
                                     if l.startswith("DRNAS_CAUSAL\t")]
                            if len(matches)!=1 or p.returncode!=0:
                                raise ValueError("DRNAS malformed output rc="+str(p.returncode)+
                                    " stderr="+p.stderr[-250:])
                            values=dict(x.split("=",1) for x in matches[0].split("\t")[1:])
                            status=values["answer"]
                        else:
                            status=classify(p.stdout,p.returncode)
                        if status!=case["official_label"]:
                            raise ValueError("official truth mismatch/invalid status="+status+
                                             " expected="+case["official_label"]+
                                             " rc="+str(p.returncode)+" out="+p.stdout[-180:])
                    except subprocess.TimeoutExpired:
                        status="TIMEOUT";sec=CAP;exit_code="TIMEOUT"
                    except Exception as e:
                        sec=time.perf_counter()-started
                        status="ERROR";error=str(e)
                    rec={"case":id,"prefix":id[:12],"truth":case["official_label"],
                       "cohort":case["cohort"],"sha256":case["sha256"],"mode":mode,
                       "rep":rep,"status":status,"wall_s":round(sec,6),
                       "error":error,"binary_sha256":binarysha[mode],
                       "cpu_core":core,"exit_code":exit_code}
                    writer.writerow(rec);file.flush();rows.append(rec)
                    print("V97_RESULT",id[:12],mode,rep,status,rec["wall_s"],error[:160],flush=True)
                    if status=="ERROR":raise RuntimeError("Fail-closed "+str(rec))
            dest.unlink(missing_ok=True)
    assert len(rows)==len(shard_cases)*len(MODE_PATHS)*REPEATS
    print("V97_SHARD_PASS",args.shard,len(rows),flush=True)
if __name__=="__main__":main()

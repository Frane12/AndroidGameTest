#!/usr/bin/env python3
"""DRNAS SAT V7.8 frozen paired benchmark, native unmodified CaDiCaL 3.0.1.

Every original CNF is SHA256 authenticated, with the known SAT/UNSAT label.
All 10 methods see exactly the same input and process cutoff.
No sample is discarded due to timeout: PAR2 = 2*cutoff for timeout.
Experimental fastpath_* modes pay identical eligibility/profile extraction
and differ only in underlying phase policy; plain is untouched baseline.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from collections import defaultdict,Counter
from pathlib import Path

METHODS=("plain","quality_guided","fastpath_plain","fastpath_guided")
FIELDS=("case","family","known_answer","method","repeat","answer","wall_s","native_s",
        "hints","first_budget","stage1","second_budget","stage2",
        "extended","resumed","observed","short3","short5","short8",
        "sum_len","short_fraction","probe_us","extension_us","resume_us",
        "variables","clauses","selected","preflight_us","mean_hint_margin",
        "strong_fraction","ternary_fraction","proposed","cutoff_s","error","header_eligible","header_variables","header_clauses")

def header_gate(source):
    """Read static eligibility even if native process later times out."""
    with open(source,encoding="ascii",errors="replace") as fp:
        for line in fp:
            line=line.strip()
            if not line or line.startswith("c"):continue
            t=line.split()
            if len(t)!=4 or t[:2]!=["p","cnf"]:
                raise ValueError("Invalid DIMACS header: "+str(source))
            n,m=int(t[2]),int(t[3])
            if n<=0 or m<=0:raise ValueError("Invalid DIMACS dimensions")
            return int(n>=180 and m>=800 and m*10>=n*39 and m*10<=n*44),n,m
    raise ValueError("No DIMACS header in "+str(source))

def execute(binary,method,source,seed,cutoff):
    start=time.perf_counter()
    try:
        result=subprocess.run([str(binary),method,str(source),str(seed)],
                   capture_output=True,text=True,check=False,timeout=cutoff)
    except subprocess.TimeoutExpired:
        return dict(answer="TIMEOUT",wall_s=cutoff,native_s=None,error="")
    wall=time.perf_counter()-start
    if result.returncode:
        raise RuntimeError(f"{method} native crash: {result.stderr[-1200:]}")
    found=[line for line in result.stdout.splitlines()
           if line.startswith("DRNAS_RESULT\t")]
    if len(found)!=1:
        raise RuntimeError(f"Machine result expected exactly once for {method}")
    tokens=found[0].split("\t")
    if len(tokens)!=28 or tokens[1]!=method or tokens[2] not in ("SAT","UNSAT"):
        raise RuntimeError(f"Malformed C++ result: {found[0][:300]}")
    try:
        return dict(answer=tokens[2],wall_s=wall,native_s=float(tokens[3])/1e6,
           hints=int(tokens[4]),first_budget=int(tokens[5]),stage1=int(tokens[6]),
           second_budget=int(tokens[7]),stage2=int(tokens[8]),
           extended=int(tokens[9]),resumed=int(tokens[10]),
           observed=int(tokens[11]),short3=int(tokens[12]),short5=int(tokens[13]),
           short8=int(tokens[14]),sum_len=int(tokens[15]),
           short_fraction=float(tokens[16]),probe_us=float(tokens[17]),
           extension_us=float(tokens[18]),resume_us=float(tokens[19]),
           variables=int(tokens[20]),clauses=int(tokens[21]),
           selected=int(tokens[22]),preflight_us=float(tokens[23]),
           mean_hint_margin=float(tokens[24]),strong_fraction=float(tokens[25]),
           ternary_fraction=float(tokens[26]),proposed=int(tokens[27]),error="")
    except (IndexError,ValueError) as ex:
        raise RuntimeError("Cannot parse C++ line "+found[0]) from ex

def summarize(rows,reps,cutoff):
    cases=defaultdict(lambda:defaultdict(list))
    groups={};status={}
    for row in rows:
        name=row["case"];m=row["method"]
        cases[name][m].append(row)
        groups[name]=row["family"]
        status[name]=row["known_answer"]
    ids=sorted(cases)
    if not ids:raise RuntimeError("No complete cases")
    for name in ids:
        if set(cases[name])!=set(METHODS):
            raise RuntimeError(f"Missing modes {name}: {set(cases[name])}")
        for mode in METHODS:
            trials=cases[name][mode]
            if len(trials)!=reps:raise RuntimeError(f"Missing repeated trial {name}/{mode}")
            if any(x["answer"] not in ("TIMEOUT",status[name]) for x in trials):
                raise RuntimeError(f"Invalid SAT answer {name}/{mode}")

    def cost(name,mode):
        return statistics.median(
            2*cutoff if x["answer"]=="TIMEOUT" else x["wall_s"]
            for x in cases[name][mode])
    def evaluate(names,mode):
        if not names:return None
        base=sum(cost(n,"plain") for n in names)
        score=sum(cost(n,mode) for n in names)
        return {
            "n_instances":len(names),
            "PAR2_sum_case_medians_s":round(score,6),
            "speed_ratio_plain_over_method":round(base/max(score,1e-15),6),
            "solved_runs":sum(x["answer"]!="TIMEOUT" for n in names for x in cases[n][mode]),
            "total_runs":len(names)*reps,
            "faster_instances_vs_plain":sum(cost(n,mode)<cost(n,"plain") for n in names),
            "slower_instances_vs_plain":sum(cost(n,mode)>cost(n,"plain") for n in names),
            "gated_instances":sum(any(x["header_eligible"] for x in cases[n][mode]) for n in names) if mode.startswith("fastpath_") else 0,
            "header_eligible_instances":sum(any(x["header_eligible"] for x in cases[n][mode]) for n in names),
            "extended_instances":sum(any(x["extended"] for x in cases[n][mode]) for n in names),
            "gated_hinted_instances":sum(any(x["hints"] and x["selected"]
                     for x in cases[n][mode]) for n in names),
        }
    fam=defaultdict(list)
    for k in ids:fam[groups[k]].append(k)
    by_fam={f:{m:evaluate(keys,m) for m in METHODS}
              for f,keys in sorted(fam.items())}
    overall={m:evaluate(ids,m) for m in METHODS}
    rng=random.Random(78081031)
    contrasts={}
    matched=[
      ("fastpath_guided","fastpath_plain"),
      ("fastpath_guided","quality_guided"),
      ("fastpath_guided","plain"),
      ("quality_guided","plain")
    ]
    for a,b in matched:
        ratios=[]
        ca=sum(cost(k,a) for k in ids)
        cb=sum(cost(k,b) for k in ids)
        for _ in range(800):
            draw=[rng.choice(ids) for __ in ids]
            aa=sum(cost(k,a) for k in draw)
            bb=sum(cost(k,b) for k in draw)
            ratios.append(bb/max(aa,1e-15))
        ratios.sort()
        contrasts[f"{a}_vs_{b}"]={
            "ratio_control_over_method":round(cb/max(ca,1e-15),6),
            "paired_bootstrap_95pct":[round(ratios[19],6),round(ratios[779],6)],
            "faster_instances":sum(cost(k,a)<cost(k,b) for k in ids),
            "slower_instances":sum(cost(k,a)>cost(k,b) for k in ids),
        }
    return {
       "n_instances":len(ids),
       "repetitions":reps,
       "cutoff_s":cutoff,
       "unmodified_solver":"Official CaDiCaL rel-3.0.1",
       "fastpath_rule":"n>=180, m>=800, 3.9<=m/n<=4.4; only static input counts",
       "methods":overall,
       "families":by_fam,
       "contrasts":contrasts,
       "caveats":[
         "All original SATLIB / SAT Competition 2025 CNF originals verified by SHA256 before solving.",
         "Method run order randomized independently per CNF and repetition.",
         "PAR2 score sums median per-CNF process wall clock; timeouts penalized 2x cutoff, not discarded.",
         "Cheap gate O(1) uses only header-derived variable and clause counts.",
         "Gated candidate variants pay same extra polarity-feature diagnostic preflight, matched no-hint control.",
         "Clause-size callback is observational, not LBD and not necessarily all solver learn events.",
         "No labels or names are read by the gate. SAT model verified in C++; UNSAT status cross-checks original known labels.",
         "Bootstrap intervals resample original formulas; intervals containing 1 do not prove acceleration.",
         "Benefit Predictor fields are telemetry only; selecting thresholds after reviewing this holdout would invalidate independent validation."
       ]
    }

def main(args):
    source=json.loads(Path(args.verification).read_text())
    roots=source[args.group]
    root=Path(args.outdir);root.mkdir(parents=True,exist_ok=True)
    rows=[]
    with (root/"raw.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for i,entry in enumerate(roots):
            path=Path(entry["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["expected_sha256"]:
                raise RuntimeError("SHA256 incorrect: "+str(path))
            if entry["status"] not in ("SAT","UNSAT"):
                raise RuntimeError("Missing original SAT/UNSAT label")
            eligible_header,header_n,header_m=header_gate(path)
            for rep in range(args.repeats):
                order=list(METHODS)
                random.Random(78081031+i*193+rep*101).shuffle(order)
                for mode in order:
                    outcome=execute(args.binary,mode,path,
                        seed=78080031+i*313+rep*631,cutoff=args.timeout)
                    row={col:outcome.get(col) for col in FIELDS}
                    row.update(case=entry["name"],family=entry["family"],
                           known_answer=entry["status"],method=mode,
                           repeat=rep,cutoff_s=args.timeout,
                           header_eligible=eligible_header,header_variables=header_n,
                           header_clauses=header_m)
                    if outcome["answer"]!="TIMEOUT" and int(outcome["selected"])!=eligible_header:
                        raise RuntimeError("C++ V7.8 gate disagrees with original CNF header on "+entry["name"])
                    rows.append(row)
                    writer.writerow(row);f.flush()
                    if outcome["answer"] not in ("TIMEOUT",entry["status"]):
                        raise RuntimeError(f"WRONG ANSWER {entry['name']}/{mode}: "+
                                           str(outcome["answer"]))
            print(f"VERIFIED {args.group} {i+1}/{len(roots)} {entry['name']}: "+
                  str(dict(Counter(x["answer"] for x in rows
                             if x["case"]==entry["name"]))),flush=True)
    result=summarize(rows,args.repeats,args.timeout)
    (root/"summary.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print("SUMMARY "+json.dumps({k:result[k] for k in
             ("n_instances","methods","contrasts")},indent=2),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--verification",required=True)
    p.add_argument("--group",choices=("pilot","holdout"),required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--timeout",type=float,default=12)
    p.add_argument("--repeats",type=int,default=2)
    args=p.parse_args()
    if args.repeats<1:raise ValueError("repeats must be positive")
    main(args)

#!/usr/bin/env python3
"""DRNAS NeuroFlow 7.9: prospective matched-control benchmark on untouched
SHA256-pinned original GBD SAT formulas; three repetitions, 15 second cutoff.

Pilot excluded from holdout. All variants run original unchanged
CaDiCaL 3.0.1; only public APIs on one persistent solver.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from collections import defaultdict,Counter
from pathlib import Path

METHODS=("plain","split1024","guided1024","quality_guided","quality_plain",
         "v79_selective","v79_matched_plain","v79_matched_random","v79_forced_guided")
FIELDS=("case","family","known_answer","method","repeat","answer","wall_s",
        "native_s","path","eligible","checkpoint","stage1","budget2","stage2",
        "candidate_count","observed","short5","short_ratio","preflight_us",
        "probe_us","extend_us","resume_us","resumed","variables","clauses",
        "timeout_probe_path","timeout_probe_observed","timeout_probe_short5",
        "timeout_probe_candidates","cutoff_s","error")
INT_FIELDS=("path","eligible","checkpoint","stage1","budget2","stage2",
            "candidate_count","observed","short5","resumed","variables","clauses")

def execute(binary,method,source,seed,timeout):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary),method,str(source),str(seed)],
                  capture_output=True,text=True,check=False,timeout=timeout)
    except subprocess.TimeoutExpired as err:
        # A pre-timeout flushed probe log may tell us WHICH path was taken;
        # do not replace native missing fields with fabricated values.
        raw=err.stdout or b""
        if isinstance(raw,bytes):raw=raw.decode("utf-8",errors="replace")
        result=dict(answer="TIMEOUT",wall_s=timeout,native_s=None,error="")
        for line in raw.splitlines():
            parts=line.split("\t")
            if len(parts)==10 and parts[0]=="DRNAS_PROBE" and parts[1]==method:
                result["timeout_probe_path"]=parts[2]
                result["timeout_probe_observed"]=int(parts[3])
                result["timeout_probe_short5"]=int(parts[4])
                result["timeout_probe_candidates"]=int(parts[6])
        return result
    wall=time.perf_counter()-started
    if p.returncode:
        raise RuntimeError(f"{method} native failed exit={p.returncode}: {p.stderr[-1200:]}")
    lines=[line.split("\t") for line in p.stdout.splitlines()
           if line.startswith("DRNAS_RESULT\t")]
    if len(lines)!=1 or len(lines[0])!=21 or lines[0][1]!=method or lines[0][2] not in ("SAT","UNSAT"):
        raise RuntimeError(f"Bad native result schema {method}: {p.stdout[-400:]}")
    r=lines[0]
    try:
        out=dict(answer=r[2],wall_s=wall,native_s=float(r[3])/1e6,
             short_ratio=float(r[13]),preflight_us=float(r[14]),
             probe_us=float(r[15]),extend_us=float(r[16]),resume_us=float(r[17]),
             timeout_probe_path=None,timeout_probe_observed=None,
             timeout_probe_short5=None,timeout_probe_candidates=None,error="")
        for key,pos in zip(INT_FIELDS,(4,5,6,7,8,9,10,11,12,18,19,20)):
            out[key]=int(r[pos])
        return out
    except (IndexError,ValueError) as exc:
        raise RuntimeError("Malformed native result "+str(r)) from exc

def summarize(rows,reps,timeout):
    lookup=defaultdict(lambda:defaultdict(list))
    families,labels={},{}
    for r in rows:
        key=r["case"]
        lookup[key][r["method"]].append(r)
        families[key]=r["family"]
        labels[key]=r["known_answer"]
    keys=sorted(lookup)
    if not keys:raise RuntimeError("Empty original benchmark")
    for key in keys:
        if set(lookup[key])!=set(METHODS):
            raise RuntimeError("Missing matched methods "+key)
        for mode in METHODS:
            case=lookup[key][mode]
            if len(case)!=reps or len(set(x["repeat"] for x in case))!=reps:
                raise RuntimeError("Missing or duplicated repetition "+key+" "+mode)
            for r in case:
                if r["answer"] not in ("TIMEOUT",labels[key]):
                    raise RuntimeError("WRONG ANSWER "+key+" "+mode+" "+r["answer"])
    def score(key,mode):
        return statistics.median(
            2*timeout if v["answer"]=="TIMEOUT" else float(v["wall_s"])
            for v in lookup[key][mode])
    def metrics(cases,mode):
        base=sum(score(k,"plain") for k in cases)
        total=sum(score(k,mode) for k in cases)
        return {"instances":len(cases),"par2_sum_case_medians_s":round(total,6),
            "speed_ratio_plain_over_method":round(base/max(total,1e-12),5),
            "solved_attempts":sum(x["answer"]!="TIMEOUT" for k in cases for x in lookup[k][mode]),
            "attempts":len(cases)*reps,
            "path_guide_cases":sum(any((x["path"]==2 or x["timeout_probe_path"]=="guide")
                                   for x in lookup[k][mode]) for k in cases),
            "path_split_cases":sum(any((x["path"]==1 or x["timeout_probe_path"]=="split")
                                   for x in lookup[k][mode]) for k in cases),
            "faster_vs_plain":sum(score(k,mode)<score(k,"plain") for k in cases),
            "slower_vs_plain":sum(score(k,mode)>score(k,"plain") for k in cases)}
    methods={m:metrics(keys,m) for m in METHODS}
    rng=random.Random(79081031)
    matched=[
      ("v79_selective","v79_matched_plain"),
      ("v79_selective","v79_matched_random"),
      ("v79_selective","plain"),
      ("v79_matched_plain","split1024"),
      ("v79_forced_guided","v79_selective"),
      ("guided1024","split1024"),
      ("quality_guided","quality_plain")]
    contrasts={}
    for a,b in matched:
        paired=[]
        for i in range(2500):
            ss=[rng.choice(keys) for _ in keys]
            c1=sum(score(k,a) for k in ss)
            c2=sum(score(k,b) for k in ss)
            paired.append(c2/max(c1,1e-12))
        paired.sort()
        aa=sum(score(k,a) for k in keys)
        bb=sum(score(k,b) for k in keys)
        contrasts[f"{a}_vs_{b}"]={
          "speed_ratio_control_over_method":round(bb/max(aa,1e-12),6),
          "paired_bootstrap_95pct":[round(paired[62],5),round(paired[2437],5)],
          "faster_instances":sum(score(k,a)<score(k,b) for k in keys),
          "slower_instances":sum(score(k,a)>score(k,b) for k in keys)}
    subfamilies=defaultdict(list)
    for k in keys:subfamilies[families[k]+"/"+labels[k]].append(k)
    per_case=[]
    for k in keys:
        d=dict(case=k,family=families[k],status=labels[k])
        d.update({m+"_par2_s":round(score(k,m),6) for m in METHODS})
        per_case.append(d)
    return {
      "version":"7.9",
      "n_originals":len(keys),"repetitions":reps,"cutoff_s":timeout,
      "methods":methods,"contrasts":contrasts,"per_case":per_case,
      "strata":{family:{m:metrics(items,m) for m in METHODS}
                for family,items in sorted(subfamilies.items())},
      "caveats":[
        "Original GBD input SHA256 freeze preceded solver benchmarking.",
        "Only non-excluded original CNFs included; input size limits predeclared.",
        "Native solver unchanged official CaDiCaL 3.0.1.",
        "Three repeats are not three independent formulas; paired bootstrap resamples original formulas.",
        "Guide/plain/random matched V7.9 branches share identical 1024-conflict checkpoint and 512-conflict follow-on boundaries.",
        "Clause-size offers are not LBD; intervention rule is heuristic and not trained.",
        "TIMED OUT subprocesses count as PAR2=30 seconds; native decision traces may be available before timeout.",
        "Original known SAT/UNSAT status cross-checks successful final answers; each SAT model checked clause by clause.",
        "Early candidates were screened only by predeclared source SIZE; no formulas cherry-picked by solve time.",
        "This single GBD polynomial family benchmark cannot prove general SAT superiority."
      ]}
def main(args):
    spec=json.loads(Path(args.verification).read_text())
    items=spec[args.group]
    if not items:raise RuntimeError("No eligible original CNFs")
    root=Path(args.outdir);root.mkdir(parents=True,exist_ok=True)
    rows=[]
    with (root/"raw.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for i,row in enumerate(items):
            original=Path(row["path"])
            if hashlib.sha256(original.read_bytes()).hexdigest()!=row["expected_sha256"]:
                raise RuntimeError("Original CNF SHA256 mismatch")
            if row["status"] not in ("SAT","UNSAT"):
                raise RuntimeError("Missing published label")
            seed_base=int(row["hash"][:8],16)
            for rep in range(args.repeats):
                order=list(METHODS)
                random.Random(seed_base^79081031^(rep*997)).shuffle(order)
                for mode in order:
                    data=execute(args.binary,mode,original,
                            (seed_base+rep*631)&0xffffffff,args.timeout)
                    one={k:data.get(k) for k in FIELDS}
                    one.update(case=row["name"],family=row["family"],
                          known_answer=row["status"],method=mode,repeat=rep,
                          cutoff_s=args.timeout)
                    rows.append(one);w.writerow(one);f.flush()
                    if one["answer"] not in ("TIMEOUT",row["status"]):
                        raise RuntimeError(f"INCORRECT SOLVER ANSWER {row['name']} {mode}")
            c=Counter(x["answer"] for x in rows if x["case"]==row["name"])
            print(f"VERIFIED {args.group} {i+1}/{len(items)} {row['name']} {dict(c)}",flush=True)
    result=summarize(rows,args.repeats,args.timeout)
    (root/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print("RESULT "+json.dumps(result["methods"],indent=2),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--verification",required=True)
    p.add_argument("--group",choices=("pilot","holdout"),required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--timeout",type=int,default=15)
    opts=p.parse_args()
    if opts.repeats<1 or opts.timeout<1:raise ValueError("Invalid repetition or timeout")
    main(opts)

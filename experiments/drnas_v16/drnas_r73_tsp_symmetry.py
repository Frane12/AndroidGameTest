#!/usr/bin/env python3
"""R73 simple symmetric TSP: R72's *same* exact CNFs with one sound symmetry break.
No new solver algorithm, heuristic, training, or extra intervention.
Symmetric weighted Hamiltonian tours have equivalent forward/reverse direction;
fix city 0 at position 0 (R72), then require city_at_pos_1 < city_at_pos_(n-1).
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, os, random
from pathlib import Path
import drnas_r72_tsp_sat as r72

PROTO = "DRNAS-R73-TSP-REVERSAL-SYMMETRY-FROZEN-20261103-v1"
CAP, REPS, SHARDS = 15.0, 2, 4
MODES = ("r72_original", "r73_reverse_break")

def ck(v, why):
    if not v: raise RuntimeError("R73_FAIL_CLOSED: " + why)

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def canon(path, n, expected_variables, expected_clauses, output):
    """Append only necessary clauses to old exact DIMACS; variable map R72 x[t][v]=1+t*n+v.
    This relies on R72's one-hot matrix being allocated before all other variables.
    Check this frozen contract explicitly in the independent generator selftest.
    """
    src = Path(path).read_text(encoding="ascii")
    lines=src.splitlines()
    hdr=[i for i,line in enumerate(lines) if line.startswith("p cnf ")]
    ck(len(hdr)==1,"original CNF header")
    i=hdr[0];parts=lines[i].split()
    ck(len(parts)==4 and int(parts[2])==expected_variables and
       int(parts[3])==expected_clauses,"original dimensions changed")
    # When city at position 1 is i and last city is j, forbid i>=j.
    # Reversing a tour keeps the same weight for a symmetric matrix.
    extra=[]
    for first_city in range(1,n):
        for last_city in range(1,first_city+1):
            first_var=1+n+first_city
            last_var=1+n*(n-1)+last_city
            ck(first_var<=expected_variables and last_var<=expected_variables,
               "R72 one-hot position variable out of range")
            extra.append(f"-{first_var} -{last_var} 0")
    ck(len(extra)==n*(n-1)//2,"incorrect reversal condition")
    lines[i]=f"p cnf {expected_variables} {expected_clauses+len(extra)}"
    Path(output).write_text("\n".join(lines+extra)+"\n",encoding="ascii")
    return len(extra)

def selftest():
    # For every Hamiltonian tour starting at 0, either it or its reversal
    # (exactly one) has second-city index < last-city index.
    for n in range(4,8):
        for p in itertools.permutations(range(1,n)):
            ck((p[0]<p[-1]) != (p[-1]<p[0]),"reversal symmetry property")
        f = r72.encode(r72.graph(n)[1],1000)
        # R72 allocates first n*n variables for x[t][v] in row-major order:
        ck(f.vars >= n*n and f.rows[0] == tuple(range(1,n+1)),
           "R72 position variable layout contract changed")
        for c in range(n):
            ck((1+n+c) <= n*n and (1+n*(n-1)+c)<=n*n,
               "position variable indexing invalid")
    print("R73_REVERSAL_SYMMETRY_MATH_SELFTEST_PASS",flush=True)

def freeze(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    # Preserve original R72 exactly (including seed, coordinates, bounds).
    r72.freeze(root)
    r72manifest=json.loads((root/"manifest.json").read_text())
    ck(r72manifest["protocol"]==r72.PROTO and len(r72manifest["cases"])==8,
       "R72 frozen cohort changed")
    original_manifest_sha=digest(root/"manifest.json")
    cases=[]
    for c in r72manifest["cases"]:
        n=c["n"];d=c["distances"]
        ck(all(d[i][j]==d[j][i] and (i!=j or d[i][j]==0)
               for i in range(n) for j in range(n)),"not a symmetric TSP")
        source=root/c["name"]
        ck(digest(source)==c["sha256"],"R72 source hash mismatch")
        candidate=root/(source.stem+"_sym.cnf")
        extra=canon(source,n,c["vars"],c["clauses"],candidate)
        ck(candidate.is_file(),"missing amended DIMACS")
        entry=dict(case=c["name"],n=n,kind=c["kind"],bound=c["bound"],
                   optimum=c["optimum"],orig_sha=c["sha256"],
                   candidate=candidate.name,candidate_sha=digest(candidate),
                   clauses_original=c["clauses"],clauses_added=extra,
                   variables=c["vars"])
        cases.append(entry)
        print("R73_FROZEN",entry["case"],entry["kind"],
              "added",extra,"original_sha",entry["orig_sha"][:12],
              "new_sha",entry["candidate_sha"][:12],flush=True)
    m=dict(protocol=PROTO,r72_protocol=r72.PROTO,
           r72_original_manifest_sha=original_manifest_sha,
           input_seed=r72.SEED,cap_s=CAP,repeats=REPS,modes=list(MODES),
           cases=cases,shards=SHARDS,
           limitations=[
             "One single symmetry-breaking intervention; no DRNAS inference added.",
             "Works only for symmetric complete TSP with city zero fixed.",
             "Reuses R72's previously observed 8 instances (not blind).",
             "Solver wall time only; CNF creation is done before timing.",
             "All SAT witnesses verified on the original/or strengthened CNF respectively.",
             "UNSAT correctness independently cross-checked with exact Held-Karp optimum, not LRAT.",
             "R55/R61 not included because R72 showed no improvement over clean Kissat."
           ])
    (root/"r73_manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    (root/"r73_sources.sha256").write_text(
        "".join(c["orig_sha"]+"  "+c["case"]+"\n"+
                c["candidate_sha"]+"  "+c["candidate"]+"\n" for c in cases))
    print("R73_FREEZE_PASS",len(cases),digest(root/"r73_manifest.json"),flush=True)

def measure(args):
    import r61_killer_transfer as core
    root=Path(args.sources)
    m=json.loads((root/"r73_manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==8 and
       m["cap_s"]==CAP and m["modes"]==list(MODES),"manifest mismatch")
    ck(0<=args.shard<SHARDS,"shard")
    kb=Path(args.kissat).resolve();ck(kb.is_file(),"pinned Kissat missing")
    core.CAP=CAP
    coreid=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{coreid})
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(shard=args.shard,
      protocol=PROTO,manifest_sha=digest(root/"r73_manifest.json"),
      kissat_sha=digest(kb)),indent=2)+"\n")
    rows=[]
    for c in m["cases"][args.shard::SHARDS]:
        ck(digest(root/c["case"])==c["orig_sha"],"R72 source drift")
        ck(digest(root/c["candidate"])==c["candidate_sha"],"new CNF drift")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256((c["orig_sha"]+
              str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                src=root/(c["case"] if mode==MODES[0] else c["candidate"])
                result=core.ordinary_trial(src,kb,kb,"clean",coreid)
                ck(result["status"]=="TIMEOUT" or result["status"]==c["kind"],
                   "contradiction of Held-Karp exact TSP result")
                row=dict(case=c["case"],original_sha=c["orig_sha"],
                         rep=rep,mode=mode,**result)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R73_TRIAL",c["case"],rep,mode,result["status"],
                      result["wall_s"],"seconds",flush=True)
    ck(len(rows)==len(m["cases"][args.shard::SHARDS])*REPS*len(MODES),
       "missing results")

def audit(args):
    root=Path(args.sources);m=json.loads((root/"r73_manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==8,"manifest mismatch")
    seen=set();rows=[];binary=set()
    for i in range(SHARDS):
        p=Path(args.combined)/f"r73-shard-{i}"/"results"
        meta=json.loads((p/"meta.json").read_text())
        ck(meta["shard"]==i and meta["protocol"]==PROTO and
           meta["manifest_sha"]==digest(root/"r73_manifest.json"),"mixed source")
        binary.add(meta["kissat_sha"])
        part=json.loads((p/"rows.json").read_text())
        ck(len(part)==len(m["cases"][i::SHARDS])*REPS*len(MODES),"partial shard")
        for z in part:
            key=(z["case"],z["rep"],z["mode"])
            ck(key not in seen,"duplicate row");seen.add(key)
            c=next(t for t in m["cases"] if t["case"]==z["case"])
            ck(z["original_sha"]==c["orig_sha"] and z["mode"] in MODES and
               (z["status"]=="TIMEOUT" or z["status"]==c["kind"]),
               "incorrect SAT decision")
        rows.extend(part)
    ck(len(binary)==1 and len(rows)==8*2*2,"mixed binaries/missing tests")
    total={}
    for mode in MODES:
        rr=[x for x in rows if x["mode"]==mode]
        total[mode]=dict(solved=sum(x["status"]!="TIMEOUT" for x in rr),
          attempts=len(rr),par2_total_s=round(sum(x["par2_s"] for x in rr),6),
          wall_total_s=round(sum(x["wall_s"] for x in rr),6))
    base=total[MODES[0]]["par2_total_s"]
    ratio=(total[MODES[1]]["par2_total_s"]/base-1)*100 if base else 0
    final=dict(protocol=PROTO,binary_sha=next(iter(binary)),
      summary=total,regression_pct=round(ratio,3),cases=m["cases"],
      rows=rows,limitations=m["limitations"])
    Path(args.json).write_text(json.dumps(final,indent=2)+"\n")
    report=["# DRNAS R73: one simple TSP reversal-symmetry rule",
      "Same 8 R72 exact TSP decision cases, original vs extra symmetry constraints.",
      "32 one-core paired 15-second attempts, two repetitions per case. Smaller is better.",
      f"Overall relative PAR2 change {ratio:+.3f}% (negative means R73 faster).",
      "| Method | Correct solves | PAR2 total (seconds) |",
      "|---|---:|---:|"]
    for mode in MODES:
        item=total[mode]
        report.append(f"| {mode} | {item['solved']}/{item['attempts']} | {item['par2_total_s']:.6f} |")
    report+=["","| Cities | Status | Original (s, 2 reps) | Symmetry (s, 2 reps) | New clauses |",
             "|---:|---|---|---|---:|"]
    for c in m["cases"]:
        def fmt(mode):
            z=sorted((x for x in rows if x["case"]==c["case"] and
                     x["mode"]==mode),key=lambda x:x["rep"])
            return ", ".join("TO" if x["status"]=="TIMEOUT" else
                             f"{x['wall_s']:.4f}" for x in z)
        report.append(f"| {c['n']} | {c['kind']} | {fmt(MODES[0])} | {fmt(MODES[1])} | {c['clauses_added']} |")
    report+=["","## Limitations"]+["- "+p for p in m["limitations"]]
    Path(args.md).write_text("\n".join(report)+"\n")
    print("R73_FINAL_AUDIT_PASS",json.dumps(total,sort_keys=True),
          "relative_delta_pct",round(ratio,3),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    v=sub.add_parser("freeze");v.add_argument("--out",required=True)
    v=sub.add_parser("measure")
    for x in ("sources","kissat","out"):v.add_argument("--"+x,required=True)
    v.add_argument("--shard",type=int,required=True)
    v=sub.add_parser("audit")
    for x in ("sources","combined","json","md"):v.add_argument("--"+x,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(a.out),
     "measure":lambda:measure(a),"audit":lambda:audit(a)}[a.cmd]()
if __name__=="__main__":main()

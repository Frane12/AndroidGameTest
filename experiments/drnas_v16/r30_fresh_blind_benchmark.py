#!/usr/bin/env python3
"""R30 new SHA-frozen, predeclared 9-family stress test. No solver tuning after freeze.
72 different CNFs, 2 paired repetitions, 6 modes = 864 trials. Synthetic,
not an official SAT Competition corpus. Native R29/R28 source unmodified.
"""
import argparse,csv,hashlib,json,os,random,subprocess,time
from pathlib import Path
from collections import Counter
import r29_hidden_partial_benchmark as r29
import r28_exact_gf2_benchmark as prior

PROTO="DRNAS-R30-FRESH-NINE-FAMILY-BLIND-20261103-V1"
SALT="R30-DISTINCT-SHA-SEED-a4c9702e912f-20261103-NO-PREVIOUS-SOLVER-FEEDBACK"
FAMILIES=("new_hidden_xor3","new_hidden_xor6","new_hidden_mixed",
          "new_visible_partial","new_decoy","new_gauss_units",
          "independent_planted3sat","independent_pigeonhole","independent_graph3color")
N_PER=8; REPS=2; SHARDS=4; CAP=3.0
MODES=("Kissat_clean","R28_exact","R29_shadow","R29_active",
       "CryptoMiniSat_Ubuntu","CaDiCaL_Ubuntu")
r29.CAP=CAP
r29.SALT=SALT

def check(condition,message):
    if not condition:raise RuntimeError("R30_AUDIT_FAIL "+message)
def sha(data):return hashlib.sha256(data).hexdigest()
def rng_case(family,i):return random.Random(int(sha((SALT+"/"+family+"/"+str(i)).encode()),16))
def dimacs(n,clauses):return r29.write_dimacs(n,clauses)
def planted3(i):
    rng=rng_case("independent_planted3sat",i)
    n=100+(i%4)*10; truth={v:rng.getrandbits(1) for v in range(1,n+1)}
    clauses=[r29.planted_clause(rng,list(truth),truth) for _ in range(410+20*(i%3))]
    rng.shuffle(clauses);return n,clauses,"SAT"
def pigeonhole(i):
    holes=4+(i%4);pigeons=holes+1
    var=lambda p,h:1+p*holes+h
    clauses=[[var(p,h) for h in range(holes)] for p in range(pigeons)]
    for h in range(holes):
        for p in range(pigeons):
            for q in range(p+1,pigeons):
                clauses.append([-var(p,h),-var(q,h)])
    rng_case("independent_pigeonhole",i).shuffle(clauses)
    return pigeons*holes,clauses,"UNSAT"
def graphcolor(i):
    rng=rng_case("independent_graph3color",i)
    nv=24+(i%4)*3
    # Fixed hidden 3-color partition; odd instances gain a forced K4 (UNSAT).
    colors=list(range(3))*(nv//3)
    rng.shuffle(colors)
    var=lambda v,c:1+3*v+c
    clauses=[]
    for v in range(nv):
        clauses.append([var(v,c) for c in range(3)])
        for c in range(3):
            for d in range(c+1,3):clauses.append([-var(v,c),-var(v,d)])
    edges=set()
    while len(edges)<min(150,nv*(nv-1)//6):
        u,v=rng.sample(range(nv),2)
        if colors[u]==colors[v]:continue
        edges.add(tuple(sorted((u,v))))
    if i%2:
        for u in range(4):
            for v in range(u+1,4):edges.add((u,v))
    for u,v in sorted(edges):
        for c in range(3):clauses.append([-var(u,c),-var(v,c)])
    rng.shuffle(clauses)
    return 3*nv,clauses,("UNSAT" if i%2 else "SAT")
def make_case(family,i):
    mapping={"new_hidden_xor3":"hidden_xor3","new_hidden_xor6":"hidden_xor6",
             "new_hidden_mixed":"hidden_mixed","new_visible_partial":"visible_partial",
             "new_decoy":"split_near_xor_decoy"}
    if family in mapping:return r29.regular_case(mapping[family],i+1001)
    if family=="new_gauss_units":return r29.gaussian_unit_case(i+1001)
    if family=="independent_planted3sat":return planted3(i)
    if family=="independent_pigeonhole":return pigeonhole(i)
    if family=="independent_graph3color":return graphcolor(i)
    raise ValueError(family)

def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for i in range(N_PER):
            n,clauses,expected=make_case(family,i)
            raw=dimacs(n,clauses)
            name=family+"_"+f"{i:02d}"+".cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              n=n,m=len(clauses),sha256=sha(raw)))
    check(len(cases)==72 and len({c["sha256"] for c in cases})==72,"Duplicate formula")
    manifest=dict(protocol=PROTO,salt=SALT,cases=cases,modes=MODES,reps=REPS,
                  shards=SHARDS,cap_s=CAP,
                  provenance="72 unseen generated CNFs, with frozen R29/R28 algorithm",
                  limitations=["Synthetic fresh seeds, not real external SAT2026 problems",
                               "First 6 families reuse R29 distribution with unseen seeds",
                               "Last 3 families have independently constructed CNFs",
                               "No tuning on this locked cohort",
                               "3 s single-core limit; penalty 6s per timed-out attempt"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R30_FROZEN",len(cases),sha((out/"manifest.json").read_bytes()),flush=True)

def external_run(mode,binaries,path,clauses,case):
    cmd=[str(binaries["cms" if mode=="CryptoMiniSat_Ubuntu" else "cadical"]),str(path)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=CAP)
        sec=time.monotonic()-start
        if p.returncode==10 or "s SATISFIABLE" in p.stdout:status="SAT"
        elif p.returncode==20 or "s UNSATISFIABLE" in p.stdout:status="UNSAT"
        else:raise RuntimeError(mode+" bad exit "+str(p.returncode)+" "+p.stderr[-350:])
        check(status==case["expected"],mode+" incorrect answer "+case["name"])
        if status=="SAT":
            has_model=any(line.startswith("v ") for line in p.stdout.splitlines())
            if has_model:check(prior.check_sat_model(p.stdout,case["n"],clauses),
                               mode+" invalid SAT model "+case["name"])
            certificate="SAT_model_checked" if has_model else "SAT_without_model"
        else:certificate="UNSAT_solver_only"
    except subprocess.TimeoutExpired:
        sec=time.monotonic()-start;status="TIMEOUT";certificate="not_applicable"
    return dict(status=status,seconds=round(sec,6),par2=6.0 if status=="TIMEOUT" else round(sec,6),
                route=mode,certificate=certificate,cert_size=0)

def measure(a):
    root=Path(a.inputs); manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and manifest["modes"]==list(MODES),"Protocol mismatch")
    check(manifest["cap_s"]==CAP and manifest["reps"]==REPS,"Unfrozen cap")
    check(0<=a.shard<SHARDS,"Bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={k:Path(getattr(a,k)).resolve() for k in ("kissat","r28","r29","cms","cadical")}
    check(all(p.is_file() for p in binaries.values()),"Missing binary")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=a.shard,manifest_sha256=sha((root/"manifest.json").read_bytes()),
              binary_sha256={k:sha(v.read_bytes()) for k,v in binaries.items()})
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        path=(root/case["name"]).resolve()
        check(sha(path.read_bytes())==case["sha256"],"Formula hash mismatch")
        n,clauses=prior.load_clauses(path)
        check(n==case["n"] and len(clauses)==case["m"],"CNF header mismatch")
        for repeat in range(REPS):
            order=list(MODES)
            random.Random(int(sha(("R30-ORDER/"+case["sha256"]+"/"+str(repeat)).encode()),16)).shuffle(order)
            for mode in order:
                if mode in r29.MODES:
                    result=r29.run_one(mode,binaries,path,clauses,case)
                else:result=external_run(mode,binaries,path,clauses,case)
                rows.append(dict(formula=case["name"],family=case["family"],repeat=repeat,mode=mode,**result))
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R30_TRIAL",a.shard,case["name"],repeat,mode,result["status"],
                      result["seconds"],result["route"],flush=True)
        answer={r["status"] for r in rows if r["formula"]==case["name"]}-{"TIMEOUT"}
        check(len(answer)<=1,"Solver contradiction "+case["name"])
    print("R30_SHARD_DONE",a.shard,len(rows),flush=True)

def aggregate(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    digest=sha((root/"manifest.json").read_bytes())
    rows=[];binary_sets=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r30-shard-{shard}"/"results"
        metadata=json.loads((folder/"metadata.json").read_text())
        check(metadata["shard"]==shard and metadata["manifest_sha256"]==digest,
              "Shard provenance mismatch")
        binary_sets.add(json.dumps(metadata["binary_sha256"],sort_keys=True))
        part=json.loads((folder/"rows.json").read_text())
        check(len(part)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "Incomplete shard "+str(shard))
        rows.extend(part)
    check(len(rows)==72*2*6 and len(binary_sets)==1,"Incomplete 864 attempts / binaries drift")
    summary={}
    for family in ("ALL",)+FAMILIES:
        group={}
        for mode in MODES:
            subset=[x for x in rows if x["mode"]==mode and
                    (family=="ALL" or x["family"]==family)]
            cands=[c for c in manifest["cases"] if family=="ALL" or c["family"]==family]
            solved=sum(all(r["status"]!="TIMEOUT" for r in subset if r["formula"]==c["name"]) for c in cands)
            group[mode]=dict(solved=solved,total=len(cands),
                             par2_sum=round(sum(r["par2"] for r in subset),6),
                             timeouts=sum(r["status"]=="TIMEOUT" for r in subset),
                             checked_sat=sum(r["certificate"]=="SAT_witness_checked" or
                                             r["certificate"]=="SAT_model_checked" for r in subset),
                             independent_proofs=sum(r["certificate"] in
                                ("xor_unsat_resolve_verified","gf2_derived_units_verified") for r in subset))
        summary[family]=group
        print("R30_SUMMARY",family,json.dumps(group,sort_keys=True),flush=True)
    result=dict(protocol=PROTO,manifest_sha256=digest,
                binary_sha256=json.loads(next(iter(binary_sets))),summary=summary,rows=rows,
                limitations=manifest["limitations"])
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    md=["# DRNAS R30 blinded fresh nine-family comparison",
        "72 SHA-locked synthetic CNFs, 9 families x 8, 2 repeats x 6 solvers = 864 runs.",
        "3s cap, PAR-2 timeout penalty 6s, smaller better. Same inputs and CPU core pinning.",
        "**Not an official world leaderboard. Unseen seeds but six generators inherited from R29.**","",
        "| Family | Kissat | R28 | R29 shadow | R29 active | CryptoMiniSat | CaDiCaL |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for fam,d in summary.items():
        md.append("| "+fam+" | "+" | ".join(f"{d[m]['par2_sum']:.4f}" for m in MODES)+" |")
    md+=["","The reported sums cover two attempts; timeout counts add a PAR-2 penalty.",
          "Raw per-formula times and certificates are in results.json and results.csv."]
    Path(a.report).write_text("\n".join(md)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print("R30_AUDIT_PASS",len(rows),len(manifest["cases"]),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    v=sub.add_parser("prepare");v.add_argument("--outdir",required=True)
    v=sub.add_parser("measure")
    for x in ("inputs","kissat","r28","r29","cms","cadical","outdir"):v.add_argument("--"+x,required=True)
    v.add_argument("--shard",type=int,required=True)
    v=sub.add_parser("aggregate")
    for x in ("inputs","combined","output","report","csv"):v.add_argument("--"+x,required=True)
    a=p.parse_args()
    if a.cmd=="prepare":prepare(a.outdir)
    elif a.cmd=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()

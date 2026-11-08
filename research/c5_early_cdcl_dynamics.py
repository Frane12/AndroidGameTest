#!/usr/bin/env python3
"""C5: frozen native CMS, dedup and exact-duplicate-tail early CDCL dynamics.
Development-only mechanistic experiment. Three independent fresh processes
at 100, 1000, 5000 conflicts; these are NOT a continuation of one solver.
A bounded solve is never counted as a full end-to-end SAT/UNSAT benchmark.
"""
import argparse,collections,hashlib,json,os,pathlib,re,subprocess,time
import c4_duplicate_order_causal as c4
import r195_native_cms_benchmark as cms
OUT=pathlib.Path("c5_out")
PROTO="DRNAS-C5-4KNOWN-SHA-3MODES-3SEEDS-3BOUNDED-CHECKPOINTS-v1"
BUDGETS=(100,1000,5000)
MODES=("cpp_native","cpp_dedup","cpp_tail")
REPS=3
def need(x,m):
    if not x:raise RuntimeError("C5_FAIL_CLOSED "+str(m))
def run(item,rep,mode,budget):
    need(rep in range(REPS) and mode in MODES and budget in BUDGETS,"unregistered attempt")
    need(hashlib.sha256(item["path"].read_bytes()).hexdigest()==item["sha256"],"SHA drift")
    binary="c4/bin/native" if mode=="cpp_tail" else "c2/bin/native"
    need(pathlib.Path(binary).is_file(),"missing pinned native binary")
    seed=c4.seed(item,rep)
    env=os.environ.copy()
    env["DRNAS_MAX_CONFLICTS"]=str(budget)
    t=time.perf_counter()
    p=subprocess.run([str(pathlib.Path(binary).resolve()),str(item["path"].resolve()),
                      mode,str(seed)],env=env,capture_output=True,text=True,
                     errors="replace",timeout=40,check=False)
    wall=time.perf_counter()-t
    need(p.returncode==0,"solver failed: "+p.stderr[-1000:])
    m=re.search(r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=(\d+) derived_rows=(\d+)$",p.stdout,re.M)
    need(m is not None,"missing bounded solver stats")
    status=m[1]
    need(status in ("SAT","BUDGET"),"unexpected terminal status on known SAT original: "+status)
    model={}
    for line in p.stdout.splitlines():
        if line.startswith("v "):
            for v in map(int,line[2:].split()):
                if v:need(abs(v) not in model or model[abs(v)]==(v>0),"conflicting model");model[abs(v)]=v>0
    if status=="SAT":cms.verify_model(item["path"],model)
    else:need(not model,"bounded result fabricated SAT model")
    g=c4.gate_native(p.stdout,mode)
    if mode=="cpp_tail":
        need(g["certificate"]=="original_CNF_exact_clause_permutation","tail certificate")
    if mode=="cpp_dedup":
        need(g["certificate"]=="original_CNF_clause_identity","dedup certificate")
    return dict(protocol=PROTO,gbd=item["gbd"],source_sha256=item["sha256"],
        mode=mode,rep=rep,seed=seed,conflict_budget=budget,status=status,
        bounded_only=True,original_SAT_witness_verified=(status=="SAT"),
        conflicts=int(m[2]),decisions=int(m[3]),propagations=int(m[4]),
        decisions_per_conflict=round(int(m[3])/max(1,int(m[2])),6),
        propagations_per_conflict=round(int(m[4])/max(1,int(m[2])),6),
        elapsed_s=round(wall,6),gate_s=g["native_gate_s"],
        source_duplicate_removed=g["duplicate_clauses_removed"],
        source_duplicate_moved=g.get("duplicate_clauses_moved",0),
        source_sha_unchanged=True,build_sha=os.environ.get("GITHUB_SHA","local"))
def shard(i):
    cc=c4.sources()
    need(i in range(len(cc)),"source shard")
    OUT.mkdir(exist_ok=True)
    rows=[]
    for rep in range(REPS):
        for mode in MODES:
            for cap in BUDGETS:
                row=run(cc[i],rep,mode,cap)
                rows.append(row)
                (OUT/f"shard-{i}.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
                print("C5_EARLY",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==27,"partial shard")
    print("C5_SHARD_PASS",i,len(rows),flush=True)
def audit():
    sources=c4.sources()
    bysha={c["sha256"]:c for c in sources}
    rows=[]
    for i in range(4):
        path=OUT/f"shard-{i}.json"
        need(path.is_file(),"missing shard")
        part=json.loads(path.read_text())
        need(len(part)==27,"incomplete shard")
        rows+=part
    need(len(rows)==108,"not 108 bounded trials")
    seen=set()
    for x in rows:
        need(x["protocol"]==PROTO and x["bounded_only"] and x["source_sha_unchanged"],"protocol mismatch")
        src=bysha.get(x["source_sha256"])
        need(src and src["gbd"]==x["gbd"],"source mismatch")
        need(x["seed"]==c4.seed(src,x["rep"]),"seed mismatch")
        need(x["mode"] in MODES and x["rep"] in range(REPS) and x["conflict_budget"] in BUDGETS,"unknown cell")
        need(x["status"] in ("SAT","BUDGET"),"invalid bounded status")
        need(x["status"]!="SAT" or x["original_SAT_witness_verified"],"unverified model")
        need(x["conflicts"]>=0 and x["decisions"]>=0 and x["propagations"]>=0,"invalid counters")
        key=(x["source_sha256"],x["rep"],x["mode"],x["conflict_budget"])
        need(key not in seen,"duplicate attempt");seen.add(key)
    need(len(seen)==108,"not complete factorial")
    summary={}
    for cap in BUDGETS:
        bymode={}
        for mode in MODES:
            subset=[x for x in rows if x["conflict_budget"]==cap and x["mode"]==mode]
            bymode[mode]=dict(attempts=len(subset),
                early_sat=sum(x["status"]=="SAT" for x in subset),
                bounded=sum(x["status"]=="BUDGET" for x in subset),
                conflicts=sum(x["conflicts"] for x in subset),
                decisions=sum(x["decisions"] for x in subset),
                propagations=sum(x["propagations"] for x in subset),
                wall_s=round(sum(x["elapsed_s"] for x in subset),6),
                gate_s=round(sum(x["gate_s"] for x in subset),6))
        summary[str(cap)]=bymode
    output=dict(protocol=PROTO,cohort="four known C2/C3 cases; development only",
       n=108,sha=[c["sha256"] for c in sources],caps=BUDGETS,
       full_solver_PAR2_measured=False,independent_UNSAT_proof=False,
       bounded_results_are_not_full_solves=True,
       interpretation="independent restarts at fixed conflict budgets, NOT sequential continuation",
       summary=summary)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("C5_FINAL",json.dumps(output,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    shard(a.shard) if a.action=="shard" else audit()

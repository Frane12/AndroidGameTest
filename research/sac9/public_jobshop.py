#!/usr/bin/env python3
"""Source-pinned public Lawrence LA01/LA02 four-job DERIVED stress cases.
Not full original benchmarks and not an untouched blind benchmark.
No result label or job-shop metadata is passed to SAC9; only identical CNF.
"""
import argparse,collections,hashlib,json,math,os,subprocess,time
from pathlib import Path

SOURCES = {"la01":"de4b9841eb38c18e3f65287fdf73ebccd75a99f9",
           "la02":"f37607c178e8f6733dee34d1a4e125d9cb4c8e03"}

def parse_source(raw,name):
    sha=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
    if sha!=SOURCES[name]:raise ValueError("public Git blob SHA mismatch")
    lines=[x.strip() for x in raw.decode('ascii').splitlines() if x.strip() and not x.startswith('#')]
    n,m=map(int,lines[0].split())
    assert n==10 and m==5 and len(lines)==n+1
    jobs=[]
    for row in lines[1:]:
        xs=list(map(int,row.split()))
        assert len(xs)==2*m
        job=[(xs[i],xs[i+1]) for i in range(0,2*m,2)]
        assert sorted(x for x,d in job)==list(range(m)) and all(d>0 for x,d in job)
        jobs.append(job)
    return jobs[:4],sha

def encode(jobs,h):
    ops=[];jobseq=[];by_machine=collections.defaultdict(list)
    for j,job in enumerate(jobs):
        consumed=0; total=sum(d for _,d in job);seq=[]
        for machine,dur in job:
            earliest=consumed;latest=h-(total-consumed)
            if latest<earliest:raise ValueError("horizon precedes longest job")
            op={"idx":len(ops),"m":machine,"d":dur,"min":earliest,"max":latest}
            ops.append(op);seq.append(op);by_machine[machine].append(op)
            consumed+=dur
        jobseq.append(seq)
    count=0;clauses=[];selectors={}
    def new():
        nonlocal count
        count+=1;return count
    def add(*cl):clauses.append(tuple(cl))
    for op in ops:
        dom=[(t,new()) for t in range(op["min"],op["max"]+1)]
        selectors[op["idx"]]=dom
        xs=[v for t,v in dom];add(*xs)
        if len(xs)>1:
            prev=new();add(-xs[0],prev)
            for v in xs[1:-1]:
                aux=new();add(-v,aux);add(-prev,aux);add(-v,-prev);prev=aux
            add(-xs[-1],-prev)
    for seq in jobseq:
        for a,b in zip(seq,seq[1:]):
            for ta,va in selectors[a["idx"]]:
                for tb,vb in selectors[b["idx"]]:
                    if tb<ta+a["d"]:add(-va,-vb)
    for machine,seq in by_machine.items():
        for idx,a in enumerate(seq):
            for b in seq[idx+1:]:
                for ta,va in selectors[a["idx"]]:
                    for tb,vb in selectors[b["idx"]]:
                        if ta<tb+b["d"] and tb<ta+a["d"]:add(-va,-vb)
    return ops,jobseq,by_machine,count,clauses

def structured(ops,jobseq,by_machine,budget):
    from ortools.sat.python import cp_model
    tick=time.perf_counter();m=cp_model.CpModel();start={};by=collections.defaultdict(list)
    for o in ops:
        s=m.NewIntVar(o["min"],o["max"],"start_"+str(o["idx"]))
        start[o["idx"]]=s
        by[o["m"]].append(m.NewFixedSizeIntervalVar(s,o["d"],"itv_"+str(o["idx"])))
    for z in by.values():m.AddNoOverlap(z)
    for seq in jobseq:
        for a,b in zip(seq,seq[1:]):m.Add(start[a["idx"]]+a["d"]<=start[b["idx"]])
    construction=time.perf_counter()-tick
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=budget
    solver.parameters.num_search_workers=1
    rc=solver.Solve(m)
    return dict(status=solver.StatusName(rc),e2e_s=round(time.perf_counter()-tick,6),
                model_build_s=round(construction,6),branches=solver.NumBranches())

def raw_cpsat(nv,clauses,budget):
    from ortools.sat.python import cp_model
    if len(clauses)>400000:return {"status":"SKIPPED_RAW_BUILD_GATE","clauses":len(clauses)}
    tick=time.perf_counter();m=cp_model.CpModel()
    x=[None]+[m.NewBoolVar("x"+str(i)) for i in range(1,nv+1)]
    for cl in clauses:m.AddBoolOr([x[v] if v>0 else x[-v].Not() for v in cl])
    construction=time.perf_counter()-tick
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=budget
    solver.parameters.num_search_workers=1
    rc=solver.Solve(m)
    return dict(status=solver.StatusName(rc),e2e_s=round(time.perf_counter()-tick,6),
                model_build_s=round(construction,6),branches=solver.NumBranches())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--name',required=True,choices=list(SOURCES))
    p.add_argument('--multiplier',required=True,type=float,choices=[1.08,1.25])
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--drat-trim',required=True,type=Path)
    p.add_argument('--cdcl',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--limit',type=float,default=8.0)
    args=p.parse_args()
    try:os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    except (AttributeError,OSError):pass
    output=args.out;output.mkdir(parents=True,exist_ok=True)
    jobs,sha=parse_source(args.source.read_bytes(),args.name)
    loads=[sum(d for m,d in job) for job in jobs]
    for machine in range(5):loads.append(sum(d for job in jobs for m,d in job if m==machine))
    h=math.ceil(max(loads)*args.multiplier)
    started=time.perf_counter()
    ops,jobseq,bymachine,nv,clauses=encode(jobs,h)
    cnf=output/'original.cnf'
    with cnf.open('w') as f:
        f.write(f'p cnf {nv} {len(clauses)}\n')
        for cl in clauses:f.write(' '.join(map(str,cl))+' 0\n')
    pre=time.perf_counter()-started
    result={"source":args.name,"source_blob_sha":sha,"derived_first_jobs":4,
            "horizon":h,"multiplier":args.multiplier,"vars":nv,"clauses":len(clauses),
            "cnf_sha256":hashlib.sha256(cnf.read_bytes()).hexdigest(),
            "encoding_s":round(pre,6),"arms":{}}
    if len(clauses)>1200000:
        result["status"]="MODEL_TOO_LARGE"
    else:
        for mode in ("sac9","cdcl"):
            t=time.perf_counter()
            if mode=="sac9":
                proof=output/'candidate.drat';report=output/'sac9.json'
                cmd=[str(args.binary.resolve()),'--cnf',str(cnf),'--drat',str(proof),
                    '--report',str(report),'--seconds',str(args.limit),'--cap','6000']
            else:cmd=[str(args.cdcl.resolve()),str(cnf),'--mode','core','--time',str(args.limit)]
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=args.limit+14)
            e2e=time.perf_counter()-t
            (output/(mode+'.log')).write_text(proc.stdout+'\n'+proc.stderr)
            if mode=="sac9":
                s=json.loads(report.read_text());status=s['status']
                recorded=dict(status=status,e2e_s=round(e2e,6),checks=s['checks'],
                              nested_support_pairs=s['nested_support_pairs'])
                if status=="EMITTED_UNCHECKED":
                    tick=time.perf_counter()
                    q=subprocess.run([str(args.drat_trim.resolve()),str(cnf),str(proof),'-U','-t','20'],
                         capture_output=True,text=True,timeout=30)
                    (output/'checker.log').write_text(q.stdout+'\n'+q.stderr)
                    accepted=q.returncode==0 and 's VERIFIED' in q.stdout
                    recorded.update(accepted=accepted,checker_s=round(time.perf_counter()-tick,6))
                    if not accepted:raise RuntimeError('Unverified native UNSAT candidate')
                result['arms'][mode]=recorded
            else:result['arms'][mode]={"status":{10:"SAT",20:"UNSAT",0:"UNKNOWN"}.get(proc.returncode,"ERROR"),"e2e_s":round(e2e,6)}
        result['arms']['structured']=structured(ops,jobseq,bymachine,args.limit)
        result['arms']['raw_cpsat']=raw_cpsat(nv,clauses,args.limit)
        known=[]
        for name,arm in result['arms'].items():
            got=arm['status']
            if got in ("OPTIMAL","FEASIBLE","SAT"):known.append((name,"SAT"))
            elif got in ("INFEASIBLE","UNSAT") or (name=="sac9" and got=="EMITTED_UNCHECKED" and arm.get("accepted")):
                known.append((name,"UNSAT"))
        if len(set(x[1] for x in known))>1:raise RuntimeError('contradictory solver statuses')
        result['oracle']=known
    (output/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('SAC9_PUBLIC '+json.dumps(result,sort_keys=True),flush=True)

if __name__=='__main__':main()

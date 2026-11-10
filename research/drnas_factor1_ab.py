#!/usr/bin/env python3
"""FACTOR1 A/B: A native CDCL full CNF; B exact separator projection.

For each candidate separator assignment, independently enumerate each
component's local variables, then join feasible projections. Complete
small-model exhaustive source truth independently verifies SAT/UNSAT.
This is a proof-of-concept, NOT an LRAT generator or scalable factor solver.
"""
import itertools,json,pathlib,random,subprocess,time,collections,math,re
OUT=pathlib.Path("mre_factor1");OUT.mkdir(exist_ok=True)
BIN=OUT/"bin/drnas_sre2c"
def normalized(clauses):
    return sorted(set(tuple(sorted(set(c),key=lambda x:(abs(x),x))) for c in clauses))
def exact(clauses,n):
    for bits in range(1<<n):
        if all(any(bool(bits&(1<<(abs(l)-1)))==(l>0) for l in c) for c in clauses):
            return {v:bool(bits&(1<<(v-1))) for v in range(1,n+1)}
    return None
def dimacs(clauses,n):
    return f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)
def case(seed):
    rng=random.Random(20261110+seed)
    k=1+seed%4
    ncomp=2+seed%3
    size=2+seed%2
    sep=list(range(1,k+1));nextv=k+1
    components=[];clauses=[]
    for ci in range(ncomp):
        local=list(range(nextv,nextv+size));nextv+=size
        # Each local component has a constraint on its first separator bit:
        # (s OR x), (s OR -x) force s=true; negated analog force s=false.
        bit=sep[ci%k]
        sign=(1 if (seed+ci)%5 else -1)
        if seed%7==0 and ci==ncomp-1:sign=-1
        clauses.extend([[sign*bit,local[0]],[sign*bit,-local[0]]])
        # Add nontrivial local SAT structure without cross-component edges.
        for j in range(size-1):
            clauses.append([-local[j],local[j+1]])
        if ci%2:clauses.append([local[-1],-local[0]])
        components.append(local)
    # A handful of cases add a contradiction across component projections.
    if seed%6==1 and ncomp>=2:
        bit=sep[0]
        other=components[-1][0]
        clauses.extend([[-bit,other],[-bit,-other]])
    return nextv-1,normalized(clauses),sep,components
def decompose(clauses,n,sep):
    ss=set(sep);parent={v:v for v in range(1,n+1) if v not in ss}
    def find(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]];v=parent[v]
        return v
    def union(a,b):
        a=find(a);b=find(b)
        if a!=b:parent[b]=a
    for clause in clauses:
        vs=[abs(x) for x in clause if abs(x) not in ss]
        for v in vs[1:]:union(vs[0],v)
    groups=collections.defaultdict(list)
    for v in parent:groups[find(v)].append(v)
    comp=[sorted(v) for v in groups.values()]
    comp.sort(key=lambda c:c[0])
    assigned={v:i for i,c in enumerate(comp) for v in c}
    clauses_by=[[] for _ in comp];separator_only=[]
    for clause in clauses:
        ids={assigned[abs(l)] for l in clause if abs(l) not in ss}
        if len(ids)>1:raise RuntimeError("invalid decomposition cross-component clause")
        if not ids:separator_only.append(clause)
        else:clauses_by[ids.pop()].append(clause)
    return comp,clauses_by,separator_only
def projected(clauses,n,sep,cap_assignments=16):
    started=time.perf_counter()
    comp,by,sep_only=decompose(clauses,n,sep)
    if len(sep)>4 or any(len(c)>7 for c in comp):
        return None,dict(abstain=True,reason="projection_budget")
    checks=0;rejected=0;model=None;projection=[]
    for bits in itertools.product((False,True),repeat=len(sep)):
        fixed=dict(zip(sep,bits))
        def valid(c,assign):
            return all(any(assign[abs(l)]==(l>0) for l in clause) for clause in c)
        if not valid(sep_only,fixed):
            rejected+=1;continue
        local_models=[]
        for vars_,cls in zip(comp,by):
            found=None
            for assignment in itertools.product((False,True),repeat=len(vars_)):
                checks+=1
                trial={**fixed,**dict(zip(vars_,assignment))}
                if valid(cls,trial):
                    found=dict(zip(vars_,assignment));break
            if found is None:break
            local_models.append(found)
        else:
            projection.append(list(bits))
            if model is None:
                model=dict(fixed)
                for part in local_models:model.update(part)
        if len(projection)==0 and model is None:rejected+=1
    elapsed=time.perf_counter()-started
    return model,dict(abstain=False,separator_size=len(sep),
        components=len(comp),largest_component=max(map(len,comp),default=0),
        separator_assignments=2**len(sep),rejected_separator_assignments=rejected,
        feasible_separator_assignments=len(projection),
        local_assignment_checks=checks,projection_s=elapsed,
        feasible_projection=projection)
def native(path):
    started=time.perf_counter()
    p=subprocess.run([str(BIN.resolve()),str(path.resolve()),"--mode","plain",
        "--time","2"],capture_output=True,text=True,timeout=5)
    wall=time.perf_counter()-started
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr)
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    line=re.search(r"^SRE2C_TRIAL (.*)$",p.stdout,re.M)
    if not line:raise RuntimeError(p.stdout)
    fields=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
    model=None
    if status=="SAT":
        lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ")
              for x in l[2:].split() if x!="0"]
        model={abs(l):l>0 for l in lits}
    return status,wall,fields,model
def main():
    rows=[];cases=[]
    for seed in range(24):
        n,cls,sep,parts=case(seed)
        # Verify source truth independently of both arms.
        truth=exact(cls,n)
        if truth is None and seed%3==0:
            pass
        path=OUT/f"factor_{seed:02}.cnf";path.write_text(dimacs(cls,n))
        cases.append((seed,n,cls,sep,path,truth))
    for seed,n,cls,sep,path,truth in cases:
        expected="SAT" if truth is not None else "UNSAT"
        for rep in range(3):
            status,wall,stats,model=native(path)
            if status!=expected:raise RuntimeError(f"native wrong {seed}")
            if model is not None and not all(any(model[abs(l)]==(l>0) for l in c) for c in cls):
                raise RuntimeError("native original witness invalid")
            rows.append(dict(seed=seed,arm="A_native",rep=rep,status=status,
                E2E_s=round(wall,7),decisions=int(stats["decisions"]),
                conflicts=int(stats["conflicts"]),separator_size=len(sep)))
            started=time.perf_counter()
            factor_model,telemetry=projected(cls,n,sep)
            elapsed=time.perf_counter()-started
            if telemetry["abstain"]:raise RuntimeError("unexpected abstention")
            factor_status="SAT" if factor_model is not None else "UNSAT"
            if factor_status!=expected:raise RuntimeError(f"factor incorrect {seed}")
            if factor_model is not None and not all(any(factor_model[abs(l)]==(l>0) for l in c) for c in cls):
                raise RuntimeError("factor original witness invalid")
            rows.append(dict(seed=seed,arm="B_factor",rep=rep,status=factor_status,
                E2E_s=round(elapsed,7),decisions=0,conflicts=0,
                separator_size=len(sep),telemetry=telemetry))
            print("FACTOR1_TRIAL "+json.dumps(rows[-2],sort_keys=True),flush=True)
            print("FACTOR1_TRIAL "+json.dumps(rows[-1],sort_keys=True),flush=True)
    summary={}
    for arm in ("A_native","B_factor"):
        subset=[x for x in rows if x["arm"]==arm]
        summary[arm]=dict(solved=len(subset),PAR2_s=round(sum(x["E2E_s"] for x in subset),6),
            median_s=round(sorted(x["E2E_s"] for x in subset)[len(subset)//2],7))
    by_separator={}
    for k in range(1,5):
        by_separator[k]={arm:round(sum(x["E2E_s"] for x in rows if x["arm"]==arm and x["separator_size"]==k),6)
            for arm in ("A_native","B_factor")}
    result=dict(protocol="FACTOR1-24-SYNTHETIC-2-ARMS-3-REPS-ONECPU",
        sources=24,trials=len(rows),synthetic_nonblind=True,
        independent_exhaustive_truth=True,original_SAT_witness_verified=True,
        original_UNSAT_independent_LRAT=False,
        factor_B_is_Python_exhaustive_projection_not_native_CDCL=True,
        source_separator_supplied=True,
        summary=summary,by_separator=by_separator,rows=rows)
    (OUT/"audit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("FACTOR1_FINAL "+json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":main()

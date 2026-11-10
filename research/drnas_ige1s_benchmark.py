#!/usr/bin/env python3
"""DRNAS IGE1-S structural feedback, proof-first development pilot.

Paired original/UP-certified failed-literal reduction and unchanged source.
Do not use exhaustive truth to choose reductions: exhaustive enumeration is
ONLY an independent post-hoc verification for small development CNFs.
"""
import collections,itertools,json,math,pathlib,random,re,subprocess,time

OUT=pathlib.Path("mre_ige1s")
BIN=OUT/"bin/drnas_sre2c"

def normalize(cnf):
    result=[]
    for clause in cnf:
        c=sorted(set(clause),key=lambda x:(abs(x),x))
        if any(-x in c for x in c):continue
        result.append(tuple(c))
    return sorted(set(result))

def unit_propagate(clauses, assumptions=()):
    assignment={}
    queue=list(assumptions)
    while True:
        while queue:
            lit=queue.pop()
            var=abs(lit);val=lit>0
            if var in assignment:
                if assignment[var]!=val:return None
                continue
            assignment[var]=val
        changed=False
        for c in clauses:
            if any(assignment.get(abs(l))==(l>0) for l in c):continue
            unknown=[l for l in c if abs(l) not in assignment]
            if not unknown:return None
            if len(unknown)==1:
                queue.append(unknown[0]);changed=True
        if not changed:return assignment

def failed_literal_reduction(clauses,n,probe_cap=32):
    """F+lit UP contradiction proves F entails -lit. Add ONLY entailed units."""
    derived=[];probes=0;started=time.perf_counter()
    current=list(clauses)
    for v in range(1,n+1):
        if probes+2>probe_cap:break
        for lit in (v,-v):
            probes+=1
            if unit_propagate(current,(lit,)) is None:
                forced=-lit
                current.append((forced,))
                derived.append(forced)
                break
    return normalize(current),dict(probes=probes,derived=derived,
        reduction_s=time.perf_counter()-started)

def structure(clauses,n):
    # Primal graph: variables adjacent when appearing together in a clause.
    graph=[set() for _ in range(n+1)]
    for clause in clauses:
        variables=sorted(set(abs(l) for l in clause))
        for i,a in enumerate(variables):
            for b in variables[i+1:]:
                graph[a].add(b);graph[b].add(a)
    visited=set();components=[]
    for v in range(1,n+1):
        if v in visited:continue
        stack=[v];visited.add(v);comp=[]
        while stack:
            a=stack.pop();comp.append(a)
            for b in graph[a]-visited:
                visited.add(b);stack.append(b)
        components.append(comp)
    # Deterministic min-degree elimination as an upper bound on treewidth.
    remaining={v:set(graph[v]) for v in range(1,n+1)}
    width=0;fill=0
    while remaining:
        v=min(remaining,key=lambda x:(len(remaining[x]),x))
        neighbors=list(remaining[v]);width=max(width,len(neighbors))
        for i,a in enumerate(neighbors):
            for b in neighbors[i+1:]:
                if b not in remaining[a]:
                    remaining[a].add(b);remaining[b].add(a);fill+=1
        for a in neighbors:remaining[a].discard(v)
        del remaining[v]
    return dict(vars=n,clauses=len(clauses),
        edges=sum(map(len,graph))//2,components=len(components),
        max_component=max(map(len,components),default=0),
        min_degree_width_upper=width,fill_edges=fill)

def simplify(clauses,units,n):
    assigned={abs(l):l>0 for l in units}
    simplified=[]
    for clause in clauses:
        if any(assigned.get(abs(l))==(l>0) for l in clause):continue
        rest=tuple(l for l in clause if abs(l) not in assigned)
        simplified.append(rest)
    # Preserve variable indices for native original model validation.
    return normalize(simplified),assigned

def exact_truth(clauses,n):
    assert n<=15
    for bits in range(1<<n):
        if all(any(((bits>>(abs(l)-1))&1)==(l>0) for l in c) for c in clauses):
            return True
    return False

def dimacs(clauses,n):
    return "p cnf %d %d\n"%(n,len(clauses))+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)

def family_cases():
    cases=[]
    for seed in range(4):
        rng=random.Random(seed+20261110)
        # Deliberately small, varying source families. A unit-propagation
        # failed-literal motif: (a or b)&(!a or c)&(!b or c)&(!c or d).
        clauses=[[1,2],[-1,3],[-2,3],[-3,4]]
        for i in range(5,9):clauses.extend([[-(i-1),i]])
        if seed%2:clauses.append([-8])
        cases.append(("implication",seed,8,clauses))
        # Small parity chains; exact CNF encodes XOR3.
        xor=[]
        for a,b,c,rhs in [(1,2,3,seed%2),(3,4,5,1),(5,6,7,0)]:
            for bits in range(8):
                if bits.bit_count()%2!=rhs:
                    xor.append([(-a if bits&1 else a),(-b if bits&2 else b),(-c if bits&4 else c)])
        xor.extend([[1],[-2]])
        if seed%2:xor.append([7])
        cases.append(("xor",seed,7,xor))
        # Graph-coloring exact-one and conflicting same-color assignments.
        nverts=4+seed%2;colors=3;graph=[]
        for v in range(nverts):
            x=[3*v+i+1 for i in range(3)]
            graph.append(x)
        cl=[]
        for x in graph:
            cl.append(x)
            cl.extend([[-a,-b] for a,b in itertools.combinations(x,2)])
        edges=[(0,1),(1,2),(2,3)]
        if seed%2:edges.extend([(0,2),(0,3),(1,3)])
        for a,b in edges:
            for k in range(colors):cl.append([-graph[a][k],-graph[b][k]])
        cases.append(("coloring",seed,3*nverts,cl))
        # Independent components: mixed small implications, with optional link.
        mixed=[[1,2],[-1,3],[-2,3],[4,5],[-4,6],[-5,6],
               [7,8],[-7,9],[-8,9]]
        if seed%2:mixed.extend([[-3,4],[-6,7]])
        if seed==3:mixed.append([-9])
        cases.append(("components",seed,9,mixed))
    return cases

def run_native(path,mode,cap=1.5):
    started=time.perf_counter()
    p=subprocess.run([str(BIN.resolve()),str(path.resolve()),"--mode",mode,
                      "--time",str(cap)],capture_output=True,text=True,timeout=cap+3)
    wall=time.perf_counter()-started
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr)
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    line=re.search(r"^SRE2C_TRIAL (.*)$",p.stdout,re.M)
    if not line:raise RuntimeError(p.stdout)
    telemetry=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
    return status,wall,telemetry,p.stdout

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for family,seed,n,raw in family_cases():
        clauses=normalize(raw)
        before=structure(clauses,n)
        reduced,info=failed_literal_reduction(clauses,n)
        # Derive exact simplified residual graph only after certified units.
        residual,assigned=simplify(clauses,info["derived"],n)
        after=structure(residual,n)
        truth=exact_truth(clauses,n)
        if exact_truth(reduced,n)!=truth:raise RuntimeError("bad failed-literal entailment")
        base=OUT/(f"{family}_{seed}_original.cnf")
        transformed=OUT/(f"{family}_{seed}_entailed.cnf")
        base.write_text(dimacs(clauses,n))
        transformed.write_text(dimacs(reduced,n))
        for arm,path in [("control",base),("failed_literal",transformed)]:
            for rep in range(2):
                status,wall,metrics,stdout=run_native(path,"plain")
                expected="SAT" if truth else "UNSAT"
                if status!=expected:raise RuntimeError(f"truth error {family} {seed} {arm}: {status} vs {expected}")
                if status=="SAT":
                    lits=[int(x) for l in stdout.splitlines() if l.startswith("v ")
                          for x in l[2:].split() if x!="0"]
                    model={abs(l):l>0 for l in lits}
                    if len(model)!=n or not all(any(model[abs(l)]==(l>0) for l in c) for c in clauses):
                        raise RuntimeError("original SAT witness invalid")
                row=dict(family=family,seed=seed,arm=arm,rep=rep,status=status,
                    E2E_s=round(wall+(info["reduction_s"] if arm=="failed_literal" else 0),7),
                    operation_s=round(info["reduction_s"],7) if arm=="failed_literal" else 0,
                    source_truth_exhaustively_verified=True,
                    source_shape=before,residual_shape=after,
                    entailed_units=info["derived"],probes=info["probes"],
                    conflicts=int(metrics["conflicts"]),decisions=int(metrics["decisions"]))
                rows.append(row)
                print("IGE1S_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={}
    for arm in ("control","failed_literal"):
        r=[x for x in rows if x["arm"]==arm]
        summary[arm]=dict(solved=sum(x["status"]!="UNKNOWN" for x in r),
           PAR2_s=round(sum(x["E2E_s"] for x in r),6),
           conflicts=sum(x["conflicts"] for x in r),
           decisions=sum(x["decisions"] for x in r))
    by_family={}
    for fam in sorted(set(x["family"] for x in rows)):
        by_family[fam]={arm:round(sum(x["E2E_s"] for x in rows
              if x["family"]==fam and x["arm"]==arm),6)
              for arm in ("control","failed_literal")}
    result=dict(protocol="IGE1S-16-FROZEN-SYNTHETIC-2ARMS-2REPS-ONECPU",
       sources=16,trials=len(rows),nonblind_synthetic=True,
       original_truth_independently_exhaustive=True,
       original_SAT_models_verified=True,original_UNSAT_LRAT=False,
       certified_reduction="UP failed-literal entails unit",
       no_foreign_solver=True,one_logical_cpu=True,
       summary=summary,by_family=by_family,rows=rows)
    (OUT/"audit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("IGE1S_FINAL "+json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":main()

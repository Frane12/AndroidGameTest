#!/usr/bin/env python3
"""IGE1-T: residual-variable structural gate. Frozen 8 train / 8 holdout.
Compare plain, unconditional failed-literal and source-only selective gate.
No label/truth/time leakage into gating. 1 logical CPU per native trial.
"""
import importlib.util,json,pathlib,subprocess,time,collections
spec=importlib.util.spec_from_file_location("ige","research/drnas_ige1s_benchmark.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=pathlib.Path("mre_ige1t");OUT.mkdir(exist_ok=True)
m.BIN=OUT/"bin/drnas_sre2c"
def active_structure(clauses,n):
    # Only count variables in currently unsatisfied non-unit residual clauses.
    root=m.unit_propagate(clauses)
    if root is None:return dict(active=0,components=0,max_component=0,
        edges=0,width_upper=0,root_conflict=True)
    residual=[]
    for c in clauses:
        if any(root.get(abs(l))==(l>0) for l in c):continue
        remaining=[l for l in c if abs(l) not in root]
        if remaining:residual.append(remaining)
    active=sorted({abs(l) for c in residual for l in c})
    graph={v:set() for v in active}
    for c in residual:
        vs=sorted({abs(l) for l in c})
        for i,a in enumerate(vs):
            for b in vs[i+1:]:graph[a].add(b);graph[b].add(a)
    seen=set();components=[]
    for v in active:
        if v in seen:continue
        stack=[v];seen.add(v);size=0
        while stack:
            a=stack.pop();size+=1
            for b in graph[a]-seen:seen.add(b);stack.append(b)
        components.append(size)
    rem={v:set(graph[v]) for v in active}
    width=0
    while rem:
        v=min(rem,key=lambda x:(len(rem[x]),x))
        ns=list(rem[v]);width=max(width,len(ns))
        for i,a in enumerate(ns):
            for b in ns[i+1:]:rem[a].add(b);rem[b].add(a)
        for a in ns:rem[a].discard(v)
        del rem[v]
    return dict(active=len(active),components=len(components),
        max_component=max(components,default=0),
        edges=sum(map(len,graph.values()))//2,
        width_upper=width,root_conflict=False)
def source_gate(features):
    # Prespecified, source-only: avoid failed-literal when root UP already
    # exhausted all variables or contradiction is already discovered.
    # Attempt only a single two-polarity probe when a connected active
    # component has >=3 variables and >=2 edges.
    return (not features["root_conflict"] and features["active"]>=3 and
            features["max_component"]>=3 and features["edges"]>=2)
def main():
    rows=[];examples=[]
    for family,seed,n,raw in m.family_cases():
        clauses=m.normalize(raw)
        source=m.active_structure(clauses,n) if hasattr(m,"active_structure") else active_structure(clauses,n)
        # Never use the answer or a reduction result for the gate.
        gate=source_gate(source)
        truth=m.exact_truth(clauses,n)
        src=OUT/f"{family}_{seed}_source.cnf";src.write_text(m.dimacs(clauses,n))
        transforms={}
        for arm in ("control","always","gated"):
            started=time.perf_counter()
            if arm=="control" or (arm=="gated" and not gate):
                new=clauses;meta=dict(probes=0,derived=[],reduction_s=0.)
            else:
                new,meta=m.failed_literal_reduction(clauses,n,
                    probe_cap=(2 if arm=="gated" else 32))
            overhead=time.perf_counter()-started
            # Source-only structural gate cost is measured too, including
            # the source shape scan. A shared source scan is charged to gate.
            if arm=="gated":overhead+=source["scan_s"]
            if m.exact_truth(new,n)!=truth:raise RuntimeError("unsound reduction")
            residual,assigned=m.simplify(clauses,meta["derived"],n)
            shape=active_structure(residual,n)
            target=OUT/f"{family}_{seed}_{arm}.cnf"
            target.write_text(m.dimacs(new,n))
            transforms[arm]=(target,overhead,meta,shape)
        for arm in ("control","always","gated"):
            target,overhead,meta,shape=transforms[arm]
            for rep in range(3):
                status,wall,metrics,stdout=m.run_native(target,"plain",cap=2.)
                expected="SAT" if truth else "UNSAT"
                if status!=expected:raise RuntimeError(f"truth mismatch {family}/{seed}/{arm}")
                if status=="SAT":
                    lits=[int(x) for l in stdout.splitlines() if l.startswith("v ")
                          for x in l[2:].split() if x!="0"]
                    model={abs(l):l>0 for l in lits}
                    if len(model)!=n or not all(any(model[abs(l)]==(l>0) for l in c) for c in clauses):
                        raise RuntimeError("original model invalid")
                row=dict(family=family,seed=seed,split=("train" if seed<2 else "holdout"),
                    arm=arm,rep=rep,status=status,
                    E2E_s=round(wall+overhead,7),
                    reduction_and_gate_s=round(overhead,7),
                    original_active=source["active"],
                    original_max_component=source["max_component"],
                    original_width_upper=source["width_upper"],
                    residual_active=shape["active"],
                    residual_max_component=shape["max_component"],
                    residual_width_upper=shape["width_upper"],
                    gate_selected=gate if arm=="gated" else None,
                    derived_units=len(meta["derived"]),probes=meta["probes"],
                    conflicts=int(metrics["conflicts"]),decisions=int(metrics["decisions"]))
                rows.append(row)
                print("IGE1T_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={}
    for split in ("train","holdout","all"):
        part=[r for r in rows if split=="all" or r["split"]==split]
        summary[split]={}
        for arm in ("control","always","gated"):
            sub=[r for r in part if r["arm"]==arm]
            summary[split][arm]=dict(solved=len(sub),
                PAR2_s=round(sum(r["E2E_s"] for r in sub),6),
                decisions=sum(r["decisions"] for r in sub),
                conflicts=sum(r["conflicts"] for r in sub),
                applied=sum(bool(r["gate_selected"]) for r in sub))
    audit=dict(protocol="IGE1T-16-SOURCES-3-ARMS-3-REPS-ONECPU-v1",
        sources=16,trials=len(rows),holdout_sources=8,
        gate="root-UP residual active>=3 and largest component>=3 and edges>=2; two probes",
        gate_uses_outcome=False,source_truth_independently_exhaustive=True,
        original_SAT_model_independent=True,UNSAT_independent_LRAT=False,
        synthetic_nonblind=True,one_logical_cpu=True,summary=summary,rows=rows)
    (OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    print("IGE1T_FINAL "+json.dumps({k:v for k,v in audit.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":
    # Wrap structure so its timing is included in the gated arm.
    old=active_structure
    def timed(clauses,n):
        t=time.perf_counter();x=old(clauses,n)
        x["scan_s"]=time.perf_counter()-t
        return x
    active_structure=timed
    main()

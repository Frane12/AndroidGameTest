#!/usr/bin/env python3
"""ATLAS BLOCK2: exact SCC substitution; randomized equivalent B control.
Source-frozen SATLIB, original-model verified, 1CPU E2E including preprocessing.
"""
import hashlib,io,json,os,pathlib,resource,subprocess,tarfile,time,urllib.request
import sys
sys.path.insert(0,"research")
import drnas_atlasmap2_learn as L

OUT=pathlib.Path("mre_map2_real47");OUT.mkdir(exist_ok=True)
META=json.loads(pathlib.Path("research/drnas-sat-v7-4/frozen_real_medium.json").read_text())
SETS=[("uf100-430",15),("uf250-1065",14),("flat200-479",14),("planning-logistics",4)]
SHARD=int(os.environ.get("MAP2_REAL47_SHARD","0"))
assert 0<=SHARD<5
CAP=20.0
REPS=2
ARMS=("A","LIVE","FALLBACK","kissat","cadical")
BIN=pathlib.Path("mre_atlasmap2/bin/drnas_atlasmap2").resolve()
REFBIN={"kissat":pathlib.Path("mre_map2_real47/bin/kissat").resolve(),
        "cadical":pathlib.Path("mre_map2_real47/bin/cadical").resolve()}
def normalize(raw):
    header=None;clauses=[];current=[];ended=False
    for line in raw.decode("ascii","strict").splitlines():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):ended=True;continue
        if ended:
            if line=="0":continue
            raise ValueError("unexpected trailer")
        if line.startswith("p "):
            p=line.split()
            if len(p)!=4 or p[1]!="cnf" or header is not None:raise ValueError("bad header")
            header=(int(p[2]),int(p[3]));continue
        if header is None:raise ValueError("missing header")
        for w in line.split():
            lit=int(w)
            if lit:
                if abs(lit)>header[0]:raise ValueError("literal out of range")
                current.append(lit)
            else:clauses.append(current);current=[]
    if header is None or current or len(clauses)!=header[1]:raise ValueError("clause count")
    n,_=header
    data=(f"p cnf {n} {len(clauses)}\n"+
          "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    return data,n,clauses
def atlas_extended_screen(n,clauses):
    """Binary implication graph, exact SCC equivalences, candidate blocks.
    Diagnostic only: no new CNF clauses or unverified substitutions.
    """
    edges={};binary=0
    for c in clauses:
        if len(c)!=2 or abs(c[0])==abs(c[1]):continue
        a,b=c;edges.setdefault(-a,set()).add(b);edges.setdefault(-b,set()).add(a)
        binary+=1
    nodes=set(edges)
    for vs in edges.values():nodes.update(vs)
    sys.setrecursionlimit(max(sys.getrecursionlimit(),4*n+100))
    index=0;stack=[];on=set();ids={};low={};components=[]
    def visit(v):
        nonlocal index
        ids[v]=index;low[v]=index;index+=1;stack.append(v);on.add(v)
        for w in edges.get(v,()):
            if w not in ids:visit(w);low[v]=min(low[v],low[w])
            elif w in on:low[v]=min(low[v],ids[w])
        if low[v]==ids[v]:
            comp=[]
            while True:
                w=stack.pop();on.remove(w);comp.append(w)
                if w==v:break
            components.append(comp)
    for v in sorted(nodes):
        if v not in ids:visit(v)
    roots={v:i for i,c in enumerate(components) for v in c}
    return {"binary_implications":2*binary,
      "equivalent_literal_pairs":sum(len(c)*(len(c)-1)//2 for c in components),
      "contradictory_scc":any(roots.get(v)==roots.get(-v) for v in range(1,n+1)
                              if v in roots and -v in roots),
      "small_block_candidates":sum(2<=len(c)<=4 for c in clauses),
      "mode":"screen_only_no_new_clauses"}

sources=[]
for family,count in SETS:
    entry=next(x for x in META["archives"] if x["set"]==family)
    with urllib.request.urlopen(entry["url"],timeout=90) as response:
        archive=response.read(25_000_000)
    if hashlib.sha256(archive).hexdigest()!=entry["archive_sha256"]:
        raise RuntimeError("pinned archive SHA mismatch "+family)
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tf:
        members=sorted((x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")),
           key=lambda x:hashlib.sha256((family+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
        if len(members)<count:raise RuntimeError("not enough sources")
        for member in members[:count]:
            raw=tf.extractfile(member).read()
            data,n,clauses=normalize(raw)
            sources.append({"id":len(sources),"family":family,"entry":member.name,
              "archive_sha256":entry["archive_sha256"],
              "raw_sha256":hashlib.sha256(raw).hexdigest(),
              "source_sha256":hashlib.sha256(data).hexdigest(),
              "variables":n,"clauses":len(clauses),"data":data})
assert len(sources)==47 and len({s["source_sha256"] for s in sources})==47
selection=[{k:v for k,v in s.items() if k!="data"} for s in sources]
(OUT/"sources.json").write_text(json.dumps(selection,indent=2))
print("MAP2_REAL47_SOURCE "+json.dumps({"total":47,"selected":selection},sort_keys=True),flush=True)

import random
CAP=20.0
REPS=2
SHARD=int(os.environ.get("BLOCK4_SHARD","0"))
assert 0<=SHARD<3
ARMS=("A","BLOCK2","B_RANDOM","KISSAT")
def reduce_scc(n,clauses,seed=None):
    edges={};reverse={}
    for c in clauses:
        if len(c)!=2 or abs(c[0])==abs(c[1]):continue
        a,b=c
        for u,v in ((-a,b),(-b,a)):
            edges.setdefault(u,set()).add(v)
            reverse.setdefault(v,set()).add(u)
    nodes=set(edges)|set(reverse)
    # Iterative Kosaraju: bounded stack, deterministic graph order.
    visited=set();order=[]
    for root in sorted(nodes):
        if root in visited:continue
        visited.add(root);stack=[(root,iter(sorted(edges.get(root,()))))]
        while stack:
            v,it=stack[-1]
            w=next(it,None)
            if w is None:order.append(v);stack.pop()
            elif w not in visited:
                visited.add(w);stack.append((w,iter(sorted(edges.get(w,())))))
    comp={};groups=[]
    for root in reversed(order):
        if root in comp:continue
        idx=len(groups);members=[];stack=[root];comp[root]=idx
        while stack:
            v=stack.pop();members.append(v)
            for w in sorted(reverse.get(v,())):
                if w not in comp:comp[w]=idx;stack.append(w)
        groups.append(sorted(members))
    if any(comp.get(v)==comp.get(-v) for v in range(1,n+1)
           if v in comp and -v in comp):
        return None,{"reason":"contradictory_SCC"}
    rng=random.Random(seed)
    mapping={v:v for v in range(1,n+1)}
    seen=set()
    for i,g in enumerate(groups):
        if i in seen:continue
        other=comp.get(-g[0])
        seen.add(i)
        if other is not None:seen.add(other)
        # Representative literal is a member of the SCC, hence equivalent.
        rep=(rng.choice(g) if seed is not None else min(g,key=lambda x:(abs(x),x)))
        for lit in g:
            if lit>0:mapping[lit]=rep
            else:mapping[-lit]=-rep
        if other is not None:
            for lit in groups[other]:
                if lit>0:mapping[lit]=-rep
                else:mapping[-lit]=rep
    reduced=[];dedup=set();taut=0
    for c in clauses:
        literals=set()
        for lit in c:
            m=mapping[abs(lit)]
            literals.add(m if lit>0 else -m)
        if any(-x in literals for x in literals):
            taut+=1;continue
        key=tuple(sorted(literals))
        if key not in dedup:dedup.add(key);reduced.append(key)
    changed=sum(mapping[v]!=v for v in mapping)
    return (mapping,reduced),{"equivalent_variables_rewritten":changed,
       "clauses_before":len(clauses),"clauses_after":len(reduced),
       "tautologies_removed":taut,"unique_scc":len(groups),
       "reason":"exact_binary_implication_SCC"}
def write_cnf(path,n,clauses):
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
def native_run(path,n,clauses,original,mapping,start):
    # Native original CNF verification is repeated after lifting the model.
    command=[str(BIN),str(path.resolve()),"--mode","A","--time",str(CAP)]
    try:
        p=subprocess.run(command,text=True,capture_output=True,timeout=CAP+2)
    except subprocess.TimeoutExpired:
        return "UNKNOWN",False,0,0
    status={10:"SAT",20:"UNSAT"}.get(p.returncode,"UNKNOWN")
    if status=="UNSAT":raise RuntimeError("UNSAT requires independent proof")
    verified=False
    if status=="SAT":
        vals={}
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                for token in line.split()[1:]:
                    lit=int(token)
                    if lit:vals[abs(lit)]=lit>0
        lifted={}
        for v in range(1,n+1):
            m=mapping[v]
            if abs(m) not in vals:raise RuntimeError("incomplete SAT witness")
            lifted[v]=vals[abs(m)] if m>0 else not vals[abs(m)]
        verified=all(any(lifted[abs(l)]==(l>0) for l in c) for c in original)
        if not verified:raise RuntimeError("BLOCK2 original witness invalid")
    match=L.TELEMETRY.search(p.stdout)
    t=dict(kv.split("=",1) for kv in match.group(1).split() if "=" in kv) if match else {}
    return status,verified,int(t.get("decisions",0)),int(t.get("conflicts",0))
rows=[]
for source in sources:
    if source["id"] not in (14,16,18,19,20,22,24,25,26,28,30,32) or source["id"]%3!=SHARD:continue
    original_path=OUT/("block2_original_%02d.cnf"%source["id"])
    original_path.write_bytes(source["data"])
    _,n,clauses=L.read_cnf(original_path)
    # Half source-frozen SATLIB controls, half with exact fresh-variable aliases.
    # Alias y <-> x is definitional and equisatisfiable with the original.
    cohort="alias" if source["id"]%2==0 else "control"
    if cohort=="alias":
        original_n=n
        rng=random.Random(int(source["source_sha256"][:16],16))
        targets=rng.sample(range(1,original_n+1),min(32,original_n))
        replacements={x:original_n+i+1 for i,x in enumerate(targets)}
        new_clauses=[]
        for ci,c in enumerate(clauses):
            new_clauses.append([((replacements[abs(l)] if ci%2==0 and abs(l) in replacements else abs(l))*(1 if l>0 else -1)) for l in c])
        for x,y in replacements.items():
            new_clauses.extend([[-x,y],[x,-y]])
        n=original_n+len(replacements)
        clauses=new_clauses
        write_cnf(original_path,n,clauses)
    for rep in range(REPS):
        for arm in ARMS:
            start=time.monotonic()
            reduced=None;details={"reason":"baseline"}
            if arm not in ("A","KISSAT"):
                seed=None if arm=="BLOCK2" else int(source["source_sha256"][:16],16)+rep
                reduced,details=reduce_scc(n,clauses,seed)
            mapping={v:v for v in range(1,n+1)}
            path=original_path
            if reduced is not None:
                mapping,cls=reduced
                path=OUT/f"block2_{source['id']}_{rep}_{arm}.cnf"
                write_cnf(path,n,cls)
            if arm=="KISSAT":
                try:p=subprocess.run(["mre_map2_real47/bin/kissat",str(original_path.resolve())],capture_output=True,text=True,timeout=CAP+2)
                except subprocess.TimeoutExpired:p=subprocess.CompletedProcess([],0,"","")
                status={10:"SAT",20:"UNSAT"}.get(p.returncode,"UNKNOWN")
                vals={}
                for line in p.stdout.splitlines():
                    if line.startswith("v "):
                        for token in line.split()[1:]:
                            lit=int(token)
                            if lit:vals[abs(lit)]=lit>0
                verified=status=="SAT" and all(any(vals.get(abs(l))==(l>0) for l in c) for c in clauses)
                if status=="SAT" and not verified:raise RuntimeError("Kissat witness invalid")
                if status=="UNSAT":status="UNKNOWN"
                decisions=conflicts=0
            else:
                status,verified,decisions,conflicts=native_run(path,n,clauses,clauses,mapping,start)
            elapsed=time.monotonic()-start
            row={"id":source["id"],"family":source["family"],"sha256":source["source_sha256"],
                 "arm":arm,"rep":rep,"cohort":cohort,"status":status,"SAT_original_verified":verified,
                 "UNSAT_independent_LRAT":False,"E2E_s":round(elapsed,6),
                 "PAR2_s":round(elapsed if status=="SAT" else 2*CAP,6),
                 "decisions":decisions,"conflicts":conflicts,**details}
            rows.append(row)
            print("ATLAS_BLOCK4_KISSAT_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={}
for arm in ARMS:
    rr=[x for x in rows if x["arm"]==arm]
    summary[arm]={"trials":len(rr),"solved":sum(x["SAT_original_verified"] for x in rr),
      "PAR2_s":round(sum(x["PAR2_s"] for x in rr),6),
      "decisions":sum(x["decisions"] for x in rr),
      "conflicts":sum(x["conflicts"] for x in rr),
      "rewritten":sum(x.get("equivalent_variables_rewritten",0) for x in rr),
      "clauses_saved":sum(x.get("clauses_before",0)-x.get("clauses_after",0) for x in rr)}
(OUT/f"block4_kissat_audit_{SHARD}.json").write_text(json.dumps({"rows":rows,"summary":summary},indent=2))
print("ATLAS_BLOCK4_FINAL "+json.dumps({"shard":SHARD,"summary":summary},sort_keys=True),flush=True)

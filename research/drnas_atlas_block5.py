#!/usr/bin/env python3
"""ATLAS BLOCK2: exact SCC substitution; randomized equivalent B control.
Source-frozen SATLIB, original-model verified, 1CPU E2E including preprocessing.
"""
import hashlib,io,json,os,pathlib,resource,subprocess,tarfile,time,urllib.request
import sys
sys.path.insert(0,"research")
import drnas_atlasmap2_learn as L
import drnas_atlas_selective_gf2 as GF2

OUT=pathlib.Path("mre_map2_real47");OUT.mkdir(exist_ok=True)
META=json.loads(pathlib.Path("research/drnas-sat-v7-4/frozen_real_medium.json").read_text())
SETS=[("uf100-430",15),("uf250-1065",14),("flat200-479",14),("planning-logistics",4)]
SHARD=int(os.environ.get("MAP2_REAL47_SHARD","0"))
assert 0<=SHARD<5
CAP=20.0
REPS=3
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
CAP=12.0
REPS=2
SHARD=int(os.environ.get("BLOCK4_SHARD","0"))
assert 0<=SHARD<3
ARMS=("A","BLOCK2","B_RANDOM")
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

# BLOCK5: training only updates memory; prospective holdout never updates it.
# Model remembers relative benefit of deterministic vs random representative.
MEMORY=pathlib.Path("research/atlas_block5_memory.json")
memory=json.loads(MEMORY.read_text()) if MEMORY.exists() else {"version":1,"groups":{}}
train=[];holdout=[];rng=random.Random(51011)
for source in sources[:42]:
    (holdout if int(source["source_sha256"][:8],16)%5==0 else train).append(source)
# Ensure a useful holdout even with skewed SHA partitions.
if len(holdout)<6:holdout=train[-8:]+holdout;train=train[:-8]
def prepare(source):
    path=OUT/("block5_original_%02d.cnf"%source["id"])
    path.write_bytes(source["data"])
    _,n,clauses=L.read_cnf(path)
    cohort="alias" if source["id"]%2==0 else "control"
    if cohort=="alias":
        original_n=n
        r=random.Random(int(source["source_sha256"][:16],16))
        targets=r.sample(range(1,n+1),min(32,n))
        replacements={x:n+i+1 for i,x in enumerate(targets)}
        changed=[]
        for ci,c in enumerate(clauses):
            changed.append([(replacements.get(abs(l),abs(l)) if ci%2==0 else abs(l))*(1 if l>0 else -1) for l in c])
        for x,y in replacements.items():changed.extend([[-x,y],[x,-y]])
        n+=len(replacements);clauses=changed
        write_cnf(path,n,clauses)
    return path,n,clauses,cohort
def key_for(source,n,clauses,cohort):
    # Structural categories, never SHA or variable names.
    density=len(clauses)/max(1,n)
    return source["family"]+"|"+cohort+"|"+("dense" if density>=4 else "sparse")
def confidence(group,arm):
    a=group.get(arm,{"wins":0,"losses":0})
    # Beta(1,1) posterior, no premature certainty.
    w=a["wins"];l=a["losses"];p=(w+1)/(w+l+2)
    return p,1.96*(p*(1-p)/(w+l+3))**0.5
def run(source,phase):
    path,n,clauses,cohort=prepare(source)
    gf2=GF2.screen(clauses)
    key=key_for(source,n,clauses,cohort)+"|gf2_"+gf2["gate"]
    group=memory["groups"].setdefault(key,{})
    choices=("BLOCK2","B_RANDOM")
    for rep in range(2):
        results={}
        # A is always measured. During train both alternatives are measured.
        # During holdout one policy choice is made using frozen memory.
        if phase=="train":selected=list(choices)
        else:
            scores={arm:confidence(group,arm)[0] for arm in choices}
            selected=[max(choices,key=lambda a:(scores[a],a=="BLOCK2"))]
        for arm in ["A"]+selected:
            start=time.monotonic();details={"reason":"baseline"};mapping={v:v for v in range(1,n+1)}
            solve_path=path
            if arm!="A":
                seed=None if arm=="BLOCK2" else int(source["source_sha256"][:16],16)+rep
                reduced,details=reduce_scc(n,clauses,seed)
                if reduced is not None:
                    mapping,cls=reduced
                    solve_path=OUT/f"block5_{source['id']}_{rep}_{arm}.cnf"
                    write_cnf(solve_path,n,cls)
            status,verified,decisions,conflicts=native_run(solve_path,n,clauses,clauses,mapping,start)
            elapsed=time.monotonic()-start
            row={"id":source["id"],"source_sha256":source["source_sha256"],"phase":phase,
                 "cohort":cohort,"key":key,"rep":rep,"arm":arm,"status":status,
                 "gf2_gate":gf2["gate"],"gf2_rows":gf2["rows"],"gf2_rank":gf2["rank"],
                 "gf2_contradiction_shadow":gf2["contradiction"],
                 "SAT_original_verified":verified,"E2E_s":round(elapsed,6),
                 "PAR2_s":round(elapsed if verified else 2*CAP,6),
                 "decisions":decisions,"conflicts":conflicts,**details}
            results[arm]=row;rows.append(row)
            print("ATLAS_BLOCK5_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        if phase=="train":
            for arm in choices:
                # Treat equal times within 2% as ties, avoiding millisecond noise.
                a=results[arm];b=results["A"]
                gain=(b["PAR2_s"]-a["PAR2_s"])/max(b["PAR2_s"],0.001)
                g=group.setdefault(arm,{"wins":0,"losses":0,"ties":0,"gain_sum":0.0})
                if gain>0.02:g["wins"]+=1
                elif gain< -0.02:g["losses"]+=1
                else:g["ties"]+=1
                g["gain_sum"]+=gain
rows=[]
for source in train:run(source,"train")
# Freeze learned table BEFORE holdout. Holdout outcomes cannot change choices.
snapshot=json.loads(json.dumps(memory))
(OUT/"block5_frozen_before_holdout.json").write_text(json.dumps(snapshot,indent=2,sort_keys=True))
for source in holdout:run(source,"holdout")
MEMORY.write_text(json.dumps(snapshot,indent=2,sort_keys=True)+"\n")
summary={}
for phase in ("train","holdout"):
    for arm in ("A","BLOCK2","B_RANDOM"):
        rr=[r for r in rows if r["phase"]==phase and r["arm"]==arm]
        summary[phase+"_"+arm]={"trials":len(rr),"solved":sum(r["SAT_original_verified"] for r in rr),
          "PAR2_s":round(sum(r["PAR2_s"] for r in rr),6),
          "decisions":sum(r["decisions"] for r in rr),
          "conflicts":sum(r["conflicts"] for r in rr),
          "rewritten":sum(r.get("equivalent_variables_rewritten",0) for r in rr)}
(OUT/"block5_audit.json").write_text(json.dumps({"train_sha":[s["source_sha256"] for s in train],
 "holdout_sha":[s["source_sha256"] for s in holdout],"rows":rows,"summary":summary,
 "memory_frozen":snapshot},indent=2))
print("ATLAS_BLOCK5_FINAL "+json.dumps({"summary":summary,"memory_groups":len(snapshot["groups"]),
 "train_sources":len(train),"holdout_sources":len(holdout)},sort_keys=True),flush=True)

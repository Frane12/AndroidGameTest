#!/usr/bin/env python3
"""47 frozen original SATLIB SAT CNFs, native MAP2 structural fallback.
SHA-pinned archives, selection independent of solver outcomes, 1 CPU,
matched native A / live / structural fallback / Kissat / CaDiCaL.
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
rows=[]
for source in sources:
    if source["id"]%5!=SHARD:continue
    path=OUT/("source_%02d.cnf"%source["id"])
    path.write_bytes(source["data"])
    _,n,clauses=L.read_cnf(path)
    feat=L.features(n,clauses)
    extended=atlas_extended_screen(n,clauses)
    # No result-dependent routing. Small/easy, no parity group, and
    # contradictory source cycles go straight to own native DRNAS.
    eligible=(n>=64 and len(clauses)>=250 and
              feat["eligible_groups"]>0 and not feat["contradictory_cycle"] and
              not extended["contradictory_scc"])
    for rep in range(REPS):
        for arm in ARMS:
            mode=("LIVE" if eligible else "A") if arm=="FALLBACK" else arm
            start=time.monotonic()
            if mode in ("A","LIVE"):
                result=L.solve(BIN,path,mode,CAP,n,clauses)
            else:
                cmd=[str(REFBIN[mode]),str(path.resolve())]
                def limits():
                    resource.setrlimit(resource.RLIMIT_CPU,(20,21))
                    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
                try:
                    p=subprocess.run(cmd,text=True,capture_output=True,
                        timeout=CAP+2,preexec_fn=limits)
                    status={10:"SAT",20:"UNSAT"}.get(p.returncode,"UNKNOWN")
                    if status=="SAT" and not L.verify_sat(p.stdout,n,clauses):
                        raise RuntimeError("invalid original SAT witness: "+mode)
                    if status=="UNSAT":
                        raise RuntimeError("reference UNSAT on SATLIB SAT source")
                except subprocess.TimeoutExpired:status="UNKNOWN"
                e=time.monotonic()-start
                result={"arm":mode,"status":status,"E2E_s":round(e,6),
                    "PAR2_s":round(e if status!="UNKNOWN" else 2*CAP,6),
                    "SAT_original_verified":status=="SAT",
                    "UNSAT_independent_LRAT":False,
                    "decisions":0,"conflicts":0,"live_implications":0,
                    "live_reasons":0,"shadow_opportunities":0,"map2_groups":0}
            result.update({"id":source["id"],"family":source["family"],
                "source_sha256":source["source_sha256"],"rep":rep,
                "arm":arm,"effective_mode":mode,"fallback":arm=="FALLBACK" and not eligible,
                "structural_features":feat,"atlas_extended_screen":extended})
            rows.append(result)
            print("MAP2_REAL47_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
summary={}
for arm in ARMS:
    r=[x for x in rows if x["arm"]==arm]
    summary[arm]={"trials":len(r),"solved":sum(x["status"]=="SAT" for x in r),
       "PAR2_s":round(sum(x["PAR2_s"] for x in r),6),
       "E2E_s":round(sum(x["E2E_s"] for x in r),6),
       "live_implications":sum(x["live_implications"] for x in r),
       "decisions":sum(x["decisions"] for x in r),
       "conflicts":sum(x["conflicts"] for x in r),
       "fallback_count":sum(x["fallback"] for x in r)}
(OUT/"audit.json").write_text(json.dumps({"protocol":"MAP2-real47-original-SATLIB-SHA-2rep-20s-oneCPU",
  "shard":SHARD,"sources":selection,"rows":rows,"summary":summary},indent=2))
print("MAP2_REAL47_FINAL "+json.dumps({"shard":SHARD,"summary":summary},sort_keys=True),flush=True)

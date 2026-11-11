#!/usr/bin/env python3
"""DRNAS ATLAS WIDE500: source-pinned 20-family SAT curriculum and live CDCL journal.
400 train / 100 source-disjoint holdout. Frozen policy on holdout. No UNSAT
performance claim without independent proof. All live decisions are diagnostic:
verified completed *episodes*, not individual decisions, train strategy preference.
"""
import argparse,hashlib,io,json,os,pathlib,random,selectors,subprocess,tarfile,time,urllib.request
from itertools import combinations,product
import drnas_atlas_selective_gf2 as GF2

ROOT=pathlib.Path("mre_map2_real47")
ROOT.mkdir(exist_ok=True)
MEMROOT=pathlib.Path("research")
META=json.loads((MEMROOT/"drnas-sat-v7-4/frozen_real_medium.json").read_text())
SOURCES=["uf100-430","uuf100-430","uf250-1065","uuf250-1065","flat200-479"]
SYNTH=["random3_uniform","random3_planted","random4_planted","xor3_sat",
       "xor4_sat","xor_chain_unsat","xor_hybrid","equiv_chain",
       "implication_dag","color3_sat","color3_unsat","pigeonhole_sat",
       "pigeonhole_unsat","vertex_cover_sat","mux_circuit_sat"]
assert len(SOURCES)+len(SYNTH)==20
CAP=2.5
SHARD=int(os.environ.get("ATLAS_WIDE_SHARD","0"))
ARMS=("A","GF2_SELECTIVE","MAP2_LIVE")
BIN=pathlib.Path("mre_atlasmap2/bin/drnas_atlasmap2").resolve()

def canonical(n,clauses):
    if n<1 or n>2000 or len(clauses)>25000: raise ValueError("size bounds")
    for c in clauses:
        if any(v==0 or abs(v)>n for v in c): raise ValueError("literal out of bounds")
    return (f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def parse_original(data):
    n=declared=None; clauses=[];pending=[]
    for line in data.decode("ascii","strict").splitlines():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):break
        if line.startswith("p "):
            t=line.split()
            if len(t)!=4 or t[1]!="cnf" or n is not None:raise ValueError("bad DIMACS header")
            n=int(t[2]);declared=int(t[3]);continue
        if n is None:raise ValueError("missing header")
        for t in line.split():
            lit=int(t)
            if lit:pending.append(lit)
            else:clauses.append(pending);pending=[]
    if pending or len(clauses)!=declared:raise ValueError("CNF parse mismatch")
    return n,clauses

def source_corpus():
    result={}
    for family in SOURCES:
        entry=next(a for a in META["archives"] if a["set"]==family)
        with urllib.request.urlopen(entry["url"],timeout=90) as r:archive=r.read()
        if hashlib.sha256(archive).hexdigest()!=entry["archive_sha256"]:
            raise RuntimeError("frozen archive SHA failure: "+family)
        with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tar:
            members=sorted((m for m in tar.getmembers()
               if m.isfile() and m.name.lower().endswith(".cnf")),
               key=lambda m:hashlib.sha256((family+"|"+m.name).encode()).hexdigest())
            if len(members)<25:raise RuntimeError("SATLIB category too small: "+family)
            selection=[]
            for entry_ in members[:25]:
                original=tar.extractfile(entry_).read()
                n,clauses=parse_original(original)
                data=canonical(n,clauses)
                selection.append((n,clauses,hashlib.sha256(data).hexdigest(),entry_.name))
            result[family]=selection
    return result

def rand_clause(r,n,k,assignment=None):
    lits=[]
    for v in r.sample(range(1,n+1),k):
        lits.append(v if r.randrange(2) else -v)
    if assignment is not None and not any(assignment[abs(x)]==(x>0) for x in lits):
        lits[0]=-lits[0]
    return lits

def xor_rows(r,n,assignment,width,count):
    out=[];seen=set()
    for _ in range(count):
        vs=tuple(sorted(r.sample(range(1,n+1),width)))
        if vs in seen:continue
        seen.add(vs)
        parity=sum(int(assignment[v]) for v in vs)%2
        out.extend(GF2.parity_cnf(vs,parity))
    return out

def coloring(i,r,unsat):
    v=10+(i%8); n=3*v
    color=[r.randrange(3) for _ in range(v)]
    clauses=[]
    for u in range(v):
        xs=[3*u+j+1 for j in range(3)]
        clauses.append(xs)
        for a,b in combinations(xs,2):clauses.append([-a,-b])
    edges=set()
    if unsat:
        edges.update(tuple(pair) for pair in combinations(range(4),2))
    for _ in range(3*v):
        a,b=sorted(r.sample(range(v),2))
        if not unsat and color[a]==color[b]:continue
        edges.add((a,b))
    for a,b in edges:
        for j in range(3):clauses.append([-(3*a+j+1),-(3*b+j+1)])
    return n,clauses

def pigeonhole(i,unsat):
    h=4+i%6; p=h+int(unsat)
    n=p*h+i+1
    clauses=[[a*h+j+1 for j in range(h)] for a in range(p)]
    for j in range(h):
        for a,b in combinations(range(p),2):
            clauses.append([-(a*h+j+1),-(b*h+j+1)])
    clauses.append([n]) # Unique harmless variable per source.
    return n,clauses

def synth_one(cat,i):
    r=random.Random(int(hashlib.sha256(f"WIDE500|{cat}|{i}".encode()).hexdigest()[:16],16))
    n=32+i%35
    values={v:bool(r.getrandbits(1)) for v in range(1,n+1)}
    if cat=="random3_uniform":
        clauses=[rand_clause(r,n,3) for _ in range(125+2*i)]
    elif cat=="random3_planted":
        clauses=[rand_clause(r,n,3,values) for _ in range(115+2*i)]
    elif cat=="random4_planted":
        clauses=[rand_clause(r,n,4,values) for _ in range(90+2*i)]
    elif cat=="xor3_sat":
        clauses=xor_rows(r,n,values,3,8+i%7)
        clauses += [[v if values[v] else -v] for v in r.sample(range(1,n+1),3)]
    elif cat=="xor4_sat":
        clauses=xor_rows(r,n,values,4,7+i%6)
        clauses += [rand_clause(r,n,3,values) for _ in range(12)]
    elif cat=="xor_chain_unsat":
        clauses=GF2.parity_cnf((1,2),0)+GF2.parity_cnf((2,3),0)+GF2.parity_cnf((1,3),1)
        clauses+=xor_rows(r,n,values,3,5+i%6)
    elif cat=="xor_hybrid":
        clauses=xor_rows(r,n,values,3,6+i%5)
        clauses += [rand_clause(r,n,3,values) for _ in range(75)]
    elif cat=="equiv_chain":
        clauses=[]
        for v in range(1,n):clauses.extend([[-v,v+1],[v,-(v+1)]])
        clauses += [[1]]+[rand_clause(r,n,3,{j:True for j in range(1,n+1)}) for _ in range(35)]
    elif cat=="implication_dag":
        clauses=[[-a,b] for a,b in (sorted(r.sample(range(1,n+1),2)) for _ in range(3*n))]
        clauses += [[1],[n]]
    elif cat=="color3_sat":return coloring(i,r,False)
    elif cat=="color3_unsat":return coloring(i,r,True)
    elif cat=="pigeonhole_sat":return pigeonhole(i,False)
    elif cat=="pigeonhole_unsat":return pigeonhole(i,True)
    elif cat=="vertex_cover_sat":
        cover=set(r.sample(range(1,n+1),int(0.62*n)))
        clauses=[]
        for _ in range(3*n):
            a,b=sorted(r.sample(range(1,n+1),2))
            if a not in cover and b not in cover:continue
            clauses.append([a,b])
        clauses += [[v] for v in sorted(cover)[:2]]
    elif cat=="mux_circuit_sat":
        inputs=12+i%8; gates=15+i%12
        n=inputs+gates
        values={v:bool(r.getrandbits(1)) for v in range(1,inputs+1)}
        clauses=[]
        for v in range(inputs+1,n+1):
            a,b,sel=r.sample(range(1,v),3)
            values[v]=values[b] if values[sel] else values[a]
            clauses.extend([[sel,-a,v],[sel,a,-v],[-sel,-b,v],[-sel,b,-v]])
        clauses += [[v if values[v] else -v] for v in range(n-2,n+1)]
    else:raise ValueError(cat)
    return n,clauses

def make_dataset(shard):
    original=source_corpus()
    rows=[]
    for cat in SOURCES+SYNTH:
        for i in range(25):
            if i%5!=shard:continue
            if cat in original:
                n,clauses,sha,entry=original[cat][i]
            else:
                n,clauses=synth_one(cat,i)
                sha=hashlib.sha256(canonical(n,clauses)).hexdigest()
                entry=f"generated:{cat}:{i}"
            rows.append(dict(category=cat,index=i,n=n,clauses=clauses,sha256=sha,
                             provenance=entry,phase="train" if i<20 else "holdout"))
    if len(rows)!=100 or len({v["sha256"] for v in rows})!=100:
        raise ValueError("unbalanced or duplicate source set")
    return rows

def episode(binary,source,arm,journal):
    raw=canonical(source["n"],source["clauses"])
    cnf=ROOT/("wide500_current_%d.cnf"%SHARD)
    cnf.write_bytes(raw)
    start=time.monotonic()
    proc=subprocess.Popen([str(binary),str(cnf.resolve()),"--mode",arm,"--time",str(CAP)],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
    select=selectors.DefaultSelector()
    select.register(proc.stdout,selectors.EVENT_READ)
    buffer=b""; finished=False; output_lines=[];events=0
    deadline=start+CAP+1.2
    while time.monotonic()<deadline:
        waiting=select.select(timeout=0.12)
        if waiting:
            chunk=os.read(proc.stdout.fileno(),65536)
            if not chunk:
                finished=True;break
            buffer+=chunk
            while b"\n" in buffer:
                line,buffer=buffer.split(b"\n",1)
                line=line.decode("ascii","replace")
                if line.startswith("DRNAS_CDCL_EVENT "):
                    parts=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
                    journal.write(json.dumps(dict(phase=source["phase"],sha256=source["sha256"],
                        category=source["category"],arm=arm,elapsed_s=round(time.monotonic()-start,6),
                        telemetry=parts),sort_keys=True)+"\n")
                    journal.flush()
                    events+=1
                else:output_lines.append(line)
        if proc.poll() is not None and not waiting:break
    if proc.poll() is None:proc.kill()
    try:proc.wait(timeout=1)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    if buffer:output_lines.append(buffer.decode("ascii","replace"))
    seconds=round(time.monotonic()-start,6)
    status={10:"SAT",20:"UNSAT_UNCERTIFIED"}.get(proc.returncode,"UNKNOWN")
    model={}
    stats={}
    for line in output_lines:
        if line.startswith("v "):
            for token in line.split()[1:]:
                try:lit=int(token)
                except ValueError:continue
                if lit:model[abs(lit)]=lit>0
        if line.startswith("ATLASMAP2_TRIAL "):
            stats=dict(t.split("=",1) for t in line.split()[1:] if "=" in t)
    valid=(status=="SAT" and len(model)>=source["n"] and all(
        any(model.get(abs(lit))==(lit>0) for lit in clause) for clause in source["clauses"]))
    if status=="SAT" and not valid:
        raise AssertionError("Invalid native model: "+source["sha256"]+" "+arm)
    return {"arm":arm,"status":status,"SAT_original_verified":bool(valid),
        "UNSAT_independent_LRAT":False,"E2E_s":seconds,
        "PAR2_s":seconds if valid else 2*CAP,"CDCL_events_written":events,
        "decisions":int(stats.get("decisions","0")),
        "conflicts":int(stats.get("conflicts","0")),
        "learned":int(stats.get("learned","0")),
        "gf2_gate":int(stats.get("gf2_gate","0")),
        "gf2_implications":int(stats.get("gf2_implications","0")),
        "gf2_reasons":int(stats.get("gf2_reasons","0")),
        "gf2_derived_rows":int(stats.get("gf2_derived_rows","0"))}

def group_key(source,screen):
    cnf=source["clauses"]
    binaries=sum(len(c)==2 for c in cnf)
    b="b_hi" if binaries*3>=len(cnf) else "b_low"
    return "|".join((source["category"],"xor_"+screen["gate"],b))

def save_atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    p=path.with_name(path.name+".tmp")
    with p.open("w") as f:
        json.dump(obj,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(p,path)

def decide(group):
    if not group:return "A"
    candidate="A";best=0.0
    for arm in ("GF2_SELECTIVE","MAP2_LIVE"):
        g=group.get(arm,{})
        wins=g.get("wins",0); losses=g.get("losses",0); ties=g.get("ties",0)
        prior=(wins+1)/(wins+losses+2)
        avg=g.get("gain_sum",0)/max(1,wins+losses+ties)
        if wins+losses>=3 and prior>=0.62 and avg>0.06 and avg>best:
            candidate=arm;best=avg
    return candidate

def summarize(rows):
    answer={}
    for phase in ("train","holdout"):
        for arm in ("A","GF2_SELECTIVE","MAP2_LIVE","POLICY"):
            s=[r for r in rows if r["phase"]==phase and r["arm"]==arm]
            answer[phase+"_"+arm]={"trials":len(s),"SAT_original_verified":sum(r["SAT_original_verified"] for r in s),
                "PAR2_s":round(sum(r["PAR2_s"] for r in s),6),
                "CDCL_events_written":sum(r["CDCL_events_written"] for r in s)}
    return answer

def run_shard():
    dataset=make_dataset(SHARD)
    mpath=ROOT/f"atlas_wide500_memory_shard_{SHARD}.json"
    events=ROOT/f"atlas_wide500_events_shard_{SHARD}.jsonl"
    records=ROOT/f"atlas_wide500_results_shard_{SHARD}.json"
    memory={"schema":1,"shard":SHARD,"train_samples":{},"groups":{}}
    rows=[]
    print("ATLAS_WIDE500_SOURCE "+json.dumps({"shard":SHARD,"sources":len(dataset),
       "train":80,"holdout":20,"categories":len(set(x["category"] for x in dataset)),
       "cap_s":CAP,"one_logical_CPU":True},sort_keys=True),flush=True)
    with events.open("w",buffering=1) as journal:
        for source in dataset:
            screen=GF2.screen(source["clauses"])
            key=group_key(source,screen)
            # No evaluation result enters memory. Training and test split by
            # original SHA, never merely by a transformed copy.
            group=memory["groups"].get(key,{})
            policy=decide(group) if source["phase"]=="holdout" else None
            options=list(ARMS) if source["phase"]=="train" else ["A"]+([policy] if policy!="A" else [])
            completed={}
            for arm in options:
                outcome=episode(BIN,source,arm,journal)
                completed[arm]=outcome
                rows.append(dict(category=source["category"],index=source["index"],phase=source["phase"],
                    sha256=source["sha256"],key=key,**outcome))
                print("ATLAS_WIDE500_TRIAL "+json.dumps(rows[-1],sort_keys=True),flush=True)
            if source["phase"]=="train":
                if source["sha256"] in memory["train_samples"]:
                    raise AssertionError("duplicate training SHA")
                g=memory["groups"].setdefault(key,{})
                for arm in ARMS[1:]:
                    a,b=completed["A"],completed[arm]
                    x=g.setdefault(arm,{"wins":0,"losses":0,"ties":0,"gain_sum":0.0,"paired_verified":0})
                    if a["SAT_original_verified"] and b["SAT_original_verified"]:
                        gain=(a["PAR2_s"]-b["PAR2_s"])/max(0.001,a["PAR2_s"])
                        if gain>0.02:x["wins"]+=1
                        elif gain< -0.02:x["losses"]+=1
                        else:x["ties"]+=1
                        x["gain_sum"]+=gain;x["paired_verified"]+=1
                memory["train_samples"][source["sha256"]]={"category":source["category"],"key":key,
                   "results":completed,"source_index":source["index"]}
                # Atomically persist after each complete verified (or unknown)
                # CDCL episode: crash-safe on-run learning without test leakage.
                save_atomic(mpath,memory)
            else:
                selected=completed[policy]
                rows.append(dict(category=source["category"],index=source["index"],phase="holdout",
                    sha256=source["sha256"],key=key,arm="POLICY",selected=policy,
                    **{k:v for k,v in selected.items() if k not in ("arm",)}))
                print("ATLAS_WIDE500_POLICY "+json.dumps(rows[-1],sort_keys=True),flush=True)
    summary=summarize(rows)
    save_atomic(records,{"shard":SHARD,"rows":rows,"summary":summary,
        "train_sha":list(memory["train_samples"]),
        "holdout_sha":list({r["sha256"] for r in rows if r["phase"]=="holdout"})})
    print("ATLAS_WIDE500_FINAL "+json.dumps({"shard":SHARD,"summary":summary,
       "train_sources":len(memory["train_samples"]),"holdout_sources":20,
       "memory_groups":len(memory["groups"])},sort_keys=True),flush=True)

def merge(base):
    memory={"schema":1,"groups":{},"train_samples":{}}
    rows=[];shards=[]
    for i in range(5):
        mem=json.loads((base/f"atlas_wide500_memory_shard_{i}.json").read_text())
        result=json.loads((base/f"atlas_wide500_results_shard_{i}.json").read_text())
        shards.append(result["summary"])
        rows+=result["rows"]
        for sha,sample in mem["train_samples"].items():
            if sha in memory["train_samples"]:raise ValueError("training SHA overlap")
            memory["train_samples"][sha]=sample
        for key,strategies in mem["groups"].items():
            dst=memory["groups"].setdefault(key,{})
            for arm,stats in strategies.items():
                target=dst.setdefault(arm,{k:0 for k in stats})
                for k,v in stats.items():target[k]=target.get(k,0)+v
    if len(memory["train_samples"])!=400:raise AssertionError("expected 400 disjoint train SHAs")
    holdout={r["sha256"] for r in rows if r["phase"]=="holdout"}
    if len(holdout)!=100 or holdout.intersection(memory["train_samples"]):
        raise AssertionError("holdout size/disjointness failure")
    result={"schema":1,"train_sources":400,"holdout_sources":100,"source_categories":20,
        "summary":summarize(rows),"shard_summaries":shards,
        "method":"training episodes update memory after verified SAT; frozen holdout and no per-decision causal claims",
        "UNSAT_independent_LRAT":False}
    save_atomic(MEMROOT/"atlas_wide500_memory.json",memory)
    save_atomic(MEMROOT/"atlas_wide500_summary.json",result)
    print("ATLAS_WIDE500_MERGED "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--merge-dir")
    args=parser.parse_args()
    if args.merge_dir:merge(pathlib.Path(args.merge_dir))
    else:run_shard()

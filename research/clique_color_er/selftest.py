#!/usr/bin/env python3
"""Adversarial safety test: 80 real SAT controls with full known models.

Every SAT control deletes a different source-required clause from a
valid clique-versus-coloring UNSAT input; rejected sources MUST return
UNKNOWN. Ten generated UNSAT controls must produce VeriPB-accepted
formal proofs, not merely a custom schema acceptance.
"""
import collections,itertools,json,pathlib,random,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from source_check import recover,Unsupported
from emit_veripb import compile_source

def build(n,k):
    c=k-1
    edge={p:i+1 for i,p in enumerate(itertools.combinations(range(n),2))}
    idx=len(edge)
    P={(i,u):idx+i*n+u+1 for i in range(k) for u in range(n)}
    idx+=k*n
    C={(u,z):idx+u*c+z+1 for u in range(n) for z in range(c)}
    src=[];labels=[]
    def add(row,tag):src.append(tuple(row));labels.append(tag)
    for i in range(k):
        add([P[i,u] for u in range(n)],("P_ALO",i))
        for u,v in itertools.combinations(range(n),2):
            add([-P[i,u],-P[i,v]],("P_AMO",i,u,v))
    for i,j in itertools.combinations(range(k),2):
        for u in range(n):add([-P[i,u],-P[j,u]],("P_INJECT",i,j,u))
        for u in range(n):
            for v in range(n):
                if u!=v:add([-P[i,u],-P[j,v],
                             edge[tuple(sorted((u,v)))]],("P_EDGE",i,j,u,v))
    for u in range(n):
        add([C[u,z] for z in range(c)],("C_ALO",u))
        for z,w in itertools.combinations(range(c),2):
            add([-C[u,z],-C[u,w]],("C_AMO",u,z,w))
    for (u,v),e in edge.items():
        for z in range(c):add([-e,-C[u,z],-C[v,z]],("COLOR_EDGE",u,v,z))
    return src,labels,P,C,edge,idx+n*c

def render(src,nv,seed):
    rng=random.Random(seed);src=list(src);rng.shuffle(src)
    for i,row in enumerate(src):
        xs=list(row);rng.shuffle(xs);src[i]=xs
    return (f"p cnf {nv} {len(src)}\n"+
            "".join(" ".join(map(str,row))+" 0\n" for row in src)).encode()

def main():
    results=collections.Counter()
    with tempfile.TemporaryDirectory(prefix="clique-color-er-safety-") as td:
        tmp=pathlib.Path(td)
        for seed in range(80):
            n=4+seed%3;k=3+(seed//3)%2;c=k-1
            rows,tags,P,C,edges,nv=build(n,k)
            full=render(rows,nv,seed)
            recover(full)
            results["valid_unsat_source"]+=1
            if seed<10:
                proof,meta=compile_source(full)
                source=tmp/"original.cnf";pb=tmp/"proof.pbp"
                source.write_bytes(full);pb.write_text(proof)
                v=subprocess.run([str(ROOT/"veripb-tool/bin/veripb"),
                    "--cnf",str(source),str(pb)],
                    capture_output=True,text=True,timeout=15)
                assert v.returncode==0 and "s VERIFIED UNSATISFIABLE" in v.stdout+v.stderr
                results["independent_veripb"]+=1
            typ=seed%4
            if typ==0:
                missing=("P_ALO",0)
                picks={i:i-1 for i in range(1,k)}
                colors={u:u for u in range(c)}
                selected=list(picks.values())
                active={tuple(sorted(e)) for e in itertools.combinations(selected,2)}
            elif typ==1:
                missing=("P_INJECT",0,1,0)
                picks={i:max(0,i-1) for i in range(k)}
                colors={u:u for u in range(c)}
                selected=sorted(set(picks.values()))
                active={tuple(sorted(e)) for e in itertools.combinations(selected,2)}
            elif typ==2:
                missing=("P_EDGE",0,1,0,1)
                picks={i:i for i in range(k)}
                colors={u:0 if u in (0,1) else u-1 for u in range(k)}
                selected=list(picks.values())
                active={tuple(sorted(e)) for e in itertools.combinations(selected,2)}-{(0,1)}
            else:
                missing=("COLOR_EDGE",0,1,0)
                picks={i:i for i in range(k)}
                colors={u:0 if u in (0,1) else u-1 for u in range(k)}
                selected=list(picks.values())
                active={tuple(sorted(e)) for e in itertools.combinations(selected,2)}
            assert missing in tags
            altered=[row for row,tag in zip(rows,tags) if tag!=missing]
            truth={}
            for (i,u),v in P.items():truth[v]=picks.get(i,-1)==u
            for (u,z),v in C.items():truth[v]=colors.get(u,0)==z
            for pair,v in edges.items():truth[v]=pair in active
            assert len(truth)==nv
            assert all(any(truth[abs(v)]==(v>0) for v in clause)
                       for clause in altered),"SAT control model invalid"
            try:recover(render(altered,nv,seed+900))
            except Unsupported:results["known_SAT_rejected"]+=1
            else:raise AssertionError("FALSE UNSAT on known SAT source")
            results[f"removed_{typ}"]+=1
        rows,tags,P,C,E,nv=build(4,3)
        recover(render(rows+[(-P[0,0],)],nv,71))
        results["extra_unit_unsat_control_accepted"]+=1
    assert results["known_SAT_rejected"]==80 and results["independent_veripb"]==10
    print("CLIQUE_COLOR_ER_SAFETY_PASS "+json.dumps(results,sort_keys=True),flush=True)
if __name__=="__main__":main()

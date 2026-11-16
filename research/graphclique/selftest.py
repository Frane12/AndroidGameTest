#!/usr/bin/env python3
"""Adversarial deterministic source-control test for graph-clique VeriPB.

Positive UNSAT controls have actual original-CNF clique source clauses.
SAT controls have a complete concrete satisfying coloring; their status
is NOT inferred from a catalog label. Include variable-ID permutations
and ALO literal-order shuffles. The external checker validates a sample
of generated proofs; CI separately validates all 8 original 2026 CNFs.
"""
import hashlib,itertools,json,pathlib,random,subprocess,tempfile
from emit_veripb import compile_source,Unsupported

ROOT=pathlib.Path(__file__).resolve().parents[2]
VERIPB=ROOT/"veripb-tool/bin/veripb"

def make_source(k,n,edges,seed,shuffle_ids=False):
    rng=random.Random(seed)
    coords={(v,c):v*k+c+1 for v in range(n) for c in range(k)}
    if shuffle_ids:
        numbers=list(range(1,n*k+1));rng.shuffle(numbers)
        coords={coord:numbers[i] for i,coord in enumerate(coords)}
    rows=[[coords[v,c] for c in range(k)] for v in range(n)]
    for u,v in edges:
        for c in range(k):rows.append([-coords[u,c],-coords[v,c]])
    for r in rows:rng.shuffle(r)
    rng.shuffle(rows)
    raw=(f"p cnf {k*n} {len(rows)}\n"+
         "".join(" ".join(map(str,row))+" 0\n" for row in rows)).encode()
    return raw,coords

def model_ok(raw,model):
    n=0
    for line in raw.decode().splitlines():
        if line.startswith("p "):
            n=int(line.split()[2])
            continue
        xs=list(map(int,line.split()))[:-1]
        if not any(model[abs(x)]==(x>0) for x in xs):return False
    return len(model)==n

def main():
    results={"SAT_witness_controls":0,"UNSAT_producers":0,
             "variable_relabelings":0,"external_VERIPB":0,
             "SAT_missing_edge_control_rejected":False,
             "bad_source_rejected":False}
    with tempfile.TemporaryDirectory() as folder:
        td=pathlib.Path(folder)
        for seed in range(80):
            k=2+seed%7;n=k+1+seed%14
            rng=random.Random(7001*seed+13)
            colors=[rng.randrange(k) for _ in range(n)]
            edges=[(u,v) for u in range(n) for v in range(u+1,n)
                   if colors[u]!=colors[v] and rng.randrange(100)<30]
            raw,coords=make_source(k,n,edges,seed,shuffle_ids=seed%2==0)
            assignment={coords[v,c]:colors[v]==c for v in range(n) for c in range(k)}
            assert model_ok(raw,assignment)
            try:compile_source(raw)
            except Unsupported:results["SAT_witness_controls"]+=1
            else:raise RuntimeError("false UNSAT on an explicitly SAT source")
        for seed in range(80):
            k=2+seed%7;n=k+1+seed%14
            rng=random.Random(1237*seed+71)
            edges={(u,v) for u in range(k+1) for v in range(u+1,k+1)}
            for u in range(n):
                for v in range(u+1,n):
                    if (u,v) not in edges and rng.randrange(100)<10:
                        edges.add((u,v))
            raw,coords=make_source(k,n,edges,seed+40,shuffle_ids=seed%2==1)
            pb,meta=compile_source(raw)
            assert meta["source_sha256"]==hashlib.sha256(raw).hexdigest()
            assert meta["clique_size"]==k+1
            results["UNSAT_producers"]+=1
            if seed%2==0:results["variable_relabelings"]+=1
            if seed%8==0:
                src=td/"source.cnf";proof=td/"proof.pbp"
                src.write_bytes(raw);proof.write_text(pb)
                proc=subprocess.run([str(VERIPB),"--cnf",str(src),str(proof)],
                                    capture_output=True,text=True,timeout=10)
                assert proc.returncode==0 and "s VERIFIED UNSATISFIABLE" in proc.stdout+proc.stderr
                results["external_VERIPB"]+=1
        # A K_{k+1} with a single omitted source same-color edge clause
        # has an explicit k-coloring (two vertices share only that color).
        k=5;n=6
        all_edges=[(u,v) for u in range(n) for v in range(u+1,n)]
        raw,coords=make_source(k,n,all_edges,991,shuffle_ids=True)
        text=raw.decode().splitlines()
        clause=f"{-coords[0,0]} {-coords[1,0]} 0"
        reverse=f"{-coords[1,0]} {-coords[0,0]} 0"
        assert clause in text or reverse in text
        text.remove(clause if clause in text else reverse)
        text[0]=f"p cnf {n*k} {len(text)-1}"
        changed=("\n".join(text)+"\n").encode()
        model={coords[v,c]:(c==(0 if v<2 else v-1))
               for v in range(n) for c in range(k)}
        assert model_ok(changed,model)
        try:compile_source(changed)
        except Unsupported:results["SAT_missing_edge_control_rejected"]=True
        else:raise RuntimeError("UNSAT from missing-edge SAT source")
        try:compile_source(changed.replace(b"p cnf ",b"p cnf 0 ",1))
        except (ValueError,Unsupported):results["bad_source_rejected"]=True
        else:raise RuntimeError("malformed original source accepted")
    assert (results["SAT_witness_controls"]==80 and
            results["UNSAT_producers"]==80 and
            results["external_VERIPB"]==10 and
            results["SAT_missing_edge_control_rejected"] and
            results["bad_source_rejected"])
    print("GRAPH_CLIQUE_SELFTEST_PASS "+json.dumps(results,sort_keys=True),flush=True)

if __name__=="__main__":main()

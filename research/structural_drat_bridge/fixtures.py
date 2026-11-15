#!/usr/bin/env python3
"""Regenerate eight SHA-pinned CNFs from the pre-existing synthetic development19.
The source families/sizes, shuffle seeds, and SHA checks are fixed independently
of the new DRAT-conversion benchmark.
"""
from pathlib import Path
import hashlib,itertools,random,sys
SEED=20261115
EXPECTED={
    0:("php_8_7","18b0a7edac4cb83d0728acf089908eb89b8ff72b1a761257afdf9fa17b51bae6"),
    1:("php_11_10","924241f723a3618ca84f2b20770e193548eaf43c1a00a94e257666d713fba731"),
    3:("hall_14jobs_14machines_6to5","e4d15bfe5d0d50890edfde081b7213fde334b99be7baa10cafa36eb2cc24603a"),
    4:("hall_18jobs_18machines_9to8","518c06e4943e65d7b823a6fb2dc0c3a1faa412c4c12522e8086a10337af1eaaf"),
    7:("xor_ring_48_unsat","3e8526d7d64805d3f7954209f5d5d51973e24ebbf0a9a3575e969ff54ca3874d"),
    8:("xor_ring_96_unsat","68239fc9dfa9c8682640f2539d17beccd18bba40d252abec723ce09e67a5751f"),
    10:("tseitin_24vertices_unsat","981cb643f18d623481d9a4aff436750e25cf1ab16708d974552223a9b9cc5548"),
    11:("tseitin_48vertices_unsat","911140dea7a674da914ee35eccfe4439157b8500fdfd4ebdd3bf28c5a8219ebc"),
}
def php(p,h):
    v=lambda i,j:1+i*h+j
    cs=[[v(i,j) for j in range(h)] for i in range(p)]
    for j in range(h):
        for i,k in itertools.combinations(range(p),2):
            cs.append([-v(i,j),-v(k,j)])
    return p*h,cs

def hall(jobs,machines,subset,reduced):
    eligible=[list(range(reduced)) if i<subset else list(range(machines)) for i in range(jobs)]
    var={};pos=0
    for i,row in enumerate(eligible):
        for j in row:pos+=1;var[i,j]=pos
    cs=[]
    for i,row in enumerate(eligible):
        cs.append([var[i,j] for j in row])
        for j,k in itertools.combinations(row,2):
            cs.append([-var[i,j],-var[i,k]])
    for j in range(machines):
        eligible_j=[i for i in range(jobs) if (i,j) in var]
        for i,k in itertools.combinations(eligible_j,2):
            cs.append([-var[i,j],-var[k,j]])
    return pos,cs

def xor_clause(vs,parity):
    return [[-v if mask>>i&1 else v for i,v in enumerate(vs)]
            for mask in range(1<<len(vs)) if mask.bit_count()%2!=parity]

def xor_ring(length):
    z=length+1;cs=[]
    for i in range(length):
        parity=int(i==length//2)
        cs+=xor_clause([i+1,(i+1)%length+1,z],parity)
    return z,cs

def tseitin(nverts):
    edges=[]
    for u in range(nverts):
        a,b=sorted((u,(u+1)%nverts));edges.append((a,b))
    for i in range(nverts//2):edges.append((i,i+nverts//2))
    edges=sorted(set(edges));edgevar={e:i+1 for i,e in enumerate(edges)}
    inc=[[] for _ in range(nverts)]
    for (u,v),x in edgevar.items():inc[u].append(x);inc[v].append(x)
    cs=[]
    for i,row in enumerate(inc):
        cs+=xor_clause(row,int(i==0))
    return len(edges),cs

CASES={
 0:("pigeonhole",lambda:php(8,7)),
 1:("pigeonhole",lambda:php(11,10)),
 3:("hall_matching",lambda:hall(14,14,6,5)),
 4:("hall_matching",lambda:hall(18,18,9,8)),
 7:("xor_gf2",lambda:xor_ring(48)),
 8:("xor_gf2",lambda:xor_ring(96)),
 10:("tseitin_graph_parity",lambda:tseitin(24)),
 11:("tseitin_graph_parity",lambda:tseitin(48)),
}
def regenerate(outdir):
    outdir.mkdir(parents=True,exist_ok=True);result=[]
    for i,(family,build) in CASES.items():
        n,clauses=build()
        rng=random.Random(SEED+i*7919)
        for c in clauses:rng.shuffle(c)
        rng.shuffle(clauses)
        text=(f"c DRNAS STRUCTURAL CHALLENGE V1 | synthetic development | {family}\n"
            +f"p cnf {n} {len(clauses)}\n"
            +''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        data=text.encode('ascii')
        label,expected=EXPECTED[i]
        sha=hashlib.sha256(data).hexdigest()
        if sha!=expected:raise RuntimeError(f"FROZEN_SOURCE_DRIFT {label}: {sha}")
        p=outdir/(f"{i+1:02d}_{label}.cnf");p.write_bytes(data)
        result.append((label,p,sha))
    return result
if __name__=="__main__":
    for label,path,sha in regenerate(Path(sys.argv[1]) if len(sys.argv)>1 else Path("frozen_synthetic8")):
        print("FROZEN_INPUT",label,sha,path)

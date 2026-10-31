#!/usr/bin/env python3
"""Pinned original DIMACS Challenge graphs -> exact k-color SAT CNF.

Freeze graph names, Git blob hashes and k choices before any solve. The
DIMACS .col headers are historically not uniform: sometimes 'p edge'
declares directed arcs rather than unique undirected edges. We accept
ONLY observed edge-line count or 2x unique edge count as the header
count, and archive both values; undirected edges are deduplicated.

The encoding is bijective wrt proper k-color assignments:
(1) every vertex at least one color, (2) at most one, (3) adjacent
vertices cannot have same color. No solver-specific preprocessing.
"""
import argparse,csv,hashlib,json,urllib.request
from pathlib import Path

def download(uri):
    request=urllib.request.Request(uri,headers={
      'User-Agent':'DRNAS-SAT-v7.7-DIMACS-GraphColor-fixed-2026'})
    with urllib.request.urlopen(request,timeout=50) as h:
        raw=h.read(9_000_001)
    if len(raw)>9_000_000:raise ValueError('Oversize .col input')
    return raw

def parse_graph(raw,name):
    header=None;edges=set();line_count=0
    for line in raw.decode('ascii').splitlines():
        l=line.strip()
        if not l or l.startswith('c'):continue
        fields=l.split()
        if fields[0]=='p':
            if header or len(fields)!=4 or fields[1]!='edge':
                raise ValueError('Unexpected multiple/invalid .col header '+name)
            header=(int(fields[2]),int(fields[3]))
            continue
        if fields[0]!='e' or len(fields)!=3 or header is None:
            raise ValueError('Unexpected .col line '+str(fields[:4]))
        u,v=map(int,fields[1:])
        if not (1<=u<=header[0] and 1<=v<=header[0] and u!=v):
            raise ValueError('Invalid vertex id or self-loop')
        line_count+=1
        edges.add((min(u,v),max(u,v)))
    if header is None or not edges:raise ValueError('Empty graph')
    n,declared=header
    if not (declared==line_count or declared==2*len(edges)):
        raise ValueError(f'.col header count {declared} inconsistent with {line_count} arc-lines and {len(edges)} unique undirected edges')
    return n,sorted(edges),dict(original_header_edges=declared,
        observed_edge_lines=line_count,undirected_edges=len(edges))

def generate(n,edges,k,path):
    if not (2<=k<=40 and n>=k):raise ValueError('unexpected k or graph n')
    # 1..n*k; var(vertex_1indexed, color_1indexed)
    idx=lambda v,c:(v-1)*k+c
    count=n+n*k*(k-1)//2+len(edges)*k
    with path.open('w',encoding='ascii') as f:
        f.write(f'c DRNAS experimental exact {k}-colorability encoding\n')
        f.write(f'p cnf {n*k} {count}\n')
        for v in range(1,n+1):
            f.write(' '.join(str(idx(v,c)) for c in range(1,k+1))+' 0\n')
            for c in range(1,k+1):
                for d in range(c+1,k+1):
                    f.write(f'-{idx(v,c)} -{idx(v,d)} 0\n')
        for u,v in edges:
            for c in range(1,k+1):
                f.write(f'-{idx(u,c)} -{idx(v,c)} 0\n')
    return count

def prepare(spec,outdir,shard,shards):
    assert 0<=shard<shards
    assert shards==10 and len(spec['k_colorings_predeclared'])==10
    assert spec['decision_count']==20
    src=spec['public_source'];commit=spec['source_commit']
    selected=spec['k_colorings_predeclared'][shard]
    name=selected['name'];raw=download(f'https://raw.githubusercontent.com/{src}/{commit}/{name}')
    gitblob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()
    assert gitblob==selected['git_blob_sha'],('Git blob mismatch',name,gitblob)
    n,edges,orig=parse_graph(raw,name)
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    originals=root/'originals';originals.mkdir(exist_ok=True)
    graphpath=originals/name;graphpath.write_bytes(raw)
    canonical=root/(name+'.normalized.col')
    canonical.write_text(f'c normalized undirected input derived strictly from {name}\n'
        +f'p edge {n} {len(edges)}\n'
        +''.join(f'e {u} {v}\n' for u,v in edges),encoding='ascii')
    recorded=[]
    for k in selected['colors']:
        path=root/(name+f'.k{k}.cnf')
        nclauses=generate(n,edges,k,path)
        record=dict(case=name+f'.k{k}',family=selected['family'],
            k=k,vertices=n,undirected_edges=len(edges),
            clauses=nclauses,variables=n*k,
            input_cnf=str(path.resolve()),source_graph=str(graphpath.resolve()),
            normalized_graph=str(canonical.resolve()),
            input_cnf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_graph_sha256=hashlib.sha256(raw).hexdigest(),
            normalized_graph_sha256=hashlib.sha256(canonical.read_bytes()).hexdigest(),
            git_blob_sha=gitblob,source_commit=commit,original_header=orig,
            relation='EXACT_K_COLOR_WITH_AT_LEAST_ONE_AT_MOST_ONE_EDGE_CONSTRAINTS',
            expected_class='UNKNOWN_NOT_USED_FOR_SELECTION')
        recorded.append(record)
        print('BUILT',record['case'],f'n={n} e={len(edges)}',
              f'variables={n*k} clauses={nclauses}',
              'source_sha256='+record['source_graph_sha256'],flush=True)
    (root/'cases.json').write_text(json.dumps(recorded,indent=2))
    print('PASS: two fixed k-decision CNFs prepared from SHA-pinned graph',name,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--shard',type=int,required=True)
    p.add_argument('--shards',type=int,default=10)
    a=p.parse_args()
    prepare(json.loads(Path(a.manifest).read_text()),a.outdir,a.shard,a.shards)

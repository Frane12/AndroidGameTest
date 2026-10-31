#!/usr/bin/env python3
"""Prove exact SATLIB 3-color CNF <-> DIMACS .col instance equivalence.

Original variables are grouped by positive size-3 vertex clauses. Require
the ENTIRE original clause MULTISET exactly equals a standard 3-coloring
encoding (one vertex triple, 3 at-most-one clauses per vertex, and 3
same-color negative clauses per graph edge). Fail closed otherwise.
Only these certified graphs can be used for a mathematically fair
fixed-k ZykovColor comparison. Never heuristically infer a missing edge.
"""
import argparse,collections,csv,hashlib,json
from pathlib import Path
def parse_cnf(path):
    header=None; clauses=[];cl=[]
    with Path(path).open(encoding='ascii') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith('c'):continue
            if line.startswith('%'):break
            if line.startswith('p '):
                parts=line.split()
                if header or len(parts)!=4 or parts[:2]!=['p','cnf']:
                    raise ValueError('unsupported DIMACS header')
                header=(int(parts[2]),int(parts[3]))
                continue
            if header is None:raise ValueError('no header')
            for token in line.split():
                l=int(token)
                if l==0:
                    clauses.append(tuple(sorted(cl)))
                    cl=[]
                else:
                    if abs(l)>header[0]:raise ValueError('literal outside range')
                    cl.append(l)
    if header is None or cl or len(clauses)!=header[1]:
        raise ValueError('incomplete DIMACS')
    return header[0],clauses

def derive_graph(path):
    n,clauses=parse_cnf(path)
    vertex_clauses=[c for c in clauses if len(c)==3 and all(l>0 for l in c)]
    if n%3 or len(vertex_clauses)!=n//3:raise ValueError('not ordinary 3color formula')
    groups=sorted(set(vertex_clauses))
    if len(groups)!=len(vertex_clauses):raise ValueError('duplicate vertex clause')
    positions={}
    for v,triple in enumerate(groups):
        for color,lit in enumerate(triple):
            if lit in positions:raise ValueError('variable occurs in two vertex groups')
            positions[lit]=(v,color)
    if len(positions)!=n or set(positions)!=set(range(1,n+1)):
        raise ValueError('positive triples do not partition variables')
    expected=collections.Counter()
    for triple in groups:
        expected[tuple(sorted(triple))]+=1
        for a in range(3):
            for b in range(a+1,3):
                expected[tuple(sorted((-triple[a],-triple[b])))]+=1
    edges=collections.defaultdict(list)
    for clause in clauses:
        if len(clause)!=2 or not all(l<0 for l in clause):continue
        (v,c),(w,d)=[positions[-l] for l in clause]
        if v==w:continue
        u,z=sorted((v,w))
        if c!=d:raise ValueError('cross-edge matches different color indices')
        edges[(u,z)].append(c)
    for (u,v),colors in edges.items():
        if sorted(colors)!=[0,1,2]:
            raise ValueError('edge requires one SAME-color clause per color')
        for k in range(3):
            expected[tuple(sorted((-groups[u][k],-groups[v][k])))]+=1
    observed=collections.Counter(clauses)
    if expected!=observed:
        extra=sum((observed-expected).values())
        missing=sum((expected-observed).values())
        raise ValueError(f'original SAT CNF NOT exactly graph 3-coloring: extra={extra},missing={missing}')
    return len(groups),sorted(edges)

def verify_and_save(entry,output_dir):
    inp=Path(entry['path'])
    assert hashlib.sha256(inp.read_bytes()).hexdigest()==entry['expected_sha256']
    n,edges=derive_graph(inp)
    graph=Path(output_dir)/(entry['name']+'.col')
    graph.write_text('c SATLIB three-color graph extracted with exact CNF multiset proof\n'+
        f'p edge {n} {len(edges)}\n'+
        ''.join(f'e {u+1} {v+1}\n' for u,v in edges),encoding='ascii')
    if not (n==200 and len(edges)==479):
        raise AssertionError('SATLIB flat200-479 n=200 m=479 fingerprint mismatch')
    return dict(case=entry['name'],family=entry['family'],
        input_cnf=str(inp.resolve()),graph_col=str(graph.resolve()),
        cnf_sha256=entry['expected_sha256'],
        graph_sha256=hashlib.sha256(graph.read_bytes()).hexdigest(),
        vertices=n,edges=len(edges),k=3,graph_relation='EXACT_CNF_MULTIMSET_EQUALITY',
        original_archive_sha256=entry['source_archive_sha256'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verification',required=True)
    parser.add_argument('--outdir',required=True)
    parser.add_argument('--group',choices=('pilot','holdout'),default='holdout')
    args=parser.parse_args()
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    entries=json.loads(Path(args.verification).read_text())[args.group]
    if not entries:raise RuntimeError('zero selected SATLIB CNFs')
    good=[];failed=[]
    for i,e in enumerate(entries):
        try:good.append(verify_and_save(e,out))
        except Exception as err:
            failed.append(dict(case=e['name'],error=str(err),cnf_sha256=e['expected_sha256']))
        print('EXTRACT',i+1,'/',len(entries),e['name'],
              'OK' if len(good)==i+1 else 'REJECT',flush=True)
    (out/'graph_extraction_audit.json').write_text(json.dumps(dict(
       expected=len(entries),accepted=len(good),rejected=len(failed),
       extractor='full original DIMACS clause multiset identity check',
       entries=good,errors=failed),indent=2))
    if failed:raise RuntimeError(f'{len(failed)} selected CNFs cannot be proven exactly equivalent to .col graphs; NO guessed replacements. See audit artifact.')
    (out/'graphs.json').write_text(json.dumps(good,indent=2))
    print('PASS: all',len(good),'original SATLIB CNFs have certified identical 3-color graph',flush=True)

if __name__=='__main__':main()

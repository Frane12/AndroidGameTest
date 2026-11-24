#!/usr/bin/env python3
"""Independent source-only Hall-style clique-cover verifier for DRNAS SCALE6.
Every accepted UNSAT is entailed by original DIMACS clauses. No solver import,
no file-label oracle; this is not a standard VeriPB/DRAT/LRAT certificate.
"""
import argparse,hashlib,json
from pathlib import Path

def parse(data):
    header=None; clauses=[];current=[]
    for line in data.decode('ascii').splitlines():
        xs=line.split()
        if not xs or xs[0]=='c':continue
        if xs[0]=='p':
            if header is not None or len(xs)!=4 or xs[1]!='cnf':raise ValueError('bad header')
            header=(int(xs[2]),int(xs[3]))
            if min(header)<0:raise ValueError('negative header dimensions')
            continue
        if header is None:raise ValueError('missing header')
        for x in xs:
            lit=int(x)
            if lit==0:
                clauses.append(tuple(current));current=[]
            else:
                if abs(lit)>header[0]:raise ValueError('literal out of range')
                current.append(lit)
    if header is None or current or len(clauses)!=header[1]:raise ValueError('clause count mismatch')
    return header[0],clauses

def verify(source,cert):
    if cert.get('format')!='pcmax-scale6-clique-cover-v1':raise ValueError('format')
    digest=hashlib.sha256(source).hexdigest()
    if cert.get('source_sha256')!=digest:raise ValueError('SHA mismatch')
    nvars,clauses=parse(source)
    ids=cert.get('job_clause_indices');cliques=cert.get('mutex_cliques')
    if not isinstance(ids,list) or not ids or not isinstance(cliques,list) or not cliques:
        raise ValueError('missing witness')
    if any(type(j)!=int or j<0 or j>=len(clauses) for j in ids) or len(set(ids))!=len(ids):
        raise ValueError('invalid job indices')
    selectors=set()
    for idx in ids:
        cl=clauses[idx]
        if len(cl)<2 or any(lit<=0 for lit in cl) or len(set(cl))!=len(cl):
            raise ValueError('job demand not entailed by source')
        if selectors.intersection(cl):raise ValueError('a selector counted in multiple jobs')
        selectors.update(cl)
    negative={tuple(sorted((-a,-b))) for c in clauses if len(c)==2 and (a:=c[0])<0 and (b:=c[1])<0 and a!=b}
    covered=set()
    for group in cliques:
        if not isinstance(group,list) or not group or any(type(x)!=int or x<=0 or x>nvars for x in group):
            raise ValueError('bad clique literals')
        if len(set(group))!=len(group) or set(group).intersection(covered):
            raise ValueError('duplicate clique membership')
        for i,a in enumerate(group):
            for b in group[i+1:]:
                if tuple(sorted((a,b))) not in negative:
                    raise ValueError('missing original binary mutex')
        covered.update(group)
    if covered!=selectors:raise ValueError('cliques do not exactly cover source demands')
    if not(type(cert.get('demand'))==int and type(cert.get('capacity'))==int):
        raise ValueError('bad demand/capacity')
    if cert['demand']!=len(ids) or cert['capacity']!=len(cliques) or len(ids)<=len(cliques):
        raise ValueError('no strictly deficient clique cover')
    return dict(status='SOURCE_CLIQUE_COVER_UNSAT_VERIFIED',sha256=digest,required=len(ids),capacity=len(cliques),selectors=len(selectors))

if __name__=='__main__':
    arg=argparse.ArgumentParser();arg.add_argument('cnf',type=Path);arg.add_argument('certificate',type=Path)
    a=arg.parse_args()
    try:
        print(json.dumps(verify(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))))
    except (ValueError,TypeError,OSError,UnicodeError,KeyError) as e:
        arg.exit(1,f'REJECTED: {e}\n')

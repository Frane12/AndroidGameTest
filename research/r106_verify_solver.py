#!/usr/bin/env python3
"""R106 check solver-reported SAT models against immutable source DIMACS."""
def cnf_clauses(source):
    """Bounded independent DIMACS parser; 2025 ordering-XOR has 408044 clauses."""
    import pathlib
    file=pathlib.Path(source)
    if file.stat().st_size>24*1024*1024:raise RuntimeError('R106 large CNF refused')
    n=m=None;clauses=[];pending=[]
    with file.open('r',encoding='ascii',errors='strict') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith('c'):continue
            if line.startswith('%'):break
            if line.startswith('p '):
                fields=line.split()
                if len(fields)!=4 or fields[1]!='cnf' or n is not None:
                    raise RuntimeError('R106 bad DIMACS header')
                n,m=int(fields[2]),int(fields[3])
                if not 0<n<=2000000 or not 0<=m<=1500000:
                    raise RuntimeError('R106 DIMACS header exceeds safety limits')
                continue
            if n is None:raise RuntimeError('R106 missing DIMACS header')
            for field in line.split():
                lit=int(field)
                if abs(lit)>n:raise RuntimeError('R106 out-of-range literal')
                if lit:pending.append(lit)
                else:
                    clauses.append(tuple(pending));pending=[]
                    if len(clauses)>m:raise RuntimeError('R106 clauses exceed header')
    if pending or n is None or len(clauses)!=m:
        raise RuntimeError('R106 incomplete DIMACS input')
    return clauses
def status(output,code):
    labels=set()
    for line in output.splitlines():
        if line.startswith('s '):
            if 'UNSATISFIABLE' in line:labels.add('UNSAT')
            elif 'SATISFIABLE' in line:labels.add('SAT')
    if len(labels)>1:raise RuntimeError('contradictory solver status lines')
    decoded={10:'SAT',20:'UNSAT'}.get(code)
    if decoded is None and code==0 and len(labels)==1:decoded=next(iter(labels))
    if decoded is None or (labels and labels!={decoded}):
        raise RuntimeError('solver exit code and declared status inconsistent')
    return decoded
def model_valid(output,clauses):
    values={};present=False
    for line in output.splitlines():
        if not line.startswith('v '):continue
        present=True
        for tok in line[2:].split():
            lit=int(tok)
            if not lit:continue
            key=abs(lit);value=lit>0
            if key in values and values[key]!=value:return False
            values[key]=value
    return present and all(any(values.get(abs(v))==(v>0) for v in c)
                           for c in clauses)

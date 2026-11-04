#!/usr/bin/env python3
"""R106 check solver-reported SAT models against immutable source DIMACS."""
def cnf_clauses(source):
    import pathlib,sys
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'experiments'/'drnas_v16'))
    import r88_cooperative as r88
    return r88.read_cnf(source)[1]
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

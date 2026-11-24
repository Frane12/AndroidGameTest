#!/usr/bin/env python3
"""Convert an EMITTED_UNCHECKED native SAC9 deletion-free DRAT RUP trace into
VeriPB 3.0. Do not claim a verified result until independent VeriPB accepts it.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ft06_sac'))
from structural_sac import parse

def convert(source,drat):
    nv,clauses=parse(source)
    text=drat.decode('ascii')
    proof=['pseudo-Boolean proof version 3.0',f'f {len(clauses)} ;']
    steps=0;ended=False
    for line in text.splitlines():
        if not line.strip():continue
        if ended:raise ValueError('data following empty clause')
        xs=[int(x) for x in line.split()]
        if not xs or xs[-1]!=0 or any(x==0 for x in xs[:-1]):
            raise ValueError('not a plain RUP clause sequence')
        clause=xs[:-1]
        if not clause:
            ended=True
            break
        if any(abs(lit)>nv for lit in clause) or len(set(clause))!=len(clause):
            raise ValueError('bad literal in RUP clause')
        terms=['1 '+('x'+str(lit) if lit>0 else '~x'+str(-lit)) for lit in clause]
        proof.append('rup '+' '.join(terms)+' >= 1 ;')
        steps+=1
    if not ended:raise ValueError('missing final empty clause')
    proof.extend(['rup >= 1 ;','output NONE ;','conclusion UNSAT ;','end pseudo-Boolean proof ;'])
    return '\n'.join(proof)+'\n',steps

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cnf',type=Path,required=True)
    p.add_argument('--drat',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('proof output already exists')
    raw=a.cnf.read_bytes()
    string,steps=convert(raw,a.drat.read_bytes())
    a.out.write_text(string)
    print('EMITTED_UNCHECKED '+json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),
        'rup_steps':steps,'veripb_bytes':a.out.stat().st_size},sort_keys=True))

if __name__=='__main__':main()

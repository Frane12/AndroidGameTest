#!/usr/bin/env python3
"""Experimental direct VeriPB 3.0 RUP proof from source-only SAC.
EMITTED_UNCHECKED is not verification. Independent veripb required.
"""
import argparse,hashlib,json
from pathlib import Path
from structural_sac import derive,parse

def emit(raw):
    _,clauses=parse(raw)
    result=derive(raw,seconds=20)
    if result['status']!='UNSAT':return None,result
    lines=['pseudo-Boolean proof version 3.0',f'f {len(clauses)} ;']
    for clause in result['proof']:
        if not clause or any(v>=0 for v in clause):raise ValueError('nonnegative RUP literal')
        lines.append('rup '+' '.join(f'1 ~x{-v}' for v in clause)+' >= 1 ;')
    lines.extend(['rup >= 1 ;','output NONE ;','conclusion UNSAT ;',
                  'end pseudo-Boolean proof ;'])
    return '\n'.join(lines)+'\n',result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--cnf',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True)
    args=a.parse_args()
    if args.output.exists():raise SystemExit('refusing to overwrite proof')
    raw=args.cnf.read_bytes();proof,record=emit(raw)
    if proof is None:
        print('UNKNOWN '+json.dumps({k:v for k,v in record.items() if k!='proof'}))
    else:
        args.output.write_text(proof)
        print('EMITTED_UNCHECKED '+json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),
             'proof_bytes':args.output.stat().st_size,'rup_steps':len(record['proof'])}))

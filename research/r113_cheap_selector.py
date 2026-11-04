#!/usr/bin/env python3
"""R113: cheap, conservative XOR2 trigger. No changes to solver or source CNF.
Only calls R111 proof-carrying native path after observing a complete XOR2 pattern.
"""
import pathlib,time
import r111_sensitive_safe_gate as safe

def cheap_signal(path,byte_cap=65536,clause_cap=4000):
    masks={};clauses=0
    try:
        with pathlib.Path(path).open('rb') as f:
            sample=f.read(byte_cap+1)
        if len(sample)>byte_cap:return False,'sample_cap'
        for line in sample.decode('ascii').splitlines():
            if not line or line.startswith('c') or line.startswith('p'):continue
            lits=[int(t) for t in line.split()]
            if not lits or lits[-1]!=0:return False,'partial_clause'
            lits=lits[:-1];clauses+=1
            if clauses>clause_cap:return False,'clause_cap'
            if len(lits)!=2 or abs(lits[0])==abs(lits[1]):continue
            pair=tuple(sorted(map(abs,lits)))
            signs=sum((1<<j) for j,v in enumerate(pair) if -v in lits)
            masks[pair]=masks.get(pair,0)|(1<<signs)
            if masks[pair]==15:return True,'complete_xor2_both_parities'
        return False,'no_strong_xor2'
    except (OSError,UnicodeError,ValueError):return False,'parse_rejected'

def decide(path,native,budget_s=.5):
    t=time.perf_counter();candidate,reason=cheap_signal(path)
    if not candidate:
        return dict(decision='fallback',reason=reason,probe_s=round(time.perf_counter()-t,6))
    remaining=budget_s-(time.perf_counter()-t)
    if remaining<=.01:return dict(decision='fallback',reason='budget_exhausted')
    result=safe.decide(path,native,threshold=0,budget_s=remaining)
    result['cheap_signal']=reason
    return result

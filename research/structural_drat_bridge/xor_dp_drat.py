#!/usr/bin/env python3
"""XOR source structural certificate to DRAT via bounded Davis-Putnam RUP steps.

Unlike treating the XOR annotation as a proof, independently require all
forbidden-parity source CNF clauses for every claimed XOR row. Resolve the
source-backed XOR subformula with bounded variable elimination; each emitted
resolvent is RUP, and acceptance requires an independent DRAT checker.
"""
import argparse,hashlib,itertools,json,time
from collections import defaultdict
from pathlib import Path
from hall_er_drat import read_cnf

def parity_clauses(variables, forbidden):
    result=[]
    for mask in itertools.product((0,1),repeat=len(variables)):
        if sum(mask)%2==forbidden:
            result.append(frozenset((-v if bit else v) for v,bit in zip(variables,mask)))
    return result

def xor_core(cnf,cert):
    if hashlib.sha256(cnf.read_bytes()).hexdigest()!=cert.get("source_sha256"):
        raise ValueError("source SHA mismatch")
    if cert.get("format")!="drnas-math5-eo-xor-unit-v1":
        raise ValueError("unsupported certificate")
    n,source=read_cnf(cnf);source={frozenset(c) for c in source}
    rows=cert.get("xor_rows")
    if not rows or len(rows)>5000:raise ValueError("no bounded XOR rows")
    active=set()
    for i,row in enumerate(rows):
        vs=row.get("vars");f=row.get("forbidden_parity")
        if not isinstance(vs,list) or not 1<=len(vs)<=5 or len(set(vs))!=len(vs):
            raise ValueError("invalid XOR variables")
        if not all(isinstance(v,int) and 0<v<=n for v in vs) or f not in (0,1):
            raise ValueError("invalid XOR row")
        for c in parity_clauses(vs,f):
            if c not in source:raise ValueError(f"XOR row {i} missing source encoding")
            active.add(c)
    return n,active

def generate(cnf,cert,output,max_s=2.0,max_lemmas=200000,max_active=200000):
    n,active=xor_core(cnf,cert)
    initial=len(active);steps=rounds=0;peak=initial;started=time.perf_counter()
    with output.open("w",encoding="ascii") as out:
        while frozenset() not in active:
            if time.perf_counter()-started>max_s:raise TimeoutError("XOR RUP cap")
            occurrences=defaultdict(lambda:[[],[]])
            for c in active:
                for lit in c:occurrences[abs(lit)][lit<0].append(c)
            if not occurrences:
                raise ValueError("XOR core not refuted under full elimination")
            pivot=min(occurrences,
                      key=lambda x:(len(occurrences[x][0])*len(occurrences[x][1]),
                      sum(len(c) for bucket in occurrences[x] for c in bucket),x))
            pos,neg=occurrences[pivot]
            base={c for c in active if pivot not in c and -pivot not in c}
            bysize=defaultdict(list)
            for c in base:bysize[len(c)].append(c)
            added=set()
            for left in pos:
                for right in neg:
                    resolvent=(left-{pivot})|(right-{-pivot})
                    if any(-x in resolvent for x in resolvent):continue
                    if resolvent in base or resolvent in added:continue
                    if any(c.issubset(resolvent) for sz,cs in bysize.items()
                           if sz<=len(resolvent) for c in cs):continue
                    added={c for c in added if not resolvent.issubset(c)}
                    c=frozenset(resolvent);added.add(c)
                    out.write((" ".join(str(x) for x in sorted(c,key=lambda x:(abs(x),x)))+" 0\n") if c else "0\n")
                    steps+=1
                    if steps>max_lemmas:raise RuntimeError("XOR RUP proof-size cap")
                    if not c:break
                if frozenset() in added:break
            active=base|added;rounds+=1;peak=max(peak,len(active))
            if peak>max_active:raise RuntimeError("XOR RUP active-size cap")
    return dict(steps=steps,rounds=rounds,original_variables=n,
                original_xor_clauses=initial,peak_clauses=peak,
                proof_bytes=output.stat().st_size,
                generation_s=round(time.perf_counter()-started,6))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cnf",type=Path);ap.add_argument("certificate",type=Path)
    ap.add_argument("drat",type=Path)
    a=ap.parse_args()
    print(json.dumps(generate(a.cnf,json.loads(a.certificate.read_text()),a.drat),sort_keys=True))

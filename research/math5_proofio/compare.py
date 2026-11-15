#!/usr/bin/env python3
"""Independently re-encode completed real-instance ASCII proof traces."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'research/math5_proofio/audit.json';d=json.loads(p.read_text());checks=[]
for s in d['summary']:
 idx=s['id'];rows=[r for r in d['trials'] if r['id']==idx and r['rep']==0]
 if not all(r['accepted'] for r in rows):continue
 text=ROOT/'proofio_results'/f'{idx}-0-TEXT/proof.drat.gz'
 binary=ROOT/'proofio_results'/f'{idx}-0-BINARY/proof.drat.gz'
 h=hashlib.sha256();clauses=literals=0
 with gzip.open(text,'rt') as f:
  for line in f:
   ints=list(map(int,line.split()));assert ints[-1]==0
   buf=bytearray(b'a')
   for lit in ints[:-1]:
    u=2*abs(lit)+(lit<0)
    while u>=128:buf.append((u&127)|128);u>>=7
    buf.append(u);literals+=1
   buf.append(0);h.update(buf);clauses+=1
 actual=hashlib.sha256()
 with gzip.open(binary,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):actual.update(chunk)
 assert actual.hexdigest()==h.hexdigest(),idx
 checks.append(dict(id=idx,clauses=clauses,literals=literals,canonical_sha256=h.hexdigest(),identical=True))
d['real_trace_equivalence']=checks;p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
print(json.dumps(checks))

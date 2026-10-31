#!/usr/bin/env python3
"""Non-solving feature analysis. DEVELOPMENT ONLY: previous SAT Competition 2025
cases had known timings and inform candidate V7.3 safety gate. No benchmark
performance from these cases constitutes independent holdout evidence.
"""
import argparse,csv,json,statistics,math,hashlib
from pathlib import Path
def load(path):
    n=0;clauses=[];c=[]
    for row in Path(path).read_text().splitlines():
        if not row or row[0]=="c":continue
        if row[0]=="p":
            bits=row.split(); n=int(bits[2]); continue
        for x in row.split():
            v=int(x)
            if v==0:clauses.append(c);c=[]
            else:c.append(v)
    if c:raise RuntimeError("Unterminated clause")
    return n,clauses

def characterize(path):
    n,clauses=load(path)
    pos=[0]*(n+1);neg=[0]*(n+1)
    # Two stable shards split on clause content, not file order.
    subp=[[0]*(n+1) for _ in range(2)]
    subn=[[0]*(n+1) for _ in range(2)]
    cross=[0]*2
    lengths={}
    distinct_pairs=set()
    sample=clauses[::max(1,len(clauses)//128)][:128]
    pair_count=0
    for c in sample:
        v=sorted(set(abs(x) for x in c))
        for a in range(len(v)):
            for b in range(a+1,len(v)):
                distinct_pairs.add((v[a],v[b]))
                pair_count+=1
    for c in clauses:
        lengths[len(c)]=lengths.get(len(c),0)+1
        # deterministic FNV hash with sign and order invariant
        h=1469598103934665603
        for lit in sorted(c):
            h=(h^(lit+2147483648))*1099511628211 & ((1<<64)-1)
        shard=h & 1
        for lit in c:
            v=abs(lit)
            if lit>0:
                pos[v]+=1;subp[shard][v]+=1
            else:
                neg[v]+=1;subn[shard][v]+=1
    var=[v for v in range(1,n+1) if pos[v]+neg[v]>0]
    maj=[v for v in var if pos[v]+neg[v]>=6 and abs(pos[v]-neg[v])>=0.15*(pos[v]+neg[v]) and pos[v]!=neg[v]]
    stability=[]
    margins=[]
    for v in maj:
        a=subp[0][v]-subn[0][v]; b=subp[1][v]-subn[1][v]
        stability.append(int(a*b>0))
        margins.append(abs(pos[v]-neg[v])/(pos[v]+neg[v]))
    occ=[pos[v]+neg[v] for v in var]
    return dict(vars=n,clauses=len(clauses),density=len(clauses)/max(n,1),
       clauses_3_frac=lengths.get(3,0)/max(len(clauses),1),max_len=max(lengths,default=0),
       mean_occ=statistics.mean(occ) if occ else 0,
       occ_cv=(statistics.pstdev(occ)/statistics.mean(occ)) if occ and statistics.mean(occ) else 0,
       advised_count=len(maj),advised_fraction=len(maj)/max(len(var),1),
       polarity_stability=statistics.mean(stability) if stability else None,
       advised_mean_margin=statistics.mean(margins) if margins else None,
       advised_margin_gt_35=sum(a>0.35 for a in margins)/max(len(margins),1),
       pair_reuse=1-len(distinct_pairs)/pair_count if pair_count else 0,
       avg_clause_size=sum(k*v for k,v in lengths.items())/max(len(clauses),1))
def main(inputs,out):
    d=json.loads(Path(inputs).read_text())
    records=[]
    for group in ("pilot","holdout"):
        for r in d[group]:
            data={"group":group,"family":r["family"],"name":r["name"],"status":r["status"],"sha256":r["observed_sha256"]}
            data.update(characterize(r["path"]))
            records.append(data)
    Path(out).write_text(json.dumps(records,indent=2))
    keys=tuple(records[0])
    with Path(out).with_suffix(".csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(records)
    for r in records:
        print(f"{r['family']:<35s} {r['status']:5s} vars={r['vars']:6d} "
              f"hints={r['advised_fraction']:.3f} stab={r['polarity_stability']!s:<8} "
              f"margin={r['advised_mean_margin']!s:<8} cv={r['occ_cv']:.3f} "
              f"reuse={r['pair_reuse']:.3f}",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--inputs",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();main(a.inputs,a.out)

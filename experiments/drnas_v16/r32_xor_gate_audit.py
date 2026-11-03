#!/usr/bin/env python3
"""R32 read-only XOR gate audit. No SAT/UNSAT claims or CNF modifications."""
import argparse, collections, json, pathlib, subprocess, time, re

def inspect(path, max_clauses=2000000):
    groups=collections.defaultdict(set)
    widths=collections.Counter()
    n=m=0
    clauses=0
    units=0
    start=time.monotonic()
    with open(path,encoding="ascii",errors="replace") as f:
        pending=[]
        for line in f:
            s=line.strip()
            if not s or s.startswith("c"): continue
            if s.startswith("p "):
                parts=s.split()
                if len(parts)!=4 or parts[1]!="cnf": raise ValueError("not DIMACS CNF")
                n,m=map(int,parts[2:]);continue
            for token in s.split():
                v=int(token)
                if v:
                    pending.append(v)
                    continue
                cl=pending;pending=[]
                clauses+=1
                if clauses>max_clauses: return {"skip":"clause_scan_cap","clauses_seen":clauses,"declared_clauses":m}
                k=len(cl);widths[k]+=1
                if k==1: units+=1
                if 2<=k<=6 and len({abs(v) for v in cl})==k:
                    ordered=sorted(cl,key=lambda x:abs(x))
                    key=tuple(abs(x) for x in ordered)
                    mask=sum((1<<i) for i,x in enumerate(ordered) if x<0)
                    groups[key].add(mask)
        if pending or clauses!=m: raise ValueError("incomplete DIMACS")
    full=near=partial=0
    for key,masks in groups.items():
        k=len(key)
        even={i for i in range(1<<k) if i.bit_count()%2==0}
        odd=set(range(1<<k))-even
        if even<=masks or odd<=masks: full+=1
        elif max(len(even&masks),len(odd&masks))>=max(2,(1<<(k-1))-1):near+=1
        elif len(masks)>=2:partial+=1
    return dict(variables=n,clauses=clauses,units=units,widths=dict(widths),
                candidate_groups=len(groups),complete_parity_groups=full,
                near_complete_unproven_groups=near,partial_unproven_groups=partial,
                scan_seconds=round(time.monotonic()-start,6),
                note="Near/partial groups are signals only; NEVER certified XOR equations")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("inputs",nargs="+")
    p.add_argument("--r29")
    p.add_argument("--kissat")
    p.add_argument("--timeout",type=float,default=30)
    p.add_argument("--out",default="r32-gate-audit.json")
    a=p.parse_args()
    rows=[]
    for path in a.inputs:
        row={"path":str(path)}
        try:
            row.update(inspect(path))
            if a.r29 and a.kissat and "skip" not in row:
                start=time.monotonic()
                try:
                    r=subprocess.run([a.r29,str(path),a.kissat,"--classify-only"],
                                     capture_output=True,text=True,timeout=a.timeout)
                    row["r29_exit"]=r.returncode
                    match=re.search(r"^c R29_ROUTE (.+)$",r.stdout,re.M)
                    row["r29_route"]=match.group(1) if match else "no_route"
                    row["r29_stderr_tail"]=r.stderr[-300:]
                except subprocess.TimeoutExpired:
                    row["r29_route"]="classification_timeout"
                row["r29_classify_seconds"]=round(time.monotonic()-start,6)
        except Exception as e:
            row["error"]=str(e)
        rows.append(row)
        print("R32_GATE",json.dumps(row,sort_keys=True),flush=True)
    pathlib.Path(a.out).write_text(json.dumps({"protocol":"R32-read-only-v1",
       "no_solver_modification":True,"rows":rows},indent=2)+"\n")
if __name__=="__main__":main()

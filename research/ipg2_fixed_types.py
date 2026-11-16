#!/usr/bin/env python3
"""IPG2-A exact PCMAX for <=2 distinct job lengths. Polynomial in input size.

For machine k and i assigned jobs of size a, dp[k][i] is the maximum
number of jobs of size b placeable in those machines. Equal-size b jobs can
always fill any subset of those slots. Negative dp means infeasible.

For two job types, O(min(m,n)*n_a^2) transitions, O(n_a) memory,
integer arithmetic polynomial in bit-length of durations. No SAT/CDCL oracle.

This works on explicit PCMAX scheduling instances, NOT arbitrary CNF encodings.
An independent checker must validate the scheduling input and rerun DP.
"""
import hashlib
import json
import pathlib
import sys
import time

def normalized(instance):
    jobs=instance.get("durations")
    m=instance.get("machines")
    cap=instance.get("capacity")
    if not isinstance(jobs,list) or len(jobs)>5000 or not all(type(x)==int and x>0 for x in jobs):
        raise ValueError("durations must be positive integers, n <= 5000")
    if type(m)!=int or m<1 or type(cap)!=int or cap<0:
        raise ValueError("invalid machine count or capacity")
    return jobs,m,cap

def solve(instance):
    begin=time.perf_counter()
    jobs,m,T=normalized(instance)
    n=len(jobs)
    sizes=sorted(set(jobs))
    info={"method":"IPG2_FIXED_TYPES_V1","jobs":n,"types":len(sizes),"machines":m,
          "capacity":T,"status":"UNKNOWN","proof_kind":"NONE"}
    if len(sizes)>2:
        info["reason"]="unsupported_more_than_two_sizes"
        return info
    if not jobs:
        info.update(status="SAT",proof_kind="DIRECT",reason="empty_jobs")
        return info
    if max(jobs)>T:
        info.update(status="UNSAT",proof_kind="SOURCE_ARITHMETIC",reason="single_job_exceeds_capacity")
        return info
    m=min(m,n)
    if len(sizes)==1:
        a=sizes[0]
        total_slots=m*(T//a)
        info.update(status="SAT" if total_slots>=n else "UNSAT",
                    proof_kind="SOURCE_ARITHMETIC",
                    required=n,max_slots=total_slots,reason="single_type")
        return info

    a,b=sizes
    na=jobs.count(a);nb=jobs.count(b)
    # Minimize quadratic DP state dimension; swapping a/b is legitimate.
    if na>nb:
        a,b=b,a
        na,nb=nb,na
    dp=[-1]*(na+1)
    dp[0]=0
    transitions=0
    machine_rows=[]
    for k in range(m):
        nxt=[-1]*(na+1)
        for i,already_b in enumerate(dp):
            if already_b<0:continue
            max_a=min(na-i,T//a)
            for u in range(max_a+1):
                j=i+u
                slots=(T-u*a)//b
                value=min(nb,already_b+slots)
                if value>nxt[j]:nxt[j]=value
                transitions+=1
        dp=nxt
        if m<=20 and na<=60:machine_rows.append(dp[:])
    info.update(
        status="SAT" if dp[na]>=nb else "UNSAT",
        proof_kind="EXACT_TWO_TYPE_DP",
        reason="complete_dynamic_program",
        sizes=[a,b],counts=[na,nb],
        dp_last=dp,transitions=transitions,
        dp_rows=machine_rows,
        elapsed_s=round(time.perf_counter()-begin,7),
        complexity="O(min(m,n)*n_a^2) integer arithmetic, O(n_a) memory")
    return info

def canonical_sha(instance):
    return hashlib.sha256(json.dumps(instance,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("instance",type=pathlib.Path)
    p.add_argument("--certificate",type=pathlib.Path,required=True)
    ns=p.parse_args()
    data=json.loads(ns.instance.read_text())
    result=solve(data)
    result["schedule_sha256"]=canonical_sha(data)
    ns.certificate.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("IPG2_FIXED_RESULT "+json.dumps({k:v for k,v in result.items() if k not in ("dp_last","dp_rows")},sort_keys=True))
    return 0
if __name__=="__main__":sys.exit(main())

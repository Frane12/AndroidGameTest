#!/usr/bin/env python3
"""Independent fixed-two-type PCMAX DP checker, source-bound scheduling JSON.

This validates source SHA and rederives exact recurrence in a separately
implemented verifier. The result is an arithmetic proof for the scheduling
instance, NOT a CNF DRAT/VeriPB proof.
"""
import hashlib
import json
import pathlib
import sys

def check(schedule,certificate):
    if certificate.get("method")!="IPG2_FIXED_TYPES_V1":
        raise ValueError("bad method")
    digest=hashlib.sha256(json.dumps(schedule,sort_keys=True,
                     separators=(",",":")).encode()).hexdigest()
    if certificate.get("schedule_sha256")!=digest:
        raise ValueError("schedule hash mismatch")
    times=schedule["durations"]
    machines=schedule["machines"]
    T=schedule["capacity"]
    if type(machines)!=int or machines<1 or type(T)!=int or T<0:
        raise ValueError("bad machine count or capacity")
    if not isinstance(times,list) or any(type(t)!=int or t<=0 for t in times):
        raise ValueError("bad job sizes")
    if len(times)>5000:raise ValueError("source too large")
    sizes=sorted(set(times))
    if len(sizes)>2:
        if certificate.get("status")!="UNKNOWN":
            raise ValueError("unsupported three-type source claimed solved")
        return {"status":"IPG2_UNKNOWN_CORRECT","types":len(sizes)}
    if not times:
        expected="SAT";reason="empty_jobs"
    elif max(times)>T:
        expected="UNSAT";reason="single_job_exceeds_capacity"
    elif len(sizes)==1:
        expected="SAT" if min(machines,len(times))*(T//sizes[0])>=len(times) else "UNSAT"
        reason="single_type"
    else:
        a,b=sizes
        na=times.count(a);nb=times.count(b)
        if na>nb:
            a,b=b,a;na,nb=nb,na
        m=min(machines,len(times))
        # Different iteration order from producer, same exact recurrence.
        dp=[-1]*(na+1)
        dp[0]=0
        for _ in range(m):
            next_dp=[-1]*(na+1)
            for count_a in range(na+1):
                low=max(0,count_a-(T//a))
                for prior in range(low,count_a+1):
                    if dp[prior]<0:continue
                    new_a=count_a-prior
                    residual=T-a*new_a
                    value=min(nb,dp[prior]+residual//b)
                    if value>next_dp[count_a]:next_dp[count_a]=value
            dp=next_dp
        if certificate.get("dp_last")!=dp:
            raise ValueError("certificate DP table differs from exact recurrence")
        expected="SAT" if dp[na]>=nb else "UNSAT"
        reason="complete_dynamic_program"
        if certificate.get("sizes")!=[a,b] or certificate.get("counts")!=[na,nb]:
            raise ValueError("certificate job type counts mismatch")
    if certificate.get("status")!=expected or certificate.get("reason")!=reason:
        raise ValueError("source DP certificate verdict mismatch")
    return {"status":"IPG2_FIXED_ARITHMETIC_VERIFIED",
            "verdict":expected,"types":len(sizes),"jobs":len(times)}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("schedule",type=pathlib.Path)
    p.add_argument("certificate",type=pathlib.Path)
    ns=p.parse_args()
    try:
        result=check(json.loads(ns.schedule.read_text()),
                     json.loads(ns.certificate.read_text()))
        print("IPG2_DP_VERIFIED "+json.dumps(result,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        print("IPG2_DP_REJECTED "+str(e))
        return 1
if __name__=="__main__":sys.exit(main())

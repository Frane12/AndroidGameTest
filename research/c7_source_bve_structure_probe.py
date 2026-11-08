#!/usr/bin/env python3
"""C7-S structural BVE proxy: source-only causal contrast of duplicate removal.

Counts unique signed literal occurrences in ORIGINAL and certified-dedup CNF.
For each variable x, proxy candidate if p(x)>0, n(x)>0 and
p(x)*n(x) <= p(x)+n(x); this is ONLY a cheap raw-resolvent-count bound,
not actual CMS/CaDiCaL/Kissat BVE (which removes tautological resolvents,
uses gates, dynamic scores, subsumption, inprocessing).
It cannot prove the solver's internal BVE ordering nor a speedup.
"""
from __future__ import annotations
import collections,hashlib,json,pathlib
import c7_standard_solver_bve_crosscheck as c7
import c2_cnf_clean_ablation as c2

OUT=pathlib.Path("c7_structure")
def need(b,msg):
    if not b:raise RuntimeError("C7_STRUCT_FAIL_CLOSED "+str(msg))
def variable_uses(n,clauses):
    counts=[[0,0] for _ in range(n+1)]
    for clause in clauses:
        for x in set(clause):
            counts[abs(x)][0 if x>0 else 1]+=1
    return counts
def eligibility(c):
    p,n=c
    return p>0 and n>0 and p*n<=p+n
def compare(n,raw,der):
    r=variable_uses(n,raw)
    d=variable_uses(n,der)
    delta=[]
    for v in range(1,n+1):
        p,q=r[v];pd,qd=d[v]
        need(pd<=p and qd<=q,"source dedup increased a literal count")
        old=eligibility(r[v]);new=eligibility(d[v])
        if (p,q)!=(pd,qd):
            delta.append(dict(var=v,source_pos=p,source_neg=q,
                dedup_pos=pd,dedup_neg=qd,
                source_pairs=p*q,dedup_pairs=pd*qd,
                source_eligible=old,dedup_eligible=new,
                extra_occurrences=(p-pd)+(q-qd)))
    flips_on=sum(not eligibility(r[v]) and eligibility(d[v])
                 for v in range(1,n+1))
    flips_off=sum(eligibility(r[v]) and not eligibility(d[v])
                 for v in range(1,n+1))
    n_var=len(delta)
    top=sorted(delta,key=lambda a:(-a["extra_occurrences"],a["var"]))[:12]
    return dict(vars=n,variables_with_duplicate_inflated_occurrences=n_var,
        eligible_proxy_original=sum(eligibility(r[v]) for v in range(1,n+1)),
        eligible_proxy_dedup=sum(eligibility(d[v]) for v in range(1,n+1)),
        proxy_flips_ineligible_to_eligible=flips_on,
        proxy_flips_eligible_to_ineligible=flips_off,
        signed_occurrences_original=sum(sum(x) for x in r),
        signed_occurrences_dedup=sum(sum(x) for x in d),
        raw_resolvent_pair_sum_original=sum(p*q for p,q in r),
        raw_resolvent_pair_sum_dedup=sum(p*q for p,q in d),
        most_duplicate_inflated_vars=top)
def run():
    n,raw=3,[(1,2),(1,2),(1,2),(-1,3),(-1,3),(-1,3)]
    _,der=3,[(1,2),(-1,3)]
    test=compare(n,raw,der)
    need(test["proxy_flips_ineligible_to_eligible"]==1 and
         test["proxy_flips_eligible_to_ineligible"]==0,
         "synthetic BVE proxy cannot detect a known duplicate-induced eligibility flip")
    cc,manifest=c7.get_cases()
    result=[]
    for c in cc:
        derived=c7.DEDUP/(c["gbd"]+".cnf")
        src=c["path"]
        need(c7.digest(src)==c["sha256"] and
             c7.digest(derived)==manifest["sources"][c["sha256"]]["derived_sha256"],
             "source/derived SHA changed")
        n,raw=c2.read_clauses(src);m,der=c2.read_clauses(derived)
        need(n==m and set(c7.canonical(raw))==set(c7.canonical(der)),
             "source/dedup canonical clause set mismatch")
        data=compare(n,raw,der)
        data.update(gbd=c["gbd"],source_sha256=c["sha256"],
             original_clauses=len(raw),dedup_clauses=len(der),
             duplicates=len(raw)-len(der),
             source_control=bool(c["control"]))
        if c["control"]:
            need(data["duplicates"]==0 and
                 data["variables_with_duplicate_inflated_occurrences"]==0 and
                 data["proxy_flips_ineligible_to_eligible"]==0 and
                 data["proxy_flips_eligible_to_ineligible"]==0,
                 "source without duplicates created phantom BVE proxy change")
        result.append(data)
        print("C7_BVE_PROXY",json.dumps({k:v for k,v in data.items()
            if k!="most_duplicate_inflated_vars"},sort_keys=True),flush=True)
    need(len(result)==6,"six case coverage incomplete")
    OUT.mkdir(exist_ok=True)
    report=dict(protocol="C7-STRUCTURE-ORIGINAL-VS-EXACT-DEDUP-BVE-OCCURRENCE-PROXY-v1",
        test="source-only, no CDCL run; proxy not measured actual BVE elimination",
        case_count=6,originals_previously_studied_development_not_blind=True,
        source_SHA_pinned=True,source_equivalent=True,
        proxy_rule="positive_occurrences*negative_occurrences <= their sum, both positive",
        cases=result)
    (OUT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("C7_BVE_PROXY_FINAL",json.dumps(dict(
        cases=len(result),dupe_cases=sum(x["duplicates"]>0 for x in result),
        variable_counts_changed=sum(x["variables_with_duplicate_inflated_occurrences"]
                                    for x in result),
        eligible_flips_on=sum(x["proxy_flips_ineligible_to_eligible"] for x in result),
        eligible_flips_off=sum(x["proxy_flips_eligible_to_ineligible"] for x in result)
    ),sort_keys=True),flush=True)
if __name__=="__main__":run()

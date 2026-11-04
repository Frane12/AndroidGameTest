#!/usr/bin/env python3
"""R89: bounded cooperative gate with fail-closed XOR proof policy."""
import argparse, json, time
from pathlib import Path
import r88_cooperative as r88

def cost_gate(clauses, budget_s=0.05, max_probes=24):
    start=time.monotonic()
    groups, bridges, _=r88.partition(clauses)
    verified=[]; trace=[]; known=set(clauses); probes=0
    for gid,local in enumerate(groups):
        if not local: continue
        for assumptions in r88.assumptions_for_round(bridges,0):
            if probes>=max_probes or time.monotonic()-start>=budget_s:
                return verified,dict(probes=probes,reason="budget",trace=trace)
            probes+=1
            if not r88.bcp_conflict(local+verified,assumptions):continue
            lemma=tuple(sorted((-x for x in assumptions),key=lambda x:(abs(x),x)))
            if lemma in known or any(-x in lemma for x in lemma):continue
            # Independent full-source RUP replay; no trust in local solver flags.
            if not r88.bcp_conflict(clauses+verified,[-x for x in lemma]):
                trace.append(dict(group=gid,lemma=lemma,accepted=False,reason="RUP_FAILED"))
                continue
            verified.append(lemma);known.add(lemma)
            trace.append(dict(group=gid,lemma=lemma,accepted=True,reason="RUP_VERIFIED"))
    return verified,dict(probes=probes,reason="complete",trace=trace)

def xor_proof_gate(record):
    """Fail closed until immutable ancestry and independent replay exist."""
    required=("original_equation_ids","row_ancestry","pivot","variable_order",
              "normalization","implied_clause")
    missing=[k for k in required if k not in record]
    return dict(accepted=False,reason="MISSING_PROOF_METADATA" if missing else
                "INDEPENDENT_XOR_VERIFIER_NOT_IMPLEMENTED",missing=missing,
                pivot=record.get("pivot"))

def selftest():
    clauses=[(1,2),(-1,2),(1,-2)]
    extra,t=cost_gate(clauses,1.0)
    assert all(r88.bcp_conflict(clauses+extra[:i],[-x for x in c])
               for i,c in enumerate(extra))
    assert not xor_proof_gate(dict(pivot=484))["accepted"]
    assert not xor_proof_gate(dict(pivot=491))["accepted"]
    zero,diag=cost_gate(clauses,0.0)
    assert not zero and diag["reason"]=="budget"
    print("R89_SELFTEST_PASS",json.dumps(dict(lemmas=len(extra),probes=t["probes"],
           xor_pivots=[484,491],zero_lemma_bypass=True)))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["selftest","inspect"])
    p.add_argument("--cnf")
    p.add_argument("--out",default="r89-diagnostic.json")
    p.add_argument("--budget",type=float,default=0.05)
    a=p.parse_args()
    if a.command=="selftest":return selftest()
    assert a.cnf and 0<=a.budget<=1
    path=Path(a.cnf); n,clauses=r88.read_cnf(path)
    extras,t=cost_gate(clauses,a.budget)
    result=dict(source_sha256=r88.sha(path),variables=n,clauses=len(clauses),
                certified_rup_lemmas=len(extras),bypass=not bool(extras),
                xor_injection_enabled=False,telemetry=t)
    Path(a.out).write_text(json.dumps(result,indent=2)+"\n")
    print("R89_DIAGNOSTIC_PASS",json.dumps({k:v for k,v in result.items() if k!="telemetry"}))
if __name__=="__main__":main()

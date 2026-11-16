#!/usr/bin/env python3
"""IPG-BDD3 -> STANDARD VeriPB when a 3-class nonnegative SCALAR separator exists.

This is a deliberately limited proof bridge: it does NOT translate arbitrary
three-dimensional state exclusion (including non-convex or modular gaps) into
VeriPB. The source-bound IPG-BDD3 JSON is independently verified first.
Candidate class-linear objectives (alpha,beta,gamma) are searched. If some
objective satisfies sum_j w_j > sum_machine max_accepting_BDD(sum_selector w_j),
an ordinary source-grounded weighted capacity certificate and an existing
cutting-planes VeriPB 3.0 proof are generated.

A BDD3 count proof may exist even if NO SUCH scalar separator exists.
Output on no separator is UNKNOWN, never a false UNSAT claim.
Each positive proof MUST be externally checked by VeriPB 3.0.2 against
the *unchanged* original CNF. No SAT/CDCL or extra worker process is used
by this converter. The conversion is retrospective research, not proof that
the full 3D argument has a standard PB encoding.
"""
import argparse
import hashlib
import itertools
import json
import math
import pathlib
import sys
import time

from ipg_bdd3_checker import independently_check
from pcmax_capacity.check_capacity import check as structural_check
from pcmax_capacity.emit_veripb_capacity_weighted2 import generate as emit_veripb

MAX_ALPHA=12
MAX_SEARCH_SECONDS=20.0

def exact_machine_bound(machine,selector_weight):
    """Exact maximum nonnegative scalar weight over ALL accepted BDD paths.

    All skipped selectors remain free; their weights must be INCLUDED.
    Distinct from the triple-count producer; derives a valid weighted upper
    bound directly from source-BDD topology.
    """
    order=machine["variable_order"]
    rank={v:i for i,v in enumerate(order)}
    root=machine["root"]
    yes=machine["true_terminal"]
    no=machine["false_terminal"]
    transitions={p:(x,lo,hi) for p,x,lo,hi in machine["transitions"]}
    if root not in transitions or len(transitions)!=len(machine["transitions"]):
        raise ValueError("invalid BDD root/repeated node")
    rnk={p:rank[x] for p,(x,lo,hi) in transitions.items()}
    rnk[yes]=rnk[no]=len(order)
    prefix=[0]
    for x in order:
        prefix.append(prefix[-1]+selector_weight.get(x,0))
    best={yes:0,no:None}
    for parent in sorted(transitions,key=lambda x:rnk[x],reverse=True):
        selector,lo,hi=transitions[parent]
        candidates=[]
        for child,pick in ((lo,0),(hi,selector_weight.get(selector,0))):
            if child not in best:
                raise ValueError("cycle/forward-reference in BDD")
            if best[child] is None:continue
            gap=prefix[rnk[child]]-prefix[rnk[parent]+1]
            if gap<0:raise ValueError("negative skipped level")
            candidates.append(best[child]+gap+pick)
        best[parent]=max(candidates) if candidates else None
    if best[root] is None:raise ValueError("BDD has no accepting source path")
    return prefix[rnk[root]]+best[root]

def directions(max_weight):
    # Enumerate small primitive integer normals, including nonnegative
    # coordinate axes, to test supporting scalar inequalities.
    candidates=[]
    for triple in itertools.product(range(max_weight+1),repeat=3):
        if not any(triple):continue
        nonzero=[v for v in triple if v]
        if math.gcd(*nonzero)!=1:continue
        candidates.append(triple)
    candidates.sort(key=lambda t:(max(t),sum(t),-sum(v>0 for v in t),t))
    return candidates

def bridge(raw,graph,three_cert,max_alpha=MAX_ALPHA,
           time_limit=MAX_SEARCH_SECONDS):
    begin=time.monotonic()
    if hashlib.sha256(raw).hexdigest()!=three_cert.get("source_sha256"):
        raise ValueError("source changed since IPG-BDD3 proof")
    checked=independently_check(raw,graph,three_cert)
    if checked["status"]!="IPG_BDD3_SOURCE_UNSAT_VERIFIED":
        raise ValueError("independent 3D source checker rejected")
    groups=graph["eligible_groups"]
    classes=three_cert["classes"]
    allowed=[None]*len(groups)
    for k,group in enumerate(classes):
        for j in group:
            allowed[j]=k
    metadata={
        "status":"NO_NONNEGATIVE_SCALAR_SEPARATOR",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "3d_source_verified":True,
        "3d_classes":[len(x) for x in classes],
        "directions_checked":0,
        "max_alpha":max_alpha,
        "bridge_kind":"CLASS_WEIGHTED_SCALAR_SEPARATOR_ONLY",
    }
    for v in directions(max_alpha):
        if time.monotonic()-begin>time_limit:
            metadata["status"]="SEARCH_BUDGET_EXHAUSTED"
            break
        wbygroup=[v[k] if k is not None else 0 for k in allowed]
        demand=sum(wbygroup)
        if not demand:continue
        selected={}
        for j,w in enumerate(wbygroup):
            if w:
                for x in groups[j]:
                    selected[x]=w
        caps=[exact_machine_bound(machine,selected)
              for machine in graph["machine_graphs"]]
        metadata["directions_checked"]+=1
        if demand>sum(caps):
            intermediate={
                "format":"pcmax-capacity-v1",
                "source_sha256":metadata["source_sha256"],
                "selected_groups":[groups[j] for j,w in enumerate(wbygroup) if w>0],
                "group_weights":[w for w in wbygroup if w>0],
                "required":demand,
                "capacity_sum":sum(caps),
                "machines":[{**machine,"capacity":c}
                            for machine,c in zip(graph["machine_graphs"],caps)],
            }
            native_check=structural_check(raw,intermediate)
            if native_check.get("status")!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
                raise ValueError("independent weighted scalar verifier rejected")
            metadata.update(
                status="SCALAR_SOURCE_BOUND_VERIFIED_PB_NOT_YET",
                objective=list(v),required=demand,capacity=sum(caps),
                delta=demand-sum(caps),
                selected_job_groups=len(intermediate["selected_groups"]),
                time_s=round(time.monotonic()-begin,6),
            )
            return metadata,intermediate
    metadata["time_s"]=round(time.monotonic()-begin,6)
    return metadata,None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--graph",required=True,type=pathlib.Path)
    p.add_argument("--bdd3-certificate",required=True,type=pathlib.Path)
    p.add_argument("--capacity-certificate",required=True,type=pathlib.Path)
    p.add_argument("--pb-proof",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--max-alpha",type=int,default=MAX_ALPHA)
    p.add_argument("--search-seconds",type=float,default=MAX_SEARCH_SECONDS)
    a=p.parse_args()
    a.meta.parent.mkdir(parents=True,exist_ok=True)
    try:
        if not 1<=a.max_alpha<=32 or not 0<a.search_seconds<=120:
            raise ValueError("invalid bounded search options")
        raw=a.cnf.read_bytes()
        graph=json.loads(a.graph.read_text())
        cert=json.loads(a.bdd3_certificate.read_text())
        report,capacity=bridge(raw,graph,cert,a.max_alpha,a.search_seconds)
        if capacity is not None:
            a.capacity_certificate.write_text(json.dumps(capacity,sort_keys=True,indent=2)+"\n")
            generated=emit_veripb(a.cnf,a.capacity_certificate,a.pb_proof)
            report.update(
                status="EMITTED_VERIPB_NEEDS_EXTERNAL_CHECK",
                pb_format="VeriPB3.0",
                proof_bytes=generated["proof_bytes"],
                proof_source_sha256=generated["source_sha256"],
                pb_machine_state_lemmas=generated["pbc_state_lemmas"],
                pb_producer_s=generated["generator_s"],
            )
        else:
            a.capacity_certificate.unlink(missing_ok=True)
            a.pb_proof.unlink(missing_ok=True)
        a.meta.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        print("IPG_BDD3_TO_VERIPB "+json.dumps(report,sort_keys=True),flush=True)
        return 0
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as exc:
        a.capacity_certificate.unlink(missing_ok=True)
        a.pb_proof.unlink(missing_ok=True)
        report={"status":"UNKNOWN_OR_CONVERTER_ERROR","reason":str(exc)}
        a.meta.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        print("IPG_BDD3_TO_VERIPB "+json.dumps(report,sort_keys=True),flush=True)
        return 1

if __name__=="__main__":
    sys.exit(main())

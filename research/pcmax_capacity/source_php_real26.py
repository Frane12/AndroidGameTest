#!/usr/bin/env python3
"""PCMAX REAL26 DIRECT PHP discovery, purely from unchanged original CNF bytes.

No CDCL, no case labels, no prior CNF layouts, no access to the expected n/m.
Conservative result: prove only a partition into source-verified mutex cliques
with more pairwise disjoint positive source clauses than resource cliques.
All generated certificates must pass independent check_php_partition.py.
"""
from collections import defaultdict
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MAX_CLAUSES = 1_000_000
MAX_VARIABLES = 200_000
MAX_SIZE = 15_000_000

def discover(path):
    started=time.perf_counter()
    if path.stat().st_size>MAX_SIZE:
        return dict(status="UNKNOWN",reason="size_gate")
    raw=path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    groups=set()
    neg_pairs=set()
    header=None
    clauses=0
    current=[]
    for line in raw.splitlines():
        fields=line.split()
        if not fields or fields[0]==b'c':continue
        if fields[0]==b'p':
            if header is not None or len(fields)!=4 or fields[1]!=b'cnf':
                return dict(status="UNKNOWN",reason="header_invalid")
            n,m=map(int,fields[2:])
            if n>MAX_VARIABLES or m>MAX_CLAUSES:
                return dict(status="UNKNOWN",reason="size_gate")
            header=n,m
            continue
        if header is None:return dict(status="UNKNOWN",reason="missing_header")
        for x in fields:
            lit=int(x)
            if lit:
                if abs(lit)>header[0]:
                    return dict(status="UNKNOWN",reason="invalid_literal")
                current.append(lit)
            else:
                c=current;current=[]
                clauses+=1
                if len(c)==2 and c[0]<0 and c[1]<0:
                    a,b=sorted((-c[0],-c[1]))
                    if a!=b:neg_pairs.add((a,b))
                if len(c)>=2 and all(v>0 for v in c) and len(set(c))==len(c):
                    groups.add(tuple(sorted(c)))
    if current or not header or clauses!=header[1]:
        return dict(status="UNKNOWN",reason="bad_dimacs_clause_count")
    if len(groups)<3 or len(groups)>256:
        return dict(status="UNKNOWN",reason="disjoint_alo_gate",positive_groups=len(groups))
    groups=sorted(groups)
    owner={}
    for gi,group in enumerate(groups):
        for v in group:
            if v in owner:
                return dict(status="UNKNOWN",reason="overlapping_alo_groups",positive_groups=len(groups))
            owner[v]=gi
    # Only source-confirmed groups; all declared variables must participate
    # in the partition to avoid treating arbitrary auxiliary variables as jobs.
    if len(owner)!=header[0] or len(owner)>MAX_VARIABLES:
        return dict(status="UNKNOWN",reason="incomplete_alo_cover",
                    positive_groups=len(groups),selected=len(owner),variables=header[0])
    cross=defaultdict(set)
    for a,b in neg_pairs:
        if a in owner and b in owner and owner[a]!=owner[b]:
            cross[a].add(b)
            cross[b].add(a)
    if not cross:
        return dict(status="UNKNOWN",reason="no_cross_group_mutex")
    parent={x:x for x in owner}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def merge(a,b):
        pa,pb=find(a),find(b)
        if pa!=pb:parent[pb]=pa
    # Options from one job with identical cross-group conflict neighborhoods
    # represent candidates for the same resource. No variable ordering assumed.
    for group in groups:
        signatures={}
        for v in group:
            signature=tuple(sorted(cross[v]))
            prev=signatures.get(signature)
            if prev is None:signatures[signature]=v
            else:merge(v,prev)
    for a,b in neg_pairs:
        if a in owner and b in owner and owner[a]!=owner[b]:
            merge(a,b)
    comps=defaultdict(list)
    for v in owner:comps[find(v)].append(v)
    resources=sorted((sorted(group) for group in comps.values()),
                     key=lambda g:(g[0],len(g)))
    # A resource must be an EXACT clique. Every pairwise mutex is source-given.
    for group in resources:
        if len(group)<2:return dict(status="UNKNOWN",reason="isolated_resource")
        for i,a in enumerate(group):
            for b in group[i+1:]:
                if (min(a,b),max(a,b)) not in neg_pairs:
                    return dict(status="UNKNOWN",reason="resource_not_clique",
                                resources=len(resources),groups=len(groups))
    if len(resources)>=len(groups):
        return dict(status="UNKNOWN",reason="no_capacity_deficit",
                    resources=len(resources),groups=len(groups))
    cert=dict(format="DRNAS-source-clique-capacity-v1",source_sha256=digest,
              source_variables=header[0],source_clauses=header[1],
              selected_groups=groups,capacity_cliques=resources,
              demand=len(groups),capacity=len(resources))
    return dict(status="CERTIFICATE_EMITTED_UNCHECKED",certificate=cert,
                groups=len(groups),resources=len(resources),deficit=len(groups)-len(resources),
                time_s=round(time.perf_counter()-started,6))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    manifests=sorted(a.archive.rglob("summary.json"))
    if len(manifests)!=4:raise SystemExit("Missing 4 frozen real26 shards")
    checker=(Path(__file__).parent/"check_php_partition.py").resolve()
    cases=[]
    for manifest in manifests:
        source=json.loads(manifest.read_text())
        for item in source["cases"]:
            candidates=list(manifest.parent.rglob("*"+item["md5"]+".cnf"))
            if not candidates:
                case=dict(source_id=item["md5"],family=item["family"],
                          label_for_reporting=item["label"],
                          status="SOURCE_NOT_ARCHIVED",reason="archive_limit")
            else:
                cnf=candidates[0]
                if hashlib.sha256(cnf.read_bytes()).hexdigest()!=item["source_sha256"]:
                    raise AssertionError("source_sha256_mismatch")
                started=time.perf_counter()
                result=discover(cnf)
                cert=result.pop("certificate",None)
                case=dict(source_id=item["md5"],family=item["family"],
                          label_for_reporting=item["label"],
                          source_sha256=item["source_sha256"],
                          variables=item["variables"],clauses=item["clauses"],
                          **result)
                case["discovery_s"]=round(time.perf_counter()-started,6)
                case["checker_s"]=None
                if cert is not None:
                    outpath=a.out/(item["md5"]+".certificate.json")
                    outpath.write_text(json.dumps(cert,sort_keys=True)+"\n")
                    t=time.perf_counter()
                    checked=subprocess.run([sys.executable,str(checker),str(cnf),str(outpath)],
                                           capture_output=True,text=True,timeout=90)
                    case["checker_s"]=round(time.perf_counter()-t,6)
                    if checked.returncode==0 and "UNSAT_SOURCE_CLIQUE_VERIFIED" in checked.stdout:
                        case["status"]="UNSAT_SOURCE_CLIQUE_VERIFIED"
                    else:
                        case["status"]="CERTIFICATE_REJECTED"
                        case["checker_error"]=(checked.stderr+checked.stdout)[-400:]
                if item["label"]=="sat" and case["status"]=="UNSAT_SOURCE_CLIQUE_VERIFIED":
                    case["status"]="CRITICAL_FALSE_UNSAT_SAT_CATALOG"
            cases.append(case)
            print("PHP_REAL26_CASE "+json.dumps({k:case.get(k) for k in
                  ("source_id","family","status","reason","groups","resources",
                   "deficit","discovery_s","checker_s")},sort_keys=True),flush=True)
    cases.sort(key=lambda x:x["source_id"])
    (a.out/"cases.json").write_text(json.dumps(cases,indent=2)+"\n")
    summary=dict(total=len(cases),
                 checked_unsat=sum(x["status"]=="UNSAT_SOURCE_CLIQUE_VERIFIED" for x in cases),
                 unchecked=sum(x["status"]=="CERTIFICATE_EMITTED_UNCHECKED" for x in cases),
                 rejected=sum(x["status"]=="CERTIFICATE_REJECTED" for x in cases),
                 errors=sum(x["status"].startswith("CRITICAL") for x in cases))
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("PHP_REAL26_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)
    if summary["rejected"] or summary["errors"] or len(cases)!=16:
        raise SystemExit("Failed source-clique audit")

if __name__=="__main__":main()

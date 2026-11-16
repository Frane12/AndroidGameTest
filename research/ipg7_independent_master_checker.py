#!/usr/bin/env python3
"""IPG7 independent ORIGINAL-CNF/config-master checker, NO generator imports.

Verifies EXACT original direct bin-packing CNF in source, independently
reconstructing ALL minimal-overweight clauses and one-hot groups from
claimed weights/capacity. Enumerates every exact-T subset by independent
itertools.combinations, checks source SHA, total load 3T, k candidate
configurations and EVERY pair intersection.

If UNSAT: independently checks the derived 2-machine master CNF and the
exact 7-step (k+1 generally) cutting-planes proof structure, but an
EXTERNAL VeriPB 3.0.2 run is mandatory to certify the master UNSAT.
The original CNF is NOT directly checked by VeriPB; this checker is
the explicit sound bridge from original source to derived master.

If SAT: independently checks all true assignments against EVERY
original source clause, plus the three exact-capacity bin masks.

A source that lacks ANY minimal-overweight clause, or has ANY extra
unexplained clause, FAILS closed. Input file names and expected SAT/UNSAT
labels play no role. Exponential enumeration, max n=15.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter

def parse(raw):
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        words=line.split()
        if not words or words[0]=="c":continue
        if words[0]=="p":
            if nv is not None or len(words)!=4 or words[1]!="cnf":
                raise ValueError("unexpected original DIMACS header")
            nv,nc=int(words[2]),int(words[3])
            continue
        if nv is None:raise ValueError("clauses before header")
        for item in words:
            value=int(item)
            if abs(value)>nv:raise ValueError("original literal beyond dimension")
            if value:pending.append(value)
            else:clauses.append(tuple(pending));pending=[]
    if nv is None or pending or len(clauses)!=nc:
        raise ValueError("original clauses incomplete")
    return nv,clauses

def normalize(clauses):
    return Counter(tuple(sorted(c)) for c in clauses)

def independent_encode(weights,T):
    # Independent COMBINATORIAL enumeration by subsets of every size.
    # No subset-sum bitmask recurrence and no code imported from producer.
    n=len(weights)
    source=[]
    for j in range(n):
        xs=(3*j+1,3*j+2,3*j+3)
        source.append(xs)
        source.extend((-xs[a],-xs[b]) for a,b in
                      itertools.combinations(range(3),2))
    for size in range(1,n+1):
        for subset in itertools.combinations(range(n),size):
            total=sum(weights[j] for j in subset)
            if total<=T:continue
            if any(total-weights[j]>T for j in subset):
                continue
            for m in range(3):
                source.append(tuple(-3*j-m-1 for j in subset))
    return source

def exact_masks(weights,T):
    out=[]
    for size in range(len(weights)+1):
        for subset in itertools.combinations(range(len(weights)),size):
            if sum(weights[j] for j in subset)==T:
                out.append(sum(1<<j for j in subset))
    return sorted(out)

def verify_source(original,cert):
    raw=original.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    if cert.get("format")!="DRNAS-IPG7-SOURCE-CONFIG-MASTER-V1" or (
        cert.get("source_sha256")!=sha):
        raise ValueError("certificate not bound to exact original bytes")
    w=cert.get("weights");T=cert.get("machine_capacity")
    if (not isinstance(w,list) or not 2<=len(w)<=15 or
        any(type(v)!=int or not 0<v<=100000 for v in w) or
        type(T)!=int or not 0<T<=200000 or
        cert.get("machine_count")!=3):
        raise ValueError("invalid 3-machine direct encoding specification")
    nv,clauses=parse(raw)
    if nv!=3*len(w):
        raise ValueError("original does not contain claimed job selectors")
    expected=independent_encode(w,T)
    if normalize(clauses)!=normalize(expected) or len(clauses)!=len(expected):
        raise ValueError("original source not equal complete capacity encoding")
    if cert.get("source_vars")!=nv or cert.get("source_clauses")!=len(clauses):
        raise ValueError("claimed source dimensions wrong")
    if sum(w)!=3*T or cert.get("total_weight")!=sum(w):
        raise ValueError("total load not exactly 3 machine capacities")
    configurations=exact_masks(w,T)
    if configurations!=cert.get("exact_capacity_masks") or (
        cert.get("exact_capacity_config_count")!=len(configurations)):
        raise ValueError("claimed complete exact capacity profile is incomplete")
    return sha,nv,clauses,configurations

def verify_sat(source,certificate):
    sha,nv,clauses,configs=verify_source(source,certificate)
    if certificate.get("status")!="SAT_MODEL_VERIFIED_BY_GENERATOR":
        raise ValueError("certificate is not SAT")
    masks=certificate.get("three_machine_masks")
    literals=certificate.get("true_model_literals")
    n=nv//3
    if (not isinstance(masks,list) or len(masks)!=3 or
        any(type(m)!=int or m<0 or m>=(1<<n) for m in masks) or
        not isinstance(literals,list)):
        raise ValueError("malformed source SAT assignment")
    if any(m not in configs for m in masks) or (
        masks[0]&masks[1] or masks[0]&masks[2] or masks[1]&masks[2]):
        raise ValueError("assigned machine jobs not disjoint exact-T profiles")
    if (masks[0]|masks[1]|masks[2])!=(1<<n):
        raise ValueError("not all jobs assigned")
    expected=[3*j+m+1 for j in range(n) for m in range(3) if (masks[m]>>j)&1]
    if literals!=expected:raise ValueError("claimed original SAT variables differ")
    true=set(literals)
    if not all(any((lit in true) if lit>0 else (-lit not in true)
                   for lit in c) for c in clauses):
        raise ValueError("model fails an original source CNF clause")
    return {"status":"IPG7_ORIGINAL_CNF_SAT_MODEL_VERIFIED",
            "source_sha256":sha,"original_clauses":len(clauses),
            "original_vars":nv,"config_count":len(configs),
            "machine_job_count":[m.bit_count() for m in masks]}

def verify_unsat(source,certificate,master_source,proof):
    sha,nv,clauses,configs=verify_source(source,certificate)
    if certificate.get("status")!="UNSAT_SOURCE_STRUCTURAL_CANDIDATE_MASTER_VERIPB_UNCHECKED":
        raise ValueError("certificate does not assert master UNSAT")
    k=len(configs)
    if not 1<=k<=512:
        raise ValueError("unsupported complete config count")
    if any(not(a&b) for a in configs for b in configs):
        raise ValueError("source has two disjoint exact-T configurations -- SAT")
    mr=master_source.read_bytes()
    if certificate.get("master_sha256")!=hashlib.sha256(mr).hexdigest():
        raise ValueError("derived master bytes changed")
    mn,mc=parse(mr)
    if mn!=2*k or len(mc)!=2+k*k:
        raise ValueError("derived master dimensions wrong")
    expected=[tuple(range(1,k+1)),tuple(range(k+1,2*k+1))]
    expected.extend((-(a+1),-(k+b+1)) for a in range(k) for b in range(k))
    if normalize(mc)!=normalize(expected):
        raise ValueError("master does not encode complete cross-machine conflicts")
    if (certificate.get("master_variables")!=mn or
        certificate.get("master_clauses")!=len(mc) or
        certificate.get("master_pure_POL_steps")!=k+1 or
        certificate.get("master_RUP_steps")!=0 or
        certificate.get("every_exact_config_pair_intersects") is not True):
        raise ValueError("master proof metadata invalid")
    # Independent proof SOURCE-ID check. VeriPB is still the authoritative
    # external checker on the derived master. Proof has ONLY POL commands.
    lines=proof.read_text().splitlines()
    if (lines[:2]!=["pseudo-Boolean proof version 3.0",
                    f"f {len(mc)} ;"] or
        lines[-3:]!=["output NONE ;","conclusion UNSAT ;",
                     "end pseudo-Boolean proof ;"]):
        raise ValueError("master PB proof not in standard format")
    rows=lines[2:-3]
    if len(rows)!=k+1 or any(not l.startswith("pol ") for l in rows):
        raise ValueError("master PB proof is not POL-only with k+1 steps")
    for a in range(k):
        ids=[2]+[3+a*k+b for b in range(k)]
        tokens=[str(ids[0])]
        for cid in ids[1:]:tokens.extend((str(cid),"+"))
        tokens.extend((str(k),"d"))
        if rows[a]!="pol "+" ".join(tokens)+" ;":
            raise ValueError("unjustified master cross-option PB inference")
    ids=[1]+[len(mc)+1+a for a in range(k)]
    toks=[str(ids[0])]
    for cid in ids[1:]:toks.extend((str(cid),"+"))
    if rows[-1]!="pol "+" ".join(toks)+" ;":
        raise ValueError("last master contradiction does not follow from all options")
    return {"status":"IPG7_SOURCE_TO_MASTER_STRUCTURAL_BRIDGE_VERIFIED",
            "source_sha256":sha,"original_vars":nv,
            "original_clauses":len(clauses),"exact_capacity_configs":k,
            "master_vars":mn,"master_clauses":len(mc),
            "master_POL_only_lines":len(rows),
            "cross_machine_forbidden_pairs":k*k,
            "independently_reconstructed_all_original_nogoods":True,
            "source_original_direct_VerIPB_proof":False,
            "external_master_VerIPB_required":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True,type=pathlib.Path)
    p.add_argument("--certificate",required=True,type=pathlib.Path)
    p.add_argument("--master",type=pathlib.Path)
    p.add_argument("--proof",type=pathlib.Path)
    a=p.parse_args()
    try:
        cert=json.loads(a.certificate.read_text())
        if cert.get("status")=="SAT_MODEL_VERIFIED_BY_GENERATOR":
            if a.master or a.proof:raise ValueError("SAT certificate should not supply master")
            result=verify_sat(a.source,cert)
        else:
            if not a.master or not a.proof:
                raise ValueError("UNSAT bridge requires full master source and proof")
            result=verify_unsat(a.source,cert,a.master,a.proof)
        print("IPG7_SOURCE_BRIDGE_ACCEPT "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (OSError,TypeError,KeyError,ValueError,IndexError,UnicodeError,
            OverflowError,json.JSONDecodeError) as err:
        print("IPG7_SOURCE_BRIDGE_REJECT "+str(err),flush=True)
        return 1

if __name__=="__main__":sys.exit(main())

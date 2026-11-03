#!/usr/bin/env python3
"""R28 reproducible fixed original-CNF study.

10 historical polynomial development cases, 4 original GBD polynomial
cases absent from R26 (prospective relative to R26), 4 original R26
XOR controls. All input bytes SHA-256 verified BEFORE trial.
Do not tune on holdout. Not an official SAT Competition ranking.
"""
import argparse,hashlib,importlib.util,json,shutil,sys
from pathlib import Path

EXTRA_INDICES=(6,9,10,11) # frozen before R28 runs; original GBD SAT, no R26 measurements
CONTROL_PATHS=("xor_16.cnf","xor_17.cnf","r26_xor_08.cnf","r26_xor_09.cnf")
PROTOCOL="DRNAS-R28-AND-XOR-PHASE-AB-AUDIT-20261103-v1"
MODES=("gate_shadow","gate_zero","gate_one","gate_random","CaDiCaL301","Kissat404")
CAP=6.0
REPEATS=2
SHARDS=4

def digest(src):
    h=hashlib.sha256()
    with open(src,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""):h.update(c)
    return h.hexdigest()

def load_module(path):
    spec=importlib.util.spec_from_file_location("r28_preflight",str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def prepare(a):
    r26=Path(a.r26)
    pinned=Path(a.pinned)
    dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
    older=json.loads((r26/"manifest.json").read_text())
    if len(older["cases"])!=53:raise RuntimeError("R26 53 original inputs required")
    rows=[]
    for x in older["cases"]:
        if x["family"]=="polynomial_gbd_original":
            role="previously_measured_development"
        elif x["path"] in CONTROL_PATHS:
            role="xor_structure_control"
        else:
            continue
        src=r26/x["path"]
        if digest(src)!=x["sha256"]:raise RuntimeError("R26 source SHA mismatch "+x["id"])
        newpath="r28_"+x["path"]
        shutil.copyfile(src,dst/newpath)
        rows.append(dict(id=x["id"],path=newpath,family=x["family"],role=role,
                         expected=x["status"],sha256=digest(dst/newpath),
                         source=x["source"]))
    source=json.loads((pinned/"frozen_verified_gbd_family.json").read_text())
    fetch=load_module(pinned/"preflight.py")
    for idx in EXTRA_INDICES:
        sample=source["samples"][idx]
        if sample["group"]!="holdout" or sample["source_validation"]["validation"]!="sha256_verified":
            raise RuntimeError("Holdout original SHA not preregistered")
        if any(x["id"]==sample["name"] for x in rows):
            raise RuntimeError("R28 holdout not distinct from R26 development")
        original,metadata=fetch.download(sample,source)
        freeze=sample["source_validation"]
        data_sha=hashlib.sha256(original).hexdigest()
        if data_sha!=freeze["sha256"] or len(original)!=freeze["bytes"]:
            raise RuntimeError("Source GBD SHA mismatch "+sample["name"])
        name=f"r28_gbd_holdout_{idx}.cnf"
        (dst/name).write_bytes(original)
        rows.append(dict(id=sample["name"],path=name,
                         family="polynomial_gbd_original",role="r28_additional_original_holdout",
                         expected=sample["status"],sha256=data_sha,source=sample["url"]))
    roles={}
    for x in rows:roles[x["role"]]=roles.get(x["role"],0)+1
    assert roles=={"previously_measured_development":10,
                   "xor_structure_control":4,
                   "r28_additional_original_holdout":4},roles
    assert len({x["sha256"] for x in rows})==18
    manifest=dict(protocol=PROTOCOL,modes=MODES,cutoff_s=CAP,repetitions=REPEATS,
                  shards=SHARDS,additional_GBD_indices=EXTRA_INDICES,
                  chronological_base="R26 originals 41606832040; four GBD cases not in R26",
                  caveats=[
                      "Same original GBD bytes; no reformulation of source formula",
                      "R28 added holdout formulas are unmeasured in R26, not guaranteed globally unseen",
                      "Only original formula bytes can affect phase intervention",
                      "Experimental CaDiCaL receives 256-conflict checkpoint in every arm",
                      "gate_shadow computes identical structural features but applies no hints",
                      "gate_zero, gate_one, gate_random apply at most 512 phase calls",
                      "Pure XOR controls should have no AND/XOR coupling and zero gate hints",
                      "PAR2 uses 12s for any 6s timeout; timeout is not proof of failure",
                      "Comparative baselines unmodified CaDiCaL 3.0.1 and Kissat 4.0.4",
                      "SAT witness checked inside experimental C++; original known SAT/UNSAT label checked",
                      "No independent UNSAT certificates for baseline solver results",
                      "No parameter tuning using extra holdout timings"],cases=rows)
    (dst/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (dst/"original_files.sha256").write_text("".join(
        f'{x["sha256"]}  {x["path"]}\n' for x in rows))
    print("R28_FROZEN",len(rows),roles,
          digest(dst/"manifest.json"),flush=True)
    for x in rows:
        print("R28_CASE",x["role"],x["id"],x["expected"],x["sha256"],flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--r26",required=True)
    p.add_argument("--pinned",required=True)
    p.add_argument("--out",required=True)
    prepare(p.parse_args())

#!/usr/bin/env python3
"""R87 forensic-only independent XOR source certificate mismatch localization.

Read-only passive native run on SHA-frozen holdout originals.
This NEVER accepts unproven native XOR rows and does not benchmark speeds.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys
from pathlib import Path
import r83_live_xor_cdcl_wide as r83
import r87_unseen_official as holdout
import r32t_certified_short_xor as cert

def check(v,message):
    if not v: raise RuntimeError("R87_FORENSICS_FAIL_CLOSED "+str(message))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def linear_proof(source,rows):
    original,guard=cert.load_original(source)
    if guard is not None:
        return dict(state="SOURCE_SCOPE_GUARD",guard=str(guard))
    axioms=cert.complete_parity_axioms(original)
    basis={}
    contradictions=0
    def add(bits,rhs):
        nonlocal contradictions
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:
                basis[pivot]=(bits,rhs)
                return
            bits^=basis[pivot][0];rhs^=basis[pivot][1]
        if rhs:contradictions+=1
    for vs,rhs in axioms:
        add(cert.to_bitrow(vs),rhs)
    checked=[]
    for variables,rhs in rows:
        bits=cert.to_bitrow(variables);left=int(rhs);unmatched=None
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:
                unmatched=pivot
                break
            bits^=basis[pivot][0];left^=basis[pivot][1]
        status=("MISSING_PIVOT" if unmatched is not None
                else "RHS_CONFLICT" if left else "VERIFIED")
        checked.append(dict(vars=list(variables),rhs=int(rhs),status=status,
                            first_missing_original_pivot=unmatched,
                            remainder_rhs=left,
                            residual_support_size=int(bits.bit_count())))
    return dict(state="INDEPENDENT_CHECKED",axioms=len(axioms),
                basis_rank=len(basis),contradictory_basis_rows=contradictions,
                emitted=len(rows),verified=sum(r["status"]=="VERIFIED" for r in checked),
                failed=[r for r in checked if r["status"]!="VERIFIED"],
                first_rows=checked[:8])

def main(args):
    sources=Path(args.sources);mf=holdout.manifest(sources)
    compiled=Path(args.compiled)
    p=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
        cwd=compiled,capture_output=True,text=True)
    check(p.returncode==0,"binary_sha_check_failed "+p.stderr[-250:])
    native=(compiled/"native-r87").resolve()
    check(native.is_file() and os.access(native,os.X_OK),"pinned native missing")
    dest=Path(args.out);dest.mkdir(parents=True,exist_ok=True)
    reports=[]
    for i,case in enumerate(mf["cases"]):
        source=(sources/case["filename"]).resolve()
        check(digest(source)==case["sha256"],"original CNF SHA mismatch "+str(i))
        env=os.environ.copy()
        env.update(R32B_MODE="r32u",R32U_ACTIVE="0",R84_SCAN_EVERY="256",
                   R85_CAP="64",R85_DIVERSE="0",R87_ADAPT="0",R32S_PASSIVE_TRACE="0")
        timeout=False
        try:
            p=subprocess.run([str(native),str(source)],capture_output=True,
                              text=True,errors="replace",timeout=7,env=env)
            output=p.stdout
            returncode=p.returncode
        except subprocess.TimeoutExpired as e:
            timeout=True;returncode=None
            output=e.stdout or b""
            if isinstance(output,bytes):output=output.decode(errors="replace")
        emitted=[(tuple(int(v) for v in xs.split(",")),int(rhs))
                 for rhs,xs in r83.SOURCE_ROW.findall(output)]
        independent=linear_proof(source,emitted)
        row=dict(index=i,gbd=case["gbd"],year=case["year"],
            original_sha256=case["sha256"],source_group=case["group"],
            original_status=case["official_status"],runner=os.environ.get("RUNNER_NAME",""),
            commit=os.environ.get("GITHUB_SHA",""),run_id=os.environ.get("GITHUB_RUN_ID",""),
            native_sha256=digest(native),timeout=timeout,solver_returncode=returncode,
            emitted_count=len(emitted),independent=independent,
            mode_lines=[s for s in output.splitlines() if
                        s.startswith(("c R32U_MODE","c R32U_GUARD",
                          "c R32U_BASIS","c R85_SELECTION","c R87_MODE"))][:25])
        reports.append(row)
        print("R87_FORENSIC_SOURCE",json.dumps(dict(index=i,gbd=case["gbd"],
            emitted=len(emitted),independent_state=independent["state"],
            verified=independent.get("verified"),bad=independent.get("failed",[])[:2])),
            flush=True)
        save(dest/"partial.json",dict(protocol="R87-FORENSIC-V1",
             source_manifest_sha256=digest(sources/"manifest.json"),rows=reports))
    check(len(reports)==8,"missing input")
    result=dict(protocol="R87-FORENSIC-V1",
        status="OBSERVATIONAL_NOT_A_BENCHMARK",
        source_manifest_sha256=digest(sources/"manifest.json"),
        rows=reports,limitation="Proof failure is blocking, not ignored, no SAT or speed inference")
    save(dest/"r87-forensic.json",result)
    failures=[r for r in reports if r["independent"].get("failed")]
    print("R87_FORENSIC_FINISHED",len(reports),"sources; cert failures",len(failures),
          flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--compiled",required=True)
    p.add_argument("--out",required=True)
    main(p.parse_args())

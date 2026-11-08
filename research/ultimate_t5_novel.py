#!/usr/bin/env python3
"""DRNAS T5: certified *new* XOR consequences for CDCL, not source rows.

Only XOR combinations with independently replayed provenance are admitted.
A novel equation must not equal a selected original equation. All source CNF
bytes remain untouched. This is an ablation of new GF(2) reasoning, not a
claim that CNF CDCL cannot already reach the same implication.
"""
import collections
import hashlib
import json
import pathlib
import tempfile

import r157_source_certified_xor as cert
import r166x_certified_gauss as gf

MAX_SELECTED=24
MAX_WIDTH=6
MIN_RESIDUAL_HITS=1

def need(x,message):
    if not x:
        raise RuntimeError("T5_NOVEL_FAIL_CLOSED "+str(message))

def derive(source,evidence,out_dir,max_rows=MAX_SELECTED):
    source=pathlib.Path(source)
    out_dir=pathlib.Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    original_sha=gf.sha(source)
    need(original_sha==evidence["source_sha256"],"CNF source SHA drift")
    raw=gf.prepare(source,evidence,out_dir/"proof",max_derived=48)
    need(gf.replay(source,evidence,raw["certificate"],raw["tsv"],raw["units_tsv"]),
         "independent proof replay failed")
    n,clauses=gf.exact.parse_dimacs(source)
    original,groups,units=gf.source_equations(clauses)
    selected=gf.check_selected(evidence,groups,units)
    known=set(selected)
    residual,binary=gf.residual_frequencies(clauses,original)
    data=json.loads(pathlib.Path(raw["certificate"]).read_text())
    potential=[]
    for d in data["derived"]:
        var_tuple=tuple(d["vars"])
        m=gf.maskof(var_tuple);parity=int(d["rhs"])
        indices=list(d["source_indices"])
        width=len(var_tuple)
        if not 2<=width<=MAX_WIDTH:
            continue
        if (m,parity) in known:
            continue
        # More than one INDEPENDENT original parity premise required.
        if len(set(indices))<2:
            continue
        proof=0
        for i in indices:
            need(0<=i<len(selected),"original source index outside proof")
            proof^=1<<(i+1)
        need(gf.verify_proof([(tuple(gf.bits(x)),y) for x,y in selected],
                             m,parity,proof)==indices,
             "derived row is not the stated combination")
        hits=sum(residual[v] for v in var_tuple)
        if hits<MIN_RESIDUAL_HITS:
            continue
        linked=sum(residual[v]>0 for v in var_tuple)
        # Shorter, residual-linked, well-supported derived XOR rows first;
        # no SAT/UNSAT labels or timing data are available to this selector.
        rank=(-linked,-min(hits,1000),width,tuple(var_tuple),parity)
        potential.append((rank,d))
    potential.sort(key=lambda x:x[0])
    picked=[];seen=set()
    for _,d in potential:
        key=(tuple(d["vars"]),d["rhs"])
        if key in seen:continue
        seen.add(key);picked.append(d)
        if len(picked)==max_rows:break
    tsv=out_dir/"novel-rows.tsv"
    tsv.write_text("".join(
        f'{len(d["vars"])} {d["rhs"]} '+
        " ".join(map(str,d["vars"]))+"\n" for d in picked))
    report={
        "protocol":"DRNAS-T5-NOVEL-DERIVED-ORIGINAL-CNF-PROOF-v1",
        "source_sha256":original_sha,
        "selected_original_rows":len(selected),
        "certified_derived_candidates":len(data["derived"]),
        "residual_linked_candidates":len(potential),
        "novel_rows":len(picked),
        "novel_tsv_sha256":gf.sha(tsv),
        "max_width":MAX_WIDTH,
        "selected":[
            {"vars":d["vars"],"rhs":d["rhs"],
             "source_indices":d["source_indices"],
             "residual_hits":sum(residual[v] for v in d["vars"])}
            for d in picked],
        "proof_caveat":"GF(2) source replay only; no independent native UNSAT LRAT",
        "original_cnf_unchanged":True
    }
    (out_dir/"novel-proof.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n")
    need(gf.sha(source)==original_sha,"source mutated by proof process")
    print("T5_NOVEL_PROOF_PASS",json.dumps({
        k:report[k] for k in
        ("source_sha256","selected_original_rows",
         "certified_derived_candidates","novel_rows","novel_tsv_sha256")
    },sort_keys=True),flush=True)
    return report,tsv

def selftest():
    # XOR(1,2,3)=0 and XOR(1,2,4)=1 entail XOR(3,4)=1.
    # Neither original complete parity group alone entails this short row.
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td); p=root/"original.cnf"
        clauses=[]
        for vars,rhs in [((1,2,3),0),((1,2,4),1)]:
            for mask in range(1<<3):
                if mask.bit_count()%2==rhs:
                    continue
                clauses.append(" ".join(
                    str(-v if mask>>i&1 else v) for i,v in enumerate(vars))+" 0")
        clauses.extend(("3 5 0","-4 5 0","3 -5 0","4 5 0"))
        p.write_text("p cnf 5 "+str(len(clauses))+"\n"+"\n".join(clauses)+"\n")
        ev=cert.extract(p,root/"source.tsv",root/"source-proof.json",max_rows=64)
        need(ev["selected_rows"]==2,"synthetic source parity not extracted")
        report,tsv=derive(p,ev,root/"novel",max_rows=24)
        wanted=gf.maskof((3,4))
        need(any(gf.maskof(d["vars"])==wanted and d["rhs"]==1
                 and len(d["source_indices"])==2
                 for d in report["selected"]),
             "two-source GF2 cancellation not discovered")
        need(report["original_cnf_unchanged"],"source preservation")
        lines=tsv.read_text().splitlines()
        need("2 1 3 4" in lines,"novel row not in exported TSV")
        # Each source parity alone has 3 variables, hence neither is the row.
        need(all(len(d["vars"])!=3 for d in report["selected"]),
             "original row was passed through")
        print("T5_NOVEL_DOUBLE_XOR_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    selftest()

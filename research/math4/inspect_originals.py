#!/usr/bin/env python3
"""Read-only original-CNF algebra audit across frozen SAT2026 Main-Track families.

Reports complete source-occurring XOR half-cubes (2^(width-1) original
clauses on the same variable support) and exact GF(2) rank/contradictions.
Does not report UNSAT without a separate independently checked certificate.
The only inputs are the SHA-pinned, unmodified hall3-prepared source CNFs.
"""
import collections
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MANIFEST=Path("research/hall3/manifest.json")

def sha256_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def inspect(path,expected):
    t=time.perf_counter()
    assert sha256_file(path)==expected["sha256"],("SOURCE_SHA_MISMATCH",expected["id"])
    width_hist=collections.Counter()
    parity_patterns={}  # support tuple -> [forbidden even-mask, forbidden odd-mask]
    clauses_read=0
    longest_clause=0
    p_seen=False
    current=[]
    with path.open("r",encoding="ascii") as f:
        for line in f:
            fields=line.split()
            if not fields or fields[0]=="c":continue
            if fields[0]=="p":
                assert not p_seen and fields[1]=="cnf" and len(fields)==4
                assert int(fields[2])==expected["variables"]
                assert int(fields[3])==expected["clauses"]
                p_seen=True
                continue
            for token in fields:
                value=int(token)
                if value:
                    current.append(value)
                    continue
                clause=current
                current=[]
                clauses_read+=1
                width=len(clause)
                longest_clause=max(longest_clause,width)
                width_hist[width]+=1
                if 2<=width<=6 and len(parity_patterns)<400000:
                    support=tuple(sorted(abs(v) for v in clause))
                    if len(set(support))==width and support[0]>0:
                        loc={v:i for i,v in enumerate(support)}
                        mask=sum(1<<loc[-v] for v in clause if v<0)
                        entry=parity_patterns.setdefault(support,[set(),set()])
                        entry[mask.bit_count()&1].add(mask)
    assert p_seen and not current and clauses_read==expected["clauses"]
    rows=[]
    available=[]
    for vs,parts in parity_patterns.items():
        w=len(vs)
        for parity in (0,1):
            if len(parts[parity])==1<<(w-1):
                rows.append((vs,parity))
                available.append((tuple(vs),parity))
    # Exact GF2 algebra on equations whose entire CNF clause support was seen.
    basis={}
    relation=None
    for i,(vars_,forbidden_parity) in enumerate(rows):
        row_mask=sum(1<<(v-1) for v in vars_)
        rhs=1-forbidden_parity
        trace=1<<i
        while row_mask:
            pivot=(row_mask&-row_mask).bit_length()-1
            if pivot not in basis:
                basis[pivot]=(row_mask,rhs,trace)
                break
            mask2,rhs2,tr2=basis[pivot]
            row_mask^=mask2
            rhs^=rhs2
            trace^=tr2
        if not row_mask and rhs==1:
            combo=[j for j in range(len(rows)) if (trace>>j)&1]
            relation={"xor_rows_used":len(combo),
                      "equations":[{"variables":list(rows[j][0]),
                                    "forbidden_parity":rows[j][1]}
                                   for j in combo],
                      "note":"Algebra candidate only; not independently source-certified"}
            break
    r={
        "id":expected["id"],"file_id":expected["file_id"],
        "family":expected["family"],"catalog_label":expected["catalog_label"],
        "sha256":expected["sha256"],"variables":expected["variables"],
        "clauses":clauses_read,"histogram":dict(width_hist),
        "xor_equations":len(rows),
        "xor_by_width":dict(collections.Counter(len(v) for v,_ in rows)),
        "xor_rank_until_first_conflict":len(basis),
        "xor_contradiction_candidate":bool(relation),
        "conflict_relation":relation,
        "all_clauses_scanned":True,
        "group_limit_hit":len(parity_patterns)>=400000,
        "scan_s":round(time.perf_counter()-t,6),
    }
    return r

def main():
    assert os.path.isfile(MANIFEST)
    m=json.loads(MANIFEST.read_text())
    out=Path("math4_audit")
    out.mkdir(exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    rows=[]
    with (out/"diagnostics.jsonl").open("w") as f:
        for s in m["sources"]:
            r=inspect(Path(s["path"]),s)
            rows.append(r)
            f.write(json.dumps(r,sort_keys=True)+"\n")
            f.flush()
            print("MATH4_REAL_SOURCE "+json.dumps({k:r[k] for k in
                ("id","family","catalog_label","variables","clauses",
                 "xor_equations","xor_by_width","xor_contradiction_candidate",
                 "xor_rank_until_first_conflict","scan_s")},sort_keys=True),flush=True)
    summary={
        "sources":len(rows),"single_cpu":cpu,"all_source_SHA_verified":True,
        "catalog_labels_are_not_proofs":True,
        "xor_nonzero_sources":sum(r["xor_equations"]>0 for r in rows),
        "candidate_contradictions":sum(r["xor_contradiction_candidate"] for r in rows),
        "families":{}}
    for family in sorted({r["family"] for r in rows}):
        f=[r for r in rows if r["family"]==family]
        summary["families"][family]={
            "sources":len(f),"xor_equations":sum(r["xor_equations"] for r in f),
            "xor_candidate_sources":sum(r["xor_contradiction_candidate"] for r in f),
            "per_source":[{"id":r["id"],"xor_equations":r["xor_equations"],
                           "candidate":r["xor_contradiction_candidate"],
                           "scanned":r["all_clauses_scanned"],
                           "group_limit_hit":r["group_limit_hit"]} for r in f]}
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("MATH4_REAL_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()

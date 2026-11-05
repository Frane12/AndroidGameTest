#!/usr/bin/env python3
"""R133d: source-proof-aware, short-implication GF(2) selection for native CaDiCaL.
The R133c IPASIR-UP bridge remains unchanged: all emitted clauses stay logically
entailed by certified GF(2) equations. Development test only; no learning claim.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import time

MAX_SOURCE = 16
MAX_DERIVED = 48
MAX_WIDTH = 4

def load_verified(cnf: Path, rows_path: Path, proof_path: Path):
    evidence = json.loads(proof_path.read_text())
    digest = hashlib.sha256(cnf.read_bytes()).hexdigest()
    if evidence.get("protocol") != "R93-LIVE-XOR-PROOF-CERTS-v1":
        raise RuntimeError("unexpected source proof protocol")
    if evidence.get("source_sha256") != digest:
        raise RuntimeError("source CNF SHA mismatch")
    rows = []
    for line in rows_path.read_text().splitlines():
        if not line or line.startswith("#"): continue
        parts = [int(x) for x in line.split()]
        k, rhs, *vs = parts
        if k != len(vs) or not 2 <= k <= 8 or rhs not in (0, 1):
            raise RuntimeError("invalid certified input row")
        if sorted(set(vs)) != vs:
            raise RuntimeError("unordered or duplicate variables")
        rows.append((tuple(vs), rhs))
    proofs = evidence.get("proof_rows")
    if not isinstance(proofs, list) or len(proofs) != len(rows):
        raise RuntimeError("certified rows/proof count mismatch")
    for (vs, rhs), p in zip(rows, proofs):
        mask = sum(1 << (v - 1) for v in vs)
        if p["mask"] != mask or p["rhs"] != rhs or len(p["original_equation_ids"]) < 2:
            raise RuntimeError("certified row differs from independent source evidence")
    return rows, digest

def derive(original, max_source=MAX_SOURCE, max_derived=MAX_DERIVED, max_width=MAX_WIDTH):
    selected_original = sorted(
        ((vs, rhs, (i,)) for i,(vs,rhs) in enumerate(original) if len(vs) <= max_width),
        key=lambda x: (len(x[0]), x[0], x[1], x[2])
    )[:max_source]
    seen = {(vs, rhs) for vs, rhs in original}
    candidates = []
    for i in range(len(original)):
        va, ra = original[i]
        sa = set(va)
        for j in range(i+1, len(original)):
            vb, rb = original[j]
            vs = tuple(sorted(sa.symmetric_difference(vb)))
            rhs = ra ^ rb
            if 2 <= len(vs) <= max_width and (vs, rhs) not in seen:
                candidates.append((vs, rhs, (i, j)))
    candidates.sort(key=lambda x: (len(x[0]), x[0], x[1], x[2]))
    derived = []
    for c in candidates:
        if len(derived) >= max_derived: break
        key = (c[0],c[1])
        if key in seen: continue
        seen.add(key)
        derived.append(c)
    selected = selected_original + derived
    assert len(selected) <= max_source+max_derived
    # Reconstruct each output directly from its immutable certified sources.
    for vs, rhs, ancestry in selected:
        vset = set()
        parity = 0
        for i in ancestry:
            src, bit = original[i]
            vset.symmetric_difference_update(src)
            parity ^= bit
        if tuple(sorted(vset)) != vs or parity != rhs:
            raise RuntimeError("R133d equation ancestry replay failed")
    return selected, dict(source_kept=len(selected_original),
                          derived_kept=len(derived),
                          candidate_pairs=len(candidates),
                          original_rows=len(original),
                          selected_rows=len(selected))

def selftest():
    rows=[((1,2,3),0),((1,2,4),0),((3,4,5),1)]
    emitted, stats=derive(rows)
    assert ((3,4),0) in {(v,r) for v,r,_ in emitted}
    assert stats["derived_kept"]>=1
    for bits in itertools.product((0,1), repeat=5):
        sat = lambda vs,rhs: (sum(bits[v-1] for v in vs)&1)==rhs
        if all(sat(v,r) for v,r in rows):
            assert all(sat(v,r) for v,r,_ in emitted)
    print("R133D_PROVENANCE_SELFTEST_PASS",json.dumps(stats,sort_keys=True))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=("selftest","export"))
    ap.add_argument("--cnf",type=Path)
    ap.add_argument("--rows",type=Path)
    ap.add_argument("--proof",type=Path)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--audit",type=Path)
    a=ap.parse_args()
    if a.command=="selftest":
        selftest()
        return
    if not all((a.cnf,a.rows,a.proof,a.out,a.audit)):
        ap.error("source CNF, rows, proof, output and audit paths required")
    start=time.perf_counter()
    original,digest=load_verified(a.cnf,a.rows,a.proof)
    selected,stats=derive(original)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text("# R133d certified and pairwise independently replayed GF2 rows\n"+
        "".join(f"{len(v)} {rhs} "+" ".join(map(str,v))+"\n"
                for v,rhs,_ in selected))
    stats.update(protocol="DRNAS-R133D-SHORT-SIGNAL-V1",
                 cnf_sha256=digest,
                 max_source=MAX_SOURCE,max_derived=MAX_DERIVED,max_width=MAX_WIDTH,
                 preparation_s=round(time.perf_counter()-start,6),
                 retained_ancestries=[list(anc) for _,_,anc in selected])
    a.audit.write_text(json.dumps(stats,indent=2,sort_keys=True)+"\n")
    print("R133D_SELECT_PASS",json.dumps({k:v for k,v in stats.items() if k!="retained_ancestries"},sort_keys=True))

if __name__=="__main__":
    main()

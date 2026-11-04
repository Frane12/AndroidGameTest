#!/usr/bin/env python3
"""R93: immutable XOR equation audit and proof-carrying row export for live IPASIR-UP.

Never export a row unless independently reconstructed from original CNF parity
patterns. No tuning based on solver times, answer labels, or SAT status.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r92_verified_xor_bridge as r92
import r88_cooperative as r88

def prepare(source, target, evidence, max_rows=240):
    p = Path(source)
    n, clauses = r88.read_cnf(p)
    originals = r92.xor_sources(clauses)
    rows = r92.echelon(originals, {})
    # Derived rows only; source's own 3-CNF clauses are already present.
    possible = [r for r in rows if len(r[2]) >= 2 and 2 <= r[0].bit_count() <= 8]
    possible.sort(key=lambda r: (r[0].bit_count(), len(r[2]), r[0], r[1]))
    certified = []
    for row in possible:
        if r92.independently_certify(row, clauses, originals, []):
            certified.append(row)
    selected = certified[:max_rows]
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# R93 separately certified immutable XOR rows\n" +
        "".join(f"{r[0].bit_count()} {r[1]} " +
                " ".join(str(i+1) for i in range(r[0].bit_length()) if (r[0]>>i)&1)
                + "\n" for r in selected))
    audit = dict(protocol="R93-LIVE-XOR-PROOF-CERTS-v1",
        source_sha256=r88.sha(p), variables=n, cnf_clauses=len(clauses),
        original_xor_equations=len(originals), candidates=len(possible),
        independently_verified=len(certified), exported=len(selected),
        proof_rows=[dict(mask=r[0],rhs=r[1],original_equation_ids=sorted(r[2]))
                    for r in selected],
        default_behavior="FAIL_CLOSED: no row from this file can be injected absent certificate")
    Path(evidence).write_text(json.dumps(audit,indent=2)+"\n")
    print("R93_CERTIFIED_ROWS",json.dumps({k:v for k,v in audit.items() if k!="proof_rows"}))
    return audit

def selftest():
    clauses=[]
    for vars_ in ((1,2,3),(1,2,4)):
        for sign in (1,2,4,7):
            clauses.append(tuple(-v if sign & (1<<i) else v
                                 for i,v in enumerate(vars_)))
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        root=Path(d)
        p=root/"fixture.cnf";r88.write_augmented(4,clauses,[],p)
        audit=prepare(p,root/"rows.tsv",root/"evidence.json")
        assert audit["exported"]>=1
        rows=(root/"rows.tsv").read_text()
        assert "2 0 3 4" in rows
        assert audit["source_sha256"]==r88.sha(p)
    print("R93_EXPORT_SELFTEST_PASS")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("command", choices=["selftest","export"])
    parser.add_argument("--cnf");parser.add_argument("--rows");parser.add_argument("--evidence")
    args=parser.parse_args()
    if args.command=="selftest":selftest()
    else:
        if not (args.cnf and args.rows and args.evidence):parser.error("missing export paths")
        prepare(args.cnf,args.rows,args.evidence)

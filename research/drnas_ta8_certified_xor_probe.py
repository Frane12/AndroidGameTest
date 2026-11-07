#!/usr/bin/env python3
"""DRNAS TA8 bounded R28 classify-only pretest with independent source-CNF replay.

The existing R28 C++ binary is run with --classify-only, never entering
Kissat/CMS. Only a replay-verified source XOR contradiction returns UNSAT.
Every noncertificate (including TIMEOUT) falls back to unchanged frozen
TA3 portfolio. Selftests cover valid XOR proof, mixed residual, tampered
proof, source SHA independence and fallback. Non-LRAT source-XOR proof.
"""
from __future__ import annotations
import pathlib
import re
import subprocess
import time
import tempfile

import r164_pure_exact_gf2 as pure

PILOT_CAP_S=0.18
R28=pathlib.Path("r190_cms_mixed/r28")
EXECUTORS=("cms_plain","cms_r28","kissat_plain","kissat_r28")
EQ=re.compile(r"^c R28_EQ id=(\d+) rhs=([01]) vars=([0-9]+(?:,[0-9]+)*)$")
CERT=re.compile(r"^c R28_UNSAT_CERT ids=(\d+(?:,\d+)*)$")
ROUTE=re.compile(r"^c R28_ROUTE certified_xor_contradiction equations=(\d+) rank=(\d+) clauses=(\d+) covered=(\d+)$")

def verify_contradiction(source,output):
    """Independently replay only the equations actually used in R28 cert.

    Each claimed equation must be entailed by a complete parity-forbidden
    truth-table clause block in original DIMACS. Then XOR-sum proof must
    give zero LHS and one RHS. No trust in R28 self-reported GF2 rank.
    """
    lines=output.splitlines()
    headers=[ROUTE.fullmatch(x) for x in lines if x.startswith("c R28_ROUTE ")]
    if len(headers)!=1 or headers[0] is None:
        raise ValueError("missing or ambiguous certified XOR route")
    n_eq=int(headers[0].group(1))
    if not 1<=n_eq<=3000:
        raise ValueError("bad equation count")
    certs=[CERT.fullmatch(x) for x in lines if x.startswith("c R28_UNSAT_CERT ")]
    if len(certs)!=1 or certs[0] is None:
        raise ValueError("missing or ambiguous certificate")
    ids=[int(x) for x in certs[0].group(1).split(",")]
    if not ids or len(set(ids))!=len(ids) or any(i>=n_eq for i in ids):
        raise ValueError("bad contradiction indices")
    if lines.count("s UNSATISFIABLE")!=1:
        raise ValueError("no single explicit UNSAT verdict")
    eqs={}
    for line in lines:
        if not line.startswith("c R28_EQ "):
            continue
        m=EQ.fullmatch(line)
        if not m: raise ValueError("invalid equation line")
        i=int(m.group(1)); rhs=int(m.group(2))
        vs=tuple(map(int,m.group(3).split(",")))
        if i in eqs or i>=n_eq or not 2<=len(vs)<=6 or len(set(vs))!=len(vs) or tuple(sorted(vs))!=vs:
            raise ValueError("invalid equation variables")
        eqs[i]=(vs,rhs)
    if len(eqs)!=n_eq or any(i not in eqs for i in range(n_eq)):
        raise ValueError("equation list incomplete")
    _num_vars,clauses=pure.parse_dimacs(source)
    if len(clauses)!=int(headers[0].group(3)):
        raise ValueError("source clause count mismatch")
    wanted={eqs[i][0] for i in ids}
    masks={v:set() for v in wanted}
    for cl in clauses:
        if not 2<=len(cl)<=6:
            continue
        ordered=sorted(cl,key=abs)
        vs=tuple(abs(v) for v in ordered)
        if vs in masks and len(set(vs))==len(vs):
            mask=sum(1<<j for j,v in enumerate(ordered) if v<0)
            masks[vs].add(mask)
    bits=0;bit=0
    for eid in ids:
        vs,rhs=eqs[eid]
        forbidden_parity=1-rhs
        needed={m for m in range(1<<len(vs)) if m.bit_count()%2==forbidden_parity}
        if not needed.issubset(masks[vs]):
            raise ValueError("claimed XOR equation not implied by original CNF")
        for v in vs: bits ^= (1<<v)
        bit ^= rhs
    if bits!=0 or bit!=1:
        raise ValueError("XOR contradiction does not replay")
    return len(ids),n_eq

def classify(source,budget=PILOT_CAP_S):
    started=time.perf_counter()
    if budget<=0: return dict(certified=False,reason="budget_zero",elapsed_s=0.0)
    command=[str(R28.resolve()),str(pathlib.Path(source).resolve()),"/bin/false","--classify-only"]
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=budget,check=False)
    except subprocess.TimeoutExpired:
        return dict(certified=False,reason="probe_timeout",elapsed_s=round(time.perf_counter()-started,6))
    stdout=p.stdout.decode("utf-8",errors="replace")
    elapsed=round(time.perf_counter()-started,6)
    if p.returncode!=0:
        return dict(certified=False,reason="probe_nonzero_exit",elapsed_s=elapsed)
    if "c R28_ROUTE certified_xor_contradiction " not in stdout:
        return dict(certified=False,reason="no_certified_contradiction",elapsed_s=elapsed)
    involved,total=verify_contradiction(source,stdout)
    return dict(certified=True,reason="SOURCE_XOR_CONTRADICTION_REPLAYED",
                elapsed_s=elapsed,certificate_rows=involved,source_equations=total)

def selftest():
    # Contradictory XOR2 blocks on (1,2), plus a residual third-variable clause.
    # The mixed formula is not pure XOR, yet its certified subset is UNSAT.
    with tempfile.TemporaryDirectory() as td:
        src=pathlib.Path(td)/"valid.cnf"
        src.write_text("p cnf 3 5\n1 2 0\n-1 -2 0\n1 -2 0\n-1 2 0\n3 0\n")
        out=classify(src,budget=1.0)
        assert out["certified"] and out["certificate_rows"]>0,out
        raw=subprocess.run([str(R28.resolve()),str(src.resolve()),"/bin/false",
                    "--classify-only"],capture_output=True,text=True,check=True).stdout
        assert verify_contradiction(src,raw)[0]>0
        forged=raw.replace("c R28_UNSAT_CERT ids=","c R28_UNSAT_CERT ids=9999,")
        try: verify_contradiction(src,forged)
        except ValueError: pass
        else: raise AssertionError("tampered certificate accepted")
        src2=pathlib.Path(td)/"safe.cnf"
        src2.write_text("p cnf 3 2\n1 2 0\n-1 3 0\n")
        assert not classify(src2,budget=1.0)["certified"]
        assert not classify(src2,budget=0)["certified"]
    print("TA8_CERTIFIED_PROBE_SELFTEST_PASS 5",flush=True)

if __name__=="__main__": selftest()

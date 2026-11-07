#!/usr/bin/env python3
"""New Horizon R4e: negative middle-window witnesses; exact original CNF only.

Windows may VETO an expensive 2SAT eligibility check, never certify 2SAT,
GF(2), SAT or UNSAT. Accepted special cases still receive R4d's complete
source-wide exact membership verification and original-model validation.
"""
from __future__ import annotations

import pathlib
import subprocess
import time

import new_horizon_r4d as r4d

PROTO = "DRNAS_NH_R4E_MIDLINE_VETO_PROOF_GATED_v1"
WINDOW = 384
MIN_SAMPLE_BYTES = 640

def header_candidate(file, size):
    if size < MIN_SAMPLE_BYTES or size > r4d.MAX_SOURCE_BYTES:
        return None
    with file.open("rb") as fh:
        for line in fh:
            x = line.strip()
            if not x or x.startswith(b"c"):
                continue
            if x.startswith(b"p "):
                a = x.split()
                if len(a) != 4 or a[1] != b"cnf":
                    return None
                try:
                    n, m = int(a[2]), int(a[3])
                except ValueError:
                    return None
                if (0 < n <= r4d.TWO_MAX_VARS and
                    r4d.TWO_MIN_CLAUSES <= m <= r4d.TWO_MAX_CLAUSES):
                    return n, m
                return None
            return None
    return None

def window_has_complete_long_clause(fh, size, center):
    start = max(0, min(size, int(center) - WINDOW // 2))
    fh.seek(start)
    blob = fh.read(WINDOW)
    if start > 0:
        # Never count a possibly clipped first line or clause as evidence.
        nl = blob.find(b"\n")
        if nl < 0:
            return False
        blob = blob[nl + 1:]
    if start + WINDOW < size:
        nl = blob.rfind(b"\n")
        if nl < 0:
            return False
        blob = blob[:nl + 1]
    # Start after a complete terminator, so a clause beginning off-window
    # cannot accidentally be classified from just its tail.
    in_clause = (start == 0)
    literals = set()
    for line in blob.splitlines():
        strip = line.lstrip()
        if not strip or strip.startswith((b"c", b"p ", b"%")):
            continue
        for tok in strip.split():
            try:
                v = int(tok)
            except ValueError:
                in_clause = False
                literals.clear()
                continue
            if v == 0:
                if in_clause and len(literals) > 2:
                    return True
                in_clause = True
                literals.clear()
            elif in_clause:
                literals.add(v)
    return False

def source_evidence(source, *, policy="mid"):
    assert policy in ("mid", "tri")
    t = time.perf_counter()
    path = pathlib.Path(source)
    size = path.stat().st_size
    metadata = header_candidate(path, size)
    visited = 0
    if metadata:
        centers = (size // 2,) if policy == "mid" else (
            size // 4, size // 2, 3 * size // 4)
        with path.open("rb") as fh:
            for center in centers:
                visited += 1
                if window_has_complete_long_clause(fh, size, center):
                    return dict(route="clean", reason="middle_complete_long_clause_veto",
                        scan_s=time.perf_counter()-t, scanned=0,
                        complete_source=False, clauses=None, gf2_rows=None,
                        n=metadata[0], m=metadata[1], sample_windows=visited)
    # A window missing evidence proves NOTHING. R4d's full original-source
    # membership verification remains mandatory on every fast-path acceptance.
    ev = r4d.source_evidence(path)
    ev["scan_s"] = time.perf_counter()-t
    ev["sample_windows"] = visited
    return ev

def run_one(source, binary, cap, mode, scratch=None):
    if mode in ("clean", "pure_only", "r4d"):
        original = r4d.run_one(source, binary, cap, mode, scratch)
        original["r4e_evidence"] = None
        return original
    r4d.need(mode in ("r4e_mid", "r4e_tri"), "bad R4e policy")
    t = time.perf_counter()
    ev = source_evidence(source, policy="mid" if mode=="r4e_mid" else "tri")
    if ev["route"] != "clean" and cap-(time.perf_counter()-t) > .15:
        clauses = ev["clauses"]
        if ev["route"] == "pure":
            rows = ev["gf2_rows"]
            r4d.need(rows and ev["complete_source"], "incomplete GF2 source")
            a = r4d.pure.gaussian(rows)
            if a["status"] == "SAT":
                r4d.need(r4d.pure.verify_sat(clauses, a["model"]),
                         "GF2 model invalid for original")
            route = "gf2_exact"
            proof = ("ORIGINAL_GF2_SAT_MODEL_CHECKED" if a["status"]=="SAT"
                     else "ORIGINAL_GF2_UNSAT_CONTRADICTION_REPLAYED_NO_LRAT")
        else:
            r4d.need(ev["complete_source"], "incomplete 2SAT source")
            a = r4d.r2.solve_2sat(ev["n"], clauses)
            route = "2sat_linear"
            proof = ("ORIGINAL_2SAT_SCC_SAT_MODEL_CHECKED" if a["status"]=="SAT"
                     else "ORIGINAL_2SAT_SCC_UNSAT_NO_LRAT")
        elapsed = time.perf_counter()-t
        if elapsed < cap:
            return dict(status=a["status"],elapsed=elapsed,proof=proof,
                        route=route,reason=ev["reason"],
                        r4e_evidence={k:v for k,v in ev.items()
                                      if k not in ("clauses", "gf2_rows")})
    remain = cap-(time.perf_counter()-t)
    status, model = "TIMEOUT", {}
    if remain > .12:
        try:
            status, model = r4d.native.native(binary, source, remain)
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
    elapsed = time.perf_counter()-t
    if elapsed >= cap:
        status = "TIMEOUT"
    if status == "SAT":
        r4d.native.verify_model(source, model)
        proof = "ORIGINAL_CNFSAT_WITNESS_CHECKED"
    elif status == "UNSAT":
        proof = "NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:
        proof = "CAP"
    return dict(status=status, elapsed=elapsed, proof=proof, route="clean",
                reason=ev["reason"],
                r4e_evidence={k:v for k,v in ev.items()
                              if k not in ("clauses", "gf2_rows")})

def selftest():
    import tempfile
    r4d.selftest()
    with tempfile.TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        def write(name, n, clauses):
            f=root/name
            f.write_text(f"p cnf {n} {len(clauses)}\n"+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            return f
        for i in range(16):
            n=120+i
            chain=[(1,)]+[(-k,k+1) for k in range(1,n)]
            valid=write(f"valid-{i}.cnf",n,chain)
            for policy in ("mid","tri"):
                e=source_evidence(valid,policy=policy)
                r4d.need(e["route"]=="two_sat" and e["complete_source"],
                         "valid 2SAT must keep exact path")
            # Position of this clause is not in the last 384 bytes.
            bad=chain.copy()
            bad.insert(len(bad)//2,(1,2,3))
            path=write(f"middle-{i}.cnf",n,bad)
            r4d.need(not r4d.r2.is_2cnf(bad),"not disqualified")
            for policy in ("mid","tri"):
                e=source_evidence(path,policy=policy)
                r4d.need(e["route"]=="clean","mixed CNF accepted as 2SAT")
        malformed=root/"incomplete.cnf"
        malformed.write_text("p cnf 130 130\n"+"1 0\n"*30)
        for policy in ("mid","tri"):
            r4d.need(source_evidence(malformed,policy=policy)["route"]=="clean",
                     "truncated source accepted")
    print("NH_R4E_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    selftest()

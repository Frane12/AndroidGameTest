#!/usr/bin/env python3
"""DRNAS New Horizon SAT R2: robust linear response surrogate and exact fast paths.

Approximation applies ONLY to cost/selection, NEVER to CNF meaning.
Exact 2-SAT (SCC), Horn (forward chaining), R164 proof-gated GF(2).
Unknown/ambiguous inputs fall back to unchanged CaDiCaL.
"""
from __future__ import annotations

import collections
import pathlib
import time
import new_horizon_sat as r1
import r164_pure_exact_gf2 as pure

SCAN_CLAUSES = 64
MAX_SPECIAL_CLAUSES = 6000
MAX_SPECIAL_BYTES = 320000
R2_PROTO = "NEW_HORIZON_R2_ROBUST_LINEAR_RESPONSE_v1"


def require(ok, msg):
    if not ok:
        raise AssertionError("R2_FAIL_CLOSED " + str(msg))


def is_horn(clauses):
    return all(sum(v > 0 for v in set(c)) <= 1 for c in clauses)


def is_2cnf(clauses):
    return all(len(set(c)) <= 2 for c in clauses)


def solve_horn(n, clauses):
    """O(number of literal occurrences + n): least-model forward chaining.
    Must only be called after COMPLETE original CNF passes Horn check.
    """
    require(is_horn(clauses), "attempted Horn inference on non-Horn source")
    weight = []
    head = []
    uses = collections.defaultdict(list)
    queue = collections.deque()
    true = set()
    reasons = {}
    for ci, raw in enumerate(clauses):
        c = set(raw)
        if any(-z in c for z in c):
            continue  # tautology: always satisfied
        h = next((z for z in c if z > 0), None)
        neg = sorted({abs(z) for z in c if z < 0})
        idx = len(weight)
        weight.append(len(neg))
        head.append(h)
        for v in neg:
            uses[v].append(idx)
        if not neg:
            if h is None:
                return {"status": "UNSAT", "witness": None, "reason": "empty_original_clause"}
            if h not in true:
                true.add(h)
                queue.append(h)
                reasons[h] = ci
    while queue:
        v = queue.popleft()
        for ci in uses[v]:
            weight[ci] -= 1
            if weight[ci]:
                continue
            h = head[ci]
            if h is None:
                return {"status": "UNSAT", "witness": None, "reason": "horn_forward_contradiction"}
            if h not in true:
                true.add(h)
                queue.append(h)
                reasons[h] = ci
    model = {v: (v in true) for v in range(1, n + 1)}
    require(all(any(model[abs(l)] == (l > 0) for l in c) for c in clauses),
            "Horn least model failed ORIGINAL source")
    return {"status": "SAT", "witness": model, "reason": "horn_least_model"}


def solve_2sat(n, clauses):
    """O(n+m) iterative Kosaraju SCC, complete original 2-CNF ONLY."""
    require(is_2cnf(clauses), "attempted 2-SAT on non-2-CNF source")
    N = 2 * n
    g = [[] for _ in range(N)]
    gr = [[] for _ in range(N)]
    def node(lit):
        return 2 * (abs(lit)-1) + (lit < 0)
    def edge(a, b):
        g[a].append(b)
        gr[b].append(a)
    for raw in clauses:
        c = list(dict.fromkeys(raw))
        if not c:
            return {"status": "UNSAT", "witness": None, "reason": "empty_original_clause"}
        if len(c) == 1:
            x = node(c[0])
            edge(x ^ 1, x)
        else:
            a, b = map(node, c)
            edge(a ^ 1, b)
            edge(b ^ 1, a)
    seen = bytearray(N)
    order = []
    for s in range(N):
        if seen[s]: continue
        seen[s] = 1
        stack = [(s, 0)]
        while stack:
            v, i = stack[-1]
            if i < len(g[v]):
                w = g[v][i]
                stack[-1] = (v, i+1)
                if not seen[w]:
                    seen[w] = 1
                    stack.append((w, 0))
            else:
                order.append(v)
                stack.pop()
    comp = [-1] * N
    cc = 0
    for s in reversed(order):
        if comp[s] != -1: continue
        comp[s] = cc
        stack = [s]
        while stack:
            v = stack.pop()
            for w in gr[v]:
                if comp[w] == -1:
                    comp[w] = cc
                    stack.append(w)
        cc += 1
    for v in range(1, n+1):
        if comp[2*v-2] == comp[2*v-1]:
            return {"status": "UNSAT", "witness": None, "reason": "literal_negation_same_scc"}
    model = {v: comp[2*v-2] > comp[2*v-1] for v in range(1, n+1)}
    require(all(any(model[abs(l)] == (l > 0) for l in c) for c in clauses),
            "2-SAT model failed original source")
    return {"status": "SAT", "witness": model, "reason": "scc_model"}


def probe(path):
    """At most 64 complete CNF clauses; cheap candidate labels, never proof.
    No file label/family/SAT status is read.
    """
    start = time.perf_counter()
    n, m = None, None
    sample = []
    partial = []
    with pathlib.Path(path).open(encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("c", "%")): continue
            if line.startswith("p "):
                a = line.split()
                require(n is None and len(a) == 4 and a[1] == "cnf", "source header")
                n, m = int(a[2]), int(a[3])
                require(n >= 0 and m >= 0, "negative dimension")
                continue
            require(n is not None, "missing header")
            for tok in line.split():
                x = int(tok)
                if x:
                    require(0 < abs(x) <= n, "invalid original literal")
                    partial.append(x)
                else:
                    sample.append(tuple(partial))
                    partial = []
                    if len(sample) == SCAN_CLAUSES: break
            if len(sample) == SCAN_CLAUSES: break
    require(n is not None and (len(sample) == min(m, SCAN_CLAUSES)),
            "incomplete source probe")
    horn = is_horn(sample)
    two = is_2cnf(sample)
    ternary = all(len(set(c)) == 3 for c in sample) and bool(sample)
    # Unique variable triples and their sign-mask signatures: no permutation search.
    patterns = collections.defaultdict(set)
    if ternary:
        for c in sample:
            lit = sorted(c, key=lambda x: abs(x))
            vs = tuple(abs(x) for x in lit)
            patterns[vs].add(sum((x < 0) << j for j, x in enumerate(lit)))
    quartet = 0
    for masks in patterns.values():
        for parity in (0, 1):
            if all((v in masks) for v in range(8) if (v.bit_count() & 1) == parity):
                quartet += 1
    n_lits = sum(len(c) for c in sample)
    return dict(n=n, m=m, scan_s=time.perf_counter()-start, sample=len(sample),
                sample_literals=n_lits, candidate_horn=horn,
                candidate_two_sat=two, candidate_pure_xor3=(ternary and
                     len(sample)==m and quartet>=2 and m<=128),
                xor_quartets_sample=quartet)


def linear_cost_surrogate(info, method):
    """Fixed piecewise-affine proxy, heuristic only, NEVER a correctness proof.
    Coefficients are deliberately conservative, chosen before prospective R2.
    Units ms, not a fitted or calibrated regression. Robust margin required.
    """
    n, m = info["n"], info["m"]
    scan_ms = info["scan_s"]*1000
    # Estimate two costs from source shape, no outcome and no heavy probing.
    if method == "pure":
        cdcl_est = 1.42
        specialty_est = 0.09 + 0.0018*m + 0.0005*n
    elif method == "horn":
        cdcl_est = 0.95 + 0.0020*m + 0.003*n
        specialty_est = 0.12 + 0.0011*m + 0.0006*n
    elif method == "two_sat":
        cdcl_est = 0.95 + 0.0022*m + 0.003*n
        specialty_est = 0.20 + 0.0013*m + 0.0008*n
    else:
        return dict(choice="clean", benefit_ms=0, margin_ms=0)
    benefit = cdcl_est - specialty_est - scan_ms
    margin = max(0.20, 0.25*cdcl_est)
    return dict(method=method, cdcl_est_ms=cdcl_est,
                specialty_est_ms=specialty_est, observed_scan_ms=scan_ms,
                benefit_ms=round(benefit, 6), margin_ms=round(margin, 6),
                choice=("certify" if benefit > margin else "clean"))


def decide(info, path):
    """Choose inexpensive family verification or abstain. All outputs uncertain."""
    if info["scan_s"] > 0.020: return "clean", "scan_budget", {}
    if info["m"] > MAX_SPECIAL_CLAUSES or pathlib.Path(path).stat().st_size > MAX_SPECIAL_BYTES:
        return "clean", "source_size_budget", {}
    # pure XOR3 can be certified with full R164 source-equivalence check
    if info["candidate_pure_xor3"]:
        score = linear_cost_surrogate(info, "pure")
        return ("pure" if score["choice"]=="certify" else "clean"),"linear_pure",score
    # A Horn source is also 2SAT when clauses are <=2; choose lower predicted cost.
    options = []
    if info["candidate_horn"] and info["m"]>=50:
        options.append(("horn", linear_cost_surrogate(info,"horn")))
    if info["candidate_two_sat"] and info["m"]>=50:
        options.append(("two_sat",linear_cost_surrogate(info,"two_sat")))
    good = [(mode,score) for mode,score in options if score["choice"]=="certify"]
    if good:
        mode,score = max(good, key=lambda item:item[1]["benefit_ms"])
        return mode,"source_candidate_requires_full_proof",score
    return "clean","unknown_or_margin_not_met",dict(alternatives=options)


def run_one(source,binary,cap,mode,scratch=None):
    """Modes clean, shadow, r1, r2. Exact source semantics always preserved."""
    require(mode in ("clean","shadow","r1","r2"), "unknown R2 mode")
    st=time.perf_counter()
    info=None;score=None;route="clean";reason="baseline"
    if mode=="r1":
        r=r1.run_one(source,binary,cap,"new_horizon",scratch)
        r.update(r2_candidate=None,r2_score=None,r2_origin="r1_existing")
        return r
    if mode in ("shadow","r2"):
        info=probe(source)
        route,reason,score=decide(info,source)
        if mode=="shadow":
            route="clean";reason="shadow_probe_only"
    if mode=="r2" and route!="clean" and cap-(time.perf_counter()-st)>0.15:
        # Proof gate: the FULL original CNF must belong to the predicted tractable family.
        n,clauses=pure.parse_dimacs(source)
        actual=None;kind=None
        if route=="pure":
            ok,rows,covered=pure.detect_exact(clauses)
            if ok and all(2<=len(vs)<=6 for vs,rhs in rows):
                result=pure.gaussian(rows)
                kind=result["status"]
                if kind=="SAT":
                    require(pure.verify_sat(clauses,result["model"]),"pure SAT witness")
                    proof="CNF_EQUIV_GF2_MODEL_CHECKED"
                else:
                    proof="CNF_EQUIV_GF2_SOURCE_CONTRADICTION_REPLAYED_NO_LRAT"
                actual=dict(status=kind,proof=proof,fast_method="gf2_exact")
        elif route=="horn" and is_horn(clauses):
            cert=solve_horn(n,clauses)
            actual=dict(status=cert["status"],proof="EXACT_HORN_FORWARD_NO_LRAT",
                        fast_method="horn_linear")
        elif route=="two_sat" and is_2cnf(clauses):
            cert=solve_2sat(n,clauses)
            actual=dict(status=cert["status"],proof="EXACT_2SAT_SCC_NO_LRAT",
                        fast_method="2sat_linear")
        if actual is not None:
            elapsed=time.perf_counter()-st
            if elapsed<cap:
                return dict(status=actual["status"],elapsed=elapsed,
                            proof=actual["proof"],route=actual["fast_method"],
                            reason=reason,screen=info,preprocess=dict(linear_surrogate=score),
                            r2_candidate=route,r2_score=score,r2_origin="source_verified")
        # Any failed strict verification simply routes to unchanged CDCL.
        route="clean";reason="full_source_certificate_refused_or_budget"
    remaining=cap-(time.perf_counter()-st)
    status="TIMEOUT";model={}
    if remaining>0.12:
        try:status,model=r1.native(binary,source,remaining)
        except __import__("subprocess").TimeoutExpired: status="TIMEOUT"
    elapsed=time.perf_counter()-st
    if elapsed>=cap: status="TIMEOUT"
    if status=="SAT":
        r1.verify_model(source,model)
        proof="SAT_WITNESS_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":proof="CDCL_UNSAT_NOT_INDEPENDENTLY_LRAT_CERTIFIED"
    else:proof="CAP"
    return dict(status=status,elapsed=elapsed,proof=proof,route=route,
                reason=reason,screen=info,preprocess=None,
                r2_candidate=route,r2_score=score,r2_origin="source_unchanged")


def selftest():
    import random, tempfile
    rng=random.Random(20261107)
    with tempfile.TemporaryDirectory() as td:
        t=pathlib.Path(td)
        def record(name,n,clauses):
            p=t/name
            p.write_text(f"p cnf {n} {len(clauses)}\n"+
                         "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            return p
        for n in range(1,8):
            for _ in range(45):
                # Random Horn incl unit/empty/negative-only, compare truth table.
                horn=[]
                for i in range(rng.randrange(1,14)):
                    neg=rng.sample(range(1,n+1),rng.randrange(0,min(3,n)+1))
                    pos=[] if rng.random()<.4 else [rng.randrange(1,n+1)]
                    horn.append(tuple([-v for v in neg]+pos))
                # Remove duplicates; tautologies permitted (should be ignored).
                p=record("h.cnf",n,horn)
                h=solve_horn(n,horn)
                brute=any(all(any(((mask>>(abs(v)-1))&1)==int(v>0) for v in c)
                    for c in horn) for mask in range(1<<n))
                require((h["status"]=="SAT")==brute,"Horn exhaustive mismatch")
                # Random 2-SAT incl duplicates/empty/units.
                two=[]
                for i in range(rng.randrange(1,16)):
                    two.append(tuple((v if rng.getrandbits(1) else -v)
                                     for v in rng.sample(range(1,n+1),
                                         rng.randrange(0,min(2,n)+1))))
                a=solve_2sat(n,two)
                brute=any(all(any(((mask>>(abs(v)-1))&1)==int(v>0) for v in c)
                    for c in two) for mask in range(1<<n))
                require((a["status"]=="SAT")==brute,"2SAT exhaustive mismatch")
        # A non-Horn 3-clause passes only the early scan if later clauses differ:
        # we NEVER accept without full verification.
        p=record("not_horn.cnf",3,[(1,),(-1,2),(1,2,3)])
        require(not is_horn(pure.parse_dimacs(p)[1]),"full Horn disproof")
        p=record("not_2sat.cnf",3,[(1,2),(-1,3),(1,2,3)])
        require(not is_2cnf(pure.parse_dimacs(p)[1]),"full 2SAT disproof")
    print("NEW_HORIZON_R2_SELFTEST_PASS random_bruteforce=630",flush=True)


if __name__=="__main__":
    selftest()

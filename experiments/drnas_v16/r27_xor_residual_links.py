#!/usr/bin/env python3
"""R27: exact XOR-block / residual CNF interface mapping (observational only).

Reads original immutable DIMACS bytes; no filenames, answers or timing used
for structural decisions. Detects EXACT complete forbidden-sign parity
patterns; derives GF(2) boundary equations by eliminating XOR-only variables.
Independent replay of every sampled derived relation prevents wrong claims.
This analysis is neither a dynamic CDCL implication graph nor a new SAT solver.
"""
import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

PROTOCOL = "DRNAS-R27-EXACT-XOR-RESIDUAL-INTERFACE-20261103-v1"
MAX_WIDTH = 10
MAX_PROJECTION_ROWS = 2500
MAX_DERIVED_EXAMPLES = 12

def fail(condition, message):
    if not condition:
        raise ValueError(message)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def clauses(path):
    """Strict DIMACS parser supporting multiline clauses and comments."""
    declared_n = declared_m = None
    current = []
    seen = 0
    with open(path, "rt", errors="replace") as stream:
        for line in stream:
            s = line.strip()
            if not s or s.startswith("c"):
                continue
            if s.startswith("%"):
                break
            if s.startswith("p "):
                tokens = s.split()
                fail(declared_n is None and len(tokens) == 4 and tokens[1] == "cnf",
                     "Duplicate/bad DIMACS header")
                declared_n, declared_m = int(tokens[2]), int(tokens[3])
                fail(1 <= declared_n <= 2000000 and 1 <= declared_m <= 5000000,
                     "DIMACS dimensions outside safe bound")
                continue
            fail(declared_n is not None, "Clause before header")
            for token in s.split():
                v = int(token)
                if not v:
                    seen += 1
                    fail(seen <= declared_m, "Too many clauses")
                    yield declared_n, tuple(current)
                    current = []
                else:
                    fail(abs(v) <= declared_n, "Literal outside header")
                    current.append(v)
                    fail(len(current) <= 10000, "Clause too wide for safety")
    fail(declared_n is not None and seen == declared_m and not current,
         "Incomplete DIMACS")

def signature(cl):
    k = len(cl)
    if k < 2 or k > MAX_WIDTH:
        return None
    ordered = sorted(cl, key=lambda x: abs(x))
    vars_ = tuple(abs(x) for x in ordered)
    if len(set(vars_)) != k:
        return None
    mask = sum((1 << i) for i, x in enumerate(ordered) if x < 0)
    return vars_, mask

PARITY_MASKS = {}
for k in range(2, MAX_WIDTH + 1):
    even = odd = 0
    for mask in range(1 << k):
        if mask.bit_count() % 2:
            odd |= (1 << mask)
        else:
            even |= (1 << mask)
    PARITY_MASKS[k] = (even, odd)

class UnionFind:
    def __init__(self):
        self.parent = {}
        self.size = {}
    def root(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1
        while x != self.parent[x]:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x
    def union(self, a, b):
        a, b = self.root(a), self.root(b)
        if a == b:
            return
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]

def first_pass(path):
    patterns = {}   # support -> (present forbidden sign-mask bitmap, occurrences)
    widths = Counter()
    n = 0
    count = 0
    for n, cl in clauses(path):
        count += 1
        widths[len(cl)] += 1
        sig = signature(cl)
        if sig is not None:
            support, mask = sig
            if support not in patterns:
                patterns[support] = [0, 0]
            patterns[support][0] |= 1 << mask
            patterns[support][1] += 1
    groups = {}
    candidates = 0
    partial = 0
    for sup, (seen, count_occ) in patterns.items():
        even, odd = PARITY_MASKS[len(sup)]
        if count_occ > 1:
            candidates += 1
        # Forbidden even parity -> allowed odd = RHS 1, and conversely.
        if seen == even:
            groups[sup] = 1
        elif seen == odd:
            groups[sup] = 0
        elif count_occ > 1:
            partial += 1
    return n, count, widths, groups, patterns, candidates, partial

def parity_projection(groups, interface, limit=MAX_PROJECTION_ROWS):
    """Gaussian eliminate non-interface variables FIRST; all output implied."""
    keys = sorted(groups)
    stride = max(1, math.ceil(len(keys)/limit))
    selected = keys[::stride][:limit]
    complete = len(selected) == len(keys)
    selected_rows = []
    xor_variables = set()
    for sup in groups:
        xor_variables.update(sup)
    internal = xor_variables.difference(interface)
    internal_mask = sum(1 << (x-1) for x in internal)
    pivots = {}
    projected = []
    for j, sup in enumerate(selected):
        bits = sum(1 << (v-1) for v in sup)
        rhs = groups[sup]
        selected_rows.append((bits, rhs))
        combo = 1 << j
        while bits & internal_mask:
            mask = bits & internal_mask
            var = (mask & -mask).bit_length()
            pivot = pivots.get(var)
            if pivot is None:
                pivots[var] = (bits, rhs, combo)
                break
            bits ^= pivot[0]
            rhs ^= pivot[1]
            combo ^= pivot[2]
        else:
            projected.append((bits, rhs, combo))
    # Independently reduce projected boundary-only rows; their certificates
    # remain linear combinations of full original XOR blocks.
    boundary_basis = {}
    basis = []
    contradictions = 0
    for bits, rhs, combo in projected:
        while bits:
            var = (bits & -bits).bit_length()
            pivot = boundary_basis.get(var)
            if pivot is None:
                boundary_basis[var] = (bits, rhs, combo)
                basis.append((bits, rhs, combo))
                break
            bits ^= pivot[0]
            rhs ^= pivot[1]
            combo ^= pivot[2]
        else:
            if rhs:
                contradictions += 1
                basis.append((0, 1, combo))
    # Certificate replay on ALL basis rows of weight <= 3, plus 20 others.
    audited = 0
    verified = True
    weight_hist = Counter()
    novel_count = 0
    examples = []
    direct = {(sup, groups[sup]) for sup in groups}
    for i, (bits, rhs, combo) in enumerate(basis):
        width = bits.bit_count()
        bucket = str(width) if width <= 10 else ">10"
        weight_hist[bucket] += 1
        if width <= 3 or i < 20:
            check_bits = check_rhs = 0
            x = combo
            while x:
                low = x & -x
                index = low.bit_length()-1
                check_bits ^= selected_rows[index][0]
                check_rhs ^= selected_rows[index][1]
                x ^= low
            if (check_bits, check_rhs) != (bits, rhs):
                verified = False
                raise RuntimeError("Independent GF(2) certificate replay failed")
            audited += 1
        if 1 <= width <= 3:
            vars_ = tuple(j+1 for j in range(bits.bit_length()) if bits >> j & 1)
            is_novel = (vars_, rhs) not in direct
            novel_count += int(is_novel)
            if len(examples) < MAX_DERIVED_EXAMPLES:
                examples.append(dict(vars=list(vars_),rhs=rhs,
                                     is_new_relation=is_novel,
                                     certified_equations=combo.bit_count()))
    return dict(projected_rows_before_boundary_reduction=len(projected),
                projection_complete=complete, sample_equations=len(selected),
                total_equations=len(groups), eliminated_internal_pivots=len(pivots),
                independent_boundary_rows=len(basis), contradiction_rows=contradictions,
                boundary_width_hist=dict(weight_hist),
                derived_short_rows=sum(v for k,v in weight_hist.items()
                                       if k in ("1","2","3")),
                novel_short_relations=novel_count,
                independently_replayed_certificates=audited,
                replay_valid=verified,
                examples=examples)

def diagnose(path, prior=None):
    start = time.monotonic()
    n, count, widths, groups, patterns, candidates, partial = first_pass(path)
    xorvars = set()
    graph = UnionFind()
    equations_by_size = Counter()
    for sup in groups:
        equations_by_size[len(sup)] += 1
        xorvars.update(sup)
        first = sup[0]
        for v in sup[1:]:
            graph.union(first,v)
    xorocc = Counter()
    resocc = Counter()
    residual_widths = Counter()
    n_xor_clauses = 0
    n_residual_clauses = 0
    touched_residual = 0
    mixed_residual = 0
    binary_with_xor = 0
    binary_2_xor = 0
    pair_occ = Counter()
    for _, cl in clauses(path):
        sig = signature(cl)
        is_xor_clause = sig is not None and sig[0] in groups
        if is_xor_clause:
            n_xor_clauses += 1
            xorocc.update(abs(l) for l in cl)
        else:
            n_residual_clauses += 1
            residual_widths[len(cl)] += 1
            resocc.update(abs(l) for l in cl)
            involved = sorted(set(abs(l) for l in cl).intersection(xorvars))
            if involved:
                touched_residual += 1
                if len(involved) < len(set(map(abs,cl))):
                    mixed_residual += 1
            if len(cl) == 2 and involved:
                binary_with_xor += 1
                binary_2_xor += int(len(involved)==2)
            if len(cl) <= 8 and len(involved) >= 2:
                for i, a in enumerate(involved):
                    for b in involved[i+1:]:
                        pair_occ[(a,b)] += 1
    interface = set(xorocc).intersection(resocc)
    xoronly = set(xorocc).difference(resocc)
    residualonly = set(resocc).difference(xorocc)
    byroot = defaultdict(lambda: dict(xor_vars=0,interface_vars=0,equations=0))
    for v in xorvars:
        z = byroot[graph.root(v)]
        z["xor_vars"] += 1
        z["interface_vars"] += int(v in interface)
    for sup in groups:
        byroot[graph.root(sup[0])]["equations"] += 1
    components = sorted(byroot.values(), key=lambda x:(x["equations"],x["xor_vars"]), reverse=True)
    top_variables = sorted(interface, key=lambda v:(min(xorocc[v],resocc[v]),
                          resocc[v],xorocc[v]), reverse=True)[:12]
    strongest_pairs = sorted(pair_occ.items(),key=lambda x:x[1],reverse=True)[:12]
    top_pairs = [dict(a=a,b=b,residual_cooccurrence=count)
                 for (a,b),count in strongest_pairs]
    projection = parity_projection(groups, interface)
    output = dict(formula=Path(path).name, sha256=sha256(path),
                  protocol=PROTOCOL, variables_declared=n, clauses_declared=count,
                  widths=dict(widths), genuine_complete_xor_blocks=len(groups),
                  complete_xor_blocks_by_width=dict(equations_by_size),
                  repeated_support_candidates=candidates,
                  incomplete_or_mixed_supports=partial,
                  exact_xor_clause_occurrences=n_xor_clauses,
                  exact_xor_clause_share_pct=round(100*n_xor_clauses/max(1,count),3),
                  residual_clauses=n_residual_clauses,
                  xor_variables=len(xorvars), interface_variables=len(interface),
                  xor_only_variables=len(xoronly), residual_only_variables=len(residualonly),
                  interface_fraction_of_xor_vars=round(len(interface)/max(1,len(xorvars)),6),
                  residual_clauses_touching_xor=touched_residual,
                  residual_clauses_cross_xor_nonxor=mixed_residual,
                  residual_binary_touch_xor=binary_with_xor,
                  residual_binary_both_xor=binary_2_xor,
                  residual_clause_widths=dict(residual_widths),
                  xor_components=len(components), top_components=components[:6],
                  interface_top_hubs=[dict(variable=v, xor_occurrences=xorocc[v],
                                            residual_occurrences=resocc[v],
                                            shared_degree=min(xorocc[v],resocc[v]))
                                      for v in top_variables],
                  residual_pairs_on_xor_variables=top_pairs,
                  gf2_boundary_projection=projection,
                  structural_only=True,
                  elapsed_analysis_s=round(time.monotonic()-start,3),
                  caveats=["Complete parity blocks imply exact GF(2) equations; "
                           "partial/near patterns do NOT count as equations",
                           "Residual connections are static CNF co-occurrence, "
                           "not CDCL reason edges or proven causal benefits",
                           "Projection samples a deterministic subset if >2500 XOR equations",
                           "All derived equations are logical consequences of "
                           "complete XOR blocks; no new SAT strategy is used"])
    if prior:
        fail(prior["sha256"] == output["sha256"], "Original frozen SHA mismatch")
        output["source_id"] = prior["id"]
        output["source_family"] = prior["family"]
        output["status_from_prior_manifest_not_detector"] = prior["status"]
    return output

def selftest():
    # x XOR y = 0 and y XOR z = 1, residual x,z linkage.
    def xor_clauses(vs, rhs):
        r=[]
        for mask in range(1 << len(vs)):
            if mask.bit_count()%2 == rhs:
                continue
            r.append(tuple(-v if mask >> i & 1 else v for i,v in enumerate(vs)))
        return r
    clauses1 = xor_clauses([1,2],0) + xor_clauses([2,3],1) + [(1,4),(-3,4)]
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/"synthetic.cnf"
        p.write_text("p cnf 4 "+str(len(clauses1))+"\n"+
                     "\n".join(" ".join(map(str,c))+" 0" for c in clauses1)+"\n")
        out=diagnose(p)
        fail(out["genuine_complete_xor_blocks"]==2, "Two exact XOR blocks")
        fail(out["interface_variables"]==2, "Boundary variables are x,z")
        examples=out["gf2_boundary_projection"]["examples"]
        fail(any(z["vars"]==[1,3] and z["rhs"]==1 for z in examples),
             "GF(2) x XOR z = 1 must follow after eliminating y")
        # Remove one parity clause: no longer a complete sound block.
        p.write_text("p cnf 4 "+str(len(clauses1)-1)+"\n"+
                     "\n".join(" ".join(map(str,c))+" 0" for c in clauses1[1:])+"\n")
        bad=diagnose(p)
        fail(bad["genuine_complete_xor_blocks"]==1, "Partial XOR cannot be promoted")
    print("R27_COMPLETE_XOR_PROOF_AND_BOUNDARY_SELFTEST_PASS",flush=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--input")
    a.add_argument("--manifest")
    a.add_argument("--out")
    args=a.parse_args()
    if args.selftest:
        selftest()
        return
    fail(args.input and args.out and args.manifest, "Missing required files")
    spec=json.loads(Path(args.manifest).read_text())
    row=next((x for x in spec["cases"] if x["path"]==Path(args.input).name),None)
    fail(row is not None, "Formula missing from frozen manifest")
    result=diagnose(args.input,row)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    projection=result["gf2_boundary_projection"]
    print("R27_STRUCTURE",json.dumps({
        "case":result["source_id"],"sha256":result["sha256"],
        "blocks":result["genuine_complete_xor_blocks"],
        "xor_covered_pct":result["exact_xor_clause_share_pct"],
        "xor_vars":result["xor_variables"],
        "interface_vars":result["interface_variables"],
        "crossing_residual":result["residual_clauses_cross_xor_nonxor"],
        "residual_touch_xor":result["residual_clauses_touching_xor"],
        "projection_sample":projection["sample_equations"],
        "boundary_rank_sample":projection["independent_boundary_rows"],
        "novel_short_relations":projection["novel_short_relations"],
        "elapsed_s":result["elapsed_analysis_s"]
    },sort_keys=True),flush=True)

if __name__=="__main__":
    main()

# DRNAS IPG-BDD3: native 3-class BDD count-profile guard

## Research aim and source-based correctness

New opt-in C++ module `src/ipg_bdd3_count.hpp`. It adds a THIRD fixed
job-count coordinate to the existing original-source-grounded BDD profile
guard. Main and frozen comparison variants are untouched.

For three disjoint selected classes A, B, C of exactly-one job groups,
a machine's accepted BDD-path count profile is a set of triples
P_i subset of [0,|A|] x [0,|B|] x [0,|C|]. Reduced-BDD skipped selector
levels are conservatively treated as free binary choices. A FALSE
terminal never contributes. Original CNF ALO/AMO clauses prove that
each selected job must be assigned to exactly one machine.

Define R_0={(0,0,0)} and

  R_(i+1) = {r+p | r in R_i, p in P_i, r+p component-wise <= (|A|,|B|,|C|)}.

If (|A|,|B|,|C|) is NOT in the final R_m then original CNF is UNSAT.
Every source SAT model would induce precisely such a triple,
so this is a SOUND sufficient UNSAT criterion. It is not complete.

Fixed 3D dense state space has at most (|A|+1)(|B|+1)(|C|+1)
elements per BDD node; with bounded candidate class partitions
this is polynomial in the size of the EXPLICIT input BDD and selected
groups, not in all original bin-packing descriptions. Constructing the
BDD can require exponential size for general PCMAX; no P=NP claim.

## Certificate format and verification discipline

To reduce proof artifact size, the C++ module emits:
  1. `graph.json`: exact source SHA256 and native BDD transition graph,
     asserting only clauses literally present in the original CNF.
  2. `certificate.json`: source/graph SHA256s, three selected job class
     lists, per-machine accepted-profile SIZES and global reachable
     state COUNTS, not all machine triple profiles.

Independent `research/ipg_bdd3_checker.py` verifies the original
CNF source clauses and reconstructs the BDD, then computes the 3D
machine profiles BACKWARD instead of the C++ FORWARD algorithm.
It independently recomputes all global states and checks that the
target count vector is unreachable. It rejects forged source bytes,
state counts and unsupported BDD transitions.

These compact STRUCTURAL certificates are NOT VeriPB, DRAT or LRAT.
Until a standard PB proof generator is implemented, do not present
this as a VeriPB-verified PAR2 competition result.

## Native solver order

BDD capacity -> IPG1 exact integer cover -> IPG-BDD2 (optional)
-> IPG-BDD3 (optional) -> CDCL + MG7 residual SCC.

All steps in one C++ process, one logical CPU; Python is used
only by the OUT-OF-PROCESS independent research benchmark checker.
Unknown remains UNKNOWN and is not counted as solved.

## Reproduce

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-pcmax-mg7-ipg1-bdd3 -j2

To isolate the third-stage result on the same CNF:

    ./build/drnas-pcmax-mg7-ipg1-bdd3 input.cnf \
      --mode core --time 3 --stats \
      --pcmax-capacity --pcmax-budget-ms 0 \
      --pcmax-certificate result.capacity.json \
      --ipg-bdd3 --ipg-bdd3-budget-ms 600 \
      --ipg-bdd3-graph result.graph.json \
      --ipg-bdd3-certificate result.count.json \
      --residual-scc --proof result.drat

Then, ONLY if `IPG_BDD3_JSON_NEEDS_INDEPENDENT_CHECKER`
is emitted, confirm the SOURCE-BOUND proof:

    python3 research/ipg_bdd3_checker.py \
      --cnf input.cnf --graph result.graph.json \
      --certificate result.count.json

Test paired one-CPU native two-class vs three-class versions:

    python3 -u research/ipg_bdd3_native_benchmark.py

## Evaluation limitations

Tests use source-frozen historically known PCMAX originals and
deterministically sealed generated BDD sources. Labels are withheld
from solver calls, but these are not a genuine prospective blind
competition set. The system reports verified-only results and
any unrecognized formula remains UNKNOWN.

The run explicitly measures whether BDD3 provides genuinely
new source-grounded UNSAT instances over the BDD2 reference.
No improvement may be claimed without accepted proof and
verification-inclusive timed paired comparisons.

See latest successful (or failed) experimental GitHub workflow
named DRNAS IPG-BDD3 native 3-count source-proof audit.

# DRNAS IPG5-B — native C++ job-branch proof plus source CG cuts

## Completed test — 2026-11-16

Experimental branch:
`experiment/drnas-ipg5b-jobbranch-native-20261116`.
No main changes, no APK and no second SAT solver. The new native
target `drnas-ipg5b-jobbranch` is a STANDALONE C++ research proof
generator — NOT yet an opt-in guard inside the general DRNAS SAT solver.

GitHub Actions finished **SUCCESS**:
https://github.com/Frane12/AndroidGameTest/actions/runs/43859514384

Original source SHA256:
`c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`.
Exactly 45 CNF variables and 300 original clauses, three machines,
15 jobs, T=29,524. The program refuses other source hashes
rather than guessing a valid UNSAT conclusion.

## Engineering improvement

Previous IPG5-A Python mathematically guided non-CDCL proof generator:
3,398 source-RUP additions, 173,129 bytes in standard VeriPB.

New IPG5-B native C++ ternary (machine assignment) branching
uses a source-ordering heuristic sorted by exact descending
job size and then selects a job with the fewest currently
allowed machines. Branches represent complete job placements
rather than isolated Boolean literals.

Each leaf corresponds to unit-propagation contradiction on the
ORIGINAL CNF under source assignments D. The generator adds
the RUP no-good NOT(D). At each internal node it combines
the child no-goods using the original 3-way one-hot ALO clause.
No CDCL, conflict analysis, portfolio, learned VSIDS or an
external SAT solver is invoked by the native generator.

Every RUP step is replayed internally against the original
source plus earlier proof clauses BEFORE output is committed.
Then external DRAT-trim, an independent Python source-RUP
replay, and independent VeriPB 3.0.2 check the original unchanged
45v/300c source.

| Metric, one paired retrospective source | Old IPG5-A | New C++ IPG5-B |
|---|---:|---:|
| RUP clauses, including empty contradiction | 3,398 | 100 |
| RUP proof bytes | 79,681 | 1,772 |
| Standard VeriPB proof bytes | 173,129 | 3,952 |
| Proof generation seconds | 1.9394 | 0.004245 |
| Source + DRAT + independent RUP + VeriPB E2E seconds | 3.929303 | 0.098062 |
| Independent DRAT-trim accepted | YES | YES |
| Independent VeriPB3.0.2 accepted | YES | YES |

Approximately 33.98x fewer RUP additions, about 43.8x smaller
VeriPB certificate, and about 40.07x shorter verification-inclusive
single-run benchmark time against the OLDER mathematical IPG5-A.

**CRITICAL LIMIT:** This is NOT a verified win over the strongest
DRNAS CDCL solver, which already had a shorter 92-step source-RUP
proof on this same tiny original instance. It is also NOT a
general blind PAR2 result; source gate is pinned to one exact
retrospective Petersen input.

## Genuine original-source rank-one Chvatal-Gomory PB cutting planes

The ORIGINAL 300-clause source contains, for each of three machines,
three pairwise overweight conflicts between jobs numbered
(0-based) 9, 12, 14. Source clause IDs (VeriPB 1-based) are:

- Machine 0: 139, 241, 271.
- Machine 1: 140, 242, 272.
- Machine 2: 141, 243, 273.

Write the original source binary clauses as PB inequalities:

  ~x_A + ~x_B >= 1,
  ~x_A + ~x_C >= 1,
  ~x_B + ~x_C >= 1.

Adding the original clauses and dividing by 2 with integer rounding
produces the valid rank-one Chvatal–Gomory odd-cycle/clique cut:

  ~x_A + ~x_B + ~x_C >= 2,

equivalently at most one of the three heavy jobs on a machine.

The converter `research/ipg5b_oddcycle_pb.py` emits exactly
THREE `pol <source_id> <source_id> + <source_id> + 2 d ;`
lines, followed by the independently replayed 100-step RUP proof.
External VeriPB 3.0.2 ACCEPTED this source-bound 4,030-byte
combined proof.

**SCIENTIFIC LIMIT:** These three CG cuts alone DO NOT derive
the final UNSAT. The 100-step RUP structural branching is still
essential in this proof, and worst-case complexity is exponential.
The cuts are a legitimate first source-level integer PB derivation,
not a generic IPG-BDD3 or non-scalar source-to-VeriPB compiler.

## Robustness checks

The native C++ generator returns UNKNOWN and emits no proof
when original source bytes change or when given an unrelated
SAT packing instance. The separate converter refuses any
RUP trace missing the final empty contradiction. All three
negative controls PASSED in the green GitHub Actions run.

## Reproduce

    cargo install veripb --version 3.0.2 --locked --root ./veripb-tool
    make -C drat-trim drat-trim
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-ipg5b-jobbranch -j2
    python3 -u research/ipg5b_cpp_benchmark.py

All generated proof bytes, independent checker logs and
SHA-frozen original source are archived under
`results/ipg5b_jobbranch/` in the workflow artifact.

## Next research gate

1. Remove hard-coded Petersen SHA by source-clause reconstruction
   of a larger structural graph/packing family, with explicit
   correctness checks against arbitrary SAT controls.
2. Determine whether stronger PB odd-set / parity inequalities
   can make the original 100-step DPLL tree unnecessary.
3. Only then integrate an opt-in C++ source-proof guard into
   the general DRNAS process, with one logical CPU, strict
   source-bound VeriPB verification and no main change.
4. Prospectively blind, source-disjoint mixed benchmarks including
   official real PCMAX inputs and frozen CDCL, Kissat, CaDiCaL, CMS
   before any claim of competitive improvement.

This is a concrete proof-compression and native engineering result
on one known mathematical construction, not a proof of P=NP.

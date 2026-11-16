# DRNAS IPG-BDD3 — verified native three-class experiment (2026-11-16)

## Scientific status

This experiment introduces **three-class BDD count profiles** as an optional
one-process native C++ component in DRNAS, isolated in an experimental branch.
Main and frozen baseline targets are unchanged.

Native BDD3 computations use the existing source-validated PCMAX BDD
extractor and no external SAT/SMT solver or subprocess. Independent
Python checking occurs ONLY after the native solve and is included
as a separate reported cost; it is not used by the solver.

## Mathematical statement

Selected original one-hot job groups form three disjoint subsets A,B,C.
Using every source-validated BDD machine graph, enumerate the reachable
triples (#A,#B,#C) on accepting BDD paths, allowing skipped BDD levels to
be assigned freely. Count-vector global DP combines machine profiles.
If the mandatory count triple (|A|,|B|,|C|) is unreachable, the original
CNF is UNSAT. Any SAT model must choose exactly one selector per source
one-hot group and follow accepting machine BDD paths. This is a
sound SUFFICIENT criterion, not a complete solver.

Three fixed count dimensions give a polynomial-sized state space
relative to the EXPLICIT BDD; BDD construction can be exponential
in the underlying PCMAX instance. No general polynomial-time
PCMAX or P=NP claim follows.

## Proof format and external verification

The native implementation emits a source-bound JSON certificate with
three class selectors, source SHA-256, BDD graph SHA-256, machine profile
SIZES and global reachable state counts. Instead of trusting a huge
table of triples, the independent checker recomputes BDD profiles
BACKWARD from source-unit terminals and recomputes the global DP.
Every BDD transition, source assignment clause and at-most-one
source clause must be present in the EXACT original CNF bytes.

These compact JSON certificates are independently validated
STRUCTURAL proofs, NOT DRAT/LRAT/VeriPB proofs. Thus they do not
qualify for certified DRAT/PB SAT competition PAR2 without an
accepted translation to a standard proof format.

## Completed paired C++ audit

GitHub workflow:
https://github.com/Frane12/AndroidGameTest/actions/runs/43840237445

Experimental source set: 50 distinct CNFs and 100 serial paired
one-logical-CPU trials:

- 16 deterministic already-known generated BDD scheduling CNFs
- 24 seed-committed, label-withheld-from-solver synthetic BDD formulas
- 10 SHA-frozen, retrospective genuine original PCMAX formulas

Both old BDD2 and new BDD3 used the same source bytes, budget
and logical CPU, while the disabled PCMAX capacity gate prevented
the known capacity module from concealing the new experiment's
actual contribution.

| Result | BDD2 reference | BDD3 native |
|---|---:|---:|
| Source-checked structural UNSAT | 23 | 27 |
| Genuine original PCMAX source proofs | 1 | 2 |
| Additional source proofs over BDD2 | - | 4 |
| Auditing errors and false UNSAT | 0 | 0 |

The four additional source-verified UNSAT instances were:

- sealed_012_m2
- sealed_020_m2
- sealed_022_m2
- pcmax-scheduling-m20-4135-27005-UNSAT.sanitized

**Key ORIGINAL case**:

  Original source SHA-256:
  cf68074a07348e696d56ae179eb900c894ad294ec1175c850d4a18ad33e91af2
  20 machines, 32 eligible jobs, native BDD3 partition: (11,10,10)
  Native module: ~0.2305 s
  Native whole executable: ~0.2456 s
  Independent checker: ~0.0924 s
  Compact certificate: 640 bytes; source BDD graph: 79,594 bytes
  BDD2 reference: UNKNOWN within 2.2 seconds
  BDD3 source proof: INDEPENDENTLY VERIFIED

Critical qualification: the older weighted BDD capacity module
already proved UNSAT for this original PCMAX source. IPG-BDD3
is a NEW mathematical/engineering **route** over BDD2, not
a previously unsolved official original CNF or an overall competitive
runtime victory against the earlier strongest DRNAS capacity guard.

24 sealed synthetic samples are BLIND TO THE SOLVER (no labels
in solver inputs), but they are NOT a formal prospective blind
competition evaluation and cannot establish generalization alone.

## To reproduce

  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build --target drnas-pcmax-mg7-ipg1-bdd2 drnas-pcmax-mg7-ipg1-bdd3 -j2
  python3 -u research/ipg_bdd3_native_benchmark.py

To run new C++ module alone (disable capacity and old BDD2 guard):

  build/drnas-pcmax-mg7-ipg1-bdd3 SOURCE.cnf --mode core --time 2.2 \
    --pcmax-capacity --pcmax-budget-ms 0 --pcmax-certificate cap.json \
    --ipg-bdd3 --ipg-bdd3-budget-ms 600 \
    --ipg-bdd3-graph bdd.json --ipg-bdd3-certificate bdd3.json \
    --residual-scc --proof fallback.drat

Only if result says `IPG_BDD3_JSON_NEEDS_INDEPENDENT_CHECKER`, run:

  python3 research/ipg_bdd3_checker.py --cnf SOURCE.cnf \
    --graph bdd.json --certificate bdd3.json

## Important next gates

1. Generate **standard VeriPB proofs** for the compact 3D count
   derivation rather than treating the JSON checker as PB proof.
2. Compare verification-inclusive PAR2 and memory against
   the frozen strongest capacity and CDCL baselines, Kissat,
   CaDiCaL and CryptoMiniSat on source-disjoint prospective originals.
3. Refine selective activation: the 3D state space is often more
   expensive and may return UNKNOWN on SAT/difficult cases,
   so bounded dispatch must avoid negative runtime regressions.
4. Revisit other real original PCMAX instances only if
   genuinely improved proof coverage is certified.

Never merge into main before the proof and blind generalization
gates are satisfied.

# DRNAS MATH5 STANDARD-PROOF + FASTGATE1 — 2026-11-16

Experiment-only branch:
`experiment/drnas-math5-standardproof-gate1-20261116`.

No main changes, no frozen-binary replacement, no APK, no auto-promotion.

## 1. MATH5 independent VeriPB 3.0 proof export

`research/math5/emit_veripb_eo_multiplicity.py` compiles an already
SOURCE-CHECKED MATH5 JSON structural UNSAT certificate into
**cutting-planes VeriPB 3.0** for the restricted but useful case:

* selected source-grounded exactly-one clauses contain POSITIVE literals;
* all pairwise negative source AMO clauses for each group exist;
* each selected variable appears in exactly a common number d>=2 of
  groups, with group count q not divisible by d;
* no XOR-row or root-unit MATH5 proof is accepted by this converter.

Original source and certificate are first validated with
`research/math5/check_math5.py`. Every generated PBP must then be
accepted by independent `veripb-tool/bin/veripb --cnf EXACT.cnf proof.pbp`.
Emission alone is NOT certified.

For a group of k variables, original negative pair clauses imply the
clique bound `sum(~x_i) >= k-1`, via cutting-planes induction.
For k>=3, multiply the previous (k-1)-clique bound by (k-2),
add the k-1 original mutex clauses involving the new variable,
and divide by (k-1) with ceiling. The proof has O(q*k^2) input
references/operations and is a polynomial-size derivation in the
explicit pairwise-CNF representation.

Summing all q positive ALO constraints gives
`d*sum(x)>=q`. Dividing by d gives
`sum(x)>=ceil(q/d)`.
Summing the q clique bounds gives
`d*sum(~x)>=d*n-q`.
Dividing by d gives
`sum(~x)>=n-floor(q/d)`.
Both together contradict `sum(x)+sum(~x)=n` when q mod d != 0.

### Already locally tested with the pinned VeriPB 3.0.2 executable

Original SAT2026 `count` formulas (already previously seen in
GRAND UNIFIED; NOT a new prospective blind holdout):

* ID 31: 210 vars, 4011 clauses, source SHA256
  `8020990ff906e9b2f7ec72652da7db736d90db4170e104a888454dffa583aa88`.
  q=21, k=20, d=2. A directly equivalent local cutting-planes
  prototype emitted 34,603-byte VeriPB proof, **externally accepted**.
* ID 25: 990 vars, 42615 clauses, source SHA256
  `28b9b934f492f135dd00c3771d7670703daeb2fa03f98cf21ea8b7286958af4e`.
  q=45, k=44, d=2. Local proof 370,588 bytes,
  **externally accepted**.

Both native frozen MATH5 solvers also returned UNSAT with source-bound
exact-one group certificates in our local replay. The GitHub workflow
independently re-tests THIS committed emitter, project checker, and
external VeriPB under the full **8-second E2E cap**, twice per source,
comparing to unchanged pinned Kissat + DRAT. Do not infer strict PAR2
wins until the E2E CI report completes.

This is new ENGINEERING proof export, not a new combinatorial parity
theorem or a general XOR-to-VeriPB compiler. Other MATH5 proof types
currently return UNSUPPORTED, not an invented standard certificate.

## 2. Native C++ FASTGATE1

Separate CMake target:
`drnas-pcmax-mg7-ipg1-bdd3-fastgate1`.

Compilation macro `DRNAS_FAST_PC_GATE1` enables a conservative
source-only signature test for BDD layout: ALO job groups, signed
three-literal BDD transitions, and asserted positive/negative terminals.
If absent, the expensive optional PCMAX/IPG1/BDD2/BDD3 mathematical
guards are skipped and unchanged same-process CDCL + MG7/DRAT fallback
runs. This FASTGATE **NEVER proves SAT/UNSAT itself**.
Signature present => exactly the prior bounded native proof gates run.

Old `drnas-pcmax-mg7-ipg1-bdd3` binary remains the frozen reference;
its compile macros do NOT enable the fast gate.

Regression pilot compares 14 sources, three same-source serial arms:
CXX_BASE / unchanged CXX_BDD3 / new CXX_FAST, under 8s including
independent SAT model, DRAT, original-source capacity or BDD checks.
There are 6 previously observed 2026 original CNFs (including both
count instances) plus 8 deterministic generated BDD PCMAX fixtures.
Any baseline verified source solved-to-UNKNOWN regression fails pilot.
A green pilot is NOT a statistically significant broad speedup;
source-family-disjoint prospective testing is still required.

## Reproduce

```sh
python3 research/math5/emit_veripb_eo_multiplicity.py \
  --cnf original.cnf --certificate math5_source.json \
  --output original.pbp --meta emitted.json
veripb-tool/bin/veripb --cnf original.cnf original.pbp

python3 research/math5/math5_standard_two_count.py
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target drnas-pcmax-mg7-ipg1-bdd3-fastgate1 -j2
python3 research/math5/fastgate1_paired.py
```

Workflow: `.github/workflows/drnas-math5-standard-fastgate1.yml`.
Restores exactly the frozen original source and reference binaries from
successful GRAND UNIFIED run `43853390060`; never replaces baseline.

PROMOTION GATES: no incorrect answers or rejected certificates,
source-frozen verification, no lost BDD3 solves, enough independent new
original formula families, standard verifiers, verification-inclusive
PAR2 gains with family-level confidence and user approval.

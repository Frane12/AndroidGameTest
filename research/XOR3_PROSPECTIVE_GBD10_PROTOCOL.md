# DRNAS — prospective 10-original XOR/Tseitin GBD holdout, 2026-11-17

**Branch:** \`experiment/drnas-xor3-prospective-gbd10-20261117\`.
**No changes to main, original reference binaries, previously verified proofs, or frozen older datasets.**

## Goal and history

The new XOR3-carry MATH5 → extended cutting-planes VeriPB bridge was
independently certified on original \`tseitin_n188_d3.cnf\` (282 vars,
752 clauses) in GitHub run
[44041467828](https://github.com/Frane12/AndroidGameTest/actions/runs/44041467828):
two strictly verified source-bound UNSAT proofs in 0.08436s and
0.08493s complete E2E. This was **retrospective** and cannot demonstrate
unseen generalization by itself.

Here we preselected a new ten-original set, including Tseitin 3-XOR
from other creators/years/sizes, grid Tseitin variants that may NOT
fit XOR3, two ordering-principle-XOR formulas, and one
minimal-disagreement-parity control formula. All are authentic,
unchanged CNF downloads from the Global Benchmark Database for
SAT Competition 2023, 2024 or 2025 Main tracks. We intentionally
**do not** use catalog SAT/UNSAT classifications during evaluation.

The exact source GBD hash, 32-digit isohash, 16-digit isohash2,
filename, track and source family were committed in
\`research/xor3_prospective_gbd10/prespec.json\` at commit
\`68591920fa0478094cb304c80b9ee2f0d79596d8\`
**BEFORE any of these ten original sources were downloaded,
inspected or evaluated by any DRNAS/competitor in this experiment.**

## Preselected instances (not selected based on results)

| ID | Original GBD source | Original file | Track |
|---:|---|---|---|
| 0 | tseitin-formulas | tseitin_d3_n158.sanitized.cnf.xz | 2024 |
| 1 | tseitin-formulas | tseitin_d3_n162.sanitized.cnf.xz | 2024 |
| 2 | tseitin-formulas | tseitin_d3_n174.sanitized.cnf.xz | 2024 |
| 3 | tseitin-formulas | tseitin_d3_n160.cnf.xz | 2023 |
| 4 | tseitin-formulas | tseitin_d3_n200.cnf.xz | 2023 |
| 5 | tseitin-formulas | tseitin_grid_n12_m12.cnf.xz | 2025 |
| 6 | tseitin-formulas | tseitingrid7x160_shuffled-sc2016.cnf.xz | 2023 |
| 7 | ordering-principle-xor | xor_op_n38_d3.cnf.xz | 2025 |
| 8 | ordering-principle-xor | xor_op_n40_d3.cnf.xz | 2025 |
| 9 | minimal-disagreement-parity | par32-2.shuffled-as.sat03-1534.cnf.xz | 2025 |

GBD catalog:
https://benchmark-database.de/?context=cnf&track=main_2025
https://benchmark-database.de/?context=cnf&track=main_2024
https://benchmark-database.de/?context=cnf&track=main_2023

## Identity and source-freeze controls

Preparation restores three earlier source manifests and SHA-frozen
reference binaries from the successfully completed 2026-11-16
seven-family run \`43913499707\`:
- 67 original SAT2026 formulas in \`unified_realblind100_inputs\`
- 10 earlier SAT2025 clique-coloring formulas
- 10 SAT2025 7-family original formulas, including known Tseitin ID6.

Before the holdout solver jobs can even start,
\`research/xor3_prospective_gbd10/freeze.py\` checks all selected
GBD IDs and **both** available GBD isohash forms against the 87
previously frozen instances. Disjointness was independently checked
before prespec commit, with zero collisions.

It downloads all ten exact source files by prespecified GBD hash,
caps 20MB compressed/50MB decompressed per source, checks unmodified
DIMACS header/clauses/variables and writes a SHA-256 manifest only
after all ten succeed. If any original is too large, absent,
malformed or collides, freeze FAILS and none of the solver jobs run.
It must not substitute an alternative source after seeing any
SAT/UNSAT or timing result.

No source-family name, known result, file name, prior benchmark
runtime or source ID is fed to a solver or source prover.
"New" means selected prospectively and source-identity-disjoint
from these **specific 87** old originals; it does not mean no
researcher has ever seen these public competition instances.
Since there are only three catalog source families, any family
bootstrap CI is descriptive, not robust inferential evidence.

## Six arms and strict proof-inclusive E2E

Every source gets **two repeats**, **six arms**,
10 × 2 × 6 = **120 individual serial solver trials**.
Five independent GitHub shard jobs (two source IDs each),
at most three shard runners concurrently, one logical CPU per
solver process and no parallel solver portfolio within an arm.

| Mode | Interpretation |
|---|---|
| \`XOR3_NATIVE_VERIPB\` | Exact unchanged frozen native X59+MATH5 discovers source-supported XOR3 cert; new source-checked RED/RUP/CP exporter; external VeriPB on original |
| \`XOR3_SCOUT_THEN_MATH5\` | Same proof path scoped to a 1.0-second scout, then sequential baseline X59+MATH5 fallback using the **remaining** common 8s E2E budget |
| \`X59_MATH5_VERIPB\` | Existing unchanged MATH5+restricted EO standard exporter |
| \`Kissat\` | Frozen Kissat binary; independent SAT model or DRAT |
| \`CaDiCaL\` | Frozen CaDiCaL binary; independent SAT model or DRAT |
| \`CryptoMiniSat\` | Frozen CryptoMiniSat binary, one thread; independent SAT model or FRAT |

The external VeriPB, DRAT or FRAT checker must independently
verify any claimed UNSAT result directly on the original SHA-pinned
CNF. SAT models are independently checked on the same source.
No nonstandard MATH5 structural JSON is counted in the strict
score. Unverified, resource-limited, unsupported, timed-out,
or failed external validation scores PAR2 penalty of 16 seconds
for that arm/trial (8s cap). Wrong SAT/UNSAT certificate is a
critical error.

The original algorithm \`research/math5/emit_veripb_xor3_carry.py\`
and independent source checker are NOT changed after last certified
run; their complete SHA-256 is recorded in \`protocol.json\`.
An adversarial preflight reruns 24 independently VeriPB-verified
synthetic UNSAT proofs and 72 source/SAT-model rejection controls.

## Interpreting outcome, no overclaim

This is a **prospective instance-level generalization pilot**:
- Did five new d3 Tseitin instances produce externally accepted
  source-bound standard proofs within the same 8s cap?
- Do grid and other XOR-related CNFs correctly return UNKNOWN
  when unsupported rather than ever generating false UNSAT?
- Does bounded sequential fallback avoid major regressions against
  the old frozen MATH5 baseline?
- How does strict PAR2 compare to Kissat, CaDiCaL and CryptoMiniSat
  across all **ten**, including every timeout?

An exploratory pilot of 10 instances from 3 correlated catalog
families is NOT evidence that arbitrary SAT is polynomial or that
DRNAS dominates all solvers. No changes to \`main\` until
independent and larger prospective validation.

Workflow:
\`.github/workflows/drnas-xor3-prospective-gbd10.yml\`

Strict final artifact:
\`results/xor3_prospective_gbd10/final.json\`,
created only after all 120 attempts and checks.

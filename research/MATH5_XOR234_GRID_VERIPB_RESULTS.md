# DRNAS MATH5 XOR2/3/4 → standard VeriPB via source-checked XOR4 splitting

**Research date:** 2026-11-17. Experimental branch:
\`experiment/drnas-xor234-grid-veripb-20261117\`.
No changes to main, frozen originals or baseline solver binaries.

## Motivation: prospective XOR3 result and its known limitations

Earlier prospective instance-level original SAT2023/2024/2025 GBD
benchmark [44043273439](https://github.com/Frane12/AndroidGameTest/actions/runs/44043273439)
verified **five different unseen 3-regular Tseitin original
CNFs x2** (10 independently accepted standard VeriPB UNSATs;
strict PAR2 160.89234s across all 10 sources) versus baseline
Kissat/CaDiCaL/CryptoMiniSat each strict PAR2 320s. Three different
catalog family labels were sampled but all five successes were
from one restricted 3-XOR family.

Two **other unchanged originals** in that same frozen source-first
set were diagnosed *after* the result as the next proof bridge targets:
- ID 5, \`tseitin_grid_n12_m12.cnf\`, SHA
  \`79618e35c83016fd1a188eb63ed499c3d1d4c364f710c9c9a93eb7925054a9af\`:
  264 source variables, 968 clauses, 144 source-checked XOR equations
  (**4 width-2, 40 width-3, 100 width-4**).
- ID 6, \`tseitingrid7x160_shuffled-sc2016.cnf\`, SHA
  \`0b37c65f0c7cb2c9ed375d09a7ab3d77da34266a908f368e67186754fe9dbd37\`:
  2,240 source variables, 8,960 clauses, 1,120 source-checked
  **width-4** XOR equations.

On both, the original frozen native X59+MATH5 quickly produced
a valid custom source-bound XOR contradiction. Every selected
source XOR variable appears in **exactly two** rows, and the
sum of row right-hand sides is odd. The old VeriPB bridge
supports ONLY width-3 and must report UNKNOWN for these.

## The new standard proof bridge

Keep original CNF completely unchanged. The independent source
checker (\`research/math5/check_math5.py\`) rechecks the exact
source SHA-256, all forbidden-assignment clauses and global
odd XOR contradiction before proof construction.

For a source XOR4 row with Boolean inputs x,y,z,w:

\`\`\`
x XOR y XOR z XOR w = b
\`\`\`

Introduce fresh \`q = x XOR y\` via four verified VeriPB RED
extension clauses. Derive each of the four forbidden-assignment
clauses for \`q XOR z XOR w = b\` from the original source
XOR4 clauses, **with three source-backed RUP steps per clause**
(resolution first on x). Every new source XOR4 row becomes
two derivable 3-variable equations:

\`\`\`
x XOR y XOR q = 0
q XOR z XOR w = b
\`\`\`

The new q appears **twice** and source x,y,z,w each appear once
in this transformation, preserving the global mod-2 multiplicity
condition. Original XOR3 rows are used unchanged.

For source XOR2 rows of odd RHS, their two original
source clauses are exact lower and upper pseudo-Boolean bounds.
For even RHS, introduce one RED AND carry \`t=x AND y\`, derive
reverse RUP implications and form both integer inequalities.

All 3-XOR rows use the independently accepted old
MATH5 carry RED/RUP/CP proof. For every row this produces
both directions of:

\`\`\`
sum(row Boolean variables) - 2 * sum(row carry bits) = rhs(row)
\`\`\`

Every selected original and new splitting variable occurs
**twice**, so summing yields even coefficients on the left.
Odd total right-hand side contradicts integrality. VeriPB
independently checks the entire RED/RUP and cutting-planes
derivation against the ORIGINAL file and accepts ONLY if the
final conclusion is UNSAT.

This is a restricted, known extended cutting-planes proof
mechanism, **not** a polynomial algorithm for arbitrary SAT,
nor a new complexity theorem.

## Local source- and checker-verified outcomes

Using the original freeze archive of run 44043273439,
the unmodified native MATH5 source certificate was extracted
again on one logical CPU per process. The new generic
XOR2/3/4 bridge produced external VeriPB 3.0.2
\`s VERIFIED UNSATISFIABLE\` on BOTH unchanged originals.

| Original | RED steps | RUP steps | CP steps | Standard PBP | Emitter + external VeriPB (local) |
|---|---:|---:|---:|---:|---:|
| ID5 (144 XOR rows) | 1,682 | 1,920 | 965 | 165,156 B | 0.044 s |
| ID6 (1,120 XOR4 rows) | 16,802 | 20,160 | 8,965 | 1,820,569 B | 0.506 s |

These local measurements include **proof emission + independent
external checker only**, not native X59+MATH5 certificate generation
nor entire standardized GitHub-runner E2E overhead.
No independent strict PAR2 benchmark claim yet.

## Safety and strict CI audit

\`research/math5/xor234_split_selftest.py\` performs
24 independently VeriPB-verified UNSAT synthetic controls
covering width2, width3, width4 and mixed widths.
It also runs 48 known SAT controls with explicit all-false
assignments (24 even-RHS and 24 one-source-clause-removed),
and 24 forged SHA controls, all of which must safely fail
without an UNSAT proof. They are NOT original contest benchmarks.

\`research/math5_xor234_grid2/benchmark.py\` is a dedicated
source-frozen **retrospective** strict test over IDs 5 and 6,
2 repeats each, 6 serial arms, **24 E2E trials**:
- new XOR234 split RED/RUP/CP + frozen native MATH5
- unchanged old XOR3-only VeriPB exporter + native MATH5
- unchanged X59+MATH5 original EO-only standard exporter
- frozen Kissat + independently checked original DRAT
- frozen CaDiCaL + independently checked original DRAT
- frozen CryptoMiniSat + independently checked original FRAT

For each attempted source SHA-bound original, all attempts
use the same 8s wall-clock cap including native solver
and external proof verification, with strict PAR2=16s
for timeout, unsupported or source-verifier-only results.
One logical CPU per solver, no solver portfolio. Critical
errors are fatal, even for source-certificate invalidity.

The GitHub workflow
\`.github/workflows/drnas-math5-xor234-grid2.yml\`
restores the exact frozen originals and 2026-11-17 native
reference binary SHA hashes from run 44043273439,
independently reruns safety tests, and publishes detailed
source- and proof-hash-bound per-trial logs and a final audit.
No automatic main promotion.

## Scientific next test

Because both new successes were examined before constructing
this XOR4 proof exporter, they are *retrospective development
evidence*. To claim generalization beyond these grid
originals, prespecify a new untouched XOR2-4 Tseitin
source set, exact original GBD/hash/isohash freeze before
candidate evaluation, and compare against all three references
under proof-verified end-to-end limits.

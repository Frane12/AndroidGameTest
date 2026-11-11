# DRNAS ATLAS2 — reusable local Boolean blocks / batch proof-equivalent rewrites

**Research-only branch:** `experiment/drnas-atlas2-structured-batch-20261111`. Stable/main,
ARL1-E and ATLAS1 reference source files are not modified. The resulting
`research/drnas_atlas2.cpp` is an independent native DRNAS solver.

## The mathematical proposal

Compile the exhaustive 2–4 variable NPN Boolean function atlas *offline*
using `research/drnas_atlas1_generate.py`. There are exactly 4, 14 and
222 NPN classes for 2, 3 and 4 inputs; the run-time table maps the original
input variables and polarities back. The **output-complement bit selects a
different formula recipe**, not an SAT-preserving output inversion.

For every candidate block, obtain all selected ORIGINAL CNF clauses with
variable supports contained in the block's two-to-four variables, enumerate
every assignment to those variables, reconstruct the atlas CNF and **compare
all truth-table rows exactly**. A block is eligible only if the number of
clauses does not grow and it saves one or more literal occurrences. Candidates
are scored offline within a fixed per-input cost budget and at most 32
**pairwise clause-disjoint** modules are committed as one batch. Modules may
share variables; they cannot share removed original clause IDs. All
unaffected clauses are retained verbatim. This establishes full logical
equivalence of the rewritten and original CNF *over the same variables*.

Scanner: at most 4000 source clauses, up to 3ms scan, up to 3ms probe,
one bounded cycle followed by COMMIT, SLEEP or FALLBACK. NPN reorientation
and equivalence are tested by a native `--atlas-selftest` over all 65,808
2–4-input Boolean functions. Synthetic positive and negative controls check
multiple disjoint rewrites and actual original SAT witnesses.

**Limitation:** canonical recipe cover is deterministic and semantically
exact but not a global minimum CNF. "Saved literals" is not "time saved".
Clause order and CDCL propagation may get better or worse after rewriting.
No LRAT/FRAT UNSAT certification is supplied by the native core.

## Controlled generated structured cohort — FINISHED

GitHub Actions:
https://github.com/Frane12/AndroidGameTest/actions/runs/42934744147

These are **source-fixed, deterministic, constructed formulas, not external
benchmark instances**. Generator `research/drnas_atlas2_generate_structured.py`
has four families: (1) AND/OR, (2) XOR/XNOR, (3) exactly-one + gates, and
(4) mixed ITE/circuits. Each has a minimally encoded control and a treatment
where explicitly entailed superset clauses were introduced. All have planted
SAT models checked against source, but solver is never given the witness.
SHA256(CNF) manifests, 3 repeats, 20 s E2E cap, one logical CPU per arm,
5 arms: `drnas` (native A), `atlas1`, `atlas2`, pinned Kissat, CaDiCaL.

The 8 source-formula ATLAS2 commit counts were:
AND/OR minimal **7** blocks, redundant **32**;
XOR minimal **3**, redundant **32**;
exactly-one minimal **4**, redundant **32**;
ITE/mixed minimal **5**, redundant **32**.
Total **147** disjoint proof-equivalent replacements, **732** fewer literal
occurrences in the restructured CNFs. Some savings in nominally minimal
cohorts arise from **cross-block interactions and extra source constraints**,
not because the individual Tseitin gate encodings were inherently nonminimal.
All variants solved **24/24** generated SAT trials with independently checked
original-model witnesses.

| Arm | Solved | Total PAR2 (s) |
|---|---:|---:|
| DRNAS A | 24/24 | 0.097450 |
| Kissat | 24/24 | 0.099962 |
| DRNAS ATLAS2 | 24/24 | 0.102708 |
| DRNAS ATLAS1 | 24/24 | 0.104168 |
| CaDiCaL | 24/24 | 0.112065 |

**Interpretation:** exact compression works, but ATLAS2 was **5.4% slower**
than native A in total E2E on these short, constructed formulas. No proven
runtime breakthrough and no claim of statistical significance.

## Independent public structured cohort — separate experiment

Workflow: `.github/workflows/drnas-atlas2-real.yml` and
`research/drnas_atlas2_real_bench.py`. The four tests are real hardware
verification (miter) CNFs released as
[HWMCC 2024 via Tractables/cnfs](https://github.com/Tractables/cnfs/tree/main/hwmcc),
source pinned to commit
`de4731f68e5a5bb6629269b3be1d19b44e812763` and **individual Git
blob hashes**. They are not constructed to favor atlas patterns. Files:
`analog_estimation_convergence_unsafe.cnf.xz`,
`93.c.cnf.xz`, `bin-suffix-5.cnf.xz`,
`benchmark04_conjunctive.cnf.xz`.

For these externally sourced formulas, E2E cap is 15 s, 2 matched repeats,
one CPU, 5 variants. **Only SAT models verified against original clauses**
are counted as verified solutions. UNSAT without independent proof is
reported `UNSAT_UNVERIFIED` and earns no solved credit. UNKNOWN and
UNSAT_UNVERIFIED are scored PAR2=30 s, to avoid suggesting an uncertified
UNSAT result is independently established. Therefore reported "solved" and
PAR2 are deliberately conservative relative to conventional SAT competition
rules and must be read together with raw backend statuses.

## Next scientific question

For realistic circuit encodings, determine whether exact local Boolean
compression improves **BCP watch visits or learned conflict quality**, after
all preprocessing cost is paid. If it does not, do not add a bigger atlas
without evidence. Candidate alternatives: an ultra-cheap structural
fingerprint before loading the full 2–4-input table, and proof-checked
specialized XOR/cardinality representations only when the projected gain
exceeds the lookup cost.

Relevant background:
- Andraschko, Danner, Kreuzer (2024),
  "SAT Solving Using XOR-OR-AND Normal Forms", Mathematics in Computer Science.
- Armin Biere et al., "CNF Encoded Isomorphic and Optimized Miters from
  Hardware Model Checking Competition 2024 Models", Zenodo 2025,
  DOI:10.5281/zenodo.15207209.

# DRNAS ATLAS-MAP1 — Source-certified structural shortcut map

**Branch:** `experiment/drnas-atlasmap1-structural-shortcuts-20261111` (isolated, based on ATLAS-X).  
**Author:** Frane Drnas · **Status:** experimental / unreviewed.

## What this actually implements

ATLAS-MAP1 adds a *cost-bounded relational cheat sheet* to the independent
native DRNAS R3C SAT solver and existing ATLAS-X frontend. Its first useful
relation class is **source-certified two-variable parity**.

When BOTH original clauses `(a OR b)` and `(NOT a OR NOT b)` exist, exactly
one of those literals is true. For variables `x=abs(a)`, `y=abs(b)`, the
entailed relation is:

`value(x) XOR value(y) = 1 XOR (a<0) XOR (b<0)`.

ATLAS-MAP1 uses a parity **disjoint-set union (DSU)** to compose these
relations transitively. This is the inexpensive "cheat sheet": every
variable has a representative and a polarity (possibly negated). The
original source clauses themselves are the local proof of each learned
edge; no pattern is accepted from frequency or statistical prediction alone.

All original clauses are rewritten consistently through that proven map.
Tautologies and duplicates are removed. If a source-pair cycle is
inconsistent, the preprocessor **falls back to the original CNF**;
independent UNSAT proof emission is not implemented. On SAT, the solver's
representative model is lifted to every original variable and **the full
original CNF is checked**. No model check is skipped.

The selector prefers this cheap, exact rewrite when it saves literals.
It **does not invoke ATLAS-X's 5/6-variable lazy join** after such a
commit. Without a profitable parity shortcut it invokes the existing,
bounded, locally truth-table-verified ATLAS-X pass. The former ATLAS-X
module and native R3C CDCL are reused, not replaced.

## Optional bounded strategy memory

`MAP_LEARN` accepts `--memory PATH`, a small tabular experience file
containing only a coarse structural signature and **seen/probed/hit
counters**. It **never caches or reuses an unverified logical deduction**.

After at least four failed ATLAS-X probes for the same signature, the
learner skips the costlier ATLAS-X probe while retaining a one-in-eight
exploration opportunity. Each individual shortcut still requires exact
source evidence. Memory files must be kept separate between training and
evaluation; otherwise performance estimates leak.

This is a small *cross-formula strategy learner*, **not** dynamic
clause-level intervention during CDCL search, and not a trained AI model.
Frequency alone is not evidence of a usable logical implication.

## Modes and reproducibility

| Arm | Behavior |
| --- | --- |
| `A` | Exact native R3C baseline, no ATLAS |
| `ATLASX` | Existing compressed truth-table/local lazy join |
| `MAP1` | Source-certified parity DSU first; if no gain, ATLAS-X |
| `MAP_LEARN` | MAP1, with optional separate persistent probe memory |

```bash
mkdir -p mre_atlasmap1/bin
python3 research/drnas_atlas1_generate.py --out mre_atlasmap1/atlas1_table.hpp
g++ -std=c++17 -O2 -Wall -Wextra -I mre_atlasmap1 \
  research/drnas_atlasmap1.cpp -o mre_atlasmap1/bin/drnas_atlasmap1
mre_atlasmap1/bin/drnas_atlasmap1 --atlasmap-selftest
python3 research/drnas_atlasmap1_smoke.py
mre_atlasmap1/bin/drnas_atlasmap1 example.cnf --mode MAP1 --time 10
mre_atlasmap1/bin/drnas_atlasmap1 example.cnf --mode MAP_LEARN --time 10 --memory mre_atlasmap1/train.tsv
```

The native randomized selftest compares 350 small source-paired CNFs
with an independent exhaustive truth-table satisfiability oracle.
When a rewrite commits, it additionally checks **every model of the
reduced six-variable formula can be lifted to a model of the original**.
Dedicated tests cover inconsistent parity cycles, missing evidence,
source-certified equal/negated aliases, and a synthetic mixed-formula
control. Smoke checks SAT witnesses against the original source.

### Benchmark

Workflow `.github/workflows/drnas-atlasmap1.yml` validates the
algorithm, then attempts a *prospective-to-this-build* source-selected
SATLIB comparison, rank 41 (four SATLIB families, two repeats, 10 s cap).
It compares A, ATLASX, MAP1, MAP_LEARN **cold/no memory**, Kissat and
CaDiCaL, one logical CPU per measured solve. SHA-256, raw JSON, original
models and per-shard PAR-2 are recorded. The SATLIB inputs are publicly
known, **not globally blind**. No learned-memory performance claim
can be inferred from the cold MAP_LEARN arm.

**Important limitations:**

1. The learning and map pass currently operate **before** native CDCL
   search; no in-trail or restart-time intervention is implemented.
2. The gate is heuristically cost-bounded; a saved-literal count does
   not establish faster solving. Selective fallback can be slower.
3. Rewriting through certified parity aliases is **equisatisfiable**
   with an explicit SAT model lift, rather than a truth-table-identical
   formula over all original variable assignments.
4. The implementation has **no independently checked original-CNF UNSAT
   LRAT certificate**. Raw UNSAT is not a certified result.
5. Positive structural smoke controls cannot substitute for blind
   real-world improvements. Do not promote to `main` without audited
   correctness, verified SAT models, stratified PAR-2 and regressions.
6. Source scan bounded to 20k clauses and 12ms max, with deliberate
   safe fallbacks. Learning memory is local file state, not a proof cache.

## Next development (not implemented here)

Incremental relation event queue after each CDCL restart; proof-carrying
exports from XOR rows; dependency graph for source-certified long-range
relations; per-family frozen training/holdout selection. Each would
require a separate correctness and end-to-end audit before release.

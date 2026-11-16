# DRNAS GRAPH-CLIQUE VERIPB — 2026-11-16

**Experimental branch:** \`experiment/drnas-graphclique-veripb-real67-20261116\`.
No changes to main, any source-frozen reference binary or Android APK.

## Research result (local independently verified, NOT blind)

For all 8 ORIGINAL SAT Competition 2026 Main-track \`graph-coloring\`
CNFs in the previously frozen 67-CNF manifest from GitHub run
\`43853390060\`, a source-only structural recognizer found a clique of
size \(k+1\) in a graph constrained to just \(k\) colors.

| Frozen ID | Colors \(k\) | Clique | Source status | Local VeriPB 3.0.2 |
|---|---:|---:|---|---|
| 20 | 29 | K30 | UNSAT | VERIFIED UNSAT |
| 26 | 15 | K16 | UNSAT | VERIFIED UNSAT |
| 32 | 30 | K31 | UNSAT | VERIFIED UNSAT |
| 37 | 24 | K25 | UNSAT | VERIFIED UNSAT |
| 41 | 30 | K31 | unknown | VERIFIED UNSAT |
| 49 | 19 | K20 | UNSAT | VERIFIED UNSAT |
| 55 | 10 | K11 | UNSAT | VERIFIED UNSAT |
| 58 | 48 | K49 | unknown | VERIFIED UNSAT |

The catalog status is **never** used to prove anything. For source IDs
41 and 58, the label was \`unknown\`, but the independent external
VeriPB check has accepted a formal contradiction of the source CNF.
All 8 local proof pipelines, including Python startup, source parsing,
search, proof generation and VeriPB, completed under 8 seconds on the
local audit host. This is not yet a GitHub-runner paired E2E result.

### What the proof really means

Source ALO clauses require each selected vertex to receive at least
one of \(k\) colors. Original binary negative clauses block two
adjacent vertices from sharing a given color. Every one of the
\(\binom{k+1}{2}\) selected clique edges has the required ORIGINAL
negative clauses for each of the \(k\) colors (with explicit consistent
color alignment even if ALO literals are arbitrarily permuted).

For a clique of \(k+1\) vertices:
\[
\sum_{v \in K_{k+1}} \sum_{c=1}^k x_{v,c} \ge k+1
\]
from original ALOs. For each color \(c\), source edges form an
at-most-one clique in that color. Derive the implied
\[
\sum_{v \in K_{k+1}} \neg x_{v,c} \ge k
\]
by cutting planes: start with original binary edge clause and extend
the clique by multiplying the previous bound by \(r-2\), adding the
\(r-1\) original edges to the new vertex, and dividing by \(r-1\) with
ceiling. Sum all \(k\) clique bounds and all \(k+1\) ALOs; the
contradiction is \(0\ge1\). Every proof step is a deterministic
reference to original source clause indices or a valid CP operation.
**VeriPB 3.0.2**, not our emitter, must accept the full original CNF
and the emitted proof before the result is scored UNSAT.

The proof has polynomial size in the explicit clique source witness.
**Finding** an arbitrary \((k+1)\)-clique is NP-hard when \(k\) varies;
our bounded search is not a polynomial-time general algorithm or a
new theorem, and false negatives are returned as UNKNOWN.

### Important source-soundness controls

The graph reconstructor accepts source constraints only, not filenames,
catalog labels, benchmark outcomes or graph hints. Original positive
ALO groups must be non-overlapping and have a common width; every
candidate edge needs a full one-to-one matching of original
negative clauses. Edge matchings can be inconsistent around cycles:
the chosen clique is therefore re-aligned to a common color
permutation, and all \(k\binom{k+1}{2}\) original clauses are independently
rechecked. Then and only then is a CP proof emitted.

Locally tested with 80 CNFs having direct satisfying assignments
(0 false UNSAT), 80 intentionally uncolorable constructed CNFs,
40 global variable-label permutations, 10 external VeriPB accepted
generated proofs, and a one-clause-removed K6 five-color SAT witness,
plus a malformed-source negative control.

## New full 67-CNF strict E2E paired CI experiment

Workflow \`.github/workflows/drnas-graphclique-real67.yml\`.

The benchmark has 67 byte-identical original CNFs, 2 repetitions,
6 arms, 10 independent shards, and **804 expected trials**. Exactly
one logical CPU is used by each trial; arms run SERIAL within a
pair; there is no parallel portfolio/second solver, and no solved
instances are removed from scoring. All trials charge ONE 8-second
end-to-end cap, including source SHA, cheap ALO signature test, graph
generator process startup, full source checks, proof emission and
external VeriPB. Timeout/unsupported gets 16 seconds standard PAR2.

Compared arms:

* \`GRAPH_ONLY\`: source-structural \(k+1\)-clique followed by external
  standard VeriPB; UNKNOWN if unsupported (no CDCL).
* \`GRAPH_PLUS_MATH5\`: source-only graph proof scout with a bounded
  budget, then same unchanged native X59+MATH5 standard VeriPB E2E
  fallback with **remaining** wall time; no concurrent solver.
* \`X59_MATH5_VERIPB\`: unchanged previous standard MATH5 wrapper.
* \`Kissat\`, \`CaDiCaL\`, \`CryptoMiniSat\`: exact original source,
  same standard-model/DRAT/FRAT checker and 8-second E2E budget.

The benchmark writes a separate, source-SHA-bound record for each
source/arm/repetition. No custom JSON structural proof may count as
strict. Before completion it requires all 804 records, no duplicates,
all original source hashes, no bad SAT models or unverified UNSAT,
no contradictory independently checked SAT/UNSAT and no critical
errors. It also reports structural-inclusive score separately
from STRICT E2E PAR2, proof-kind attributions and family-clustered
bootstrapped intervals. All source and baseline binary hashes are
checked against the frozen \`43853390060\` artifact.

### Scope and promotion

This is a **retrospective development test** on previously seen
original CNFs, not a new independent SAT2026 family-disjoint blind
holdout. Constructed controls are adversarial safety tests, not a
claim of general competition performance. After successful E2E CI,
an unseen, source/family-disjoint test must be frozen *before*
candidate results are observed. Do not promote to main without
user review and independent proof/PAR2 assessment.

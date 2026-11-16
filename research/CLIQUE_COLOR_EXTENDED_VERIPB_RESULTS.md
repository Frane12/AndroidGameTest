# DRNAS Clique-vs-Coloring: STANDARD VeriPB extended source proofs

**Research date:** 2026-11-16. **Experimental branch only:**
\`experiment/drnas-cliquecolor-ext-veripb-proof1-20261116\`.
No main changes. No frozen source/input alterations. No solver-portfolio,
no P=NP claim, no worldwide proof-complexity novelty claim.

## Why the previous blind benchmark produced 0/20

Completed source-first SAT Competition 2025 Main run
[43891106380](https://github.com/Frane12/AndroidGameTest/actions/runs/43891106380)
evaluated exactly 10 original CNFs, 2 repetitions, six serial solver
arms: 120 attempts. Every arm scored **0/20 verified, strict PAR2 320s**
under the 8s cap, and all CI jobs passed.

All 10 sources had been SHA-frozen *before* this earlier benchmark.
Subsequent independent clause audit recognized the familiar
clique-versus-coloring unsatisfiable family. That diagnosis is in
\`research/CLIQUE_COLORING_2025_SOURCE_AUDIT.md\`.

The **new** formal proof procedure was developed AFTER seeing those
10 benchmark results. Thus the following is **retrospective development
evidence**, NOT a prospective blind solver-performance evaluation.

## New direct-source standard proof

1. The generator reconstructs original graph edge variables
   \`E[u,v]\`, clique-position variables \`P[i,u]\` and coloring
   variables \`C[u,z]\` by checking every required source clause,
   not reading filename, SAT status, catalog classification or solver
   outcome. Source SHA256 remains unchanged.
2. Introduce fresh definition variables \`Q[i,u,z] = P[i,u] AND C[u,z]\`.
   The three definitional clauses are added by VeriPB \`red\`
   strengthening with explicit assignment witnesses \`Q=0/1\`.
3. Introduce \`Y[i,z] = OR_u Q[i,u,z]\`, again with checker-verified
   \`red\` extension clauses.
4. Derive with explicit source-backed \`rup\` and **ordered RUP hints**
   \`OR_z Y[i,z]\` for each of the \`k\` clique positions. The proof
   uses the original source clique-position ALO and color ALOs.
5. For every pair \`i < j\` and every color z, derive
   \`~Y[i,z] OR ~Y[j,z]\` using original clique injectivity,
   P-position-to-edge implications and source edge/color conflicts.
   The intermediate RUP proof is O(n²) clauses per pair/color,
   with explicit propagation constraint IDs; no CDCL search.
6. For each color z use cutting-planes clique AMO induction to derive
   \`SUM_i (~Y[i,z]) >= k-1\`. Sum with all position-color ALO
   constraints to conclude \`0 >= k-c = 1\`, since every instance
   has \`k=c+1\`. External VeriPB independently validates the
   **entire unchanged original CNF** and every extension/proof step.

The proof is polynomial-size in the explicit clique-versus-coloring
source encoding (O(k² c n²) RUP steps, plus extension clauses).
It does **not** imply polynomial-time solving of arbitrary SAT or a
new theorem: extension-strengthened VeriPB is stronger than the
ordinary syntactic CP system with classical lower bounds for this
family. It uses the existing documented \`red\`, \`rup\` and
\`pol\` proof system.

## Independent local verifier result: all 10 original CNFs

Exact original source CNFs SHA-frozen in completed run 43891106380.
AMD64 Linux, **one logical CPU per proof**, Python native extension
emitter followed by external **VeriPB 3.0.2**. Wall-clock includes
original CNF SHA check, source parsing and independent source grammar
audit, proof generation and verifier startup. Times vary by host;
these are NOT yet 8s GitHub runner paired PAR2 timings.

| ID | n | k clique | c colors | Hint proof bytes | Whole local E2E seconds | External VeriPB |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 100 | 6 | 5 | 62,033,404 | 7.0810 | VERIFIED UNSAT |
| 1 | 30 | 7 | 6 | 8,866,052 | 0.8279 | VERIFIED UNSAT |
| 2 | 50 | 6 | 5 | 14,639,940 | 2.0897 | VERIFIED UNSAT |
| 3 | 30 | 11 | 10 | 38,798,904 | 3.0615 | VERIFIED UNSAT |
| 4 | 40 | 6 | 5 | 9,386,456 | 0.8925 | VERIFIED UNSAT |
| 5 | 30 | 9 | 8 | 20,333,424 | 1.8860 | VERIFIED UNSAT |
| 6 | 26 | 7 | 6 | 6,635,156 | 0.5511 | VERIFIED UNSAT |
| 7 | 15 | 7 | 6 | 2,084,775 | 0.1972 | VERIFIED UNSAT |
| 8 | 14 | 7 | 6 | 1,826,305 | 0.2445 | VERIFIED UNSAT |
| 9 | 32 | 5 | 4 | 3,189,020 | 0.3091 | VERIFIED UNSAT |

First unhinted direct-source VeriPB prototypes were **also accepted**
on all ten, but ID0 external verifier time alone was 53.82s.
With *ordered RUP hints*, the external verification time dropped to
**1.69s on ID0** in the focused same-source comparison (~31.8x
checker-only improvement). The hints increase proof bytes but avoid
large implicit unit-propagation searches. The full local revised ID0
production+checking finished at 7.081s, borderline for an 8s cap.

The original source 8 lacks one optional same-position AMO clause and
has an additional negative unit. This does not compromise the exact
source-backed proof: only original position-ALO, cross-position
injectivity, position-to-edge, vertex-color ALO and edge-color
clauses are used. VeriPB accepted its unchanged source.

## Adversarial source safety

The source-only structural checker also ran **80 constructed
source-supported UNSAT examples** and **80 explicit SAT witness
controls** (20 each by removing a required position-ALO, clique
injectivity, selected-edge or edge-color source clause). It rejected
all 80 satisfiable controls with UNKNOWN; the controls carry complete
true satisfying assignments. It also accepted a valid UNSAT source
with an additional negative unit. The standalone GitHub selftest
includes 10 external VeriPB proof acceptances on small generated
UNSAT controls.

This is NOT an arbitrary heuristic guessing UNSAT: if any original
clause is absent, proof production refuses to proceed.

## Check it yourself

Generator: \`research/clique_color_er/emit_veripb.py\`

Independent source checker:
\`research/clique_color_er/source_check.py\`

Safety tests: \`research/clique_color_er/selftest.py\`

8s all-original, two-repeat proof benchmark:
\`research/clique_color_er/test_original10.py\`

\`\`\`sh
python3 research/clique_color_er/emit_veripb.py \
  --cnf ORIGINAL.cnf --pbp proof.pbp --meta evidence.json
veripb-tool/bin/veripb --cnf ORIGINAL.cnf proof.pbp
\`\`\`

Workflow:
\`.github/workflows/drnas-clique-color-er-veripb-original10.yml\`

It restores **the same exact frozen 10 originals and VeriPB binary**
from completed run 43891106380 and runs fresh proof production and
external acceptance for each CNF twice, with an inclusive 8s wall
cap and 16s PAR2 penalties. An unsupported or timed-out proof receives
UNKNOWN; an externally REJECTED proof fails the audit. Input hashes
and original verifier binary SHA256 are checked before any trial.

**GitHub CI results are pending unless and until that new workflow
finishes.** Do not replace previous blind 0/20 benchmark results
with local post-discovery development numbers.

## Next scientific check

To establish unseen generalization rather than retrospective
specialization, choose a new metadata-only family/source-disjoint
test set; SHA-freeze exact source bytes before executing this code;
compare against current Kissat, CaDiCaL and CryptoMiniSat binaries,
serial one logical CPU per solver, same full E2E proof verification
and bootstrap by genuinely independent families. Promote nothing
automatically to main.

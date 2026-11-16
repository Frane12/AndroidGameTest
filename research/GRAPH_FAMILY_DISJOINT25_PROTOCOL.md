# DRNAS — new SAT2025 graph-family-disjoint holdout, frozen 2026-11-16

Research branch: \`experiment/drnas-graph-family-disjoint25-20261116\`.
Strictly experimental: **do not edit main, frozen references or APK**.

## The scientific question

The previous 10 exact original SAT Competition 2025 Main
\`clique-coloring\`, \`coloring\` and \`coloring-clique\` instances
were each given a new source-grounded VeriPB RED+RUP-hints+CP
UNSAT proof after diagnosis. That is a strong retrospective
within-family demonstration, but NOT evidence of generalization
to different combinatorial graph problems.

We therefore prespecified **10 exact ORIGINAL 2025 Main CNFs**
from seven **different** graph/graph-adjacent families before any
candidate or reference solver run in this experiment.

All 10 original GBD normalized hashes and GBD isomorphism
hashes were committed in
\`research/graph_family_disjoint25/prespec.json\`
(commit \`34a3199\`) prior to source download or evaluation.
All eight family names are distinct from both:
- the old frozen 67 SAT2026 source families
  (original archive run \`43853390060\`), and
- the old ten SAT2025 family-problem originals
  (original archive run \`43891106380\`).

Selected source families: hamiltonian (1),
independent-set-reconfiguration (3), independent-set (2),
rooks (1), tseitin-formulas (1), ramsey-numbers (1),
and random-graph-xorsat (1).

Source catalog:
https://benchmark-database.de/?context=cnf&track=main_2025

## Selection and source proof

1. PREPARE restores the frozen previous 67+10 original manifests.
2. Before any solver is run on a new source, compare all 10 GBD
   IDs, isohashes and family names against both old manifests.
   If any one overlaps, FAIL; never substitute sources based on result.
3. Download EXACT original source from each prespecified GBD URL.
   Safely decompress XZ if required, check DIMACS header, exact
   clause counts, variable range and resource limits.
4. SHA-256 freeze all ten raw original CNFs, source archive hashes,
   both old manifests, and the entire 7-arm protocol.
5. Freeze untouched native solver and independent verifier executable
   SHA-256 (Kissat/CaDiCaL/CryptoMiniSat, native X59+MATH5 and
   external VeriPB/FRAT/DRAT checkers).
6. Only then begin solver execution. Failure to fetch even one
   prespecified source aborts all trials, with no replacements.

Not all of the user's earlier experimental branches can be
exhaustively excluded. The scientifically defensible claim is
GBD source-identity/isohash/family disjointness from these two
explicit frozen development manifests (77 original CNFs), NOT
that no one has ever encountered these public problems.

## Serial 7-arm strict 8s E2E benchmark

Originals: 10; repeats: 2; solver modes: 7; trials: **168**.
Six independent GitHub shard jobs with exactly two sources/shard.
One logical CPU is assigned to one trial. All 7 arms run serially
within each source/repetition pair; no competing solver portfolio.

Arms:
1. CLIQUE_EXT_ONLY: RED extension + RUP hints + cutting-planes
   proof, strict VERIFIED only if VeriPB independently accepts
   the exact original CNF. Otherwise UNKNOWN.
2. CLIQUE_EXT_GRAPH_MATH5: same bounded source-only extension
   scout, then sequential source-based GRAPH + native X59+MATH5
   fallback sharing the same full 8s budget.
3. GRAPH_MATH5: previously successful fixed-source graph
   K_{k+1} proof scout plus native X59+MATH5 fallback.
4. X59_MATH5_VERIPB: the previously successful source-checked
   MATH5 standard exporter with unmodified frozen X59 binary.
5. Kissat (unchanged frozen binary), independently checked DRAT.
6. CaDiCaL (unchanged frozen binary), independently checked DRAT.
7. CryptoMiniSat (unchanged frozen binary), independently checked FRAT.

Every attempted source is checked by the original SHA-256,
independently verified SAT model or external standard proof.
No custom structural JSON can count as a standard UNSAT
certificate. E2E includes source verification, proof production,
native subprocess startup, model/proof checking and all fallback
overhead. Timeout/unverified: 16s PAR2 penalty.

\`results/graph_family_disjoint25/final.json\` will be accepted
only if all exactly 140 records are present, no duplicates,
SHA/family matches, zero critical proof/model checking errors
and no contradictory independently verified SAT/UNSAT claims.
The report compares mean paired per-source differences with
family-cluster bootstrap across the 7 independent catalog families.
10 sources is a small pilot, not a general world ranking.

## Interpretation and guardrail

This is a stronger **out-of-distribution family challenge** than
the prior 10 clique-coloring problems. The CLIQUE-COLOR source
grammar might recognize none of the new unrelated CNF families;
that would not invalidate earlier proofs. We measure both
recognition and overhead from safe UNKNOWN/fallback cases,
as well as any newly standard-verifiable results.

If a solver fails or an original GBD source is missing, keep
that failed status; do not silently substitute another source,
extend caps, or selectively report only solved instances.
No automatic main promotion.

Workflow:
\`.github/workflows/drnas-graph-family-disjoint25.yml\`

Reproduction:
\`\`\`sh
python3 research/graph_family_disjoint25/freeze.py
python3 research/graph_family_disjoint25/benchmark.py prepare
for i in 0 1 2 3 4 5; do
    python3 research/graph_family_disjoint25/benchmark.py shard --index "$i"
done
python3 research/graph_family_disjoint25/benchmark.py report
\`\`\`

The GitHub workflow restores exact verified old SHA-frozen files
before running these commands; the shell reproduction assumes
those immutable original reference artifacts are already present.

## Pre-freeze resource-only amendment and complete transparency

An earlier, different **12-source** preregistration
(`experiment/drnas-graph-family-disjoint25-20261116`)
was **aborted before any solver trial**, run
[43912555637](https://github.com/Frane12/AndroidGameTest/actions/runs/43912555637),
because its first graph-isomorphism CNF compressed archive was
62,056,920 bytes, exceeding the fixed 50,000,000-byte source budget.
A metadata-only remote HEAD audit measured the other 11 file sizes and
identified one missing GBD URL. No solver status or formula structure
was observed and no score can be assigned to that failed experiment.

This new branch commits a separately fixed **10-source** resource-bounded
selection with seven independent catalog families, before downloading
or solving any of those new originals. This is an honest resource-eligible
re-prespecification, **not** an untouched continuation of the aborted
12-source experiment, nor outcome-directed instance substitution.

No candidate or baseline SAT/UNSAT outcome is permitted to guide source
replacement, resource caps or proof acceptance on the new 10-source set.

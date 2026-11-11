# DRNAS ATLAS-X — compressed Boolean relations, lazy extended join

Experimental branch only: \`experiment/drnas-atlasx-lazy-extended-20261111\`.
No edits to \`main\`, frozen benchmark sources, ARL or ATLAS1 references.

## Technical design

ATLAS-X wraps the same native DRNAS R3C CDCL solver in three arms:
\`A\` (no atlas), \`ATLAS1\` (prior eager precomputed NPN rewrite), and
\`ATLASX\` (the new lazy path). It is **not** integrated into the
inner CDCL loop and it is not a proof of improved solver performance.

- **L0 compact:** each original support of 1–4 variables is represented as
  one local truth bitmask (\`uint16_t\`; at most 16 assignments). The
  \`compressed_bytes\` metric counts *bitmask payload only* and does not
  count index/vector overhead or the input CNF.
- **L1 precomputed:** reuses ATLAS1's generated exact NPN/CNF recipes for
  2–4 variables; rewrite only when fewer literals and no additional clauses.
- **L2 compressed lazy join:** for two distinct overlapping supports with
  a 5–6-variable union, lift both masks by projection, intersect them, and
  test implication without creating extended CNF. If one support implies
  another, remove only the implied module. Formal equivalence is checked
  over all assignments of the joined support *including the retained module*.
- **L2 optional materialization:** if no direct implication is found,
  \`k==5\`, at least four original selected clauses, at least 14 old
  literals, available time, and fewer than six expansions so far, generate
  a greedy exact implicate cover for the joined relation. Apply only if
  it uses no more clauses and strictly fewer literals. The greedy cover is
  not guaranteed minimal.

Candidate transformations operate only on selected **original** clauses,
never on learned clauses. The replacement is verified by exhaustive
truth-table comparison (maximum 64 assignments) before commit; other
original clauses are untouched. Original variables and satisfying
assignments are preserved exactly; no model reconstruction is required.

The bounded source scan inspects at most 900 clauses, 160 groups, 400 joined
pairs, and 6 extended CNF materializations, with a maximum preprocessing
budget of min(5 ms, 0.05% of the solver's time cap). If no proven profitable
candidate is found, the system sleeps and calls the baseline CDCL.

SAT results are independently checked against original CNF within the
executable and benchmark harness. UNSAT has **no independent LRAT proof**
and must not be described as certified. All times are end-to-end, including
atlas setup and CDCL, with one logical CPU per arm.

## Local reproduction

\`\`\`sh
python3 research/drnas_atlas1_generate.py --out mre_atlasx/atlas1_table.hpp
mkdir -p mre_atlasx/bin
g++ -std=c++17 -O2 -I mre_atlasx research/drnas_atlasx.cpp -o mre_atlasx/bin/drnas_atlasx
mre_atlasx/bin/drnas_atlasx --atlasx-selftest
python3 research/drnas_atlasx_smoke.py
mre_atlasx/bin/drnas_atlasx example.cnf --mode ATLASX --time 30
\`\`\`

The experimental workflow performs a source-only SATLIB rank-24 holdout
from each of four families: uf100-430, uf150-645, uf200-860, uf250-1065.
It measures \`A\`, \`ATLAS1\`, \`ATLASX\`, Kissat (pinned commit), and
CaDiCaL, three reps each, 30s cap, source SHA, one CPU.
PAR2 uses 60s for timeout/UNKNOWN; compare solved counts and paired E2E.
These random SATLIB formulas are mainly negative controls for structural
detection. A positive targeted synthetic control is included in the smoke
test. Further blind structured CNF tests are needed before efficacy claims.

## Known limits

- An indexed support group is not proof that a semantic graph gate exists.
  The proof rests on exhaustive local truth evaluation, not pattern names.
- Extending small truth masks does not make arbitrary SAT instances
  compressible or alter NP-completeness. Bitmask payload is not total memory.
- Local lemma reuse is not yet active across CDCL restarts; this phase
  tests sound and cheap **preprocessing** only.
- Source selection remains frozen by family and content SHA; no adaptive
  selection by reference solver outcome.

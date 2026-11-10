# DRNAS GF-CDCL — 63 original-CNF crossover scan (2026-11-10)

## Source-only screening completed
GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/42826195310
- 63/63 distinct frozen original SHA matched their source files; 0 extractor errors, 0 timing-dependent selections.
- XORABC3 previously tested 40: 7 with strictly *shorter* pairwise source-certified XOR rows.
- MIXAB3 prospective 12: **2** with strictly shorter XOR rows.
- MIXAB4 reference-easy 6: **0** such instances.
- EQUIV10M5 reference-easy/medium 5: **0** such instances.
- Total positive cross-row structure: **9/63** (7 historic hard + 2 MIXAB3). All inferred rows are exact GF(2) sums of independently original-CNF-certified source XOR blocks.
- All observed certified one-variable pair sums: 0. This is distinct from unsupported wider Gaussian elimination chains.

The earlier scan with 46 inputs had completed computations but failed GitHub Actions due to a missing output directory for `tee`; the corrected 63-input run and archived `screen.json` succeeded. Do not confuse CI status with mathematical output.

## Prespecified validation candidates
Two source-only selected MIXAB3 originals:
- `daa0360a834f...`: 20 shorter binary GF2 pair rows on the capped source exporter. Earlier CMS reference solved raw UNSAT in ~0.70 s, Kissat timed out at 12 s; no independently checked LRAT is shown.
- `e3e6b2c71ca0...`: 16 shorter binary GF2 pair rows. Earlier CMS reference solved raw UNSAT in ~6.2 s, Kissat timed out at 12 s; no independently checked LRAT shown.

**Do not** claim these are blind; they are historical original-CNF cases and prior reference outcomes are visible. Selection was based only on source mathematical geometry.

## NOVEL2D controlled benchmark
- Experimental branch `experiment/drnas-gf-cdcl-novel2d-cross-medium-20261110`, main untouched.
- 2 original SHA x 5 arms (clean CaDiCaL 2.1, direct GF2, strict cross-row NOVEL2B, cost shadow, reference CMS) x 2 repetitions = 20 matched measurements.
- One logical CPU, independently verified SAT model on the same immutable original CNF, 15s full E2E cap, strict PAR2 with *unproved* UNSAT excluded (2x cap).
- Native reasons are inherited from the proof-checked original source XOR rows and are only active on real CDCL trail.
- Competing arms use one source-pinned native CaDiCaL build, not independent differently compiled solvers.
- A reduction in decisions at timeout is a search-diagnostic, not an E2E speedup.
- Retain solver progress only if total matched PAR2 and original proof checks support it. Otherwise, investigate accepted-reason to new-assignment transition and event-indexed cost.

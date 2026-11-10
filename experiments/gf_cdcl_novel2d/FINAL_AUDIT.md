# DRNAS GF-CDCL — NOVEL2D final source-frozen crossover audit (2026-11-10)

## Evidence
- Structural 63-source SHA screen: https://github.com/Frane12/AndroidGameTest/actions/runs/42826195310
- Completed 20 original-CNF benchmark attempts, two parallel source-paired shards: https://github.com/Frane12/AndroidGameTest/actions/runs/42827184856
- Successful audit-only recovery **without rerunning timed tests**: https://github.com/Frane12/AndroidGameTest/actions/runs/42828127706

The first benchmark workflow's top-level status is FAILURE solely because the initial audit job tried to restore artifacts to the wrong path (and a transient artifact download failure on its first attempt). Both original SHA benchmark shard jobs **succeeded** (10/10 each), and the separate recovery job restored existing immutable shard JSON, verified frozen signatures, and generated the final 20/20 audit successfully. Do not equate GitHub top-level workflow success with tested solver performance.

## Source-only screened cohorts
63 immutable original SHA, 0 unsupported:
- XORABC3 previous 40: 7 with strictly reductive pairwise XOR rows
- MIXAB3 12: 2 with strictly reductive pairwise XOR rows
- MIXAB4 reference-easy 6: 0
- EQUIV10M5 reference-easy/medium 5: 0

For NOVEL2D select exactly two MIXAB3 source-only structural SHA, no candidate outcome-time selection:
- `daa0360a834fbd9f49437d2b3fd6b372d331774100d913d55c57c0de547eb623`: 20 reductive binary XOR consequences
- `e3e6b2c71ca07f5f17491a38490b29fb63045be258ad6837bcc4530b31438162`: 16 reductive binary XOR consequences

These are *previously seen* original SAT2021-23 sources, not blind holdout.

## Protocol and final results
CaDiCaL 2.1.0 pinned source, identical native executable across native arms; CMS 5.17 reference. Two SHA x two repeats x five arms, 20 attempts, 15-second nominal full E2E cap, one logical CPU per attempt, original CNF SHA checked and SAT models independently verified. Backend UNSAT is not accepted as certified without independent original-CNF LRAT/DRAT; no LRAT supplied for these two source cases.

| Arm | attempts | native SAT verified | raw UNSAT without LRAT | timeouts | strict solved | strict PAR2 s | actual E2E wall s | derived proposals | completed GF2 reasons | native CDCL decisions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CaDiCaL clean | 4 | 0 | 0 | 4 | 0 | 120.000 | 58.042 | 0 | 0 | 2,620,307 |
| GF2 direct | 4 | 0 | 0 | 4 | 0 | 120.000 | 58.043 | 1,150 | 382 | 2,206,711 |
| GF2 NOVEL2B | 4 | 0 | 0 | 4 | 0 | 120.000 | 58.041 | 514 | 92 | 2,172,048 |
| NOVEL2B shadow | 4 | 0 | 0 | 4 | 0 | 120.000 | 58.046 | 0 | 0 | 2,219,772 |
| CMS plain | 4 | 0 | 4 | 0 | 0 | 120.000 | 13.820 | 0 | 0 | n/a |

CMS returned UNSAT twice per original:
- `daa0360...`: 0.690 s and 0.683 s full E2E
- `e3e6b2...`: 6.309 s and 6.139 s full E2E

These CMS times are *diagnostic* until standard original proof is independently checked. Under the current strict proof requirement, every arm has 0 verified solved and 120 s PAR2. No candidate speedup has been demonstrated. Lower CDCL decision count under an identical timeout is not proof of faster end-to-end solving.

## Decision
1. **Do not promote NOVEL2B**. Its 514 proposals led to 92 completed reasons but no additional solved original CNF. Previous direct delivered more total reasons, yet also no solving improvement.
2. Avoid repeating the same source-hardness-biased benchmark. Source-reductive GF2 rows are rare: 9/63, absent from all 11 reference-easy/medium source-frozen samples.
3. Invest in proof-checked integration *quality*: number of actual new CDCL assignments from externally completed reasons, per-row scheduling CPU budget, cross-row closure beyond only two rows, and—separately—source-derived unit consequences.
4. To claim an UNSAT win, independently verify a DRAT/LRAT (or equivalent accepted original-CNF proof). Cross-solver agreement alone is not independent proof.
5. Next only after showing new CDCL assignment impact or a genuinely different frozen cohort. Preserve original SHA, one logical CPU, and matched E2E strict PAR2. Do not touch main.

## Housekeeping
No large proof binaries were uploaded; all changes confined to experimental branches.

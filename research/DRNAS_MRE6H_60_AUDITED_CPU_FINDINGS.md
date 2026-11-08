# DRNAS MRE6h — 60/60 audited real SAT2026 35s fast GF2 CPU results

Date: 2026-11-08
Experimental branch: experiment/drnas-mre6h-fast-gf2-cpu-20261108
Complete successful workflow: https://github.com/Frane12/AndroidGameTest/actions/runs/42507215971
Audit: ALL 60 source-paired attempts present, 3/3 shards and audit green.

## Full end-to-end PAR2 (6 official SAT2026 original CNFs × 2 repetitions)

| Mode | SAT/UNSAT solved | Timeout | PAR2 seconds | Total preprocessing wall s |
|---|---:|---:|---:|---:|
| source_xor CMS | 9/12 | 3/12 | **287.428032** | 1.002317 |
| fast_gf2_no_xor MRE6h | 9/12 | 3/12 | **287.492381** | 1.298629 |
| fast_gf2_with_xor MRE6h | 9/12 | 3/12 | 288.429359 | 1.288254 |
| graph_scc_gf2 old MRE6g | 9/12 | 3/12 | 288.939923 | 1.859414 |
| native_no_xor CMS | 9/12 | 3/12 | 290.707048 | 0.580934 |

Same native CMS 5.11.15 pinned library, same source SHA and native seed
per four/five-way comparison, OTF Gaussian OFF, 35s COMPLETE wall cap,
PAR2=70s per timeout. All completed SAT model witnesses checked on
original source; independent UNSAT LRAT not available.

## Previously studied ACTIVE SAT2026 anchor (two repetitions)

official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf

| Mode | Two-run end-to-end total s |
|---|---:|
| MRE6h signed GF2 quotient WITHOUT imported XOR | **15.714006** |
| CMS + verified source XOR | 16.117105 |
| MRE6h signed GF2 quotient WITH imported XOR | 16.949202 |
| MRE6g original GF2 quotient | 17.290447 |
| CMS native, no optional XOR | 19.709316 |

MRE6h finds the exact same **four independently certified** signed
equivalence eliminations as MRE6g, each repetition: four source XOR
equations produce 8 binary lemmas, 4 certified signed SCC substitutions.
Full SAT witness restored and verified against the SHA-pinned source.
Proof generation and source CNF transformation included in total time.

Relative improvements ON THIS SINGLE REUSED SOURCE ONLY:
- MRE6h no-XOR is 9.12% faster than legacy MRE6g;
- MRE6h no-XOR is 2.50% faster than original CMS+XOR in sum
  but this does NOT repeat consistently across native seeds:
  seed0 CMS+XOR 8.026196s vs MRE6h no-XOR 8.208766s (MRE6h slower);
  seed1 CMS+XOR 8.090909s vs MRE6h no-XOR 7.505240s (MRE6h faster);
- MRE6h fast in-process proof/rewriting prep ~0.192s vs legacy
  MRE6g ~0.340s per attempt, 43–45% less total prep time;
- GF2 short-row proof generator's own time ~0.075s each; whole
  fast equivalence finding with proof and SCC ~0.119s.

Native CPU solve time active source:
- MRE6h no-XOR: 7.985104341+7.287692124=15.272796465 s
- MRE6h with-XOR: 8.447938165+8.063648541=16.511586706 s
- MRE6g legacy: 8.475024122+8.081952809=16.556976931 s
- CMS+XOR: 7.951670700+8.018969699=15.970640399 s

Native propagation changes with alternative signed mapping:
MRE6h no-XOR: 2,386,721 / 2,001,177;
MRE6h with-XOR: 2,177,158 / 1,924,242.
Conflict counts remain ~56k per repetition. A different propagation
topology does not alone justify predicting speedup.

## New official reference-selected source cohort (4 CNFs, 8 paired attempts)

| Mode | Solved | PAR2 seconds |
|---|---:|---:|
| original native CMS | 5/8 | **263.392365** |
| source XOR CMS | 5/8 | 263.661980 |
| MRE6h fast WITH XOR | 5/8 | 263.826768 |
| MRE6g old | 5/8 | 263.947457 |
| MRE6h fast NO XOR | 5/8 | 264.166398 |

ZERO certified equivalence substitutions on any of the 4 newer
originals. No real acceleration established on new sources. In
particular, on a fast SAT source, total prep overhead from failed
GF2/SCC searches remains visible.

## Scientific decision

Maintain MRE6h as exploratory CPU-aware mathematical principle.
Do not promote to production or claim general speed superiority.
Best next experiments:
1. Precommitted SHA-locked, *never-used original* source cohort with
   certified GF2 equations and nontrivial equality, plus equal source
   controls without equality. Selection must not inspect DRNAS speed.
2. Compress preparation further, especially slow original-CNF source
   XOR scanning, by a cheap structural gate BEFORE extraction.
3. Compare group effects: certified implied CNF clauses vs quotient
   without imported XOR vs transformed XOR on same native seeds,
   then promote only if source-disjoint end-to-end CPU/PAR2 wins.

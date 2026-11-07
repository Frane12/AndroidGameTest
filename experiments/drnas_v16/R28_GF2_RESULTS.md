# DRNAS SAT R28: exact parity-CNF recognition and GF(2) elimination

Date: 2026-11-03
Workflow: https://github.com/Frane12/AndroidGameTest/actions/runs/41613064879
Final artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41613064879/artifacts/13219843060
Known R27 regression replay: artifact \`r28-known-case-proof\` on the same run.

**Scientific status: a successful engineering prototype on exact recognizable XOR formulas, NOT a new method for solving general NP problems or P = NP. Gaussian elimination for XOR is established prior art (e.g., CryptoMiniSat).**

## Algorithm and soundness

1. Parse the *entire* DIMACS CNF (bounded size; larger/unparseable files fall back).
2. Group width-2..6 clauses by identical sorted variable supports. Detect a verified XOR equation only if **all** 2^(k-1) forbidden-sign patterns of one parity are present, not merely repeated supports or a partial prefix.
3. For each independently certified complete block, form its GF(2) equation. An inconsistent subsystem yields an UNSAT row combination (0=1), including when arbitrary other CNF clauses exist. Print the source equation list and IDs of the contradictory combination. A **separate Python verifier** checks every required clause against the original CNF, then checks that the selected rows XOR to 0=1.
4. If **every** original clause is covered by complete parity blocks and the system is consistent, use GF(2) elimination to construct a SAT model, and verify the original clauses before output.
5. Otherwise, **exec** the unmodified SHA-pinned Kissat binary. Never infer SAT from a consistent XOR subsystem of a mixed formula.
6. Native code: \`experiments/drnas_v16/r28_exact_gf2.cpp\`. SHA-frozen benchmark and separate verifier: \`experiments/drnas_v16/r28_exact_gf2_benchmark.py\`. Stable V15.3.1 untouched.

## Previously known diagnostic, not blind

Problem \`tseitin_xor_64_10.cnf\` (original R27 salt):
- Clean pinned Kissat median 1.405352 s, 3 paired runs, UNSAT.
- R28 native GF2 median 0.002740 s, 3 runs, independently verified UNSAT parity certificate.
- Approx. 513x faster on this specifically constructed, already analyzed XOR formula.

## Frozen fresh multi-family benchmark

240 SHA-distinct synthetic CNFs, six families of 40, each run twice on original pinned Kissat and R28. 960 completed native attempts; 2 s cap, PAR-2 timeout=4 s. Four shards, same binary hashes, same input hashes, native CPU affinity. Separate source-reconstructed known regression excluded from the 240. All final GitHub jobs and the aggregator succeeded.

| Family | Kissat sum PAR-2 (s) | R28 sum PAR-2 (s) | R28 gain | Kissat solved | R28 solved | Independently verified GF2 UNSAT trials |
|---|---:|---:|---:|---:|---:|---:|
| **ALL** | **445.769359** | **166.253314** | **+62.704%** | **197/240** | **228/240** | **120** |
| Pure XOR3 | 50.732493 | 0.231011 | +99.545% | 36/40 | 40/40 | 40 |
| Pure XOR6 | 160.125353 | 0.281934 | +99.824% | 20/40 | 40/40 | 40 |
| Mixed XOR3 + extra clauses | 69.916641 | 0.295156 | +99.578% | 33/40 | 40/40 | 40 |
| Near-XOR decoy CNFs | 43.804857 | 43.963792 | **-0.363%** | 40/40 | 40/40 | 0 |
| Random 3-SAT at critical density | 118.530165 | 118.655062 | **-0.105%** | 28/40 | 28/40 | 0 |
| Community-structured random 3-SAT | 2.659850 | 2.826359 | **-6.260%** | 40/40 | 40/40 | 0 |

- Overall 86 timeout trials for Kissat, 24 for R28 (these are attempts, not distinct formulas).
- R28 produced 120 independent GF2 UNSAT certificates and 80 pure-XOR SAT witness cases (each count is trial-level across two repeats).
- Mixed-XOR SAT cases fall back to Kissat; mixed-XOR UNSAT cases can terminate early if the proven XOR subsystem already contradicts itself.
- R28 does NOT automatically speed up arbitrary or non-XOR CNFs, and front-end overhead causes a small negative impact on many very fast general SAT cases.

## Limitations and rigorous next test

- Both solver arms use the same original Kissat pin \`8af8e56f174b778aef3aa45af9f739b2a5f492c2\`, not current official world championship winners.
- These six generators emphasize explicit parity block structures; the 62.7% figure reflects this **chosen distribution**, not universally representative SAT.
- The 240-case suite contains no genuine industrial or SAT Competition instances. Those must be added as separately labeled out-of-distribution tests.
- UNSAT results produced by fallback CDCL were not independently proof-checked. R28 GF2 certificates were independently checked on original CNFs.
- Compare against an established parity-aware solver **CryptoMiniSat with native XOR/Gauss support** before any scientific novelty claim; verify options/version and include preprocessing and wall-clock overhead.
- Test *partial, overlapping, noisy, obfuscated and higher-width XOR* structures where exact full-block recognition may abstain, along with proof-generating mixed CNFs.
- Report paired PAR-2 and distribution-specific speedups, solved count, and worst per-formula regressions. Do not update the selection rule on the same evaluated test set.

## Engineering incidents

Initial workflow failure: native output mistakenly prefixed every SAT literal with \`v\`, breaking independent DIMACS witness parsing. Fixed without modifying algebra/proof logic. Validated rerun: \`41613064879\`. Earlier exploratory invalid runs are not counted.

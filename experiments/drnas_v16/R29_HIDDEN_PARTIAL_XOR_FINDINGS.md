# DRNAS SAT R29 — certified hidden and partial XOR relations and admission policy

Date: 2026-11-03
**Main completed frozen benchmark:** https://github.com/Frane12/AndroidGameTest/actions/runs/41617986064
**Final full results:** https://github.com/Frane12/AndroidGameTest/actions/runs/41617986064/artifacts/13222068159
Preflight proofs: https://github.com/Frane12/AndroidGameTest/actions/runs/41617986064/artifacts/13222725187

**Status:** Real, independently audited, distribution-dependent engineering improvement on deliberately generated XOR-centric SAT. Not a general SAT solution, world record, or P = NP finding. The XOR reasoning, Gaussian elimination and bounded variable elimination are established concepts.

## R29 implementation

- Sources:
  - \`experiments/drnas_v16/r29_hidden_partial.cpp\` (native)
  - \`experiments/drnas_v16/r29_hidden_partial_benchmark.py\` (SHA-frozen experiments and independent certificate verification)
  - \`.github/workflows/drnas-r29-hidden-partial-xor.yml\`
- Includes the existing R28 native GF(2) primitives.
- Reconstructs a hidden width-2..6 parity clause by sound bounded resolution of a variable occurring in exactly one positive and one negative clause. Parents must have small widths (one binary), resolvents must be nontautological, and no original parent is consumed twice. For full SAT, model assignments of eliminated auxiliary variables are reconstructed and the **entire original CNF** is checked.
- A mathematical XOR equation may be used only if **every** parity-forbidden assignment is excluded by a clause of the exact variable support (original or independently verified resolvent).
- Gaussian elimination:
  - **UNSAT** allowed when a complete-equation subsystem yields 0 = 1, even with additional arbitrary clauses. The native program emits original-parent resolution steps, the source XOR equations, and the XOR combination; an independent Python checker verifies all of these on original clauses.
  - **SAT** directly allowed only when every transformed original clause is equivalent to a verified parity or unit equation, and reconstructed assignments satisfy every original clause.
  - **Mixed, consistent** cases otherwise execute the clean, original pinned Kissat. If RREF implies new units, their proofs are independently verified; a 4-unit / 32-covered-clause / 200-clause gate *experimentally* admits injection. This admission did **not** show general time benefit, so **injection is not the default**. \`R29_MODE=active\` is required for research comparison; unset/shadow uses the safe path.
  - **Incomplete** 3-of-4 XOR block patterns never become an asserted parity equation.
- Uses the exact frozen Kissat upstream commit \`8af8e56f174b778aef3aa45af9f739b2a5f492c2\` as fallback, also benchmarked separately.

## Preregistered six-family benchmark

72 new deterministic SHA-locked synthetic CNFs (12/family) × 2 repetitions × 4 modes = 576 full attempts, all jobs passed; 3 s cap, timeout PAR-2 penalty = 6 s. These families were specifically designed to probe XOR recovery/abstention, not to represent real-world SAT distributions. Both R29 shadow and active were explicitly selected through environment flags.

| Family | Clean Kissat PAR2 sum (s) | R28 (s) | R29 shadow (s) | R29 active (s) | Active gain vs Kissat |
|---|---:|---:|---:|---:|---:|
| **ALL** | **107.021376** | **91.506993** | **0.617453** | **0.614259** | **+99.426%** |
| Hidden XOR3 | 1.748380 | 1.751480 | 0.073659 | 0.074419 | +95.744% |
| Hidden XOR6 | 72.048860 | 72.094958 | 0.110249 | 0.109284 | +99.848% |
| Hidden XOR3 plus unrelated clauses | 17.237397 | 17.332888 | 0.104075 | 0.102180 | +99.407% |
| Visible partial XOR + unrelated clauses | 15.823161 | 0.089423 | 0.091576 | 0.091899 | +99.419% |
| Incomplete split-XOR decoys | 0.076718 | 0.109744 | 0.109133 | 0.109930 | **-43.291%** |
| Consistent mixed XOR with derived backbone units | 0.086860 | 0.128500 | 0.128761 | 0.126547 | **-45.691%** |

Solved cases in both repeats: Clean Kissat 64/72, R28 65/72, R29 shadow 72/72, R29 active 72/72. Clean Kissat had 16 timeout attempts, R28 had 14, R29 shadow and active 0.

R29 active emitted 48 independently checked GF(2) contradiction certs and 24 independently checked derived-unit proofs (attempt counts; 2 repeats). It also produced 24 correctly reconstructed pure-XOR SAT witnesses. The unchanged R28 solver gets the same benefits on *visible* exact XOR contradiction cases; R29's new advantage is recovery of hidden two-clause splits.

## Exact rule for when to use or abstain

**Use algebraic resolution when it is proven:**
1. Native extraction found complete XOR CNF blocks, possibly after **audited, bounded local resolution**.
2. The GF(2) system has a contradiction -> return UNSAT with independent original-clause certificate.
3. Or every clause is covered and elimination reconstructs an original-clause SAT witness -> return SAT.
4. Otherwise original Kissat remains the sound answer-producing engine.

**Do not use it as an optimization without performance evidence:**
1. An incomplete parity block, merely repeated supports, or a statistical "XOR-looking" fingerprint is not a logical certificate.
2. Mixed consistent GF(2) does not prove SAT. New forced units are **logically sound**, but their deployment was slower than running clean Kissat for the 12 tested SAT formulas: 0.126547 vs 0.086860 s total across 24 attempts. R29 also has substantial input preprocessing overhead on rapid decoy formulas (0.109930 vs 0.076718 s), even though it correctly falls back.
3. On speed-critical general CNFs, use an **additional cheap admission filter or direct Kissat**; such a filter is not yet empirically validated.
4. Unbounded auxiliary elimination, wide XORs >6 literals, or an XOR core with arbitrary nonlinear constraints are **not** solved by this prototype unless a certified contradiction is derived; fall back.
5. Holdout measures 72 constructed CNFs only. A success here is **not** evidence of general performance on unseen industrial/competition problems.

## Next methodologically correct benchmark

- Freeze a new unseen set containing true SAT Competition/GBD CNFs, additional split-gate obfuscations, mixed XOR with non-XOR AND/OR gates, random SAT controls and difficult GF(2)-backbone cases.
- Evaluate R29 shadow-safe default vs clean Kissat, R28, and a current properly configured parity-aware solver such as CryptoMiniSat.
- Explicitly measure time spent in the structural pre-scan, resolution, Gaussian elimination, and downstream CDCL separately.
- Predict *benefit* from structural and early search features on a development set, freeze that decision rule, validate with independent SHA-distinct test formulas. Never train a "universal" selector on the same R29 cohort.
- Keep V15.3.1 unchanged; do not promote R29 into the stable application until industrial controls and proofs pass.

The \`41617986064\` benchmark preceded the source-only safe-default adjustment. In that run, \`R29_active\` and \`R29_shadow\` were selected explicitly and remain behaviorally unchanged by the new default.

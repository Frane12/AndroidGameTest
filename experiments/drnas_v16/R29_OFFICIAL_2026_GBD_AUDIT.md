# DRNAS SAT R29 — SAT Competition 2026 original GBD check

Date: 2026-11-03
GitHub Actions completed and audited: https://github.com/Frane12/AndroidGameTest/actions/runs/41620579411
Final artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41620579411/artifacts/13222893290

**Conclusion: The spectacular synthetic XOR speedups do not generalize to these 14 original SAT Competition 2026 polynomial-family GBD CNFs under a short 6-second cap. No proof of an R29 improvement over pinned Kissat on this real subset.**

## Corpus and protocol

- 14 original SHA-256-verified GBD formulas from SAT Competition 2026, exactly the 10 previous development + 4 previously held-out but subsequently seen original R28 polynomial CNFs.
- Original source archive from successful R28 workflow 41614909924. Decompression (where needed) changes only file representation, not logical clauses; original source SHA and raw normalized SHA were checked.
- Four *synthetic* XOR control formulas in the R28 archive are excluded.
- Each official CNF tested on the same runner/CPU with two paired repeats, native pinned Kissat, native CaDiCaL 3.0.1, R29 safe default, and explicitly enabled R29 active unit injection: 14 × 2 × 4 = **112 trials**.
- Hard 6-second cutoff. PAR-2 timeout penalty 12 seconds. Sum over the per-CNF medians, rather than raw wall times of all attempts.
- Retrospective experiment on real published original CNFs, **NOT a fresh blind holdout or official competition ranking**.
- Original expected SAT/UNSAT labels were checked when solvers returned answers. Independent UNSAT proof checking and external SAT model checking were not performed in this run.

## Verified 112-trial final summary

| Solver | Solved both repeats | Sum per-case median PAR-2 (s) | Timeout attempts (of 28) | Relative to Kissat |
|---|---:|---:|---:|---:|
| Pinned Kissat | 2/14 | 150.260289 | 24 | baseline |
| CaDiCaL 3.0.1 | 1/14 | 156.181246 | 26 | -3.940% |
| **R29 safe** | **2/14** | **150.163420** | **24** | **+0.064%** |
| R29 active | 2/14 | 150.206840 | 24 | +0.036% |

These differences vs Kissat are extremely small and do **not** establish an R29 speedup. Both successful R29 cases explicitly used \`fallback reason=input_guard\`, delegating the actual SAT solving to pinned Kissat. This is a guard, not a successful XOR-derived action. For 12 timed-out formulas the captured tool only reports timeout; it does not prove what structural routing occurred internally.

## Representative original formulas

| Official filename | Pinned Kissat (median s) | CaDiCaL 3.0.1 | R29 safe | R29 active | Note |
|---|---:|---:|---:|---:|---|
| mp1-Nb5T16.cnf.xz | 5.498820 | timeout | 5.476540 | 5.494412 | SAT; R29 input_guard/fallback |
| mp1-Nb7T43.cnf.xz | 0.761469 | timeout | 0.686880 | 0.712429 | SAT; R29 input_guard/fallback; tiny wall-clock changes not proof of algorithmic gain |
| mp1-Nb6T28.cnf.xz | timeout | **0.181246** | timeout | timeout | SAT; CaDiCaL strong single case |
| Other 11 original GBD inputs | timeout | timeout | timeout | timeout | All four methods exceed 6-second cap in both repeats |

All four extra R28 GBD cases were timeouts in every mode: 48 PAR-2 seconds per mode, no observed gain.

## Scientific interpretation and next hypothesis

- Strong R29 synthetic speedups (+99.4% selected distribution) came from deliberate *explicitly recoverable* XOR structures; not replicated on these polynomial-family official instances.
- \`input_guard\` means R29 refused structural parsing due to a size/format/resource guard and delegated to native Kissat. The guard's exact limiting field for each original instance was not instrumented in this test. **Do not remove safety guards blindly.**
- Before claiming anything on real official problems: add a bounded streaming/approximate XOR structural pre-scan that records exact skip causes, and a *proven complete* parity/reconstruction certificate path where feasible.
- Measure pre-processing and fallback overhead, avoid modifying solver for unverified XOR hints.
- Broaden to *different* official 2026 categories and genuine untouched hashes; increase cap beyond 6s so timeouts do not dominate, report hardware and proofs.
- Hold R29 proof-gated synthetic implementation as an experimental branch only; stable V15.3.1 unchanged.

No claim here that P = NP or a world record has been reached.

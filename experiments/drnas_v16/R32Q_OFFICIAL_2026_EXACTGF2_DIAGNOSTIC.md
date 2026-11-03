# R32q real SAT Competition 2026: verified exact-XOR diagnostic

**Run (all green):** https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807  
**Complete output and SHA records:** https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807/artifacts/13239399691  
**R32p original independent source archive:** https://github.com/Frane12/AndroidGameTest/actions/runs/41656883104/artifacts/13240166954

**Date:** 2026-11-03. **This is an already examined formula,
not blind holdout**. Original official SAT Competition 2026 Main CNF
from https://benchmark-database.de/file/75429ff7acb5acb597abe01aa745c2a6

- Original SHA256 of decompressed source:
  `243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83`
- Exactly 250 variables, 1000 original clauses, all independently
  checked on R28 SAT witness.
- Same GitHub Actions runner with one solver per attempt.
- Original pinned upstream Kissat SHA:
  `8af8e56f174b778aef3aa45af9f739b2a5f492c2`.
- Historical existing R28 exact GF2 recognizer based on complete
  parity CNFs + sound Gaussian elimination, not newly invented.
- Source identity, solver binaries and outputs checked by workflow.
- 2 matched attempts per mode, 60-second timeout, PAR-2=120s
  for unsolved attempts.

| Attempt | Original clean Kissat | Certified exact GF2 R28 |
|---|---|---|
| Repeat 0 | TIMEOUT after 60.002056 s | SAT in **0.004179 s** |
| Repeat 1 | TIMEOUT after 60.002141 s | SAT in **0.004189 s** |
| Median | Exceeds 60 s (unknown completion) | **0.004184 s** |
| PAR2 sum | 240.000000 s | 0.008368 s |

R28 reports:
`c R28_ROUTE certified_pure_xor_sat rank=250 equations=250 clauses=1000 covered=1000`.

**The original 250-variable witness was independently validated against
all 1000 original DIMACS clauses**, no violations.

There is a large lower-bound runtime contrast on this **one particular
official problem**: since Kissat did not terminate within 60 seconds
but R28 returned after roughly 4.2ms, the observed time-limit ratio
is >14,000x. It is a *lower bound* because Kissat's true finishing
time is unknown; it is NOT a precisely measured equal-completion
speedup. PAR2 scores should be reported separately (120-second penalty).

### Scientific and engineering caveats

1. This is prior-art Gaussian elimination on an exact CNF parity
   structure, **not** a new general SAT, P=NP or complexity-theoretic
   breakthrough. Other parity-aware solvers (e.g. CryptoMiniSat)
   exploit similar mathematics.
2. The target is the **previously observed** R32p official CNF, so the
   result is diagnostic, not a blind holdout.
3. R32p's R32n native unit-gated Kissat was a separate implementation:
   it detected 250 implied units but `gap.extra<=12` guard abstained,
   so its 60-second timeouts do not contradict R28's exact-XOR gain.
4. The general R32p eight-real-source official cohort solved only
   2/8, with **zero injected GF2 root units**; that result remains
   the correct unbiased description of the current R32n native method.
5. This one-source targeted diagnostic is not on the competition's
   official hardware/time cap and cannot be compared with world
   leaderboard standings.
6. Next: integrate a bounded proof-checked **complete-source XOR solve
   or safe high-rank unit handling** *within one native Kissat* and
   validate prospectively on **new unexamined real external CNFs**.
   Compare to strong existing XOR-enabled state of the art.

No watchdog or parallel process portfolio was used.

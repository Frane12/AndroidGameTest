# DRNAS R32u: first real 2026 active XOR/CDCL benchmark

**Date:** 2026-11-03  
**Source, 60-source audit, identical binary:** https://github.com/Frane12/AndroidGameTest/actions/runs/41683024261  
**Method and 31/31 direct XOR source-proof preflight:** https://github.com/Frane12/AndroidGameTest/actions/runs/41681988821  
**Branch:** `experiment/drnas-r32u-active-xor-cdcl-20261103`

## Exact original CNFs and protected protocol

Five **previously seen**, source-SHA-verified SAT Competition 2026
original CNFs. Chosen by pre-observed algebraic coverage, *not* as a
blind competition sample. Each case was run on a single GitHub Actions
runner in three serial modes:

- `clean`: pinned unmodified Kissat 8af8e56f
- `passive`: same pinned native build, source GF2 RREF + read-only
  CDCL trace; **no** native XOR reason assignments
- `active`: exactly the same native binary, but source-entailed
  short GF2 rows may assign one missing variable **with an attached
  native CNF reason during CDCL**

One trial per mode and original; 75-second right-censored cap;
PAR2=150 seconds for timeouts. No portfolio or watchdog.

## Real times and native XOR interventions

| Original 2026 GBD ID | Clean | Passive | **Active R32u** | Proven short rows | Active CNF-reason log events |
|---|---:|---:|---:|---:|---:|
| `12535b3264a9c88bac14522171b497ef` | Timeout 75s | Timeout 75s | Timeout 75s | 64 | 0 |
| `7db30d12cb06f0dc2f30abff80d96d6a` | Timeout 75s | Timeout 75s | Timeout 75s | 31 | **≥16** |
| `b76b9699c2deb74dd9b4a99a05179acd` | Timeout 75s | Timeout 75s | Timeout 75s | 8 | **≥1** |
| `e305def35c314eec8266087e89a9ab46` | SAT **45.755s** | SAT **46.075s** | SAT **46.500s** | 0 | 0 |
| `fca71c20202ef404349136c3a00465eb` | Timeout 75s | Timeout 75s | Timeout 75s | 0 | 0 |

All five source/candidate SHAs and all five 3-mode trial artifacts
were independently re-audited after the GitHub audit job's
**Markdown variable-shadowing exception**. The five benchmark job
shards are all green, with valid recorded outputs; the original
workflow reports red only because its last report-render step failed.
No solver job needs rerunning.

| Mode | Sources solved | PAR2 sum seconds |
|---|---:|---:|
| Clean | 1/5 | 645.755164 |
| Passive | 1/5 | 646.074791 |
| Active | 1/5 | 646.499631 |

The source-structure audit confirmed exactly **64, 31 and 8**
independently verifiable derived short parity rows for the three
XOR-active candidate formulas. All 103 selected rows were also
independently reconstructed from complete original parity CNF
encodings. The active solver emitted **17 or more actual native
conditional assignments**, each supplied with a sound clause reason.
The event count is a *lower bound* because timeout runs log only
early and sampled attachments.

The 60-source deterministic soundness CI check independently
confirmed **45 SAT, 15 UNSAT, zero contradictory outcomes**, and
every returned SAT model satisfied the original CNF.

## Scientific conclusion

- **Native active XOR reasoning implemented and observed**: YES.
  It changes the native CDCL trail and supplies CNF reason clauses
  rather than unexplained assignments.
- **Mathematical original-CNF source entailment verified**: YES,
  for every selected short GF2 row in the three candidate formulas.
- **Measured real-world solver win**: NO. All three originally hard
  XOR-structured official instances timed out for all methods at 75s.
- **Independently verified UNSAT proof in DRAT/LRAT**: NOT YET.
  Do not use these runs to claim officially certified UNSAT results.
- **General SAT Competition/world ranking or P=NP progress**: NO.

Next evidence needed: retain *full native progress counters upon timeout*
(not only the last sparse milestone), test wider source suites including
solvable XOR-containing cases, measure changes in conflict quality and
CPU overhead, and compare stronger dedicated parity-aware SAT baselines.

A new trial must freeze the rule without picking source instances
post-hoc by winning times.

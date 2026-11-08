# DRNAS MRE8 ABCX — final verified experimental findings (2026-11-08)

**Experiment**: https://github.com/Frane12/AndroidGameTest/actions/runs/42506577511  
**Branch**: `experiment/drnas-mre8-abcx-ablation-20261108`  
**CI conclusion**: all 8/8 paired shards PASS; final 512-trial audit PASS; eight modes × sixteen original CNFs × four deterministic paired seeds, 8 s total wall cap including preprocessing.

16 original SAT2021–SAT2025 formulas are from MRE7e-PILOT16. This is a **post-hoc development cohort**, not a fresh blind holdout. Reference selection was conditioned on original CMS 0.08–5s solveability. The frozen original file SHA, paired CMS seed, SAT witness verification on original CNF and byte-identical A/Xs and C/Xc transformation checks all passed. Original UNSAT had baseline CryptoMiniSat/CaDiCaL agreement, **not independently checked LRAT**.

## Full eight-arm actual SAT-to-verdict PAR-2

| Method | Solved (64 trials) | SAT | UNSAT cross-check (no LRAT) | PAR-2 seconds | Speedup vs native |
|---|---:|---:|---:|---:|---:|
| N native CMS | 57 | 41 | 16 | 203.552960 | 1.000× |
| A positive-equality rename without cleanup | 57 | 41 | 16 | 198.421625 | 1.025861× |
| B original-CNF tautology/duplicate cleanup without equality substitution | 58 | 42 | 16 | 180.015277 | 1.130754× |
| C positive equality + full cleanup | 58 | 42 | 16 | **175.707276** | **1.158478×** |
| D ascending clause length order, no rename/cleanup | 55 | 39 | 16 | 218.248782 | 0.932665× |
| Xs streaming rename | 57 | 41 | 16 | 197.997608 | 1.028058× |
| Xc streaming combined | 58 | 42 | 16 | 177.287999 | 1.148149× |
| Xr precommitted structural router (large equivalence→dense) | 57 | 41 | 16 | 202.054193 | 1.007418× |

**Critical caveat**: on 15 formulas *excluding one 2025 formula*, C is **slower** than native: aggregate C 169.045 s vs native 167.980 s (0.9937×). Twelve of the sixteen formula-level C totals were worse (one equal on permanent 4/4 timeout, three improved). Therefore 1.158× overall is **not** a robust generalization.

## Mechanism 1 — positive equality substitution without cleanup, fdfcd52a… SAT2023

Four paired seeds, all SAT verified on original source:

- Native CMS: **9.8666 s** PAR-2, 149,092 summed conflicts and 79,955,205 propagations.
- A-only equality variable substitution: **3.2231 s** PAR-2, 60,143 conflicts and 24,751,106 propagations.
- **3.061× faster** A-only, ≈59.7% fewer conflicts and ≈69.0% fewer propagations.
- C combined substitution/cleanup: **7.0974 s**; removing redundant clauses after substitution **reversed much of the benefit**, despite mathematical equivalence.
- Xr structural router incorrectly chose dense for this source: 7.1807 s. Xs-only 3.2548 s matched A's transformed CNF and was similarly effective.

Hypothesis: keeping certified-redundant source clauses *after direct positive-equality variable substitution* can preserve helpful CDCL heuristics / useful clause input distribution. A direct certificate is important; do not assume maximal CNF compression maximizes CDCL efficiency.

## Mechanism 2 — small equivalence, 037d21e0… SAT2023

Four paired seeds:

- Native CMS: 1.6897 s.
- A rename: 1.5420 s.
- Xs streaming rename: **1.5133 s (1.117× faster)**.
- C full clean: 2.2771 s.
- Xs source rewrite uses the same emitted CNF as A, but lower aggregate preprocessing. This is net full-time performance, not merely bounded-CDCL telemetry.

## Mechanism 3 — duplicate clause cleanup / clause ordering, 695d8f6a… SAT2025

Four seeds, with native solving 3/4 and selected variants solving all 4:

- Native CMS PAR-2: **35.5730 s** (one 8 s timeout penalized 16 s).
- B remove **560 exact duplicate clauses** (zero positive equivalent vars): **6.6721 s**, **5.33× PAR-2 speedup**; 4/4 SAT.
- C combined same as B on this formula: **6.6618 s**, **5.34×**; 4/4 SAT.
- D *only* stable ascending length clause order: **1.3733 s**, **25.90×**; 4/4 SAT, exactly 11,328 conflicts per rep.
- BUT D across all 16 formulas regressed to 218.249 s vs native 203.553 s, with 55 solved vs native 57; **unsafe globally**.
- The large gain is unrelated to parity/XOR or positive variable equivalence: apparently clause loading order and duplicate counts can drastically influence native CDCL behavior. It requires deeper causal controls and unseen source validation.

## Important audit and interpretation

- Original CNF SAT models were replayed on every reported SAT, not inferred from conflict reductions.
- No model was promoted; user main branch unchanged.
- The unverified-LRAT UNSAT label must remain explicit, despite original CaDiCaL agreement.
- A/Xs and C/Xc produced identical transformed CNF source SHA in each matched pair; any differences in wall time are therefore frontend preprocessing overhead, not changed search semantics.
- Runtime can vary by seed, but paired arms have identical seed per source and rep. Avoid unpaired, post-hoc rankings.
- C lead is dominated by the 695d source; no claim of a general world-record improvement.

## Recommended next research: MRE8X2, not automatic deployment

Investigate cheap **three-way routing** among (1) native fallback, (2) *rename-only* for proven small or large positive equality sets and (3) *deduplicate-only* for highly duplicate small originals. This router reverses the MRE8 Xr choice of dense on high equivalence. Test frozen source-disjoint originals before interpreting a positive PAR-2 result because the rules were motivated by **observed** MRE8 development outcomes. Also test safe clause-order probes on independent formulas to understand D's one-source 25.90× yet global severe regressions.

Raw final report: workflow artifact `DRNAS-MRE8-ABCX-16SOURCE-512PAIRED-8ARM-PAR2-FINAL`.

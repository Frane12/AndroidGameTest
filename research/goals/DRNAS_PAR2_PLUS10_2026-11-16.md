# DRNAS SAT: verified PAR2 improvement target (2026-11-16)

Status: PREREGISTERED RESEARCH TARGET — NOT ACHIEVED.

## Primary objective
On a newly frozen, source-disjoint blind holdout of original mixed SAT and UNSAT CNFs, achieve >=10% lower strict verified end-to-end PAR2 than the best of Kissat, CaDiCaL, and CryptoMiniSat, evaluated under the same per-instance limits and hardware. Define gain = 1 - (DRNAS strict PAR2 / min(reference strict PAR2)). Threshold: gain >= 0.10.

## Protocol
- One logical CPU per solver; no parallel portfolio; identical hardware, wall/CPU limits and max RSS cap.
- Freeze code, versions, random seeds, dataset hashes and provenance before opening the blind holdout.
- Separate training, validation, and holdout by generator/source family; prohibit tuning on holdout.
- Count SAT only with independently checked satisfying assignments; UNSAT only with independently checked standard certificates (DRAT/LRAT/VeriPB as applicable). Missing or failed certificates count as unsuccessful, not wins.
- End-to-end timing includes preprocessing, solving, proof generation and independent proof checking. Publish both source-only and strict E2E PAR2, but strict E2E is the primary metric.
- Report per-family wins/losses, verified solve counts, checker failures, CPU seconds, max RSS, confidence intervals, and raw trial JSONL.
- Zero false SAT/UNSAT results and zero unverified claims; report crashes/timeouts as failures.
- Compare a frozen baseline and ablations of MATH5, PCMAX/IPG and structural gates; enable modules only when validated without regression.
- No changes to main, no automatic promotion, no unnecessary Actions runs.

## Evidence baseline
MATH5 REAL67 run 43874420143: 67 originals, 134 paired attempts per arm, strict PAR2 X59_MATH5_VERIPB 2050.497864 s vs Kissat 2083.597814 s (approx. 1.59% improvement). Family-cluster 95% interval includes zero. This is not proof of general superiority.

## Acceptance
Gain >=10% on the untouched holdout; independently verified results; no correctness errors; confidence interval and family-level breakdown published. If threshold is missed, retain negative results and do not promote.

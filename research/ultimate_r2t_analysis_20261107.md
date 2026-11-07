# DRNAS Ultimate R2T — Structural Portfolio

Experiment based on R2x commit 6de0c39. Source corpus: identical 20 original frozen SHA files, same R153, R1A and native R166x binaries; 5 modes × 2 repeats × 20 CNFs = 200 paired attempts. CPU pinned within each shard.

## Mechanism
R153 exact GF2 is unchanged. If it falls back, an at-most-120-ms syntactic scan of the original CNF selects clean R166x CDCL only for sparse, Horn-dominant instances with substantial binary implications. Otherwise the exact R1A reference fallback runs. No prior solved outcomes or hardcoded source identities are consulted. No change to CNF or inferred proofs. Both reference and clean are tested independently.

## Important epistemic limitation
The hypothesis was formed *after observing this source corpus*. Successful 200-trial paired result is regression evidence only, NOT blind validation nor a new mathematical complexity bound. A second disjoint source cohort and true external holdout are needed before promotion. CPU types differ between historical runs: use same-run paired comparisons. No independent LRAT native UNSAT proof.

## Safety
Abstain to R1A on malformed, large, unsupported or scan-time-exhausting inputs. Verify SHA, SAT witness on original, GF2 replay, and status agreement. Never claim live GF2 reasons where telemetry is missing. The main branch is not modified.

# DRNAS LEGO-3 — bounded UP learned relation grammar, short 5s

Experimental only; **main and all frozen X22/X24/LEGO-1/LEGO-2 branches remain untouched**.

## Hypothesis

LEGO-2's recursive GF(2) and signed binary-implication proof grammar worked on generated positives but showed no improvement on real SAT E2E. LEGO-3 learns which SOURCE-PROVEN relation procedures induce **new bounded unit propagations** rather than which yield more clauses.

A table entry is a structural signature (source relation kinds, widths, overlap, join depth and output width), with observed propagation gain and number of completed probes. **The table is never a proof oracle.** Every chosen consequence is checked against original CNF clause IDs and source-replayed parity/implication evidence before insertion.

This is classical constraint communication and not physical quantum entanglement. Conditional correlations between connected equation clusters are a possible future extension, tested by measuring changes under assumptions.

## Diverse pre-registered dataset

8 structurally distinct families of compositional parity/graph blocks: XOR2, XOR3, XOR4, overlapping parity cycles, two-hop signed graph bridges and mixed networks; permuted variable labels, signed polarities, and disconnected noise. Original SAT witnesses are planted and verified.

Training: 80 positive synthetic + 16 incomplete-XOR and incomplete-cycle negative synthetic + 8 recycled real SHA = **104 separate training CNFs**.

Evaluation: **32 positive synthetic + 8 negative synthetic + 8 previously used real X22 original CNFs** = 48 disjoint evaluation SHA (not a genuinely unseen real-world blind holdout).

Evaluation sources are SHA-disjoint from training; labels and solver outcomes are **not** part of the training score.

Five configurations: original Kissat+CaDiCaL parallel race; native X24 GF(2) proof-first; LEGO static grammar; LEGO local bounded-UP ranking; LEGO frozen learned-UP ranking.

48 evaluation CNFs × 2 repetitions × 5 arms = **480 paired 5-second E2E trials**, 8 parallel shards × 60 trials. Timeout PAR2 penalty = 10 seconds. Source-SHA and binary/source hashes frozen before timing.

## Cheap per-equation measurement

For each short derived relation, test up to 4 signed assignment assumptions with deterministic bounded BCP. A useful relation earns points only for additional propagated assignments or earlier conflict relative to original formula under the SAME assumptions. The diagnostic BCP is *not* a CDCL run and cannot be presented as time improvement. BCP calculations have a nominal 4 ms/candidate ceiling, 130 ms/training formula, 36 candidates/formula, bounded 1.15 s preprocessing for evaluation.

Only source-proof-replayed unit/binary clauses may be appended to original CNF; cap 20 clauses, 10 relation rows per evaluation. Fail closed on unsupported proofs or budget exhaustion. Test baseline and learned strategies on the **same original SHA** with pinned Kissat and CaDiCaL source SAT-witness replay; UNSAT accepted only if original-X22 dual-backend agrees, not independently LRAT-certified.

Report separate synthetic positive/negative, recycled original real CNF, and overall PAR2; time and CPU; number of solved; number of new verified clauses; propagation probe counts and gains; training signature diversity, fallback, and proof accuracy. Do not auto-promote any experimental build.

If bounded BCP shows no gain or learned ranking doesn't outperform static on real original CNF, record that as negative evidence and investigate cross-block conditional message passing next.

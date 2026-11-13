# FAMILY15: original-source diagnostic benchmark

75 unmodified original SAT2024 formulas: 15 each from five GBD families:
hamiltonian, minimum-disagreement-parity, miter, scheduling, argumentation.
The five smaller eligible families were chosen from the public 400-instance
SAT2024 metadata and archive sizes. Within each family, selection uses smallest
compressed source size then GBD hash, excluding duplicate isohash2 values.
Original decompressed SHA256 identity is checked before any solver is run.
Historical SAT/UNSAT labels are retained only as metadata, not used to select
instances or certify outputs. The naturally occurring SAT/UNSAT mix is not
balanced through outcome filtering. These sources may have appeared in prior
project experiments: this is retrospective diagnosis, not a globally blind test.

Five family shards, one logical CPU per solver, randomized serial arms, two
repetitions, 15 s E2E cap including model/proof verification. Six arms:
unchanged X5_NO_MIN, frozen CORE, Kissat, CaDiCaL, CryptoMiniSat, and X5_DIAG.
Total 900 trials. No global policy, cache, new training or model promotion.
All candidate/reference binaries retain their original source and checksums.

X5_DIAG is generated from the exact same X5 source with observational timers,
periodic flushed progress and parse/search phase labels. It separately measures
BCP, conflict analysis, variable selection and clause reduction wall time;
it retains conflicts, decisions, propagations, restarts, learned/deleted clause
counts, clause slots, heap entries, GC counts and observed process peak RSS.
Its overhead is explicitly measured against uninstrumented X5_NO_MIN.
It must not be called a faster build or used to substitute performance timings.
Timers and stderr I/O can affect the wall-time budget; completed deterministic
cases are checked for identical search counters, models and proof bytes.

Samples flush about once per second at safe parser/search checkpoints, plus
search start/finish. A long single operation can delay a sample. The harness
keeps pipe output after process-group SIGKILL and marks the last sample as
partial. Last flushed counters are not final full-budget totals and are never
silently replaced with zero. An external-kill self-test requires multiple
nonzero work samples to survive. Independent original model/DRAT/LRAT checks
remain mandatory; uncertified results receive the PAR2 timeout penalty.

The report fails closed on incomplete source/arm/repetition coverage and shows
per-family PAR2, solved counts, paired bootstrap by original SHA, and telemetry.
This experiment diagnoses the next single optimization; it does not merge or
promote one automatically.

## Recovery from interrupted stderr writes

Run 43390611380 stopped in telemetry JSON parsing after budget enforcement. Recovery reuses exactly its inputs and diagnostic binary and the same frozen solver binaries. Only malformed, unterminated final records after an external timeout kill may be skipped; their byte count and SHA256 are audited. Raw stderr is saved before parsing. All prior complete samples remain intact, and complete malformed records still fail.

Recovery retains only complete six-arm groups for one formula and repetition, validating source, binary, cap and telemetry identities. Incomplete groups are rerun together on one runner; original artifacts remain available. Each result records its originating run. All 900 trials are still required. The original workflow is manual-only during recovery to prevent duplicate launches.

# DRNAS ATLAS39 — Clause Utility Memory CUM1 (2026-11-11)

## Hypothesis and intervention selection

ATLAS38 identified sharply divergent results from changing a **single
reduction** from 75% to 100%, including verified SAT->TIMEOUT transitions
on UF250 while an UUF250 control sometimes improved. BCP watch/prop
alone was not discriminative.

ATLAS39 changes the *identity*, not the number, of deleted learned
clauses: hold deletion quota at 75% of baseline C7 quota, and demote
recently reused learned clauses from top deletion candidates using an
independently counted, online utility proxy. Thus the intervention is
conditional **protection of a clause**, not a global aggressive
route. No training on source SHA, family, SAT/UNSAT labels or later results.

### Per-clause online score

For each learned clause ID, track:
- the most recent **valid learned-clause reason read during conflict
  minimization** (conflict clock);
- a saturating hit counter (max 8) for uses within 4,500 conflicts.
- utility-qualified means at least 2 touches and last touch within
  4,500 conflicts.

On every C7 reduction, candidate clauses still pass the frozen C7
locked-reason, LBD < 7, and short-clause checks. The current C7
priority is `100 * LBD + min(clause_size, 99)`; C39_PROTECT
subtracts 500 for a utility-qualified candidate. C39_SHADOW computes
the exact same metadata and records how many clauses qualify, but
does not change sorting. This is a fixed preregistered threshold.

Unlike a no-delete guard, the discount does not make any learned
clause immortal: if the eligible pool requires deleting it, it can
still be removed. The same 75% deletion **quota and cadence** are
preserved in both C39 modes. A separate counter
`atlas39_changed_rank` measures how many selected deletion CIDs
actually differ from the unmodified baseline ranking; a nonzero
metadata or recent-count alone does not prove a behavioral intervention.

### Precision, memory, CDCL integrity

The collector measures only a subset of reason uses: valid learned
reasons examined during clause minimization; it is **not** a complete
measure of all BCP implications or every conflict analysis reason.
No SAT/UNSAT inference code is changed, and no heuristics or RNG
calls are introduced on the frozen C7/A36/Kissat arms.

Metadata uses per-slot uint32 conflict timestamps and uint8 saturated
hits, remapped with the same authoritative CID table as the LBD during
compaction. It is instrumented only in C39 modes; its capacity cost is
reported. SHADOW isolates overhead of monitoring from the causal
effect of applying the bonus.

## Paired benchmark

- Experimental branch only; main and original CNFs untouched.
- 10 original SATLIB SHA from regression indices 0/1 (nonblind).
- 6 original SATLIB SHA from extension indices 10/11 (nonblind).
- 10 additional original SATLIB SHA from five families at indices
  12/13 (prospective relative to ATLAS37, **not global blind**).
- 5 arms: C7 stable, A36_75, C39_SHADOW, C39_PROTECT, pinned Kissat.
- 2 paired seeds, one logical CPU per solver, caps 10s regression,
  12s extension and hard. 26 SHA x 2 x 5 = **260 trials**.
- Original CNF SAT model verification required; any UNSAT without an
  independent LRAT proof remains UNSAT_UNVERIFIED. Both verified
  SAT-only PAR2 and reported (unverified UNSAT included) PAR2
  are disclosed separately. E2E and telemetry include runtime overhead.

### Promotion gate

Only consider C39_PROTECT for default if the held-out hard cohort
shows verified solved/PAR2 benefit and no material regressions,
relative to both C39_SHADOW and frozen A36_75, with evidence
`atlas39_changed_rank > 0` that protection actually changed the
deletion selection. Otherwise retain A36_75.

## Reproduction

- Generator: `research/drnas_atlas39_build.py`
- Runner: `research/drnas_atlas39_benchmark.py`
- Independent audit: `research/drnas_atlas39_audit.py`
- Workflow: `.github/workflows/drnas-atlas39-clause-utility.yml`.

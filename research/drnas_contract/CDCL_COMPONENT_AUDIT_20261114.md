# DRNAS CDCL ↔ component contract audit — 2026-11-14

**Status:** source audit plus isolated experimental verification; **not** a production promotion.
**Baseline:** frozen COOP5 FIXED (SHA `4dc87df8...`) and COOP5.2 cap24k, under 1 logical CPU and original-CNF proof checks.
**Source scope:** `src/drnas_x5.cpp`, `research/drnas_coop4/{coop.hpp,retention_methods.inc,build.py}`,
`research/drnas_coop5/{probe_methods.inc,build.py}`, `research/drnas_coop52/build.py`;
OMEGA4.2 is a **separate CaDiCaL external-propagator backend**, not a module in this X5 binary.

## Actual call graph (COOP5/X5 variant)

```text
parse original DIMACS -> CDCL original clause store -> COOP4 original copy
  -> init fixed VSIDS heap + COOP4 delayed source analysis
  -> loop:
       CDCL propagate (binary implications + watched literals)
       COOP5 pending-feedback settlement (observational; no proof)
       IF at BCP fixpoint: COOP4 step
           independent structural/Walsh scan on source CNF
           certified RUP proof intermediates -> proof stream
           certified lemma -> CDCL clause store (must be globally entailed)
           optional actual unit/conflict and propagation
           unproven structural variable hint (only advisory)
       WHEN no conflict:
           X5 native branch choice
           COOP5 (bounded speculative BCP) compares baseline/COOP4 hint,
                 can only override branch variable, never claim SAT/UNSAT
           true CDCL decision/enqueue
       conflict: first-UIP analysis -> learned clause -> backtrack -> restart/reduce/GC
```

**Current result:** 2026-11-14 REAL36 `run 43531107776`, 72 matched attempts per arm:
frozen COOP5 24 solved / 770.053 s PAR2; COOP5.2 cap24k 24 / 770.068 s;
COOP5.2 fallback 24 / 771.573 s; Kissat 26 / 745.502 s; CaDiCaL 26 / 742.929 s.
All scored UNSAT are independently proof checked. Dataset is retrospective, not blind.
Fallback consumed 147,076 probe pairs and made 5,358 overrides without solving a new instance.
These data refute the premise that more speculative BCP automatically helps.

## Findings (code-level, with evidence and uncertainty)

| ID | Boundary | Finding | Severity / interpretation |
|---|---|---|---|
| A01 | COOP4 `known` ↔ CDCL reducer | `Engine::known` remembers certified lemmas; ordinary `reduceLearnts` may delete the CDCL clause without clearing the corresponding `known` key when COOP4 mode is `on`. | P1 **liveness/efficiency risk**, not demonstrated wrong answer. Re-derivation can be suppressed after deletion; require lifecycle bookkeeping and a regression. |
| A02 | COOP4 hint ↔ BCP | `cooperate()` assigns `coop_hint_=out.hint` **before** adding/propagating certified clauses. Its hint can become stale if propagation, a unit, or a backtrack changes the trail. | P1 **policy coherence risk**. Current branch variable is checked unassigned, but the hint's derivation state is not explicitly validated after mutations. |
| A03 | COOP5 probes ↔ CDCL state | Speculative `probe()` uses live solver watched lists, trail and heap, then backtracks. Trail restoration is intended; watched-literal relocation is permitted. No explicit probe postcondition currently checks trail/phase consistency. | P1 **contract-test gap**, not a demonstrated solver defect. Audit sampled returns; never require identical watch ordering. |
| A04 | COOP5 feedback ↔ controller | `coop5Settle()` measures a chosen branch's immediate implied literals/structural distance, not the unchosen branch's counterfactual outcome. | P2 **learning metric mismatch**. Must not train policy with proxy as if verified end-to-end speedup. |
| A05 | Probe partials ↔ ranking | Limited BCP prefixes can differ in measured reduction; the score compares prefixes rather than completed subproblems. | P2 **bias risk**; report complete/incomplete separately and gate on confidence. |
| A06 | Controller ↔ resource budget | 25 ms is per-solve cumulative budget. Fallback polls many times and raises overhead even when there is no high-utility recommendation. | P2 **performance**; require utility gate and adaptive abstention from blind holdout. |
| A07 | COOP4 proofs ↔ CDCL clause owner | COOP4 may provide only original-CNF implied clauses. Proof intermediates must precede learned-lemma insertion; UNSAT status requires an independent DRAT/LRAT checker. | **Safety invariant**; existing tests cover many small cases. Audit all generated results. |
| A09 | Native CDCL settings ↔ component efficacy | The COOP5 benchmark invokes `--x5-no-minimize`; base X5 defaults `x5_retain_=false` and `x5_restarts_=false` (adaptive restarts OFF, geometric restart schedule ON). The LBD protection branch in `reduceLearnts()` is only active under retention. | P1 **benchmark configuration gap**. Do not conclude component quality explains the two extra UNSAT timeouts without separately testing minimization, retention and adaptive restarts on identical originals. |
| A08 | X5 CDCL ↔ OMEGA bridge | OMEGA4.2's connected CaDiCaL external propagator and X5/COOP5 do **not** share a native clause/trail/reason API. Previous OMEGA UNSAT lacks an independent original-CNF proof, and its parser/extractor logged failures. | **Integration blocker**. Do not call this a unified solver without implementing a typed, proof-carrying bridge. |

## Required component protocol (future architecture)

Components must consume an immutable `Context` snapshot:
`{original_sha256, solver_epoch, trail_epoch, decision_level, conflict_id, qhead_fixpoint, budget}`.
They may return exactly one of:

- `Abstain(reason, cost)`: no state mutation.
- `Hint(variable, proposed_phase?, context_epoch, confidence, cost)`:
  **not a logical consequence**; CDCL may ignore it and must discard it if epoch changed.
- `Lemma(clause, proof_steps, origin_sha, context_epoch, cost)`:
  clause must be globally entailed by the **original CNF** and independently checkable.
  CDCL owns insertion, watch lists, deletion and reason IDs.
- `Conflict(proof)`: only after CDCL/independent proof validation, never from
  a bounded speculative BCP timeout.

### Nonnegotiable invariants

1. No solver may claim SAT without a witness checked on the **original** CNF.
2. No UNSAT in the verified PAR2 metric without independently checked DRAT/LRAT.
3. A speculative probe may never commit assignments, decision stack, reasons, phases, or clauses.
   Watch relocation is allowed if it preserves watcher invariants.
4. A hint is valid **only** for the trail epoch from which it was computed.
5. Every component clause has provenance and a deletion/GC lifecycle event.
6. Deleting a component clause updates its presence ledger, without treating
   a remembered signature as a clause still active in the solver.
7. CPU, preparation, proof-generation and probe costs are included in E2E solve time.
8. Freeze reference binaries/source SHA; use one logical CPU per solver, paired source/seed,
   train/validation/holdout separation, and no automatic promotion.

## First measured dynamic contract evidence

[Contract safety run 43534791673](https://github.com/Frane12/AndroidGameTest/actions/runs/43534791673) completed successfully:
- 71 exact tiny SAT/UNSAT formulas × 2 modes × 2 compiled audit/repair variants = **284** oracle trials, **104** independently checked UNSAT proofs, no false SAT/UNSAT;
- six additional real SAT2024 originals, including planning ID 5, Simon XOR, scheduling and miter;
- **62 sampled speculative BCP rollback checks**, no detected trail/phase/qhead leakage;
- one observed hint generated before a mutation of the CDCL trail (miter ID 23); repair explicitly invalidated it;
- repair tracked **140 component-generated lemma insertions** on these six real originals and cleared **121 remembered signatures** when CDCL removed their clauses (mostly hardware-miter ID 23). These are cleanup counts, **not** proof of improved runtime or of 121 unique clauses being rederived;
- audit-only and repair each verified 1 SAT and 1 UNSAT among the 6 originals within the 2 s cap.

These are **source-/execution-grounded behavior differences** rather than a general benchmark win.
The modified *repair* binary is proof-safe in these tests; the full paired performance run must
determine speed impact. No promotion until independent blind holdout.

## Verification stages

**C0 — static source contract:** identify all CDCL mutation sites (enqueue,
cancel, propagate, analyze, reduce, GC), bridge ingress/egress, proof writers
and output parsers. Fail if expected generator source markers move.

**C1 — dynamic safety:** 280+ small SAT/UNSAT oracle runs plus independent DRAT
verification, and larger real planning/XOR/scheduling originals. Record
probe rollback invariant and hint invalidation. Every false proof/mismatched
model aborts the workflow.

**C2 — provenance and lifecycle:** track component-origin clauses, log deletion
and known-key invalidation, test no stale IDs after GC and no active clause
lost because of a remembered-but-deleted signature.

**C3 — performance:** same-source paired baseline vs audit-only vs repaired
variants; cap 3–8 s; report verified PAR2, overhead, actual branch overrides,
conflicts, clause learning, proof costs, RSS. No positive performance claim
from proxy-only counts.

**C4 — OMEGA adapter:** until a typed explanation/proof interface exists,
keep OMEGA4.2 in a separate comparison arm. Validate original DIMACS parser,
XOR-row source extraction, and independent proof on UNSAT before allowing its
conclusions into a combined CDCL engine.

## Promotion gate

No changes to `main`. A repair can be promoted only after (a) zero incorrect
SAT or UNSAT, (b) complete, independently verified source/proof accounting,
(c) a new source-disjoint blind holdout with robust family-level bootstrap,
(d) >=10% verified PAR2 improvement against frozen best baseline without
unacceptable family regressions, and (e) single-logical-CPU reproducibility.

**Links:** [COOP5.2 REAL36 cross](https://github.com/Frane12/AndroidGameTest/actions/runs/43531107776),
[COOP5.2 safety preflight](https://github.com/Frane12/AndroidGameTest/actions/runs/43530828469),
[OMEGA4.2 development](https://github.com/Frane12/AndroidGameTest/actions/runs/43519470159).

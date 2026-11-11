# LTM3 audit findings before implementation

Audit date: 2026-11-11. Frozen upstream commit: 4c49a9e34366072331ff1163ef96cee13c19bcb7. Upstream run: https://github.com/Frane12/AndroidGameTest/actions/runs/43077442528 (running when inspected).

1. `mi_ltm3/experiment.py` subtracts preprocessing from the nominal 3 s budget, but calls `mi_ltm1/native_paired.py::solve`, which grants `timeout=cap+2`. `run_arm` credits valid return codes without checking full E2E against CAP_S. Late solver results can receive solved/PAR2 credit. Fix on an isolated branch: hard subprocess timeout using remaining E2E budget and explicit `within_budget` scoring, retain late-valid candidate status separately.
2. `mi_ltm1/xor_templates.py::derive_bounded` combines source rows only. It does not recursively combine newly derived relations. This limits discovery of length-three cycle contradictions and longer transitive binary implications. Proposed experiment: bounded overlap-indexed closure, each derived row carrying an XOR set of original equation indices; independent revalidation against original CNF before injection. Preserve existing pairwise method as a separately measured control. No imported cross-formula facts.
3. Gating must use only current cheap structural features and a training-only frozen policy. Changing intervention or accounting semantics requires separate memory/cache identity; old measurements must not train the new policy. Original generators, source manifests and native solver remain unchanged.
4. Export separate gate/probe/write/native timing, actual additions, activated-but-empty probes, certificate-verification time, result deadline classification, and pairwise-versus-closure measurements. Template recognition is diagnostic, not evidence that it changed a CDCL decision or improved solve time.
5. Existing holdout is reused and is therefore a regression holdout after its first evaluation, even if SHA-disjoint from training. Validation of broad generalization requires a later pre-registered untouched external cohort, with one logical CPU and original-CNF proof checking.

These are source-level findings and experimental hypotheses, not measured speedups. Stable main, upstream LTM3 branch and frozen controls are not to be modified.

## Implemented experiment

- Unchanged native ATLAS15 A solver and unchanged CNF generator, pinned through parent commit.
- Strict remaining-budget child timeout and explicit full-E2E solved eligibility. Late-valid outcomes remain visible as candidate_status.
- Bounded overlap-indexed multi-step XOR closure with symmetric-difference source provenance; independent original-CNF verifier gates injection. Pure binary XOR uses linear component/parity traversal. BCP-redundant transitive binaries are not injected.
- Existing pairwise inference remains the PAIRWISE control. Forced relational inference and training-only frozen GATE are separate arms.
- Empty-positive policy falls back without scanning CNF features. No arbitrary forced activation is presented as learning.
- Separate relational-v2 training database/cache prevents old timing/intervention evidence from affecting policy.
- Original CNFs and compact model/inference certificates are retained; external verification cost is separately reported.
- 15 tests include 200 independently enumerated random small formulas, 3-row XOR cycle, long relations/provenance cancellation, incomplete encodings, tampered proofs, budgets, empty-policy fallback and late valid SAT.

This is an experimental research variant. A correctly discovered relation is not a speedup claim. Repeated holdout is regression evidence, not new blind validation. General external UNSAT proof tracing remains a separate requirement.

## Publication reconciliation

Before publication, upstream LTM3 still points to `4c49a9e34366072331ff1163ef96cee13c19bcb7`. A separate ongoing audit-fix branch now exists at `cbb85ebdc19f833ea7c27fc0207ea89eeb777c7f`, with successful benchmark run https://github.com/Frane12/AndroidGameTest/actions/runs/43081281276. That branch implements bounded Gaussian/RREF closure and strict timing. REL2 is an isolated ablation from the common frozen parent, not a replacement or overwrite of that work. Its distinct changes are overlap-guided closure, binary parity-component conflict detection, omission of BCP-redundant binary additions, empty-policy fast fallback, and retained independent artifact checks. No old runs are dispatched again.

The existing audit-fix run solved all 384 holdout attempts in each arm. BASE PAR2 was 2.184396 s; pairwise 2.891715 s; MI_CHAIN 2.905027 s; gated 2.322322 s. MI_CHAIN changed conflicts from 4260 to 4032 but had zero learned gate activations. These are prior-run observations, not same-machine timings against REL2.

Timeouts are audited trials, not mathematically verified solutions; `trial_audited` and `verified` are separate. Linux native-child and harness peak RSS are exported across the entire run, explicitly not per-arm memory measurements. The native process address-space guard is 2 GiB. Certificate checking has separate elapsed time and is not counted as solver PAR2 time.

# DRNAS Q-LINK / Quantum-like Coupled Relations (NOT quantum computing)
## A proof-carrying message language for interaction between equation clusters

Status: **proposed design only, no Q-LINK benchmark launched**.
Parent experiment: LEGO-3, branch \`experiment/drnas-lego3-up-learning-diverse-short5-20261109\`.
Research branch: \`experiment/drnas-qlink-proof-carrying-messages-20261109\`.
The separate branch intentionally does not edit frozen benchmark sources or stable main.

### Research hypothesis

LEGO-3 learns a structural table based on additional unit-propagation gain of
already-proven XOR/implication relations. Q-LINK asks whether communications
between *different* constraint clusters can be cheaper and more useful than
materializing all possible relations, when a shared separator becomes assigned.

The name "coupling" is only a metaphor. The actual mechanism is classical:
proof-carrying logical implication, GF(2) elimination, bounded
constraint/factor-graph message passing, watched variables and CDCL propagation.
No physical entanglement and no claim of polynomial algorithms for NP-complete
SAT.

### 1. What is coupled?

A cluster C is a limited family of original-source-proven XOR equations,
binary implications, and original CNF clauses. Two clusters are connected
through small shared variable separators. Distinct clusters may share a hidden
linear expression even if they have no direct binary implication.

Example:
  A: a XOR b XOR x = 0 [complete original CNF XOR cube]
  B: a XOR b XOR y = 1 [complete original CNF XOR cube]

Q-LINK reduces the symmetric difference:
  L: x XOR y = 1 [replay with source certificates for A and B]

If x=1 on the *current CDCL trail*, y=0 follows. But this is a CONDITIONAL
message (reason ¬x ∨ ¬y), not an unconditional learned unit. The reason is
a valid consequence of the original source, and the decision-level guard must
remain attached to any materialized inference.

For larger parity rows:
  A: a XOR b XOR x XOR z = 0
  B: a XOR b XOR y = 1
  => x XOR y XOR z = 1.
If trail includes x=1,z=1 then y=1, with source-entailed reason
  (¬x ∨ ¬z ∨ y).
The reason is logically valid globally; y=1 is valid ONLY in the guarded
context. On backtrack, the temporary assignment is retracted.

### 2. Minimal exchange language (QCL-1)

All examples below are human-readable diagnostic form. Implement using typed
C++ records, not a free-form interpreted language on the solver hot path.

  CTX  sha256=<original-CNF-SHA> session=<solve-id> epoch=<trail-epoch>
  DEFINE id=R17 domain=GF2 vars=[a,b,x,z] rhs=0 proof=SOURCE_CUBE:[7,14,19,28,...]
  DEFINE id=R21 domain=GF2 vars=[a,b,y] rhs=1 proof=SOURCE_CUBE:[...]
  JOIN   id=R22 parents=[R17,R21] rule=XOR source_proof=DAG
         result=(x XOR y XOR z = 1)
  WATCH  relation=R22 separator=[x,z,y] recipient=CDCL_TRAIL
  SEND   id=M14 from=R22 guard=[x=1,z=1] effect=[y=1]
         reason=[-x,-z,y] proof=DAG:R22 ttl=1
  ACK    id=M14 accepted=1 new_propagations=1 conflict=0
         elapsed_us=<measured>; decision_delta=<diagnostic_or_missing>
  DROP   id=M14 why=budget|duplicate|no_new_propagation|stale_epoch|invalid_proof

A conditional message can be delivered as:
- a trail propagation with a valid reason (and proper undo on backtracking);
- an implied CNF reason clause of bounded width, after proof verification;
- a watched higher-width XOR row (not all 2^(k-1) clauses materialized).

Message identity: (source-SHA, normalized relation, guard, effect, trail epoch).
No messages between different *original CNF* source SHA instances. The
learned **ranking policy** may be transferred across cases; actual theorem
claims, learned clauses, UNSAT proofs and assignments may NOT be transferred.

### 3. Formal safety invariants

I1. Every unconditional derived row R is globally entailed by the original
    CNF: F |= R. Verify each source XOR cube, each graph implication path
    and every linear XOR proof composition from original clause indices.
I2. A conditional message is an implication F |= (G => L). The full guarded
    implication, not L alone, must be checked. Guard literals are ordered
    and deduplicated; contradictions invalidate the message.
I3. CDCL trail assignments are not global axioms. Every propagation carries
    a reason clause; backtracking retracts the assignment. Never add L as
    a permanent unit just because G happened to be true.
I4. Watchers subscribe by shared variables and only wake on relevant changes.
    Never assume separate disjoint clusters can exchange a theorem.
I5. Any CNF augmentation is append-only, source-entailed and validated
    against original CNF with independent proof replay. Timeouts fail closed.
I6. Stop duplicate cycles: normalized message hash, monotonically increasing
    trail generation, TTL (at most 2 hops) and source-DAG deduplication.
I7. SAT must be checked with the ORIGINAL CNF witness. UNSAT certificates:
    use an independently checked LRAT/FRAT/DRAT where available; otherwise
    mark as cross-solver agreement, NOT independent certificate.
I8. Learning only controls scheduling, attention and bounded exploration.
    A model or signature table NEVER changes what counts as a proof.

### 4. Concrete algorithm: equation-to-equation communication

A. Parse original CNF. Detect complete XOR half-cubes width 2-4, signed
   SCC aliases with exact original binary paths. Build proof DAG.
B. Hypergraph: cluster source-proven relations by overlap; keep separator
   size <=3, cap row width <=8, rank connected candidate pairs by overlap,
   potential output width and watched trail activity.
C. Sparse elimination: cache normalized XOR cancellation keys. Cancel
   shared variables to create R=A XOR B and source-proof witness.
   Reuse relation DAG; avoid expensive all-pairs Gaussian scans.
D. Register a watched parity row. Under CDCL trail, update unassigned
   count and accumulated parity; only emit when one variable is unassigned,
   or when no variable remains and parity conflicts.
E. Convert any real propagation into a globally valid guarded reason
   clause (or equivalent fully certified reason), and pass it to CDCL.
F. On ACK, update *value of information* (VOI) for the relation signature:
      (new UP + w_conflict*new conflicts + w_decisions*saved decisions)
      / (cost microseconds + proof verification + wakeups).
   Exact weights frozen before test; zero progress yields no reward.
G. If communication is idle or costly, abstain. Keep original Kissat or
   CaDiCaL racing as a reliable fallback.

"Quantum-like correlation" is therefore a small, sparse, proved bridge
between equation clusters; it is not faster-than-light signaling or a
quantum computer.

### 5. A discriminating experiment (after LEGO-3 audit)

Stage Q0 (logic tests, no solver):
- signed polarity permutation and variable renaming,
- connected XOR pairs with hidden separator cancellation,
- 3-/4-way chains with genuine conditional propagation,
- incomplete XOR cubes, broken SCC paths, unrelated components,
- contradictory guards, backtrack stale messages, proof-cycle dedup.
- Exhaustive truth tables for <=12 variables; larger cases source-replay.
Required: 0 unsound messages, fully verified reasons. Fail closed.

Stage Q1 (cheap 1s structural screening, <=50 ms total extra work/formula):
- log cluster count, sparse elimination operations, watched events,
  actually new propagations, conflicts, proof replay time and guard width.
- compare no-message placebo, static proof-only, learned VOI scheduling.
- keep per-relation microbudget <=1ms, wake only on changed trail vars.
- collect family diversity; do not overfit one XOR-rich synthetic family.

Stage Q2 (5s paired end-to-end, same original SHA and two-CPU budgets):
- 8 proof-rich generated positives; 8 negative controls;
  8 source-original SAT2024/2025/2026 instances (recycled, label not blind)
  => 24 sources x 2 seeds x 4 arms = 192 E2E trials.
- arms: source-only race; LEGO3 frozen best; Q-LINK proof-only
  placebo/no SEND; Q-LINK active + pretrained ranking.
- cap 5s/attempt, timeout PAR2=10s, 4 concurrent shards.
- report per cohort: solved, total PAR2, % and x, CPU cost,
  new BCP propagations and conflicts, CDCL decisions where instrumented,
  verified proof count, stale/drop counts, fallbacks, regressions.
- more than source-agreement UNSAT must be explicitly certified
  before counting independently proved UNSAT.

A genuinely new blind real-source evaluation should follow only after
stronger proof-gated controls, and must be prepared with disjoint
source SHA and pre-registered exclusions.

### 6. Promotion criteria

Proof soundness 100% on unit tests and source replays.
At least one **measured conditional propagation not present in the original
BCP closure** on positive controls, with zero negative-control false claims.
Q-LINK active must improve PAR2 on held-out real cohort *including all
communication and proof costs*, not just derived equation count or CPU total.
No automatic promotion to stable baseline.


---

## Q-LINK-1 implemented short5 pilot (2026-11-09)

Executable prototype: \`research/drnas_qlink1_messages.py\`.
Workflow: \`.github/workflows/drnas-qlink1-short5.yml\`.

In contrast to the eventual target of native, in-process CaDiCaL/Kissat
watcher integration, THIS FIRST PILOT uses an **offline BCP simulator**
before launching the two CDCL solvers. It conditionally materializes a
globally implied *guarded reason clause* for the second CaDiCaL worker.
The first Kissat worker always receives the unchanged original CNF.
\`ACK\` means "new BCP propagation in a deterministic simulated trail";
it is NOT an ACK from a running CDCL solver and not evidence of faster
CDCL propagation. Do not describe this as native CDCL message passing.

Typed message contents:
- \`CTX\`: frozen source SHA + epoch (probe epoch 0);
- \`JOIN\`: two or three source-entailed XOR and signed-SCC relations,
  with original clause-index proof references;
- \`WATCH\`: variables of the proven sparse parity relation;
- \`SEND\`: full guard on all but one relation variable, implied effect,
  globally entailed CNF reason clause \`(not guard OR effect)\`;
- \`ACK\`: new BCP assignments in a bounded offline test on the exact same
  original clauses and assumptions;
- \`DROP\`: budget, baseline already implies, duplicate, source-proof
  failure. SAT run is never changed if proof or time budget fails.

Safety gates: source-proof replay for every joined parity row; exhaustive
reason-clause truth-table validation on every emitted relation (width <=5);
read-only original source SHA; 2 logical pinned solver CPUs; 5s E2E cap;
original SAT witness verified; UNSAT only accepted with original frozen
X22 cross-solver agreement (no independent LRAT).

Frozen LEGO-3 data reused: 104 training sources and 24 E2E evaluation
sources selected from its prior 48 evaluation sources: eight synthetic
positive (one per structural family), eight negative, eight original X22
SHA instances (recycled, NOT a fresh blind holdout). Source SHA train/eval
disjoint; no learned solver outcome leakage. Four paired strategies with
two repetitions -> 192 E2E trials across four shards of 48 each:
  race_original; lego3_learned; qlink_shadow; qlink_active.

The shadow performs the SAME proof, bounded probes, and bookkeeping but
does NOT insert messages into CaDiCaL input, separating prep overhead from
actual clause benefit. Report both total PAR2 and cohort-specific counts,
CPU, preprocessing, guarded reason count, simulation ACK count, total
simulated BCP gain, and regressions. Do not promote a regression or a
synthetic-only advantage.

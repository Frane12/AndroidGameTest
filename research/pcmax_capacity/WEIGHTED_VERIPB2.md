# DRNAS PCMAX Weighted VeriPB2 — source-bound certificates

Status: experimental. No changes to `main` or the CDCL reference solver.

## Claim and trust boundary

For a SHA-verified original CNF, the native PCMAX detector emits a structural
capacity certificate. `check_capacity.py` independently checks the original
clauses, BDD transitions, group clauses, capacities, and the SHA. That checker
alone is **not** an external VeriPB proof.

`emit_veripb_capacity_weighted2.py` emits a VeriPB 3.0 proof directly from the
**unchanged input CNF** and source-checked certificate. The producer prints
`EMITTED_UNCHECKED`, never `VERIFIED`. Only the independently installed
VeriPB 3.0.2 checker returning code zero and
`s VERIFIED UNSATISFIABLE` establishes a standard accepted proof.

## Mathematical scheme

For each BDD machine, give selected variables positive integer weights `w_i`
(the group weights; unselected decision variables have zero weight). For every
state `q`, let `W(q)` be the total remaining selected weight in its ordered
suffix and `M(q)` the *maximum* weight of accepted assignments from `q`,
with skipped selectors conservatively counted as selectable. The recursive
maxima are independently checked against actual source transition clauses.

Prove the source-entailing conditional weighted inequality:

```text
  sum_{i in suffix(q)} w_i * ~x_i + D(q) * ~q >= D(q),
  D(q) = W(q) - M(q).
```

For a node testing `x` of weight `w`, obtain the inductive low/high bounds
from already derived child inequalities and the **original** CNF clauses:

```text
  ~q +  x + lo >= 1
  ~q + ~x + hi >= 1
```

For suitable nonnegative child deficits `A,B` and remaining complement
weighted sum `T`, cutting planes derive:

```text
  T + A*~q + A*x  >= A   (low)
  T + B*~q + B*~x >= B   (high)
```

The parent deficit `D` satisfies `D <= A+w` and `D <= B`. Under the
negation of the parent inequality, combine the low inequality using `pol`,
weaken the state literal, and divide to derive `x >= 1`. Do the same for the
high inequality to obtain `~x >= 1` or an immediate contradiction. This
`pbc ... : subproof ... qed;` certifies the conditional parent inequality.
Dead BDD nodes are certified by source RUP; false terminals use input unit
clauses. No exhaustive forbidden-subset lattice or general SAT backend is
required in this proof producer.

At each input root (which has a source unit clause), discharge `~q` to get:

```text
  sum_{x_i on machine j} w_i*~x_i >= sum_{i on machine j} w_i - C_j.
```

Weight each input group at-least-one clause by its group weight `w_g`.
Summing all group inequalities with all machine bounds cancels every selector
with its complement, deriving a contradiction whenever:

```text
  required_weight > total_machine_capacity
```

This is an existing cutting-planes / BDD-proof technique application; it is
**not** a claim of a new complexity class, P=NP, or world-record SAT speed.

## Reproduction and frozen evaluation

See `.github/workflows/drnas-pcmax-veripb-weighted2.yml`.

- Pin independent `veripb` version `3.0.2`.
- Fetch each source original using `sources20.json` SHA-256 identity.
- Compile existing `drnas-pcmax`; run one logical CPU.
- Regenerate native capacity certificate; source-check it separately.
- Produce `.pbp`; call `veripb --cnf original.cnf proof.pbp` with hard limits.
- Count `UNSAT` only for a successful external verification; otherwise fail
  the audit or return `UNKNOWN`.
- Log SAT-labelled controls and all negative or inconclusive results.

The original20 collection has been used for earlier development: results are
**retrospective**, not blind, and not a competitive PAR2 comparison.
Independent prospective holdout and head-to-head per-solver CPU + E2E time
measurements are required before claiming generalization or speedups.

### First smoke (15 Nov 2026)

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43719128700

| Original | Required | Capacity | VeriPB 3.0.2 | Bytes | Producer s | Checker s |
|---|---:|---:|---|---:|---:|---:|
| PCMAX m11 | 16 | 15 | accepted | 181816 | 0.08561 | 0.02117 |
| PCMAX m13 | 105 | 104 | accepted | 323657 | 0.09683 | 0.03065 |
| PCMAX m14 | 31 | 30 | accepted | 557597 | 0.13993 | 0.04557 |
| PCMAX m20 | 42 | 41 | accepted | 929189 | 0.20559 | 0.06073 |

The m14 case is labelled `UNKNOWN` in `sources20.json` (its name includes
UNSAT). The external VeriPB acceptance is evidence of UNSAT for the exact
SHA-identified CNF; catalogue metadata must not be used as an oracle.

### Complete retrospective original20 verification (15 Nov 2026)

Green reproducible run: https://github.com/Frane12/AndroidGameTest/actions/runs/43719601339

- Source CNFs checked by SHA-256: **20/20**.
- Native and independently source-checked structural UNSAT: **11/20**.
- Exact original CNFs independently accepted by VeriPB 3.0.2: **11/11** structural UNSAT cases.
- SAT-labelled controls safely left UNKNOWN (no UNSAT certificate): **9/9**.
- Rejected standard proofs: **0**; benchmark errors: **0**.
- Proof sizes across the eleven cases: **181,816 to 2,586,374 bytes**.
- Measured proof production times: **0.05013 to 0.49727 s** on this runner.
- Measured independent checker times: **0.01192 to 0.13845 s** on this runner.

The verified PCMAX44 proof is **181,816 bytes** vs the earlier
**14,595,317-byte** RUP + cover-lattice proof accepted in
https://github.com/Frane12/AndroidGameTest/actions/runs/43710302901
(approximately 80.3x smaller). The output speed is not a paired SAT solver
benchmark; this size improvement is a proof-generation and checking result.

This is full retrospective coverage of the already known PCMAX20 dataset.
Do not claim broad performance improvements or fresh blind generalization from it.

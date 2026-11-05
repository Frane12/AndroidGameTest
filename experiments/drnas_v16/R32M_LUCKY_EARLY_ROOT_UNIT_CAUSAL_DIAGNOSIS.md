# DRNAS R32m follow-up: why 12 root GF(2) units unlock lucky-early

**Date:** 2026-11-03  
**Baseline run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41649862030  
**Audited summary:** https://github.com/Frane12/AndroidGameTest/actions/runs/41649862030/artifacts/13236702953  
**Original SHA-frozen CNFs:** https://github.com/Frane12/AndroidGameTest/actions/runs/41649862030/artifacts/13236134214  
**Native pinned clean/phase binaries:** https://github.com/Frane12/AndroidGameTest/actions/runs/41649862030/artifacts/13236957799

## Exact single-process cause

Investigation used the original R32m pinned Linux x86_64 native binary and
previously SHA-audited original CNF files. The same mathematically certified
signed root units were added to the **original CNF source** as new unit
clauses for independent leave-one-out diagnosis; the result phase was
compared against the prior native parse-time ablation. This is an
equivalent SAT formula but not a bit-for-bit identical input, so wall
times are taken primarily from the frozen R32m benchmark.

**The exact successful Kissat native routine** on the two striking
R32l coupled-stress cases is `backward_false_satisfiable`, called by
`kissat_lucky` in the **early lucky phase** before `kissat_preprocess`.
This is a heuristic sequence of reverse-ordered attempted false
assignments with immediate probing. A case succeeds if the attempted
assignment/propagation route covers all active variables; it may fail
and backtrack on early conflicts. It is NOT a solver proof that regular
Boolean unit propagation alone solved the remaining source CNF.

Under native OFF on the 448-variable, 2,055-clause stressed sources,
12 original unit clauses force twelve `z_i=0` values.
Adding all twelve certified `w_i=1` consequences means 24 root
assignments and **424 variables still unassigned** at the entrance to
early lucky. The original unit-closure residual still has **1,995 clauses**,
including 368 binary and 1,627 ternary clauses. Therefore the early
result is unequivocally due to a *lucky/probing assignment route*, not
mere closure of the CNF by Boolean unit propagation.

## Why the native GF(2) units are mathematically true

Each source XOR gadget has four variables `(x,y,z,w)`, with a complete
set of eight parity-related 3-literal CNF clauses and the original
unit `¬z`. For example gadget #1 includes:

- `(x ∨ ¬y ∨ z)`, `(¬x ∨ y ∨ z)`,
- `(x ∨ y ∨ w)`, `(¬x ∨ ¬y ∨ w)`,
- and the original `¬z`, plus other clauses completing the parity blocks.

Since `z=0`, the first pair implies `x ⇔ y`.
If `w=0`, the next pair would imply `x ≠ y`,
a contradiction. Hence **`w=1` is logically entailed** even though
initial ordinary BCP need not derive it without trial assignments.
For the twelve independent gadgets, `w` variables have external DIMACS
IDs `[4,8,12,16,20,24,28,32,36,40,44,48]`.
This elementary local CNF proof agrees with the separately audited GF2
derivation and original-CNF witness checks.

The inference does NOT solve SAT in polynomial time; it adds sound
low-cost information from a **recognized special structure**.

## Actual leave-one-out causal probe

Under augmented original CNF, the terminal phase of exactly one native
Kissat process was checked with `R32M_PHASES=1` and original
`R32L_TRACE=1`. Reversing and shuffling the order of the 12 added
certified unit clauses did **not** change any of the three main
diagnostic cases' early success.

| SHA-audited formula | OFF exit | All 12 | Any 11 (one omitted) | Verified deletion-minimal triggering set |
|---|---|---|---|---|
| `r32l_stress_consistent_visible_331.cnf` | lucky late | lucky early | **all 12 omissions fail early** | 12 units (all) |
| `r32l_stress_consistent_mixed_333.cnf` | lucky late | lucky early | **all 12 omissions fail early** | 12 units (all) |
| `r32l_fresh_consistent_hidden_303.cnf` | lucky late | lucky early | Omit 16,36,48 individually without losing early result | **9-unit deletion-minimal set:** 4,8,12,20,24,28,32,40,44 |
| `r32m_base_consistent_visible_405.cnf` | lucky late | lucky early | **all 12 omissions fail early** | 12 units (all) |
| `r32m_base_consistent_mixed_403.cnf` | lucky late | lucky early | Some omissions tolerated | **8-unit deletion-minimal set:** 4,8,20,24,28,32,40,44 |

For the 9-unit and 8-unit sets above, removing **any one** additional
unit from the tested set reverts to a later phase. The qualifier
**deletion-minimal** means locally minimal by individual removal, not
a proof that no other smaller or different sufficient set exists.
The last two source identities belong to R32m's fresh synthetic cohort;
their terminal phases were audited in the original R32m benchmark,
while the per-unit omission probe was performed after that benchmark.

Under `-v -v` on the first case:
- All 12 units: forward-false and forward-true probing fail, then
  `lucky in backward setting literals to false` succeeds **before preprocess**.
- Missing signed unit 48: after the same forward attempts, early
  `backward assigning ... to false` reaches an inconsistency after 1
  conflict, and backward-true also reaches a 1-conflict inconsistency.
  `lucky_early` returns 0, the solver runs expensive preprocessing,
  then reaches SAT in `lucky_late`.
- Missing unit 4: early backward-false fails after four attempted
  conflicts, backward-true after two conflicts.
- The newly fresh `r32m_base_consistent_mixed_403.cnf` has a different
  successful early route: **backward-TRUE**, confirming that we must not
  incorrectly label all lucky wins as backward-false.

## Phase-local R32m timings (official audited 5/10-repeat medians)

| Original source | Native OFF end | Full-12 end | Native OFF median preprocessing CPU | Full-12 preprocessing CPU | OFF wall median | Full-12 wall median |
|---|---|---|---:|---:|---:|---:|
| `r32l_stress_consistent_visible_331.cnf` | lucky late | lucky early | 21.298 ms | **0 ms** | 24.851 ms | 3.719 ms |
| `r32l_stress_consistent_mixed_333.cnf` | lucky late | lucky early | 24.098 ms | **0 ms** | 28.050 ms | 4.226 ms |
| `r32l_fresh_consistent_hidden_303.cnf` | lucky late | lucky early | 27.475 ms | **0 ms** | 31.638 ms | 4.323 ms |
| `r32m_base_consistent_visible_405.cnf` | lucky late | lucky early | 19.956 ms | **0 ms** | 23.112 ms | 3.211 ms |
| `r32m_base_consistent_mixed_403.cnf` | lucky late | lucky early | 18.581 ms | **0 ms** | 22.776 ms | 4.207 ms |

### Scientific interpretation

The supplied root GF2 literals prevent native lucky probing from
taking logically impossible choices that its bounded forward/backward
probe heuristics do not always recover from. Once the relevant units
are fixed, at least some complete model-finding trajectories become
easy for native lucky. The causal conjunction of necessary units
is instance-specific; 12 is not a universal threshold. Variable
assignment *order* and connectivity to background CNF can still
change the success path.

Exactly which internal variable triggers each first failed probe has
**not yet been directly logged**; the next hypothesis should log
the first failed literal's original index and decision depth inside
`backward_false_satisfiable` and `backward_true_satisfiable`, read-only.
If new hard external cases are tested, keep the original-CNF unit
certificate and track total computation cost. This five-case
analysis is a controlled synthetic mechanism result, **not** a
general SAT performance guarantee or P versus NP breakthrough.

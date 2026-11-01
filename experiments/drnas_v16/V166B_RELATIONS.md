# DRNAS SAT V16.6b — Signed incidence-graph relations

## Scope and origin

This branch tests a **portfolio policy over the same pinned upstream Kissat 4.0.4 binary**. It does **not** change SAT semantics, imply satisfiability, add certified clauses, or create a new native SAT-solving algorithm.

The selector is an **exploratory hypothesis calibrated on already viewed V16.5 seeds**, not a newly discovered general mathematical law. V16.6b uses a wholly distinct, preregistered sequence of 8 test seeds `166600..166607`, without filtering based on running times, correctness labels, or difficulty.

## Exact structural relations

Let the original CNF have variable set `V` and clause set `C`. For every unordered variable pair `{u,v}` sharing a clause of size 2 through 5, record whether the literal signs of `u,v` have the same sign parity or different sign parity.

If `e(u,v)` and `o(u,v)` count the pair's equal-parity and unequal-parity occurrences:

- **Repeated-pair count**: number of pairs with `e+o >= 2`.
- **Repeated-pair rate**: repeated-pair count / total number of clauses.
- **Signed frustrated four-cycles**: `F = Σ e(u,v) * o(u,v)`.
- **Signed consistent four-cycles**: `G = Σ [e(u,v)(e(u,v)-1)/2 + o(u,v)(o(u,v)-1)/2]`.
- **Frustration proportion**: `F/(F+G)`, when the denominator is positive. Opposite pair parity on a four-cycle is a *descriptive signed-graph statistic*, **not** a logical contradiction.
- **Local polarity skew**: `(1/n)Σ |positive_occurrences(v)-negative_occurrences(v)| / total_occurrences(v)`. Degree-zero variables contribute zero.

Additional guards: near-threshold clause/variable density, exactly-three-literal clause fraction, degree coefficient of variation, literal polarity balance, and minimum signed-cycle sample count.

These signals are computed solely from **original CNF clauses**, no filename, seed, SAT/UNSAT result, Kissat runtime, or runtime trace.

## Why this candidate was tested

Previously observed development data:

| V16.5 formula | Density | Four-cycle frustration | Repeated-pair rate | Local skew | V16.6b policy |
| --- | ---: | ---: | ---: | ---: | --- |
| 165000 | 4.25938 | 0.52695 | 0.05906 | 0.22678 | `--sat` |
| 165001 | 4.25938 | 0.49693 | 0.05686 | 0.22855 | abstain/default |
| 165004 | 4.26042 | 0.49133 | 0.08069 | 0.23707 | abstain/default |
| 165005 | 4.26042 | 0.48387 | 0.07286 | 0.23640 | `--sat` |

The development cases were known to have different performance responses to `--sat`. This relation policy is therefore **post hoc for these four cases** and must not be scored on them as independent evidence. The fact that a graph statistic separates the examples does **not** establish a causal mechanism or a high-confidence predictor.

## Frozen policy

When near-threshold random-3SAT guards hold, select `--sat` only if either:

1. Frustration proportion >= 0.515, local skew <= 0.232 and repeated-pair rate >= 0.050, or
2. Frustration proportion <= 0.49 and repeated-pair rate between 0.065 and 0.080.

Otherwise **abstain** and run unmodified Kissat. No SAT/UNSAT prediction or answer is made by this policy.

## Protocol and limitations

- First run `v166b_property_test.py` to independently validate feature values and clause-order invariance.
- Generate and hash **all eight** fresh seed CNFs, plus two density controls, **before** timing.
- Run the same Kissat commit and hardware per case with four strategies: default, always `--sat`, V16.5 policy, V16.6b policy.
- Two repeats per CNF, rotate mode order. **Include selector file-scan time** for adaptive strategies.
- Check returned SAT assignments against the entire original CNF; compare SAT/UNSAT results across all modes.
- Evaluate on the **whole untouched test group using solved fraction and PAR-2**, including timeouts; present per-case winners/losses, but do not selectively exclude slowdowns.
- Leave V16.6b thresholds untouched after observing the results. Further work needs a *new* holdout and richer independent SAT source classes.

The holdout still uses the same generated random-3SAT family as development data; it is not an external SAT Competition test and does not demonstrate performance on arbitrary SAT instances.

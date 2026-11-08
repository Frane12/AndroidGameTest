# DRNAS MRE8f — MRE6f as a permanent experimental reference
**Final audited 2026-11-08, run 42504415829.** Branch:
\`experiment/drnas-mre8f-6f-reference-gate-20261108\`

## Reference and invariant
**MRE6f run 42499854392 is the immovable development reference.** The
certified positive equality detected using the two ORIGINAL binary CNF clauses,
transitive quotient, original-CNF SAT model reconstruction and original-SHA
verification are preserved. Do not replace this with uncertified learned-XOR
claims or silently redefine the MRE6f 5,000-conflict result as an SAT solution.

- Source and binary pin: upstream MRE6e run 42499473274;
  CMS shared-library source commit \`3b709118fd08eb1d15f25e0e239dbc596f967b60\`.
- New code: \`research/mre8f_6f_reference_gate.py\`
- Workflow: \`.github/workflows/drnas-mre8f-6f-reference-gate.yml\`
- Independent audit: same original SHA, same per-source seed, same binary, verified SAT witness,
  declared UNKNOWN at conflict caps, no independent UNSAT LRAT, total wall time inclusive of preparation.
- 3 arms: \`cms_native\`, \`mre6f_all\`, \`mre8f_gate\`.
- Predeclared gate: at least 128 eliminated variables, 256 eliminated clauses,
  and 8% fewer clauses. Never use runtime labels to choose gate treatment.
- Gate preflight checks original binary clauses first; if too few certified pairs,
  skip full quotient and use the original CMS.

## Audited bounded CDCL (7 reused SAT2026 originals, not blind)
126 attempts = 7 original SHAs x 3 repetitions x 2 conflict budgets (1,000 and 5,000)
x 3 arms. Each mode has **42 BUDGET, 0 solved**; PAR2=504s for
every arm because *bounded UNKNOWN is not SAT/UNSAT*.

| Arm | Total wall (s) | Total prep (s) | Quotient activations |
|---|---:|---:|---:|
| CMS native | 7.469325 | 1.833218 | 0/42 |
| MRE6f all | 8.250267 | 2.979115 | 12/42 |
| MRE8f gate | 7.643811 | 2.373610 | 6/42 |

MRE8f gate is **1.079x** faster than MRE6f all in bounded *total wall*;
it is **~2.34% slower** than pure CMS native. This is NOT a solver-verdict
PAR2 improvement.

- MRE6f known positive \`2fcd8533...\`: gate activated on 6/6 matched
  attempts, 672 variables removed, 1,344 clauses removed;
  the prior MRE6f reference measured about 35.09% fewer propagations at
  5,000 conflicts and 1.208918x full-wall bounded timing.
- MRE6f small-equality negative \`a45aefde...\`: gate abstained on 6/6;
  MRE6f all had known ~2x regression from expensive transform on this case.
- MRE6f no-equality control \`de8c42d5...\`: gate abstained on 6/6.
- Other four original source cases were included, not filtered post-hoc.

## Audited full SAT-to-verdict pilot (6 reference-selected SAT2024/2025 originals)
36 attempts = 6 SHA-locked original sources x 2 repeats x 3 arms;
full 8 s wall cap, PAR2 timeout 16 s. These six were already used in MRE7
pilot, selected by reference easiness, not a fresh 20-case holdout.

| Arm | PAR2 total (s) | Solved/12 | Timeout/12 | Gate activated |
|---|---:|---:|---:|---:|
| CMS native | 113.390861 | 6 | 6 | 0 |
| MRE6f all | 113.373049 | 6 | 6 | 0 |
| MRE8f gate | 113.325810 | 6 | 6 | 0 |

All solved attempts were SAT with original model verification.
The approx. 0.057% PAR2 difference native/gate is negligible timing noise,
**not proof that MRE8f improves end-to-end PAR2**.
No LRAT-certified UNSAT outcomes were obtained.

## Conclusions and next controlled experiment
1. The mathematical signal from MRE6f remains the mechanistic reference,
   not a general end-to-end speedup.
2. The selective gate avoids the obvious MRE6f all-equalities regression,
   and correctly abstains on weak/no-equality controls.
3. Python front-end still costs measurable wall time even when abstaining.
   **Next optimize preflight CPU cost in native C++ before altering threshold.**
4. Re-run an independently frozen source-disjoint cohort with a valid
   mix of quick-and-medium SAT/UNSAT instances. Do NOT select by observed
   target-runtime improvement. Clearly separate structural enrichment
   and unbiased source-disjoint evaluation.
5. Only promote if complete original-SAT-verdict PAR2 improves repeatedly
   at realistic limits, regressions are controlled, and proof correctness
   is independently checked where relevant. No production promotion now.

**Run:** https://github.com/Frane12/AndroidGameTest/actions/runs/42504415829
**Reference MRE6f:** https://github.com/Frane12/AndroidGameTest/actions/runs/42499854392

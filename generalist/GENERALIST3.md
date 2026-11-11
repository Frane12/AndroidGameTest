# GENERALIST3 Native strategy selection

Runtime: `python -m generalist.generalist3 solve original.cnf --policy frozen.json --binary mre_atlas23/bin/drnas_atlas40 --cap 60 --seed 1`.

This **actually invokes** the selected native A36_75/A39_PROTECT/A40_TREE mode
in one CPU process; does not invoke multiple solvers or guarantee wins.
`GENERALIST3_DECISION` records structure, selection and fallback.

Training: `python -m generalist.generalist3 train verified_trials.jsonl --out frozen.json`.
Every training record requires original SHA256, feature_key computed from the
original CNF, arm, verified_par2_s, cap_s, and original_verified=true.
Here original_verified means the trial was audited, NOT that SAT/UNSAT is solved.
Unverified UNSAT must be charged as 2×cap before preparing trial data.
Use at least 8 distinct original CNFs per structural cell, paired with baseline.
Cells lacking enough data fall back to A36. Do not tune on holdout cases.

The prior 26-CNF cohort has only 2 CNFs per narrow family, and therefore
does **not** license an automatic nondefault policy. Generalist3 structural
feature extraction uses density, clause lengths, binary fraction, unit clauses,
and maximum variable occurrence. It never inspects instance names or outcomes.
This does NOT prove predictive utility yet.

Prospective benchmark: freeze a SHA-disjoint policy and original manifest;
then compare native GENERALIST3_AUTO vs frozen A36, A39, A40 and Kissat with
one logical CPU per arm, identical timeouts and SAT witness checking. UNSAT
requires independent LRAT/DRAT or equivalent verified proof before certification.

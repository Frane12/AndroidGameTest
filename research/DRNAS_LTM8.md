# LTM8 fast and chaos

Build from the repository root:

```sh
python3 research/drnas_ltm8_compile.py
python3 research/drnas_ltm8_selftest.py
mre_atlas23/bin/drnas_ltm8 formula.cnf --mode LTM8_FAST --time 15 --seed 7 --policy 1.0,0.85
mre_atlas23/bin/drnas_ltm8 formula.cnf --mode LTM8_CHAOS --time 15 --seed 7 --policy 1.0,0.85
```

Both modes are native C++, single-threaded, in one executable. FAST uses mostly
VSIDS with saved phases, four bounded profiles and updates every 512 conflicts.
CHAOS updates every 256 conflicts and randomly varies variable choice, phase
flips, activity decay, restart timing and deletion quota. Its risk is slower
search, never speculative SAT/UNSAT inference. A fixed seed and identical memory
snapshot reproduce the choices; a wall-time cap can still stop at different points.

Online reward combines reciprocal learned-clause LBD and propagation work. This
is a heuristic surrogate, not proof of faster solving or neural-network training.
Profiles are retained across processes in `ltm8_memory.fast.BUCKET` and
`ltm8_memory.chaos.BUCKET`, separated by coarse source-CNF features. Use
`DRNAS_LTM8_MEMORY=/absolute/path/policy` to choose a durable location, or set it
to an empty string to disable disk memory for a clean benchmark. Lock contention
or an unwritable path falls back to session learning and prints a warning.
Snapshots have a version, checked values and atomic replacement under a lock.
Only complete observation windows are saved. Solves under 256/512 conflicts do
not train the cross-run profile memory. GitHub ephemeral runners do not retain
these files unless separately cached; this change does not alter workflows.

Both modes reuse existing complete-source-XOR certification and Gaussian
elimination for inputs up to 2,000 variables / 12,000 clauses. Existing Gaussian
row limits apply. SAT witnesses are checked against the original CNF. UNSAT
results still need external certification for a verified benchmark table.
Original clauses, locked reasons and low-LBD learned clauses retain their guards.
The active C7 learned-count accounting is corrected after deletion.

The existing PHP workflow generator now includes both modes. Its comparison
list remains unchanged; no workflow is dispatched by the compile script.
The baseline dispatch remains available. The new modes use reusable 1-UIP marks
and timestamp LBD counting; successful internal checks avoid temporary string
allocation. Persistent memory carries parameters, never assignments or clauses
from a different formula.

Validation: the selftest checks 640 small SAT/UNSAT cases against exhaustive
truth-table enumeration, validates original SAT witnesses, tests memory reload
on pigeonhole formulas and checks fixed-seed decision/conflict reproducibility.
This is correctness/regression validation, not a claim of superiority over
Kissat or CryptoMiniSat. Tune on separate training formulas; freeze the memory
snapshot for holdout comparisons and report all seeds, timeouts and PAR2.

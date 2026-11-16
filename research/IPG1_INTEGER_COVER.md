# IPG1 — Integer configuration cover, experimental

## Theorem (source-clause exact-cover obstruction)

Let the original CNF contain mutually disjoint three-selector at-least-one clauses
for jobs j, together with all three pairwise at-most-one clauses for each job.
Each satisfying assignment must assign every job to exactly one of three machines.

For machine m, collect only original all-negative clauses consisting of selectors
belonging to machine m. Such a clause forbids a particular set F of jobs from
being assigned together to that machine. Define A_m to be the set of subsets
that contain none of those source-grounded forbidden F sets.

If no three admissible sets A_1, A_2, A_3 can be pairwise disjoint and
partition all jobs, the ORIGINAL CNF is UNSAT. This is a sound sufficient
condition because every satisfying assignment of the full CNF must also
satisfy the selected source clauses. Other clauses are ignored conservatively.

## Scope and complexity

- Exactly 3 machines; 3–15 jobs; no auxiliary variables; selected source ALO/AMO
  groups must be disjoint and cover all DIMACS variables.
- All forbidden configurations come directly from original negative source
  clauses. No comments, filenames or expected statuses are proof premises.
- Enumerates 2^n machine subsets and up to 3^n partition candidates.
  THIS IS EXPONENTIAL. No polynomial general PCMAX claim is made.
- Unsupported encodings, time-budget exhaustion, or feasible relaxed partitions
  return UNKNOWN, allowing the next stage to run.

## One native process, three proof routes

1. BDD capacity pre-gate: source-bound structural JSON plus independent
   weighted VeriPB3 proof verification.
2. IPG1 exact integer-cover gate: source-bound exhaustive certificate plus
   independent Python checker (NOT DRAT, LRAT or VeriPB).
3. If neither pre-gate settles the source: CDCL with residual SCC, producing
   DRAT for independent drat-trim verification or a fully checked SAT model.

IPG1 does not run a second SAT solver or a parallel portfolio. No files on
the main branch are changed. The old standalone targets are preserved.

Build: cmake -S . -B build && cmake --build build --target drnas-pcmax-mg7-ipg1

Run: build/drnas-pcmax-mg7-ipg1 input.cnf --mode core --time 5
  --pcmax-capacity --pcmax-budget-ms 100 --pcmax-certificate input.capacity.json
  --ipg1 --ipg1-budget-ms 400 --ipg1-certificate input.integer.json
  --residual-scc --proof input.drat

On IPG1 proof-kind output, independently check:
python3 research/ipg1_check.py input.cnf input.integer.json

## Test protocol and limits

Use the Petersen construction from the saved PCMAX counterexample with SHA-256
c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70,
plus small 3-machine SAT/UNSAT controls, PHP fallback and frozen PCMAX #44.
Tampered proof counters and altered CNF bytes must be rejected.

This is a developmental, nonblind benchmark. No comparative verified PAR2
or completeness claim is justified. Next improvement: standard pseudo-Boolean
proof generation for integer cover conflicts and broader encoding recognition.

# DRNAS NP Lab v0.7 — NeuroFlow certified Horn front-end + CaDiCaL CDCL

**Status:** experimental, no claim of general SAT superiority.

Workflow: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-np-v07-cadical.yml

## Motivation and engineering change

Our previous v0.6.2 had ~2.47x speedup on externally untrained,
*manufactured* SAT renamable-Horn controls, but v0.6.3 failed to
accelerate actual third-party circuits/software CNFs. The older fallback
was Python DPLL, and many external problems timed out.

Version 0.7 switches to a **real CaDiCaL CDCL executable** installed
from Ubuntu's package. All non-Horn inputs are given to the same binary
in both arms using the exact same original CNF bytes.

### Mode A: baseline

`cadical --no-colors original.cnf`; return its SAT/UNSAT/UNKNOWN
status. Parse and verify any SAT assignment against the original CNF.

### Mode B: NeuroFlow + CDCL

1. If globally disabled or trivially too small, pass the same CNF
   directly to CaDiCaL, with effectively zero additional feature work.
2. Otherwise parse original DIMACS inside measured wall time, compute
   cheap sign frequency and unit-clause gate from frozen v0.6.2
   thresholds.
3. If promising, count clauses not Horn after majority-polarity flips.
4. If already Horn, solve Horn exactly; otherwise attempt exact
   renamable-Horn 2SAT recognition with bounded time and pair count.
5. For proven Horn formula, use the mathematically equivalent Horn
   solver, reverse polarity flips and **verify the satisfying model**
   against the original formula. UNSAT conclusions are checked with
   independent CryptoMiniSat when reference finishes.
6. On rejection, failed recognition or timeout, give the exact
   unchanged original CNF to CaDiCaL.

The Horn branch bypasses CaDiCaL only after a mathematically valid
equivalence proof; this is a **certified solver-selection front end**,
not yet a universal CNF simplifier which always feeds residual clauses
into CDCL. We must not misdescribe it as such.

### Comparability

Both arms use the exact same CaDiCaL binary/build, same run environment,
same original CNF, and same per-attempt wall clock budget. Timings
include subprocess startup, input parsing inside the policy,
preprocessing, witness processing and checks. The Python orchestration
still adds noise, especially for trivial cases.

Every case is run in 3 counterbalanced repeats; all individual times
and status codes recorded. Speed summaries use only matched, completed
pairs and display timeouts and coverage, avoiding survivorship bias.

## Corpus

- 60 preselected external, already published cases in pinned versions
  of Tractables/cnfs and Byt-wyze-technology/sat-instances-library:
  circuit SAT, software configuration SAT and third-party synthetic SAT.
  Prior v0.6.3 used these same files, but **v0.7 hyperparameters are
  frozen from v0.6.2 before their use**, so this is a backend comparison,
  not a new untouched holdout claim.
- 36 *new constructed* positive/negative controls: 12 SAT
  renamable-Horn, 12 UNSAT Horn with explicit contradiction and
  12 near-Horn, clearly separated from external natural datasets.
- CryptoMiniSat checks SAT/UNSAT independently (timeout recorded
  separately), while SAT witnesses in every solver path are checked
  against the original clauses.
- CaDiCaL from Ubuntu 24.04 (normally 1.7.4) and CryptoMiniSat both
  run inside one pinned GitHub Actions job.

## What matters

We only establish real benefit if the **same CDCL backend preceded by
NeuroFlow** wins on independent natural problems after charging all
feature costs, with equivalent solved counts and correct models.
Specialized speedups on the constructed controls are useful engineering
evidence but not a generalized SAT discovery or P vs NP result.

## Next improvements if evidence supports them

- Move the first inexpensive filter into the existing DIMACS parser,
  eliminating duplicate scans.
- Add safe polarity/pure-literal preconditioning with an explicit model
  reconstruction trail, and compare *identical backend with transformed
  vs untouched CNF*. This will truly pass useful information to CaDiCaL.
- For UNSAT claims use independently checkable proof logging when
  transform chains are introduced; no policy confidence is a SAT proof.

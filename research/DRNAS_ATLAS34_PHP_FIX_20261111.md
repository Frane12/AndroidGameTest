# DRNAS ATLAS34: PHP substructure fix

Date: 2026-11-11. Isolated experimental branch only.

## Root cause and algorithm
The ATLAS33 exact PHP gate inspected *all* all-positive CNF clauses as a
single family. Unrelated positive clauses prevented recognizing a valid
PHP-UNSAT subformula, even when all required positive at-least-one and
negative binary at-most-one clauses were present in the original CNF.

ATLAS34 keeps the previous exact detector and bounded root unit
simplification, but on a miss it:
1. Buckets candidate original positive clauses by width (2..64).
2. Builds a graph linking positive groups when original negative binary
   exclusions join variables belonging to different positive groups.
3. Separates connected components and rejects ambiguous variable reuse.
4. For every candidate component, calls the **unchanged exact PHP checker**
   on the selected positive clauses and original negative exclusions.
5. Emits theorem-UNSAT only on an exact complete pigeonhole contradiction
   (pigeon count > hole count, each selected pigeon has a positive
   at-least-one clause, each hole has all cross-pigeon exclusions).
6. Falls back to the original native V23 solver otherwise.

This procedure is conservative and may miss more elaborate encodings. It
never rewrites original CNF or guesses UNSAT from a statistical pattern.
Additional unrelated clauses can only strengthen an already contradictory
subformula; original SAT/UNSAT logic remains correct.

### Proof and limitations
This is an independently checked **structural theorem certificate**,
not LRAT/DRAT. For reported ATLAS34 theorem-UNSAT, Python independently
reconstructs a PHP subformula from original CNF under sound unit
propagation and checks the mathematical pigeonhole contradiction.
Theorem and unverified CDCL UNSAT remain separate classes.

## Reproduction
- Generator: `research/drnas_atlas34_regression.py`
- Native C++: `research/drnas_atlas34_php_native.cpp`
- Independent verifier: `research/drnas_atlas34_php_verify.py`
- Five selftests: `research/drnas_atlas34_selftest.py`
- GitHub Actions: `.github/workflows/drnas-atlas34-php-substructure.yml`

Matched: 52 SHA (36 deterministic generated sources at indices 820..831,
plus 16 nonblind SATLIB regression/extension SHA), 4 arms (native V23,
ATLAS33 PHP, ATLAS34 subset PHP, Kissat), 2 repeats, one logical CPU,
15-s cap, 416 trials. Every generated PHP test is extended with an
independent always-satisfiable 3-variable positive clause; half of the
PHP cases also use unit-definitional encoding. Thus ATLAS33's known
false negatives are challenged without modifying frozen original SHA
or the original SATLIB corpus.

SAT on original CNF requires a verified witness. UNSAT from Kissat or
the fallback CDCL is not independently LRAT-certified. Reported PAR2
counts a reported UNSAT as solved, while a strict certified-only PAR2
would penalize those; these measures must never be conflated.

## What this does NOT fix
SATLIB UF250/UUF250 CDCL speed regressions are not PHP substructure
detection misses. On those cases, the PHP gate correctly invokes
DRNAS fallback. A separate instrumentation and solver-search benchmark
is needed to address decisions, restarts, LBD, BCP and clause deletion.

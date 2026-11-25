# PCMAX conference validation — protocol v1
Frozen structural implementation: 466a5fa3a974304f710482ea4f403dab389319e2 (SCALE4).
No changes to detector or main. This protocol follows the scientific presentation feedback of Prof. Alan Jović (22 Nov 2026); it does not claim his endorsement or external replication.

## Research questions
RQ1: Can a raw CNF detector recover source-proven Hall deficits on previously unrun instances?
RQ2: What are its coverage, end-to-end cost and failure boundaries relative to general SAT and specialized methods?
RQ3: Does evidence generalize to independently sourced scheduling instances and other encodings?

## Cohorts
A: 100 fresh synthetic cases from a predeclared generator, 40 planted Hall UNSAT, 40 feasible, 20 UNSAT with cross-slot decoys. Fresh seeds generated after code freeze, recorded along with exact CNF hashes. This is a synthetic holdout, NOT independent external validation. Decoy UNKNOWN is allowed; any incorrectly certified UNSAT is a critical failure.
B: Original externally authored CNFs, independently selected and deduplicated by SHA-256 against all development runs; include SAT, UNSAT, open cases, multiple encodings and difficult non-Hall examples. Selection by independent evaluator preferred. Do not tune after release of this manifest. Report separately; not yet collected.
C: Public scheduling sources (e.g. JSPLIB) with fixed encoding, multiple deadlines and explicit source hashes. FT06 already used in development, so not a holdout. Report raw-CNF vs structured-input baselines separately.

## Rules
One logical CPU per timed process, default native settings, three paired repetitions for definitive study (initial pilot one repetition), same input bytes, fixed caps. Report coverage, UNKNOWN/timeouts, PAR-2 with unresolved/uncertified = 2*cap, proof sizes and verification times separately; never use a fast UNKNOWN as a solve. For pure DRNAS, no CDCL fallback. SAT models must satisfy all original clauses. UNSAT certificates checked against original input; SCALE4 custom source-bound checker is not standard VeriPB. Separate standard-proof export and independent reproducibility remain required. Keep solver-reported and certified metrics separate. Never omit failures.

## Existing evidence
SCALE4 regression run 45301885213: 8 planted UNSAT source-certificate checks, 8 SAT and 8 decoy UNKNOWN controls. SCALE7 mixed-width VeriPB run 45344803833 must be audited separately, not used to imply SCALE4 standard proof coverage. Public FT06 run 45345607598: pure native clique UNKNOWN for both deadline 54/55 while CP-SAT solves both; three repetitions. Include in discussion.
## Paper structure
Motivation and scope; related work (Hall matching, cardinality extraction, SAT preprocessing, PB/CP-SAT); explicit gap (testable claim about source-bound reconstruction from raw CNF, not novelty of Hall's theorem); research questions; conceptual pipeline and diagrams; formal method and proof; preregistered experiment; results; discussion including negative cases; conclusion; appendix with reproducible manifests. External reviewer has not verified the method.

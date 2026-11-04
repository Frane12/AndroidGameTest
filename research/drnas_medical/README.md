# DRNAS Medical v0.1 — SAT for computational biology (research only)

**Goal.** Test whether DRNAS SAT structure recognition (including certified R108 XOR reasoning) offers measurable computational benefit on mathematically defined problems relevant to systems biology.

**Scope warning.** v0.1 uses **fully synthetic**, biology-inspired Boolean networks. They are not published gene-regulatory models, patient data, drug candidates, or clinical evidence. No claims about a disease or treatment can follow from these timings. The test only prepares a rigorous bridge into bioinformatics.

## First question

Can DRNAS R108 help the SAT search for fixed points and genuine length-2 cycles in synchronous Boolean regulatory networks **after including the full preprocessing cost**?

A node's next value is determined by a Boolean rule: copy, inhibition (AND-NOT), OR, NOT, or XOR. We encode the transition relation into DIMACS CNF using exhaustive local truth tables. A length-2 cycle is required to visit two distinct states. This tests structural interactions rather than creating fake clinical data.

## v0.1 protocol

1. Run `python3 research/drnas_medical/boolean_models.py selftest`. Exhaustively verify all state-transition assignments on 4-node models across five families and periods 1/2 (1360 checks).
2. Generate 30 deterministic cases with `generate`: five families x 3 sizes (6, 10, 20 nodes) x 2 periods (fixed point / exact 2-cycle). Every CNF gets a SHA-256 and rule-level manifest.
3. For networks up to 12 nodes, independently enumerate state transitions and record the expected SAT/UNSAT status. Larger cases are `UNKNOWN` until independently solved.
4. Compare CaDiCaL 1.9.5, Kissat 4.0.4, and MiniSat 2.2 via the same PySAT package. Record repetitions, independent witness verification, time cap and PAR-2.
5. Run R108 selective prepass on six structurally diverse small cases, and compare `R108 + CaDiCaL` against bare CaDiCaL on identical original CNFs. Charge **all** preprocessing time; do not claim improvements from prep-free solve times.
6. Fail closed for invalid SAT witnesses, mismatched expected labels, incorrect R108 source digest, and cross-solver disagreements. Store CSV, JSON and input CNFs as an Actions artifact.

**Interpretation:** A change in solve time here establishes only a property of this synthetic workload, not a speedup in drug development. A prepass that adds overhead without advantage is a negative result worth preserving. A SAT model must be checked; UNSAT must be cross-validated and eventually proof-checked before strong claims.

## Follow-on stages

- **v0.2 Real biological models:** identify and license-check specific published logical gene-regulatory models in [Biodivine Boolean Models](https://bbm.sybila.fi.muni.cz/), [Cell Collective](https://research.cellcollective.org/) or [BioModels](https://www.ebi.ac.uk/biomodels/); capture model accession, publication, source hash, license, rule format and immutable snapshots. Build an SBML-qual/BNet importer with equivalent-transition checks. No user/patient data.
- **v0.3 Representative tasks:** use attractor/fixed-point enumeration, intervention constraints and network reachability with biologically justified semantics; check domain-expert interpretation.
- **v0.4 External blind holdout:** separate development and unseen biological model families; identical hardware, pinned solvers and versions, repeated randomized order, all timeouts counted, zero reuse of training models.
- **v0.5 Broader computational science:** only after the previous milestones, evaluate appropriate molecular constraint or experimental-design problems. A faster SAT solver is only one part of a validated discovery workflow.

## References

- [Dubrova and Teslenko: SAT-based attractor finding](https://pubmed.ncbi.nlm.nih.gov/21778527/)
- [Boolean-network attractor algorithms review](https://doi.org/10.1016/j.csbj.2022.05.027)
- [Biodivine Boolean Models](https://bbm.sybila.fi.muni.cz/) (dataset to audit for future real-data trials)
- [CoLoMoTo model formats](https://colomoto.github.io/) (SBML qual interoperability)
- [PySAT](https://pysathq.github.io/) (baseline solver interface)

## Command summary

```bash
python3 research/drnas_medical/boolean_models.py selftest
python3 research/drnas_medical/boolean_models.py generate --out medical-results/cnfs
python3 -m pip install python-sat==1.9.dev18
python3 research/drnas_medical/benchmark.py --dir medical-results/cnfs --cap 8 --repeats 2 --r108-limit 6
```

The `benchmark.py` script requires the existing `research/r108_hidden_xor.py` and its dependencies from the parent R108 branch. The workflow writes outputs as Actions artifacts and does not modify existing SAT development versions.

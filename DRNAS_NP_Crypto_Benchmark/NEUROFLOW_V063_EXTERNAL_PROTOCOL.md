# DRNAS NeuroFlow v0.6.3 — EXTERNAL AUTHORS, ZERO-SHOT

Workflow: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-neuroflow-v063.yml

## Why this test exists
Earlier v0.6.2 measured up to 2.47x median speed-up on constructed SAT renamable-Horn controls, but proved no general SATLIB advantage. The present study specifically attempts to **falsify/generalize** that limited claim using independently existing CNF files from third-party authors.

## Sources (not copied from our prior work)
1. [Tractables/cnfs](https://github.com/Tractables/cnfs): LGSynth89 logic-synthesis circuits (12); ISCAS85b combinational hardware (8); ISCAS89 sequential hardware (12); real-world software product-line feature model constraints (12) used as the SAT abstraction of model-counting CNFs. Upstream library gathers these independently existing practical benchmark families.
2. [Byt-wyze-technology/sat-instances-library](https://github.com/Byt-wyze-technology/sat-instances-library): a different author's third-party synthetic SAT benchmark instances (16). These are separately labeled and **not** claimed to be industrial real-world problems.

Exactly 60 file choices are made with documented deterministic RNG seeds and source-byte size limits **before any solver is consulted**. Lists are retrieved from pinned upstream commits, and each file's original SHA256 and canonical equivalent DIMACS SHA256 are preserved. The test does not contain any of DRNAS's own manufactured Horn controls or SATLIB formulas.

The script downloads original files in a GitHub Action without adding them to the DRNAS repo. Only SHA/provenance metadata and benchmark results go into the run artifact.

The LGSynth/ISCAS circuit datasets are circuit-encoding SAT abstractions; feature-models are counting-problem formulas interpreted as ordinary SAT constraints. A successful result would not imply improved model counting or solving physical circuits directly.

## Method
- **ZERO-SHOT frozen policy** from v0.6.2: `enabled=true, n>=30, minority in [.13,.28], unit share<=0, Horn defect<=.10, 12ms exact 2SAT cap`. No hyperparameter tuning on this external data.
- Independently obtain reference SAT/UNSAT from CryptoMiniSat 5.11.15 with 7s timeout per instance.
- On every instance, three counterbalanced in-process wall-clock comparisons of original DRNAS DPLL, frozen NeuroFlow adaptive, forced Horn detector, and disabled old v0.6 (which still calculates 17 costly features).
- Inference overhead counted. SAT assignments verified against the exact DIMACS formula in DRNAS.
- Cases where CryptoMiniSat cannot decide, or where reference/DRNAS runs time out, are reported separately. Median/mean gains use only matched completed, independently validated pairs; solved rate and timeout count must be reported alongside gains.
- No generic SAT speedup claim unless speed and completion improve on independent external families.

## Limitations
The chosen files are size-bounded and biased toward smaller examples that fit a Python baseline. Feature-models are selected from the first 1000 GitHub directory entries if the API truncates listings; samples are not uniformly drawn from the entire collection. Sources are **two publishers**, not five independent maintainers; five are separate benchmark families. Any source with parser/canonicalization problems is recorded, not silently replaced. Compare against CryptoMiniSat only for outcome correctness, not wall-clock speed (external process startup vs in-process Python).

All code and data paths are on an experimental branch. The prior working v0.6.2 remains unchanged.

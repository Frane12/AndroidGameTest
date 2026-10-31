# DRNAS NP Lab v0.5 — frozen structural NeuroFlow experiment

Goal: test whether **cheap structural evidence**, not retrospective speed alone,
can improve exact SAT representation selection.

- Training: 160 SATLIB problems from original deterministic SATLIB-160 run,
  plus 72 generated controls (renamed Horn SAT/UNSAT and near-Horn SAT).
- Held out: 160 SATLIB examples selected by a new seed and verified **not**
  to occur either in original SATLIB-160 or the prior v0.4 unseen set;
  plus 72 new controls from disjoint generation seeds.
- Train-only features: majority-polarity-Horn defect, estimated in O(total literals).
- Candidate decisions: skip Horn transformation, exact direct Horn if every
  clause becomes Horn after simple sign orientation, or full renamable-Horn 2-SAT.
- Freeze one per-size threshold using paired training times, with an explicit
  utility penalty and default-off when there is no convincing evidence.
- Heldout: compare v0.2 baseline, costly always-probe, and frozen v0.5
  selection, counterbalancing program order and repeating each case 3 times.
- Time includes feature extraction, probing, fallback and solving, **not**
  per-process Python startup (all runs are in one benchmark process).
- Correctness: model checking against original CNF, plus actual CryptoMiniSat
  5.11.15 checks on all 160 heldout external problems.

Original SATLIB sources: https://www.cs.ubc.ca/~hoos/SATLIB/benchm.html

Caution: this is an evaluation of scheduling known exact algorithms, not
a proof of a new class of efficient NP algorithms. Controls are constructed.
Training labels are never exposed on heldout policy decisions; all selected
thresholds are frozen before the test starts.

GitHub Actions output: nf05_results/{train_samples,heldout,summary}.csv,
frozen_policy.json, protocol.json, both SATLIB manifests, canonical CNFs.

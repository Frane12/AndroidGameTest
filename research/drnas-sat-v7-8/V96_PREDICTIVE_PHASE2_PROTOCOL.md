# DRNAS V9.6 Phase II — prospective prediction (frozen 2026-10-31)

## Hypothesis
CNF-only features capturing strong/weak phase majority coherence, clause coverage, and pair reuse may predict when sparse (strong-only) initial phase hints beat broad (>=15% imbalance) hints. The algorithm predicts before any conflicts. This does NOT prove clause-learning mediation.

## Training
Original 22 SATLIB formulas (four 225/250-var SAT/UNSAT families), official data artifact 13053713581 / workflow 41231448657. 330 experimental runs. SHA256 checked. Fourteen formula-level statistics are calculated strictly from original CNF; no label, filename, timing, or first-256 outcome enters features. StandardScaler + Ridge(alpha=10) on clipped log(Broad/Sparse runtime) in [-1.5,1.5]. Frozen full-fit coefficients and normalization stored inline in v96_predictive_holdout.py. Select sparse if forecast > log(1.30), otherwise broad.

## Preliminary leave-one-formula-out (retrospective)
14/22 winner predictions; sum chosen per-CNF median times 17.04826s, compared with always sparse 17.08426s, always broad 17.48661s, plain CaDiCaL 16.74643s. Approx 0.21% vs sparse, no convincing gain. Model design explored on prior data: NOT unbiased performance evidence.

## Prospective test
SHA-sorted six unscreened source members from EACH of four unchanged 100-file SATLIB archives, excluding ALL 20 CaDiCaL-screened members per archive from historical artifact. Salt: drnas-v96-satlib-unscreened-20261031-precommitted. 24 unique source members, no outcome screening or choice based on predicted outcome. Same public SATLIB families, disjoint CNFs; not an independent external SAT Competition test.

Pinned CaDiCaL 3.0.1 at c60730422e758ef1cebe7aeddf2dda31c996bf04. Compare ca_plain, frozen v92_sparse, frozen v92_structural (broad), and v96_predict. Three repeats per formula, 288 actual runs, 4-second wall cap, PAR2 timeout penalty=8s, one CPU per shard, randomized order. Prediction includes Python feature extraction in measured wall time. Fail closed on missing/corrupt data and contradictory SAT/UNSAT labels.

Model and code frozen BEFORE benchmark. No tuning based on holdout; no world-record, P=NP, or universal improvement claim without independent validation and proof certificates.

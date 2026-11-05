# DRNAS R135 – structural portfolio pilot

Frozen R134-derived rule: sample <=128KiB/2000 clauses; use CaDiCaL if binary ratio <0.20 and Horn ratio <0.50, else Kissat. Compare paired against pure Kissat, pure CaDiCaL and frozen R118 on new SHA-disjoint real SAT CNFs. Include detection in 15s cap and refuse promotion without independent UNSAT certification. Branch experimental; no changes to main/frozen baselines.

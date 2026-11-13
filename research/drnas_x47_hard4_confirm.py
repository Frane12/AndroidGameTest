#!/usr/bin/env python3
"""X47 LONG HARD4: fixed, independent 4-SAT source-family confirmation.

Use the existing source/solver/certificate harness unchanged, replacing
ONLY the declared synthetic family cohort by hard planted 4-SAT. Distinct
generator indices (>=1200000) avoid all earlier train, validation and
medium-holdout samples. This independent 4-SAT cohort was motivated by the
known large variance within the preceding multi-family exploratory run,
so it is an *exploratory replication*, not a globally blind holdout.
"""
import drnas_x47_long_bench as B

if __name__=="__main__":
    B.SYNTH_FAMILIES=("critical4_planted",)
    B.main()

#!/usr/bin/env python3
"""X4.7 FAST5 independent Pigeonhole UNSAT cohort.

Reuse the identical X4.7 native harness, frozen cost/guard policies, witness
and strict-PHP-core certification, paired arms and PAR2 computation.
Only the synthetic cohort family selector changes; no solver modifications.
"""
import drnas_x47_long_bench as bench

if __name__ == "__main__":
    bench.SYNTH_FAMILIES = ("php_structural_unsat",)
    bench.main()

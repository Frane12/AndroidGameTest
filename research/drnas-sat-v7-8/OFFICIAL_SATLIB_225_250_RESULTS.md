# DRNAS SAT — OFFICIAL SATLIB 225/250, medium difficulty, paired benchmark
Date: 2026-10-31
Successful run: https://github.com/Frane12/AndroidGameTest/actions/runs/41231448657
Official SATLIB source: https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/

## Protocol
Four original published SATLIB archives: uf225-960, uuf225-960, uf250-1065, uuf250-1065.
20 deterministic SHA256-sorted original files per archive screened using ONLY plain CaDiCaL 3.0.1, 3-second cap.
Eligible cases had baseline times 0.08–2.70 seconds and agreed with official group SAT or UNSAT truth.
6/6/6/4 cases selected in order of proximity to 0.6 seconds = 22 official medium examples.
22 examples x 3 time repetitions x 5 frozen modes = 330 final solver calls; additional 80 baseline screens.
Mode order randomized per case/rep; same CPU affinity, same instrumented pinned CaDiCaL version.
Four-second final timeout with PAR2=8 second penalty. Every selected case and unsolved run included.
Original downloaded SATLIB archive bytes, file-member names, original and normalized SHA256 hashes, screen data and raw performance rows retained in artifacts.
Selection bias: selecting on plain CaDiCaL baseline runtime may favor DRNAS relative to a completely random sample; ratios and totals are descriptive.
Experimental run does not compare to SAT Competition 2026 entrants and is NOT a world record.

## Final results: sum of per-problem medians, seconds (smaller is better)
- plain CaDiCaL: 16.74643 s — best overall
- DRNAS v9.2 sparse/strong hints: 17.08426 s (~2.02% slower than CaDiCaL)
- DRNAS v7.6 without initial hints: 17.29641 s (~3.28% slower)
- DRNAS v9.2 structural selector: 17.48661 s (~4.42% slower)
- DRNAS v7.6 guided: 17.53159 s (~4.69% slower)

## Best individual observed gain
SATLIB archive uf250-1065, source member ai/hoos/Shortcuts/UF250.1065.100/uf250-084.cnf, 250 variables / 1065 clauses (SAT).
Plain CaDiCaL median 0.49667s; DRNAS v9.2 sparse hints median approximately 0.01245s = 39.88x.
All three sparse hint attempts 0.01245, 0.01241, 0.01248s (timing repeats; mode likely does not use seed for stochastic variation).
Compare original DRNAS v7.6 without hints median 0.2358s: new sparse hints ~18.9x faster on this single case.
All five solvers returned SAT on all three repeats. A strong instance-level gain, not a solver-world-record or proof of generalization.

Further large examples: uf225-960-12 CaDiCaL 0.4003s vs frozen v7.6 no hints 0.0742s (5.40x);
uf225-960-19 0.7604 vs 0.2319 (3.28x); uf225-960-07 CaDiCaL 0.3070 vs v9.2 sparse 0.0972 (3.16x).

## Split by SAT/UNSAT, seconds
Satisfiable uf225: CaDiCaL 2.516, sparse 2.364 (~6% lower).
Satisfiable uf250: CaDiCaL 2.994, sparse 2.522 (~15.8% lower).
Unsatisfiable uuf225: CaDiCaL 3.930, sparse 4.065 (~3.4% worse).
Unsatisfiable uuf250: CaDiCaL 7.307, sparse 8.133 (~11.3% worse).
TOTAL SAT ~CaDiCaL 5.510s vs sparse 4.886s (~11.3% faster).
TOTAL UNSAT ~CaDiCaL 11.237s vs sparse 12.198s (~8.6% slower).
On meaningful cases, sparse hints: 4 practical wins >1.25x and 4 regressions <0.8x compared to CaDiCaL.

## Correctness and limitations
No contradictory SAT/UNSAT answers or execution errors detected; official SATLIB SAT/UNSAT labels are also consistent.
SAT witnesses checked in C++; UNSAT refutations not independently checked with DRAT/LRAT.
Timing repetitions with different passed seeds do not necessarily imply independent solver paths; deterministic phase modes may ignore those seeds.
Input screening 80 cases and final 22 are synthetic random 3-SAT, not industrial or 2026 Main Track instances.
Moderate threshold is defined on plain CaDiCaL screening and excludes 58 of 80 from final evaluation; report screen.json for selection transparency.
Do not claim a world record. Most useful next research: diagnose the stable 39.88x phase-path change and investigate why sparse hints lose on larger UNSAT instances, then preregister gate and test on separate official medium-hard families.

Artifacts: run -> DRNAS-OFFICIAL-SATLIB-225-250-FULL-AUDIT -> summary.md, all_raw.csv, details.json, screen_all.json and source metadata.

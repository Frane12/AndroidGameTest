# DRNAS R146c — selector cost guard / Horn misrouting

Based on R135 shard 4 and shard 6 paired logs (manifest SHA256 619665dd5f4ba6680b11200a63ac77ecc706c9897317b5452dbf22a82ef4b787).

## Observations
- Official SAT formula ac6db654...: horn_ratio=0.953681, binary_ratio=0.0; R135 selected Kissat and timed out twice at 15s, while CaDiCaL solved in 10.940619s and 10.938699s.
- Official SAT formula 509361302...: R135 scan 0.027302/0.028621s, total 0.035044/0.036411s; Kissat solved in 0.005474/0.005562s.
- Shard 4 external XOR aa0cdb92...: R135 selected CaDiCaL, 0.071122s vs Kissat 0.025272s (repeat 0).
- R135 full/incomplete scans may cost >0.1s or >0.28s on large official formulas. Scanning alone is not evidence of benefit.

## R146c experimental change request
1. Replace unconditional full-CNF scan with bounded deterministic prefix/stratified sampling. Hard cap by clause count and monotonic clock; record sampled fraction and detection wall time.
2. Explicitly track decision confidence. If sampling is incomplete/ambiguous, use frozen default solver rather than interpreting sampled Horn ratio as a reliable global statistic.
3. Do not route to Kissat solely on high Horn ratio. Treat high Horn + zero binary ratio as uncertain; learn threshold on training data only.
4. Use estimated expected solver gain > scan cost + safety margin as a necessary condition for switching; otherwise no selector overhead.
5. Preserve R135 as frozen comparator. R146c is experimental and must not touch main/frozen branches.
6. Validate SAT/UNSAT correctness and paired time on SHA-disjoint holdout with Kissat, CaDiCaL, R118, R135, R146c, same hardware/seeds/caps. Report solved, PAR-2, regressions, median and selector overhead separately.
7. Avoid claim of improvement until complete matched runs; do not tune thresholds using the 400-instance blind evaluation cohort.

Status: design specification committed; not yet an implemented solver or launched benchmark.

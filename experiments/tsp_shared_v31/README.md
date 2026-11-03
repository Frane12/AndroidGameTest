# DRNAS TSP v3.1 versus LKH-3

External benchmark on identical **TSPLIB EUC_2D** instances. This is a dedicated experimental branch; the default branch is not modified.

- Cities: 2,000 and 5,000; seeds: 0, 1, 2; DRNAS: 64 **virtual** agents (not 64 physical cores).
- LKH-3: genuine [cerebis/LKH3](https://github.com/cerebis/LKH3) clone compiled in CI, one run with MAX_TRIALS=3 and TIME_LIMIT=6.
- DRNAS: independent, shared-best-route, batched Shared Lookup, 6 seconds timed search each.
- Same EUC_2D coordinates and rounded edge-cost matrix across methods. CSV includes reported route lengths and wall time.
- **Fairness warning:** DRNAS search time and preprocessing are separate fields, while LKH's solver startup/preprocessing are part of its wall time. Do not claim equal elapsed end-to-end time without comparing total_seconds. One LKH run is not proof of optimality.
- The LKH-3 source is **not** embedded in this repository due to its research-use licensing. GitHub Actions fetches it during the job.

Workflow: [DRNAS TSP v3.1 vs LKH-3](../../.github/workflows/drnas-tsp-v31-lkh.yml)

Artifacts: `tsp_world_compare.csv`, LKH logs and tour outputs. On failures consult the workflow logs; no external results are imputed.

Local re-run: install numpy, scipy, numba and a compiled genuine LKH-3 binary, then run:
```bash
PYTHONPATH=experiments/tsp_shared_v31 python experiments/tsp_shared_v31/compare_lkh.py --cities 2000 5000 --seeds 0 1 2 --seconds 6 --lkh ./LKH3/LKH --out tsp_world_compare.csv
```

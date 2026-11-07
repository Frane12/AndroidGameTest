# DRNAS New Horizon SAT R4b — independent-seed repeat confirmation

Purpose: Re-test the promising early R4b local gains without changing
R4b code or tuning its thresholds after seeing results.

## Design

- 48 **different** SHA-frozen CNF sources using new deterministic seeds
  from five **known generator families**. This is **NOT** an independent
  external industrial blind holdout.
- 12 source-complete pure XOR3 CNFs, 12 small 2-SAT CNFs, 8 large 2-SAT
  CNFs, 8 late-disproof CNFs (first 96 clauses misleading) and 8 general
  planted 3-CNF controls.
- Five repetitions per original CNF; four frozen policies:
  clean CaDiCaL, original R4, R4b pure-only, R4b hybrid.
  **48 × 5 × 4 = 960 paired runs.**
- Original CNFs and native CaDiCaL 2.1 executable are SHA-pinned.
  Each policy sees identical source and cap; policy order randomized
  deterministically within repetition.
- Every scan and exact source-proof check is included in elapsed time.
  PAR2 per case uses the identical cap.
- The 4-shard audit rejects missing runs, mismatched source SHA, wrong
  known SAT/UNSAT labels, contradictory answers and incorrect PAR2.
- Exact SAT models are checked on original source; native CDCL UNSAT
  lacks independently replayed LRAT/FRAT.
- Sub-millisecond results require replication on dedicated stable CPUs.

## Questions

1. Does source-complete XOR3 stay >1x faster across new seeds and repeats?
2. Does small source-certified 2SAT offset one-pass verification cost?
3. Does abstention rescue large 2SAT where R4 paid Python SCC overhead?
4. Is R4b safer than R4 on late deceptive clauses?
5. What is total cost including all fallback screening?
6. Are any gains transferable to unseen hard industrial SAT? **Not
   answered by this known-generator synthetic confirmation.**

R4b original development audit: run 42326199590.
Fresh-seed confirmation workflow: drnas-new-horizon-r4b-repeat-confirm.yml.

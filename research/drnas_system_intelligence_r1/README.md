# DRNAS System Intelligence R1

**Goal:** understand a hidden system by observing and intervening, then steer unseen initial states toward exact targets. Educational research only, **not** a Bitcoin private-key recovery tool.

## Dynamics
- Hidden state: two coordinates z in a finite field modulo prime p.
- Unknown reversible actuator B: z_next = z + B u (mod p).
- Unknown reversible sensor A: linear observations y = A z (mod p).
- Nonlinear stress case: v=A z; y=(v0+v1^2, v1) (mod p).
- Agent gets only sensor readings and may choose control vectors u. It does not receive A, B, or hidden states.

## Protocol
Two probes per system: (1,0), then (0,1). The two measured sensor differences give the unknown input-response matrix C=A B in the linear class. For new target y*, control u=C^-1(y*-y). Tests use 24 independently sampled systems per size and 48 held-out start/goal pairs per system.

Primes: 17, 31, 127, 509, 2039 (linear); 17, 31, 127 (nonlinear).

## Results (local R1 reproducible seed)
| class | p | learned | naïve | random | shuffled model |
| --- | ---: | ---: | ---: | ---: | ---: |
| linear | 17 | 1152/1152 | 11/1152 | 4/1152 | 4/1152 |
| linear | 31 | 1152/1152 | 0/1152 | 3/1152 | 0/1152 |
| linear | 127 | 1152/1152 | 0/1152 | 0/1152 | 0/1152 |
| linear | 509 | 1152/1152 | 0/1152 | 0/1152 | 0/1152 |
| linear | 2039 | 1152/1152 | 0/1152 | 0/1152 | 0/1152 |
| nonlinear | 17 | 74/1152 | 3/1152 | 1/1152 | 6/1152 |
| nonlinear | 31 | 33/1152 | 0/1152 | 0/1152 | 0/1152 |
| nonlinear | 127 | 12/1152 | 0/1152 | 0/1152 | 0/1152 |

Success means exact hidden state and observable target. Controls are powerful modular vectors, not unit-only moves. For the linear class, success follows from standard black-box system identification: it is not a novel algorithmic breakthrough. The fixed linear response fails to generalize to state-dependent nonlinear observation, as expected.

All randomness uses fixed, independently SHA-256-derived streams for setup, calibration and holdout. The harness may inspect hidden state only to check correctness. The learner may not.

**Limits:** benchmark reports success and intervention counts, not GPU/CPU acceleration or asymptotic time complexity. The holdout is unseen starts/goals but uses known functional classes. Neither the system nor this experiment implements ECDLP or a method to recover Bitcoin private keys.

## Reproduce
```bash
python3 research/drnas_system_intelligence_r1/drnas_system_r1.py --systems 24 --targets 48 --out results
```
Outputs: summary.csv, summary.json, trials.csv. Python 3.10+ stdlib only.

## Next test R2
Adaptive local probing with feedback on unseen nonlinear environments, fixed total intervention budget, matched baselines and untouched holdout.

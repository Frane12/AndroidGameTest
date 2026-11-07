# DRNAS R20 — real native local learned-clause usefulness test

Native in-process R20 local gate and inverse control; no off-policy replay.
All 160 CNFs SHA-disjoint from earlier experiments; 3 repeats each.

| Fold | Strategy | PAR2 (s) | Δ vs monitor | 95% formula bootstrap CI | Selected | >2x regressions |
|---|---|---:|---:|---|---:|---:|
| random3_development | monitor | 128.956710 | +0.000% | [0, 0] | None | 0 |
| random3_development | r11_2048_50 | 135.393635 | -4.992% | [-14.12861907754681, 3.2661478370505357] | None | 5 |
| random3_development | r16_live50 | 130.570085 | -1.251% | [-3.0601441276527064, -0.03575400008510951] | None | 0 |
| random3_development | r20_local50 | 129.999735 | -0.809% | [-2.580391860610541, 0.28537279921315795] | 9 | 1 |
| random3_development | r20_inverse50 | 136.188894 | -5.608% | [-14.31122396363096, 1.5863788263960115] | 111 | 4 |
| random3_development | original_kissat | 129.006789 | -0.039% | [-0.3064273567747756, 0.16597740201455838] | None | 0 |
| random3_development | stable_v1531 | 129.240139 | -0.220% | [-0.36836083547512904, -0.08589845284486983] | None | 0 |
| random3_test | monitor | 97.424631 | +0.000% | [0, 0] | None | 0 |
| random3_test | r11_2048_50 | 92.210779 | +5.352% | [-4.949527274224209, 15.03399978955905] | None | 4 |
| random3_test | r16_live50 | 96.496137 | +0.953% | [-2.833670069384824, 6.451657517023828] | None | 1 |
| random3_test | r20_local50 | 97.619165 | -0.200% | [-0.6723942187586477, 0.13502134582479536] | 6 | 0 |
| random3_test | r20_inverse50 | 92.168886 | +5.395% | [-4.747096256186755, 15.303348069350221] | 108 | 3 |
| random3_test | original_kissat | 97.220150 | +0.210% | [0.02762048026837597, 0.42544692027004566] | None | 0 |
| random3_test | stable_v1531 | 97.590926 | -0.171% | [-0.40453697177598386, 0.04880271670034728] | None | 0 |
| community3_development | monitor | 5.281569 | +0.000% | [0, 0] | None | 0 |
| community3_development | r11_2048_50 | 5.268659 | +0.244% | [-6.791016025258998, 8.570351109298732] | None | 0 |
| community3_development | r16_live50 | 5.331579 | -0.947% | [-3.9701677047667463, 1.1719098198539144] | None | 0 |
| community3_development | r20_local50 | 5.350405 | -1.303% | [-3.448286172294216, 0.15476067119075773] | 3 | 0 |
| community3_development | r20_inverse50 | 5.221470 | +1.138% | [-5.869339770294069, 9.095299263716004] | 57 | 0 |
| community3_development | original_kissat | 5.247547 | +0.644% | [0.36061164706005344, 1.1604702603613255] | None | 0 |
| community3_development | stable_v1531 | 5.381836 | -1.898% | [-2.5282218021194254, -1.4083899626560463] | None | 0 |
| community3_test | monitor | 3.283062 | +0.000% | [0, 0] | None | 0 |
| community3_test | r11_2048_50 | 3.228451 | +1.663% | [-3.029500599422787, 6.076053918991232] | None | 0 |
| community3_test | r16_live50 | 3.218149 | +1.977% | [-1.660428368452859, 5.711714560801704] | None | 0 |
| community3_test | r20_local50 | 3.298370 | -0.466% | [-1.6423088454709225, 0.582161892749526] | 0 | 0 |
| community3_test | r20_inverse50 | 3.256211 | +0.818% | [-4.389190723408141, 5.5610168552049055] | 57 | 0 |
| community3_test | original_kissat | 3.265207 | +0.544% | [-0.13084492502079964, 1.3160608298764762] | None | 0 |
| community3_test | stable_v1531 | 3.349094 | -2.011% | [-2.8992061880293005, -1.334140570088066] | None | 0 |

The clause-reuse count is observational, not a proof of causal solver dynamics.
Primary claim requires a new random3_test benefit with formula-bootstrap CI >0.
UNSAT certificates were NOT independently verified.

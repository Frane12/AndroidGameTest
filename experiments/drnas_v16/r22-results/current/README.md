# DRNAS R22 prospective native SAT

R22 real native frozen clause-age/LBD/implication-role gate; NOT off-policy.
Same-binary comparisons; 160 fresh SHA-exclusive synthetic CNFs, 3840 true runs.
| Fold | Strategy | PAR2 s | Gain % | 95% formula bootstrap CI | Switches | >2x regressions |
|---|---|---:|---:|---|---:|---:|
| random3_development | monitor | 95.674053 | +0.000% | [0, 0] | None | 0 |
| random3_development | r11_2048_50 | 104.046799 | -8.751% | [-32.098344822253964, 8.964702840224579] | None | 3 |
| random3_development | r16_live50 | 101.114746 | -5.687% | [-29.56439658467582, 9.183149400713857] | None | 2 |
| random3_development | r21_inverse50 | 105.226577 | -9.984% | [-34.35193552218377, 7.835939743687818] | None | 3 |
| random3_development | r22_chain50 | 97.185646 | -1.580% | [-3.5248110565443866, 0.12443028046999824] | 12 | 0 |
| random3_development | r22_inverse50 | 103.467474 | -8.146% | [-33.03528705267083, 10.1509788701282] | 105 | 3 |
| random3_development | original_kissat | 92.241891 | +3.587% | [3.2014132941566547, 4.009491802416467] | None | 0 |
| random3_development | stable_v1531 | 92.646618 | +3.164% | [2.8073561220295984, 3.533801240815087] | None | 0 |
| random3_test | monitor | 85.827727 | +0.000% | [0, 0] | None | 0 |
| random3_test | r11_2048_50 | 86.824180 | -1.161% | [-16.75643537280261, 9.661244920530056] | None | 6 |
| random3_test | r16_live50 | 85.220977 | +0.707% | [-1.8733596446910754, 3.9602185101642693] | None | 0 |
| random3_test | r21_inverse50 | 86.150007 | -0.375% | [-14.967321129009397, 10.168365860491857] | None | 5 |
| random3_test | r22_chain50 | 86.426902 | -0.698% | [-6.460863528233492, 5.1328187070827305] | 18 | 1 |
| random3_test | r22_inverse50 | 85.713598 | +0.133% | [-13.263056886369167, 9.392561260850181] | 102 | 4 |
| random3_test | original_kissat | 82.585654 | +3.777% | [3.430635345790227, 4.297022103863497] | None | 0 |
| random3_test | stable_v1531 | 82.958592 | +3.343% | [3.0946005725267822, 3.6731954135204137] | None | 0 |
| community3_development | monitor | 6.613928 | +0.000% | [0, 0] | None | 0 |
| community3_development | r11_2048_50 | 6.118365 | +7.493% | [-11.382351502744037, 22.178808736204537] | None | 0 |
| community3_development | r16_live50 | 5.838051 | +11.731% | [-3.1992024414791005, 24.083553910657756] | None | 0 |
| community3_development | r21_inverse50 | 6.128614 | +7.338% | [-11.385636082869858, 22.475978222233206] | None | 0 |
| community3_development | r22_chain50 | 6.615641 | -0.026% | [-0.22508794506919122, 0.19388873126605435] | 0 | 0 |
| community3_development | r22_inverse50 | 6.131135 | +7.300% | [-11.958995487165321, 22.47754832960154] | 45 | 0 |
| community3_development | original_kissat | 6.124996 | +7.392% | [6.609096802337037, 8.52811117350455] | None | 0 |
| community3_development | stable_v1531 | 6.250375 | +5.497% | [4.983634317961286, 6.097983209230869] | None | 0 |
| community3_test | monitor | 5.191946 | +0.000% | [0, 0] | None | 0 |
| community3_test | r11_2048_50 | 4.875807 | +6.089% | [-6.074264943826196, 18.660199096923073] | None | 0 |
| community3_test | r16_live50 | 5.104985 | +1.675% | [-0.056843999556745614, 3.593873609704877] | None | 0 |
| community3_test | r21_inverse50 | 4.880488 | +5.999% | [-6.222715586327077, 18.586296936351403] | None | 0 |
| community3_test | r22_chain50 | 5.177764 | +0.273% | [-0.19108241649444568, 0.8941744486689838] | 0 | 0 |
| community3_test | r22_inverse50 | 4.884442 | +5.923% | [-6.166565640299376, 18.602009118399597] | 42 | 0 |
| community3_test | original_kissat | 4.792596 | +7.692% | [6.929119615082967, 8.606110648559712] | None | 0 |
| community3_test | stable_v1531 | 4.909921 | +5.432% | [4.4725750439447145, 6.326609517565831] | None | 0 |

Formula-level inference is exploratory; no causal law or official world record.
UNSAT result certificates NOT independently verified.

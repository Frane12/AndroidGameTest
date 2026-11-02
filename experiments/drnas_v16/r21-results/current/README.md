# DRNAS R21 prospective native SAT

R21 real native frozen clause-age/LBD/implication-role gate; NOT off-policy.
Same-binary comparisons; 160 fresh SHA-exclusive synthetic CNFs, 3840 true runs.
| Fold | Strategy | PAR2 s | Gain % | 95% formula bootstrap CI | Switches | >2x regressions |
|---|---|---:|---:|---|---:|---:|
| random3_development | monitor | 138.570273 | +0.000% | [0, 0] | None | 0 |
| random3_development | r11_2048_50 | 135.852772 | +1.961% | [-6.165068369299026, 11.322988345856883] | None | 2 |
| random3_development | r16_live50 | 136.011639 | +1.846% | [-2.8287590365576505, 8.724486382484722] | None | 1 |
| random3_development | r20_local50 | 138.232844 | +0.244% | [-0.7303512950821583, 1.419871838280959] | None | 0 |
| random3_development | r21_mature_low50 | 138.532638 | +0.027% | [-0.1673077144348245, 0.19986450703528671] | 0 | 0 |
| random3_development | r21_inverse50 | 136.136408 | +1.756% | [-6.582147406412258, 11.27034810637688] | 111 | 2 |
| random3_development | original_kissat | 134.653244 | +2.827% | [2.628797056609647, 3.0607220245239986] | None | 0 |
| random3_development | stable_v1531 | 134.986246 | +2.586% | [2.3857873599340564, 2.8137683049538156] | None | 0 |
| random3_test | monitor | 82.669388 | +0.000% | [0, 0] | None | 0 |
| random3_test | r11_2048_50 | 73.111426 | +11.562% | [0.7008833730380646, 22.560505186382194] | None | 3 |
| random3_test | r16_live50 | 82.084005 | +0.708% | [-6.005335038814671, 7.002128672052877] | None | 0 |
| random3_test | r20_local50 | 82.539041 | +0.158% | [-0.1331294774252434, 0.4043230980325597] | None | 0 |
| random3_test | r21_mature_low50 | 82.550115 | +0.144% | [-0.15265578878274919, 0.4037634701315118] | 0 | 0 |
| random3_test | r21_inverse50 | 75.339484 | +8.867% | [-1.480660291517225, 19.16024033034968] | 114 | 2 |
| random3_test | original_kissat | 79.739685 | +3.544% | [3.246646217711698, 4.0400645599554394] | None | 0 |
| random3_test | stable_v1531 | 80.136721 | +3.064% | [2.6757169726120176, 3.5110810644447925] | None | 0 |
| community3_development | monitor | 6.278912 | +0.000% | [0, 0] | None | 0 |
| community3_development | r11_2048_50 | 6.267041 | +0.189% | [-13.044416612056796, 10.523304369036138] | None | 0 |
| community3_development | r16_live50 | 6.061567 | +3.462% | [-0.09811135583399697, 9.616463356324532] | None | 0 |
| community3_development | r20_local50 | 6.272176 | +0.107% | [-0.23743806303558465, 0.5177056159013327] | None | 0 |
| community3_development | r21_mature_low50 | 6.267696 | +0.179% | [-0.11649476598930816, 0.5910116809934038] | 0 | 0 |
| community3_development | r21_inverse50 | 6.279723 | -0.013% | [-13.927737289486734, 10.147124888194062] | 45 | 0 |
| community3_development | original_kissat | 5.879445 | +6.362% | [5.577867089970515, 7.372564820633216] | None | 0 |
| community3_development | stable_v1531 | 5.989854 | +4.604% | [4.120159658662734, 5.180076321928082] | None | 0 |
| community3_test | monitor | 6.910304 | +0.000% | [0, 0] | None | 0 |
| community3_test | r11_2048_50 | 7.434301 | -7.583% | [-23.614588905228988, 9.93448834265497] | None | 0 |
| community3_test | r16_live50 | 7.027251 | -1.692% | [-15.918642660938653, 9.765755786666082] | None | 0 |
| community3_test | r20_local50 | 6.947250 | -0.535% | [-1.3335946740609312, 0.2298648738021386] | None | 0 |
| community3_test | r21_mature_low50 | 6.927121 | -0.243% | [-0.7996455846394938, 0.22946818765608784] | 0 | 0 |
| community3_test | r21_inverse50 | 7.429744 | -7.517% | [-23.42902541148344, 8.220851436763162] | 54 | 0 |
| community3_test | original_kissat | 6.432927 | +6.908% | [6.265503477583475, 7.740656123923312] | None | 0 |
| community3_test | stable_v1531 | 6.579367 | +4.789% | [3.9518853146311015, 5.630139670861722] | None | 0 |

Formula-level inference is exploratory; no causal law or official world record.
UNSAT result certificates NOT independently verified.

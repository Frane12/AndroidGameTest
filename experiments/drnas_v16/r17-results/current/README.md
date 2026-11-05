# DRNAS R17 — real native frozen harm risk veto

Risk coefficients trained on 39 R16 development CNFs only, frozen before generating
any R17 problem. Main policy: R16 live50 score > .25 AND estimated harm risk <=.30.
Secondary risk ceiling .45. Monitor/R16/forced50 measured in same runner/core.

| Fold | Mode | PAR2 (s) | Δ vs monitor | Bootstrap formula CI | Selected | Real switches | Regressions >2x |
|---|---|---:|---:|---|---:|---:|---:|
| random3_development | monitor | 90.31041 | +0.000% | [0.0, 0.0] | None | None | 0 |
| random3_development | r11_2048_50 | 95.49540 | -5.741% | [-29.478781436768074, 10.663949818527685] | None | None | 2 |
| random3_development | r16_live50 | 91.11490 | -0.891% | [-2.635336471180323, 0.5858601424822052] | None | None | 0 |
| random3_development | r17_risk30 | 90.78992 | -0.531% | [-2.130261685361873, 0.5065152614972338] | 6 | 6 | 0 |
| random3_development | r17_risk45 | 91.15730 | -0.938% | [-2.6874615033678273, 0.4702475220011187] | 18 | 18 | 0 |
| random3_development | original_kissat | 90.79918 | -0.541% | [-0.6901319707106011, -0.3950742468089799] | None | None | 0 |
| random3_development | stable_v1531 | 91.15778 | -0.938% | [-1.1724938694551055, -0.7688720275582186] | None | None | 0 |
| random3_test | monitor | 81.79476 | +0.000% | [0.0, 0.0] | None | None | 0 |
| random3_test | r11_2048_50 | 86.31253 | -5.523% | [-14.938294877101244, 2.7287339435202216] | None | None | 4 |
| random3_test | r16_live50 | 83.02572 | -1.505% | [-8.14576390138037, 3.2578405739855802] | None | None | 0 |
| random3_test | r17_risk30 | 84.40907 | -3.196% | [-9.70546091933367, 0.14486288082687482] | 9 | 9 | 0 |
| random3_test | r17_risk45 | 83.92413 | -2.603% | [-9.064927405929037, 1.459193930676561] | 21 | 21 | 0 |
| random3_test | original_kissat | 82.80638 | -1.237% | [-1.7543891650936727, -0.8070036260264647] | None | None | 0 |
| random3_test | stable_v1531 | 83.20273 | -1.721% | [-2.688524150780471, -0.8749417945045446] | None | None | 0 |
| community3_development | monitor | 5.42897 | +0.000% | [0.0, 0.0] | None | None | 0 |
| community3_development | r11_2048_50 | 5.87748 | -8.261% | [-20.653753289880598, 1.3252546543295454] | None | None | 0 |
| community3_development | r16_live50 | 5.40151 | +0.506% | [-1.8855365249482554, 2.881411442326859] | None | None | 0 |
| community3_development | r17_risk30 | 5.44294 | -0.257% | [-1.1698993504341142, 0.4170326360561361] | 3 | 3 | 0 |
| community3_development | r17_risk45 | 5.39840 | +0.563% | [-1.7499051965430532, 2.7322434219710834] | 12 | 12 | 0 |
| community3_development | original_kissat | 5.44290 | -0.256% | [-0.7040330130822698, 0.07055503221438054] | None | None | 0 |
| community3_development | stable_v1531 | 5.55468 | -2.315% | [-3.478730277049976, -1.493238538319271] | None | None | 0 |
| community3_test | monitor | 4.41522 | +0.000% | [0.0, 0.0] | None | None | 0 |
| community3_test | r11_2048_50 | 4.32202 | +2.111% | [-5.4936931676950564, 9.84522396724966] | None | None | 0 |
| community3_test | r16_live50 | 4.24120 | +3.941% | [-0.2733680180587297, 10.100178444712157] | None | None | 0 |
| community3_test | r17_risk30 | 4.36172 | +1.212% | [-0.11517876857010084, 3.2747797012727506] | 3 | 3 | 0 |
| community3_test | r17_risk45 | 4.23481 | +4.086% | [-0.07941184194829025, 10.01289770360613] | 6 | 6 | 0 |
| community3_test | original_kissat | 4.40395 | +0.255% | [0.010947254462074191, 0.5616180390579402] | None | None | 0 |
| community3_test | stable_v1531 | 4.54104 | -2.850% | [-3.622677827622706, -2.2622106575938377] | None | None | 0 |

Primary: R17_risk30 vs SAME-BINARY monitor on fresh random3_test.
The R17 test set remains a holdout only for the *frozen* rule.
Any policy changes based on these results require ANOTHER unseen formula set.
No official competition score, no independent UNSAT proof certification.
All 16 manifests contain native and input SHA256, seed, pinned CPU and source revision.

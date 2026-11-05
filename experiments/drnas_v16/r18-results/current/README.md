# DRNAS R18 — frozen paired-time prediction with uncertainty

Real native in-process R18 LCB and mean-only. No replay, no model tuning.

| Fold | Mode | PAR-2 (s) | Δ vs monitor | 95% formula-bootstrap CI | Native actions | Regressions >2× |
|---|---|---:|---:|---|---:|---:|
| random3_development | monitor | 130.94568 | +0.000% | [0.0, 0.0] | None | 0 |
| random3_development | r11_2048_50 | 127.05687 | +2.970% | [-4.930358067488212, 10.724489759650904] | None | 4 |
| random3_development | r16_live50 | 132.15664 | -0.925% | [-5.023658638565399, 2.0606781276141963] | None | 1 |
| random3_development | r17_risk30 | 130.85760 | +0.067% | [-0.05247701856002768, 0.18645644581997906] | None | 0 |
| random3_development | r17_risk45 | 132.73718 | -1.368% | [-5.9351060113495295, 1.5278079287317095] | None | 1 |
| random3_development | r18_lcb | 130.77699 | +0.129% | [0.0016754969308618677, 0.24339140897776038] | 0 | 0 |
| random3_development | r18_mean | 131.10195 | -0.119% | [-0.4293541842244802, 0.17457073447633506] | 3 | 0 |
| random3_development | original_kissat | 130.74947 | +0.150% | [-0.08450481877325444, 0.3439114414364007] | None | 0 |
| random3_development | stable_v1531 | 130.78625 | +0.122% | [-0.037616607907739845, 0.2460456375315821] | None | 0 |
| random3_test | monitor | 82.19822 | +0.000% | [0.0, 0.0] | None | 0 |
| random3_test | r11_2048_50 | 62.89310 | +23.486% | [11.399294129855791, 36.97301484705467] | None | 2 |
| random3_test | r16_live50 | 75.90288 | +7.659% | [-1.6591825421304742, 17.43234074721342] | None | 0 |
| random3_test | r17_risk30 | 80.05194 | +2.611% | [0.4408302772375713, 5.764378657543406] | None | 0 |
| random3_test | r17_risk45 | 76.06669 | +7.459% | [-1.4902575532846611, 17.36145481094647] | None | 0 |
| random3_test | r18_lcb | 82.05981 | +0.168% | [-0.07431771936117933, 0.44797952754398984] | 0 | 0 |
| random3_test | r18_mean | 82.28040 | -0.100% | [-0.6808466957907603, 0.32322353302875106] | 3 | 0 |
| random3_test | original_kissat | 82.00919 | +0.230% | [-0.040813223669049103, 0.4873545788719873] | None | 0 |
| random3_test | stable_v1531 | 82.23621 | -0.046% | [-0.4800736506516015, 0.3193545505132855] | None | 0 |
| community3_development | monitor | 4.86340 | +0.000% | [0.0, 0.0] | None | 0 |
| community3_development | r11_2048_50 | 5.58275 | -14.791% | [-25.709264341413274, -5.710994310804615] | None | 1 |
| community3_development | r16_live50 | 5.03020 | -3.430% | [-8.770317488041695, 0.5866387205894918] | None | 0 |
| community3_development | r17_risk30 | 4.86370 | -0.006% | [-0.19310024027811223, 0.24698100615441543] | None | 0 |
| community3_development | r17_risk45 | 5.02826 | -3.390% | [-8.59849115547792, 0.6486543777286589] | None | 0 |
| community3_development | r18_lcb | 4.86816 | -0.098% | [-0.21640926605675437, 0.009002823427517567] | 0 | 0 |
| community3_development | r18_mean | 4.89056 | -0.558% | [-1.9524460008841211, 0.20400027694399006] | 6 | 0 |
| community3_development | original_kissat | 4.88149 | -0.372% | [-0.8842871319760393, 0.05943639124488709] | None | 0 |
| community3_development | stable_v1531 | 4.96951 | -2.182% | [-3.0185705543461028, -1.6116742395393742] | None | 0 |
| community3_test | monitor | 4.42647 | +0.000% | [0.0, 0.0] | None | 0 |
| community3_test | r11_2048_50 | 4.07681 | +7.899% | [-3.9223485186645077, 21.926581041462974] | None | 0 |
| community3_test | r16_live50 | 4.23463 | +4.334% | [-1.9128259969490111, 13.899148087070612] | None | 0 |
| community3_test | r17_risk30 | 4.41707 | +0.212% | [-0.4135354110359607, 0.8263679753845925] | None | 0 |
| community3_test | r17_risk45 | 4.19327 | +5.268% | [-0.04455352769754477, 15.407596208009615] | None | 0 |
| community3_test | r18_lcb | 4.45078 | -0.549% | [-2.205833530967668, 0.5559625266963582] | 0 | 0 |
| community3_test | r18_mean | 4.40705 | +0.439% | [-0.5595160768662041, 1.627536153873616] | 0 | 0 |
| community3_test | original_kissat | 4.38228 | +0.998% | [0.242722741347854, 2.2956843459762037] | None | 0 |
| community3_test | stable_v1531 | 4.53334 | -2.415% | [-4.319580654878725, -1.1703349193854609] | None | 0 |

R18 LCB bound is a heuristic decision margin, not a mathematical confidence bound.
Primary R18-LCB compared against same-binary monitor on untouched random3_test.
All folds are newly generated, not SAT competition official formulas.
SAT models checked; no independent UNSAT certificate verified.

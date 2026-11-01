# DRNAS SAT V15.3.1 — read-only mathematical relational audit
4296 source attempts, 392 source-paired formula comparisons.
Analysis predefines route, formula-level delta, additive overhead, repeat jitter and calibration axes.
No modification to solver or previous experimental measurements.

## New structural route observation
- Medium 40 routes: {'kissat': 40}.
- Short 40 routes: {'v153_affine_unsat': 10, 'kissat': 30}.
- Structural/affine routes can be beneficial on their own families; do not extrapolate to all random SAT.

## Fallback overhead model (only external medium 40)
- Median delta: 1.7011 ms; formula-bootstrap 95% interval [1.27114750002022, 2.184808499990254] ms.
- Leave-one-formula-out absolute error: additive 2.4028 ms; proportional 3.3342 ms.
- Better LOOCV fit: additive.
- Within-run repeat range >= observed delta in 35/40 formulas.

## Per source family
- 2sat: 12 formulas; median delta -0.0812 ms; V15.3.1 faster 12/12; routes {'v153_binary_sat_verified': 6, 'v153_binary_scc': 6}.
- aim_sat: 8 formulas; median delta 0.9234 ms; V15.3.1 faster 0/8; routes {'kissat': 8}.
- aim_unsat: 8 formulas; median delta 0.9504 ms; V15.3.1 faster 0/8; routes {'kissat': 8}.
- dubois_unsat: 10 formulas; median delta -0.4183 ms; V15.3.1 faster 10/10; routes {'v153_affine_unsat': 10}.
- equiv_binary: 12 formulas; median delta 0.4247 ms; V15.3.1 faster 6/12; routes {'kissat': 6, 'v153_unified_linear_unsat': 6}.
- equiv_xor3: 12 formulas; median delta -0.0528 ms; V15.3.1 faster 11/12; routes {'v153_unified_sat_verified': 6, 'v153_unified_linear_unsat': 6}.
- graph_color: 12 formulas; median delta 0.4017 ms; V15.3.1 faster 6/12; routes {'kissat': 6, 'v153_binary_scc': 6}.
- graph_coloring: 18 formulas; median delta 1.8446 ms; V15.3.1 faster 1/18; routes {'kissat': 18}.
- hall_dense: 12 formulas; median delta -0.3093 ms; V15.3.1 faster 12/12; routes {'v153_hall_sat_verified': 6, 'v153_hall_unsat': 6}.
- hall_residual: 12 formulas; median delta -0.3947 ms; V15.3.1 faster 7/12; routes {'kissat': 5, 'v153_hall_unsat': 6, 'v153_hall_sat_verified': 1}.
- hall_sparse: 12 formulas; median delta -0.1821 ms; V15.3.1 faster 12/12; routes {'v153_hall_sat_verified': 5, 'v153_hall_unsat': 6, 'v153_binary_sat_verified': 1}.
- mixed_xor4: 12 formulas; median delta -0.1359 ms; V15.3.1 faster 12/12; routes {'v153_unified_sat_verified': 4, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 2}.
- mixed_xor6: 12 formulas; median delta -0.0762 ms; V15.3.1 faster 12/12; routes {'v153_unified_sat_verified': 4, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 2}.
- php_general: 12 formulas; median delta -0.6474 ms; V15.3.1 faster 12/12; routes {'v153_hall_sat_verified': 5, 'v153_hall_unsat': 6, 'v153_binary_sat_verified': 1}.
- planted3: 12 formulas; median delta 0.4052 ms; V15.3.1 faster 6/12; routes {'kissat': 6, 'v153_binary_scc': 6}.
- stress: 8 formulas; median delta 1.3277 ms; V15.3.1 faster 1/8; routes {'unrecorded_route': 8}.
- uf200-860: 10 formulas; median delta 2.0290 ms; V15.3.1 faster 0/10; routes {'kissat': 10}.
- uf250-1065: 10 formulas; median delta 1.5053 ms; V15.3.1 faster 2/10; routes {'kissat': 10}.
- uniform20: 8 formulas; median delta 0.9445 ms; V15.3.1 faster 0/8; routes {'kissat': 8}.
- uniform50: 8 formulas; median delta 1.0177 ms; V15.3.1 faster 0/8; routes {'kissat': 8}.
- uniform_sat: 10 formulas; median delta 0.9369 ms; V15.3.1 faster 0/10; routes {'kissat': 10}.
- uniform_unsat: 10 formulas; median delta 1.1026 ms; V15.3.1 faster 0/10; routes {'kissat': 10}.
- unit_chain: 12 formulas; median delta -0.0691 ms; V15.3.1 faster 12/12; routes {'v153_unit_model': 6, 'v153_unit_propagation': 6}.
- uuf200-860: 10 formulas; median delta 1.8527 ms; V15.3.1 faster 1/10; routes {'kissat': 10}.
- uuf250-1065: 10 formulas; median delta 1.1384 ms; V15.3.1 faster 4/10; routes {'kissat': 10}.
- xor10: 12 formulas; median delta -0.2670 ms; V15.3.1 faster 6/12; routes {'v153_affine_sat_verified': 6, 'v153_exhaustive_support': 6}.
- xor8: 12 formulas; median delta -0.1504 ms; V15.3.1 faster 11/12; routes {'v153_affine_sat_verified': 6, 'v153_exhaustive_support': 6}.
- xor_w10: 12 formulas; median delta 0.2717 ms; V15.3.1 faster 2/12; routes {'v153_unified_sat_verified': 4, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 2}.
- xor_w3: 12 formulas; median delta -0.0846 ms; V15.3.1 faster 10/12; routes {'v153_unit_model': 3, 'v153_unified_linear_unsat': 6, 'v153_unified_sat_verified': 3}.
- xor_w4: 12 formulas; median delta -0.0692 ms; V15.3.1 faster 12/12; routes {'v153_unified_sat_verified': 3, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 3}.
- xor_w5: 12 formulas; median delta -0.0830 ms; V15.3.1 faster 12/12; routes {'v153_unit_model': 2, 'v153_unified_linear_unsat': 6, 'v153_unified_sat_verified': 4}.
- xor_w6: 12 formulas; median delta -0.0695 ms; V15.3.1 faster 12/12; routes {'v153_unit_model': 5, 'v153_unified_linear_unsat': 6, 'v153_unified_sat_verified': 1}.
- xor_w7: 12 formulas; median delta -0.0813 ms; V15.3.1 faster 11/12; routes {'v153_unified_sat_verified': 2, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 4}.
- xor_w8: 12 formulas; median delta -0.0130 ms; V15.3.1 faster 6/12; routes {'v153_unified_sat_verified': 2, 'v153_unified_linear_unsat': 6, 'v153_unit_model': 4}.
- xor_w9: 12 formulas; median delta 0.0866 ms; V15.3.1 faster 6/12; routes {'v153_unit_model': 3, 'v153_unified_linear_unsat': 6, 'v153_unified_sat_verified': 3}.

## Limitations
Correlation is not causation. Structural fingerprints and early dynamics need independent data and passive tracing.
SAT/UNSAT model and proof checks are those recorded in original runs; do not claim independent universal UNSAT verification.
No multiple-testing claims; any new correlations require a fresh frozen validation set.

## Files
scatter_delta_medium.png, scatter_delta_short.png, scatter_relative_medium.png, scatter_route_short.png, formula_pairs.csv, group_route.csv, group_category.csv, relation_audit.json.

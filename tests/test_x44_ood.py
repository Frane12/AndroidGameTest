#!/usr/bin/env python3
"""Offline deterministic audits for X4.4's source-only abstention and split isolation."""
from __future__ import annotations
import copy
import json
import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "research"))
import drnas_x44_ood as M
import drnas_x43_two_cycle as X


def mock_rows():
    families = [
        "planted_uniform", "planted_balanced", "planted_dense",
        "planted_negation", "planted_local20", "planted_local40",
        "planted_hubmix", "planted_clausewidth",
    ]
    rows = []
    for i in range(2400):
        split = "train" if i < 1800 else "validation"
        features = [
            math.log1p(220 + i % 70), math.log1p(900 + i % 120),
            4.2 + (i % 7) * .09, (i % 17 == 0) * .09,
            .45 + (i % 13) * .01, .23 + (i % 11) * .01,
            .05 + (i % 5) * .003, 1.4 + (i % 19) * .05,
            .2 + (i % 7) * .01, .075 + (i % 3) * .05,
            0.0, .0,
        ]
        core = .05 + (i % 100) * .007
        adaptive = core * (.8 if i % 5 < 3 else 1.2)
        rows.append({
            "id": i, "sha256": f"{i:064x}", "family": "GENERATED:" + families[i // 300],
            "split": split, "features": features,
            "arms": {X.ARM_CORE: {"status": "SAT_VERIFIED", "PAR2_s": core},
                     X.ARM_ADAPT: {"status": "SAT_VERIFIED", "PAR2_s": adaptive}},
        })
    return rows


def main():
    data = mock_rows()
    model = M.prepare_model(data)
    assert model["schema"] == 1
    assert model["train_count"] == 1800
    assert model["calibration_count"] == 360
    assert model["validation_count"] == 600
    assert model["no_holdout_outcomes_used"]
    assert model["no_per_sha_memory"]
    assert model["ood_threshold"] >= 0
    assert model["fallback"] in (X.ARM_CORE, X.ARM_ADAPT)
    # Model MUST NOT depend on any holdout outcome, features, ID, SHA or family.
    altered = copy.deepcopy(data)
    altered.extend([
        {"id": i, "sha256": f"{i:064x}", "split": "holdout",
         "family": "MALICIOUS_HOLDOUT", "features": [float(i)] * len(X.FEATURES),
         "arms": {X.ARM_CORE: {"PAR2_s": 1e30},
                  X.ARM_ADAPT: {"PAR2_s": 1e-10}}}
        for i in range(2400, 2420)
    ])
    assert M.prepare_model(altered) == model
    for row in data[::183]:
        chosen, guarded, score, flagged = M.route(model, row["features"])
        assert chosen in (X.ARM_CORE, X.ARM_ADAPT)
        assert guarded in (X.ARM_CORE, X.ARM_ADAPT)
        assert math.isfinite(score)
        assert isinstance(flagged, bool)
        if flagged:
            assert guarded == model["fallback"]
    # A strongly shifted source MUST trigger abstention.
    weird = [1e3] * len(X.FEATURES)
    assert M.route(model, weird)[3] is True

    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        sources = []
        for family in M.FAMILIES:
            for rep in (0, 1):
                src = M.new_source(family, rep, root)
                feats = X.extract_features(src["path"], src["nvars"], src["nclauses"])
                assert len(feats) == 12 and all(math.isfinite(v) for v in feats)
                assert src["source_kind"].startswith("GENERATED")
                assert src["sha256"] not in {z["sha256"] for z in sources}
                assert src["split"] == ("eval_known" if family in M.KNOWN else "eval_ood")
                sources.append(src)
        assert len(sources) == 10
        if X.X41.exists() and X.X3.exists():
            first = sources[0]
            for arm in (X.ARM_CORE, X.ARM_ADAPT):
                run, _ = X.checked_run(first, arm, 0.25)
                assert run["status"] in ("SAT_VERIFIED", "UNKNOWN")
    print("X44_TEST_PASS " + json.dumps({
        "mock_train": 1800, "mock_validation": 600,
        "new_family_smoke": 10, "holdout_leakage": False,
        "ood_threshold": model["ood_threshold"], "fallback": model["fallback"]
    }, sort_keys=True))


if __name__ == "__main__":
    main()

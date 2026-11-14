#!/usr/bin/env python3
"""Proof-checked COOP54B no-block fastpath vs its exact frozen baseline.

Uses the audited COOP54 paired runner with an isolated five-arm configuration.
No blind holdout, no promotion, source/BIN SHA checked per shard.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path("research").resolve()))
from drnas_coop54 import paired as P

P.ARMS=("COOP53_BASE","COOP54B_GATE","COOP54B_FULL","KISSAT","CADICAL")
P.BIN.update({
 "COOP54B_GATE":"build/drnas-coop54-gate",
 "COOP54B_FULL":"build/drnas-coop54-gate",
})
P.EXTRA.update({
 "COOP54B_GATE":["--x5-no-minimize"],
 "COOP54B_FULL":["--x5-retain","--x5-restarts"],
})
P.PINS={"frozen_coop53_run":43534791673,
        "coop54b_preflight_run":43579405454,
        "real36_source_run":43387395060,
        "frozen_kissat_cadical_run":43449841902}
if __name__=="__main__":
    P.main()

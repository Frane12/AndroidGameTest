#!/usr/bin/env python3
"""COOP55 proof-first A/B on original SAT2024 with frozen competitors."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path("research").resolve()))
from drnas_coop54 import paired as P
P.ARMS=("COOP53_BASE","COOP54B_GATE","COOP55_SHADOW","COOP55_ACTIVE","KISSAT","CADICAL")
P.BIN.update({
    "COOP54B_GATE":"build/drnas-coop54-gate",
    "COOP55_SHADOW":"build/drnas-coop55-shadow",
    "COOP55_ACTIVE":"build/drnas-coop55-active",
})
P.EXTRA.update({
    "COOP54B_GATE":["--x5-no-minimize"],
    "COOP55_SHADOW":["--x5-no-minimize"],
    "COOP55_ACTIVE":["--x5-no-minimize"],
})
P.PINS={"coop55_proof_run":43580031955,"coop54b_preflight_run":43579405454,
        "real36_source_run":43387395060,"frozen_refs_run":43449841902}
if __name__=="__main__":P.main()

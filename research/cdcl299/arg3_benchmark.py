#!/usr/bin/env python3
"""No-tuning post-discovery source #299 comparison with ARG3 enabled.
Original SAT source known, so this is targeted validation, not a blind result.
"""
import json
from pathlib import Path
import diagnose as D
D.OUT=D.ROOT/"cdcl299_arg3_results"
D.ARMS={
 "BASE":[],
 "ARG3_15":["--arg3-ms","15"],
 "ARG3_50":["--arg3-ms","50"],
 "ARG3_100":["--arg3-ms","100"],
 "ARG3_PLUS_MATH":["--arg3-ms","50","--sat-construct-ms","25"],
 "MIN_OFF_RESTART":["--x5-no-minimize","--x5-restarts"],
 "CaDiCaL":None
}
if __name__=="__main__":
    D.main()
    rows=json.loads((D.OUT/"trials.json").read_text())
    for row in rows:
        if row["arm"].startswith("ARG3"):
            a=row["telemetry"].get("SAT_ARG3_STATS",{})
            print("ARG3_VERIFIED_TRIAL "+json.dumps(dict(
                arm=row["arm"],rep=row["rep"],status=row["status"],
                e2e_s=row["e2e_s"],found=a.get("found"),
                recognized=a.get("recognized"),iterations=a.get("iterations"),
                stable_candidates=a.get("stable_candidates"),
                blocked_candidates=a.get("blocked_candidates"),
                wall_ms=a.get("wall_ms")),sort_keys=True),flush=True)

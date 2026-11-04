#!/usr/bin/env python3
"""R102: audit whether certified XOR clause emission predicts CDCL benefit.
Observational only: paired runs are NOT a causal ablation or blind holdout.
Usage: python3 research/r102_xor_value_audit.py paired.csv
"""
import csv, json, pathlib, statistics, sys
from collections import defaultdict

def main(path):
    data=list(csv.DictReader(open(path,newline="")))
    required={"formula","sha256","rep","mode","status","total_s","par2_s","emitted","signals","prep_s"}
    if not data or not required.issubset(data[0]):
        raise SystemExit("R102_FAIL_CLOSED: missing required columns")
    groups=defaultdict(dict)
    for row in data:
        key=(row["sha256"],row["rep"])
        if row["mode"] in groups[key]:
            raise SystemExit("R102_FAIL_CLOSED: duplicate paired mode")
        groups[key][row["mode"]]=row
    out=[]
    for key,modes in sorted(groups.items()):
        if "clean" not in modes:
            raise SystemExit("R102_FAIL_CLOSED: missing clean comparator")
        clean=modes["clean"]
        for name,row in modes.items():
            if name=="clean": continue
            if row["status"] not in ("SAT","UNSAT","TIMEOUT"):
                raise SystemExit("R102_FAIL_CLOSED: invalid status")
            if clean["status"] in ("SAT","UNSAT") and row["status"] in ("SAT","UNSAT") and clean["status"]!=row["status"]:
                raise SystemExit("R102_FAIL_CLOSED: SAT/UNSAT mismatch")
            out.append({"sha256":key[0],"rep":key[1],"mode":name,
                        "emitted":int(row["emitted"]),"signals":int(row["signals"]),
                        "prep_s":float(row["prep_s"]),
                        "par2_delta_s":float(row["par2_s"])-float(clean["par2_s"]),
                        "solved_delta":int(row["status"]!="TIMEOUT")-int(clean["status"]!="TIMEOUT")})
    summary={}
    for mode in sorted({r["mode"] for r in out}):
        rows=[r for r in out if r["mode"]==mode]
        summary[mode]={"pairs":len(rows),
            "par2_delta_sum_s":round(sum(r["par2_delta_s"] for r in rows),6),
            "median_pair_delta_s":round(statistics.median(r["par2_delta_s"] for r in rows),6),
            "emitted_total":sum(r["emitted"] for r in rows),
            "solved_delta":sum(r["solved_delta"] for r in rows),
            "prep_s_total":round(sum(r["prep_s"] for r in rows),6)}
    print(json.dumps({"protocol":"R102-observational-not-causal","summary":summary,
        "warning":"Emission counts cannot identify useful clauses. Need randomized matched selective-vs-monitor-vs-active ablation and independent holdout."},indent=2))
if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit(__doc__)
    main(sys.argv[1])

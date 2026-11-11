#!/usr/bin/env python3
"""ATLAS33 CDCL regression triage: paired per-SHA E2E/PAR2, no unsupported claims."""
import json,sys,collections
rows=[]
for path in sys.argv[1:]:
    rows.extend(json.load(open(path))["rows"])
by=collections.defaultdict(dict)
for r in rows:
    by[(r["sha256"],r["rep"])][r["arm"]]=r
print("ATLAS33_REGRESSION_DIAG trials",len(rows),"pairs",len(by))
family=collections.defaultdict(lambda:collections.defaultdict(lambda:{"par2":0., "solved":0,"n":0}))
worst=[]
for key,arms in by.items():
    if set(arms)!={"KISSAT","V23_C7_STABLE","V23_PHP"}:continue
    k,v,p=(arms[x] for x in ("KISSAT","V23_C7_STABLE","V23_PHP"))
    fam=k["family"]
    for arm,r in arms.items():
        a=family[fam][arm];a["par2"]+=r["PAR2_reported_s"];a["solved"]+=r["status"]!="UNKNOWN";a["n"]+=1
    if fam.startswith("satlib_"):
        worst.append((v["PAR2_reported_s"]/max(k["PAR2_reported_s"],1e-6),fam,key[0],key[1],k["PAR2_reported_s"],v["PAR2_reported_s"],p["PAR2_reported_s"],k["status"],v["status"]))
for fam,arms in sorted(family.items()):
    print("FAMILY",fam,json.dumps(arms,sort_keys=True))
for x in sorted(worst,reverse=True)[:20]:
    print("REGRESSION",json.dumps(dict(ratio=round(x[0],2),family=x[1],sha=x[2],rep=x[3],kissat_s=x[4],v23_s=x[5],php_s=x[6],kissat_status=x[7],v23_status=x[8]),sort_keys=True))

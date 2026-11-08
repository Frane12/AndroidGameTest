#!/usr/bin/env python3
"""MRE11 prospective official SAT2026 4SAT+4UNSAT, SHA frozen BEFORE any
candidate solver or DRNAS MRE10 performance is inspected.

Source selection: SHA salted official GBD ID, verified published SAT/UNSAT
status and fixed geometry limits only. Explicit exclusions: R63/R81/R82/R32p,
visible historical research IDs, and the SHA-locked MRE6b original SAT2026
pilot downloaded separately from its official GitHub Actions artifact.
"""
from __future__ import annotations
import argparse,hashlib,json,pathlib,re
import mre6b_blind_freeze as source

ROOT=pathlib.Path("mre11_blind")
PRIOR_MRE6B=pathlib.Path("mre11_prior/mre6b_blind/manifest.json")
PRIOR_MRE7=pathlib.Path("mre11_prior/mre7_medium/manifest.json")
PROTO="DRNAS-MRE11-2026-NEW-SHA-SALT-8-4SAT4UNSAT-2REPS-35S-v1"
SALT="DRNAS-MRE11-PROSPECTIVE-SOURCE-DISJOINT-20261108-NO-PERFORMANCE-LOOKUP"
TARGET=8
CAP=35.0
REPS=2
MODES=("cpp_native","cpp_rename","cpp_clean","cpp_joint","cpp_route","cpp_ref_6f","kissat","cadical")
def need(v,m):
    if not v:raise RuntimeError("MRE11_SOURCE_FAIL_CLOSED "+m)
def source_exclusions():
    previous=json.loads(PRIOR_MRE6B.read_text())
    need(previous["protocol"]=="DRNAS-MRE6B-SAT2026-UNSEEN-GBD-8OFFICIAL-4ARM-2REP-v1" and
         len(previous["cases"])>=4,"previous 2026 prospectively selected pilot missing")
    ids={c["gbd"] for c in previous["cases"]}
    if PRIOR_MRE7.exists():
        second=json.loads(PRIOR_MRE7.read_text())
        for k in ("cases","selected_cases","source_set"):
            for c in second.get(k,[]):
                if isinstance(c,dict) and re.fullmatch("[0-9a-f]{32}",str(c.get("gbd",""))):
                    ids.add(c["gbd"])
    need(all(re.fullmatch("[0-9a-f]{32}",q) for q in ids),
         "historical official source ID invalid")
    return ids
def freeze():
    ids=source_exclusions()
    raw=set(q.strip() for q in source.PRIOR.read_text().splitlines()
            if re.fullmatch("[0-9a-f]{32}",q.strip()))
    raw.update(ids)
    ROOT.mkdir(parents=True,exist_ok=True)
    prior=ROOT/"prior-registry-augmented.txt"
    prior.write_text("\n".join(sorted(raw))+"\n")
    source.PRIOR=prior
    source.PROTO=PROTO
    source.SALT=SALT
    source.TARGET=TARGET
    source.MIN_READY=TARGET
    source.MAX_FETCH=150
    source.freeze(ROOT)
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==TARGET,
         "did not freeze all eight exact original 2026 SHA cases")
    need(m["statuses"]=={"SAT":4,"UNSAT":4},
         "source publication quota drift from four SAT four UNSAT")
    need(all(c["gbd"] not in ids for c in m["cases"]),
         "previously used 2026 input leaked into prospect")
    m["protocol"]=PROTO
    m["cap_s"]=CAP
    m["repetitions"]=REPS
    m["modes"]=list(MODES)
    m["comparison_design"]="7 MRE10 C++ and reference solvers; unfiltered by solver runtime, MRE equivalences or reductions"
    m["previous_MRE6B_source_ids_excluded"]=len(ids)
    m["reference_before_result_freeze"]=True
    m["provisional_source_registry_disjoint_not_globally_exhaustive"]=True
    m["no_auto_promotion"]=True
    (ROOT/"manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("MRE11_FROZEN",json.dumps(dict(
        SHA_count=len(m["cases"]),statuses=m["statuses"],
        official_indexes=m["official_index"],
        historic_ids_excluded=m["previous_registered_ids"],
        additional_pilot_ids_excluded=len(ids),
        original_input_hashes=[c["sha256"] for c in m["cases"]]),
        sort_keys=True),flush=True)
def verify():
    source.PROTO=PROTO
    source.MIN_READY=TARGET
    source.TARGET=TARGET
    source.verify(ROOT)
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["statuses"]=={"SAT":4,"UNSAT":4} and len(m["cases"])==TARGET,
         "source quota altered")
    need(m["cap_s"]==CAP and m["repetitions"]==REPS and
         m["modes"]==list(MODES),"benchmark protocol altered")
    return m
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("freeze","verify"))
    args=a.parse_args()
    if args.action=="freeze":freeze()
    else:
        x=verify();print("MRE11_SOURCE_VERIFY_PASS",len(x["cases"]))

#!/usr/bin/env python3
"""DRNAS MRE11-L35: untouched MRE11 C++ binary, identical seven 2026 originals
and identical four SHA-paired seeds; ONLY the per-trial real wall cap changes
from 8s to 35s. In particular, do not re-freeze, re-screen, retune, or
recompile the selector. PAR2 cap penalty is 70s. This is a predeclared
follow-up prompted by 140/140 timeouts at 8s: it is not a new blind holdout.
SAT models are checked against original source SHA, UNSAT only agrees with
published official CaDiCaL; no independent LRAT certificate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import tempfile
import mre11_holdout as b

PARENT_PROTOCOL=b.PROTO
PROTO="DRNAS-MRE11-L35-FROZEN-SAT2026-7ORIGINAL-5ARMS-4SEEDS-35S-v1"
FROZEN_RUN=42513542283
FROZEN_ARTIFACT="mre11-2026-prospective-frozen-sources-and-native-CPP"
EXPECTED={
    "a45aefde8bb26edb9634004146d0de89":"66ab1c4d519a7ec5b0bd8edcba799ceb35b2a9ed94e7a827564b60e81b18caa4",
    "15456f0d13b26f0b4b21525ef7d0d711":"bef68708b5e9a9412fcf2128111c1442d5205bb33e0ba8a7a262048f4025d0b8",
    "782b29d2d691fdc94e0ec5b899390e10":"5b66e930ea9d45d193332bcfe5bda4bbeae460c7e19c412eb4a75c1cac689046",
    "de8c42d50f1dbf43a731f1916dc6bf01":"66eed3751ae85783d036a9231b847eed441f246c0e9a9ed3dff7eb029b62a558",
    "416e33a8463911546e4cd87d282a7e1e":"a37a3f891d438d859c3285a1236ddc3d4e92cc50bb6e5dd74f1e3390c999400b",
    "db099269d468029b70419bf4a49e99a1":"d9ed4ad91f3be7ec0b28ad6a91e1be26d921d4362f58f27a4dbef941fb336337",
    "6ad453d6174581d982c4e75e37a38d79":"8c94fd728fe8cda5d50bcc634b745ea6eb405e00a5d9cf0566916bdd21982145"
}
ORIGINAL_EIGHT_SEC_TOTAL_PAR2_EACH=448.0
ROOT=b.ROOT
MODES=b.MODES

def frozen_seed(case,rep):
    b.need(0<=rep<4,"invalid frozen repetition")
    return int(hashlib.sha256(
        (PARENT_PROTOCOL+"|SEED|"+case["sha256"]+"|"+str(rep)).encode()
    ).hexdigest()[:8],16)

def cases():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    bb=manifest["cases"]
    b.need(manifest["protocol"]==PARENT_PROTOCOL,"not exact original MRE11 freeze")
    b.need(len(bb)==7 and len(EXPECTED)==7 and manifest["actual"]==7,
           "frozen original cardinality changed")
    b.need({x["gbd"] for x in bb}==set(EXPECTED),"MRE11 original GBD set differs")
    b.need(all(x["year"]==2026 for x in bb),"unexpected year")
    b.need(sum(x["official_status"]=="SAT" for x in bb)==4 and
           sum(x["official_status"]=="UNSAT" for x in bb)==3,
           "original frozen SAT/UNSAT balance changed")
    for c in bb:
        file=ROOT/c["filename"]
        b.need(file.is_file(),"frozen source absent")
        data=file.read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        b.need(digest==c["sha256"]==EXPECTED[c["gbd"]] and
               len(data)==c["bytes"],"source bytes drifted from MRE11 audit")
    return bb

# Explicitly only change cap and protocol label, never original model/seed.
b.CAP=35.0
b.PROTO=PROTO
b.cases=cases
b.seed=frozen_seed

def selftest():
    cc=cases()
    b.need(b.CAP==35.0 and len(MODES)==5 and b.REPS==4 and
           b.SHARDS==4 and b.ROOT==pathlib.Path("mre11"),"L35 protocol drift")
    c=next(c for c in cc if c["gbd"]=="15456f0d13b26f0b4b21525ef7d0d711")
    b.need(frozen_seed(c,0)==2254905642 and
           frozen_seed(c,1)==1876755172,
           "original MRE11 seed pairing changed")
    b.need(all(len({frozen_seed(c,r) for r in range(4)})==4 for c in cc),
           "seed collisions within original case")
    print("MRE11_L35_FROZEN_SOURCE_SEED_SELFTEST_PASS",
          json.dumps(dict(sources=len(cc),modes=len(MODES),repetitions=4,
                          cap_s=b.CAP,old_run=FROZEN_RUN,old_protocol=PARENT_PROTOCOL,
                          protocol=PROTO),sort_keys=True),flush=True)

def gate_diagnostics(standalone):
    """Measure only the standalone rewriting metadata, separately from PAR2."""
    cc=cases()
    data=[]
    with tempfile.TemporaryDirectory(prefix="mre11-l35-gate-") as td:
        dst=pathlib.Path(td)/"derived.cnf"
        for c in cc:
            original=ROOT/c["filename"]
            record={"gbd":c["gbd"],"source_sha256":c["sha256"],
                    "official_status":c["official_status"],"modes":{}}
            for mode in MODES:
                g=b.subprocess_gate(original,mode,dst,standalone)
                record["modes"][mode]=g
            data.append(record)
            print("MRE11_L35_GATE_TELEMETRY",json.dumps(record,sort_keys=True),flush=True)
    pathlib.Path("mre11_l35").mkdir(exist_ok=True)
    b.save("mre11_l35/gate_diagnostics.json",
           {"protocol":PROTO,"no_solver_cpu_in_source_selection":True,
            "outside_PAR2_timing":True,"cases":data})
    print("MRE11_L35_GATE_DIAGNOSTIC_PASS",len(data),flush=True)

def audit():
    b.audit()
    output=ROOT/"report.json"
    result=json.loads(output.read_text())
    b.need(result["cap_s"]==35.0 and
           result["official_2026_sources"]==7 and
           result["total_trials"]==140,"L35 audit coverage or cap mismatch")
    result["previous_frozen_8s_run_id"]=FROZEN_RUN
    result["previous_frozen_8s_per_arm_PAR2_s"]=ORIGINAL_EIGHT_SEC_TOTAL_PAR2_EACH
    result["baseline_8s_all_timeout"]=True
    result["same_exact_original_seven_CNF_SHA"]=True
    result["same_exact_frozen_MRE11_seeds"]=True
    result["same_exact_frozen_MRE11_CMS_native_binary"]=True
    result["new_holdout_claim"]=False
    result["only_changed_parameter"]="wall_cap_s: 8.0 -> 35.0"
    result["independent_UNSAT_LRAT"]=False
    b.save(output,result)
    print("MRE11_L35_FINAL",json.dumps(
        {k:v for k,v in result.items() if k!="per_source"},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","diagnostics","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre11/bin/native")
    p.add_argument("--standalone",default="mre11/bin/standalone")
    a=p.parse_args()
    if a.action=="verify":selftest()
    elif a.action=="diagnostics":gate_diagnostics(a.standalone)
    elif a.action=="shard":
        selftest()
        b.shard(a.shard,a.native)
    else:
        selftest()
        audit()

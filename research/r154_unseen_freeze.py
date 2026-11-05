#!/usr/bin/env python3
"""R154 SHA-disjoint original 2026 Lights-Out and linear equations holdout.

Freeze entirely before any solver evaluation. Family membership and syntactic
parity coverage only; no tuning against source timings. Reuse R152's exact
source-fetch and structural-signature logic with NEW random seed and prior SHA
exclusion, including the 13 R152 development cases. Selected 2026 official
source filenames are included for audit. This remains a conditional family
holdout, not cross-domain SAT.
"""
import json
import pathlib
import importlib.util
ROOT=pathlib.Path("r154")
ROOT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location("r152_source","research/r152_lightsout_unseen.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=ROOT
m.orig.ROOT=ROOT
m.orig.R28=(ROOT/"r28").resolve()
m.PROTO="DRNAS-R154-UNSEEN-LIGHTSOUT-XOR-UNIT-TRANSFER-20261105-v1"
m.orig.PROTO=m.PROTO
m.MAX_CANDIDATES=320
m.QUOTA={"complete_xor":8,"partial_xor":12,"nonxor_control":12}
if __name__=="__main__":
 m.freeze()
 p=ROOT/"frozen"/"manifest.json"
 manifest=json.loads(p.read_text())
 assert manifest["protocol"]==m.PROTO
 assert len(manifest["cases"])>=8, "Not enough fresh external family CNF instances"
 assert len(manifest["cases"])==len(set(c["sha256"] for c in manifest["cases"]))
 assert all(not c["known"] for c in manifest["cases"])
 assert any("prior/r152/" in f for f in manifest["exclusion_files"]), "Missing previous R152 source exclusion"
 print("R154_SOURCE_FROZEN",json.dumps({"count":len(manifest["cases"]),"cohorts":manifest["cohort_counts"],
       "checked_prior_ids":manifest["excluded_ids_count"],"checked_prior_shas":manifest["excluded_sha_count"],
       "selection":"metadata and structural signature only, no solver runtime selection"},sort_keys=True),flush=True)

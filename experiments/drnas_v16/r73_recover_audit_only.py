#!/usr/bin/env python3
"""Audit-only recovery for R73: never rerun source selection or solver trials.

Original 8 shards passed. The prior final writer used a renamed manifest key
(source_catalog_sha) absent from R73's source manifest. Repair *metadata only*
in a transient copy and invoke the already-frozen fail-closed paired audit.
"""
import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import r73_fresh_quick_unseen_2025 as r73

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--combined",required=True)
    p.add_argument("--json",required=True)
    p.add_argument("--md",required=True)
    a=p.parse_args()
    original=Path(a.sources)/"manifest.json"
    m=json.loads(original.read_text())
    r73.check(m["protocol"]==r73.PROTO and m["ready"]==8,
              "wrong historical R73 manifest")
    r73.check("source_catalog_sha" not in m and
              len(m.get("index25_sha256",""))==64 and
              len(m.get("index26_sha256",""))==64,
              "unexpected source-index metadata")
    m["source_catalog_sha"]={
        "index25_sha256":m["index25_sha256"],
        "index26_sha256":m["index26_sha256"]}
    with tempfile.TemporaryDirectory(prefix="r73-audit-metadata-") as td:
        Path(td,"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
        r73.audit(SimpleNamespace(sources=td,combined=a.combined,
                                  json=a.json,md=a.md))
    print("R73_AUDIT_ONLY_RECOVERY_PASS: no solver re-runs; source hashes unchanged",
          flush=True)

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Preregistered original SAT2026 medium/high-scale input freezer.

The selection file is committed BEFORE this code is run. No outcome-based
replacement or filtering. Rejected/unavailable sources stay in the manifest.
"""
import hashlib
import json
import lzma
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/hall3"))
from collect import download, CAT_URL, MAIN_URL, MAX_ARCHIVE, MAX_RAW

SEL = ROOT / "research/maxpar2/selection.json"
OUT = ROOT / "maxpar2_inputs"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    selection = json.loads(SEL.read_text())
    assert selection["source_count"] == 27
    assert selection["selection_frozen_before_any_solver_run"]
    assert selection["cap_s"] == 20 and selection["repetitions"] == 3
    assert len(selection["selected_sources"]) == 27
    assert len({x["file_id"] for x in selection["selected_sources"]}) == 27
    assert len({x["isohash"] for x in selection["selected_sources"]}) == 27
    old = json.loads((ROOT / "research/hall3/manifest.json").read_text())
    old_hold = json.loads((ROOT / "research/math4/holdout_selection.json").read_text())
    excluded = json.loads((ROOT / "research/hall3/exclusions.json").read_text())
    ids_old = {x["file_id"] for x in old["sources"]}
    ids_old.update(x["file_id"] for x in old_hold["source_ids"])
    ids_old.update(excluded["file_ids"])
    assert not ids_old.intersection(x["file_id"] for x in selection["selected_sources"])

    catalog_raw = download(CAT_URL, 3_000_000)
    track_raw = download(MAIN_URL, 200_000)
    assert sha(catalog_raw) == old["catalog_sha256"], "catalog_changed"
    assert sha(track_raw) == old["official_main_sha256"], "main_track_changed"
    main_ids = set(re.findall(r"/file/([a-f0-9]{32})", track_raw.decode()))
    assert len(main_ids) == selection["official_main_track_sources"] == 400
    catalog = {}
    for ln in catalog_raw.decode().splitlines()[1:]:
        p = ln.split()
        if len(p) == 6:
            k, author, family, label, iso, part = p
            catalog[k] = dict(author=author, family=family,
                              catalog_label=label, isohash=iso, participates=part)

    assert not OUT.exists()
    (OUT / "cnf").mkdir(parents=True)
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    records, failures = [], []
    for idx, entry in enumerate(selection["selected_sources"]):
        file_id = entry["file_id"]
        assert file_id in main_ids
        assert catalog[file_id] == {k: entry[k] for k in
            ("author", "family", "catalog_label", "isohash", "participates")}
        assert entry["participates"] == "yes"
        url = "https://benchmark-database.de/file/" + file_id + "?context=cnf"
        meta = dict(entry, id=idx, url=url, selected_before_results=True)
        try:
            archive = download(url, MAX_ARCHIVE)
            if archive.startswith(b"\xfd7zXZ\x00"):
                decoder = lzma.LZMADecompressor()
                raw = decoder.decompress(archive, max_length=MAX_RAW + 1)
                if len(raw) > MAX_RAW or not decoder.eof:
                    raise ValueError("raw_size_gate")
            else:
                raw = archive
            if len(raw) > MAX_RAW or len(raw) < selection["input_min_raw_bytes"]:
                raise ValueError("raw_size_gate")
            hdr = re.search(rb"^p\s+cnf\s+(\d+)\s+(\d+)\s*$", raw, re.M)
            if not hdr:
                raise ValueError("missing_DIMACS_header")
            variables, clauses = map(int, hdr.groups())
            if variables > 200_000 or clauses > 2_000_000 or (
                    clauses < selection["input_min_clauses"]):
                raise ValueError("declared_dimensions_gate")
            relative = Path("maxpar2_inputs/cnf") / f"{idx:02d}-{file_id}.cnf"
            (ROOT / relative).write_bytes(raw)
            rec = dict(meta, status="SOURCE_FROZEN", path=str(relative),
                       sha256=sha(raw), archive_sha256=sha(archive),
                       variables=variables, clauses=clauses, bytes=len(raw),
                       archive_bytes=len(archive),
                       size_tier="high_size" if clauses >= 100_000 or
                            variables >= 20_000 else "medium_size")
            records.append(rec)
            print("MAXPAR2_SOURCE " + json.dumps({k: rec[k] for k in (
                "id", "family", "file_id", "catalog_label", "variables",
                "clauses", "sha256", "size_tier")}, sort_keys=True), flush=True)
        except (ValueError, OSError, lzma.LZMAError) as exc:
            err = dict(meta, status="SOURCE_EXCLUDED", error=str(exc)[:240])
            failures.append(err)
            print("MAXPAR2_SOURCE_EXCLUDED " + json.dumps(err, sort_keys=True), flush=True)
    manifest = dict(protocol=selection["protocol"],
        selection_sha256=sha(SEL.read_bytes()),
        catalog_sha256=sha(catalog_raw), track_sha256=sha(track_raw),
        selected_count=27, downloaded_count=len(records),
        excluded_or_failed=failures, sources=records, cpu=cpu,
        selection_frozen_before_results=True, no_outcome_reselection=True,
        original_CNFs_unchanged=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("MAXPAR2_FROZEN " + json.dumps(dict(selected=27, frozen=len(records),
        excluded=len(failures), size_tiers={t:sum(r["size_tier"]==t for r in records)
        for t in ("medium_size", "high_size")}), sort_keys=True), flush=True)
    assert len(records) >= 12, "Insufficient frozen sources; no replacements"

if __name__ == "__main__":
    main()

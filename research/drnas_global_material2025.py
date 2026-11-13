#!/usr/bin/env python3
"""Immutable SAT Competition 2025 *new submissions* blind cohort.

Selection depends on family and instance hash only, never status, answer,
reference solver, labels, run-time or any learned policy. Download caps and
DIMACS validity are the only post-selection filters. No fallback to 2024.
"""
from __future__ import annotations
import argparse
import bz2
import collections
import gzip
import hashlib
import html.parser
import json
import lzma
import re
import urllib.request
from pathlib import Path

import drnas_real_material2 as M

PROTOCOL = "DRNAS-ROUTER-V2-SAT2025-NEW-v1"
INDEX = "https://benchmark-database.de/?context=cnf&track=main_2025"
FILE_BASE = "https://benchmark-database.de/file/"
COMPRESSED_LIMIT = 6_000_000
RAW_LIMIT = min(M.MAX_RAW, 18_000_000)
HEX32 = re.compile(r"^[0-9a-f]{32}$")


class IndexTables(html.parser.HTMLParser):
    """Extract HTML table cells while ignoring decorative tags and links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def select_entries(index_html, limit):
    parser = IndexTables()
    parser.feed(index_html)
    headings = {}
    rows = []
    for cells in parser.rows:
        names = [x.strip().lower() for x in cells]
        if all(k in names for k in ("hash", "family", "filename", "track")):
            headings = {name: i for i, name in enumerate(names)}
            continue
        if not headings:
            continue
        if len(cells) <= max(headings.get(k, -1) for k in ("hash", "family", "filename", "track")):
            continue
        record = {k: cells[headings[k]] for k in ("hash", "family", "filename", "track")}
        record["hash"] = record["hash"].strip().lower()
        record["family"] = record["family"].strip().lower()
        record["filename"] = record["filename"].strip()
        tracks = {x.strip() for x in record["track"].split(",")}
        if not ({"main_2025", "submissions_2025"} <= tracks):
            continue
        if not HEX32.fullmatch(record["hash"]) or not record["family"]:
            continue
        rows.append(record)
    if len(rows) < 24:
        raise RuntimeError("Official SAT2025 new-submissions index unavailable/too small: %d rows" % len(rows))
    # First pass one per family, next passes second/third from other families.
    # Hash order and family order are frozen and independent of labels/outcomes.
    families = collections.defaultdict(list)
    for record in rows:
        families[record["family"]].append(record)
    order = sorted(families, key=lambda f: hashlib.sha256(("router-v2-20261113|"+f).encode()).hexdigest())
    for group in families:
        families[group].sort(key=lambda r: r["hash"])
    result, seen = [], set()
    for depth in range(max(len(v) for v in families.values())):
        for group in order:
            if depth >= len(families[group]):
                continue
            rec = families[group][depth]
            if rec["hash"] not in seen:
                result.append(rec)
                seen.add(rec["hash"])
            if len(result) >= limit:
                return result
    return result


def bounded_decompress(blob):
    if blob.startswith(b"\xfd7zXZ\x00"):
        decomp = lzma.LZMADecompressor()
        raw = decomp.decompress(blob, max_length=RAW_LIMIT+1)
        if not decomp.eof:
            raise ValueError("Incomplete/oversize xz")
    elif blob.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(blob)
    elif blob.startswith(b"BZh"):
        raw = bz2.decompress(blob)
    else:
        raw = blob
    if len(raw) > RAW_LIMIT:
        raise ValueError("Original CNF size exceeds cap")
    return raw


def fetch(url, limit, timeout=35):
    req = urllib.request.Request(url, headers={
        "User-Agent": "DRNAS research reproducible SAT benchmark/1.0",
        "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(limit+1)
    if len(data) > limit:
        raise ValueError("Response size bound exceeded")
    return data


def prepare(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    (out/"cnf").mkdir()
    page = fetch(INDEX, 5_000_000).decode("utf-8")
    order = select_entries(page, args.max_attempts)
    accepted = []
    seen_semantic, seen_raw = set(), set()
    rejects = collections.Counter()
    for i, item in enumerate(order):
        if len(accepted) >= args.count:
            break
        url = FILE_BASE+item["hash"]+"?context=cnf"
        try:
            packed = fetch(url, COMPRESSED_LIMIT, timeout=40)
            raw = bounded_decompress(packed)
            nvars, nclauses, clauses, semantic = M.parse(raw)
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_raw or semantic in seen_semantic:
                rejects["semantic_duplicate"] += 1
                continue
            file = "cnf/"+digest+".cnf"
            (out/file).write_bytes(raw)
            accepted.append({
                "sha256": digest, "semantic_sha256": semantic,
                "file": file, "family": item["family"], "gbd_hash": item["hash"],
                "original_filename": item["filename"],
                "source_url": url, "source_year": 2025,
                "track": "main_2025,submissions_2025",
                "nvars": nvars, "nclauses": nclauses, "bytes": len(raw),
                "features": M.features(raw)
            })
            seen_raw.add(digest)
            seen_semantic.add(semantic)
        except Exception as exc:
            name = type(exc).__name__
            rejects[name] += 1
            if rejects[name] <= 3:
                M.emit("ROUTER_V2_DOWNLOAD_SKIP", {"index":i,"reason":name,
                    "details":str(exc)[:160]})
        if (i+1) % 12 == 0:
            M.emit("ROUTER_V2_MATERIAL_PROGRESS", {"attempted":i+1,
                "accepted":len(accepted), "families":len({r["family"] for r in accepted})})
    manifest = {
        "protocol": PROTOCOL, "source": "SAT Competition 2025 via Global Benchmark Database",
        "source_index": INDEX, "selection": "hash/family only, pre-run; no solver labels",
        "only_new_2025_submissions": True,
        "requested": args.count, "attempt_limit": args.max_attempts,
        "sources": sorted(accepted, key=lambda x: x["sha256"]),
        "rejects": dict(rejects),
    }
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    n = len(accepted)
    families = len({r["family"] for r in accepted})
    M.emit("ROUTER_V2_MATERIAL_FINAL", {"originals":n, "families":families, "rejected":dict(rejects)})
    if n < min(args.count, 24) or families < 10:
        raise RuntimeError("Refuse underpowered holdout: %d originals, %d families" % (n, families))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--count", type=int, default=64)
    p.add_argument("--max-attempts", type=int, default=165)
    a = p.parse_args()
    if a.count < 24 or a.max_attempts < a.count or a.max_attempts > 350:
        p.error("Require count>=24, count<=max-attempts<=350")
    prepare(a)

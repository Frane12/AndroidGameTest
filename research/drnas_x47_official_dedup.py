#!/usr/bin/env python3
"""Repair *selection only* for the separate X47 LONG official retrospective job.

SAT2024's archive contains duplicate original CNF bytes under different
file names. Deduplicate by the SHA-256 of the decompressed ORIGINAL CNF
BEFORE benchmarking, never by native result, difficulty, or solve time.

Imports the unchanged benchmark harness, monkey-patching only the loader.
"""
from __future__ import annotations
import bz2
import gzip
import hashlib
import lzma
from pathlib import Path
import random

import drnas_x47_long_bench as B

def official_sources(count):
    from remotezip import RemoteZip
    with RemoteZip(B.OFFICIAL_ARCHIVE,timeout=95) as z:
        entries=sorted((entry for entry in z.infolist()
            if not entry.is_dir()
            and entry.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
            and 50000<=entry.file_size<=800000),
            key=lambda e:(e.file_size,e.filename))
        families={}
        for entry in entries:
            family=B.official_family(entry.filename)
            if family not in families:families[family]=entry
        universe=list(families.values())
        count_candidates=min(len(universe),max(8*count,160))
        if count_candidates<count:raise RuntimeError("too few official source families")
        candidates=[universe[min(len(universe)-1,
                round((i+.5)*len(universe)/count_candidates))]
                for i in range(count_candidates)]
        random.Random(20261113).shuffle(candidates)
        selected=[];seen_sha=set();skipped=0
        for entry in candidates:
            if len(selected)>=count:break
            try:
                raw=z.read(entry)
                if entry.filename.endswith(".xz"):raw=lzma.decompress(raw)
                elif entry.filename.endswith(".gz"):raw=gzip.decompress(raw)
                elif entry.filename.endswith(".bz2"):raw=bz2.decompress(raw)
            except (OSError,ValueError,EOFError) as exc:
                B.emit("X47_OFFICIAL_RETRY_SKIP",{"entry":entry.filename,
                    "reason":"read_failure","message":str(exc)[:90]})
                skipped+=1
                continue
            if not 100<=len(raw)<=18000000:skipped+=1;continue
            try:txt=raw.decode("ascii")
            except UnicodeError:skipped+=1;continue
            header=[line.split() for line in txt.splitlines()
                if line.lstrip().startswith("p cnf ")]
            if len(header)!=1 or len(header[0])!=4:skipped+=1;continue
            try:n=int(header[0][2]);m=int(header[0][3])
            except ValueError:skipped+=1;continue
            if not (1<=n<=30000 and 1<=m<=900000):skipped+=1;continue
            original_sha=hashlib.sha256(raw).hexdigest()
            if original_sha in seen_sha:
                skipped+=1
                continue
            seen_sha.add(original_sha)
            selected.append({"kind":"official_retrospective",
              "family":B.official_family(entry.filename),"source_id":len(selected),
              "nvars":n,"nclauses":m,"cert":"OFFICIAL_UNSAT_UNVERIFIED",
              "content":txt,"archive_path":entry.filename,
              "archive_url":B.OFFICIAL_ARCHIVE,"sha256":original_sha,
              "filename":f"official_{len(selected):02d}.cnf"})
        if len(selected)!=count:
            raise RuntimeError(f"deduplicated official SAT2024 selection got {len(selected)}/{count} originals; skipped {skipped}")
        if len({x["family"] for x in selected})!=count:
            raise AssertionError("duplicate normalized name family")
        B.emit("X47_OFFICIAL_RETRY_SELECTION",{"selected":len(selected),
            "original_SHA_distinct":True,"family_distinct":True,
            "rejected_duplicate_or_invalid":skipped,
            "selection_method":"size-quantile source families randomized before outcome"})
        return selected

if __name__=="__main__":
    B.official_sources=official_sources
    B.main()

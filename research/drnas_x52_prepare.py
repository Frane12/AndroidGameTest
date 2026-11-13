#!/usr/bin/env python3
"""Outcome-blind SHA-deduplicated SAT2024 input selection with family round robin."""
import argparse,bz2,gzip,hashlib,json,lzma,random,collections
from pathlib import Path
from remotezip import RemoteZip
from drnas_x47_long_bench import OFFICIAL_ARCHIVE,official_family

MAX_RAW=18_000_000
def decode_member(name,data):
    if name.endswith(".xz"):
        d=lzma.LZMADecompressor()
        out=d.decompress(data,max_length=MAX_RAW+1)
        if not d.eof:raise ValueError("oversized or truncated xz")
    elif name.endswith(".gz"):
        out=gzip.decompress(data)
    elif name.endswith(".bz2"):
        out=bz2.decompress(data)
    else:out=data
    if not 100<=len(out)<=MAX_RAW:raise ValueError("size bound")
    txt=out.decode("ascii")
    headers=[line.split() for line in txt.splitlines() if line.lstrip().startswith("p cnf ")]
    if len(headers)!=1 or len(headers[0])!=4:raise ValueError("DIMACS header")
    n,m=map(int,headers[0][2:])
    if not (1<=n<=30000 and 1<=m<=900000):raise ValueError("DIMACS dimensions")
    return out,n,m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--count",type=int,default=100)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.count<1 or a.out.exists():raise RuntimeError("invalid count or preexisting directory")
    groups=collections.defaultdict(list)
    with RemoteZip(OFFICIAL_ARCHIVE,timeout=95) as z:
        for entry in z.infolist():
            if entry.is_dir() or not entry.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2")):continue
            if not 15_000<=entry.file_size<=3_000_000:continue
            groups[official_family(entry.filename)].append(entry)
        for group in groups.values():group.sort(key=lambda e:(e.file_size,e.filename))
        order=sorted(groups)
        random.Random(20261113).shuffle(order)
        selected=[];seen=set();rejections=collections.Counter()
        for depth in range(max(map(len,groups.values()),default=0)):
            for family in order:
                group=groups[family]
                if depth>=len(group):continue
                e=group[depth]
                try:
                    raw,n,m=decode_member(e.filename,z.read(e))
                except (OSError,EOFError,UnicodeError,ValueError,lzma.LZMAError) as exc:
                    rejections[type(exc).__name__]+=1;continue
                h=hashlib.sha256(raw).hexdigest()
                if h in seen:rejections["duplicate_SHA"]+=1;continue
                seen.add(h)
                selected.append({"source_id":len(selected),"sha256":h,"family":family,
                                 "archive_path":e.filename,"nvars":n,"nclauses":m,"content":raw})
                if len(selected)>=a.count:break
            if len(selected)>=a.count:break
    if len(selected)!=a.count:
        raise RuntimeError(f"only {len(selected)}/{a.count} source SHAs found; family_groups={len(groups)}, rejections={rejections}")
    a.out.mkdir(parents=True)
    manifest={"protocol":"X52-original-SAT2024-selection-v2","dataset":"SAT Competition 2024 main archive retrospective",
              "selection":"deterministic family-round-robin; byte SHA dedup; no solver-outcome screening",
              "source_families":len({s["family"] for s in selected}),"sources":[]}
    for i,s in enumerate(selected):
        raw=s["content"];h=s["sha256"]
        path=a.out/f"{i:03d}.cnf"
        path.write_bytes(raw)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==h
        manifest["sources"].append({"id":i,"file":path.name,"sha256":h,
            "family":s["family"],"archive_path":s["archive_path"],
            "nvars":s["nvars"],"nclauses":s["nclauses"],"bytes":len(raw)})
    assert len(manifest["sources"])==a.count
    assert len({s["sha256"] for s in manifest["sources"]})==a.count
    (a.out/"source_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("X52_FROZEN_SOURCES",json.dumps({"selected":a.count,"source_families":manifest["source_families"],
          "unique_sha":a.count,"total_raw_bytes":sum(x["bytes"] for x in manifest["sources"]),
          "preselection_rejections":dict(rejections)}),flush=True)
if __name__=="__main__":main()

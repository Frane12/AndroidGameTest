#!/usr/bin/env python3
"""REAL-LEARN2: acquire *complete* original CNFs, split-lock family, select fresh sources.

Never select by SAT/UNSAT answers or solver timing. The immutable REAL1 split
and REAL2 catalog are consulted BEFORE selecting any new training instance.
Only bounded ZIP member reads, not entire multigigabyte public archives.
"""
import argparse
import bz2
import collections
import contextlib
import gzip
import hashlib
import io
import json
import lzma
import random
from pathlib import Path
from remotezip import RemoteZip
from drnas_x47_long_bench import OFFICIAL_ARCHIVE, official_family

ARCHIVES = {
    "2024": OFFICIAL_ARCHIVE,
    "2023": "https://zenodo.org/records/11426992/files/sat-competition-2023-main-benchmarks.zip?download=1",
}
MAX_RAW = 16_000_000
MAX_VARS = 500_000
MAX_CLAUSES = 1_200_000
ROLES = ("train", "validation", "holdout")
ROLE_TARGETS = {"train": .70, "validation": .15, "holdout": .15}
TIER_TARGETS = {"small": .65, "medium": .25, "large": .10}

def h(x):
    return hashlib.sha256(x).hexdigest()

def split_for_family(family, existing):
    if family in existing:
        return existing[family]
    n=int(h(("real2-permanent-family-role-v1|"+family).encode())[:8],16)%100
    return "train" if n<70 else "validation" if n<85 else "holdout"

def tier(size):
    return "small" if size<=120_000 else "medium" if size<=600_000 else "large"

def decode(name, blob):
    if name.endswith(".xz"):
        z=lzma.LZMADecompressor()
        raw=z.decompress(blob, max_length=MAX_RAW+1)
        if not z.eof:
            raise ValueError("oversized or incomplete xz member")
    elif name.endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as z:
            raw=z.read(MAX_RAW+1)
    elif name.endswith(".bz2"):
        z=bz2.BZ2Decompressor()
        raw=z.decompress(blob,max_length=MAX_RAW+1)
        if not z.eof:
            raise ValueError("oversized or incomplete bz2 member")
    else:
        raw=blob
    if not 40 <= len(raw)<=MAX_RAW:
        raise ValueError("source byte bound exceeded")
    return raw

def validate_complete_dimacs(raw):
    """Full parse, not just header. Checks every clause, terminator, literal bound."""
    text=raw.decode("ascii")
    header=False;n=m=0;clauses=0;inside=0;semantic=hashlib.sha256()
    header_count=0;max_width=0;total_lits=0
    for line in io.StringIO(text):
        line=line.strip()
        if not line or line.startswith(("c","%")):
            continue
        if line.startswith("p"):
            fields=line.split()
            if header or fields[:2]!=["p","cnf"] or len(fields)!=4:
                raise ValueError("invalid or repeated DIMACS header")
            n,m=map(int,fields[2:])
            if not 1<=n<=MAX_VARS or not 1<=m<=MAX_CLAUSES:
                raise ValueError("DIMACS dimensions outside bounds")
            semantic.update(("p cnf "+str(n)+" "+str(m)+"\n").encode())
            header=True;header_count+=1
            continue
        if not header:
            raise ValueError("clause before header")
        for token in line.split():
            lit=int(token)
            if lit==0:
                clauses+=1
                max_width=max(max_width,inside)
                inside=0
                semantic.update(b"0\n")
                if clauses>m:
                    raise ValueError("too many clauses")
            else:
                if clauses>=m or abs(lit)>n:
                    raise ValueError("invalid literal or trailing data")
                inside+=1
                total_lits+=1
                semantic.update(str(lit).encode()+b" ")
    if header_count!=1 or clauses!=m or inside:
        raise ValueError("incomplete DIMACS clauses")
    return {"nvars":n,"nclauses":m,"semantic_sha":semantic.hexdigest(),
            "n_literals":total_lits,"max_width":max_width}

def prior_sets(prior_state, prior_real1):
    seen_sha=set();seen_sem=set();family_roles={}
    if prior_real1:
        initial=json.loads(Path(prior_real1).read_text())
        for r in initial["sources"]:
            seen_sha.add(r["sha256"])
            fam=r["family"];role=r["split"]
            if fam in family_roles and family_roles[fam]!=role:
                raise ValueError("REAL1 family collision across splits")
            family_roles[fam]=role
    if prior_state and Path(prior_state).is_file():
        state=json.loads(Path(prior_state).read_text())
        for r in state.get("sources",[]):
            seen_sha.add(r["sha256"])
            if r.get("semantic_sha"):seen_sem.add(r["semantic_sha"])
            fam=r["family"];role=r["split"]
            if fam in family_roles and family_roles[fam]!=role:
                raise ValueError("cross-cycle family split leakage")
            family_roles[fam]=role
    return seen_sha,seen_sem,family_roles

def order_entries(items):
    # Family round robin, small first inside each family; deterministic.
    groups=collections.defaultdict(list)
    for item in items:groups[item["family"]].append(item)
    for group in groups.values():
        group.sort(key=lambda i:(i["zip_size"], i["year"],i["name"]))
    ordered_families=sorted(groups,key=lambda f:h(("real2-cycle-family|"+f).encode()))
    out=[]
    for depth in range(max((len(group) for group in groups.values()),default=0)):
        for family in ordered_families:
            if depth<len(groups[family]):out.append(groups[family][depth])
    return out

def select(args):
    if args.count<60 or args.shards<1 or args.out.exists():
        raise ValueError("invalid count/shards or existing destination")
    old_sha,old_sem,permanent=prior_sets(args.state,args.real1_splits)
    raw_items=[]
    connections={}
    errors={}
    with contextlib.ExitStack() as resources:
        for year,url in ARCHIVES.items():
            try:
                archive=resources.enter_context(RemoteZip(url,timeout=95))
                connections[year]=archive
            except Exception as exc:
                errors[year]=str(exc)[:180]
                continue
            for e in archive.infolist():
                name=e.filename
                if e.is_dir() or not name.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2")):
                    continue
                if not 80<=e.file_size<=4_000_000:
                    continue
                family=official_family(name)
                role=split_for_family(family,permanent)
                raw_items.append({"year":year,"name":name,"zip_size":e.file_size,
                                  "family":family,"split":role,"tier":tier(e.file_size),
                                  "entry":e})
        if not raw_items:
            raise RuntimeError("no remote original SAT CNF archive accessible: "+str(errors))
        buckets=collections.defaultdict(list)
        for i in raw_items:
            buckets[(i["split"],i["tier"])].append(i)
        for k in buckets:
            buckets[k]=order_entries(buckets[k])
        candidates=[];used_entries=set()
        role_lists={role:[] for role in ROLES}
        def queue(role,t,limit):
            added=0
            for item in buckets.get((role,t),[]):
                identity=(item["year"],item["name"])
                if identity in used_entries:continue
                used_entries.add(identity);role_lists[role].append(item);added+=1
                if added>=limit:return
        for role in ROLES:
            for t in ("small","medium","large"):
                target=round(args.count*ROLE_TARGETS[role]*TIER_TARGETS[t])
                if target>0:queue(role,t,target*3+10)
        for role in ROLES:
            for t in ("small","medium","large"):
                queue(role,t,args.count*3)
        indices={role:0 for role in ROLES}
        plan={role:0 for role in ROLES}
        while any(indices[r]<len(role_lists[r]) for r in ROLES):
            available=[r for r in ROLES if indices[r]<len(role_lists[r])]
            role=min(available,key=lambda r:(plan[r]/max(1,ROLE_TARGETS[r]),ROLES.index(r)))
            candidates.append(role_lists[role][indices[role]])
            indices[role]+=1
            plan[role]+=1
        selected=[];reject=collections.Counter();by_role=collections.Counter()
        max_attempts=min(len(candidates),max(args.count*7,1200))
        for item in candidates[:max_attempts]:
            if len(selected)>=args.count or sum(x["bytes"] for x in selected)>=args.max_raw_bytes:
                break
            try:
                raw=decode(item["name"],connections[item["year"]].read(item["entry"]))
                sha=h(raw)
                if sha in old_sha:
                    reject["historical_sha"]+=1;continue
                parsed=validate_complete_dimacs(raw)
                if parsed["semantic_sha"] in old_sem:
                    reject["historical_semantic_sha"]+=1;continue
                if len(selected)+1<args.count and sum(x["bytes"] for x in selected)+len(raw)>args.max_raw_bytes:
                    reject["raw_byte_budget"]+=1;continue
            except (OSError,EOFError,UnicodeError,ValueError,lzma.LZMAError) as exc:
                reject[type(exc).__name__]+=1
                continue
            old_sha.add(sha);old_sem.add(parsed["semantic_sha"])
            permanent[item["family"]]=item["split"]
            s={"id":len(selected),"file":f"{len(selected):04d}.cnf",
               "sha256":sha, "family":item["family"],"split":item["split"],
               "archive_url":ARCHIVES[item["year"]],"archive_path":item["name"],
               "source_year":item["year"],"source_tier":item["tier"],
               "bytes":len(raw),**parsed,"content":raw}
            selected.append(s);by_role[s["split"]]+=1
        if len(selected)<max(80,args.count//2):
            raise RuntimeError("insufficient fresh originals: "+json.dumps({
                "selected":len(selected),"target":args.count,
                "archives":list(connections),"errors":errors,"rejections":reject}))
        if min(by_role.values())<10 or len(by_role)!=3:
            raise RuntimeError("split imbalance: "+json.dumps(by_role))
        args.out.mkdir(parents=True)
        sources_dir=args.out/"real2_source";sources_dir.mkdir()
        manifest=[]
        for s in selected:
            (sources_dir/s["file"]).write_bytes(s.pop("content"))
            assert h((sources_dir/s["file"]).read_bytes())==s["sha256"]
            manifest.append(s)
        role_counts={r:sum(v["split"]==r for v in manifest) for r in ROLES}
        family_counts={r:len({v["family"] for v in manifest if v["split"]==r}) for r in ROLES}
        split_manifest={
            "protocol":"DRNAS-REAL-LEARN1-v1",
            "extension":"DRNAS-REAL-LEARN2-v1",
            "dataset":"Original SAT Competition 2023+2024 main track retrospective",
            "source_count":len(manifest),"family_count":len({x["family"] for x in manifest}),
            "split_counts":role_counts,"split_families":family_counts,
            "sources":manifest}
        (args.out/"real2_splits.json").write_text(json.dumps(split_manifest,sort_keys=True,indent=2)+"\n")
        (args.out/"catalog_delta.json").write_text(json.dumps({"sources":manifest},sort_keys=True,indent=2)+"\n")
        stats={"selected":len(manifest),"target":args.count,
               "raw_bytes":sum(v["bytes"] for v in manifest),
               "split_counts":role_counts,"split_families":family_counts,
               "archives":dict(collections.Counter(v["source_year"] for v in manifest)),
               "tiers":dict(collections.Counter(v["source_tier"] for v in manifest)),
               "rejected":dict(reject),"remote_errors":errors}
        (args.out/"material_report.json").write_text(json.dumps(stats,sort_keys=True,indent=2)+"\n")
        emit("REAL2_COMPLETE_MATERIAL",stats)
        # Separate source packages so each job reads its own ~1/8 share, not all input bytes.
        for shard in range(args.shards):
            package=args.out/f"shard_{shard}"
            pdir=package/"real2_source";pdir.mkdir(parents=True)
            (package/"real2_splits.json").write_text(json.dumps(split_manifest,sort_keys=True)+"\n")
            for role in ("trainval","holdout"):
                rr=sorted((s for s in manifest if (s["split"]=="holdout")==(role=="holdout")),key=lambda x:x["sha256"])
                for i,s in enumerate(rr):
                    if i%args.shards==shard:
                        (pdir/s["file"]).hardlink_to(sources_dir/s["file"])
        return stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--count",type=int,default=320)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--state",type=Path)
    p.add_argument("--real1-splits",type=Path)
    p.add_argument("--shards",type=int,default=8)
    p.add_argument("--max-raw-bytes",type=int,default=650_000_000)
    a=p.parse_args()
    select(a)

if __name__=="__main__":
    main()

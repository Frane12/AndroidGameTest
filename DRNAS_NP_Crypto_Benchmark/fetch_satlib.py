#!/usr/bin/env python3
"""Download and sample ORIGINAL SATLIB benchmarks. Never generate a SAT instance.

8 public source archives x 20 fixed-seed randomly selected original CNFs = 160.
Archives: https://www.cs.ubc.ca/~hoos/SATLIB/benchm.html
Selection is deterministic and performed before solving; no cherry-picking.
"""
import csv,hashlib,io,random,tarfile,time,urllib.request
from pathlib import Path
from drnas_np_lab import read_dimacs

BASE="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT"
SOURCES=[
 ("uf20-91","RND3SAT/uf20-91.tar.gz","SAT"),
 ("uf50-218","RND3SAT/uf50-218.tar.gz","SAT"),
 ("uuf50-218","RND3SAT/uuf50-218.tar.gz","UNSAT"),
 ("uf75-325","RND3SAT/uf75-325.tar.gz","SAT"),
 ("uuf75-325","RND3SAT/uuf75-325.tar.gz","UNSAT"),
 ("uf100-430","RND3SAT/uf100-430.tar.gz","SAT"),
 ("uuf100-430","RND3SAT/uuf100-430.tar.gz","UNSAT"),
 ("flat30-60","GCP/flat30-60.tar.gz","SAT")
]
def fetch(url):
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-NP-Lab/0.3-research"})
            with urllib.request.urlopen(req,timeout=50) as r:
                return r.read(70_000_001)
        except Exception as exc:
            last=exc
            time.sleep(2*(attempt+1))
    raise RuntimeError(f"Cannot download authoritative SATLIB archive: {url} ({last})")
def build(destination="external_cases",per_group=20):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    (out/"archives.sha256").write_text("")
    (out/"originals").mkdir(exist_ok=True)
    records=[]; hashes=set()
    for group_idx,(group,path,expected) in enumerate(SOURCES):
        url=BASE+"/"+path;blob=fetch(url)
        if len(blob)>70_000_000:raise RuntimeError("Archive too large for safe run")
        archive_sha=hashlib.sha256(blob).hexdigest()
        with (out/"archives.sha256").open("a") as f:f.write(f"{archive_sha}  {url}\n")
        with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as tar:
            members=[m for m in tar.getmembers()
                     if m.isfile() and m.name.lower().endswith(".cnf") and m.size<3_000_000]
            members.sort(key=lambda m:m.name)
            if len(members)<per_group:raise AssertionError(f"{group}: only {len(members)} candidates")
            selected=random.Random(20261031+group_idx*701).sample(members,per_group)
            for member in selected:
                raw=tar.extractfile(member).read()
                h=hashlib.sha256(raw).hexdigest()
                if h in hashes:raise AssertionError(f"Duplicate CNF across corpus: {member.name}")
                hashes.add(h)
                i=len(records)+1;case_id=f"satlib_{i:04d}";cnf_path=out/f"{case_id}.cnf"
                (out/"originals"/f"{case_id}.original.cnf").write_bytes(raw)
                # Parse the original SATLIB '%' EOF correctly; serialize canonical
                # DIMACS without its terminator, which CryptoMiniSat rejects.
                # BOTH solvers receive these IDENTICAL, equivalence-preserving CNF bytes.
                cnf_path.write_bytes(raw)
                n,clauses=read_dimacs(cnf_path)
                if n<1 or not clauses:raise ValueError(f"Empty or malformed CNF: {member.name}")
                if max((abs(lit) for c in clauses for lit in c),default=0)>n:raise ValueError("Bad DIMACS")
                canonical=(f"c canonical DIMACS of SATLIB original {member.name}\n"
                           +f"p cnf {n} {len(clauses)}\n"
                           +"".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
                cnf_path.write_text(canonical,encoding="utf-8")
                canonical_sha=hashlib.sha256(cnf_path.read_bytes()).hexdigest()
                n2,c2=read_dimacs(cnf_path)
                assert n2==n and c2==clauses
                records.append(dict(case_id=case_id,family=group,n=n,m=len(clauses),
                    seed="SATLIB_original",expected=expected,
                    description="Independent SATLIB source; canonical DIMACS sent identically to both solvers",
                    source_url=url,original_name=member.name,archive_sha256=archive_sha,
                    source_sha256=h,cnf_sha256=canonical_sha))
        print(f"Fetched {group}: {per_group} original CNFs; archive sha256={archive_sha[:16]}",flush=True)
    assert len(records)==8*per_group and len(records)==160
    with (out/"manifest.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    print(f"READY: {len(records)} original unmodified SATLIB CNFs",flush=True)
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--dir",default="external_cases")
    args=p.parse_args();build(args.dir)

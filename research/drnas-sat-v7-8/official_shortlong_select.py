#!/usr/bin/env python3
"""Freeze a small ORIGINAL SAT Competition 2026, file-size-bounded sample.
Baseline official results are used ONLY to stratify the selection, never
as features/prediction targets. Records all rejected candidates. Train/test
split frozen BEFORE any experimental solver execution.
"""
import bz2,csv,gzip,hashlib,json,lzma,math,sys,tempfile,urllib.request
from collections import defaultdict
from pathlib import Path
REV="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
SCORES_GIT_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
SALT="DRNAS-SAT-official-2026-short-long-predict-v1-FROZEN-1031"
QUOTAS={"sat_fast":3,"unsat_fast":2,"sat_mid":3,"unsat_mid":2,
        "sat_slow":4,"unsat_slow":4}
# Hard limits to keep GitHub Actions runners reliable: not a representative sample.
RAW_CAP=64*1024*1024
CNF_CAP=48*1024*1024
VARIABLE_CAP=500000
CLAUSE_CAP=2000000
EXCLUDED={"4ae685a11b5cecca76dc3d463481ce92",
          "43d40ced32b5be08814ef24f97379654",
          "0c9da400944b002f90fd385d4fdab385"}
def hashorder(s):
    return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
def download_and_features(case,save_to=None):
    url="https://benchmark-database.de/file/"+case
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-SAT-shortlong-2026/1.0"})
    with tempfile.TemporaryDirectory() as t:
        raw=Path(t)/"compressed"
        with urllib.request.urlopen(req,timeout=75) as response,raw.open("wb") as f:
            size=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>RAW_CAP:raise ValueError("compressed > 64 MiB")
                f.write(chunk)
        with raw.open("rb") as f:magic=f.read(6)
        opener=(lzma.open if magic.startswith(b"\xfd7zXZ\x00") else
                gzip.open if magic.startswith(b"\x1f\x8b") else
                bz2.open if magic.startswith(b"BZh") else open)
        digest=hashlib.sha256();unpacked=0
        # Retain up to 48 MiB after checking limit per chunk.
        with opener(raw,"rb") as f:
            parts=[]
            while True:
                chunk=f.read(1024*1024)
                if not chunk:break
                unpacked+=len(chunk)
                if unpacked>CNF_CAP:raise ValueError("DIMACS > 48 MiB")
                digest.update(chunk);parts.append(chunk)
        payload=b"".join(parts)
    # Parse standard DIMACS. Do not use official solver result in features.
    header=None
    clauses=0
    pending=[]
    widths={2:0,3:0,4:0}
    lit_total=0; max_width=0; pos=neg=None
    for line in payload.splitlines():
        line=line.strip()
        if not line or line.startswith(b"c") or line.startswith(b"%"):continue
        if line.startswith(b"p "):
            if header is not None:raise ValueError("duplicate DIMACS header")
            q=line.split()
            if len(q)<4 or q[1]!=b"cnf":raise ValueError("not a CNF header")
            n=int(q[2]);m=int(q[3])
            if n<1 or n>VARIABLE_CAP or m<1 or m>CLAUSE_CAP:
                raise ValueError("DIMACS header size exceeds bounds")
            header=(n,m);pos=[0]*(n+1);neg=[0]*(n+1)
            continue
        if header is None:raise ValueError("missing header")
        # Standard DIMACS permits wrapping clauses across physical lines.
        for word in line.split():
            lit=int(word)
            if lit:
                v=abs(lit)
                if v>header[0]:raise ValueError("variable out of range")
                if lit>0:pos[v]+=1
                else:neg[v]+=1
                pending.append(lit)
            else:
                width=len(pending)
                if width==0:raise ValueError("empty clause not supported in preflight")
                max_width=max(max_width,width);lit_total+=width
                if width in widths:widths[width]+=1
                clauses+=1
                if clauses>header[1]:raise ValueError("excess clauses")
                pending.clear()
    if header is None or clauses!=header[1] or pending:
        raise ValueError("invalid clause count")
    n,m=header
    active=[i for i in range(1,n+1) if pos[i]+neg[i]>0]
    if not active:raise ValueError("no variable occurrences")
    imbalance=sum(abs(pos[i]-neg[i]) for i in active)/max(1,lit_total)
    majority=sum(1 for i in active if pos[i]+neg[i]>=6 and
                 abs(pos[i]-neg[i])*100>=15*(pos[i]+neg[i]) and pos[i]!=neg[i])
    features={
      "log_vars":round(math.log1p(n),8),
      "log_clauses":round(math.log1p(m),8),
      "clause_var":round(m/n,8),
      "avg_width":round(lit_total/m,8),
      "binary_frac":round(widths[2]/m,8),
      "ternary_frac":round(widths[3]/m,8),
      "four_frac":round(widths[4]/m,8),
      "polarity_imbalance":round(imbalance,8),
      "majority_coverage":round(majority/len(active),8)}
    if save_to is not None:Path(save_to).write_bytes(payload)
    return {"id":case,"source_url":url,"sha256":digest.hexdigest(),
            "cnf_bytes":unpacked,"variables":n,"clauses":m,
            "max_width":max_width,"features":features}
def main():
    official=Path("official_scores.csv")
    with official.open(newline="",encoding="utf8") as f:rows=list(csv.DictReader(f))
    baseline=[r for r in rows if r["solverid"]=="biere_cadical3[main]"]
    assert len(baseline)==400,len(baseline)
    pools=defaultdict(list)
    for row in baseline:
        if row["status"] not in ("sat-verified","unsat-verified"):continue
        id=row["instanceid"]
        if id in EXCLUDED:continue
        sec=float(row["runtime"])
        grade=("fast" if sec<5 else "mid" if sec<30 else "slow" if sec<=180 else None)
        if not grade:continue
        label="sat" if row["status"]=="sat-verified" else "unsat"
        pools[label+"_"+grade].append(dict(id=id,official_label=label.upper(),
                               grade=grade,official_baseline_s=sec))
    attempts=[];cases=[]
    for stratum,needed in QUOTAS.items():
        candidates=sorted(pools[stratum],key=lambda row:hashorder(stratum+"/"+row["id"]))
        got=0
        for row in candidates:
            try:
                info=download_and_features(row["id"])
            except Exception as e:
                attempts.append({"id":row["id"],"stratum":stratum,
                                 "accepted":False,"reason":str(e)})
                print("OFFICIAL_SKIP",stratum,row["id"],str(e),flush=True)
                continue
            accepted={**row,**info,"stratum":stratum}
            # Alternating holdout assignment, balanced across strata.
            # The two odd-sized strata use opposite starting parity.
            parity=(1 if stratum=="sat_mid" else 0)
            accepted["split"]="train" if (got+parity)%2==0 else "holdout"
            cases.append(accepted)
            got+=1
            attempts.append({"id":row["id"],"stratum":stratum,"accepted":True})
            print("OFFICIAL_ACCEPT",stratum,accepted["split"],row["id"],
                  info["cnf_bytes"],info["sha256"],flush=True)
            if got==needed:break
        if got!=needed:
            raise RuntimeError(f"Incomplete frozen selection: {stratum} got {got}/{needed}")
    assert len(cases)==18
    assert len({x["id"] for x in cases})==18
    assert sum(x["split"]=="train" for x in cases)==9
    assert sum(x["split"]=="holdout" for x in cases)==9
    # Interleave expensive/cheap strata among jobs for balanced shard makespan.
    cases=sorted(cases,key=lambda x:hashorder("schedule/"+x["id"]))
    manifest={"protocol":SALT,"scores_git_blob":SCORES_GIT_BLOB,
              "official_commit":REV,"selection":"deterministic from official CaDiCaL 2026 times; size-bounded",
              "quotas":QUOTAS,"raw_max_bytes":RAW_CAP,"cnf_max_bytes":CNF_CAP,
              "rejected_or_accepted_candidates":attempts,
              "warnings":["File-size-selected subset, NOT representative of SAT Competition 2026",
                          "Official baseline runtimes used solely for stratification",
                          "No DRNAS timings used to select or split cases",
                          "Official labels known; this is not a fully blind holdout",
                          "UNSAT matches official label; no separate proof certificate"],
              "cases":cases}
    out=Path("official_shortlong_manifest.json")
    out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("FROZEN_OFFICIAL_18",len(cases),
          "manifest_sha256",hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":main()

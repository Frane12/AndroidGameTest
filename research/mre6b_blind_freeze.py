#!/usr/bin/env python3
"""DRNAS MRE6b official 2026 source-disjoint prospective freeze.

Selection is decided by salted official GBD identity, verified published
SAT/UNSAT status and precommitted resource-size limits ONLY. No solver
times, XOR structure, equality availability or CPU labels inform inclusion.

Known historical source registries:
  - R63 official freeze full source-scan log (run 41707669490)
  - R81 official freeze full source-scan log (run 41752571755)
  - R32p pinned official identities
  - R82 2026 prospective freeze first 220 SHA-ranked GBD candidates
  - all 32-char official IDs and 64-char source digests visibly present in
    this repository's tracked historical research/experiments scripts.
These are the explicitly verified exclusions; this is NOT a guarantee
against unrecorded legacy experiments. Frozen manifest exposes checks.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,pathlib,re,subprocess,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52

PROTO="DRNAS-MRE6B-SAT2026-UNSEEN-GBD-8OFFICIAL-4ARM-2REP-v1"
SALT="DRNAS-MRE6B-PROTOCOL-LOCKED-SAT2026-UNUSED-BEFORE-CPU-20261108"
TARGET,MIN_READY,MAX_FETCH=8,4,85
MAX_RAW=10*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS,MAX_CLAUSES=12000,35000
STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}
PRIOR=pathlib.Path("research/mre6b_official_prior_gbd.txt")
ROOT=pathlib.Path("mre6b_blind")


def need(ok,msg):
    if not ok:raise RuntimeError("MRE6B_BLIND_FREEZE_FAIL_CLOSED "+str(msg))

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def persist(p,x):
    pathlib.Path(p).write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def inspect_repo_ids(gbds):
    # Metadata-only: no reading remote incumbent CPU outcomes.
    ids=set()
    old_sha=set()
    try:
        out=subprocess.run(
          ["git","grep","-I","-E","-oh","[[:xdigit:]]{32}|[[:xdigit:]]{64}",
           "--","research","experiments"],
          capture_output=True,text=True,check=False)
        if out.returncode in (0,1):
            for s in out.stdout.lower().splitlines():
                if re.fullmatch(r"[0-9a-f]{32}",s) and s in gbds:ids.add(s)
                if re.fullmatch(r"[0-9a-f]{64}",s):old_sha.add(s)
    except Exception:pass
    return ids,old_sha

def freeze(root=ROOT):
    root=pathlib.Path(root)
    root.mkdir(parents=True,exist_ok=True)
    raw_index=r52.fetch_bytes(r52.URI,100000)
    official=[u.strip().rsplit("/",1)[-1] for u in raw_index.decode().strip().splitlines()]
    need(len(official)==400 and len(set(official))==400,"official 2026 Main index drift")
    official_set=set(official)
    csv_raw=r52.fetch_bytes(r52.SCORES,24*1024*1024)
    statuses={r["instanceid"]:r["status"] for r in csv.DictReader(io.StringIO(csv_raw.decode()))
              if r.get("solverid")=="biere_cadical3[main]"}
    need(len(statuses)==400,"official verified status source not 400")
    need(PRIOR.exists(),"historical registry file missing")
    frozen=set()
    for item in PRIOR.read_text().splitlines():
        item=item.strip()
        if not item or item.startswith("#"):continue
        need(re.fullmatch(r"[0-9a-f]{32}",item),"bad historical GBD")
        frozen.add(item)
    repo_ids,old_sha=inspect_repo_ids(official_set)
    # R82 included 2026 originals drawn from the first <=220 eligible
    # official 2026 candidates using its frozen 2026 SHA rank; exclude
    # ALL first 220 (even if too large) as a conservative superset.
    r82_first220=set(sorted(official,key=lambda g:hashlib.sha256(
        ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1"
         +"/2026/"+g).encode()).hexdigest())[:220])
    exclude=(frozen|repo_ids|r82_first220)
    need(len(exclude & official_set)>=220,"incomplete official prior exclusion")
    eligible=sorted((g for g in official if g not in exclude),
        key=lambda g:sha256((SALT+"|"+g).encode()))
    need(len(eligible)>=TARGET,"historical exclusion leaves too few sources")
    trace=[];selected=[];counts={"SAT":0,"UNSAT":0}
    r32p.CNF_LIMIT=MAX_PLAIN
    for g in eligible[:MAX_FETCH]:
        if len(selected)>=TARGET:break
        status=STATUS.get(statuses.get(g))
        log=dict(gbd=g,official_status=status)
        if status is None:
            log["action"]="unverified_official_verdict"
            trace.append(log)
            continue
        # Precommitted 4+4 status quotas, not based on runtime or structure.
        if counts[status]>=TARGET//2:
            log["action"]="balanced_status_quota_full"
            trace.append(log)
            continue
        path=root/(g+".cnf")
        try:
            compressed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=40)
            plain,method=r32p.decode(compressed)
            need(len(plain)<=MAX_PLAIN,"source exceeds 12MiB DIMACS")
            n,m=r32p.parse_dimacs_metadata(plain)
            need(n<=MAX_VARS and m<=MAX_CLAUSES,
                 "precommitted variable/clause resource limit")
            file_sha=sha256(plain)
            need(file_sha not in old_sha,
                 "source digest occurs in prior visible research metadata")
            path.write_bytes(plain)
            row=dict(gbd=g,filename=path.name,sha256=file_sha,
                 vars=n,clauses=m,bytes=len(plain),
                 raw_sha256=sha256(compressed),
                 raw_bytes=len(compressed),compression=method,
                 original_verified_status=status,
                 official_source_url="https://benchmark-database.de/file/"+g,
                 redirect_url=redirect,year=2026,
                 source_disjoint_from_declared_registry=True)
            counts[status]+=1
            selected.append(row)
            log.update(action="frozen_before_solving",sha256=file_sha,
                       n=n,m=m,bytes=len(plain))
        except Exception as e:
            path.unlink(missing_ok=True)
            log.update(action="excluded_input_size_fetch_or_integrity",
                       reason=(type(e).__name__+": "+str(e))[:160])
        trace.append(log)
        print("MRE6B_BLIND_SOURCE_SCAN",json.dumps(log,sort_keys=True),flush=True)
    need(len(selected)>=MIN_READY,
         "not enough independently fetched official sources within resource limit")
    need(len({x["gbd"] for x in selected})==len(selected) and
         len({x["sha256"] for x in selected})==len(selected),
         "duplicate original holdout source")
    for x in selected:
        need(sha256((root/x["filename"]).read_bytes())==x["sha256"],
             "frozen source SHA mismatch")
        need(x["gbd"] not in exclude,"historical source leaked")
    mask=hashlib.sha256("\n".join(sorted(exclude)).encode()).hexdigest()
    manifest=dict(protocol=PROTO,official_index=r52.URI,
        official_score_table=r52.SCORES,
        official_index_sha256=sha256(raw_index),
        official_scores_sha256=sha256(csv_raw),
        previous_registered_ids=len(exclude&official_set),
        historical_log_registry_sha256=sha256(PRIOR.read_bytes()),
        excluded_2026_r82_first220=220,
        historical_full_exhaustiveness_not_guaranteed=True,
        strict_disjoint_from_declared_prior_registry=True,
        original_source_count=len(selected),target_count=TARGET,
        shortfall=TARGET-len(selected),
        statuses=counts,cases=selected,selection_attempts=trace,
        selection_policy="salted GBD ID+published verdict balancing+input size; never XOR/equality or solve times",
        cap_s=18.0,repetitions=2,
        modes=("native_no_xor","xor","quotient_no_xor","quotient"),
        expectation="unknown performance; no runtime winner selection")
    persist(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in selected))
    print("MRE6B_BLIND_FREEZE_PASS",json.dumps(
       dict(sources=len(selected),status=counts,excluded=len(exclude&official_set),
            manifest_sha256=sha256((root/"manifest.json").read_bytes())),
       sort_keys=True),flush=True)

def verify(root=ROOT):
    root=pathlib.Path(root)
    mf=json.loads((root/"manifest.json").read_text())
    need(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET,
         "frozen manifest changed")
    need(len({x["gbd"] for x in mf["cases"]})==len(mf["cases"]),
         "duplicate GBD")
    for case in mf["cases"]:
        p=root/case["filename"]
        need(p.exists() and sha256(p.read_bytes())==case["sha256"] and
             p.stat().st_size==case["bytes"],"source SHA/size mismatch")
    print("MRE6B_BLIND_SOURCES_VERIFIED",len(mf["cases"]),flush=True)

def selftest():
    g="0"*32
    need(len(sha256((SALT+"|"+g).encode()))==64,"salted ranking")
    need(TARGET==8 and MIN_READY==4 and
         len(set(("native_no_xor","xor","quotient_no_xor","quotient")))==4,
         "protocol mutated")
    print("MRE6B_BLIND_FREEZE_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","freeze","verify"))
    a.add_argument("--root",default=str(ROOT))
    z=a.parse_args()
    if z.action=="selftest":selftest()
    elif z.action=="freeze":freeze(z.root)
    else:verify(z.root)

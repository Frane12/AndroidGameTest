#!/usr/bin/env python3
"""DRNAS C11b — official SAT2026 source-only freeze for frozen three-backend selector.

12 target originals, >=8 accepted, SAT/UNSAT status-stratified but NOT
chosen based on nvars, density, cost, Kissat/CaDiCaL observed outcomes or
other structural features. Exclude prior C9c 12 originals by SHA/GBD,
prior X5 3, C8D 19, and archived R82/MRE6b and repo SHA IDs.
Official status quotas are published pre-timing references, not proof of
UNSAT. This guarantees disjointness only w.r.t. explicitly indexed history.
"""
from __future__ import annotations
import collections,csv,hashlib,io,json,pathlib,re,sys
import c10b_official26_freeze as previous
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
PROTO="DRNAS-C11B-SAT2026-12SHA-SALTED-THREE-SOLVER-SOURCE-FREEZE-v2"
SALT="DRNAS-C11B-20261109-LOCKED-PRETEST-THREE-SOLVER-2026-v1"
ROOT=pathlib.Path("c11b_official")
PREVC10B=pathlib.Path("c11b_previous_c10b/c10b_official/manifest.json")
PREVC11A=pathlib.Path("c11a_reference/report.json")
TARGET=12;MIN_READY=5;MAX_ATTEMPTS=360
MAX_RAW=30*1024*1024
MAX_PLAIN=45*1024*1024
MAX_VARS=100000;MAX_CLAUSES=950000
MAX_PER_STATUS=9;MIN_PER_STATUS=0
REPS=2;CAP=60.0
STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}
C10B_PROTO="DRNAS-C10B-SAT2026-12SHA-SALTED-STATUS-ONLY-PRETEST-FREEZE-v2"
C11A_PROTO="DRNAS-C11A-39SHA-THREE-BACKEND-DEVELOPMENT-AUDIT-20261109-v1"
FROZEN_RULE="if 200<=nvars<=1500 and clauses/nvars<=60: cadical_noelim; elif nvars<=400 or clauses/nvars>=200 or (nvars>=25000 and clauses/nvars<=2): kissat; else: cadical"
def need(ok,why):
    if not ok:raise RuntimeError("C11B_SOURCE_FAIL_CLOSED "+str(why))
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for x in iter(lambda:f.read(1<<20),b""):h.update(x)
    return h.hexdigest()
def sha(data):return hashlib.sha256(data).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def history():
    # Reuse C10b's full chained C8D/C9c/R82/MRE6b/C10a historical
    # source exclusion, then add NEW C10b original SHA to avoid reuse.
    ids,old_sha,prior=previous.history()
    need(PREVC10B.is_file() and PREVC11A.is_file(),
         "C10b source-only manifest or C11a frozen policy report missing")
    last=json.loads(PREVC10B.read_text())
    policy=json.loads(PREVC11A.read_text())
    need(last["protocol"]==C10B_PROTO and last["source_count"]==8
         and last["SHA_original_frozen_before_ANY_solver_attempt"],
         "previous C10b frozen 8 SHA manifest changed")
    need(policy["protocol"]==C11A_PROTO and policy["source_SHA_count"]==39
         and policy["policy_frozen_for_C11b"]==FROZEN_RULE
         and policy["development_after_observing_C10b_600variable_exception"]
         and policy["no_auto_promotion"],
         "C11a pre-test policy not properly frozen")
    ids.update(x["gbd"] for x in last["cases"])
    old_sha.update(x["sha256"] for x in last["cases"])
    old_sha.update(x["sha256"] for x in policy["all_cases"])
    return ids,old_sha,dict(
        C10b_prior_source_manifest_SHA256=digest(PREVC10B),
        C11a_policy_SHA256=digest(PREVC11A),
        preceding_C10b_historical_hashes=prior)
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    indexraw=r52.fetch_bytes(r52.URI,100000)
    official=[x.strip().rsplit("/",1)[-1] for x in indexraw.decode().splitlines()
              if x.strip()]
    need(len(official)==400 and len(set(official))==400,
         "unexpected official 2026 original GBD count")
    scoresraw=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    status={row["instanceid"]:STATUS.get(row["status"])
            for row in csv.DictReader(io.StringIO(scoresraw.decode()))
            if row.get("solverid")=="biere_cadical3[main]"}
    need(len(status)==400,"missing full official SAT2026 prior status reference")
    ids,old_sha,checks=history()
    git_ids,git_sha=previous.previous.known.inspect_repo_ids(set(official))
    ids|=git_ids
    old_sha|=git_sha
    ids|={g for g in previous.previous.known.PRIOR.read_text().lower().split()
          if re.fullmatch("[0-9a-f]{32}",g)}
    ranked=sorted([g for g in official if g not in ids],
                 key=lambda g:sha((SALT+"|"+g).encode()))
    need(len(ranked)>=40,"too few source-disjoint official identities")
    counts=collections.Counter()
    chosen=[];audit=[]
    r32p.CNF_LIMIT=MAX_PLAIN
    for g in ranked[:MAX_ATTEMPTS]:
        if len(chosen)==TARGET:break
        s=status.get(g)
        record=dict(gbd=g,published_reference=s)
        if s not in ("SAT","UNSAT"):
            record["decision"]="SKIP_NOT_VERIFIED_PUBLISHED_REFERENCE"
            audit.append(record);continue
        if counts[s]>=MAX_PER_STATUS:
            record["decision"]="SKIP_PREDECLARED_STATUS_QUOTA"
            audit.append(record);continue
        p=ROOT/(g+".cnf")
        try:
            raw,_=r32p.request_url(
                "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=25)
            plain,kind=r32p.decode(raw)
            need(len(plain)<=MAX_PLAIN,"raw DIMACS above fixed size bound")
            n,m=r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARS and 0<m<=MAX_CLAUSES,
                 "CNF geometry exceeds preregistered limits")
            h=sha(plain)
            need(h not in old_sha and h not in
                 {c["sha256"] for c in chosen},
                 "duplicate previous original SHA")
            p.write_bytes(plain)
            chosen.append(dict(gbd=g,sha256=h,filename=p.name,
                bytes=len(plain),variables=n,clauses=m,status=s,
                raw_sha256=sha(raw),source_compression=kind,
                original_source_url="https://benchmark-database.de/file/"+g))
            counts[s]+=1
            record.update(decision="SOURCE_FROZEN_BEFORE_SOLVER",
                          original_SHA=h,nvars=n,nclauses=m)
        except Exception as e:
            p.unlink(missing_ok=True)
            record.update(decision="SOURCE_REJECTED_BEFORE_SOLVER",
                          reason=(type(e).__name__+": "+str(e))[:170])
        audit.append(record)
        print("C11B_SOURCE_SCAN",json.dumps(record,sort_keys=True),flush=True)
    need(len(chosen)>=MIN_READY and
         counts["SAT"]>=MIN_PER_STATUS and counts["UNSAT"]>=MIN_PER_STATUS,
         "source-only v2 minimum 5 new SHA originals not found")
    need(not ({x["sha256"] for x in chosen}&old_sha),
         "past original SHA reused")
    data=dict(protocol=PROTO,salt=SALT,source_count=len(chosen),
        requested_count=TARGET,min_ready=MIN_READY,
        predeclared_max_attempts=MAX_ATTEMPTS,
        min_per_status=MIN_PER_STATUS,max_per_status=MAX_PER_STATUS,
        source_quota_revision="v2 source-only: 5 SAT original SHA after v1 freeze failed without ANY solver trial; no UNSAT validity claim; threshold rule unchanged",
        status_counts=dict(counts),
        SHA_original_frozen_before_ANY_solver_attempt=True,
        history_disjoint_but_not_guaranteed_globally_unseen=True,
        no_source_selection_by_density_or_router_outcome=True,
        original_index_sha256=sha(indexraw),official_scores_sha256=sha(scoresraw),
        official_index_uri=r52.URI,official_scores_uri=r52.SCORES,
        exclusion_reference=checks,
        policy_string=FROZEN_RULE,
        cap_s=CAP,repeat_count=REPS,
        max_raw_bytes=MAX_RAW,max_plain_bytes=MAX_PLAIN,
        max_vars=MAX_VARS,max_clauses=MAX_CLAUSES,
        independent_UNSAT_LRAT=False,no_auto_promotion=True,
        cases=chosen,source_attempt_log=audit)
    save(ROOT/"manifest.json",data)
    (ROOT/"source.sha256").write_text("".join(
       x["sha256"]+"  "+x["filename"]+"\n" for x in chosen))
    print("C11B_SOURCE_FROZEN",json.dumps(dict(
       original_count=len(chosen),statuses=dict(counts),
       density_route_frozen_not_used_for_selection=True,
       manifest_sha256=digest(ROOT/"manifest.json"),
       source_rejected=sum(a["decision"]=="SOURCE_REJECTED_BEFORE_SOLVER"
                           for a in audit)),sort_keys=True),flush=True)
def cases():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    need(manifest["protocol"]==PROTO and manifest["policy_string"]==FROZEN_RULE
         and manifest["SHA_original_frozen_before_ANY_solver_attempt"]
         and manifest["cap_s"]==CAP and manifest["repeat_count"]==REPS,
         "source freeze parameters drifted")
    cc=manifest["cases"]
    count=collections.Counter(x["status"] for x in cc)
    need(MIN_READY<=len(cc)<=TARGET and all(count[k]>=MIN_PER_STATUS
              for k in ("SAT","UNSAT")),"source status balance changed")
    ids,old_sha,_=history()
    for c in cc:
        p=ROOT/c["filename"]
        need(c["gbd"] not in ids and c["sha256"] not in old_sha and
             p.is_file() and p.stat().st_size==c["bytes"] and
             digest(p)==c["sha256"],"source original SHA not safe")
    need(len({x["sha256"] for x in cc})==len(cc),
         "duplicate newly frozen original SHA")
    return cc
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify"))
    a=p.parse_args()
    if a.action=="freeze":freeze()
    else:
        c=cases()
        print("C11B_SOURCE_SHA_VERIFIED",len(c),flush=True)

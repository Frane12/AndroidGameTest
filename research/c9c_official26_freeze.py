#!/usr/bin/env python3
"""C9c source-only official SAT2026 prospective freeze BEFORE SAT attempts.

Preregistered: 12 target (6 SAT, 6 UNSAT), at least 10 distinct ORIGINAL
official 2026 GBD/SHA, no C9 19-SHA training or prior X5 3-SHA overlap.
Official published status is used for status stratification ONLY, not runtime.
Identity selected by salted SHA rank, source size cap precommitted, not
posthoc feature or solver runtime. Predeclared "small" nvars<=1500 rule is
NEVER used for inclusion or quotas. Not claimed to be globally unobserved.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,pathlib,re,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import mre6b_blind_freeze as known

PROTO="DRNAS-C9C-2026-FROZEN-12SHA-PUBLISHED-STATUS-BALANCED-v1"
SALT="C9C-20261108-LOCK-400OFFICIAL-ID-NO-C9-C9B-OUTCOMES"
ROOT=pathlib.Path("c9c_official")
X5=pathlib.Path("c9c_previous_x5")/"mre_x5_blind"/"manifest.json"
R82=pathlib.Path("c9c_previous_r82")/"world"/"manifest.json"
MRE6B=pathlib.Path("c9c_previous_mre6b")/"manifest.json"
C9=pathlib.Path("c9_reference")/"report.json"
TARGET=12
MIN_READY=10
MAX_ATTEMPT=380
MAX_RAW=30*1024*1024
MAX_PLAIN=45*1024*1024
MAX_VARS=100000
MAX_CLAUSES=950000
MAX_PER_STATUS=6
MIN_PER_STATUS=4
CAP=60.0
REPS=2
STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}
C9_TRAIN_PROTO="DRNAS-C9-LOFO-19SHA-SOURCE-ONLY-STUMP-6SOLVERS-NO-PILOT-v1"
X5_PROTO="DRNAS-MRE-X5-SAT2026-PROSPECTIVE-SHIFTED-SPREAD-3ARMS-4SEED-18S-v1"

def need(ok,why):
    if not ok:raise RuntimeError("C9C_SOURCE_FAIL_CLOSED "+str(why))
def sha(data):
    return hashlib.sha256(data).hexdigest()
def digest(path):
    return sha(pathlib.Path(path).read_bytes())
def save(path,obj):
    p=pathlib.Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def reference():
    need(C9.is_file() and X5.is_file() and R82.is_file() and MRE6B.is_file(),
         "all previous original source registries must be loaded")
    c9=json.loads(C9.read_text())
    x5=json.loads(X5.read_text())
    r82=json.loads(R82.read_text())
    mre6b=json.loads(MRE6B.read_text())
    need(c9["protocol"]==C9_TRAIN_PROTO and c9["source_SHA_count"]==19 and
         c9["final_all19_candidate_rule_for_future_prospective_test"]["rule"]==
         ["nvars",1500,"le"] and
         c9["final_all19_candidate_rule_for_future_prospective_test"]["mode"]==
         "cadical_noelim", "frozen old C9 policy missing")
    need(x5["protocol"]==X5_PROTO and len(x5["cases"])==3 and
         x5["original_SHA_frozen_before_any_solver"],
         "previous X5 source registry changed")
    need(r82["protocol"]==
         "DRNAS-R82-WIDE-OFFICIAL-2025-2026-NOSCREEN-20261104-v1",
         "R82 prior manifest changed")
    old_sha={f["source_sha256"] for f in c9["folds"]}
    old_sha.update(x["sha256"] for x in x5["cases"])
    old_sha.update(x["sha256"] for x in r82.get("cases",[]) if "sha256" in x)
    prior=mre6b.get("cases") or mre6b.get("source_cases")
    need(len(prior)>=4,"MRE6B 2026 prior source registry incomplete")
    old_sha.update(x["sha256"] for x in prior)
    old_ids={x["gbd"] for x in x5["cases"]}
    old_ids.update(x["gbd"] for x in prior)
    old_ids.update(x["gbd"] for x in r82.get("cases",[])
                   if x.get("year")==2026)
    old_ids.update(x["gbd"] for x in r82.get("source_selection_attempts",[])
                   if x.get("year")==2026)
    old_ids.update(x["gbd"] for x in r82.get("source_selection_attempts",[])
                   if x.get("year")==2026)
    old_ids.update(x["gbd"] for x in c9.get("folds",[]) if x.get("gbd"))
    return old_ids,old_sha,dict(
        c9_original_report_sha256=digest(C9),x5_original_sha256=digest(X5),
        r82_original_sha256=digest(R82),mre6b_original_sha256=digest(MRE6B))
def freeze():
    ROOT.mkdir(exist_ok=True)
    rawidx=r52.fetch_bytes(r52.URI,100000)
    official=[u.strip().split("/")[-1] for u in rawidx.decode().strip().splitlines()]
    need(len(official)==400 and len(set(official))==400,
         "official Main2026 original index changed")
    csvraw=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    reference_status={x["instanceid"]:STATUS.get(x["status"])
                      for x in csv.DictReader(io.StringIO(csvraw.decode()))
                      if x.get("solverid")=="biere_cadical3[main]"}
    need(len(reference_status)==400,"published original reference table missing")
    ids,prior_sha,refhash=reference()
    git_ids,git_sha=known.inspect_repo_ids(set(official))
    ids|=git_ids
    prior_sha|=git_sha
    ids|={x for x in known.PRIOR.read_text().lower().split()
          if re.fullmatch("[0-9a-f]{32}",x)}
    ranked=sorted([g for g in official if g not in ids],
         key=lambda g:sha((SALT+"|"+g).encode()))
    need(len(ranked)>=60,"too few pre-unseen official2026 IDs after exclusions")
    counts=collections.Counter()
    chosen=[];attempts=[]
    r32p.CNF_LIMIT=MAX_PLAIN
    for g in ranked[:MAX_ATTEMPT]:
        if len(chosen)==TARGET:break
        status=reference_status.get(g)
        a=dict(gbd=g,official_published_status=status)
        if status not in ("SAT","UNSAT"):
            a["action"]="skip_no_official_verified_status"
            attempts.append(a);continue
        if counts[status]>=MAX_PER_STATUS:
            a["action"]="skip_precommitted_status_quota"
            attempts.append(a);continue
        src=ROOT/(g+".cnf")
        try:
            compressed,_=r32p.request_url(
                "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=22)
            plain,encoding=r32p.decode(compressed)
            need(len(plain)<=MAX_PLAIN,"uncompressed source > precommitted cap")
            nv,nc=r32p.parse_dimacs_metadata(plain)
            need(0<nv<=MAX_VARS and 0<nc<=MAX_CLAUSES,
                 "original geometry exceeds precommitted size")
            d=sha(plain)
            need(d not in prior_sha and d not in
                 {x["sha256"] for x in chosen},
                 "previously used exact original SHA or repeated source")
            src.write_bytes(plain)
            chosen.append(dict(gbd=g,filename=src.name,sha256=d,
                variables=nv,clauses=nc,bytes=len(plain),
                status=status,raw_sha256=sha(compressed),
                compression=encoding,source_url="https://benchmark-database.de/file/"+g))
            counts[status]+=1
            a.update(action="FROZEN_BEFORE_SOLVER",sha256=d,variables=nv,
                     clauses=nc,status=status)
        except Exception as exc:
            src.unlink(missing_ok=True)
            a.update(action="SOURCE_REJECTED_BEFORE_SOLVER",
                     reason=(type(exc).__name__+": "+str(exc))[:180])
        attempts.append(a)
        print("C9C_SOURCE_SCAN",json.dumps(a,sort_keys=True),flush=True)
    need(len(chosen)>=MIN_READY and
         counts["SAT"]>=MIN_PER_STATUS and counts["UNSAT"]>=MIN_PER_STATUS,
         "fewer than 10 balanced SAT2026 originals under frozen restrictions")
    need(all(x["sha256"] not in prior_sha for x in chosen),
         "prior source SHA overlap postcondition")
    manifest=dict(protocol=PROTO,salt=SALT,year=2026,
       official_index=r52.URI,official_index_sha256=sha(rawidx),
       official_scores=r52.SCORES,official_scores_sha256=sha(csvraw),
       previous_exclusion_digest=refhash,
       history_not_guaranteed_globally_exhaustive=True,
       source_only_no_runtime_or_bve_gate_selection=True,
       precommitted_source_max_raw_bytes=MAX_RAW,
       precommitted_source_max_plain_bytes=MAX_PLAIN,
       precommitted_source_max_vars=MAX_VARS,
       precommitted_source_max_clauses=MAX_CLAUSES,
       target=TARGET,min_ready=MIN_READY,max_attempt=MAX_ATTEMPT,
       max_per_status=MAX_PER_STATUS,min_per_status=MIN_PER_STATUS,
       original_source_count=len(chosen),statuses=dict(counts),
       all_original_SHA_frozen_before_ANY_solver_trial=True,
       independent_UNSAT_LRAT=False,cap_s=CAP,reps=REPS,
       modes=("cadical","cadical_noelim","kissat","c9_route"),
       no_auto_promotion=True,
       cases=chosen,selection_trace=attempts)
    save(ROOT/"manifest.json",manifest)
    (ROOT/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in chosen))
    print("C9C_SOURCE_FROZEN",json.dumps(dict(
        n=len(chosen),statuses=dict(counts),
        selected_small=sum(x["variables"]<=1500 for x in chosen),
        manifest_sha256=digest(ROOT/"manifest.json"),
        rejected=collections.Counter(a["action"] for a in attempts)),
        sort_keys=True),flush=True)
def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["year"]==2026 and
         m["all_original_SHA_frozen_before_ANY_solver_trial"] and
         m["cap_s"]==CAP and m["reps"]==REPS,
         "prospective freeze protocol drift")
    a=m["cases"]
    counts=collections.Counter(x["status"] for x in a)
    need(MIN_READY<=len(a)<=TARGET and all(
        counts[k]>=MIN_PER_STATUS for k in ("SAT","UNSAT")),
        "source status quota changed")
    old_ids,old_sha,_=reference()
    for c in a:
        f=ROOT/c["filename"]
        need(c["gbd"] not in old_ids and c["sha256"] not in old_sha,
             "already known official source after freeze")
        need(f.is_file() and f.stat().st_size==c["bytes"] and digest(f)==c["sha256"],
             "source SHA or size changed")
    need(len({x["sha256"] for x in a})==len(a),"duplicate frozen originals")
    return a
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("freeze","verify"))
    a=p.parse_args()
    if a.action=="freeze":freeze()
    else:
        arr=cases()
        print("C9C_SOURCE_SHA_VERIFIED",len(arr),
              json.dumps(collections.Counter(x["status"] for x in arr)),flush=True)

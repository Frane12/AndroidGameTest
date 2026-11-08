#!/usr/bin/env python3
"""DRNAS MRE7: medium-difficulty official SAT2026 cohort, no DRNAS-time selection.

Two *reused, known-solved* official anchors (SAT and UNSAT, 2-10s CMS in
MRE3) make the test interpretable instead of all-timeout. Four separate
official sources are pre-selected by published CaDiCaL3 reference solve
time 2-15s and SAT/UNSAT balance, BEFORE any DRNAS or CMS trial.
Not a pure blind holdout: labels identify reused anchors vs new-reference.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,pathlib,shutil,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE7-MEDIUM-2KNOWN+4REF-4ARMS-2REPS-35S-v1"
ROOT=pathlib.Path("mre7_medium")
SALT="DRNAS-MRE7-20261108-MEDIUM-REF-2-15s-PRECOMMIT"
ANCHORS=(
 "official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf", # SAT known CMS ~8s
 "official-12cd0c3196589ac8105653cbfe613fc6.cnf", # UNSAT CMS ~2.5s
)
MIN_REF,MAX_REF=.75,15.
MAX_VARS,MAX_CLAUSES=80000,150000
MAX_RAW,MAX_DIMACS=30*1024**2,55*1024**2
NEW_SOURCES=4
CAP=35.
REPS=2
MODES=("cms_native","cms_source_xor","mre6b_proof_quotient","mre7_cpu_guard")
PRIOR=pathlib.Path("research/mre6b_official_prior_gbd.txt")


def need(ok,msg):
    if not ok:raise RuntimeError("MRE7_FREEZE_FAIL_CLOSED "+str(msg))

def digest(blob):return hashlib.sha256(blob).hexdigest()

def select_frozen(root=ROOT):
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
    # Prior MRE5 inputs are copied unchanged; SHA verified by r195 manifest.
    byname={x["name"]:x for x in r195.cases()}
    all_cases=[]
    for name in ANCHORS:
        need(name in byname,"missing reused known-solved official anchor "+name)
        c=byname[name]
        need(c["cohort"]=="reused_official_2026","anchor source not original")
        src=r195.FROZEN/name
        need(r195.digest(src)==c["sha256"],"anchor SHA mismatch")
        dst=root/name;shutil.copyfile(src,dst)
        need(r195.digest(dst)==c["sha256"],"copied anchor drift")
        all_cases.append(dict(name=name,sha256=c["sha256"],bytes=c["bytes"],
           expected="SAT" if "28dcc" in name else "UNSAT",
           cohort="REUSED_known_solved_diagnostic",
           published_reference_solver=None,published_reference_s=None,
           reason="guaranteed test calibration, NOT blind evidence"))
    raw_uri=r52.fetch_bytes(r52.URI,100000)
    gbds=[u.strip().rsplit("/",1)[-1] for u in raw_uri.decode().strip().splitlines()]
    need(len(gbds)==400 and len(set(gbds))==400,"official Main2026 index drift")
    raw_scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    csvrows=list(csv.DictReader(io.StringIO(raw_scores.decode())))
    allowed=set(gbds)
    published=[r for r in csvrows if r.get("solverid")=="biere_cadical3[main]"
               and r.get("instanceid") in allowed]
    need(len(published)==400,"missing original official 2026 reference")
    need(PRIOR.exists(),"historical original exclusion registry missing")
    old={x.strip() for x in PRIOR.read_text().splitlines()
         if x.strip() and not x.startswith("#")}
    # Disjoint from the previous seven-source MRE6b holdout as well.
    old_mf=pathlib.Path("mre6b_blind/manifest.json")
    need(old_mf.exists(),"previous official seven-source holdout provenance missing")
    old |= {x["gbd"] for x in json.loads(old_mf.read_text())["cases"]}
    old |= {str(x).replace(".cnf","") for x in ANCHORS}
    pool={"SAT":[],"UNSAT":[]}
    for r in published:
        g=r["instanceid"]
        if g in old:continue
        expected={"sat-verified":"SAT","unsat-verified":"UNSAT"}.get(r["status"])
        if expected is None:continue
        try:t=float(r["runtime"])
        except Exception:continue
        if MIN_REF<=t<=MAX_REF:
            pool[expected].append(dict(gbd=g,expected=expected,
                       published_reference_s=t))
    need(all(len(pool[x])>=2 for x in pool),
         "not enough official reference-solved 2-15s candidates")
    selection_log=[]
    r32p.CNF_LIMIT=MAX_DIMACS
    # One .75-5s and one 5-15s candidate per SAT/UNSAT status, when possible.
    for status in ("SAT","UNSAT"):
        for lo,hi in ((.75,5.),(5.,15.)):
            ordered=sorted((p for p in pool[status]
                            if lo<=p["published_reference_s"]<hi),
                key=lambda p:digest((SALT+"|"+status+"|"+str(lo)+"|"+p["gbd"]).encode()))
            accepted=False
            for c in ordered[:50]:
                g=c["gbd"]
                attempt=dict(gbd=g,official_status=status,
                             official_reference_s=c["published_reference_s"])
                try:
                    data,redir=r32p.request_url(
                        "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=45)
                    src,compression=r32p.decode(data)
                    need(len(src)<=MAX_DIMACS,"oversize source")
                    n,m=r32p.parse_dimacs_metadata(src)
                    need(n<=MAX_VARS and m<=MAX_CLAUSES,"precommitted CNF size")
                    sha=digest(src)
                    need(sha not in {x["sha256"] for x in all_cases},
                         "duplicate original SHA")
                    dest=root/(g+".cnf");dest.write_bytes(src)
                    all_cases.append(dict(name=dest.name,gbd=g,sha256=sha,
                        bytes=len(src),n=n,m=m,expected=status,
                        cohort="NEW_official_reference_medium",
                        published_reference_solver="CaDiCaL3[Main2026]",
                        published_reference_s=c["published_reference_s"],
                        compression=compression,redirect=redir,
                        reason="official pre-solve reference stratum, not DRNAS outcome"))
                    attempt.update(action="frozen",sha256=sha,bytes=len(src),clauses=m)
                    accepted=True
                except Exception as exc:
                    attempt.update(action="excluded_size_or_download",
                        reason=(type(exc).__name__+": "+str(exc))[:130])
                selection_log.append(attempt)
                print("MRE7_SOURCE_SCAN",json.dumps(attempt,sort_keys=True),flush=True)
                if accepted:break
            need(accepted,"failed to freeze medium reference "+status+":"+str(lo))
    need(len(all_cases)==6 and len({x["sha256"] for x in all_cases})==6,
         "six distinct SHA-locked sources required")
    manifest=dict(protocol=PROTO,selection_salt=SALT,cases=all_cases,
         anchor_count=2,new_reference_count=4,
         published_reference_bands_s=[[.75,5],[5,15]],
         published_solver="biere_cadical3[main]",
         external_reference_used_ONLY_to_select_difficulty=True,
         DRNAS_CMS_performance_not_used_for_new_selection=True,
         new_source_disjoint_from_recorded_prior_registry=True,
         historical_registry_not_exhaustive=True,
         original_index_sha256=digest(raw_uri),
         original_scores_sha256=digest(raw_scores),
         attempts=selection_log,cap_s=CAP,reps=REPS,modes=MODES)
    (root/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (root/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["name"]+"\n" for x in all_cases))
    print("MRE7_FREEZE_PASS",json.dumps(
      dict(cases=len(all_cases),anchors=2,new_official=4,
           status_counts={k:sum(x["expected"]==k for x in all_cases)
                          for k in ("SAT","UNSAT")}),sort_keys=True),flush=True)

def verify(root=ROOT):
    root=pathlib.Path(root)
    m=json.loads((root/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==6 and
         m["anchor_count"]==2 and m["new_reference_count"]==4,
         "cohort/protocol drift")
    need(len({x["sha256"] for x in m["cases"]})==6,"duplicates")
    for c in m["cases"]:
        p=root/c["name"]
        need(p.exists() and r195.digest(p)==c["sha256"] and
             p.stat().st_size==c["bytes"],"original SHA mismatch")
    print("MRE7_SOURCES_VERIFIED",len(m["cases"]),flush=True)

def selftest():
    need(len(ANCHORS)==2 and len(MODES)==4 and
         CAP==35. and MIN_REF==.75 and MAX_REF==15.,
         "safety protocol changed")
    print("MRE7_FREEZE_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify"))
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":select_frozen()
    else:verify()

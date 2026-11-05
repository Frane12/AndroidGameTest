#!/usr/bin/env python3
"""R135S mini frozen independent follow-up, NO performance-dependent cherry picking.

Reuse real external GBD/SAT2024 CNF files that were acquired but NEVER measured
by the 56-formula R135 pilot, and exclude known R132 and pre-frozen 400-case
R135 SHA identities. Formula selection deterministic by SHA per cohort.
No web fetch, no new acquisition, no solver run during freeze.
"""
import collections,hashlib,json,pathlib,shutil
ROOT=pathlib.Path("r135s")
FROZEN=ROOT/"frozen"
PRIOR=pathlib.Path("r135-source/frozen")
R132=pathlib.Path("r132-source/frozen")
FOURHUNDRED=pathlib.Path("holdout-400")
PROTO="DRNAS-R135S-REAL-MINI-UNMEASURED-SOURCE-20261105-v1"
TARGETS={"miter":4,"cryptography":6,"uniform_random":6,
         "official2024":6,"xor_shifting":6}
TOTAL_CAP=24
MIN_TOTAL=16
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for x in iter(lambda:f.read(1048576),b""):h.update(x)
    return h.hexdigest()
def read(path):
    assert path.is_file(),"required provenance missing "+str(path)
    return json.loads(path.read_text())
def freeze():
    oldm=PRIOR/"manifest.json"
    r132m=R132/"manifest.json"
    bigm=FOURHUNDRED/"manifest-400.json"
    old=read(oldm);prior=read(r132m);big=read(bigm)
    assert len(old.get("cases",[]))==56
    assert len(prior.get("cases",[]))==125
    assert len(big.get("formulas",[]))==400
    assert big.get("status")=="COMPLETE"
    forbid={x["sha256"] for x in old["cases"]}
    forbid.update(x["sha256"] for x in prior["cases"])
    forbid.update(x["sha256"] for x in big["formulas"])
    by=collections.defaultdict(list)
    counts=collections.Counter()
    for f in sorted(PRIOR.glob("*.cnf")):
        co=f.name.rsplit("-",1)[0]
        if co not in TARGETS:continue
        h=sha(f)
        if h in forbid:
            counts["known_sha_excluded"]+=1
            continue
        by[co].append((h,f))
    for group in by.values():group.sort(key=lambda x:x[0])
    cases=[];used=set();co_counts=collections.Counter()
    # Round robin across independent real SAT families; never inspect timing.
    for index in range(max(TARGETS.values())):
        for co,target in TARGETS.items():
            if len(cases)>=TOTAL_CAP:break
            if index>=target or index>=len(by[co]):continue
            h,src=by[co][index]
            assert h not in used
            used.add(h)
            cases.append(dict(id=src.name,cohort=co,sha256=h,bytes=src.stat().st_size,
                              original_source="R135 56-formula freezer unmeasured surplus; original GBD/CNF"))
            co_counts[co]+=1
    assert MIN_TOTAL<=len(cases)<=TOTAL_CAP,("insufficient actual unseen CNFs",dict(co_counts),dict(counts))
    FROZEN.mkdir(parents=True,exist_ok=True)
    for c in cases:
        src=PRIOR/c["id"]
        shutil.copyfile(src,FROZEN/c["id"])
        assert sha(FROZEN/c["id"])==c["sha256"]
    manifest=dict(protocol=PROTO,phase="PRECOMMITTED_SHA_EXCLUDED_UNMEASURED_REAL_MINI",
        cases=cases,source_sha_verified=True,excluded_prior_SHA_total=len(forbid),
        source_manifest_sha256={"R135_56":sha(oldm),"R132_125":sha(r132m),"R135_400":sha(bigm)},
        source_ids_sha_excluded=True,previous_R135_56_excluded=True,
        previously_seen_R132_excluded=True,
        ongoing_R135_400_excluded=True,
        quotas=TARGETS,cohort_counts=dict(co_counts),target_max=TOTAL_CAP,
        rejection_counts=dict(counts),repeats=2,shards=4,cap_s=15,
        no_speed_filter_or_training=True,
        note="Independent small exploratory check of frozen R135 cheap detector; not a formal official SAT Competition score.")
    (FROZEN/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("R135S_FROZEN",json.dumps({"cases":len(cases),"cohorts":dict(co_counts),
        "excluded_SHA":len(forbid),"source_hashes":manifest["source_manifest_sha256"]},sort_keys=True),flush=True)
if __name__=="__main__":freeze()

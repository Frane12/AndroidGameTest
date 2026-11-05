#!/usr/bin/env python3
"""R135 precommitted SHA-excluded source acquisition from R132 proven pool."""
import collections,hashlib,json,pathlib
import r132_wide_xor_benchmark as old
ROOT=pathlib.Path("r135")
SOURCES=ROOT/"frozen"
PROTO="DRNAS-R135-FROZEN-NONXOR-PORTFOLIO-20261105-v1"
QUOTA={"miter":12,"cryptography":12,"xor_shifting":12,"uniform_random":12,"official2024":12,"official2025":12}
R132=ROOT/"prior"/"r132"/"manifest.json"
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""): h.update(chunk)
    return h.hexdigest()
def freeze():
    assert R132.is_file(),"missing R132 SHA exclusion ledger"
    old_cases=json.loads(R132.read_text())["cases"]
    assert len(old_cases)==125
    known_sha={c["sha256"] for c in old_cases}
    known_urls={c.get("url") for c in old_cases}
    known_gbd={c.get("gbd") for c in old_cases}
    old.ROOT=ROOT
    old.SOURCES=SOURCES
    old.PROTO=PROTO
    old.freeze()  # SHA/URL/ID exclusion for 12 earlier manifests
    f=SOURCES/"manifest.json"
    m=json.loads(f.read_text())
    chosen=[];counts=collections.Counter();rejects=collections.Counter()
    for c in m["cases"]:
        co=c["cohort"]
        if c["sha256"] in known_sha or c.get("url") in known_urls or c.get("gbd") in known_gbd:
            rejects["prior_R132_overlap"]+=1
            continue
        if counts[co]>=QUOTA.get(co,0):
            rejects["fixed_cohort_quota"]+=1
            continue
        chosen.append(c);counts[co]+=1
    assert len(chosen)>=32,("too few unseen CNFs",dict(counts))
    assert len({c["sha256"] for c in chosen})==len(chosen)
    m.update(cases=chosen,counts=dict(counts),r132_manifest_sha256=sha(R132),
       excluded_all_known_R132_sources=True,r135_rejections=dict(rejects),
       phase="FROZEN_SHA_DISJOINT_UNMEASURED_R135",quota_precommitted=QUOTA,
       selector="binary fraction <0.20 AND Horn fraction <0.50 on >=32 sampled clauses -> pinned CaDiCaL; else Kissat; max 128KiB/2000 clauses",
       no_holdout_tuning=True)
    f.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    for c in chosen: assert sha(SOURCES/c["id"])==c["sha256"]
    print("R135_FREEZE_FINAL",json.dumps({"selected":len(chosen),"counts":dict(counts),"rejections":dict(rejects)}),flush=True)
if __name__=="__main__":freeze()

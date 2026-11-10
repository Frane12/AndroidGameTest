#!/usr/bin/env python3
"""Audit recovery for frozen AB7, original run 42805430723.

Only replicate 2 failed because e9.seedpair only allows EQUIV9 two reps.
Leave all frozen benchmark source, original CNFs, native binary, caps, modes,
and recorded replicates 0/1 EXACTLY UNCHANGED. Supply distinct prospective,
SHA-derived deterministic Kissat seed only for replicate 2, then run unchanged
AB7 shard(2) and AB7.audit(). This is not an additional source selection.
"""
import hashlib,json,pathlib
import drnas_gf2_screen6_cdcl_ab7 as ab7

def main():
    m=ab7.verify()
    assert m["reps"]==3 and m["shards"]==3
    original=ab7.e9.seedpair
    seed_record={}
    def seedpair3(sha,rep):
        if rep in (0,1):return original(sha,rep)
        if rep!=2 or sha!=ab7.SOURCE_SHA:
            raise RuntimeError("GF2_AB7_RECOVERY_SEED_REFUSED")
        s1=int(hashlib.sha256((sha+"|GF2_AB7_KISSAT_BASE|2").encode()).hexdigest()[:7],16)
        s2=int(hashlib.sha256((sha+"|GF2_AB7_KISSAT_ALT|2").encode()).hexdigest()[:7],16)
        if s1==s2:raise RuntimeError("GF2_AB7_SEED_COLLISION")
        seed_record.update(rep=2,seed_base=s1,seed_alt=s2,sha=sha,
            derivation="SHA256(source_SHA|GF2_AB7_KISSAT_[BASE,ALT]|2), first 7 hex",
            existing_seedpairs_0_1_unmodified=True)
        return s1,s2
    ab7.e9.seedpair=seedpair3
    ab7.shard(2)
    if not seed_record:raise RuntimeError("replicate2 Kissat actually not executed")
    p=ab7.ROOT/"seed-recovery.json"
    p.write_text(json.dumps(seed_record,sort_keys=True,indent=2)+"\n")
    print("GF2_AB7_RECOVERY_SEED "+json.dumps(seed_record,sort_keys=True),flush=True)
    ab7.audit()
    print("GF2_AB7_RECOVERY_PASS all 21 frozen source E2E original SHA attempts audited",flush=True)
if __name__=="__main__":main()

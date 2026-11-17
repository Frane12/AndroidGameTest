#!/usr/bin/env python3
"""Strict E2E two original grid Tseitin sources (IDs 5 and 6) x2 x6 arms.

This is retrospective development after reviewing new source grammar.
All inputs are the byte-identical SHA-frozen originals from completed
prospective run 44043273439, and all original solver binaries and
standard VeriPB/DRAT/FRAT checkers are SHA-pinned.
A native MATH5 source certificate counts STRICT only after a separately
generated proof passes the external VeriPB checker on unchanged CNF.
"""
import argparse,collections,hashlib,importlib.util,json,os,pathlib,random,statistics,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"results/math5_xor234_grid2"
MANIFEST=ROOT/"research/xor3_prospective_gbd10/inputs/manifest.json"
EXT=ROOT/"research/math5/emit_veripb_xor234_split.py"
OLD_EXT=ROOT/"research/math5/emit_veripb_xor3_carry.py"
CERTCHECK=ROOT/"research/math5/check_math5.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research/graphclique"))
import real67 as graph
spec=importlib.util.spec_from_file_location("xor3_old_pipeline",
    ROOT/"research/math5/xor3_tseitin_id6.py")
xor3=importlib.util.module_from_spec(spec)
spec.loader.exec_module(xor3)
ARMS=("XOR234_SPLIT_VERIPB","XOR3_ONLY_VERIPB",
      "X59_MATH5_VERIPB","Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
SOURCE_IDS=(5,6)
EXPECTED_SHA={
   5:"79618e35c83016fd1a188eb63ed499c3d1d4c364f710c9c9a93eb7925054a9af",
   6:"0b37c65f0c7cb2c9ed375d09a7ab3d77da34266a908f368e67186754fe9dbd37"}
STRICT={"MODEL","DRAT","FRAT","VERIPB_MATH5",
        "VERIPB_XOR3_CARRY_RED_RUP_CP","VERIPB_XOR234_SPLIT_RED_RUP_CP"}
CAP=8.0
REPS=2
SHARDS=2

def sha(p):return frozen.sha(p)

def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def affinity():
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1

def originals():
    m=json.loads(MANIFEST.read_text())
    assert m["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert m["selected_count"]==len(m["sources"])==10
    by_id={s["id"]:s for s in m["sources"]}
    assert {5,6}.issubset(by_id)
    picked=[by_id[i] for i in SOURCE_IDS]
    for s in picked:
        assert s["family"]=="tseitin-formulas"
        assert s["sha256"]==EXPECTED_SHA[s["id"]]
        assert sha(ROOT/s["path"])==s["sha256"],("ORIGINAL_CHANGED",s["id"])
    return picked

def prepare():
    affinity()
    src=originals()
    pins=frozen.pinned()
    policy={"experiment":"DRNAS-XOR234-GRID-ORIGINAL2-STRICT-E2E-V1",
        "original_source_ids":list(SOURCE_IDS),
        "original_source_sha256":EXPECTED_SHA,
        "source_frozen_manifest_sha256":sha(MANIFEST),
        "arms":list(ARMS),
        "repetitions":REPS,"shards":SHARDS,
        "expected_attempts":len(src)*REPS*len(ARMS),
        "cap_s":CAP,"strict_timeout_penalty_s":2*CAP,
        "pinned_reference_binary_sha256":pins,
        "standard_emitter_sha256":sha(EXT),
        "old_emitter_sha256":sha(OLD_EXT),
        "independent_math5_source_checker_sha256":sha(CERTCHECK),
        "benchmark_sha256":sha(HERE/"benchmark.py"),
        "workflow_commit_sha256":os.environ.get("GITHUB_SHA"),
        "one_logical_CPU_per_solver":True,"serial_trials":True,
        "independent_proof_check_in_same_e2e_wall_cap":True,
        "retrospective_after_diagnosing_both_original_grid_CNF":True,
        "not_blind_prospective":True,
        "no_main_promotion":True}
    save(OUT/"protocol.json",policy)
    print("MATH5_XOR234_PREPARED "+json.dumps({
        "sources":len(src),"arms":len(ARMS),
        "expected_trials":policy["expected_attempts"],
        "source_sha256":policy["original_source_sha256"]},sort_keys=True),flush=True)

def restore():
    affinity()
    picked=originals()
    policy=json.loads((OUT/"protocol.json").read_text())
    assert policy["experiment"]=="DRNAS-XOR234-GRID-ORIGINAL2-STRICT-E2E-V1"
    assert policy["original_source_ids"]==list(SOURCE_IDS)
    assert policy["source_frozen_manifest_sha256"]==sha(MANIFEST)
    assert policy["pinned_reference_binary_sha256"]==frozen.pinned()
    assert policy["standard_emitter_sha256"]==sha(EXT)
    assert policy["old_emitter_sha256"]==sha(OLD_EXT)
    assert policy["independent_math5_source_checker_sha256"]==sha(CERTCHECK)
    assert policy["benchmark_sha256"]==sha(HERE/"benchmark.py")
    assert policy["workflow_commit_sha256"]==os.environ.get("GITHUB_SHA")
    return picked,policy

def proof_trial(src,arm,rep):
    # The old pipeline independently checks the exact original source,
    # executes frozen native MATH5, then new/old emitter, then external VeriPB.
    xor3.OUT=OUT/"accepted_external_veripb"/f"source_{src['id']}"
    if arm=="XOR234_SPLIT_VERIPB":
        xor3.EMITTER=EXT
    else:
        xor3.EMITTER=OLD_EXT
    r=dict(xor3.strict_xor3(src,rep))
    assert r["source_sha256"]==src["sha256"]
    r.update(arm=arm,file_id=src["file_id"],family=src["family"])
    if r["strict_accepted"]:
        assert r["certificate_kind"]=="VERIPB_XOR3_CARRY_RED_RUP_CP"
        r["certificate_kind"]=("VERIPB_XOR234_SPLIT_RED_RUP_CP"
                if arm=="XOR234_SPLIT_VERIPB"
                else "VERIPB_XOR3_CARRY_RED_RUP_CP")
        # Old upstream reproduction script writes hard-coded ID6 names.
        # Rename to the exact current ID after independent acceptance.
        folder=xor3.OUT/"verified_original_proofs"
        for item in folder.glob(f"ID6_rep{rep}_*"):
            item.rename(folder/item.name.replace("ID6_",f"source{src['id']}_"))
    return r

def one(src,arm,rep):
    if arm in ("XOR234_SPLIT_VERIPB","XOR3_ONLY_VERIPB"):
        result=proof_trial(src,arm,rep)
    elif arm=="X59_MATH5_VERIPB":
        result=graph.old.standard_trial(src,rep)
    else:
        result=frozen.trial(src,arm,rep)
    assert result["source_sha256"]==src["sha256"]
    assert result["rep"]==rep and result["arm"]==arm
    assert not result["strict_accepted"] or (
        result["accepted"] and result.get("certificate_kind") in STRICT)
    return result

def shard(idx):
    assert 0<=idx<SHARDS
    picked,_=restore()
    src=picked[idx]
    folder=OUT/f"shard-{idx}"
    folder.mkdir(parents=True,exist_ok=False)
    records=[]
    with (folder/"trials.jsonl").open("w") as stream:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(f"XOR234-SOURCE-{src['sha256']}-{rep}").shuffle(order)
            arms={}
            for arm in order:
                r=one(src,arm,rep)
                records.append(r)
                stream.write(json.dumps(r,sort_keys=True)+"\n");stream.flush()
                arms[arm]={"status":r["status"],"strict":r["strict_accepted"],
                    "PAR2_strict_s":r["PAR2_strict_s"],
                    "e2e_s":r["e2e_s"],"proof_kind":r.get("certificate_kind")}
            print("MATH5_XOR234_GRID_PAIR "+json.dumps({
                "id":src["id"],"rep":rep,"arms":arms},sort_keys=True),flush=True)
    assert len(records)==REPS*len(ARMS)==12
    print("MATH5_XOR234_SHARD "+json.dumps({
        "id":src["id"],"trials":len(records),
        "totals":{arm:{"strict":sum(r["strict_accepted"] for r in records if r["arm"]==arm),
                      "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in records if r["arm"]==arm),6)}
                  for arm in ARMS}},sort_keys=True),flush=True)

def report():
    sources,policy=restore()
    rows=[]
    for idx in range(SHARDS):
        path=OUT/f"shard-{idx}/trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",idx)
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    expected={(i,rep,arm) for i in SOURCE_IDS for rep in range(REPS) for arm in ARMS}
    actual={(r["id"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(expected)==len(actual)==24 and actual==expected
    errors=[]
    for r in rows:
        if r["source_sha256"]!=EXPECTED_SHA[r["id"]]:
            errors.append({"reason":"FROZEN_SOURCE_SHA_CHANGED","row":r})
        if r["critical"]:
            errors.append({"reason":"CRITICAL_SOLVER_OR_EXTERNAL_CHECK","row":r})
        if r["strict_accepted"] and (not r["accepted"] or r.get("certificate_kind") not in STRICT):
            errors.append({"reason":"UNKNOWN_PROOF_SCORING_AS_STRICT","row":r})
        if not r["strict_accepted"] and r["PAR2_strict_s"]!=2*CAP:
            errors.append({"reason":"WRONG_STRICT_PAR2_SCORING","row":r})
    for id in SOURCE_IDS:
        accepted=[r for r in rows if r["id"]==id and r["strict_accepted"]]
        if (any(r["status"]=="SAT_VERIFIED" for r in accepted)
            and any(r["status"]=="UNSAT_VERIFIED" for r in accepted)):
            errors.append({"reason":"CONTRADICTORY_SAT_UNSAT","id":id})
    totals={}
    for arm in ARMS:
        cases=[r for r in rows if r["arm"]==arm]
        totals[arm]={
            "attempts":len(cases),
            "strict_verified":sum(r["strict_accepted"] for r in cases),
            "strict_sources":len({r["id"] for r in cases if r["strict_accepted"]}),
            "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in cases),6),
            "statuses":dict(collections.Counter(r["status"] for r in cases)),
            "proof_kinds":dict(collections.Counter(
                r.get("certificate_kind") for r in cases if r["strict_accepted"]))}
    final={"status":"COMPLETE" if not errors else "CRITICAL",
        "original_sources":list(SOURCE_IDS),
        "attempts":len(rows),"cap_s":CAP,
        "critical_count":len(errors),"critical":errors,
        "totals":totals,
        "source_manifest_sha256":policy["source_frozen_manifest_sha256"],
        "new_emitter_sha256":policy["standard_emitter_sha256"],
        "strict_standard_checkers_only":True,
        "retrospective_development":True,
        "no_main_promotion":True}
    save(OUT/"final.json",final)
    print("MATH5_XOR234_GRID_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("prepare","shard","report"))
    a.add_argument("--index",type=int)
    v=a.parse_args()
    if v.action=="prepare":prepare()
    elif v.action=="shard":shard(v.index)
    else:report()

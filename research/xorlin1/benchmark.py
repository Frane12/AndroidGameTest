#!/usr/bin/env python3
"""DRNAS XOR-LIN1 source-only GF2/VeriPB vs native XOR234 + frozen references.

10 original SAT2022/24 CNFs from source-frozen 2026-11-17 run 44049316105.
This is a RETROSPECTIVE regression test: XOR-LIN1 was developed after
studying sources 5/7/9. Source SHA and solver binary SHAs remain frozen.
Serial 6-arm paired repeats, cap 8s inclusive source/parsing/VeriPB.
"""
import argparse,collections,hashlib,importlib.util,json,os,pathlib,random,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"results/xorlin1_original10"
DATA=ROOT/"research/xor234_prospective_tseitin10/inputs"
EXTRACT=HERE/"extract.py"
EMITTER=HERE/"emit_veripb.py"
CHECKER=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research/graphclique"))
import real67 as graph
spec=importlib.util.spec_from_file_location("old_native_xor234",
   ROOT/"research/math5/xor3_tseitin_id6.py")
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
BASELINE_EMITTER=ROOT/"research/math5/emit_veripb_xor234_split.py"
ARMS=("XORLIN1_SOURCE_ONLY","XOR234_NATIVE_VERIPB","X59_MATH5_VERIPB",
      "Kissat","CaDiCaL","CryptoMiniSat")
CAP=8.0;REPS=2;SHARDS=5
STRICT={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5",
        "VERIPB_XOR234_SPLIT_RED_RUP_CP","VERIPB_XORLIN1"}
ORIGINAL_EXPECTED_SHA={
  5:"c6e93b07d65c7e344164cee4b55785f415e904aff804d62aec359495145fa41c",
  7:"082f20570abb6d5a4d87f9b83df1c83c2fa9cf04f3547a5260221e4577445474",
  9:"38bd3cb7690adb56c1e22c5378a326f86c139c92a99e19a91afe4906c8542643"}

def sha(path):return frozen.sha(path)

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def onecpu():
    if hasattr(os,"sched_setaffinity"):
        core=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{core})
        assert len(os.sched_getaffinity(0))==1

def originals():
    m=json.loads((DATA/"manifest.json").read_text())
    assert m["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert m["selected_count"]==len(m["sources"])==10
    assert {s["id"] for s in m["sources"]}==set(range(10))
    for s in m["sources"]:
        assert sha(ROOT/s["path"])==s["sha256"],("SOURCE_CHANGED",s["id"])
        if s["id"] in ORIGINAL_EXPECTED_SHA:
            assert s["sha256"]==ORIGINAL_EXPECTED_SHA[s["id"]]
    return m["sources"]

def prepare():
    onecpu()
    sources=originals()
    binaries=frozen.pinned()
    code_paths=(
       EXTRACT,EMITTER,HERE/"benchmark.py",HERE/"selftest.py",
       ROOT/"research/math5/check_math5.py",
       ROOT/"research/math5/xor3_tseitin_id6.py",
       BASELINE_EMITTER)
    p={"protocol":"DRNAS-XORLIN1-SOURCE-GF2-PBP-STRICT-V1",
       "source_count":10,"arms":list(ARMS),"repetitions":REPS,
       "shards":SHARDS,"expected_trials":10*REPS*len(ARMS),
       "cap_s":CAP,"unverified_PAR2_penalty_s":2*CAP,
       "source_manifest_sha256":sha(DATA/"manifest.json"),
       "source_code_hashes":{str(path.relative_to(ROOT)):sha(path) for path in code_paths},
       "reference_binary_hashes":binaries,
       "workflow_commit_sha256":os.environ.get("GITHUB_SHA"),
       "source_sha256_excluded_from_solver_configuration":True,
       "one_logical_cpu_per_solver":True,
       "no_simultaneous_solver_portfolio":True,
       "valid_strict_proof_kinds":sorted(STRICT),
       "retrospective_development_after_source_analysis":True,
       "not_new_blind":True,
       "no_main_promotion":True}
    save(OUT/"protocol.json",p)
    print("XORLIN1_PREPARED "+json.dumps({
      "sources":len(sources),"arms":len(ARMS),"attempts":p["expected_trials"],
      "input_sha256":p["source_manifest_sha256"]},sort_keys=True),flush=True)

def restore():
    onecpu()
    src=originals()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["protocol"]=="DRNAS-XORLIN1-SOURCE-GF2-PBP-STRICT-V1"
    assert p["source_manifest_sha256"]==sha(DATA/"manifest.json")
    assert p["reference_binary_hashes"]==frozen.pinned()
    assert p["arms"]==list(ARMS)
    assert p["workflow_commit_sha256"]==os.environ.get("GITHUB_SHA")
    for path,digest in p["source_code_hashes"].items():
        assert sha(ROOT/path)==digest,("CODE_SOURCE_CHANGED",path)
    return src,p

def custom_row(s,rep,started,status,critical=False,reason=None,
               proof=None,details=None,checker_s=0):
    total=time.perf_counter()-started
    if total>CAP and not critical:status="E2E_OVER_CAP"
    verified=status=="UNSAT_VERIFIED" and not critical and total<=CAP
    return {"id":s["id"],"file_id":s["file_id"],
      "source_sha256":s["sha256"],"family":s["family"],
      "rep":rep,"arm":"XORLIN1_SOURCE_ONLY","rc":20 if verified else None,
      "status":status,"accepted":verified,"strict_accepted":verified,
      "critical":critical,"reason":reason,
      "certificate_kind":"VERIPB_XORLIN1" if verified else None,
      "proof_bytes":proof.stat().st_size if verified else 0,
      "proof_sha256":sha(proof) if verified else None,
      "metadata":details if verified else None,
      "checker_s":round(checker_s,6),
      "e2e_s":round(total,6),
      "PAR2_s":round(total if verified else 2*CAP,6),
      "PAR2_strict_s":round(total if verified else 2*CAP,6)}

def source_only(s,rep):
    started=time.perf_counter()
    cnf=ROOT/s["path"]
    assert sha(cnf)==s["sha256"]
    with tempfile.TemporaryDirectory(prefix="drnas-xorlin1-original-") as d:
        folder=pathlib.Path(d)
        cert=folder/"gauss.json"
        selection=folder/"selection.json"
        pb=folder/"proof.pbp"
        proofmeta=folder/"pb_meta.json"
        rem=CAP-(time.perf_counter()-started)
        if rem<=0:return custom_row(s,rep,started,"NO_EXTRACT_BUDGET")
        extract=frozen.execute([sys.executable,str(EXTRACT),
           "--cnf",str(cnf),"--certificate",str(cert),"--meta",str(selection)],rem)
        if extract["expired"]:
            return custom_row(s,rep,started,"XORLIN1_EXTRACT_TIMEOUT")
        if extract["returncode"]==2 and not cert.exists():
            return custom_row(s,rep,started,"XORLIN1_SAFE_UNKNOWN")
        if extract["returncode"]!=0 or not cert.exists() or not selection.exists():
            return custom_row(s,rep,started,"INVALID_XORLIN1_EXTRACT",
                critical=True,reason=(extract["stdout"]+extract["stderr"])[-300:])
        meta=json.loads(selection.read_text())
        if meta.get("original_sha256")!=s["sha256"]:
            return custom_row(s,rep,started,"INVALID_EXTRACT_SHA",critical=True)
        rem=CAP-(time.perf_counter()-started)
        if rem<=0:return custom_row(s,rep,started,"NO_EMITTER_BUDGET")
        emit=frozen.execute([sys.executable,str(EMITTER),
            "--cnf",str(cnf),"--certificate",str(cert),
            "--output",str(pb),"--meta",str(proofmeta)],rem)
        if emit["expired"]:
            return custom_row(s,rep,started,"XORLIN1_EMITTER_TIMEOUT")
        if emit["returncode"]==2 and not pb.exists():
            return custom_row(s,rep,started,"XORLIN1_UNSUPPORTED_CERT")
        if emit["returncode"]!=0 or not pb.exists() or not proofmeta.exists():
            return custom_row(s,rep,started,"INVALID_XORLIN1_EMITTER",
                critical=True,reason=(emit["stdout"]+emit["stderr"])[-300:])
        metadata=json.loads(proofmeta.read_text())
        if metadata.get("source_sha256")!=s["sha256"]:
            return custom_row(s,rep,started,"INVALID_EMITTER_SOURCE_SHA",critical=True)
        rem=CAP-(time.perf_counter()-started)
        if rem<=0:return custom_row(s,rep,started,"NO_EXTERNAL_CHECKER_BUDGET")
        ck=frozen.execute([str(CHECKER),"--cnf",str(cnf),str(pb)],rem)
        if ck["expired"]:
            return custom_row(s,rep,started,"VERIPB_TIMEOUT",checker_s=ck["wall_s"])
        if ck["returncode"]!=0 or (
            "s VERIFIED UNSATISFIABLE" not in ck["stdout"]+ck["stderr"]):
            return custom_row(s,rep,started,"INVALID_EXTERNAL_VERIPB",
                 critical=True,reason=(ck["stdout"]+ck["stderr"])[-300:],
                 checker_s=ck["wall_s"])
        row=custom_row(s,rep,started,"UNSAT_VERIFIED",proof=pb,
                       details=metadata,checker_s=ck["wall_s"])
        if row["strict_accepted"]:
            folder=OUT/"accepted_proofs"/f"source_{s['id']:02d}"
            folder.mkdir(parents=True,exist_ok=True)
            (folder/f"rep{rep}.pbp").write_bytes(pb.read_bytes())
            (folder/f"rep{rep}.json").write_bytes(cert.read_bytes())
        return row

def old_native(s,rep):
    native.OUT=OUT/"old_native_proof_artifacts"/f"source_{s['id']:02d}"
    native.EMITTER=BASELINE_EMITTER
    native.CAP=CAP
    row=dict(native.strict_xor3(s,rep))
    row["arm"]="XOR234_NATIVE_VERIPB"
    row["file_id"]=s["file_id"]
    if row["strict_accepted"]:
        assert row["certificate_kind"]=="VERIPB_XOR3_CARRY_RED_RUP_CP"
        row["certificate_kind"]="VERIPB_XOR234_SPLIT_RED_RUP_CP"
    return row

def one(s,arm,rep):
    if arm=="XORLIN1_SOURCE_ONLY":r=source_only(s,rep)
    elif arm=="XOR234_NATIVE_VERIPB":r=old_native(s,rep)
    elif arm=="X59_MATH5_VERIPB":r=graph.old.standard_trial(s,rep)
    else:r=frozen.trial(s,arm,rep)
    assert r["id"]==s["id"] and r["rep"]==rep and r["arm"]==arm
    assert r["source_sha256"]==s["sha256"]
    assert r["PAR2_strict_s"]<=2*CAP
    if r["strict_accepted"] and (
       not r["accepted"] or r.get("certificate_kind") not in STRICT):
        raise AssertionError("UNSUPPORTED_STRICT_ACCEPTANCE")
    return r

def shard(i):
    assert 0<=i<SHARDS
    sources,_=restore()
    chosen=[s for s in sources if s["id"]%SHARDS==i]
    assert len(chosen)==2
    folder=OUT/f"shard-{i}"
    folder.mkdir(parents=True,exist_ok=False)
    all_rows=[]
    with (folder/"trials.jsonl").open("w") as out:
        for s in chosen:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(f"XORLIN1-{s['gbd_hash']}-{rep}").shuffle(arms)
                pair={}
                for arm in arms:
                    row=one(s,arm,rep)
                    all_rows.append(row)
                    out.write(json.dumps(row,sort_keys=True)+"\n");out.flush()
                    pair[arm]={"status":row["status"],
                        "strict":row["strict_accepted"],
                        "strict_PAR2_s":row["PAR2_strict_s"],
                        "kind":row.get("certificate_kind")}
                print("XORLIN1_PAIRED "+json.dumps(
                    {"id":s["id"],"rep":rep,"arms":pair},sort_keys=True),flush=True)
    assert len(all_rows)==2*REPS*len(ARMS)==24
    print("XORLIN1_SHARD "+json.dumps({"index":i,"sources":len(chosen),
       "trials":len(all_rows),"summary":{arm:{
         "strict_verified":sum(r["strict_accepted"] for r in all_rows if r["arm"]==arm),
         "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in all_rows if r["arm"]==arm),6)}
         for arm in ARMS}},sort_keys=True),flush=True)

def report():
    sources,p=restore()
    rows=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}/trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",i)
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    expected={(i,rep,arm) for i in range(10) for rep in range(REPS) for arm in ARMS}
    actual={(r["id"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(actual)==len(expected)==120 and actual==expected
    by_id={s["id"]:s for s in sources}
    critical=[]
    for r in rows:
        if r["critical"]:critical.append({"id":r["id"],"arm":r["arm"],"status":r["status"]})
        if r["source_sha256"]!=by_id[r["id"]]["sha256"]:
            critical.append({"id":r["id"],"reason":"SOURCE_SHA_CHANGED"})
        if r["strict_accepted"] and (
            not r["accepted"] or r.get("certificate_kind") not in STRICT):
            critical.append({"id":r["id"],"reason":"NONSTANDARD_UNSAT"})
        if not r["strict_accepted"] and r["PAR2_strict_s"]!=2*CAP:
            critical.append({"id":r["id"],"reason":"WRONG_PAR2_PENALTY"})
    for i in range(10):
        accepted=[r for r in rows if r["id"]==i and r["strict_accepted"]]
        if any(r["status"]=="SAT_VERIFIED" for r in accepted) and any(
           r["status"]=="UNSAT_VERIFIED" for r in accepted):
            critical.append({"id":i,"reason":"CONTRADICTORY_VERIFIED_OUTCOMES"})
    totals={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        totals[arm]={"attempts":len(rr),
           "strict_verified":sum(r["strict_accepted"] for r in rr),
           "strict_sources":len({r["id"] for r in rr if r["strict_accepted"]}),
           "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rr),6),
           "statuses":dict(collections.Counter(r["status"] for r in rr)),
           "certificate_kinds":dict(collections.Counter(r.get("certificate_kind")
                for r in rr if r["strict_accepted"]))}
    final={"status":"COMPLETE" if not critical else "CRITICAL",
        "originals":10,"trials":len(rows),
        "original_SHA_manifest":p["source_manifest_sha256"],
        "critical_count":len(critical),"critical":critical,
        "totals":totals,"single_logical_CPU":True,
        "new_source_only_method":True,
        "retrospective_after_source_analysis":True,"not_blind":True,
        "no_main_promotion":True}
    save(OUT/"final.json",final)
    print("XORLIN1_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if critical:raise SystemExit(1)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("prepare","shard","report"))
    a.add_argument("--index",type=int)
    args=a.parse_args()
    if args.action=="prepare":prepare()
    elif args.action=="shard":shard(args.index)
    else:report()

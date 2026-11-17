#!/usr/bin/env python3
"""Single-executable XORLIN1/CDCL ON vs OFF paired NEW original GBD sources 12x2x5.

This test is PROSPECTIVE at the original instance level; 12 new GBD sources
were preregistered before source download and any solver outcomes. One logical CPU per solver;
no parallel solver portfolio. Verifier is a separate post-solver process,
serially counted under the identical 8-second end-to-end cap.
"""
import argparse,collections,hashlib,importlib.util,json,os,pathlib,random,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"results/xorlin_cdcl1_prospective_mixed12"
DATA=HERE/"inputs"
BIN=ROOT/"build/drnas-xorlin-cdcl1"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
ARMS=("HYBRID_ON","HYBRID_OFF","Kissat","CaDiCaL","CryptoMiniSat")
CAP=8.0;SHARDS=4;REPS=2
BASELINES=("Kissat","CaDiCaL","CryptoMiniSat")
PROOF_KINDS={"VERIPB_XORLIN1","DRAT","MODEL","FRAT"}
LOCKED_CODE={
 "research/xorlin1/extract.py":"7deba9716ec2165ff61434c7c326c63d564cecc5c272e9bade679484a7c151a3",
 "research/xorlin1/emit_veripb.py":"f3636b39c9f02a7b0fdfa166b982667c64b6ffb19de64dc2229cdee8a9a4ec07",
 "research/xorlin1/selftest.py":"19147961e174777c970695847d893518d50931377896c6936b606f0d626fd40a",
 "research/math5/check_math5.py":"ebfec304d1823574bbf2530d3e277e468446965362f6a6a6ad7d8371473a381a",
 "research/math5/emit_veripb_xor234_split.py":"f1d7d7e782a9b8db58c711972d034b0b037cd0899f279662fefdc789fcf288d0",
 "research/math5/xor3_tseitin_id6.py":"a2907650bb9f4276229634037e92014b26287bc7c78aec8fc090d349068392b3"
}
def sha(path):return frozen.sha(path)
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def cpu1():
    if hasattr(os,"sched_setaffinity"):
        core=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{core})
        assert len(os.sched_getaffinity(0))==1
def locked():
    for path,expect in LOCKED_CODE.items():
        assert sha(ROOT/path)==expect,("OLD_CERTIFIED_CODE_MODIFIED",path)
    assert BIN.is_file()
    assert sha(BIN)=="2046aee7f7cb1eb3dfc44b2e7a7b5a9f69b482230f106a4aaea93ab968f60646", "FROZEN_ONEPROCESS_BINARY_CHANGED"
    assert sha(ROOT/"research/xorlin_cdcl1/solver.cpp")=="19d55c9e39fd876e70a7617bd6ec12d4b2bdafb1dc23f3c1f45573e817c36a56", "FROZEN_ONEPROCESS_CPP_CHANGED"
    assert sha(ROOT/"src/drnas_x59.cpp")=="87985c90d03ce03aba069bb2a0e594f81cdb842bc1b0d49eaad79891c77b49a2", "FROZEN_X59_CDCL_CHANGED"
def sources():
    prespec=json.loads((HERE/"prespec.json").read_text())
    m=json.loads((DATA/"manifest.json").read_text())
    assert prespec["protocol"]=="DRNAS-XORLIN-CDCL1-PROSPECTIVE-MIXED12-20261117-V2"
    assert prespec["preregistration_history"]["no_previous_solver_evaluations"] is True
    assert prespec["preregistration_history"]["v1_failed_preflight_runs"]==[44070338062,44070631698]
    assert m["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert m["protocol"]==prespec["protocol"]
    assert m["selected_count"]==len(m["sources"])==prespec["exact_selected_count"]==12
    assert len({s["sha256"] for s in m["sources"]})==12
    assert sha(HERE/"prespec.json")==m["prespec_sha256"]
    assert m["provenance"]["previous_source_count"]==119
    assert m["provenance"]["previous_gbd_overlap"]==0
    assert m["provenance"]["previous_iso_overlap"]==0
    assert m["provenance"]["source_isohashes_disjoint"]
    assert m["provenance"]["source_GBD_disjoint"]
    for name in prespec["earlier_source_manifests"]:
        assert sha(ROOT/name)==m["provenance"]["old_manifests_sha256"][name],("PRIOR_MANIFEST_CHANGED",name)
    for selected,original in zip(prespec["sources"],m["sources"]):
        for field in ("id","gbd_hash","isohash","isohash2","family","catalog_result","track"):
            assert selected[field]==original[field],("SOURCE_SELECTION_CHANGED",original["id"],field)
        assert original["file_id"]==original["gbd_hash"]
        assert sha(ROOT/original["path"])==original["sha256"]
    return m
def prepare():
    cpu1();locked()
    m=sources()
    policy={"experiment":"DRNAS-XORLIN-CDCL1-PROSPECTIVE-ORIGINAL12-V2",
       "sources":12,"reps":REPS,"shards":SHARDS,"arms":list(ARMS),
       "expected_trials":12*REPS*len(ARMS),"cap_s":CAP,
       "strict_timeout_penalty_s":2*CAP,
       "source_manifest_sha256":sha(DATA/"manifest.json"),
       "prespec_sha256":sha(HERE/"prespec.json"),
       "prior_119_source_manifests_sha256":m["provenance"]["old_manifests_sha256"],
       "locked_math_source_sha256":LOCKED_CODE,
       "frozen_reference_binaries_sha256":frozen.pinned(),
       "old_cdcl_cpp_sha256":sha(ROOT/"src/drnas_x59.cpp"),
       "new_native_cpp_sha256":sha(ROOT/"research/xorlin_cdcl1/solver.cpp"),
       "new_binary_sha256":sha(BIN),
       "workflow_commit_sha256":os.environ.get("GITHUB_SHA"),
       "one_logical_CPU_per_solver":True,
       "single_process_for_math_and_CDCL":True,
       "embedded_Python_not_native_math_port":True,
       "external_Veripb_or_DRAT_check_after_solver_and_within_e2e":True,
       "no_parallel_solver_portfolio":True,
       "instance_level_prospective":True,
       "not_family_disjoint":True,
       "no_main_promotion":True}
    save(OUT/"protocol.json",policy)
    print("XORLIN_CDCL1_PROSPECTIVE_PREPARED "+json.dumps({
       "originals":12,"attempts":policy["expected_trials"],
       "binary_sha256":policy["new_binary_sha256"]},sort_keys=True),flush=True)
def restore():
    cpu1();locked()
    m=sources()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["experiment"]=="DRNAS-XORLIN-CDCL1-PROSPECTIVE-ORIGINAL12-V2"
    assert p["source_manifest_sha256"]==sha(DATA/"manifest.json")
    assert p["prespec_sha256"]==sha(HERE/"prespec.json")
    assert p["frozen_reference_binaries_sha256"]==frozen.pinned()
    assert p["new_native_cpp_sha256"]==sha(ROOT/"research/xorlin_cdcl1/solver.cpp")
    assert p["old_cdcl_cpp_sha256"]==sha(ROOT/"src/drnas_x59.cpp")
    assert p["new_binary_sha256"]==sha(BIN)
    assert p["workflow_commit_sha256"]==os.environ.get("GITHUB_SHA")
    return m["sources"],p
def make_row(src,rep,arm,started,rc,status,route=None,proof=None,
             critical=False,reason=None,checker_s=0):
    wall=time.perf_counter()-started
    if wall>CAP and not critical:status="E2E_OVER_CAP"
    accepted=status in ("SAT_VERIFIED","UNSAT_VERIFIED") and not critical and wall<=CAP
    kind=("MODEL" if status=="SAT_VERIFIED" else
         ("VERIPB_XORLIN1" if route=="GATE_VERIPB" else "DRAT")
         if status=="UNSAT_VERIFIED" else None)
    return {"id":src["id"],"file_id":src["file_id"],
        "family":src["family"],"source_sha256":src["sha256"],
        "arm":arm,"rep":rep,"rc":rc,"status":status,
        "accepted":accepted,"strict_accepted":accepted,
        "certificate_kind":kind,"proof_route":route,"critical":critical,
        "reason":reason,
        "proof_bytes":proof.stat().st_size if accepted and proof and proof.is_file() else 0,
        "proof_sha256":sha(proof) if accepted and proof and proof.is_file() else None,
        "e2e_s":round(wall,6),
        "checker_s":round(checker_s,6),
        "PAR2_strict_s":round(wall if accepted else 2*CAP,6)}
def hybrid_trial(src,rep,arm):
    started=time.perf_counter()
    cnf=ROOT/src["path"]
    assert sha(cnf)==src["sha256"]
    with tempfile.TemporaryDirectory(prefix="drnas-xorlin-cdcl1-") as temp:
        pb=pathlib.Path(temp)/"proof"
        gate="on" if arm=="HYBRID_ON" else "off"
        remain=CAP-(time.perf_counter()-started)
        if remain<0.01:return make_row(src,rep,arm,started,None,"NO_SOLVE_BUDGET")
        args=[str(BIN),str(cnf),"--mode","core","--gate",gate,
            "--gate-ms","700","--time",str(remain),"--repo-root",str(ROOT),
            "--proof",str(pb)]
        run=frozen.execute(args,remain)
        if run["expired"]:
            return make_row(src,rep,arm,started,run["returncode"],"TIMEOUT")
        code=run["returncode"]
        lines=run["stdout"].splitlines()
        routes=[line.rsplit(" ",1)[-1] for line in lines if
                line.startswith("c XORLIN_CDCL1_ROUTE ")]
        if code not in (0,10,20):
            return make_row(src,rep,arm,started,code,"SOLVER_ERROR",critical=True,
                reason=(run["stdout"]+run["stderr"])[-550:])
        if len(routes)!=1 or routes[0] not in ("GATE_VERIPB","CDCL_DRAT"):
            return make_row(src,rep,arm,started,code,"MISSING_OR_INVALID_PROOF_ROUTE",
                            critical=True,reason=run["stdout"][-300:])
        route=routes[0]
        if gate=="off" and route!="CDCL_DRAT":
            return make_row(src,rep,arm,started,code,"OFF_USED_GF2_ROUTE",
                            route=route,critical=True)
        if code==0:
            return make_row(src,rep,arm,started,code,"UNKNOWN",route=route)
        expected="s SATISFIABLE" if code==10 else "s UNSATISFIABLE"
        if expected not in lines:
            return make_row(src,rep,arm,started,code,"INVALID_DIMACS_STATUS",
                            critical=True,route=route)
        if code==10:
            if route=="GATE_VERIPB":
                return make_row(src,rep,arm,started,code,"GF2_SAT_CONTRADICTION",
                                critical=True,route=route)
            if not frozen.model_ok(cnf,run["stdout"]):
                return make_row(src,rep,arm,started,code,"INVALID_SAT_MODEL",
                                critical=True,route=route)
            return make_row(src,rep,arm,started,code,"SAT_VERIFIED",route=route)
        if not pb.is_file() or not pb.stat().st_size:
            return make_row(src,rep,arm,started,code,"UNSAT_NO_PROOF",
                            critical=True,route=route)
        remain=CAP-(time.perf_counter()-started)
        if remain<=0.01:
            return make_row(src,rep,arm,started,code,"NO_EXTERNAL_CHECK_BUDGET",
                            route=route)
        if route=="GATE_VERIPB":
            command=[str(ROOT/"veripb-tool/bin/veripb"),
                     "--cnf",str(cnf),str(pb)]
            proof_verdict="s VERIFIED UNSATISFIABLE"
        else:
            command=[str(ROOT/"build/drat-trim"),str(cnf),str(pb)]
            proof_verdict="VERIFIED"
        check=frozen.execute(command,remain)
        if check["expired"]:
            return make_row(src,rep,arm,started,code,"CHECK_TIMEOUT",
                            route=route,checker_s=check["wall_s"])
        if check["returncode"]!=0 or proof_verdict not in (check["stdout"]+check["stderr"]):
            return make_row(src,rep,arm,started,code,"INVALID_EXTERNAL_PROOF",
                route=route,critical=True,checker_s=check["wall_s"],
                reason=(check["stdout"]+check["stderr"])[-700:])
        row=make_row(src,rep,arm,started,code,"UNSAT_VERIFIED",route=route,
                     proof=pb,checker_s=check["wall_s"])
        if row["strict_accepted"]:
            dst=OUT/"accepted_external_proofs"/f"source_{src['id']:02d}"
            dst.mkdir(parents=True,exist_ok=True)
            kind="VERIPB" if route=="GATE_VERIPB" else "DRAT"
            (dst/f"rep{rep}_{arm}_{kind}.proof").write_bytes(pb.read_bytes())
        return row
def one(src,rep,arm):
    row=hybrid_trial(src,rep,arm) if arm.startswith("HYBRID_") else frozen.trial(src,arm,rep)
    assert row["id"]==src["id"] and row["rep"]==rep
    assert row["arm"]==arm and row["source_sha256"]==src["sha256"]
    assert row["PAR2_strict_s"]<=16
    if row["strict_accepted"] and (not row["accepted"] or
        row.get("certificate_kind") not in PROOF_KINDS):
        raise RuntimeError("INVALID_STRICT_CERTIFICATE_KIND")
    return row
def shard(i):
    assert 0<=i<SHARDS
    cases,_=restore()
    selected=[s for s in cases if s["id"]%SHARDS==i]
    assert len(selected)==3
    folder=OUT/f"shard-{i}"
    folder.mkdir(parents=True,exist_ok=False)
    records=[]
    with (folder/"trials.jsonl").open("w") as stream:
        for source in selected:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random("XORLIN-CDCL1-"+source["sha256"]+":"+str(rep)).shuffle(arms)
                pair={}
                for arm in arms:
                    row=one(source,rep,arm)
                    records.append(row)
                    stream.write(json.dumps(row,sort_keys=True)+"\n")
                    stream.flush()
                    pair[arm]={"status":row["status"],
                        "strict":row["strict_accepted"],
                        "route":row.get("proof_route"),
                        "PAR2":row["PAR2_strict_s"]}
                print("XORLIN_CDCL1_PROSPECTIVE_PAIR "+json.dumps(
                    {"id":source["id"],"rep":rep,"arms":pair},sort_keys=True),flush=True)
    assert len(records)==3*REPS*len(ARMS)==30
    print("XORLIN_CDCL1_PROSPECTIVE_SHARD "+json.dumps({
      "shard":i,"attempts":len(records),
      "totals":{arm:{"strict":sum(r["strict_accepted"] for r in records if r["arm"]==arm),
        "PAR2":round(sum(r["PAR2_strict_s"] for r in records if r["arm"]==arm),6)}
              for arm in ARMS}},sort_keys=True),flush=True)
def aggregate():
    cases,p=restore()
    entries=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}/trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",i)
        entries.extend(json.loads(x) for x in path.read_text().splitlines())
    expected={(i,rep,arm) for i in range(12) for rep in range(REPS) for arm in ARMS}
    observed={(r["id"],r["rep"],r["arm"]) for r in entries}
    assert len(entries)==len(expected)==len(observed)==120 and observed==expected
    source_by_id={s["id"]:s for s in cases}
    critical=[]
    for r in entries:
        if r.get("critical"):critical.append({"arm":r["arm"],"id":r["id"],"reason":r["status"]})
        if r["source_sha256"]!=source_by_id[r["id"]]["sha256"]:
            critical.append({"id":r["id"],"reason":"SOURCE_SHA_MISMATCH"})
        if r["strict_accepted"] and (
           not r["accepted"] or r.get("certificate_kind") not in PROOF_KINDS):
            critical.append({"id":r["id"],"reason":"UNVERIFIED_STRICT"})
        if not r["strict_accepted"] and r["PAR2_strict_s"]!=16:
            critical.append({"id":r["id"],"reason":"PAR2_BAD_PENALTY"})
    for id in range(12):
        subset=[r for r in entries if r["id"]==id and r["strict_accepted"]]
        if any(x["status"]=="SAT_VERIFIED" for x in subset) and (
           any(x["status"]=="UNSAT_VERIFIED" for x in subset)):
            critical.append({"id":id,"reason":"SAT_UNSAT_CONTRADICTION"})
    totals={}
    for arm in ARMS:
        rr=[r for r in entries if r["arm"]==arm]
        totals[arm]={"attempts":len(rr),
            "strict_verified":sum(r["strict_accepted"] for r in rr),
            "strict_sources":len({r["id"] for r in rr if r["strict_accepted"]}),
            "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rr),6),
            "proof_kinds":dict(collections.Counter(r.get("certificate_kind") for r in rr if r["strict_accepted"])),
            "routes":dict(collections.Counter((r.get("proof_route") or "NO_ROUTE") for r in rr if r["arm"].startswith("HYBRID_"))),
            "statuses":dict(collections.Counter(r["status"] for r in rr))}
    regressions=[]
    per={(r["id"],r["rep"],r["arm"]):r for r in entries}
    for i in range(12):
        for rep in range(REPS):
            off=per[(i,rep,"HYBRID_OFF")]
            on=per[(i,rep,"HYBRID_ON")]
            if off["strict_accepted"] and not on["strict_accepted"]:
                regressions.append({"id":i,"rep":rep,"OFF":off["status"],"ON":on["status"]})
    final={"status":"COMPLETE" if not critical else "CRITICAL",
       "sources":12,"attempts":len(entries),"critical_count":len(critical),
       "critical":critical,"totals":totals,
       "ON_solved_to_unsolved_regressions":regressions,
       "fixed_reference_source_SHA":p["source_manifest_sha256"],
       "single_executable_single_process":True,
       "math_method_embedded_python":True,
       "internal_CDCL_fallback":True,
       "strict_postcheck_in_E2E":True,
       "one_logical_CPU_per_solver":True,"cap_s":CAP,
       "instance_level_prospective":True,
       "not_family_disjoint":True,"no_main_promotion":True,
       "algorithm_frozen_sha256":p["locked_math_source_sha256"],
       "candidate_binary_sha256":p["new_binary_sha256"],
       "original_source_manifest_sha256":p["source_manifest_sha256"]}
    save(OUT/"final.json",final)
    print("XORLIN_CDCL1_PROSPECTIVE_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if critical:raise SystemExit(1)
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("prepare","shard","aggregate"))
    a.add_argument("--index",type=int)
    args=a.parse_args()
    if args.action=="prepare":prepare()
    elif args.action=="shard":shard(args.index)
    else:aggregate()

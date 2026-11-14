#!/usr/bin/env python3
"""RET6 REAL14: source-verified six-arm continual clause retention ablation.

No fitted rules. 14 original SAT2024 CNFs previously present in REAL36,
source SHA and original archive pinned, not blind prospective data.
Each arm runs the same native CDCL on ONE logical CPU, all operations
serial per source, with independent original SAT model/UNSAT DRAT checks.
Six policies differ only in deletion-protection/quota logic as defined
in drnas_retain6_build.py. All future-use telemetry is diagnostic only.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,resource,signal,subprocess,sys,tempfile,time
from pathlib import Path

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research"))
import drnas_x55_cpu_real36 as REAL

OUT=Path("retain6_real14")
OUT.mkdir(exist_ok=True)
BIN=(R/"build/drnas-ret6").resolve()
FROZEN=(R/"build/drnas-ret6-reference").resolve()
DRAT=(R/"build/drat-trim").resolve()
IDS=(0,3,5,6,9,12,15,16,19,20,23,24,28,31)
MODES=("OFF","FULL","LBD_ONLY","RECENT_ONLY","QUOTA_ONLY","FULL_HALF")
SHARDS=3
CAP=5.0

def sha(b):return hashlib.sha256(b).hexdigest()
def emit(tag,d):print(tag+" "+json.dumps(d,sort_keys=True),flush=True)
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")

def protocol():
    sources,old=REAL.official_manifest()
    assert len(sources)==36
    byid={s["id"]:s for s in sources}
    assert len(byid)==36 and len(IDS)==len(set(IDS)) and all(i in byid for i in IDS)
    selected=[byid[i] for i in IDS]
    assert len({s["sha256"] for s in selected})==len(selected)
    for s in selected:
        raw=Path(s["path"]).read_bytes()
        assert sha(raw)==s["sha256"],("ORIGINAL_SHA_DRIFT",s["id"])
        n,clauses=REAL.parse_cnf(raw)
        assert n==s["nvars"] and len(clauses)==s["nclauses"]
    freeze={
        "status":"FROZEN_BEFORE_SOLVING",
        "original_competition":"SAT Competition 2024",
        "retrospective_not_blind":True,"baseline_real36_run":43387395060,
        "real36_manifest_sha256":old["manifest_sha256"],
        "cases":len(selected),"source_ids":list(IDS),
        "source_sha256":[s["sha256"] for s in selected],
        "families":dict(collections.Counter(s["family"] for s in selected)),
        "modes":list(MODES),"fixed_cap_s":CAP,"shards":SHARDS,
        "same_native_x5_core":True,"one_logical_cpu_each_solver":True,
        "single_solver_process_serial_per_source":True,
        "module_changes":"continuous protection/reduction choices only",
        "all_proofs_original_source":True,"no_main_modification":True,
        "no_fitted_policy_or_promotion":True
    }
    return selected,freeze

def trial(source,mode,reference=False):
    raw=Path(source["path"]).read_bytes()
    assert sha(raw)==source["sha256"]
    n,clauses=REAL.parse_cnf(raw)
    assert n==source["nvars"] and len(clauses)==source["nclauses"]
    with tempfile.TemporaryDirectory() as d:
        proof=Path(d)/"result.drat"
        timeinfo=Path(d)/"usage.txt"
        cmd=[str(FROZEN if reference else BIN),
             str(Path(source["path"]).resolve()),"--mode","core",
             "--time",str(CAP),"--stats","--x5-no-minimize",
             "--x5-retain" if mode!="OFF" else "--x5-no-retain",
             "--proof",str(proof)]
        if not reference:cmd+=["--r6-policy",mode]
        cmd=["/usr/bin/time","-f","%U %S %M","-o",str(timeinfo),*cmd]
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        killed=False
        try:stdout,stderr=p.communicate(timeout=CAP+1.2)
        except subprocess.TimeoutExpired:
            killed=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            stdout,stderr=p.communicate()
        wall=time.perf_counter()-start
        cpu=None;rss=None
        if timeinfo.is_file():
            try:
                stats_line=timeinfo.read_text().strip().splitlines()[-1].split()
                cpu=float(stats_line[0])+float(stats_line[1]);rss=int(stats_line[2])
            except (ValueError,IndexError):pass
        if not killed:
            assert p.returncode in (0,10,20),(
                "EXEC_ERROR",source["id"],mode,p.returncode,stderr[-900:])
        status="TIMEOUT" if killed else {
            10:"SAT",20:"UNSAT",0:"UNKNOWN"}.get(p.returncode,"UNKNOWN")
        verified=False;check_s=0.0
        if status=="SAT":
            verified=REAL.check_sat(stdout,clauses,n)
            assert verified,("ORIGINAL_SAT_MODEL_INVALID",source["id"],mode)
        elif status=="UNSAT":
            assert proof.is_file() and proof.stat().st_size,(
                "ORIGINAL_UNSAT_PROOF_MISSING",source["id"],mode)
            started=time.perf_counter()
            verify=subprocess.run([str(DRAT),str(Path(source["path"]).resolve()),
                                   str(proof)],capture_output=True,text=True,timeout=75)
            check_s=time.perf_counter()-started
            verified=verify.returncode==0 and "s VERIFIED" in verify.stdout
            assert verified,("ORIGINAL_DERIVATION_INVALID",source["id"],mode,
                             verify.stdout[-500:],verify.stderr[-500:])
        fields={}
        if not killed:
            for line in stderr.splitlines():
                tag,sp,payload=line.partition(" ")
                if tag not in ("X41_STATS","X5_STATS","RET6_STATS"):continue
                assert tag not in fields,("DUPLICATE_TELEMETRY",tag)
                fields[tag]=json.loads(payload)
            assert "X41_STATS" in fields and "X5_STATS" in fields
            if not reference:assert "RET6_STATS" in fields
            assert fields["X41_STATS"]["status"]==status
        core=fields.get("X41_STATS",{})
        retain=fields.get("RET6_STATS",{})
        if not reference:
            assert retain.get("policy")==mode
            assert retain.get("effective_reductions",0)<=retain.get("reduction_calls",0)
            assert retain.get("total_deleted",0)<=retain.get("total_candidates",0)
            assert retain.get("first_reduce_conflicts",-1)>=0 or retain.get("reduction_calls",0)==0
            if mode=="OFF":
                assert not retain["protected_low"] and not retain["protected_recent"] and not retain["protected_combo"]
        return {
            "arm":mode,"status":status,"verified":verified,
            "accepted":verified and wall<=CAP,
            "wall_e2e_s":wall,"cpu_s":cpu,"maxrss_kib":rss,
            "PAR2_s":wall if verified and wall<=CAP else 2*CAP,
            "proof_check_s":check_s,
            "conflicts":core.get("conflicts"),"decisions":core.get("decisions"),
            "propagations":core.get("propagations"),
            "learned":core.get("learnt"),"removed":core.get("reduce_removed"),
            "protected":fields.get("X5_STATS",{}).get("protected_clauses"),
            "retention":retain
        }

def shard(k):
    assert k in range(SHARDS)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    for p in (BIN,FROZEN,DRAT):assert p.is_file(),p
    sources,proto=protocol()
    group=[s for i,s in enumerate(sources) if i%SHARDS==k]
    assert len(group)>=4
    folder=OUT/str(k)
    folder.mkdir(parents=True,exist_ok=True)
    manifest_path=folder/"protocol.json"
    save(manifest_path,proto)
    emit("RET6_FROZEN",{"shard":k,"cases":len(group),
        "protocol_sha256":sha(manifest_path.read_bytes()),
        "source_ids":[s["id"] for s in group]})
    rng=random.Random(141177+k)
    rng.shuffle(group)
    entries=[]
    for source in group:
        arms=list(MODES)
        random.Random(int(source["sha256"][:14],16)).shuffle(arms)
        res={}
        for arm in arms:res[arm]=trial(source,arm)
        verified={r["status"] for r in res.values() if r["verified"]}
        assert len(verified)<=1,("SOURCE_CONTRADICTORY_MODELS",source["id"],verified)
        # Different policy may change later trajectory but never pre-first
        # deletion. This SHA-independent prefix is a causal control.
        signature=("first_reduce_conflicts","first_reduce_decisions","first_reduce_hash")
        signatures=[tuple(res[a]["retention"][key] for key in signature)
                    for a in MODES]
        assert len(set(signatures))==1,(
            "PRE_FIRST_DELETION_PREFIX_NOT_IDENTICAL",source["id"],signatures)
        if source["id"] in (6,16):
            for mode in ("OFF","FULL"):
                baseline=trial(source,mode,reference=True)
                if baseline["verified"] and res[mode]["verified"]:
                    for key in ("status","conflicts","decisions",
                                "propagations","learned","removed"):
                        assert baseline[key]==res[mode][key],(
                            "INSTRUMENTATION_ALTERED_SOLVE",source["id"],mode,key,
                            baseline.get(key),res[mode].get(key))
        record={"id":source["id"],"family":source["family"],
                "sha256":source["sha256"],"arms":res}
        entries.append(record)
        emit("RET6_PAIR",{
            "id":source["id"],"family":source["family"],
            "verified":{a:res[a]["verified"] for a in MODES},
            "status":{a:res[a]["status"] for a in MODES},
            "PAR2_s":{a:round(res[a]["PAR2_s"],5) for a in MODES},
            "conflicts":{a:res[a]["conflicts"] for a in MODES},
            "deletion_cycles":{a:res[a]["retention"].get("effective_reductions") for a in MODES},
            "deleted":{a:res[a]["retention"].get("total_deleted") for a in MODES}
        })
    (folder/"pairs.jsonl").write_text(
        "".join(json.dumps(r,sort_keys=True)+"\n" for r in entries))
    emit("RET6_SHARD_COMPLETE",{"shard":k,"pairs":len(entries),"serial_one_cpu":True})

def final():
    sources,proto=protocol()
    all_entries=[]
    for k in range(SHARDS):
        shard_dir=Path("retain6_downloads")/("ret6-shard-"+str(k))/"retain6_real14"/str(k)
        p=shard_dir/"protocol.json"
        assert json.loads(p.read_text())==proto,(
            "FROZEN_MANIFEST_MISMATCH",k)
        for line in (shard_dir/"pairs.jsonl").read_text().splitlines():
            all_entries.append(json.loads(line))
    expected={(s["id"],s["sha256"]) for s in sources}
    observed=[(r["id"],r["sha256"]) for r in all_entries]
    assert len(observed)==len(set(observed))==len(expected) and set(observed)==expected
    byarm={}
    for a in MODES:
        cur=[r["arms"][a] for r in all_entries]
        byarm[a]={
            "cases":len(cur),
            "verified":sum(x["verified"] for x in cur),
            "PAR2_s":round(sum(x["PAR2_s"] for x in cur),5),
            "cpu_s":round(sum(x["cpu_s"] or 0 for x in cur),5),
            "effective_reductions":sum(x["retention"]["effective_reductions"] for x in cur),
            "protected_low":sum(x["retention"]["protected_low"] for x in cur),
            "protected_recent":sum(x["retention"]["protected_recent"] for x in cur),
            "protected_combo":sum(x["retention"]["protected_combo"] for x in cur),
            "deleted":sum(x["retention"]["total_deleted"] for x in cur),
            "reason_BCP_postfirst500":sum(
                x["retention"]["post_first_500_BCP_reasons"] for x in cur
                if x["retention"]["post_first_500_fully_exposed"]),
            "reason_analysis_postfirst500":sum(
                x["retention"]["post_first_500_analysis_reasons"] for x in cur
                if x["retention"]["post_first_500_fully_exposed"]),
        }
    paired={}
    full={r["id"]:r["arms"]["FULL"] for r in all_entries}
    for arm in MODES:
        if arm=="FULL":continue
        diff=[]
        wins=losses=ties=0
        for x in all_entries:
            baseline=full[x["id"]]["PAR2_s"]
            val=x["arms"][arm]["PAR2_s"]
            diff.append(val-baseline)
            if val+0.005 < baseline:wins+=1
            elif baseline+0.005<val:losses+=1
            else:ties+=1
        paired[arm+"_minus_FULL"]={
            "delta_PAR2_s":round(sum(diff),5),
            "faster_arms":wins,"slower_arms":losses,"tied_or_both_timeout":ties
        }
    original_successes={
        "all_valid_proofs_original_CNF":True,
        "no_mismatched_pre_first_deletion_state":True,
        "one_logical_CPU_per_solver":True,
        "all_sequential_runs_within_each_shard":True}
    report={
        "status":"COMPLETE","sources":len(all_entries),
        "cap_s":CAP,"shards":SHARDS,
        "retrospective":True,"not_blind":True,"no_general_speedup_claim":True,
        "comparison_is_ablations_not_training":True,
        "no_main_changes":True,"no_promotion":True,
        "verified_original_source_controls":original_successes,
        "aggregates":byarm,"paired_against_full":paired,
        "original_source_manifest_sha256":proto["real36_manifest_sha256"]}
    save(OUT/"final_report.json",report)
    emit("RET6_FINAL",report)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("shard","final"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    shard(args.shard) if args.stage=="shard" else final()

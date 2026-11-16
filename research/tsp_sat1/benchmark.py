#!/usr/bin/env python3
"""TSP-SAT1 paired proof-aware pilot: DRNAS native, native Structure-Gate, 3 references.

Independent Held-Karp ground truth, frozen integer Euclidean TSP sources,
Tseitin decision CNFs (tour cost <= B), verified SAT models/tours, and
externally verified DRAT/FRAT/VeriPB for UNSAT on unchanged decision CNFs.

This certifies the CNF answer, conditional on the correctness of the
TSP-to-CNF reduction. The encoder is exhaustively tested on n<=6 but is
NOT formally verified. No original-TSPLIB/heldout or P=NP claim.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/tsp_sat1"))
import encoding as enc

OUT=ROOT/"results/tsp_sat1"
BIN={
 "DRNAS_X59":"build/drnas-sat-native-x59",
 "DRNAS_STRUCTURE_GATE":"build/drnas-x59-structure-gate1",
 "Kissat":"build/kissat","CaDiCaL":"build/cadical",
 "CryptoMiniSat":"build/cms"
}
ARMS=tuple(BIN)
REPS=2
CAP=12.0
SHARDS=5
CONF=[("euclidean5",5,251),("euclidean6",6,467),
      ("euclidean7",7,685),("euclidean8",8,853),("euclidean9",9,991)]
KINDS=("MODEL","DRAT","FRAT","VERIPB_MATH5")
REQUIRED=tuple(sorted(set(BIN.values())|{
    "build/drat-trim","build/frat-rs","veripb-tool/bin/veripb",
    "build/cms-libs/usr/lib/x86_64-linux-gnu/libcryptominisat5.so.5.11"}))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):
            h.update(part)
    return h.hexdigest()

def save(path,record):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")

def affinity():
    mask=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(mask)})
    assert len(os.sched_getaffinity(0))==1

def coords_for(n,seed):
    rng=random.Random(seed)
    seen=set()
    pts=[]
    while len(pts)<n:
        p=(rng.randrange(0,72),rng.randrange(0,72))
        if p in seen:continue
        seen.add(p);pts.append(p)
    return [list(p) for p in pts]

def freeze():
    affinity()
    enc.selftest()
    sources=[]
    for name,n,seed in CONF:
        coords=coords_for(n,seed)
        D=enc.euc_distance(coords)
        optimum,route=enc.held_karp(D)
        assert optimum>0
        directory=OUT/"sources"/name
        original=directory/"tsp.json"
        save(original,dict(name=name,metric="EUC_2D_INTEGER",
            coords=coords,n=n,seed=seed))
        variants={}
        for label,bound in (("BELOW_OPT",optimum-1),("AT_OPT",optimum)):
            cnf=directory/(label+".cnf")
            expr,info=enc.encode(coords,bound)
            expr.output(cnf)
            variants[label]=dict(path=str(cnf.relative_to(ROOT)),
                sha256=sha(cnf),cnf_vars=expr.nvars,
                cnf_clauses=len(expr.clauses),B=bound,
                expected="UNSAT" if label=="BELOW_OPT" else "SAT")
            if n<=6:
                # The full set of TSP tours has already been exhaustively
                # checked by encoding.selftest on separate controls.
                for perm in __import__("itertools").permutations(range(1,n)):
                    enc.evaluate_tour(expr,info,(0,)+perm)
        sources.append(dict(name=name,n=n,seed=seed,coords=coords,
           original_json=str(original.relative_to(ROOT)),
           original_sha256=sha(original),
           opt_held_karp=optimum,
           opt_tour=list(route),
           variants=variants))
    manifest=dict(protocol="DRNAS-TSP-SAT1-EUC-EXACT-CNF-V1",
        source_is_synthetic=True,no_tsplib_originals=True,
        no_new_blind_holdout=True,formal_encoder_proof=False,
        cases=sources)
    save(OUT/"manifest.json",manifest)
    pinned={p:sha(ROOT/p) for p in REQUIRED}
    proto=dict(source_manifest_sha256=sha(OUT/"manifest.json"),
        code_sha=sha(Path(__file__)),
        encoder_sha=sha(ROOT/"research/tsp_sat1/encoding.py"),
        git_sha=os.environ.get("GITHUB_SHA"),
        binary_sha256=pinned,arms=ARMS,cap_s=CAP,repetitions=REPS,
        sources=len(sources),decision_cnfs=2*len(sources),
        expected_trials=len(sources)*2*REPS*len(ARMS),
        one_logical_cpu=True,serial_trials=True,no_parallel_solver_portfolio=True,
        proof_checker_inside_solver_cap=True,
        CNF_source_grounding="exhaustive n<=6 controls + Held-Karp for every case; encoder not formally verified",
        no_main_promotion=True)
    save(OUT/"protocol.json",proto)
    print("TSP_SAT1_READY "+json.dumps(dict(
        instances=len(sources),formulas=2*len(sources),
        trials=proto["expected_trials"],optima={
            s["name"]:s["opt_held_karp"] for s in sources},
        binary_hashes=pinned),sort_keys=True),flush=True)

def restore():
    affinity()
    manifest=json.loads((OUT/"manifest.json").read_text())
    proto=json.loads((OUT/"protocol.json").read_text())
    assert manifest["protocol"]=="DRNAS-TSP-SAT1-EUC-EXACT-CNF-V1"
    assert proto["source_manifest_sha256"]==sha(OUT/"manifest.json")
    assert proto["encoder_sha"]==sha(ROOT/"research/tsp_sat1/encoding.py")
    assert proto["code_sha"]==sha(Path(__file__))
    assert proto["git_sha"]==os.environ.get("GITHUB_SHA")
    assert proto["binary_sha256"]=={p:sha(ROOT/p) for p in REQUIRED}
    assert proto["arms"]==list(ARMS) and proto["cap_s"]==CAP
    assert len(manifest["cases"])==len(CONF)
    for case in manifest["cases"]:
        c=case["coords"]
        assert c==coords_for(case["n"],case["seed"])
        assert case["opt_held_karp"]==enc.held_karp(enc.euc_distance(c))[0]
        assert sha(ROOT/case["original_json"])==case["original_sha256"]
        for spec in case["variants"].values():
            assert sha(ROOT/spec["path"])==spec["sha256"],"CNF mutated"
    return manifest,proto

def exec_limited(argv,timeout):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,)*2)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",
             MKL_NUM_THREADS="1",
             LD_LIBRARY_PATH=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu"))
    t=time.perf_counter()
    task=subprocess.Popen([str(x) for x in argv],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,env=env,start_new_session=True,
        preexec_fn=limits)
    expired=False
    try:
        stdout,stderr=task.communicate(timeout=max(0.001,timeout))
    except subprocess.TimeoutExpired:
        expired=True
        try:os.killpg(task.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=task.communicate()
    return dict(rc=task.returncode,stdout=stdout,stderr=stderr,
                wall_s=time.perf_counter()-t,expired=expired)

def args_for(arm,cnf,drat,certificate):
    if arm=="DRNAS_X59":
        return [ROOT/BIN[arm],cnf,"--mode","core","--time",str(CAP),
                "--proof",drat,"--stats"]
    if arm=="DRNAS_STRUCTURE_GATE":
        return [ROOT/BIN[arm],cnf,"--mode","core","--time",str(CAP),
                "--sat-construct-ms","25","--math5-ms","100",
                "--structure-gate-ms","12","--math5-certificate",certificate,
                "--proof",drat,"--stats"]
    if arm=="Kissat":return [ROOT/BIN[arm],cnf,drat]
    if arm=="CaDiCaL":return [ROOT/BIN[arm],"-q","--no-binary",cnf,drat]
    if arm=="CryptoMiniSat":
        return [ROOT/BIN[arm],"--threads=1","--verb=0","--frat="+str(drat),cnf]
    raise ValueError(arm)

def trial(case,label,rep,arm):
    taskinfo=case["variants"][label]
    cnf=ROOT/taskinfo["path"]
    assert sha(cnf)==taskinfo["sha256"]
    # Independently regenerate the mapping; reject any encoder drift.
    _,encoded=enc.encode(case["coords"],taskinfo["B"])
    start=time.perf_counter()
    status="UNKNOWN";proof_type=None;strict=False;critical=False;details=""
    checker_s=0;solver_s=0;found_cost=None;route=None
    with tempfile.TemporaryDirectory(prefix="tsp-sat1-") as td:
        work=Path(td)
        certificate=work/"math5.json"
        proof=work/("proof.frat" if arm=="CryptoMiniSat" else "proof.drat")
        ran=exec_limited(args_for(arm,cnf,proof,certificate),CAP)
        solver_s=ran["wall_s"]
        status="TIMEOUT" if ran["expired"] else "UNKNOWN"
        if not ran["expired"] and ran["rc"] in (10,20):
            expected="s SATISFIABLE" if ran["rc"]==10 else "s UNSATISFIABLE"
            if expected not in ran["stdout"].splitlines():
                critical=True;status="INVALID_SAT_CONTRACT"
            elif ran["rc"]==10:
                proof_type="MODEL"
                if certificate.exists():status="INVALID_SAT_WITH_STRUCTURAL_CERT";critical=True
                else:
                    try:
                        found=enc.verify_sat(ran["stdout"],cnf,encoded)
                        route=found["route"];found_cost=found["route_cost"]
                        status="SAT_VERIFIED";strict=True
                    except (ValueError,AssertionError,TypeError) as ex:
                        critical=True;status="INVALID_SAT_TOUR";details=str(ex)[:250]
            else:
                if certificate.exists():
                    proof_type="VERIPB_MATH5"
                    if proof.exists() and proof.stat().st_size:
                        status="INVALID_MIXED_PROOF";critical=True
                    else:
                        sequence=[
                            [sys.executable,ROOT/"research/math5/check_math5.py",cnf,certificate],
                            [sys.executable,ROOT/"research/math5/emit_veripb_eo_multiplicity.py",
                             "--cnf",cnf,"--certificate",certificate,
                             "--output",work/"proof.pbp"],
                            [ROOT/"veripb-tool/bin/veripb","--cnf",cnf,work/"proof.pbp"]
                        ]
                        for i,check in enumerate(sequence):
                            remaining=CAP-(time.perf_counter()-start)
                            if remaining<=0:status="CHECK_BUDGET";break
                            audit=exec_limited(check,remaining)
                            checker_s+=audit["wall_s"]
                            if audit["expired"]:status="MATH5_CHECK_TIMEOUT";break
                            if i==1 and audit["rc"]==2:
                                status="UNSUPPORTED_VERIPB_EXPORT";break
                            expected_word=("UNSAT_MATH5_CERTIFICATE_VERIFIED" if i==0
                                           else "MATH5_VERIPB_EMITTED" if i==1
                                           else "s VERIFIED UNSATISFIABLE")
                            if audit["rc"]!=0 or expected_word not in (
                                    audit["stdout"]+audit["stderr"]):
                                status="INVALID_MATH5_STANDARD_PROOF";critical=True
                                details=(audit["stdout"]+audit["stderr"])[-300:];break
                        else:status="UNSAT_VERIFIED";strict=True
                elif proof.exists() and proof.stat().st_size:
                    proof_type="FRAT" if arm=="CryptoMiniSat" else "DRAT"
                    remaining=CAP-(time.perf_counter()-start)
                    if remaining<=0:status="CHECK_BUDGET"
                    else:
                        command=([ROOT/"build/frat-rs","elab",proof,cnf,"-v"] if
                                 proof_type=="FRAT" else
                                 [ROOT/"build/drat-trim",cnf,proof])
                        check=exec_limited(command,remaining)
                        checker_s+=check["wall_s"]
                        if check["expired"]:status="PROOF_CHECK_TIMEOUT"
                        elif check["rc"]==0 and "VERIFIED" in (
                                check["stdout"]+check["stderr"]):
                            status="UNSAT_VERIFIED";strict=True
                        else:
                            status="INVALID_DRAT_FRAT";critical=True
                            details=(check["stdout"]+check["stderr"])[-300:]
                else:status="UNSAT_UNVERIFIED"
        elif not ran["expired"] and ran["rc"] in (137,-9,-25,-11):
            status="RESOURCE_LIMIT"
        elif not ran["expired"] and ran["rc"] not in (0,153,None):
            status="SOLVER_ERROR";critical=True;details=ran["stderr"][-300:]
        elapsed=time.perf_counter()-start
        if elapsed>CAP:
            strict=False
            if not critical:status="E2E_OVER_CAP"
        if strict:
            expected=taskinfo["expected"]
            if (expected=="SAT" and status!="SAT_VERIFIED") or (
                expected=="UNSAT" and status!="UNSAT_VERIFIED"):
                status="CONTRADICTS_HELD_KARP";strict=False;critical=True
        return dict(name=case["name"],cities=case["n"],era="SYNTHETIC_EUC_2D",
            decision=label,B=taskinfo["B"],optimum=case["opt_held_karp"],
            cnf_sha256=taskinfo["sha256"],arm=arm,rep=rep,
            status=status,proof_kind=proof_type,strict_accepted=strict,
            critical=critical,reason=details,solver_s=round(solver_s,6),
            checker_s=round(checker_s,6),elapsed_s=round(elapsed,6),
            strict_PAR2_s=round(elapsed if strict else 2*CAP,6),
            route=route,route_cost=found_cost)

def shard(index):
    assert 0<=index<SHARDS
    manifest,_=restore()
    case=manifest["cases"][index]
    out=OUT/f"shard-{index}"
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for label in ("BELOW_OPT","AT_OPT"):
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(f"{case['name']}:{label}:{rep}:tsp_sat1").shuffle(arms)
            for arm in arms:
                row=trial(case,label,rep,arm)
                rows.append(row)
                with (out/"trials.jsonl").open("a") as fd:
                    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                print("TSP_SAT1_TRIAL "+json.dumps({
                    "case":case["name"],"B":row["B"],"arm":arm,
                    "rep":rep,"status":row["status"],
                    "strict_par2_s":row["strict_PAR2_s"]},sort_keys=True),flush=True)
    assert len(rows)==2*REPS*len(ARMS)
    print("TSP_SAT1_SHARD "+json.dumps({
        "shard":index,"case":case["name"],"trials":len(rows),
        "optimum":case["opt_held_karp"]},sort_keys=True),flush=True)

def report():
    manifest,proto=restore()
    rows=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}"/"trials.jsonl"
        if not path.exists():raise RuntimeError("MISSING_SHARD "+str(i))
        rows.extend(json.loads(x) for x in path.read_text().splitlines())
    expected={(case["name"],label,rep,arm) for case in manifest["cases"]
              for label in ("BELOW_OPT","AT_OPT")
              for rep in range(REPS) for arm in ARMS}
    observed={(r["name"],r["decision"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(expected)==proto["expected_trials"] and observed==expected
    source={x["name"]:x for x in manifest["cases"]}
    issues=[]
    for r in rows:
        spec=source[r["name"]]["variants"][r["decision"]]
        if r["cnf_sha256"]!=spec["sha256"]:issues.append(("HASH_CHANGED",r["name"]))
        if r["critical"]:issues.append((r["name"],r["arm"],r["status"],r["reason"]))
        if r["strict_accepted"] and r["proof_kind"] not in KINDS:
            issues.append(("UNVERIFIED_CREDIT",r["name"],r["arm"]))
        if r["strict_accepted"] and r["decision"]=="AT_OPT" and r["route_cost"]!=source[r["name"]]["opt_held_karp"]:
            issues.append(("NONOPTIMAL_SAT",r["name"],r["arm"]))
    totals={}
    for arm in ARMS:
        group=[x for x in rows if x["arm"]==arm]
        totals[arm]=dict(trials=len(group),
            strict_verified=sum(x["strict_accepted"] for x in group),
            sat=sum(x["status"]=="SAT_VERIFIED" for x in group),
            unsat=sum(x["status"]=="UNSAT_VERIFIED" for x in group),
            strict_PAR2_s=round(sum(x["strict_PAR2_s"] for x in group),6),
            statuses=dict(collections.Counter(x["status"] for x in group)))
    verdicts={}
    for case in manifest["cases"]:
        verdicts[case["name"]]=dict(
            optimum_held_karp=case["opt_held_karp"],
            proof_pairs={arm:all(
                any(x["strict_accepted"] for x in rows
                    if x["name"]==case["name"] and x["arm"]==arm
                    and x["decision"]==label)
                for label in ("BELOW_OPT","AT_OPT")) for arm in ARMS})
    conclusion=dict(status="FAIL" if issues else "COMPLETE",
        trials=len(rows),instances=len(manifest["cases"]),
        accepted_certificates=totals,per_instance=verdicts,
        failures=issues,protocol=proto,
        no_claim_of_fully_formal_TSP_encoder_correctness=True,
        no_competition_or_blind_claim=True,
        note="SAT/UNSAT standard proof is against generated CNF; independent Held-Karp and complete small-n encoding controls link back to TSP.")
    save(OUT/"final.json",conclusion)
    print("TSP_SAT1_FINAL "+json.dumps(dict(status=conclusion["status"],
        instances=conclusion["instances"],trials=len(rows),
        totals=totals,pairs=verdicts,
        critical_count=len(issues)),sort_keys=True),flush=True)
    if issues:raise SystemExit(1)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("prepare","shard","report"))
    ap.add_argument("--index",type=int)
    args=ap.parse_args()
    if args.action=="prepare":freeze()
    elif args.action=="shard":shard(args.index)
    else:report()

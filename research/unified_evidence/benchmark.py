#!/usr/bin/env python3
"""Original 2026 Main CNF realblind100, strictly source-paired and proof-checked.

No source/solver selection based on outcomes. Result from a solver is never
trusted without independently reading the original CNF or proof checker.
Structural MATH5 proofs have a DIFFERENT score track from DRAT/FRAT.
"""
import argparse,collections,hashlib,json,os,random,resource,signal,statistics,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"prespec.json").read_text())
DATA=ROOT/"unified_realblind100_inputs"
OUT=ROOT/"unified_realblind100_results"
CAP=P["cap_s"]
REPS=P["repetitions"]
ARMS=tuple(P["arms"])
SHARDS=P["shards"]
BIN={"X59_OFF":"build/drnas-sat-native-x59",
     "X59_ON25":"build/drnas-sat-native-x59",
     "X59_ON25_MATH5_100":"build/drnas-x59-xor-math5-unified1",
     "Kissat":"build/kissat","CaDiCaL":"build/cadical",
     "CryptoMiniSat":"build/cms"}
REQUIRED_BIN=tuple(sorted(set(BIN.values())|{"build/drat-trim","build/frat-rs",
            "build/cms-libs/usr/lib/x86_64-linux-gnu/libcryptominisat5.so.5.11"}))
CHECKER=ROOT/"research/math5/check_math5.py"

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def frozen_sources():
    m=json.loads((DATA/"manifest.json").read_text())
    n=m["selected"]
    assert P["min_sources"]<=n<=P["target_sources"] and len(m["sources"])==n,m.get("selected")
    assert m["target"]==P["target_sources"]
    assert m["catalog_sat_controls"]>=P["min_catalog_sat"]
    assert m["catalog_unsat_controls"]>=P["min_catalog_unsat"]
    assert m["prespec_sha256"]==sha(HERE/"prespec.json")
    assert len({s["sha256"] for s in m["sources"]})==n
    assert {s["id"] for s in m["sources"]}==set(range(n))
    for s in m["sources"]:
        assert sha(ROOT/s["path"])==s["sha256"],("SOURCE_CHANGED",s["id"])
    return m
def pinned():
    assert all((ROOT/p).is_file() for p in REQUIRED_BIN)
    return {p:sha(ROOT/p) for p in REQUIRED_BIN}
def affinity():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    return cpu
def prepare():
    affinity()
    m=frozen_sources()
    n=len(m["sources"])
    fingerprints=pinned()
    proto=dict(prespec_sha256=sha(HERE/"prespec.json"),
        source_manifest_sha256=sha(DATA/"manifest.json"),source_count=n,
        target_sources=P["target_sources"],availability_amendment=P["availability_amendment"],
        code_git_sha=os.environ.get("GITHUB_SHA"),binary_sha256=fingerprints,
        arms=ARMS,reps=REPS,cap_s=CAP,shards=SHARDS,
        source_disjoint_from_recorded_history=True,
        does_not_claim_all_history_audited=True,
        original_official_cnf=True,not_xor_selected=True,
        checker_included_in_cap=True,one_core_per_solver=True,
        primary_includes_structural=True,strict_requires_standard_proofs=True,
        no_automatic_promotion=True)
    save(OUT/"protocol.json",proto)
    print("REALBLIND100_READY "+json.dumps(dict(sources=len(m["sources"]),
          expected_trials=n*REPS*len(ARMS),
          protocol_sha256=sha(OUT/"protocol.json")),sort_keys=True),flush=True)
def restore():
    affinity()
    m=frozen_sources()
    proto=json.loads((OUT/"protocol.json").read_text())
    assert proto["source_manifest_sha256"]==sha(DATA/"manifest.json")
    assert proto["prespec_sha256"]==sha(HERE/"prespec.json")
    assert proto["binary_sha256"]==pinned(), "reference changed"
    return m["sources"],proto
def model_ok(path,stdout):
    model={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            try:l=int(token)
            except ValueError:return False
            if l:
                v=abs(l)
                if v in model and model[v]!=(l>0):return False
                model[v]=(l>0)
    if not model:return False
    n=nc=None
    total=0;clause_open=False;satisfied=False
    with Path(path).open(errors="strict") as f:
        for line in f:
            z=line.split()
            if not z or z[0] in ("c","%"):continue
            if z[0]=="p":
                if n is not None or len(z)!=4 or z[1]!="cnf":return False
                try:n,nc=map(int,z[2:])
                except ValueError:return False
                if any(v>n for v in model):return False
                continue
            if n is None:return False
            for tok in z:
                try:l=int(tok)
                except ValueError:return False
                if abs(l)>n:return False
                if l:
                    clause_open=True
                    satisfied=satisfied or model.get(abs(l))==(l>0)
                else:
                    if not satisfied:return False
                    total+=1;clause_open=False;satisfied=False
    return n is not None and not clause_open and total==nc

def command(arm,cnf,proof,cert):
    inp=str(cnf)
    if arm.startswith("X59_"):
        binary=str(ROOT/BIN[arm])
        args=[binary,inp,"--mode","core","--time",str(CAP),
              "--proof",str(proof),"--stats"]
        if arm!="X59_OFF":args+=["--sat-construct-ms","25"]
        if arm=="X59_ON25_MATH5_100":
            args+=["--math5-ms","100","--math5-certificate",str(cert)]
        return args
    if arm=="Kissat":return [str(ROOT/BIN[arm]),inp,str(proof)]
    if arm=="CaDiCaL":return [str(ROOT/BIN[arm]),"-q","--no-binary",inp,str(proof)]
    if arm=="CryptoMiniSat":
        return [str(ROOT/BIN[arm]),"--threads=1","--verb=0","--frat="+str(proof),inp]
    raise ValueError(arm)

def execute(cmd,timeout,allow_file=True):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(P["memory_limit_bytes"],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(P["proof_limit_bytes"],)*2)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    env["LD_LIBRARY_PATH"]=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu")
    t=time.perf_counter()
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=env,text=True,start_new_session=True,preexec_fn=limits)
    expired=False
    try:
        stdout,stderr=proc.communicate(timeout=max(.001,timeout))
    except subprocess.TimeoutExpired:
        expired=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=proc.communicate()
    return dict(returncode=proc.returncode,stdout=stdout,stderr=stderr,
                expired=expired,wall_s=time.perf_counter()-t)

def trial(src,arm,rep):
    cnf=ROOT/src["path"]
    assert sha(cnf)==src["sha256"]
    with tempfile.TemporaryDirectory(prefix="realblind100-") as td:
        root=Path(td)
        proof=root/"proof"
        cert=root/"math5.json"
        started=time.perf_counter()
        solve=execute(command(arm,cnf,proof,cert),CAP)
        solver_s=time.perf_counter()-started
        remaining=CAP-solver_s
        status="TIMEOUT" if solve["expired"] else "UNKNOWN"
        certified=False;kind=None;critical=False;reason=None
        checker_s=0.0;proof_sha=None;proof_bytes=0
        if not solve["expired"] and solve["returncode"] in (10,20):
            declared="s SATISFIABLE" if solve["returncode"]==10 else "s UNSATISFIABLE"
            if declared not in solve["stdout"].splitlines():
                status="INVALID_STATUS";critical=True
            elif remaining<=0:
                status="NO_CHECK_BUDGET"
            elif solve["returncode"]==10:
                kind="MODEL"
                if cert.exists():
                    status="INVALID_STALE_CERT";critical=True
                elif model_ok(cnf,solve["stdout"]):
                    certified=True;status="SAT_VERIFIED"
                else:
                    status="INVALID_SAT_MODEL";critical=True
            else:
                checker=None
                if cert.exists():
                    kind="STRUCTURAL_MATH5"
                    if arm!="X59_ON25_MATH5_100" or (proof.exists() and proof.stat().st_size):
                        status="INVALID_CERT_AND_DRAT";critical=True
                    else:
                        try:
                            assert json.loads(cert.read_text())["format"]=="drnas-math5-eo-xor-unit-v1"
                            checker=[sys.executable,str(CHECKER),str(cnf),str(cert)]
                        except (ValueError,AssertionError,KeyError):
                            status="INVALID_CERT_FORMAT";critical=True
                elif proof.exists() and proof.stat().st_size:
                    kind="FRAT" if arm=="CryptoMiniSat" else "DRAT"
                    if kind=="FRAT":
                        checker=[str(ROOT/"build/frat-rs"),"elab",str(proof),str(cnf),"-v"]
                    else:
                        checker=[str(ROOT/"build/drat-trim"),str(cnf),str(proof)]
                else:status="UNSAT_UNVERIFIED"
                if checker is not None:
                    remain=CAP-(time.perf_counter()-started)
                    if remain>0:
                        chk=execute(checker,remain)
                        checker_s=chk["wall_s"]
                        certified=(not chk["expired"] and chk["returncode"]==0
                                   and "VERIFIED" in chk["stdout"])
                        status="UNSAT_VERIFIED" if certified else (
                            "CHECK_TIMEOUT" if chk["expired"] else "INVALID_PROOF")
                        if not certified and not chk["expired"]:critical=True
                        if certified:
                            if kind=="STRUCTURAL_MATH5":
                                proof_sha=sha(cert);proof_bytes=cert.stat().st_size
                            else:
                                proof_sha=sha(proof);proof_bytes=proof.stat().st_size
                    else:status="NO_CHECK_BUDGET"
        elif not solve["expired"] and solve["returncode"] not in (0,153):
            status="RESOURCE_LIMIT" if solve["returncode"] in (137,-9,-25) else "SOLVER_ERROR"
            critical=status=="SOLVER_ERROR"
            reason=solve["stderr"][-550:]
        elapsed=time.perf_counter()-started
        accepted=certified and elapsed<=CAP
        strict=accepted and kind in ("MODEL","DRAT","FRAT")
        stats={}
        for line in solve["stderr"].splitlines():
            for prefix in ("SAT_CONSTRUCT_STATS ","MATH5_UNIFIED_STATS "):
                if line.startswith(prefix):
                    try:stats[prefix.strip()]=json.loads(line[len(prefix):])
                    except ValueError:critical=True
        if certified and ((solve["returncode"]==10 and src["catalog_label"]=="unsat")
                          or (solve["returncode"]==20 and src["catalog_label"]=="sat")):
            reason="CERTIFIED_RESULT_DIFFERS_FROM_UNVERIFIED_CATALOG_LABEL"
        return dict(id=src["id"],file_id=src["file_id"],source_sha256=src["sha256"],
            family=src["family"],catalog_label=src["catalog_label"],
            arm=arm,rep=rep,rc=solve["returncode"],status=status,
            accepted=accepted,strict_accepted=strict,certificate_kind=kind,
            critical=critical,reason=reason,
            solver_s=round(solver_s,6),checker_s=round(checker_s,6),
            e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6),
            PAR2_strict_s=round(elapsed if strict else 2*CAP,6),
            proof_sha256=proof_sha,proof_bytes=proof_bytes,stats=stats)

def shard(idx):
    assert 0<=idx<SHARDS
    sources,proto=restore()
    selected=[s for s in sources if s["id"]%SHARDS==idx]
    assert selected,("EMPTY_SHARD",idx)
    dest=OUT/f"shard-{idx}"
    dest.mkdir(parents=True,exist_ok=False)
    with (dest/"trials.jsonl").open("w") as f:
        for src in selected:
            for rep in range(REPS):
                arms=list(ARMS);rng=random.Random(P["selection_seed"]+str(src["id"])+":"+str(rep));rng.shuffle(arms)
                for arm in arms:
                    row=trial(src,arm,rep)
                    f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
    records=[json.loads(l) for l in (dest/"trials.jsonl").read_text().splitlines()]
    assert len(records)==len(selected)*REPS*len(ARMS)
    sums={a:dict(solved=sum(r["accepted"] for r in records if r["arm"]==a),
        par2_s=round(sum(r["PAR2_s"] for r in records if r["arm"]==a),6))
        for a in ARMS}
    print("REALBLIND100_SHARD "+json.dumps(dict(shard=idx,source_count=len(selected),
        trials=len(records),summary=sums),sort_keys=True),flush=True)

def report():
    sources=frozen_sources()["sources"]
    n=len(sources)
    rows=[]
    for idx in range(SHARDS):
        path=OUT/f"shard-{idx}"/"trials.jsonl"
        assert path.is_file(),("MISSING_SHARD",idx)
        rows += [json.loads(x) for x in path.read_text().splitlines()]
    expected={(i,rep,a) for i in range(n) for rep in range(REPS) for a in ARMS}
    assert len(rows)==len(expected)==n*REPS*len(ARMS)
    assert {(r["id"],r["rep"],r["arm"]) for r in rows}==expected
    by_id={s["id"]:s for s in sources}
    assert all(r["source_sha256"]==by_id[r["id"]]["sha256"] for r in rows)
    problems=[r for r in rows if r["critical"]]
    for source in sources:
        statuses={r["status"].split("_")[0] for r in rows if r["id"]==source["id"] and r["accepted"]}
        if "SAT" in statuses and "UNSAT" in statuses:
            problems.append(dict(id=source["id"],reason="CONTRADICTORY_CERTIFIED_ANSWERS"))
    totals={}
    for a in ARMS:
        rr=[r for r in rows if r["arm"]==a]
        totals[a]=dict(attempts=len(rr),accepted=sum(r["accepted"] for r in rr),
            strict_accepted=sum(r["strict_accepted"] for r in rr),
            verified_sources=len({r["id"] for r in rr if r["accepted"]}),
            solved_sat=sum(r["status"]=="SAT_VERIFIED" for r in rr),
            solved_unsat=sum(r["status"]=="UNSAT_VERIFIED" for r in rr),
            structural=sum(r["accepted"] and r["certificate_kind"]=="STRUCTURAL_MATH5" for r in rr),
            PAR2_s=round(sum(r["PAR2_s"] for r in rr),6),
            PAR2_strict_s=round(sum(r["PAR2_strict_s"] for r in rr),6),
            statuses=dict(collections.Counter(r["status"] for r in rr)))
    per_source={i:{a:statistics.mean(r["PAR2_s"] for r in rows
        if r["id"]==i and r["arm"]==a) for a in ARMS} for i in range(n)}
    best_reference=min(("Kissat","CaDiCaL","CryptoMiniSat"),key=lambda a:totals[a]["PAR2_s"])
    deltas={a:[per_source[i][best_reference]-per_source[i][a] for i in range(n)]
            for a in ("X59_OFF","X59_ON25","X59_ON25_MATH5_100")}
    rng=random.Random(20261115)
    boots={}
    for a,changes in deltas.items():
        samples=sorted(sum(changes[rng.randrange(n)] for _ in range(n)) for _ in range(2000))
        boots[a]=dict(reference=best_reference,aggregate_saving_s=round(sum(changes),6),
            bootstrap95_s=[samples[50],samples[1950]],
            wins=sum(v>0.0001 for v in changes),
            losses=sum(v<-0.0001 for v in changes),
            ties=sum(abs(v)<=0.0001 for v in changes))
    final=dict(status="CRITICAL" if problems else "COMPLETE",source_count=n,
        target_sources=P["target_sources"],availability_amendment=P["availability_amendment"],
        attempts=len(rows),catalog_labels=dict(collections.Counter(s["catalog_label"] for s in sources)),
        real_origins=True,no_xor_source_filter=True,
        independent_certificates_required=True,
        original_source_sha256=sha(DATA/"manifest.json"),
        best_reference=best_reference,totals=totals,paired=boots,critical=problems)
    save(OUT/"final.json",final)
    print("REALBLIND100_FINAL "+json.dumps(dict(status=final["status"],
        sources=n,trials=len(rows),best_reference=best_reference,
        totals=totals,paired=boots,critical_count=len(problems)),sort_keys=True),flush=True)
    if problems:raise SystemExit("Critical invalid answers/proofs: review frozen audit")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","shard","report"))
    parser.add_argument("--index",type=int)
    args=parser.parse_args()
    if args.action=="prepare":prepare()
    elif args.action=="shard":shard(args.index)
    else:report()

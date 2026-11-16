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
OUT=ROOT/"unified_evidence_results"
CAP=P["cap_s"]
REPS=P["repetitions"]
ARMS=("X59_OFF","X59_MATH5","CXX_BASE","CXX_BDD3","CXX_UNION","CORE1_FROZEN","Kissat","CaDiCaL","CryptoMiniSat")
SHARDS=P["shards"]
BIN={
  "X59_OFF":"build/drnas-sat-native-x59",
  "X59_MATH5":"build/drnas-x59-xor-math5-unified1",
  "CXX_BASE":"build/drnas-pcmax-base",
  "CXX_BDD3":"build/drnas-pcmax-mg7-ipg1-bdd3",
  "CXX_UNION":"build/drnas-pcmax-mg7-ipg1-bdd3",
  "CORE1_FROZEN":"build/drnas-unified-core1",
  "Kissat":"build/kissat","CaDiCaL":"build/cadical",
  "CryptoMiniSat":"build/cms"}
REQUIRED_BIN=tuple(sorted(set(BIN.values())|{
 "build/drat-trim","build/frat-rs",
 "build/cms-libs/usr/lib/x86_64-linux-gnu/libcryptominisat5.so.5.11",
 "veripb-tool/bin/veripb"}))
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
        source_disjoint_from_recorded_history=False,
        does_not_claim_all_history_audited=True,
        original_official_cnf=True,not_xor_selected=True,
        checker_included_in_cap=True,one_core_per_solver=True,
        primary_includes_structural=True,strict_requires_standard_proofs=True,
        no_automatic_promotion=True)
    save(OUT/"protocol.json",proto)
    print("GRAND_UNIFIED_READY "+json.dumps(dict(sources=len(m["sources"]),
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

def command(arm,cnf,proof,cert,work,remaining):
    inp=str(cnf)
    if arm in ("X59_OFF","X59_MATH5"):
        argv=[str(ROOT/BIN[arm]),inp,"--mode","core","--time",str(max(.001,remaining)),
              "--proof",str(proof),"--stats"]
        if arm=="X59_MATH5":
            argv+=["--sat-construct-ms","25","--math5-ms","100",
                   "--math5-certificate",str(cert)]
        return argv
    if arm.startswith("CXX_"):
        argv=[str(ROOT/BIN[arm]),inp,"--mode","core","--time",
              str(max(.001,remaining)),"--stats","--proof",str(proof)]
        if arm!="CXX_BASE":
            argv+=["--pcmax-capacity","--pcmax-budget-ms","100",
                   "--pcmax-certificate",str(work/"capacity.json"),
                   "--ipg1","--ipg1-budget-ms","90",
                   "--ipg1-certificate",str(work/"ipg1.json"),
                   "--ipg-bdd2","--ipg-bdd2-budget-ms","80",
                   "--ipg-bdd2-graph",str(work/"bdd2_graph.json"),
                   "--ipg-bdd2-certificate",str(work/"bdd2.json"),
                   "--ipg-bdd3","--ipg-bdd3-budget-ms","140",
                   "--ipg-bdd3-graph",str(work/"bdd3_graph.json"),
                   "--ipg-bdd3-certificate",str(work/"bdd3.json"),
                   "--residual-scc"]
        return argv
    if arm=="CORE1_FROZEN":
        return [str(ROOT/BIN[arm]),inp,"--time",str(max(.001,remaining)),
                "--proof",str(proof),"--certificate",str(cert)]
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
    started=time.perf_counter()
    cnf=ROOT/src["path"]
    assert sha(cnf)==src["sha256"], "ORIGINAL_SOURCE_CHANGED"
    with tempfile.TemporaryDirectory(prefix="grand-union-") as td:
        folder=Path(td)
        proof=folder/"proof";cert=folder/"math5.json"
        pre=folder/"preproof.json"
        status="UNKNOWN"; certified=False;strict=False; kind=None
        critical=False;reason=None;checker_s=0;solver_s=0
        proof_sha=None;proof_bytes=0
        observed_rc=None
        if arm=="CXX_UNION":
            if cnf.stat().st_size<=256000:
                pre_cap=min(1.3 if cnf.stat().st_size<=24000 else .35,CAP*.20)
                pre_run=execute([sys.executable,str(ROOT/"research/unified_evidence/precheck.py"),
                                 str(cnf),str(pre)],pre_cap)
                solver_s+=pre_run["wall_s"]
                if pre_run["returncode"]==20 and pre.is_file():
                    kind="STRUCTURAL_UNION"
                    check_remain=CAP-(time.perf_counter()-started)
                    if check_remain>0:
                        ck=execute([sys.executable,str(ROOT/"research/unified_evidence/check_preproof.py"),
                                    str(cnf),str(pre)],check_remain)
                        checker_s+=ck["wall_s"]
                        certified=not ck["expired"] and ck["returncode"]==0 and "UNION_PRECHECK_VERIFIED " in ck["stdout"]
                        status="UNSAT_VERIFIED" if certified else ("CHECK_TIMEOUT" if ck["expired"] else "INVALID_UNION_PROOF")
                        critical=not certified and not ck["expired"]
                        if certified:proof_sha=sha(pre);proof_bytes=pre.stat().st_size
                    else:status="NO_CHECK_BUDGET"
                elif pre_run["returncode"] not in (0,20) and not pre_run["expired"]:
                    status="INVALID_PRECHECK_ERROR";critical=True;reason=pre_run["stderr"][-250:]
                elif pre_run["returncode"]==20:
                    status="INVALID_MISSING_PRECHECK_PROOF";critical=True
                # Budget-limited proof scout may be killed. Safe native fallback.
        if kind=="STRUCTURAL_UNION" or critical:
            elapsed=time.perf_counter()-started
            accepted=certified and elapsed<=CAP
            return dict(id=src["id"],file_id=src["file_id"],source_sha256=src["sha256"],
              family=src["family"],catalog_label=src["catalog_label"],
              arm=arm,rep=rep,rc=observed_rc,status=status,accepted=accepted,
              strict_accepted=False,certificate_kind=kind,critical=critical,
              reason=reason,solver_s=round(solver_s,6),checker_s=round(checker_s,6),
              e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6),
              PAR2_strict_s=round(2*CAP,6),proof_sha256=proof_sha,proof_bytes=proof_bytes,stats={})
        solve_remain=CAP-(time.perf_counter()-started)
        if solve_remain<=0:
            status="NO_SOLVE_BUDGET"; solve={"returncode":None,"stdout":"","stderr":"",
                                         "expired":True,"wall_s":0}
        else:
            solve=execute(command(arm,cnf,proof,cert,folder,solve_remain),solve_remain)
            observed_rc=solve["returncode"];solver_s+=solve["wall_s"]
            status="TIMEOUT" if solve["expired"] else "UNKNOWN"
        if not solve["expired"] and solve["returncode"] in (10,20):
            lines=solve["stdout"].splitlines()
            declared="s SATISFIABLE" if solve["returncode"]==10 else "s UNSATISFIABLE"
            left=CAP-(time.perf_counter()-started)
            if declared not in lines:
                status="INVALID_STATUS";critical=True
            elif left<=0:
                status="NO_CHECK_BUDGET"
            elif solve["returncode"]==10:
                kind="MODEL"
                # Deliberate no reliance on known labels or source filenames.
                if model_ok(cnf,solve["stdout"]):
                    certified=True;strict=True;status="SAT_VERIFIED"
                else:
                    status="INVALID_SAT_MODEL";critical=True
            else:
                checker=None;verdict=None
                if arm in ("CXX_BDD3","CXX_UNION"):
                    kinds=[line.rsplit(" ",1)[-1] for line in lines
                           if line.startswith("c PCMAX_UNIFIED_PROOF_KIND ")]
                    if len(kinds)!=1:
                        status="INVALID_MISSING_PROOF_KIND";critical=True
                    else:
                        label=kinds[0]
                        if label=="CAPACITY_JSON_NEEDS_VERIPB":
                            path=folder/"capacity.json";kind="VERIPB_CAPACITY"
                            if not path.exists() or (proof.exists() and proof.stat().st_size):
                                status="INVALID_CAPACITY_FILES";critical=True
                            else:
                                pb=folder/"capacity.pbp"
                                checker=[sys.executable,str(ROOT/"research/pcmax_capacity/emit_veripb_capacity_weighted2.py"),
                                         "--cnf",str(cnf),"--certificate",str(path),"--output",str(pb)]
                                verdict=("VERIPB_PREP",pb)
                        elif label=="IPG1_JSON_NEEDS_EXHAUSTIVE_CHECKER":
                            path=folder/"ipg1.json";kind="STRUCTURAL_IPG1"
                            checker=[sys.executable,str(ROOT/"research/ipg1_check.py"),str(cnf),str(path)]
                            verdict="IPG1_SOURCE_VERIFIED "
                        elif label in ("IPG_BDD2_JSON_NEEDS_INDEPENDENT_CHECKER",
                                       "IPG_BDD3_JSON_NEEDS_INDEPENDENT_CHECKER"):
                            bdd3=label.startswith("IPG_BDD3")
                            kind="STRUCTURAL_BDD3" if bdd3 else "STRUCTURAL_BDD2"
                            checker=[sys.executable,str(ROOT/("research/ipg_bdd3_checker.py" if bdd3
                                                           else "research/ipg_bdd_checker.py")),
                                     "--cnf",str(cnf),
                                     "--graph",str(folder/("bdd3_graph.json" if bdd3 else "bdd2_graph.json")),
                                     "--certificate",str(folder/("bdd3.json" if bdd3 else "bdd2.json"))]
                            verdict="IPG_BDD3_ACCEPT " if bdd3 else "IPG_BDD_ACCEPT "
                        elif label=="DRAT_PROOF":
                            kind="DRAT"
                        else:
                            status="INVALID_UNKNOWN_PROOF_KIND";critical=True
                elif arm=="CORE1_FROZEN" and cert.exists():
                    kind="STRUCTURAL_CORE1"
                    checker=[sys.executable,str(ROOT/"research/unified_core1/check.py"),
                             str(cnf),str(cert)]
                    verdict="VERIFIED"
                    if proof.exists() and proof.stat().st_size:
                        status="INVALID_MIXED_CORE1_DRAT";critical=True
                elif arm=="X59_MATH5" and cert.exists():
                    kind="STRUCTURAL_MATH5"
                    checker=[sys.executable,str(CHECKER),str(cnf),str(cert)]
                    verdict="VERIFIED"
                    if proof.exists() and proof.stat().st_size:
                        status="INVALID_MIXED_MATH5_DRAT";critical=True
                if checker is None and not critical:
                    if proof.exists() and proof.stat().st_size:
                        kind="FRAT" if arm=="CryptoMiniSat" else "DRAT"
                        checker=([str(ROOT/"build/frat-rs"),"elab",str(proof),str(cnf),"-v"]
                                 if kind=="FRAT" else
                                 [str(ROOT/"build/drat-trim"),str(cnf),str(proof)])
                        verdict="VERIFIED"
                    else:
                        status="UNSAT_UNVERIFIED"
                if checker is not None and not critical:
                    remaining=CAP-(time.perf_counter()-started)
                    if remaining<=0:status="NO_CHECK_BUDGET"
                    else:
                        ck=execute(checker,remaining)
                        checker_s+=ck["wall_s"]
                        if isinstance(verdict,tuple) and verdict[0]=="VERIPB_PREP":
                            pb=verdict[1]
                            if ck["expired"]:
                                status="CHECK_TIMEOUT"
                            elif ck["returncode"]!=0 or not pb.exists():
                                status="INVALID_CAPACITY_EMISSION";critical=True
                            else:
                                remaining=CAP-(time.perf_counter()-started)
                                if remaining<=0:status="NO_CHECK_BUDGET"
                                else:
                                    pbcheck=execute([str(ROOT/"veripb-tool/bin/veripb"),
                                                     "--cnf",str(cnf),str(pb)],remaining)
                                    checker_s+=pbcheck["wall_s"]
                                    certified=(not pbcheck["expired"] and pbcheck["returncode"]==0 and
                                               "s VERIFIED UNSATISFIABLE" in pbcheck["stdout"]+pbcheck["stderr"])
                                    status="UNSAT_VERIFIED" if certified else ("CHECK_TIMEOUT" if pbcheck["expired"] else "INVALID_VERIPB")
                                    critical=not certified and not pbcheck["expired"]
                                    if certified:proof_sha=sha(pb);proof_bytes=pb.stat().st_size
                        else:
                            certified=(not ck["expired"] and ck["returncode"]==0 and
                                       verdict in ck["stdout"]+ck["stderr"])
                            status="UNSAT_VERIFIED" if certified else (
                                "CHECK_TIMEOUT" if ck["expired"] else "INVALID_PROOF")
                            critical=not certified and not ck["expired"]
                            if certified:
                                cp=cert if kind in ("STRUCTURAL_MATH5","STRUCTURAL_CORE1") else (
                                  folder/"ipg1.json" if kind=="STRUCTURAL_IPG1" else
                                  folder/"bdd3.json" if kind=="STRUCTURAL_BDD3" else
                                  folder/"bdd2.json" if kind=="STRUCTURAL_BDD2" else proof)
                                proof_sha=sha(cp);proof_bytes=cp.stat().st_size
                strict=certified and kind in ("MODEL","DRAT","FRAT","VERIPB_CAPACITY")
        elif not solve["expired"] and solve["returncode"] not in (0,153,None):
            status="RESOURCE_LIMIT" if solve["returncode"] in (137,-9,-25) else "SOLVER_ERROR"
            critical=status=="SOLVER_ERROR"
            reason=solve["stderr"][-300:]
        elapsed=time.perf_counter()-started
        accepted=certified and elapsed<=CAP
        strict=bool(accepted and strict)
        return dict(id=src["id"],file_id=src["file_id"],source_sha256=src["sha256"],
            family=src["family"],catalog_label=src["catalog_label"],
            arm=arm,rep=rep,rc=solve["returncode"],status=status,
            accepted=accepted,strict_accepted=strict,certificate_kind=kind,
            critical=critical,reason=reason,
            solver_s=round(solver_s,6),checker_s=round(checker_s,6),
            e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6),
            PAR2_strict_s=round(elapsed if strict else 2*CAP,6),
            proof_sha256=proof_sha,proof_bytes=proof_bytes,stats={})

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
    print("GRAND_UNIFIED_SHARD "+json.dumps(dict(shard=idx,source_count=len(selected),
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
            for a in ("CXX_BDD3","CXX_UNION","CORE1_FROZEN","X59_MATH5")}
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
    # Cluster bootstrap by CNF source family (not repeated trials).
    byfamily={}
    for source in sources:
        byfamily.setdefault(source["family"],[]).append(source["id"])
    family_bootstrap={}
    for candidate in ("CXX_BDD3","CXX_UNION","CORE1_FROZEN","X59_MATH5"):
        family_deltas=[sum(per_source[i][best_reference]-per_source[i][candidate]
                           for i in ids) for ids in byfamily.values()]
        if len(family_deltas)>=2:
            rng2=random.Random(220116)
            samples=sorted(sum(family_deltas[rng2.randrange(len(family_deltas))]
                               for _ in range(len(family_deltas))) for _ in range(2000))
            ci=[round(samples[49],6),round(samples[1950],6)]
        else:ci=None
        family_bootstrap[candidate]={"families":len(family_deltas),
                                    "aggregate_delta_s":round(sum(family_deltas),6),
                                    "bootstrap95_s":ci}
    final["family_bootstrap"]=family_bootstrap
    final["evaluation_status"]="RETROSPECTIVE_POSTHOC_REPLAY_NOT_BLIND"
    final["candidate_native_single_process"]=True
    final["union_pipeline_is_sequential_python_then_native"]=True
    final["standard_only"]=True
    save(OUT/"final.json",final)
    print("GRAND_UNIFIED_FINAL "+json.dumps(dict(status=final["status"],
        sources=n,trials=len(rows),best_reference=best_reference,
        totals=totals,paired=boots,family_bootstrap=family_bootstrap,critical_count=len(problems)),sort_keys=True),flush=True)
    if problems:raise SystemExit("Critical invalid answers/proofs: review frozen audit")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","shard","report"))
    parser.add_argument("--index",type=int)
    args=parser.parse_args()
    if args.action=="prepare":prepare()
    elif args.action=="shard":shard(args.index)
    else:report()

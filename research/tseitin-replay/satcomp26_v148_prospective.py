#!/usr/bin/env python3
"""Prospectively frozen, UNOFFICIAL SAT Competition 2026 mini head-to-head.
Six new official Main Track CNFs: no DRNAS outcome-based selection; same CPU,
3GiB, 12s cap, 2 repeats. Official 2026 winner, Kissat, CryptoMiniSat, V14.7.
All conclusions are restricted to these selected inputs and short time limit.
"""
import argparse,csv,hashlib,json,os,random,resource,signal,statistics,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,"research/drnas-sat-v7-8")
sys.path.insert(0,"research/tseitin-replay")
from official_shortlong_select import download_and_features
from xor4_benchmark import dimacs
from v147_subset_bench import verify_model,verify_affine_unsat
REV="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
CSV_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
CHAMP_BLOB="5ec9be607fbf762329176beb7068d574cd528b5b"
PROTOCOL="drnas-v148-2026-prospective-fixed-20261101"
SALT="drnas-v148-satcomp26-prospective-prebenchmark-salt-20261101"
MODES=("DRNAS_V14_7","SATComp26_Official_Winner","Kissat_4_0_4","CryptoMiniSat")
QUOTAS={"SAT_fast":2,"UNSAT_fast":2,"SAT_mid":1,"UNSAT_mid":1}
CAP=12.0
REPS=2

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def fetch_csv():
    url="https://raw.githubusercontent.com/satcompetition/2026/"+REV+"/downloads/scores.csv"
    content=urllib.request.urlopen(url,timeout=90).read()
    gitblob=hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()
    assert gitblob==CSV_BLOB,(gitblob,CSV_BLOB)
    return list(csv.DictReader(content.decode().splitlines()))
def freeze(out,known_path):
    known=set()
    if Path(known_path).exists():
        m=json.loads(Path(known_path).read_text())
        for key in ("known_diagnostic","new_prospective"):
            for c in m.get(key,[]):known.add(c["id"])
    rows=fetch_csv()
    baseline=[r for r in rows if r.get("solverid")=="biere_cadical3[main]"]
    assert len(baseline)==400,len(baseline)
    buckets={key:[] for key in QUOTAS}
    for r in baseline:
        if r["status"] not in ("sat-verified","unsat-verified"):continue
        ident=r["instanceid"]
        if ident in known:continue
        seconds=float(r["runtime"])
        band="fast" if 0<=seconds<5 else "mid" if 5<=seconds<30 else None
        if not band:continue
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        key=label+"_"+band
        buckets[key].append(dict(id=ident,label=label,stratum=key,official_cadical_seconds=seconds))
    selected=[];attempts=[]
    for key,quota in QUOTAS.items():
        order=sorted(buckets[key],key=lambda c:hashlib.sha256((SALT+"/"+key+"/"+c["id"]).encode()).hexdigest())
        for case in order:
            try:info=download_and_features(case["id"])
            except Exception as ex:
                attempts.append(dict(id=case["id"],stratum=key,skip=str(ex)[:130]))
                continue
            if info["cnf_bytes"]>24*1024**2:
                attempts.append(dict(id=case["id"],stratum=key,skip="predeclared 24MiB uncompressed cap"))
                continue
            selected.append({**case,**info})
            attempts.append(dict(id=case["id"],stratum=key,accept=True))
            print("V148_FROZEN",key,case["id"],info["sha256"],info["cnf_bytes"],flush=True)
            if sum(x["stratum"]==key for x in selected)==quota:break
        assert sum(x["stratum"]==key for x in selected)==quota,("stratum missing",key)
    assert len(selected)==6 and len(set(x["id"] for x in selected))==6
    assert not known.intersection(x["id"] for x in selected)
    selected.sort(key=lambda c:hashlib.sha256((SALT+"/run/"+c["id"]).encode()).hexdigest())
    save(out,dict(protocol=PROTOCOL,score_file_blob=CSV_BLOB,score_ref=REV,
                  exclusion_prior_v96_cases=len(known),selection="stratified by only upstream CaDiCaL official outcomes; deterministic SHA ordering; hard 24MiB cap; no DRNAS/other solver timings consulted",
                  cases=selected,excluded_or_attempted=attempts,solvers=MODES,repeats=REPS,
                  cap_seconds=CAP,memory_gib=3,cpu_cores=1,
                  caveats=["Not an official SAT Competition 2026 result/ranking",
                           "2026 CNFs are public; candidates excluded if in earlier V9.6 manifest but not guaranteed unseen elsewhere",
                           "Six compressed-downloadable, size-bounded, CaDiCaL-solved formulas; not representative of all 400 official instances",
                           "12 sec cutoff instead of official 5000 sec; GitHub Actions shared CPUs vs official hardware",
                           "UNSAT outputs matching official label are not independently DRAT/LRAT certified unless subset parity proof validates",
                           "Winner package pinned by Git blob; cannot make whole-track/world record claim"]))
    print("V148_FREEZE_PASS",len(selected),"known_excluded",len(known),flush=True)

def limits():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def invoke(mode,cnf,proof_dir):
    if mode=="DRNAS_V14_7":
        cmd=[str(Path("bin/v147_subset_xor4").resolve()),str(cnf.resolve()),str(Path("bin/kissat_solver").resolve()),"0"]
    elif mode=="Kissat_4_0_4":
        cmd=[str(Path("bin/kissat_solver").resolve()),str(cnf.resolve())]
    elif mode=="CryptoMiniSat":
        cmd=["cryptominisat5","--threads=1",str(cnf.resolve())]
    else:
        champ=Path(os.environ["SATCOMP26_SOLVER_DIR"]).resolve()
        cmd=[str(champ/"run.sh"),str(cnf.resolve()),str(proof_dir.resolve())]
        proof_dir.mkdir(parents=True,exist_ok=False)
    st=time.perf_counter()
    proc=subprocess.Popen(cmd,cwd=str(champ) if mode=="SATComp26_Official_Winner" else None,
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors="replace",
             start_new_session=True,preexec_fn=limits)
    try:stdout,stderr=proc.communicate(timeout=CAP)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL)
        proc.communicate()
        return dict(status="TIMEOUT",seconds=CAP,verified="timeout",route="timeout",returncode=124)
    seconds=time.perf_counter()-st
    if seconds>CAP:return dict(status="TIMEOUT",seconds=CAP,verified="timeout",route="timeout",returncode=124)
    route="native"
    tags=[line.split("\t",1)[1] for line in stdout.splitlines() if line.startswith("DRNAS_HYBRID_RESULT\t")]
    if tags:
        assert mode=="DRNAS_V14_7" and proc.returncode==0 and len(tags)==1
        answer=json.loads(tags[0]);status=answer["status"];route=answer["path"]
        model=answer.get("model",[])
    else:
        answers=[line.strip() for line in stdout.splitlines() if line.strip() in ("s SATISFIABLE","s UNSATISFIABLE")]
        assert len(answers)==1,(mode,proc.returncode,stdout[-250:],stderr[-250:])
        status="SAT" if answers[0]=="s SATISFIABLE" else "UNSAT"
        assert proc.returncode in (0,10,20) and (proc.returncode in (0,10) if status=="SAT" else proc.returncode in (0,20))
        model=[int(v) for line in stdout.splitlines() if line.startswith("v ") for v in line.split()[1:] if int(v)]
        if mode=="DRNAS_V14_7":route="kissat_fallback"
    return dict(status=status,seconds=round(seconds,7),route=route,model=model,
                proof_present=bool((proof_dir/"proof.out").is_file()) if mode=="SATComp26_Official_Winner" else False,
                answer=answer if tags else None,returncode=proc.returncode)

def measure(manifest_path,slot,out):
    m=json.loads(Path(manifest_path).read_text())
    assert m["protocol"]==PROTOCOL and m["solvers"]==list(MODES) and len(m["cases"])==6
    assert 0<=slot<3
    cases=m["cases"][slot*2:slot*2+2]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    parent_cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{parent_cpu})
    cpu_model=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines() if x.startswith("model name")),"unknown")
    meta=dict(slot=slot,case_ids=[x["id"] for x in cases],cpu=cpu_model,core=parent_cpu,manifest_sha256=digest(manifest_path),
              drnas_sha256=digest("bin/v147_subset_xor4"),kissat_sha256=digest("bin/kissat_solver"),
              winner_archive_git_blob=os.environ["SATCOMP26_ARCHIVE_GIT_BLOB_SHA"])
    save(out/"meta.json",meta)
    rows=[]
    for case in cases:
        cnf=out/(case["id"]+".cnf")
        observed=download_and_features(case["id"],cnf)
        assert observed["sha256"]==case["sha256"] and observed["features"]==case["features"],case["id"]
        print("V148_INPUT_SHA_VERIFIED",case["id"],case["sha256"],flush=True)
        n,clauses=dimacs(cnf)
        for rep in range(REPS):
            modes=list(MODES)
            seed=int(hashlib.sha256((SALT+case["id"]+str(rep)).encode()).hexdigest()[:8],16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                proof_dir=out/"winner_proofs"/(case["id"]+"-rep"+str(rep))
                try:
                    res=invoke(mode,cnf,proof_dir)
                    status=res["status"];verified="not_independently_proved"
                    if status=="SAT":
                        verify_model(n,clauses,res["model"])
                        verified="full_CNF_model"
                    elif status=="UNSAT" and res["route"]=="affine_subset_xor4":
                        verify_affine_unsat(clauses,res["answer"])
                        verified="independently_replayed_affine_proof"
                    if status not in ("SAT","UNSAT","TIMEOUT"):raise ValueError("invalid status")
                    if status not in (case["label"],"TIMEOUT"):
                        raise ValueError("disagrees with official verified label")
                    item=dict(case=case["id"],label=case["label"],stratum=case["stratum"],
                              solver=mode,rep=rep,seconds=res["seconds"],status=status,
                              verified=verified,route=res["route"],proof_file_present=res.get("proof_present",False))
                except Exception as ex:
                    item=dict(case=case["id"],label=case["label"],stratum=case["stratum"],
                              solver=mode,rep=rep,seconds=CAP,status="ERROR",verified="rejected",
                              route="exception",error=str(ex)[:250])
                rows.append(item)
                save(out/"rows.json",rows)
                print("V148_TRIAL",json.dumps(item,sort_keys=True),flush=True)
        cnf.unlink()
    assert len(rows)==2*REPS*len(MODES)
    print("V148_SHARD_PASS",slot,len(rows),flush=True)

def audit(manifest_path,combined,out):
    m=json.loads(Path(manifest_path).read_text())
    assert m["protocol"]==PROTOCOL and len(m["cases"])==6
    root=Path(combined)
    rows=[];machines=[]
    for slot in range(3):
        folder=root/("v148-shard-"+str(slot))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["slot"]==slot and meta["manifest_sha256"]==digest(manifest_path)
        assert meta["case_ids"]==[c["id"] for c in m["cases"][slot*2:slot*2+2]]
        machines.append(meta)
        got=json.loads((folder/"rows.json").read_text())
        assert len(got)==2*REPS*len(MODES)
        rows.extend(got)
    cases={c["id"]:c for c in m["cases"]}
    keys=set()
    for r in rows:
        assert r["case"] in cases and r["label"]==cases[r["case"]]["label"]
        assert r["solver"] in MODES and r["rep"] in range(REPS)
        key=(r["case"],r["solver"],r["rep"])
        assert key not in keys;keys.add(key)
        assert r["status"] in ("SAT","UNSAT","TIMEOUT","ERROR")
        assert r["status"] not in ("SAT","UNSAT") or r["status"]==r["label"]
    assert len(keys)==6*len(MODES)*REPS
    results=[]
    for solver in MODES:
        rr=[r for r in rows if r["solver"]==solver]
        solved=[r for r in rr if r["status"] in ("SAT","UNSAT")]
        par2=[r["seconds"] if r["status"] in ("SAT","UNSAT") else CAP*2 for r in rr]
        results.append(dict(solver=solver,solved=len(solved),attempts=len(rr),
                            independently_verified=sum(r["verified"] in ("full_CNF_model","independently_replayed_affine_proof") for r in rr),
                            par2_seconds=round(statistics.mean(par2),6),
                            total_penalty_seconds=round(sum(par2),6),
                            median_solved_seconds=round(statistics.median(r["seconds"] for r in solved),6) if solved else None,
                            errors=sum(r["status"]=="ERROR" for r in rr),
                            timeouts=sum(r["status"]=="TIMEOUT" for r in rr)))
    results.sort(key=lambda x:(x["par2_seconds"],-x["solved"]))
    report=dict(protocol=PROTOCOL,unofficial=True,manifest=m,hardware=machines,results=results,trials=rows)
    save(out,report)
    print("V148_FINAL_AUDIT_PASS",len(rows),"official_cases",len(cases),flush=True)
    for row in results:print("V148_RESULT",json.dumps(row,sort_keys=True),flush=True)
    with Path("v148-results.md").open("w") as f:
        f.write("# Unofficial SAT Competition 2026 prospective mini simulation\n\n")
        f.write("Six size-bounded official 2026 CNFs, two repeats, 12 seconds, 3 GiB, one core, GitHub Actions CPUs. **Not the official 2026 ranking.**\n\n")
        f.write("| Solver | Solved / 12 | PAR-2 mean s | Timeout | Error | Independent SAT/proof checks |\n|---|---:|---:|---:|---:|---:|\n")
        for x in results:f.write(f'| {x["solver"]} | {x["solved"]}/12 | {x["par2_seconds"]:.6f} | {x["timeouts"]} | {x["errors"]} | {x["independently_verified"]}/12 |\n')
        f.write("\nOriginal source SHA256, all attempts, labels and limits in JSON artifact. UNSAT without a replayed parity certificate relies on published official label only.\n")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="cmd",required=True)
    a=subs.add_parser("freeze");a.add_argument("--out",required=True);a.add_argument("--prior",required=True)
    a=subs.add_parser("measure");a.add_argument("--manifest",required=True);a.add_argument("--slot",type=int,required=True);a.add_argument("--out",required=True)
    a=subs.add_parser("audit");a.add_argument("--manifest",required=True);a.add_argument("--combined",required=True);a.add_argument("--out",required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a.out,a.prior)
    elif a.cmd=="measure":measure(a.manifest,a.slot,a.out)
    else:audit(a.manifest,a.combined,a.out)

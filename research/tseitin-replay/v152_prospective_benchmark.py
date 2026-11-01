#!/usr/bin/env python3
"""DRNAS V15.2: prospective ORIGINAL SAT Competition 2026 subset + new-seed Hall controls.
Frozen inputs before any solver runs. Only original verified labels and upstream
CaDiCaL runtimes determine selection. This is NOT the official competition ranking.
"""
import argparse,csv,hashlib,json,os,random,resource,statistics,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,"research/drnas-sat-v7-8")
sys.path.insert(0,"research/tseitin-replay")
from official_shortlong_select import download_and_features
from proofcheck import dimacs,verify_model
from v151_proof_checker import verify_certificate as verify_v151_certificate
from v152_hall_cases import make_case,verify_hall,write
REV="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
SCORES_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
PROTOCOL="DRNAS-V152-PROSPECTIVE-SC2026-HALL-20261101"
SALT="drnas-v152-SC2026-no-tuning-20261101"
STRATA={"SAT":8,"UNSAT":8}
MAX_SIZE=16*1024*1024
SCORES_URL="https://raw.githubusercontent.com/satcompetition/2026/"+REV+"/downloads/scores.csv"
SOLVERS=("v151","v152","kissat")
OFFICIAL_CAP=8.0
HALL_CAP=3.0
REPEATS=2
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def get_ids(data):
    ids=set()
    def visit(x):
        if isinstance(x,dict):
            if "id" in x and isinstance(x["id"],str) and len(x["id"])==32:
                ids.add(x["id"])
            for y in x.values():visit(y)
        elif isinstance(x,list):
            for y in x:visit(y)
    visit(data)
    return ids
def get_official_scores():
    raw=urllib.request.urlopen(SCORES_URL,timeout=90).read()
    blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    assert blob==SCORES_BLOB,(blob,SCORES_BLOB)
    return list(csv.DictReader(raw.decode().splitlines()))
def freeze(prior96,prior148,out):
    seen=get_ids(json.loads(Path(prior96).read_text())) | get_ids(json.loads(Path(prior148).read_text()))
    rows=[r for r in get_official_scores() if r.get("solverid")=="biere_cadical3[main]"]
    assert len(rows)==400
    selected=[];attempts=[]
    for label,count in STRATA.items():
        pool=[]
        for row in rows:
            if row["instanceid"] in seen:continue
            if row["status"]!=("sat-verified" if label=="SAT" else "unsat-verified"):continue
            s=float(row["runtime"])
            if not 0<=s<=180:continue
            band="fast" if s<5 else "mid" if s<30 else "slow"
            pool.append(dict(id=row["instanceid"],label=label,stratum=label+"_"+band,
                             official_cadical_seconds=s))
        # Prespecified SHA lottery across all difficulty bands. Do not prefer
        # fast cases after the prior pools have been exhausted.
        pool.sort(key=lambda c:hashlib.sha256((SALT+"/"+label+"/"+c["id"]).encode()).hexdigest())
        for case in pool:
            try:
                detail=download_and_features(case["id"])
                if detail["cnf_bytes"]>MAX_SIZE:raise ValueError("over 16 MiB fixed cap")
                accepted={**case,**detail}
                selected.append(accepted)
                attempts.append(dict(id=case["id"],stratum=case["stratum"],accepted=True))
                print("V152_FROZEN",case["stratum"],case["id"],detail["sha256"],detail["cnf_bytes"],flush=True)
            except Exception as err:
                attempts.append(dict(id=case["id"],stratum=case["stratum"],accepted=False,reason=str(err)[:160]))
            if sum(c["label"]==label for c in selected)==count:break
        assert sum(c["label"]==label for c in selected)==count,("insufficient new cases",label)
    assert len(selected)==16 and len({c["id"] for c in selected})==16
    assert not seen.intersection(c["id"] for c in selected)
    selected.sort(key=lambda c:hashlib.sha256((SALT+"/schedule/"+c["id"]).encode()).hexdigest())
    dump(out,dict(protocol=PROTOCOL,selection="16 prospective original 2026 CNFs, 8 SAT/8 UNSAT chosen by fixed SHA lottery among official CaDiCaL <=180s, no DRNAS evaluation",
                  official_rev=REV,score_blob=SCORES_BLOB,excluded_prior_cases=len(seen),source_inputs=selected,
                  attempts=attempts,solvers=SOLVERS,repeats=REPEATS,official_cap=OFFICIAL_CAP,
                  hall_cap=HALL_CAP,one_cpu=True,memory_gib=3,
                  limitations=["Not official SC2026 ranking, uses 8s not competition 5000s and GitHub shared hardware",
                   "Size cap 16MiB and <=180s official CaDiCaL baseline; balanced SAT/UNSAT, not representative of full track",
                   "Original official labels publicly known; new holdout only relative to frozen prior DRNAS subsets",
                   "For native UNSAT checks run independent certificate verifier; Kissat UNSAT trusted against published label",
                   "Hall generator is newly seeded but mathematical class is known from prior development"]))
    print("V152_FROZEN_PASS",len(selected),"prior_known",len(seen),flush=True)
def setup():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def invoke(solver,path,cap):
    path=path.resolve()
    if solver=="kissat":cmd=[str(Path("bin/kissat_solver").resolve()),str(path)]
    else:cmd=[str(Path("bin",{"v151":"v151_expanded","v152":"v152_hall_portfolio"}[solver]).resolve()),
               str(path),str(Path("bin/kissat_solver").resolve()),"0"]
    begin=time.perf_counter()
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=cap,route="timeout",payload=None,model=[])
    seconds=time.perf_counter()-begin
    if seconds>cap:return dict(status="TIMEOUT",seconds=cap,route="timeout",payload=None,model=[])
    payloads=[line.split("\t",1)[1] for line in p.stdout.splitlines() if line.startswith("DRNAS_HYBRID_RESULT\t")]
    if payloads:
        assert len(payloads)==1 and p.returncode==0,(solver,p.returncode,p.stderr[-250:])
        payload=json.loads(payloads[0]);status=payload["status"]
        route=payload["path"];model=payload.get("model",[])
    else:
        status={10:"SAT",20:"UNSAT"}.get(p.returncode)
        assert status and "s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in p.stdout.splitlines(),(solver,p.returncode,p.stdout[-200:],p.stderr[-200:])
        payload=None
        route="kissat_direct" if solver=="kissat" else "kissat_fallback"
        model=[int(v) for line in p.stdout.splitlines() if line.startswith("v ") for v in line.split()[1:] if v!="0"]
    return dict(status=status,seconds=round(seconds,7),route=route,payload=payload,model=model)
def check_result(n,clauses,answer,official_label):
    if answer["status"]=="TIMEOUT":return "timeout"
    assert answer["status"]==official_label,("wrong answer",official_label,answer["status"])
    if answer["status"]=="SAT":
        verify_model(n,clauses,answer["model"])
        return "independent_model"
    payload=answer["payload"]
    if payload:
        if payload["path"]=="hall_deficiency_exact":
            verify_hall(clauses,payload)
            return "independent_hall_proof"
        assert verify_v151_certificate(payload,clauses),("invalid native V15.1 certificate",payload["path"])
        return "independent_v151_certificate"
    return "published_official_label_only"
def measure(slot,manifest_file,out):
    m=json.loads(Path(manifest_file).read_text())
    assert m["protocol"]==PROTOCOL and len(m["source_inputs"])==16
    assert slot in range(4)
    setup()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    meta=dict(slot=slot,manifest_sha256=hash_file(manifest_file),
              src_151_sha256=hash_file("bin/v151_expanded"),
              src_152_sha256=hash_file("bin/v152_hall_portfolio"),
              kissat_sha256=hash_file("bin/kissat_solver"),
              cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines() if x.startswith("model name")),"unknown"),
              case_ids=[x["id"] for x in m["source_inputs"][4*slot:4*slot+4]])
    dump(out/"meta.json",meta)
    results=[]
    def perform(tag,caseid,p,n,clauses,label,cap,features=None):
        for rep in range(REPEATS):
            order=list(SOLVERS)
            random.Random(int(hashlib.sha256((SALT+"/"+tag+"/"+caseid+"/"+str(rep)).encode()).hexdigest()[:8],16)).shuffle(order)
            for solver in order:
                try:
                    ans=invoke(solver,p,cap)
                    proof=check_result(n,clauses,ans,label)
                    row=dict(group=tag,case=caseid,label=label,rep=rep,solver=solver,
                             status=ans["status"],route=ans["route"],seconds=ans["seconds"],check=proof)
                except Exception as e:
                    row=dict(group=tag,case=caseid,label=label,rep=rep,solver=solver,
                             status="ERROR",route="exception",seconds=cap,check="REJECT",
                             error=str(e)[:260])
                results.append(row)
                dump(out/"rows.json",results)
                print("V152_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    for case in m["source_inputs"][4*slot:4*slot+4]:
        cnf=out/(case["id"]+".cnf")
        info=download_and_features(case["id"],cnf)
        assert info["sha256"]==case["sha256"] and info["features"]==case["features"]
        n,clauses=dimacs(cnf)
        assert n==case["variables"] and len(clauses)==case["clauses"]
        print("V152_OFFICIAL_SOURCE_SHA_OK",case["id"],case["sha256"],flush=True)
        perform("official",case["id"],cnf,n,clauses,case["label"],OFFICIAL_CAP)
        cnf.unlink()
    for unsat in (False,True):
        n,clauses,label,description=make_case(slot,unsat)
        caseid="hall-"+str(slot)+("-unsat" if unsat else "-sat")
        p=out/(caseid+".cnf")
        write(p,n,clauses)
        print("V152_HALL_SOURCE_SHA",caseid,hash_file(p),description,flush=True)
        perform("hall_new_seed",caseid,p,n,clauses,label,HALL_CAP)
        p.unlink()
    assert len(results)==(4+2)*2*len(SOLVERS)==36
    print("V152_SHARD_PASS",slot,len(results),flush=True)
def audit(manifest_file,all_dir,out):
    manifest=json.loads(Path(manifest_file).read_text())
    assert manifest["protocol"]==PROTOCOL and len(manifest["source_inputs"])==16
    trials=[];metas=[]
    for slot in range(4):
        folder=Path(all_dir)/("v152-shard-"+str(slot))
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["slot"]==slot and meta["manifest_sha256"]==hash_file(manifest_file)
        assert meta["case_ids"]==[x["id"] for x in manifest["source_inputs"][4*slot:4*slot+4]]
        metas.append(meta)
        rows=json.loads((folder/"rows.json").read_text())
        assert len(rows)==36,len(rows)
        trials+=rows
    keys=set()
    for row in trials:
        key=(row["group"],row["case"],row["solver"],row["rep"])
        assert key not in keys;keys.add(key)
        assert row["status"] in ("SAT","UNSAT","TIMEOUT"),row
        assert row["status"] not in ("SAT","UNSAT") or row["status"]==row["label"]
        if row["solver"]=="v152" and row["route"]=="hall_deficiency_exact":
            assert row["check"]=="independent_hall_proof"
        if row["status"]=="SAT":assert row["check"]=="independent_model"
    assert len(trials)==4*36==144
    summary=[]
    for group,cap,expected in (("official",OFFICIAL_CAP,32),("hall_new_seed",HALL_CAP,16)):
        for solver in SOLVERS:
            rows=[r for r in trials if r["group"]==group and r["solver"]==solver]
            assert len(rows)==expected
            p2=[r["seconds"] if r["status"]!="TIMEOUT" else 2*cap for r in rows]
            item=dict(group=group,solver=solver,solved=sum(r["status"]!="TIMEOUT" for r in rows),
                      attempts=len(rows),par2_mean_s=round(statistics.mean(p2),6),
                      par2_sum_s=round(sum(p2),6),verified=sum(r["check"].startswith("independent") for r in rows),
                      routes={s:sum(r["route"]==s for r in rows) for s in sorted({r["route"] for r in rows})},
                      errors=0)
            summary.append(item)
            print("V152_RESULT",json.dumps(item,sort_keys=True),flush=True)
    assert all(m["src_151_sha256"]==metas[0]["src_151_sha256"] and
               m["src_152_sha256"]==metas[0]["src_152_sha256"] and
               m["kissat_sha256"]==metas[0]["kissat_sha256"] for m in metas)
    dump(out,dict(protocol=PROTOCOL,unofficial=True,manifest=manifest,hardware=metas,summary=summary,trials=trials))
    print("V152_FINAL_AUDIT_PASS",len(trials),"official_inputs",16,"new_hall_inputs",8,flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    f.add_argument("--old96",required=True);f.add_argument("--old148",required=True);f.add_argument("--out",required=True)
    m=sub.add_parser("measure");m.add_argument("--slot",type=int,required=True);m.add_argument("--manifest",required=True);m.add_argument("--out",required=True)
    a=sub.add_parser("audit");a.add_argument("--manifest",required=True);a.add_argument("--all",required=True);a.add_argument("--out",required=True)
    args=parser.parse_args()
    if args.cmd=="freeze":freeze(args.old96,args.old148,args.out)
    elif args.cmd=="measure":measure(args.slot,args.manifest,args.out)
    else:audit(args.manifest,args.all,args.out)

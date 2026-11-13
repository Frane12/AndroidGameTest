#!/usr/bin/env python3
"""COOP5 two-binary fixed 25ms vs dynamic BCP gate original CNF proof-checked A/B.

Historical real minisample + synthetic originals. Each credited SAT witness
and UNSAT proof is independently verified. This is NOT blind performance evidence.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, tempfile, time, signal
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_coop1"))
sys.path.insert(0,str(ROOT/"research"))
from synthetic import FAMILIES, make, text as dimacs, model_ok
import drnas_x55_cpu_real36 as B

ARMS=("X5_FROZEN","ALGEBRA","DIRECT_ON","FIXED_SHADOW","FIXED_ON","DYNAMIC_SHADOW","DYNAMIC_ON")
CONFIG={
 "ALGEBRA":("fixed","algebra","off"),
 "DIRECT_ON":("fixed","on","off"),
 "FIXED_SHADOW":("fixed","on","shadow"),
 "FIXED_ON":("fixed","on","on"),
 "DYNAMIC_SHADOW":("dynamic","on","shadow"),
 "DYNAMIC_ON":("dynamic","on","on")}

def instances(cohort):
    if cohort=="synthetic":
        for family in FAMILIES:
            for level in range(3):
                seed=1713119+FAMILIES.index(family)*1000+level*100
                n,cs,expected=make(family,level,seed,"stress")
                payload=dimacs(n,cs)
                yield {"family":family,"id":f"{family}:{level}:0",
                    "n":n,"clauses":cs,"expected":expected,
                    "source":payload,"sha256":hashlib.sha256(payload.encode()).hexdigest()}
    else:
        originals,_=B.official_manifest()
        eligible=[]
        for src in originals:
            data=pathlib.Path(src["path"]).read_bytes()
            assert B.sha(data)==src["sha256"]
            n,cs=B.parse_cnf(data)
            if n<=4096 and len(cs)<=12000:
                eligible.append({"family":src["family"],"id":str(src["id"]),
                   "n":n,"clauses":cs,"expected":None,
                   "source":data.decode(),"sha256":src["sha256"]})
        # All eligible real original CNFs, selected only by input dimensions;
        # never by solve status or previously measured improvement.
        for c in eligible:yield c

def one(binary,checker,case,cnf,arm,cap,rep,work):
    proof=work/(f"{case['id'].replace(':','_')}_{rep}_{arm}.drat")
    if arm=="X5_FROZEN":
        target=ROOT/"build/drnas-x5"
        extra=[]
    else:
        policy,algebra,probes=CONFIG[arm]
        target=ROOT/"build"/("drnas-coop5-"+policy)
        extra=["--coop4",algebra,"--coop5",probes]
    cmd=[str(target),str(cnf),"--mode","core","--time",str(cap),
         "--stats","--x5-no-minimize","--proof",str(proof),*extra]
    begin=time.perf_counter()
    q=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,start_new_session=True)
    try:
        out,err=q.communicate(timeout=cap+0.6)
        rc=q.returncode
    except subprocess.TimeoutExpired:
        os.killpg(q.pid,signal.SIGKILL)
        out,err=q.communicate();rc=0
    sec=time.perf_counter()-begin
    if rc not in (0,10,20):raise RuntimeError(("CRASH",case["id"],arm,rc,err[-500:]))
    status="UNKNOWN"
    if rc==10:
        if not model_ok(case["n"],case["clauses"],out):
            raise RuntimeError(("WRONG SAT",case["id"],arm))
        status="SAT"
    elif rc==20:
        p=subprocess.run([str(checker),str(cnf),str(proof)],
                         text=True,capture_output=True,timeout=20)
        if p.returncode!=0 or "s VERIFIED" not in p.stdout:
            raise RuntimeError(("WRONG UNSAT PROOF",case["id"],arm,p.stdout[-300:],p.stderr[-300:]))
        status="UNSAT"
    if case["expected"] is not None and status in ("SAT","UNSAT"):
        assert (status=="SAT")==case["expected"],("WRONG EXPECTED",case["id"],status)
    audited=[json.loads(t.split(" ",1)[1]) for t in err.splitlines()
             if t.startswith("COOP5_PROBE ")]
    native=[json.loads(t.split(" ",1)[1]) for t in err.splitlines()
            if t.startswith("X41_STATS ")]
    if arm!="X5_FROZEN" and (rc in (0,10,20)):
        assert len(audited)==1,(case["id"],arm,err[-450:])
        st=audited[0]
        assert st["mode"]==CONFIG[arm][2]
        assert st["default_policy"]==CONFIG[arm][0]
        assert st["actually_overrode"]<=st["would_override"]
        if st["mode"]!="on":assert st["actually_overrode"]==0
        assert st["probe_wall_ms"]<=st["budget_ms"]+2.0,(case["id"],arm,st)
    credit=(status!="UNKNOWN" and sec<=cap)
    return {"id":case["id"],"family":case["family"],"sha256":case["sha256"],
            "rep":rep,"arm":arm,"status":status,"certified":status!="UNKNOWN",
            "accepted":credit,"time_s":round(sec,6),"PAR2":round(sec if credit else 2*cap,6),
            "probe":audited[0] if audited else {},"native":native[0] if native else {}}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("synthetic","real"),required=True)
    p.add_argument("--cap",type=float,default=1.0)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--out",required=True)
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=3)
    args=p.parse_args()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binary=(ROOT/"build/drnas-coop5-fixed").resolve()
    checker=(ROOT/"build/drat-trim").resolve()
    assert binary.is_file() and checker.is_file()
    assert (ROOT/"build/drnas-coop5-dynamic").is_file()
    assert (ROOT/"build/drnas-x5").is_file()
    assert 0<=args.shard<args.shards
    cases=list(instances(args.cohort))
    assert len(cases)>0
    selected=[case for i,case in enumerate(cases) if i%args.shards==args.shard]
    assert selected
    dest=ROOT/args.out;dest.mkdir(parents=True,exist_ok=False)
    (dest/"manifest.json").write_text(json.dumps({
       "cohort":args.cohort,"shard":args.shard,"shards":args.shards,
       "total_sources":len(cases),"selected_sha256":[x["sha256"] for x in selected],
       "cap_s":args.cap,"repeats":args.repeats,"arms":ARMS,
       "binaries":{p:hashlib.sha256((ROOT/"build"/p).read_bytes()).hexdigest()
         for p in ("drnas-coop5-fixed","drnas-coop5-dynamic","drnas-x5")},
       "blind_holdout":False,"promotion":False},sort_keys=True,indent=2)+"\n")
    trials=[];answers=collections.defaultdict(set)
    with tempfile.TemporaryDirectory() as d,(dest/"trials.jsonl").open("w") as log:
        t=pathlib.Path(d)
        for i,case in enumerate(selected):
            cnf=t/"case.cnf";cnf.write_text(case["source"])
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(20261114+17*i+rep).shuffle(order)
                for arm in order:
                    row=one(binary,checker,case,cnf,arm,args.cap,rep,t)
                    if row["certified"]:
                        answers[case["sha256"]].add(row["status"])
                        if len(answers[case["sha256"]])>1:
                            raise RuntimeError(("CERTIFIED CONTRADICTION",case["id"]))
                    trials.append(row)
                    log.write(json.dumps(row,sort_keys=True)+"\n");log.flush()
            print("COOP5_PROGRESS "+json.dumps({"cohort":args.cohort,
                "shard":args.shard,"completed":i+1,"total":len(selected)}),flush=True)
    assert len(trials)==len(selected)*args.repeats*len(ARMS)
    results={}
    for arm in ARMS:
        rows=[r for r in trials if r["arm"]==arm]
        stats=[r["probe"] for r in rows]
        results[arm]={"attempts":len(rows),
          "verified":sum(r["accepted"] for r in rows),
          "PAR2_s":round(sum(r["PAR2"] for r in rows),6),
          "SAT":sum(r["accepted"] and r["status"]=="SAT" for r in rows),
          "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT" for r in rows),
          "probe_wall_ms":round(sum(x.get("probe_wall_ms",0) for x in stats),6),
          **{key:sum(x.get(key,0) for x in stats) for key in
             ("attempted_pairs","would_override","actually_overrode",
              "shadow_recommend","completed_pairs","partial_pairs","feedback_good",
              "feedback_bad","depth96","depth320","depth900","adaptive_cooldowns")}}
    report={"status":"COMPLETE","scope":"retrospective development evidence, not blind",
      "cohort":args.cohort,"shard":args.shard,"cases":len(selected),
      "repeats":args.repeats,"cap":args.cap,"overall":results,"promotion":False}
    (dest/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("COOP5_SHARD_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()

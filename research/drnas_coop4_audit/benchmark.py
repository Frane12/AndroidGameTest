#!/usr/bin/env python3
"""Same-binary COOP4 hint audit: OFF / ALGEBRA / ON / ON_FRESH.

Historical real minisample + synthetic originals. Each credited SAT witness
and UNSAT proof is independently verified. This is NOT blind performance evidence.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, tempfile, time, signal
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_coop1"))
sys.path.insert(0,str(ROOT/"research"))
from synthetic import FAMILIES, make, text as dimacs, model_ok
import drnas_x55_cpu_real36 as B

ARMS=("OFF","ALGEBRA","ON","ON_FRESH")
FLAGS={"OFF":["--coop4","off"],"ALGEBRA":["--coop4","algebra"],
       "ON":["--coop4","on"],"ON_FRESH":["--coop4","on","--coop4-audit-fresh"]}

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
        groups=collections.defaultdict(list)
        for c in eligible:groups[c["family"]].append(c)
        # family-balanced, outcome-agnostic; at most 2 original CNFs/family
        selected=[c for family in sorted(groups) for c in groups[family][:2]]
        for c in selected[:12]:yield c

def one(binary,checker,case,cnf,arm,cap,rep,work):
    proof=work/(f"{case['id'].replace(':','_')}_{rep}_{arm}.drat")
    cmd=[str(binary),str(cnf),"--mode","core","--time",str(cap),
         "--stats","--x5-no-minimize","--proof",str(proof),*FLAGS[arm]]
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
             if t.startswith("COOP4_HINT_AUDIT ")]
    telemetry=[json.loads(t.split(" ",1)[1]) for t in err.splitlines()
               if t.startswith("COOP4_STATS ")]
    if rc in (10,20) or (rc==0 and audited):
        assert len(audited)==len(telemetry)==1,(case["id"],arm,err[-450:])
        assert audited[0]["fresh"]==(arm=="ON_FRESH")
        assert telemetry[0]["mode"]==({"ON_FRESH":"on","ON":"on","OFF":"off","ALGEBRA":"algebra"}[arm])
        assert audited[0]["stale_overrides"]<=audited[0]["overrides"]
        assert audited[0]["overrides"]<=audited[0]["selected"]
        assert audited[0]["phase_opposite_small_branch"]<=audited[0]["phase_comparable"]
        if arm=="ON_FRESH":
            assert audited[0]["stale_overrides"]==0
            assert audited[0]["suppressed"]==audited[0]["stale_proposals"]
    credit=(status!="UNKNOWN" and sec<=cap)
    return {"id":case["id"],"family":case["family"],"sha256":case["sha256"],
            "rep":rep,"arm":arm,"status":status,"certified":status!="UNKNOWN",
            "accepted":credit,"time_s":round(sec,6),"PAR2":round(sec if credit else 2*cap,6),
            "audit":audited[0] if audited else {},"coop":telemetry[0] if telemetry else {}}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("synthetic","real"),required=True)
    p.add_argument("--cap",type=float,default=1.0)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binary=(ROOT/"build/drnas-coop4-audit").resolve()
    checker=(ROOT/"build/drat-trim").resolve()
    assert binary.is_file() and checker.is_file()
    cases=list(instances(args.cohort))
    assert len(cases)>0
    dest=ROOT/args.out;dest.mkdir(parents=True,exist_ok=False)
    trials=[];answers=collections.defaultdict(set)
    with tempfile.TemporaryDirectory() as d,(dest/"trials.jsonl").open("w") as log:
        t=pathlib.Path(d)
        for i,case in enumerate(cases):
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
            print("COOP4_AUDIT_PROGRESS "+json.dumps({"cohort":args.cohort,
                "completed":i+1,"total":len(cases)}),flush=True)
    assert len(trials)==len(cases)*args.repeats*len(ARMS)
    results={}
    for arm in ARMS:
        rows=[r for r in trials if r["arm"]==arm]
        audit=[r["audit"] for r in rows]
        results[arm]={"n":len(rows),"verified":sum(r["accepted"] for r in rows),
          "PAR2":round(sum(r["PAR2"] for r in rows),5),
          **{field:sum(v.get(field,0) for v in audit) for field in
            ("proposals","stale_proposals","suppressed","selected","overrides",
             "stale_overrides","phase_comparable","phase_opposite_small_branch")},
          "families_solved":dict(collections.Counter(
              r["family"] for r in rows if r["accepted"]))}
    assert results["ON_FRESH"]["stale_overrides"]==0
    report={"status":"COMPLETE","scope":"retrospective audit, not blind",
      "cohort":args.cohort,"cases":len(cases),"repeats":args.repeats,"cap":args.cap,
      "binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
      "overall":results,"promotion":False}
    (dest/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("COOP4_HINT_AUDIT_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()

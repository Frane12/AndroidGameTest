#!/usr/bin/env python3
"""DRNAS V14.0 native exact PHP recognition; pinned real 2024 regression.
Eight new deterministically variable-permuted complete PHP CNFs, each fully
UNSAT by n+1 pigeons into n holes; reject altered/incomplete near-misses.
Twelve previously SHA-locked external SAT Competition 2024 inputs (known from
previous experiment), with original official labels; NOT unseen to our project.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
import v134_constructive as v134
import v137_fastpath as exact
import official_shortlong_select as source
import official_2026_mini_sim as mini
import v139_evaluate as prior

PROTO="DRNAS-V140-NATIVE-EXACT-PHP-REAL2024-20261101-v1"
REALPROTO="DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101"
SALT="DRNAS-V140-PHP-NEW-PERMUTED-8-20261101-v1"
HOLES=(6,7,8,9,10,11,12,13)
PHP_MODES=("V140_Native","V139_Native","V137_Exact","Kissat404")
REAL_MODES=("V140_Native","V76_adaptive_plain","Kissat404")
SHARDS=8;REAL_SHARDS=6;REPS=2;PHPCAP=30.;REALCAP=20.
source.RAW_CAP=96*1024**2;source.CNF_CAP=96*1024**2
source.VARIABLE_CAP=1000000;source.CLAUSE_CAP=4000000

def check(x,msg):
    if not x:raise RuntimeError(msg)
def load(p):return json.loads(Path(p).read_text())
def save(p,d):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(p):return digest(Path(p).read_bytes())
def php(i):
    holes=HOLES[i];birds=holes+1
    rng=random.Random(int(digest((SALT+"/"+str(i)).encode()),16))
    count=holes*birds;perm=list(range(1,count+1));rng.shuffle(perm)
    var=lambda b,h:perm[b*holes+h]
    clauses=[tuple(var(b,h) for h in range(holes)) for b in range(birds)]
    for h in range(holes):
        for b in range(birds):
            for other in range(b+1,birds):
                clauses.append((-var(b,h),-var(other,h)))
    clauses=[tuple(rng.sample(c,len(c))) for c in clauses]
    rng.shuffle(clauses)
    raw=v134.dimacs(count,clauses)
    entry={"id":f"v140/php/{i:02}","index":i,"holes":holes,"birds":birds,
           "sha256":digest(raw),"official_label":"UNSAT","clauses":len(clauses),
           "variables":count,"source":"synthetic_permuted_php"}
    return entry,raw
def selftest():
    arr=[php(i)[0] for i in range(len(HOLES))]
    check(len({x["sha256"] for x in arr})==len(HOLES),"Duplicate PHP")
    for i in range(len(HOLES)):
        c,raw=php(i)
        n,clauses=exact.read_dimacs(raw)
        z=exact.decide(raw)
        check(z["status"]=="UNSAT" and z["path"]=="pigeonhole_exact",
              "Independent PHP proof detector failed")
        check(exact.verify(n,clauses,z),"Independent PHP proof verifier failed")
    print("V140_GENERATOR_SELFTEST_PASS 8 distinct complete PHP",flush=True)
def freeze(a):
    selftest()
    real=load(a.real)
    check(real["protocol"]==REALPROTO and len(real["cases"])==12,
          "Wrong historical external competition cohort")
    check(all(c["official_label"] in ("SAT","UNSAT") and
          len(c["sha256"])==64 for c in real["cases"]),"Bad external SHA labels")
    save(a.out,{"protocol":PROTO,"php_cases":[php(i)[0] for i in range(8)],
       "external_cases":real["cases"],"external_manifest_sha256":sha(a.real),
       "php_cap":PHPCAP,"real_cap":REALCAP,"reps":REPS,
       "php_modes":PHP_MODES,"real_modes":REAL_MODES,
       "limits":"3GiB, pinned one CPU, paired runner, two repetitions",
       "disclaimer":[
          "8 NEW constructed, permuted PHP formulas; established pigeonhole theorem.",
          "12 genuine official 2024 CNFs, independently SHA-frozen before prior V13.9 testing; these are REUSED regression cases, not fresh unseen holdout.",
          "No official SAT Competition score, world record, or general SAT complexity claim.",
          "UNSAT from complete native PHP proof is independently reverified, all other UNSAT checked only against historical official labels.",
          "30s synthetic PHP and 20s external cutoff; 3GiB, 1 CPU GitHub runners."]})
    print("V140_FREEZE_PASS 8 PHP+12 external real",sha(a.out),flush=True)
def memory():mini.memory_limit()
def direct(mode,cnf,seed,truth,a,cap,cohort):
    mini.CAP=cap;mini.MEMORY_GIB=3
    if mode=="Kissat404":
        z=mini.trial("Kissat404",cnf,seed,a.v76,a.kissat,truth)
        return dict(status=z["status"],seconds=z["seconds"],
                    error=z["error"],path="kissat")
    if mode=="V76_adaptive_plain":
        z=prior.v76.trial(mode,cnf,seed,truth,a.v76,a.legacy,a.kissat)
        return dict(status=z["status"],seconds=z["seconds"],
                    error=z["error"],path="v76_plain")
    if mode=="V137_Exact":
        import sys
        cmd=[sys.executable,str(Path(exact.__file__).resolve()),
             str(Path(cnf).resolve()),"--drnas",str(Path(a.legacy).resolve()),
             "--kissat",str(Path(a.kissat).resolve()),"--seed",str(seed)]
        start=time.monotonic()
        try:
            p=subprocess.run(cmd,timeout=cap,capture_output=True,text=True,
                             errors="replace",preexec_fn=memory)
            sec=time.monotonic()-start
            check(p.returncode==0,"V13.7 exact process exit "+p.stderr[-250:])
            lines=[x for x in p.stdout.splitlines()
                   if x.startswith("DRNAS_V137_RESULT\t")]
            check(len(lines)==1,"Missing original V13.7 result")
            result=json.loads(lines[0].split("\t",1)[1])
            check(result["status"]==truth and result["path"]=="pigeonhole_exact",
                  "V13.7 wrong PHP result")
            n,clauses=exact.read_dimacs(cnf.read_bytes())
            check(exact.verify(n,clauses,result),"V13.7 PHP proof verification failed")
            return dict(status=truth,seconds=round(sec,6),
                        error="",path="pigeonhole_exact")
        except subprocess.TimeoutExpired:
            return dict(status="TIMEOUT",seconds=cap,error="",path="timeout")
        except Exception as e:
            return dict(status="ERROR",seconds=min(cap,time.monotonic()-start),
                        error=str(e)[:320],path="ERROR")
    binary=a.v140 if mode=="V140_Native" else a.v139
    cmd=[str(Path(binary).resolve()),str(Path(cnf).resolve()),
         str(Path(a.v76).resolve()),str(seed)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,errors="replace",
             timeout=cap,preexec_fn=memory)
        sec=time.monotonic()-start
        check(p.returncode==0,"Native exited "+str(p.returncode)+" "+p.stderr[-240:])
        lines=p.stdout.splitlines()
        exacts=[x for x in lines if x.startswith("DRNAS_HYBRID_RESULT\t")]
        if exacts:
            check(len(exacts)==1,"Duplicate structural result")
            proof=json.loads(exacts[0].split("\t",1)[1])
            check(proof["status"]==truth and proof["verified"],"Wrong exact result")
            n,cs=exact.read_dimacs(cnf.read_bytes())
            check(exact.verify(n,cs,proof),"Independent exact proof rejection")
            path=proof["path"]
            if cohort=="php":check(path=="pigeonhole_exact","Failed expected native PHP")
        else:
            check(any(x=="DRNAS_HYBRID_ROUTE\tfallback_v76" for x in lines),
                  "No exact result or fallback marker")
            answers=[x for x in lines if x.startswith("DRNAS_RESULT\t")]
            check(len(answers)==1,"No V7.6 fallback result")
            label=answers[0].split("\t")[2]
            check(label==truth,"Wrong fallback result")
            path="fallback_v76"
            if cohort=="php":raise RuntimeError("PHP did not reach exact path")
        check(sec<=cap,"Late process")
        return dict(status=truth,seconds=round(sec,6),path=path,error="")
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=cap,path="timeout",error="")
    except Exception as ex:
        return dict(status="ERROR",seconds=min(cap,time.monotonic()-start),
                    path="ERROR",error=str(ex)[:320])
def run(a,cohort):
    m=load(a.manifest);check(m["protocol"]==PROTO,"Invalid protocol")
    n=SHARDS if cohort=="php" else REAL_SHARDS
    check(0<=a.shard<n,"Wrong shard")
    cases=(m["php_cases"] if cohort=="php" else m["external_cases"])[a.shard::n]
    check(len(cases)==1 if cohort=="php" else len(cases)==2,"Wrong partition")
    modes=PHP_MODES if cohort=="php" else REAL_MODES
    cap=PHPCAP if cohort=="php" else REALCAP
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    import v136_symbolic
    meta={"protocol":PROTO,"shard":a.shard,"cohort":cohort,
          "manifest_sha":sha(a.manifest),"ids":[c["id"] for c in cases],
          "binaries":{x:sha(getattr(a,x)) for x in ("v140","v139","v76","legacy","kissat")},
          "code":sha(exact.__file__),"cpu":next((z.split(":",1)[1].strip()
          for z in Path("/proc/cpuinfo").read_text().splitlines()
          if z.startswith("model name")),"unknown")}
    save(out/"meta.json",meta);rows=[]
    for c in cases:
        if cohort=="php":
            original,raw=php(c["index"])
            check(original==c,"Generator changed")
            cnf=out/(c["sha256"]+".cnf");cnf.write_bytes(raw)
        else:
            cnf=out/(c["id"]+".cnf")
            obs=source.download_and_features(c["id"],cnf)
            check(obs["sha256"]==c["sha256"] and
                  obs["features"]==c["features"],"Official source CNF changed")
        check(sha(cnf)==c["sha256"],"CNF byte SHA mismatch")
        attempts=[]
        for rep in range(REPS):
            seed=(1402026+int(c["sha256"][:8],16)+rep*1009)%(2**32)
            order=list(modes);random.Random(seed^140).shuffle(order)
            for mode in order:
                z=direct(mode,cnf,seed,c["official_label"],a,cap,cohort)
                check(z["status"] in ("SAT","UNSAT","TIMEOUT"),
                      "Incorrect/problem solver: "+mode+" "+c["id"]+" "+z["error"])
                check(z["status"]=="TIMEOUT" or z["status"]==c["official_label"],
                      "Answer mismatches official/proof label")
                attempts.append({"mode":mode,"rep":rep,**z})
                print("V140_TRIAL",cohort,c["id"],mode,rep,z["status"],
                      z["seconds"],z["path"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"label":c["official_label"],
                     "cohort":cohort,"trials":attempts})
        save(out/"rows.json",rows);cnf.unlink()
    print("V140_SHARD_PASS",cohort,a.shard,len(rows),flush=True)
def stats(rows,modes,cap):
    times=defaultdict(list);solved=Counter();routes=Counter()
    for c in rows:
        trials={(x["mode"],x["rep"]):x for x in c["trials"]}
        check(len(trials)==len(modes)*REPS,"Missing paired trial")
        for mode in modes:
            for rep in range(REPS):
                x=trials[(mode,rep)]
                check(x["status"] in ("SAT","UNSAT","TIMEOUT") and not x["error"],
                      "Audit solver status failure")
                if x["status"]!="TIMEOUT":check(x["status"]==c["label"],"Wrong label")
                if c["cohort"]=="php" and mode=="V140_Native":
                    check(x["path"]=="pigeonhole_exact","PHP certificate missing")
                times[mode].append(2*cap if x["status"]=="TIMEOUT" else x["seconds"])
                solved[mode]+=int(x["status"]!="TIMEOUT")
                routes[mode+":"+x["path"]]+=1
    return {"formulas":len(rows),
      "solvers":{m:{"solved":solved[m],"attempts":len(rows)*REPS,
                     "PAR2_s":round(statistics.mean(times[m]),6)} for m in modes},
      "paths":dict(routes)}
def audit(a):
    m=load(a.manifest);check(m["protocol"]==PROTO,"Wrong manifest")
    shas=set();binaries=set();cpu=set();outputs={}
    for cohort,n in (("php",SHARDS),("real",REAL_SHARDS)):
        all_rows=[];cases=m["php_cases"] if cohort=="php" else m["external_cases"]
        for shard in range(n):
            path=Path(a.combined)/f"v140-{cohort}-{shard}"
            meta=load(path/"meta.json");rr=load(path/"rows.json")
            check(meta["protocol"]==PROTO and meta["shard"]==shard and
                  meta["cohort"]==cohort and meta["manifest_sha"]==sha(a.manifest),
                  "Shard manifest drift")
            expected=cases[shard::n]
            check(meta["ids"]==[c["id"] for c in expected] and
                  [r["id"] for r in rr]==meta["ids"],"Missing/wrong case")
            binaries.add(json.dumps(meta["binaries"],sort_keys=True))
            cpu.add(meta["cpu"]);all_rows.extend(rr)
        check(len(all_rows)==len(cases),"Incomplete cohort")
        for rr in all_rows:
            c=next(z for z in cases if z["id"]==rr["id"])
            check(c["sha256"]==rr["sha256"] and
                  c["official_label"]==rr["label"],"Source identity mismatch")
            check(rr["sha256"] not in shas,"Duplicate CNF");shas.add(rr["sha256"])
        outputs[cohort]=stats(all_rows,PHP_MODES if cohort=="php" else REAL_MODES,
                               PHPCAP if cohort=="php" else REALCAP)
    check(len(binaries)==1 and len(cpu)>=1,"Solver binary identity mismatch")
    report={"protocol":PROTO,"manifest_sha":sha(a.manifest),"results":outputs,
            "cpus":sorted(cpu),"binaries":json.loads(next(iter(binaries))),
            "limitations":m["disclaimer"]}
    save(a.out,report)
    lines=["# V14.0 native exact PHP + GF(2) / V7.6 fallback","",
      "8 new permuted complete PHP CNFs, plus 12 previously published official 2024 regression CNFs.",
      "Paired 2-repeat single-core GitHub tests; 3GiB. PHP cap 30s, real cap 20s.",""]
    for cohort,z in outputs.items():
        lines.extend([f"## {cohort}: {z['formulas']} formulas",
             "| Method | Solved | PAR2 seconds ↓ |","|---|---:|---:|"])
        for mode,d in z["solvers"].items():
            lines.append(f"| {mode} | {d['solved']}/{d['attempts']} | {d['PAR2_s']:.6f} |")
        lines.append("")
    lines+=["## Caveats"]+["- "+x for x in m["disclaimer"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V140_FINAL_AUDIT_PASS",json.dumps(outputs),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    z=sub.add_parser("freeze")
    for name in ("real","out"):z.add_argument("--"+name,required=True)
    for name in ("php","real"):
        z=sub.add_parser(name)
        for key in ("manifest","v140","v139","v76","legacy","kissat","out"):
            z.add_argument("--"+key,required=True)
        z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for name in ("manifest","combined","out","md"):z.add_argument("--"+name,required=True)
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    elif a.cmd=="freeze":freeze(a)
    elif a.cmd=="audit":audit(a)
    else:run(a,a.cmd)
if __name__=="__main__":main()

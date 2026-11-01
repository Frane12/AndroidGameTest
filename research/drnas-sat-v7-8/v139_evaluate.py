#!/usr/bin/env python3
"""DRNAS V13.9 native C++ exact GF2 + V7.6 fallback benchmark, strict paired audit.

48 exact V7.6.1 XOR cases from historical frozen bytes (8 x 6), 2 repeats,
and 12 historical V13.4 non-XOR cases (six planted3 and six 3-color) as a
non-XOR fallback safety cohort. Per process 30s, 3 GiB, same runner and core.
No retraining, case rejection, or claim of general polynomial SAT.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,sys,time
from collections import Counter,defaultdict
from pathlib import Path
import v761_xor_holdout as xor
import v134_constructive as v134
import v137_fastpath as exact
import v137_vs_v76_xor as previous
import v76_v134_matched as v76
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-V139-NATIVE-AFFINE-48-XOR-12-FALLBACK-20261101-v1"
XOR_PROTO="DRNAS-V761-XOR-REPEATS-AND-48-FROZEN-20261101-v1"
MIX_PROTO="DRNAS-V134-LOCKED-STRUCTURAL-LADDERS-20261101"
PRIMARY_MODES=("V139_Native","V137_Exact","V76_adaptive_guided","Kissat404")
FALLBACK_MODES=("V139_Native","V76_adaptive_plain","Kissat404")
REPS=2;SHARDS=8;CAP=30.0
mini.CAP=CAP;mini.MEMORY_GIB=3
def check(ok,msg):
    if not ok:raise RuntimeError(msg)
def load(x):return json.loads(Path(x).read_text())
def save(x,z):
    path=Path(x);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(z,sort_keys=True,indent=2)+"\n")
def sha(x):return hashlib.sha256(Path(x).read_bytes()).hexdigest()
def parse_v76(lines,method):
    candidates=[line for line in lines if line.startswith("DRNAS_RESULT\t")]
    check(len(candidates)==1,"Missing V76 result")
    parts=candidates[0].split("\t")
    check(len(parts)>=5 and parts[1]==method and parts[2] in ("SAT","UNSAT"),
          "Malformed V76 output")
    return parts[2]
def run_native(path,seed,label,a,required):
    cmd=[str(Path(a.native).resolve()),str(path.resolve()),
         str(Path(a.v76).resolve()),str(seed)]
    t0=time.monotonic()
    try:
        p=subprocess.run(cmd,timeout=CAP,capture_output=True,text=True,errors="replace",
                         preexec_fn=mini.memory_limit)
        elapsed=time.monotonic()-t0
        check(p.returncode==0,"Native hybrid failure: "+p.stderr[-500:])
        lines=p.stdout.splitlines()
        routes=[line for line in lines if line.startswith("DRNAS_HYBRID_ROUTE\t")]
        reports=[line for line in lines if line.startswith("DRNAS_HYBRID_RESULT\t")]
        if reports:
            check(len(reports)==1 and not routes,"Ambiguous hybrid route")
            obj=json.loads(reports[0].split("\t",1)[1])
            check(obj["path"]=="affine_exact" and obj["verified"] and
                  obj["status"]==label,"Unverified native GF2 output")
            n,clauses=exact.read_dimacs(path.read_bytes())
            check(exact.verify(n,clauses,obj),"Independent Python GF2 proof check failed")
            route="affine_exact"
        else:
            check(routes==["DRNAS_HYBRID_ROUTE\tfallback_v76"],
                  "Missing explicit native fallback route")
            answer=parse_v76(lines,"adaptive_plain")
            check(answer==label,"Wrong fallback SAT status")
            route="fallback_v76"
        check(route==required,"Wrong route: expected "+required+" but got "+route)
        check(elapsed<=CAP,"Late result")
        return {"status":label,"seconds":round(elapsed,6),"route":route,
                "proof_verified":route=="affine_exact","error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"route":"timeout",
                "proof_verified":False,"error":""}
    except Exception as exc:
        return {"status":"ERROR","seconds":min(CAP,time.monotonic()-t0),
                "route":"error","proof_verified":False,"error":str(exc)[:420]}
def baseline(mode,path,seed,label,a):
    if mode=="V137_Exact":
        z=previous.exact_trial(path,seed,a.legacy,a.kissat,label)
        return {"status":z["status"],"seconds":z["seconds"],"route":z.get("path","v137"),
                "proof_verified":z.get("verified",False),"error":z["error"]}
    if mode.startswith("V76"):
        z=v76.trial(mode,path,seed,label,a.v76,a.legacy,a.kissat)
        return {"status":z["status"],"seconds":z["seconds"],"route":mode,
                "proof_verified":False,"error":z["error"]}
    z=mini.trial("Kissat404",path,seed,a.legacy,a.kissat,label)
    return {"status":z["status"],"seconds":z["seconds"],"route":mode,
            "proof_verified":False,"error":z["error"]}
def selftest():
    xor.selftest();v134.selftest()
    for i in range(48):
        c,raw=xor.make(i)
        z=exact.decide(raw)
        check(z["path"]=="affine_exact" and z["status"]==c["official_label"],
              "Wrong old exact reference for XOR")
    for f in ("planted3_sat","color3_sat"):
        for i in range(6):
            c,raw=v134.make(f,i)
            z=exact.decide(raw)
            check(z["status"]=="FALLBACK","Unexpected exact-family identification")
    check(CAP==30 and REPS==2 and SHARDS==8,"Bench settings changed")
    print("V139_SELFTEST_PASS 48 XOR + 12 non-XOR",flush=True)
def freeze(a):
    old_xor=load(a.xor_manifest);old_mix=load(a.mixed_manifest)
    check(old_xor["protocol"]==XOR_PROTO and len(old_xor["new_cases"])==48,
          "Wrong original 48 manifest")
    check(old_mix["protocol"]==MIX_PROTO and len(old_mix["cases"])==30,
          "Wrong original 30 manifest")
    xcases=old_xor["new_cases"]
    check(xcases==[xor.make(i)[0] for i in range(48)],"Frozen XOR changed")
    mitems=[c for c in old_mix["cases"] if c["family"] in ("planted3_sat","color3_sat")]
    check(len(mitems)==12 and all(c==v134.make(c["family"],c["index"])[0]
                                     for c in mitems),"Frozen fallback cohort drift")
    save(a.out,{"protocol":PROTOCOL,"xor_manifest_sha256":sha(a.xor_manifest),
                "mixed_manifest_sha256":sha(a.mixed_manifest),"xor_cases":xcases,
                "fallback_cases":mitems,"cap_seconds":CAP,"repetitions":REPS,
                "modes_xor":list(PRIMARY_MODES),"modes_fallback":list(FALLBACK_MODES),
                "original_v137_blob":"e4f44436ef53682a514fbb852e876c5c0d0a2ee3",
                "exclusions":[],"limitations":[
                  "Known, familiar XOR family, not novel general SAT or world-ranking benchmark.",
                  "48 XOR cases and 12 non-XOR cases originally frozen in earlier independent experiments.",
                  "V13.9 native C++ exact structural detector + GF2 elimination + independently checked proofs.",
                  "V13.9 non-XOR fallback directly execs V7.6 adaptive_plain, never selects from filename.",
                  "V13.7 unchanged Python process measured including interpreter startup.",
                  "30s, 3 GiB, CPU affinity pinned, two reps per solver; different GitHub runners may vary.",
                  "No official SAT Competition scores or claims of newly discovered mathematics.",
                  "The XOR speedup is expected for classic polynomial-time affine SAT subclass."]})
    print("V139_FREEZE_PASS 48+12",sha(a.out),flush=True)
def metadata(a,shard,ids):
    import v136_symbolic
    return {"protocol":PROTOCOL,"shard":shard,"manifest_sha256":sha(a.manifest),
            "ids":ids,"cpu":next((line.split(":",1)[1].strip()
              for line in Path("/proc/cpuinfo").read_text().splitlines()
              if line.startswith("model name")),"unknown"),
            "binaries":{x:sha(getattr(a,x)) for x in ("native","v76","legacy","kissat")},
            "exact_code":sha(exact.__file__),"router_code":sha(v136_symbolic.__file__)}
def run_cases(a,cases,cohort,shard,modes):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    save(root/"meta.json",metadata(a,shard,[x["id"] for x in cases]))
    rows=[]
    for c in cases:
        if cohort=="xor":check(c==xor.make(c["index"])[0],"Changed XOR case")
        else:check(c==v134.make(c["family"],c["index"])[0],"Changed fallback case")
        raw=(xor.make(c["index"])[1] if cohort=="xor" else
             v134.make(c["family"],c["index"])[1])
        cnf=root/(c["sha256"][:20]+".cnf");cnf.write_bytes(raw)
        check(sha(cnf)==c["sha256"],"Input SHA mismatch")
        trials=[]
        for rep in range(REPS):
            seed=(1392026+int(c["sha256"][:8],16)+1009*rep)%(2**32)
            order=list(modes);random.Random(seed^139).shuffle(order)
            for mode in order:
                data=(run_native(cnf,seed,c["official_label"],a,
                                 "affine_exact" if cohort=="xor" else "fallback_v76")
                      if mode=="V139_Native" else baseline(mode,cnf,seed,c["official_label"],a))
                check(data["status"] in ("SAT","UNSAT","TIMEOUT"),
                      "Bad or failed solver: "+mode+" "+c["id"]+" "+data["error"])
                check(data["status"]=="TIMEOUT" or
                      data["status"]==c["official_label"],"Wrong solver answer")
                trials.append({"mode":mode,"rep":rep,**data})
                print("V139_TRIAL",cohort,c["id"],mode,rep,
                      data["status"],data["seconds"],data["route"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"label":c["official_label"],
                     "family":c["family"],"cohort":cohort,"trials":trials})
        save(root/"rows.json",rows);cnf.unlink()
    check(len(rows)==len(cases),"Incomplete cohort")
    print("V139_SHARD_PASS",cohort,shard,len(rows),flush=True)
def runxor(a):
    m=load(a.manifest);check(m["protocol"]==PROTOCOL and 0<=a.shard<SHARDS,
                             "Bad protocol/shard")
    subset=m["xor_cases"][a.shard::SHARDS]
    check(len(subset)==6,"Bad XOR partition")
    run_cases(a,subset,"xor",a.shard,PRIMARY_MODES)
def runfallback(a):
    m=load(a.manifest);check(m["protocol"]==PROTOCOL,"Bad manifest")
    items=m["fallback_cases"];check(len(items)==12,"Wrong fallback size")
    run_cases(a,items,"fallback",-1,FALLBACK_MODES)
def aggregate(rows,modes):
    times=defaultdict(list);solved=Counter();path=Counter();each={}
    for r in rows:
        trials={(t["mode"],t["rep"]):t for t in r["trials"]}
        check(len(trials)==len(modes)*REPS,"Missing trials")
        item={"label":r["label"],"family":r["family"],"PAR2_per_mode":{}}
        for mode in modes:
            costs=[]
            for rep in range(REPS):
                t=trials[(mode,rep)]
                check(t["status"] in ("SAT","UNSAT","TIMEOUT") and not t["error"],
                      "Failed trial")
                check(t["status"]=="TIMEOUT" or t["status"]==r["label"],
                      "Answer mismatch")
                solved[mode]+=int(t["status"]!="TIMEOUT")
                path[(mode,t["route"])]+=1
                val=CAP*2 if t["status"]=="TIMEOUT" else t["seconds"]
                times[mode].append(val);costs.append(val)
            item["PAR2_per_mode"][mode]=round(statistics.mean(costs),6)
        each[r["id"]]=item
    return {"formulas":len(rows),"solvers":{mode:{"solved":solved[mode],
             "attempts":len(rows)*REPS,
             "PAR2_s":round(statistics.mean(times[mode]),6)} for mode in modes},
             "paths":{mode:{route:num for (k,route),num in path.items() if k==mode}
                      for mode in modes},"per_case":each}
def audit(a):
    m=load(a.manifest);check(m["protocol"]==PROTOCOL,"Wrong protocol")
    rows=[];binshas=set();codes=set();cpu=set()
    for shard in range(SHARDS):
        d=Path(a.combined)/f"v139-xor-{shard}"
        meta=load(d/"meta.json");part=load(d/"rows.json")
        expected=m["xor_cases"][shard::SHARDS]
        check(meta["shard"]==shard and meta["ids"]==[c["id"] for c in expected]
              and meta["manifest_sha256"]==sha(a.manifest),"Bad XOR provenance")
        check(len(part)==6 and [x["id"] for x in part]==meta["ids"],
              "Wrong shard size/rows")
        rows+=part;binshas.add(json.dumps(meta["binaries"],sort_keys=True))
        codes.add((meta["exact_code"],meta["router_code"]));cpu.add(meta["cpu"])
    d=Path(a.fallback)
    meta=load(d/"meta.json");fr=load(d/"rows.json")
    check(meta["shard"]==-1 and meta["ids"]==[c["id"] for c in m["fallback_cases"]]
          and meta["manifest_sha256"]==sha(a.manifest) and len(fr)==12,
          "Wrong fallback provenance")
    binshas.add(json.dumps(meta["binaries"],sort_keys=True))
    codes.add((meta["exact_code"],meta["router_code"]));cpu.add(meta["cpu"])
    check(len(binshas)==1 and len(codes)==1,"Non-identical binaries/source")
    check(len(rows)==48 and len({x["sha256"] for x in rows})==48,
          "XOR cohort incomplete or repeated")
    index={c["id"]:c for c in m["xor_cases"]+m["fallback_cases"]}
    for r in rows+fr:
        c=index[r["id"]]
        check(r["sha256"]==c["sha256"] and r["label"]==c["official_label"],
              "CNF source mismatch")
    result={"protocol":PROTOCOL,"source_manifest_sha256":sha(a.manifest),
            "xor":aggregate(rows,PRIMARY_MODES),
            "xor_unsat":aggregate([x for x in rows if x["label"]=="UNSAT"],PRIMARY_MODES),
            "xor_sat":aggregate([x for x in rows if x["label"]=="SAT"],PRIMARY_MODES),
            "fallback":aggregate(fr,FALLBACK_MODES),
            "binaries_sha256":json.loads(next(iter(binshas))),
            "CPUs":sorted(cpu),"warnings":m["limitations"],"rows":rows,"fallback_rows":fr}
    save(a.out,result)
    lines=["# DRNAS V13.9 – Native affine GF(2) + original V7.6 fallback","",
           "Audited 48 old XOR + 12 old non-XOR CNFs, two repetitions each; no input cherry-picking.",
           "30s per attempt, 3 GiB, pinned CPU, exact SAT/UNSAT truth and independent proof checks.",""]
    for name in ("xor","xor_unsat","xor_sat","fallback"):
        z=result[name]
        lines.extend([f"## {name}: {z['formulas']} formulas","",
                      "| Solver | Solved / attempts | PAR2 s ↓ |",
                      "|---|---:|---:|"])
        for mode,x in z["solvers"].items():
            lines.append(f"| {mode} | {x['solved']}/{x['attempts']} | {x['PAR2_s']:.6f} |")
        lines.append("")
    lines+=["## Limitations"]+["- "+x for x in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V139_AUDIT_PASS",json.dumps({"xor":result["xor"]["solvers"],
                                    "fallback":result["fallback"]["solvers"]}),flush=True)
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    s.add_parser("selftest")
    z=s.add_parser("freeze")
    for k in ("xor_manifest","mixed_manifest","out"):z.add_argument("--"+k,required=True)
    for kind in ("runxor","runfallback"):
        z=s.add_parser(kind)
        for k in ("manifest","native","v76","legacy","kissat","out"):z.add_argument("--"+k,required=True)
        if kind=="runxor":z.add_argument("--shard",type=int,required=True)
    z=s.add_parser("audit")
    for k in ("manifest","combined","fallback","out","md"):z.add_argument("--"+k,required=True)
    a=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(a),"runxor":lambda:runxor(a),
     "runfallback":lambda:runfallback(a),"audit":lambda:audit(a)}[a.cmd]()
if __name__=="__main__":main()

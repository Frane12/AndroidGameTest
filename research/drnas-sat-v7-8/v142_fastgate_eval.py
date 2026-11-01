#!/usr/bin/env python3
"""V14.1 adaptive *general* SAT controlled benchmark.

24 heldout SAT/UNSAT synthetic *non-XOR/non-PHP* CNFs and 12 already-locked
genuine SAT Competition 2024 Main Track CNFs. Compare V14.1, original V14.0,
V7.6 and Kissat404 on exactly the same cases with pinned single CPU, 20s cap.
No use of SAT/UNSAT truth in routing, no trained policy, no world-rank claim.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict,Counter
import v134_constructive as old
import v137_fastpath as exact
import v76_v134_matched as v76
import official_shortlong_select as source
import official_2026_mini_sim as mini

P="DRNAS-V142-FASTGATE-24-SYNTHETIC-12-REAL2024-20261101-v1"
ORIGINAL="DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101"
SALT="DRNAS-V141-NEW-NONXOR-3-FAMILIES-20261101-v1"
FAMILIES=("planted3_sat","color3_sat","color3_k4_unsat")
MODES=("V142_FastGate","V141_Adaptive","V76_adaptive_plain","Kissat404")
REPS=2;SYNTH_SHARDS=6;REAL_SHARDS=6;CAP=20.0
mini.CAP=CAP;mini.MEMORY_GIB=3
source.RAW_CAP=96*1024**2;source.CNF_CAP=96*1024**2
source.VARIABLE_CAP=1000000;source.CLAUSE_CAP=4000000

def check(ok,msg):
    if not ok:raise RuntimeError(msg)
def load(x):return json.loads(Path(x).read_text())
def save(x,z):
    p=Path(x);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(z,indent=2,sort_keys=True)+"\n")
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(x):return digest(Path(x).read_bytes())
def seeded(f,i):
    return random.Random(int(digest((SALT+"/"+f+"/"+str(i)).encode()),16))
def synthetic(f,i):
    check(f in FAMILIES and 0<=i<8,"Unknown generated formula")
    r=seeded(f,i);n=0;cs=[];w=None
    if f=="planted3_sat":
        n=(80,110,140,170,200,230,260,290)[i]
        density=(3.3,3.6,3.85,4.1,4.3,4.5,4.6,4.7)[i]
        w={v:bool(r.getrandbits(1)) for v in range(1,n+1)}
        seen=set()
        while len(cs)<round(n*density):
            vs=r.sample(range(1,n+1),3)
            row=[v if r.getrandbits(1) else -v for v in vs]
            if not any(w[abs(l)]==(l>0) for l in row):
                j=r.randrange(3);row[j]=vs[j] if w[vs[j]] else -vs[j]
            clause=tuple(sorted(row,key=abs))
            if clause not in seen:cs.append(clause);seen.add(clause)
    else:
        vertices=(20,30,40,50,60,70,80,90)[i]
        if f=="color3_k4_unsat":vertices+=4
        n=vertices*3
        if f=="color3_sat":
            colors=[r.randrange(3) for _ in range(vertices)]
        else:
            colors=[j%3 for j in range(vertices)]
        w={3*v+j+1:(colors[v]==j) for v in range(vertices) for j in range(3)}
        for v in range(vertices):
            b=3*v+1;cs.append((b,b+1,b+2))
            for j in range(3):
                for k in range(j+1,3):cs.append((-(b+j),-(b+k)))
        edges=set()
        if f=="color3_k4_unsat":
            for u in range(4):
                for v in range(u+1,4):edges.add((u,v)) # K4 needs four colors
        for u in range(vertices):
            for v in range(u+1,vertices):
                if (u,v) in edges:continue
                if colors[u]!=colors[v] and r.random()<4.0/vertices:
                    edges.add((u,v))
        for u,v in sorted(edges):
            for j in range(3):cs.append((-(3*u+j+1),-(3*v+j+1)))
    r.shuffle(cs)
    label="UNSAT" if f=="color3_k4_unsat" else "SAT"
    if label=="SAT":check(old.valid(cs,w),"SAT witness invalid")
    else:check(all((u,v) in edges for u in range(4) for v in range(u+1,4)),
               "K4 UNSAT obstruction absent")
    raw=old.dimacs(n,cs)
    info={"id":f"v141/{f}/{i}","index":i,"family":f,
          "sha256":digest(raw),"official_label":label,"source":"synthetic",
          "variables":n,"clauses":len(cs),
          "proof":{"kind":"3-coloring-K4-impossible" if label=="UNSAT" else "explicit_sat_witness"}}
    return info,raw
def selftest():
    candidates=[synthetic(f,i)[0] for f in FAMILIES for i in range(8)]
    check(len(candidates)==24 and len({x["sha256"] for x in candidates})==24,
          "Invalid fresh synthetic cases")
    for f in FAMILIES:
        for i in range(8):
            meta,raw=synthetic(f,i)
            check(synthetic(f,i)==(meta,raw),"Generator nondeterminism")
            try:z=exact.decide(raw)
            except ValueError:continue
            check(z["status"]=="FALLBACK","Known general non-XOR class misdetected")
    print("V141_NEW_SYNTHETIC_SELFTEST_PASS 24 non-XOR formulas",flush=True)
def freeze(a):
    selftest()
    prior=load(a.prior)
    check(prior["protocol"]=="DRNAS-V141-ADAPTIVE-GENERAL-24-NEW-12-REAL2024-20261101-v1",
          "Wrong V14.1 old manifest")
    check(len(prior["synthetic"])==24 and len(prior["real"])==12,
          "Prior formula counts drift")
    check(prior["synthetic"]==[synthetic(f,i)[0] for f in FAMILIES for i in range(8)],
          "Synthetic CNF SHA changed between V14.1 and V14.2")
    check(len({x["sha256"] for x in prior["real"]})==12,
          "Duplicate official real CNF")
    prior["protocol"]=P
    prior["modes"]=list(MODES)
    prior["prior_v141_manifest_sha256"]=sha(a.prior)
    prior["decision_policy"]="Fast native exact full XOR/PHP proof when promising, otherwise immediately exec pinned Kissat. No V7.6 probe."
    prior["limitations"].append("EXACT same 36 input CNF SHA values as V14.1, known comparison/regression sample, not fresh holdout.")
    prior["limitations"].append("V14.2 does not incorporate local mixed-CNF XOR learning; that is a separate certified research branch V13.14.")
    save(a.out,prior)
    print("V142_FREEZE_PASS original 24+12 SHA-pinned",sha(a.out),flush=True)
def memory():mini.memory_limit()
def native(mode,cnf,seed,truth,a):
    if mode=="V142_FastGate":
        cmd=[str(Path(a.v142).resolve()),str(Path(cnf).resolve()),
             str(Path(a.kissat).resolve()),str(seed)]
    else:
        cmd=[str(Path(a.v141).resolve()),str(Path(cnf).resolve()),
             str(Path(a.v140).resolve()),str(Path(a.v76).resolve()),
             str(Path(a.kissat).resolve()),str(seed)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         timeout=CAP,preexec_fn=memory)
        sec=time.monotonic()-start
        lines=p.stdout.splitlines();path=""
        exacts=[x for x in lines if x.startswith("DRNAS_HYBRID_RESULT\t")]
        quick=[x for x in lines if x.startswith("DRNAS_GENERAL_RESULT\t")]
        v76s=[x for x in lines if x.startswith("DRNAS_RESULT\t")]
        if len(exacts)==1:
            z=json.loads(exacts[0].split("\t",1)[1])
            check(p.returncode==0 and z["status"]==truth and z["verified"],
                  "Wrong exact proof")
            n,clauses=exact.read_dimacs(cnf.read_bytes())
            check(exact.verify(n,clauses,z),"Independent exact verifier failed")
            path=z["path"];status=z["status"]
        elif len(quick)==1:
            z=json.loads(quick[0].split("\t",1)[1])
            status=z["status"];path=z["path"]
            check(p.returncode==0 and path=="v76_quick","Wrong V76 quick result")
        elif len(v76s)==1:
            fields=v76s[0].split("\t")
            check(fields[1]=="adaptive_plain" and p.returncode==0,"Bad V140 fallback")
            status=fields[2];path="v76_fallback"
        else:
            # V141 direct Kissat runs in same process via execv; exit 10 or 20.
            check(mode in ("V142_FastGate","V141_Adaptive") and p.returncode in (10,20),
                  "No valid solver status: "+str(p.returncode)+" "+p.stderr[-250:])
            status="SAT" if p.returncode==10 else "UNSAT"
            needle="s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE"
            check(needle in p.stdout and
                  any(x.startswith("DRNAS_V142_ROUTE\tkissat_direct" if mode=="V142_FastGate" else "DRNAS_GENERAL_ROUTE\tkissat") for x in lines),
                  "Invalid Kissat fallback output")
            path="kissat_fallback"
        check(status==truth,"Wrong truth label from "+mode+": "+status)
        check(sec<=CAP,"Result past deadline")
        return {"status":status,"seconds":round(sec,6),"path":path,"error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"path":"timeout","error":""}
    except Exception as exc:
        return {"status":"ERROR","seconds":min(CAP,time.monotonic()-start),
                "path":"error","error":str(exc)[:320]}
def trial(mode,cnf,seed,label,a):
    if mode in ("V142_FastGate","V141_Adaptive"):
        return native(mode,cnf,seed,label,a)
    if mode.startswith("V76_"):
        v=v76.trial(mode,cnf,seed,label,a.v76,a.legacy,a.kissat)
    else:v=mini.trial(mode,cnf,seed,a.legacy,a.kissat,label)
    return {"status":v["status"],"seconds":v["seconds"],
            "path":mode,"error":v["error"]}
def run(a,cohort):
    m=load(a.manifest);check(m["protocol"]==P and 0<=a.shard<6,"Protocol drift")
    cases=m["synthetic" if cohort=="synthetic" else "real"][a.shard::6]
    check(len(cases)==4 if cohort=="synthetic" else len(cases)==2,"Wrong shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    meta={"protocol":P,"cohort":cohort,"shard":a.shard,"manifest_sha":sha(a.manifest),
       "ids":[x["id"] for x in cases],
       "binaries":{x:sha(getattr(a,x)) for x in ("v142","v141","v140","v76","legacy","kissat")},
       "cpu":next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
                    if x.startswith("model name")),"unknown")}
    save(root/"meta.json",meta);rows=[]
    for c in cases:
        dest=root/(c["sha256"][:24]+".cnf")
        if cohort=="synthetic":
            actual,raw=synthetic(c["family"],c["index"])
            check(actual==c,"New generated CNF drift")
            dest.write_bytes(raw)
        else:
            got=source.download_and_features(c["id"],dest)
            check(got["sha256"]==c["sha256"] and
                  got["features"]==c["features"],"Real official source drift")
        check(sha(dest)==c["sha256"],"Input SHA mismatch")
        observations=[]
        for rep in range(REPS):
            seed=(1412026+int(c["sha256"][:8],16)+rep*1009)%(2**32)
            modes=list(MODES);random.Random(seed^141).shuffle(modes)
            for mode in modes:
                z=trial(mode,dest,seed,c["official_label"],a)
                check(z["status"] in ("SAT","UNSAT","TIMEOUT"),
                      "Failed trial "+mode+" "+c["id"]+" "+z["error"])
                check(z["status"]=="TIMEOUT" or z["status"]==c["official_label"],
                      "Solver truth mismatch")
                observations.append({"mode":mode,"rep":rep,**z})
                print("V142_TRIAL",cohort,c["id"],mode,rep,z["status"],
                      z["seconds"],z["path"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"label":c["official_label"],
                     "family":c["family"],"cohort":cohort,"trials":observations})
        save(root/"rows.json",rows);dest.unlink()
    print("V142_SHARD_PASS",cohort,a.shard,len(rows),flush=True)
def summarize(rows):
    solved=Counter();times=defaultdict(list);routes=Counter();per={}
    for row in rows:
        pairs={(x["mode"],x["rep"]):x for x in row["trials"]}
        check(len(pairs)==REPS*len(MODES),"Incomplete pairs")
        for mode in MODES:
            for rep in range(REPS):
                x=pairs[mode,rep]
                check(x["status"] in ("SAT","UNSAT","TIMEOUT") and not x["error"],
                      "Invalid trial")
                if x["status"]!="TIMEOUT":check(x["status"]==row["label"],"Wrong truth")
                solved[mode]+=int(x["status"]!="TIMEOUT")
                times[mode].append(2*CAP if x["status"]=="TIMEOUT" else x["seconds"])
                routes[mode+":"+x["path"]]+=1
    return {"formulas":len(rows),
       "solvers":{m:{"solved":solved[m],"total":len(rows)*REPS,
        "PAR2_s":round(statistics.mean(times[m]),6)} for m in MODES},
        "routing":dict(routes)}
def audit(a):
    m=load(a.manifest);check(m["protocol"]==P,"Wrong manifest")
    binaries=set();cpus=set();result={}
    for cohort in ("synthetic","real"):
        cases=m[cohort];rows=[]
        for shard in range(6):
            d=Path(a.combined)/f"v142-{cohort}-{shard}"
            meta=load(d/"meta.json");part=load(d/"rows.json")
            expected=cases[shard::6]
            check(meta["protocol"]==P and meta["cohort"]==cohort and
                  meta["shard"]==shard and meta["manifest_sha"]==sha(a.manifest) and
                  meta["ids"]==[c["id"] for c in expected],"Wrong provenance")
            check([x["id"] for x in part]==meta["ids"],"Incomplete shard")
            binaries.add(json.dumps(meta["binaries"],sort_keys=True))
            cpus.add(meta["cpu"]);rows+=part
        check(len(rows)==len(cases) and len({x["sha256"] for x in rows})==len(rows),
              "Cohort incomplete")
        index={z["id"]:z for z in cases}
        for row in rows:
            c=index[row["id"]]
            check(row["sha256"]==c["sha256"] and
                  row["label"]==c["official_label"],"Result case identity drift")
        result[cohort]=summarize(rows)
        result[cohort+"_rows"]=rows
    check(len(binaries)==1,"Different solver binary versions between shards")
    final={"protocol":P,"manifest_sha":sha(a.manifest),"results":result,
           "binaries":json.loads(next(iter(binaries))),
           "CPUs":sorted(cpus),"limitations":m["limitations"]}
    save(a.out,final)
    lines=["# DRNAS V14.2 - general SAT native FastGate controlled benchmark","",
      "Fresh 24 synthetic non-XOR CNFs; previously frozen twelve actual SAT Competition 2024 CNFs.",
      "20-second cap, 3GiB, pinned CPU, four methods, two runs per CNF.",""]
    for cohort in ("synthetic","real"):
        z=result[cohort]
        lines.extend([f"## {cohort}: {z['formulas']} formulas","",
          "| Solver | Solved | PAR2 ↓ |","|---|---:|---:|"])
        for method,v in z["solvers"].items():
            lines.append(f"| {method} | {v['solved']}/{v['total']} | {v['PAR2_s']:.6f} s |")
        lines.append("")
        lines.append("Routes: "+json.dumps(z["routing"],sort_keys=True))
        lines.append("")
    lines+=["## Methodology and limits"]+["- "+v for v in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("V142_AUDIT_PASS",json.dumps({x:result[x]["solvers"]
                                   for x in ("synthetic","real")}),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    z=sub.add_parser("freeze")
    for k in ("prior","out"):z.add_argument("--"+k,required=True)
    for name in ("synthetic","real"):
        z=sub.add_parser(name)
        for k in ("manifest","v142","v141","v140","v76","legacy","kissat","out"):
            z.add_argument("--"+k,required=True)
        z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for k in ("manifest","combined","out","md"):z.add_argument("--"+k,required=True)
    a=p.parse_args()
    {"selftest":selftest,"freeze":lambda:freeze(a),"synthetic":lambda:run(a,"synthetic"),
     "real":lambda:run(a,"real"),"audit":lambda:audit(a)}[a.cmd]()
if __name__=="__main__":main()

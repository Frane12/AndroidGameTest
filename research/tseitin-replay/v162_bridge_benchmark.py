#!/usr/bin/env python3
"""V16.2 reproducible, frozen-schema comparison. Five solver binaries:
pinned Kissat CLI, same-parser Kissat API, unchanged V15.3, V15.4 and V16.2.
Modes: 160 NEW generated controls / 12 NEW ORIGINAL SC2026 CNF inputs.
No solver receives an expected label, family, class or filename-derived hint.
All SAT models independently checked; DRNAS original-CNF UNSAT certs replayed.
Kissat/API UNSAT trusted on externally verified official labels, not LRAT.
This does NOT constitute an official SAT Competition ranking.
"""
import collections,hashlib,json,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
sys.path.insert(0,"research/drnas-sat-v7-8")
import v155_training as gen
from v153_proof_checker import verify_certificate as check_native
from official_shortlong_select import download_and_features
SEED="DRNAS-V162-UNSEEN-20261101-NEWSEED-B"
REPS=3;CAP=6.
SOLVERS={"kissat_cli":"kissat_solver","kissat_api":"kissat_api_control",
         "v1531":"v1531_nohang","v159":"v159_relational_dispatch","v162":"v162_bridge_solver"}
OFFICIAL_REV="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
SCORES_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
PREVIOUS="prev/v152-frozen.json"
def digest(bytes_):return hashlib.sha256(bytes_).hexdigest()
def save(path,value):
 p=Path(path);p.parent.mkdir(exist_ok=True,parents=True)
 p.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
def parse(path):
 n=0;m=None;cls=[];pending=[]
 for line in Path(path).read_text().splitlines():
  l=line.strip()
  if not l or l.startswith("c"):continue
  if l.startswith("p "):
   x=l.split();assert len(x)==4 and x[1]=="cnf"
   assert not n;n=int(x[2]);m=int(x[3]);continue
  assert n
  for token in l.split():
   v=int(token);assert abs(v)<=n
   if v:pending.append(v)
   else:cls.append(pending);pending=[]
 assert n>0 and not pending and m==len(cls)
 return n,cls
def verify_sat(n,cls,model):
 vals={}
 for lit in model:
  assert type(lit)==int and 1<=abs(lit)<=n
  if abs(lit) in vals:assert vals[abs(lit)]==(lit>0)
  vals[abs(lit)]=(lit>0)
 assert all(any(vals.get(abs(lit))==(lit>0) for lit in cl) for cl in cls)
def run(solver,path):
 binary=Path("bin",SOLVERS[solver]).resolve()
 p=Path(path).resolve()
 cmd=([str(binary),str(p)] if solver in ("kissat_cli","kissat_api")
      else [str(binary),str(p),str(Path("bin/kissat_solver").resolve()),"1"])
 t=time.perf_counter()
 try:proc=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=CAP,path="timeout",payload=None,model=[])
 dt=time.perf_counter()-t
 if dt>CAP:return dict(status="TIMEOUT",seconds=CAP,path="timeout",payload=None,model=[])
 payloads=[l.split("\t",1)[1] for l in proc.stdout.splitlines()
           if l.startswith("DRNAS_HYBRID_RESULT\t")]
 assert len(payloads)<=1
 payload=json.loads(payloads[0]) if payloads else None
 if payload:
  assert proc.returncode==0,(solver,proc.returncode,proc.stderr[-300:])
  status=payload["status"];route=payload["path"]
  model=payload.get("model",[])
 else:
  lines=proc.stdout.splitlines()
  if "s SATISFIABLE" in lines:status="SAT"
  elif "s UNSATISFIABLE" in lines:status="UNSAT"
  else:raise RuntimeError(f"{solver} unknown exit {proc.returncode}: {proc.stdout[-150:]} {proc.stderr[-150:]}")
  assert proc.returncode in (0,10,20),(solver,proc.returncode)
  meta=[z for z in lines if z.startswith("DRNAS_V154_ROUTE\t") or z.startswith("DRNAS_V162_ROUTE\t")]
  route=meta[-1].split("\t")[1] if meta else solver
  model=[int(v) for line in lines if line.startswith("v ") for v in line.split()[1:] if v!="0"]
 return dict(status=status,seconds=round(dt,7),path=route,payload=payload,model=model)
def plan_generated():
 gen.SEED=SEED
 gen.freeze("v162-generated-480")
 frozen=json.loads(Path("v162-generated-480/manifest.json").read_text())
 byfamily=collections.defaultdict(list)
 for x in frozen["samples"]:byfamily[x["family"]].append(x)
 cases=[]
 for family in gen.FAMILIES:
  # Only first eight SAT-balanced seed-index entries, fixed BEFORE runs.
  for x in sorted(byfamily[family],key=lambda x:x["index"])[:8]:
   cases.append({**x,"path":str(Path("v162-generated-480")/x["relative_path"])})
 assert len(cases)==160
 save("v162-generated-160-manifest.json",
   {"seed":SEED,"reps":REPS,"timeout":CAP,"test_type":"synthetic", "cases":cases,
    "limitations":["Generated 20 categories, not third-party or official benchmark",
                   "All 160 chosen before timing, balanced 4 SAT / 4 UNSAT per category"]})
 print("V162_GENERATED_FROZEN",len(cases),len(gen.FAMILIES),flush=True)
 return cases
def plan_official():
 import csv,urllib.request
 url=f"https://raw.githubusercontent.com/satcompetition/2026/{OFFICIAL_REV}/downloads/scores.csv"
 data=urllib.request.urlopen(url,timeout=90).read()
 blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
 assert blob==SCORES_BLOB
 scores=list(csv.DictReader(data.decode().splitlines()))
 assert len([x for x in scores if x["solverid"]=="biere_cadical3[main]"])==400
 prior=json.loads(Path(PREVIOUS).read_text())
 seen={x["id"] for x in prior["source_inputs"]}
 all_=list(x for x in scores if x["solverid"]=="biere_cadical3[main]"
           and x["status"] in ("sat-verified","unsat-verified")
           and 0<=float(x["runtime"])<=180 and x["instanceid"] not in seen)
 all_.sort(key=lambda x:digest((SEED+"/official/"+x["instanceid"]).encode()))
 selected=[];attempts=[]
 for row in all_:
  try:
   info=download_and_features(row["instanceid"])
   if info["cnf_bytes"]>8*1024*1024:raise ValueError("8MiB fixed size")
   label="SAT" if row["status"]=="sat-verified" else "UNSAT"
   selected.append({**info,"id":row["instanceid"],"expected":label,
                    "official_cadical_seconds":float(row["runtime"]),
                    "band":("fast" if float(row["runtime"])<5 else
                            "medium" if float(row["runtime"])<30 else "slow")})
   attempts.append({"id":row["instanceid"],"accepted":True})
   print("V162_OFFICIAL_ACCEPT",label,row["instanceid"],selected[-1]["band"],flush=True)
  except Exception as e:
   attempts.append({"id":row["instanceid"],"accepted":False,"reason":str(e)[:150]})
  if len(selected)==12:break
 assert len(selected)==12
 assert not any(c["id"] in seen for c in selected)
 save("v162-official-12-manifest.json",
   {"rev":OFFICIAL_REV,"score_blob":SCORES_BLOB,
    "selection":"fixed SHA lottery among label-verified original SC2026 with pinned CaDiCaL runtime<=180 and CNF<=8MiB; no DRNAS timings",
    "cases":selected,"attempts":attempts,"timeout":CAP,"reps":2,
    "warnings":["Not official ranking, restricted file sizes and runtime limits",
                "Public official labels known, not a fully blinded dataset",
                "Original UNSAT externally verified via competition status; no LRAT from Kissat"]})
 print("V162_OFFICIAL_FROZEN",len(selected),collections.Counter(x["band"] for x in selected),flush=True)
 return selected
def main():
 mode=sys.argv[1];assert mode in ("generated","official")
 if hasattr(os,"sched_setaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
 cases=plan_generated() if mode=="generated" else plan_official()
 if mode=="official":
  for c in cases:
   path=Path("v162-official-12")/(c["id"]+".cnf")
   path.parent.mkdir(exist_ok=True,parents=True)
   info=download_and_features(c["id"],path)
   assert info["sha256"]==c["sha256"]
   c["path"]=str(path)
 repeats=REPS if mode=="generated" else 2
 rows=[]
 for j,c in enumerate(cases):
  path=c["path"];n,cls=parse(path)
  assert digest(Path(path).read_bytes())==c["sha256"]
  for rep in range(repeats):
   order=list(SOLVERS)
   random.Random(int(digest((SEED+"/"+mode+"/"+c["id"]+"/"+str(rep)).encode())[:12],16)).shuffle(order)
   for solver in order:
    try:
     ans=run(solver,path)
     status=ans["status"]
     assert status in ("TIMEOUT",c["expected"]),(solver,c["id"],status,c["expected"])
     if status=="SAT":
      verify_sat(n,cls,ans["model"]);check="model"
     elif status=="UNSAT" and ans["payload"]:
      assert check_native(ans["payload"],cls),(solver,ans["path"])
      check="native_certificate"
     elif status=="UNSAT":check="generator_or_official_label"
     else:check="timeout"
     item={"case":c["id"],"family":c.get("family","official"),"band":c.get("band",None),
           "solver":solver,"rep":rep,"status":status,
           "seconds":ans["seconds"],"route":ans["path"],"check":check}
    except Exception as e:
     item={"case":c["id"],"solver":solver,"rep":rep,"status":"ERROR",
           "seconds":CAP,"error":str(e)[:400]}
    rows.append(item)
  if j%8==7:
   save(f"v162-{mode}-progress.json",{"complete":False,"rows":rows})
   print("V162_PROGRESS",mode,j+1,len(cases),flush=True)
 assert all(x["status"]!="ERROR" for x in rows),[x for x in rows if x["status"]=="ERROR"][:4]
 scores=collections.defaultdict(list);routes=collections.defaultdict(collections.Counter)
 for row in rows:
  scores[row["solver"],row["case"]].append(CAP*2 if row["status"]=="TIMEOUT" else row["seconds"])
  routes[row["solver"]][row["route"]]+=1
 summary={}
 for solver in SOLVERS:
  s=[r for r in rows if r["solver"]==solver]
  summary[solver]={"solved_attempts":sum(r["status"] in ("SAT","UNSAT") for r in s),
    "attempts":len(s),"par2_sum_s":round(sum(statistics.median(v) for (z,_),v in scores.items() if z==solver),6),
    "routes":dict(routes[solver]),"independently_verified":sum(r["check"] in ("model","native_certificate") for r in s)}
  print("V162_RESULT",mode,solver,json.dumps(summary[solver],sort_keys=True),flush=True)
 save(f"v162-{mode}-results.json",{"mode":mode,"cases":len(cases),"repetitions":repeats,"timeout":CAP,
   "summary":summary,"trials":rows,
   "warnings":["Synthetic vs official must never be aggregated as world records",
               "All native original-CNF proof paths checked by independent v153 checker",
               "No claim of official competition timing or rankings"]})
 print("V162_AUDIT_PASS",mode,len(rows),"cases",len(cases),flush=True)
if __name__=="__main__":main()

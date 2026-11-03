#!/usr/bin/env python3
"""R41 small matched real-official test, flush-based telemetry survives timeout."""
import argparse,hashlib,json,os,random,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_v94_select import download_and_features
CASES=(
 "12cd0c3196589ac8105653cbfe613fc6", # R38 quality-positive, early-resume
 "ee44c3f464238366729bf2cb16eb412a", # hints harmful
 "5de866bc7ff4dfde3cd682b5aca75894", # sparse wins
 "9ef9243ff051b32795890fccd6c3f6b2", # long timeout control
)
MODES=("v91_quality_gate","v91_rescue","v91_force_fallback","v91_never_late")
CAP=10.0
REPS=2
def decode(x):
 if x is None:return ""
 if isinstance(x,bytes):return x.decode("utf-8","replace")
 return str(x)
def trace(log,prefix):
 lines=[x for x in log.splitlines() if x.startswith(prefix+"\t")]
 if len(lines)>1:raise ValueError("multiple "+prefix)
 if not lines:return None
 data={}
 for f in lines[0].split("\t")[1:]:
  if "=" not in f:raise ValueError("malformed "+prefix)
  k,v=f.split("=",1);data[k]=v
 return data
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--index",type=int,required=True)
 p.add_argument("--native",required=True);p.add_argument("--out",required=True)
 a=p.parse_args()
 assert 0<=a.index<4
 man=Path(a.manifest);m=json.loads(man.read_text())
 assert len(m["cases"])==12
 lookup={x["id"]:x for x in m["cases"]}
 id=CASES[a.index]
 assert id in lookup
 item=lookup[id];o=Path(a.out);o.mkdir(parents=True,exist_ok=True)
 cnf=o/(id+".cnf");native=Path(a.native).resolve()
 sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 cores=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cores[0]})
 rows=[]
 try:
  check=download_and_features(id,cnf)
  assert check["sha256"]==item["sha256"],"SHA drift"
  assert check["features"]==item["features"],"input feature drift"
  print("R41_OFFICIAL_SHA_PASS",id,item["sha256"],flush=True)
  for rep in range(REPS):
   seed=(830031+int(item["sha256"][:8],16)+rep*101)%2**32
   modes=list(MODES);random.Random(int(id[:8],16)+rep*41111).shuffle(modes)
   for mode in modes:
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.monotonic();stderr="";stdout="";err="";status=""
    try:
     r=subprocess.run([str(native),mode,str(cnf),str(seed)],
       capture_output=True,text=True,timeout=CAP,check=False)
     sec=time.monotonic()-start;stderr=decode(r.stderr);stdout=decode(r.stdout)
     if r.returncode!=0:raise RuntimeError("Native rc="+str(r.returncode)+" "+stderr[-1000:])
     lines=[line for line in stdout.splitlines() if line.startswith("DRNAS_CAUSAL\t")]
     if len(lines)!=1:raise RuntimeError("missing solver final output")
     d=dict(x.split("=",1) for x in lines[0].split("\t")[1:] if "=" in x)
     if d.get("mode")!=mode:raise RuntimeError("mode drift")
     status=d.get("answer")
     if status!=item["official_label"]:raise RuntimeError("official SAT/UNSAT mismatch: "+str(status))
    except subprocess.TimeoutExpired as ex:
     sec=CAP;stderr=decode(ex.stderr);stdout=decode(ex.stdout);status="TIMEOUT"
    except Exception as ex:
     sec=time.monotonic()-start;status="ERROR";err=str(ex)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
    cp=trace(stderr,"R41_CHECKPOINT")
    action=trace(stderr,"R41_RESUME")
    if cp and cp.get("policy")!=("v91_gate" if mode=="v91_quality_gate" else
           "v91_never" if mode=="v91_never_late" else mode):
     raise RuntimeError("wrong checkpoint policy: "+str(cp))
    row=dict(id=id,label=item["official_label"],sha256=item["sha256"],
      rep=rep,seed=seed,mode=mode,status=status,
      wall_s=round(sec,6),cpu_s=round(cpu,6),cap_s=CAP,checkpoint=cp,
      before_resume=action,error=err)
    rows.append(row)
    print("R41_TRIAL",id[:8],rep,mode,status,row["wall_s"],
      "CP",json.dumps(cp,sort_keys=True) if cp else "not_reached",
      "ACTION",json.dumps(action,sort_keys=True) if action else "not_reached",flush=True)
    if status=="ERROR":raise RuntimeError("Invalid trial "+str(row))
 finally:cnf.unlink(missing_ok=True)
 assert len(rows)==REPS*len(MODES)
 (o/"trials.json").write_text(json.dumps(rows,indent=2)+"\n")
 (o/"meta.json").write_text(json.dumps(dict(id=id,index=a.index,
   original_manifest_sha256=sha(man),bin_sha256=sha(native),
   cpu_core=cores[0],available_cores=cores,cap_s=CAP,reps=REPS,
   modes=MODES,n_trials=len(rows)),indent=2)+"\n")
 print("R41_SHARD_PASS",id,len(rows),"with_checkpoint",sum(r["checkpoint"] is not None for r in rows),flush=True)
if __name__=="__main__":main()

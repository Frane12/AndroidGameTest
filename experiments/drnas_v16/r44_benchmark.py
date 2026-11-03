#!/usr/bin/env python3
"""R44 native controlled prospective 0/16/32 selector on original 2026 CNFs.

Exact frozen 8-case SHA-locked manifest and one pinned binary for all variants.
Two paired seeds/case. Up to 15s per run, same single CPU, randomized orders.
Note GitHub hosted CPU contention and test-file size selection biases.
"""
import argparse,hashlib,json,os,random,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import download_and_features
MODES=("v91_quality_gate","v91_cap32","v91_adaptive","kissat_pinned")
CAP=15.0;REPS=2
FINGERPRINT=("stage1","extended","quality","learned","lbd2","lbd4",
 "props","conflicts","backtracks","hints","learned_delta","threshold")
def decode(x):
 if x is None:return ""
 if isinstance(x,bytes):return x.decode("utf-8","replace")
 return x
def gettrace(s,prefix):
 matches=[line for line in s.splitlines() if line.startswith(prefix+"\t")]
 if len(matches)>1:raise ValueError("Duplicate "+prefix+" records")
 if not matches:return None
 return dict(part.split("=",1) for part in matches[0].split("\t")[1:] if "=" in part)
def expected_dose(cp):
 if not cp or cp["extended"]!="0" or cp["quality"]!="1":return 0
 L=int(cp["learned"]);Q=int(cp["lbd2"]);P=int(cp["props"]);C=int(cp["conflicts"])
 if L<=0 or C<=0:return 0
 if 100*Q<=12*L and P<=384*C:return 32
 if 100*Q<=20*L and P<=512*C:return 16
 return 0
def main():
 a=argparse.ArgumentParser()
 a.add_argument("--manifest",required=True);a.add_argument("--shard",required=True,type=int)
 a.add_argument("--native",required=True);a.add_argument("--kissat",required=True)
 a.add_argument("--out",required=True)
 x=a.parse_args()
 assert 0<=x.shard<4
 mf=Path(x.manifest);m=json.loads(mf.read_text())
 assert m["protocol"]=="R44-FROZEN-QUALITY-DOSE-20261103-V1"
 assert len(m["cases"])==8
 cases=m["cases"][2*x.shard:2*x.shard+2]
 assert len(cases)==2
 out=Path(x.out);out.mkdir(parents=True,exist_ok=True)
 native=Path(x.native).resolve();kissat=Path(x.kissat).resolve()
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 assert native.is_file() and kissat.is_file()
 core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
 meta=dict(protocol=m["protocol"],shard=x.shard,manifest_sha256=sha(mf),
  binary_sha256=dict(native=sha(native),kissat=sha(kissat)),
  modes=MODES,cap_s=CAP,reps=REPS,core=core,
  source_case_ids=[c["id"] for c in cases])
 (out/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
 rows=[]
 for c in cases:
  cid=c["id"];cnf=out/(cid+".cnf")
  try:
   check=download_and_features(cid,cnf)
   assert check["sha256"]==c["sha256"],"CNF original SHA mismatch"
   assert check["features"]==c["features"],"CNF structure mismatch"
   print("R44_INPUT_SHA_PASS",cid,c["official_label"],c["sha256"],flush=True)
   for rep in range(REPS):
    seed=(441144+int(c["sha256"][:8],16)+rep*103)%2**32
    modes=list(MODES);random.Random(440044+int(cid[:8],16)+rep*1009).shuffle(modes)
    sameprefix=[]
    for mode in modes:
     cmd=([str(kissat),str(cnf)] if mode=="kissat_pinned" else
          [str(native),mode,str(cnf),str(seed)])
     before=resource.getrusage(resource.RUSAGE_CHILDREN)
     start=time.monotonic();outlog="";errlog="";err="";final=None
     try:
      p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP,check=False)
      elapsed=time.monotonic()-start;outlog=decode(p.stdout);errlog=decode(p.stderr)
      if mode=="kissat_pinned":
       if p.returncode not in (10,20):raise ValueError("Bad Kissat exit "+str(p.returncode))
       status="SAT" if p.returncode==10 else "UNSAT"
       if not any(line.strip()==("s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE")
           for line in outlog.splitlines()):raise ValueError("Kissat result marker missing")
      else:
       if p.returncode!=0:raise ValueError("Native rc "+str(p.returncode)+" "+errlog[-450:])
       matches=[z for z in outlog.splitlines() if z.startswith("DRNAS_CAUSAL\t")]
       if len(matches)!=1:raise ValueError("Missing unique native answer")
       final=dict(q.split("=",1) for q in matches[0].split("\t")[1:] if "=" in q)
       if final.get("mode")!=mode:raise ValueError("mode mismatch")
       status=final.get("answer")
      if status!=c["official_label"]:raise ValueError("SAT/UNSAT official mismatch "+str(status))
     except subprocess.TimeoutExpired as ex:
      status="TIMEOUT";elapsed=CAP;outlog=decode(ex.stdout);errlog=decode(ex.stderr)
     except Exception as ex:
      status="ERROR";elapsed=time.monotonic()-start;err=str(ex)
     after=resource.getrusage(resource.RUSAGE_CHILDREN)
     cpu=max(0,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
     if status=="ERROR":raise RuntimeError(f"R44 failed case {cid} mode {mode}: {err}")
     cp=None if mode=="kissat_pinned" else gettrace(errlog,"R41_CHECKPOINT")
     act=None if mode=="kissat_pinned" else gettrace(errlog,"R41_RESUME")
     if mode!="kissat_pinned":
      if cp:
       assert cp["policy"]==("v91_gate" if mode=="v91_quality_gate" else "v91_rescue")
       assert cp["stage1"]=="0"
       L=int(cp["learned"]);Q=int(cp["lbd2"]);P=int(cp["props"]);C=int(cp["conflicts"])
       expected_quality=(L>=20 and C>0 and 100*Q>=6*L and P>=32*C)
       assert int(cp["quality"])==int(expected_quality)
       sameprefix.append(tuple(cp[k] for k in FINGERPRINT))
      if act:
       assert cp is not None and act["quality"]==cp["quality"] and act["extended"]==cp["extended"]
       actual=int(act.get("actual_hints","0"))
       if mode=="v91_adaptive":
        assert actual==min(expected_dose(cp),int(cp["hints"])),("native adaptive dose drift",cid,actual,cp,act)
       elif mode=="v91_cap32":
        target=(32 if cp["extended"]=="0" and cp["quality"]=="1" else 0)
        assert actual==min(target,int(cp["hints"])),("native cap32 drift",cid,actual,cp,act)
       else:
        assert actual==0
       assert (act["phase_applied"]=="1" and cp["extended"]=="0")==(actual>0)
     r=dict(id=cid,official_label=c["official_label"],sha256=c["sha256"],
      rep=rep,seed=seed,mode=mode,status=status,
      wall_s=round(elapsed,6),cpu_s=round(cpu,6),
      PAR2_s=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
      error=err,checkpoint=cp,before_resume=act,
      actual_early_hints=int(act.get("actual_hints","0")) if act else 0)
     rows.append(r)
     print("R44_NATIVE",cid[:8],"rep",rep,mode,status,r["wall_s"],
       "checkpoint",("yes" if cp else "no"),
       "dose",r["actual_early_hints"],flush=True)
    if len(sameprefix)==3:assert len(set(sameprefix))==1,("R44_PREFIX_DIFFERENT",cid,rep)
    print("R44_PAIRED_CASE",cid[:8],rep,"checkpointed",len(sameprefix),flush=True)
  finally:
   cnf.unlink(missing_ok=True)
 assert len(rows)==2*REPS*len(MODES)
 (out/"trials.json").write_text(json.dumps(rows,indent=2)+"\n")
 print("R44_SHARD_PASS",x.shard,len(rows),flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""R43 prospective dose sweep on 4 previously tested external official CNFs
plus the original R42 anchor case. 5 CNFs * 4 modes * 2 paired seeds = 40
native trials. R42 cap+checkpoint implementation, no changed learning logic.
All cases selected prior to R43 outcomes; this is NOT a blind holdout.
"""
import argparse,hashlib,json,os,random,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_v94_select import download_and_features
CASES=(
 "12cd0c3196589ac8105653cbfe613fc6", # R42 anchor, positive gate
 "ee44c3f464238366729bf2cb16eb412a", # R38 measured harmful hints
 "5de866bc7ff4dfde3cd682b5aca75894", # R38 measured sparse advantage
 "0c9da400944b002f90fd385d4fdab385", # R38 near tie
 "9ef9243ff051b32795890fccd6c3f6b2", # R41 positive gate, previous timeout
)
MODES=("v91_quality_gate","v91_cap16","v91_cap32","v91_cap64")
CAP=10.0
REPS=2
PREFIX_KEYS=("stage1","extended","quality","learned","lbd2","lbd4",
             "props","conflicts","backtracks","hints","learned_delta","threshold")
def decode(x):
 if x is None:return ""
 return x.decode("utf-8","replace") if isinstance(x,bytes) else x
def trace(log,prefix):
 matches=[x for x in log.splitlines() if x.startswith(prefix+"\t")]
 if len(matches)!=1:raise RuntimeError(f"R43 expected one {prefix} marker, got {len(matches)}")
 return dict(part.split("=",1) for part in matches[0].split("\t")[1:] if "=" in part)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--index",type=int,required=True)
 p.add_argument("--native",required=True);p.add_argument("--out",required=True)
 a=p.parse_args()
 assert 0<=a.index<len(CASES)
 mf=Path(a.manifest);manifest=json.loads(mf.read_text())
 assert len(manifest["cases"])==12
 byid={c["id"]:c for c in manifest["cases"]}
 cid=CASES[a.index];assert cid in byid
 c=byid[cid];o=Path(a.out);o.mkdir(parents=True,exist_ok=True)
 sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
 cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
 exe=Path(a.native).resolve();assert exe.is_file()
 cnf=o/"input.cnf";rows=[]
 try:
  check=download_and_features(cid,cnf)
  assert check["sha256"]==c["sha256"],"CNF SHA drift"
  assert check["features"]==c["features"],"CNF features drift"
  print("R43_OFFICIAL_SHA_VERIFIED",cid,c["official_label"],c["sha256"],flush=True)
  for rep in range(REPS):
   seed=(830031+int(c["sha256"][:8],16)+rep*101)%2**32
   order=list(MODES);random.Random(434300+int(cid[:8],16)+rep*871).shuffle(order)
   group=[]
   for mode in order:
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    began=time.monotonic();stdout="";stderr="";err=""
    try:
     proc=subprocess.run([str(exe),mode,str(cnf),str(seed)],
       capture_output=True,text=True,timeout=CAP,check=False)
     wall=time.monotonic()-began;stdout=decode(proc.stdout);stderr=decode(proc.stderr)
     if proc.returncode!=0:
      raise RuntimeError(f"native rc {proc.returncode}; {stderr[-600:]}")
     final=[s for s in stdout.splitlines() if s.startswith("DRNAS_CAUSAL\t")]
     if len(final)!=1:raise RuntimeError("missing or duplicate final answer line")
     v=dict(part.split("=",1) for part in final[0].split("\t")[1:] if "=" in part)
     assert v.get("mode")==mode,"mode mismatch"
     status=v["answer"]
     if status!=c["official_label"]:raise RuntimeError("SAT answer mismatch")
    except subprocess.TimeoutExpired as ex:
     wall=CAP;status="TIMEOUT";stdout=decode(ex.stdout);stderr=decode(ex.stderr)
    except Exception as ex:
     wall=time.monotonic()-began;status="ERROR";err=str(ex)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds=max(0,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
    if status=="ERROR":raise RuntimeError(f"R43 native execution failed: {mode} {err}")
    cp=trace(stderr,"R41_CHECKPOINT")
    act=trace(stderr,"R41_RESUME")
    assert cp["policy"]==act["policy"]==("v91_gate" if mode=="v91_quality_gate" else "v91_rescue")
    assert cp["stage1"]=="0", "Expected 256-conflict boundary before solve"
    assert act["quality"]==cp["quality"] and act["extended"]==cp["extended"]
    candidates=int(cp["hints"])
    target=0 if mode=="v91_quality_gate" else int(mode.removeprefix("v91_cap"))
    should_activate=(mode!="v91_quality_gate" and cp["quality"]=="1" and cp["extended"]=="0")
    n=int(act["actual_hints"])
    expected=min(target,candidates) if should_activate else 0
    assert n==expected,("incorrect native dose",mode,cid,n,expected,act)
    assert (act["phase_applied"]=="1")==(n>0)
    rec=dict(case_id=cid,official_label=c["official_label"],sha256=c["sha256"],
      rep=rep,seed=seed,mode=mode,status=status,
      wall_s=round(wall,6),cpu_s=round(cpu_seconds,6),
      PAR2_s=round(wall,6) if status!="TIMEOUT" else 2*CAP,
      cap_s=CAP,checkpoint=cp,action=act,actual_hints=n)
    rows.append(rec);group.append(rec)
    print("R43_TRIAL",json.dumps({k:rec[k] for k in ("case_id","rep","mode","status","wall_s","actual_hints")},sort_keys=True),flush=True)
   assert set(r["mode"] for r in group)==set(MODES)
   beforestates={tuple(r["checkpoint"].get(k) for k in PREFIX_KEYS) for r in group}
   assert len(beforestates)==1,("not identical 256 conflict prefix",cid,rep)
   print("R43_PREFIX_IDENTICAL",cid[:8],rep,"quality",group[0]["checkpoint"]["quality"],
         "extension",group[0]["checkpoint"]["extended"],flush=True)
 finally:cnf.unlink(missing_ok=True)
 assert len(rows)==REPS*len(MODES)
 (o/"trials.json").write_text(json.dumps(rows,indent=2)+"\n")
 (o/"meta.json").write_text(json.dumps(dict(
    protocol="R43_SMALL_DOSE_TRANSFER_PRESELECTED",
    index=a.index,case_id=cid,manifest_sha256=sha(mf),native_sha256=sha(exe),
    pinned_core=cpu,cap_s=CAP,reps=REPS,modes=MODES,
    n_trials=len(rows)),indent=2)+"\n")
 print("R43_SHARD_PASS",cid[:8],len(rows),"actual_hint_total",sum(x["actual_hints"] for x in rows),flush=True)
if __name__=="__main__":main()

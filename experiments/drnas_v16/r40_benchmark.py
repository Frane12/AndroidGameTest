#!/usr/bin/env python3
"""R40 native paired test on frozen additional SAT Competition 2026 formulas.

Four SAME-BINARY CaDiCaL policies + pinned untouched Kissat. 2 paired seeds;
all modes use identical CNF, SHA, CPU pin, cap 12s. No tuning mid-test.
No old R37/R38 CNFs rerun. SAT witnesses for CaDiCaL internally checked.
"""
import argparse,csv,hashlib,json,os,random,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import download_and_features
MODES=("v91_quality_gate","v91_rescue","v91_force_fallback","v91_never_late","kissat_pinned")
CAP=12.0
REPS=2
FIELDS=("id","sha256","official_label","cap_s","rep","seed","mode","status","wall_s","cpu_s","error",
"stage1","extended","v91_phase_applied","gate_reason","hints",
"v90_learned_256","v90_lbd2_256","v90_lbd4_256","v90_props_256",
"v90_conflicts_256","v90_backtracks_256","v90_jumpdepth_256","cpu_256_ns")
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--shard",type=int,required=True)
 p.add_argument("--probe",required=True);p.add_argument("--kissat",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 assert 0<=a.shard<4
 mpath=Path(a.manifest);m=json.loads(mpath.read_text())
 assert m["protocol"]=="R40-EARLY-RESCUE-UNSEEN-20261103-v1" and len(m["cases"])==8
 cohort=m["cases"][a.shard*2:(a.shard+1)*2]
 assert len(cohort)==2
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
 probe=Path(a.probe).resolve();kissat=Path(a.kissat).resolve()
 sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
 bin_sha={"probe":sha(probe),"kissat":sha(kissat)}
 (out/"meta.json").write_text(json.dumps({"shard":a.shard,"core":core,
  "cpu":Path("/proc/cpuinfo").read_text()[:2000],
  "manifest_sha256":sha(mpath),"binaries_sha256":bin_sha,
  "cap_s":CAP,"repetitions":REPS,"modes":MODES},indent=2)+"\n")
 rows=[]
 with (out/"raw.csv").open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
  for c in cohort:
   cid=c["id"];dest=out/(cid+".cnf")
   try:
    check=download_and_features(cid,dest)
    assert check["sha256"]==c["sha256"],"SAT input SHA drift"
    assert check["features"]==c["features"],"SAT input feature drift"
    print("R40_VERIFIED_FORMULA",cid,c["official_label"],c["sha256"],flush=True)
    for rep in range(REPS):
     seed=(920401+int(c["sha256"][:8],16)+rep*101)%2**32
     order=list(MODES);random.Random(int(cid[:8],16)+40001+rep*917).shuffle(order)
     for mode in order:
      cmd=([str(kissat),str(dest)] if mode=="kissat_pinned" else
           [str(probe),mode,str(dest),str(seed)])
      before=resource.getrusage(resource.RUSAGE_CHILDREN)
      started=time.monotonic()
      attrs={};err=""
      try:
       p=subprocess.run(cmd,capture_output=True,text=True,
          timeout=CAP,check=False)
       sec=time.monotonic()-started
       if mode=="kissat_pinned":
        if p.returncode not in (10,20):
         raise ValueError("Kissat exit="+str(p.returncode)+" stderr="+p.stderr[-300:])
        status="SAT" if p.returncode==10 else "UNSAT"
        if not any(line.strip()==("s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE")
         for line in p.stdout.splitlines()):
         raise ValueError("Kissat official answer marker missing")
       else:
        if p.returncode!=0:raise ValueError("probe exit="+str(p.returncode)+" stderr="+p.stderr[-300:])
        lines=[x for x in p.stdout.splitlines() if x.startswith("DRNAS_CAUSAL\t")]
        if len(lines)!=1:raise ValueError("Missing or duplicate diagnostic record")
        attrs=dict(part.split("=",1) for part in lines[0].split("\t")[1:] if "=" in part)
        if attrs.get("mode")!=mode:raise ValueError("Native probe mode mismatch")
        status=attrs["answer"]
       if status!=c["official_label"]:
        raise ValueError("Official SAT/UNSAT contradiction "+status)
      except subprocess.TimeoutExpired:
       status="TIMEOUT";sec=CAP
      except Exception as exc:
       status="ERROR";sec=time.monotonic()-started;err=str(exc)
      after=resource.getrusage(resource.RUSAGE_CHILDREN)
      cpu=max(0,after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)
      row={key:attrs.get(key,"") for key in FIELDS}
      row.update(id=cid,sha256=c["sha256"],official_label=c["official_label"],cap_s=CAP,
        rep=rep,seed=seed,mode=mode,status=status,wall_s=round(sec,6),
        cpu_s=round(cpu,6),error=err)
      rows.append(row);writer.writerow(row);f.flush()
      print("R40_NATIVE",cid[:8],"rep",rep,mode,status,row["wall_s"],
        "action",attrs.get("v91_phase_applied","?"),
        "reason",attrs.get("gate_reason",""),flush=True)
      if status=="ERROR":raise RuntimeError(f"R40 invalid trial {cid} {mode}: {err}")
   finally:
    dest.unlink(missing_ok=True)
 assert len(rows)==len(cohort)*REPS*len(MODES)
 (out/"summary.json").write_text(json.dumps({"shard":a.shard,"total_trials":len(rows),
  "timeouts":sum(r["status"]=="TIMEOUT" for r in rows)},indent=2)+"\n")
 print("R40_SHARD_PASS",a.shard,len(rows),flush=True)
if __name__=="__main__":main()

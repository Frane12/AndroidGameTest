#!/usr/bin/env python3
"""R42 single preselected official UNSAT CNF, 10 real paired executions total.

Controls:
  v91_quality_gate: old no-new-action decision
  v91_cap32/128/512: EXACT v9.1 gate; at 256-conflict early resume
                         apply only first N precomputed hint candidates
  v91_rescue: old R40 full-dose rescue (known regression)
Two deterministic paired seeds, 10 second cap. This is retrospective
mechanistic dose-response, NOT a new blind benchmark/record claim.
"""
import argparse,hashlib,json,os,random,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_v94_select import download_and_features
CID="12cd0c3196589ac8105653cbfe613fc6"
MODES=("v91_quality_gate","v91_cap32","v91_cap128","v91_cap512","v91_rescue")
CAP=10.0
REPS=2
PREFIX_FIELDS=("stage1","extended","quality","learned","lbd2","lbd4",
               "props","conflicts","backtracks","hints","learned_delta","threshold")
def decode(x):
 if x is None:return ""
 if isinstance(x,bytes):return x.decode("utf-8","replace")
 return x
def gettrace(log,head):
 items=[x for x in log.splitlines() if x.startswith(head+"\t")]
 if len(items)!=1:raise RuntimeError("Missing/duplicate "+head+" "+str(len(items)))
 return dict(q.split("=",1) for q in items[0].split("\t")[1:] if "=" in q)
def run(manifest,native,out):
 m=json.loads(manifest.read_text());cohort={c["id"]:c for c in m["cases"]}
 assert len(cohort)==12 and CID in cohort
 item=cohort[CID];assert item["official_label"]=="UNSAT"
 out.mkdir(parents=True,exist_ok=True)
 cnf=out/"original.cnf"
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 exe=native.resolve();assert exe.is_file()
 core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
 rows=[]
 try:
  check=download_and_features(CID,cnf)
  assert check["sha256"]==item["sha256"] and check["features"]==item["features"],"CNF fingerprint drift"
  print("R42_FORMULA_SHA_VERIFIED",CID,item["sha256"],flush=True)
  for rep in range(REPS):
   seed=(830031+int(item["sha256"][:8],16)+rep*101)%2**32
   order=list(MODES);random.Random(424201+rep*1021).shuffle(order)
   current={}
   for mode in order:
    start=time.monotonic()
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    stderr="";stdout="";error=""
    try:
     p=subprocess.run([str(exe),mode,str(cnf),str(seed)],
       capture_output=True,text=True,timeout=CAP,check=False)
     wall=time.monotonic()-start
     stderr=decode(p.stderr);stdout=decode(p.stdout)
     if p.returncode!=0:
      raise RuntimeError(f"solver rc {p.returncode}, tail stderr {stderr[-500:]}")
     final=[x for x in stdout.splitlines() if x.startswith("DRNAS_CAUSAL\t")]
     if len(final)!=1:raise RuntimeError("missing DRNAS_CAUSAL final")
     status=dict(part.split("=",1) for part in final[0].split("\t")[1:] if "=" in part).get("answer")
     if status!="UNSAT":raise RuntimeError("SAT/UNSAT mismatched published label "+str(status))
    except subprocess.TimeoutExpired as ex:
     status="TIMEOUT";wall=CAP;stderr=decode(ex.stderr);stdout=decode(ex.stdout)
    except Exception as ex:
     status="ERROR";wall=time.monotonic()-start;error=str(ex)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=max(0,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
    if status=="ERROR":raise RuntimeError(f"Invalid native {mode}: {error}")
    cp=gettrace(stderr,"R41_CHECKPOINT")
    action=gettrace(stderr,"R41_RESUME")
    expectedpolicy="v91_gate" if mode=="v91_quality_gate" else "v91_rescue"
    assert cp["policy"]==action["policy"]==expectedpolicy
    assert cp["stage1"]=="0" and cp["extended"]=="0" and cp["quality"]=="1"
    assert action["extended"]==cp["extended"] and action["quality"]==cp["quality"]
    actual=int(action["actual_hints"]);candidates=int(cp["hints"])
    target=0 if mode=="v91_quality_gate" else (candidates if mode=="v91_rescue" else int(mode.removeprefix("v91_cap")))
    assert actual==min(target,candidates),(mode,actual,target,candidates)
    assert (action["phase_applied"]=="1")==(actual>0)
    row=dict(id=CID,sha256=item["sha256"],rep=rep,seed=seed,
             mode=mode,status=status,PAR2_s=round(wall,6) if status!="TIMEOUT" else 2*CAP,
             wall_s=round(wall,6),cpu_s=round(cpu,6),cap_s=CAP,
             checkpoint=cp,action=action,actual_hints=actual)
    rows.append(row);current[mode]=row
    print("R42_TRIAL",json.dumps({key:row[key] for key in
       ("rep","mode","status","wall_s","PAR2_s","actual_hints")},sort_keys=True),flush=True)
   assert set(current)==set(MODES)
   prefix={tuple(current[mode]["checkpoint"][k] for k in PREFIX_FIELDS) for mode in MODES}
   assert len(prefix)==1,"R42 early-search divergence"
   print("R42_PAIRED_PREFIX_PASS",rep,"checkpoint=256_conflict",flush=True)
 finally:
  cnf.unlink(missing_ok=True)
 assert len(rows)==10
 by_mode={}
 for mode in MODES:
  subset=[r for r in rows if r["mode"]==mode]
  by_mode[mode]={"n":len(subset),"solved":sum(r["status"]=="UNSAT" for r in subset),
   "timeouts":sum(r["status"]=="TIMEOUT" for r in subset),
   "mean_PAR2_s":round(sum(r["PAR2_s"] for r in subset)/len(subset),6),
   "wall_s":[r["wall_s"] for r in subset],
   "actual_hints":[r["actual_hints"] for r in subset]}
 baseline=by_mode["v91_quality_gate"]["mean_PAR2_s"]
 delta={mode:round(100*(by_mode[mode]["mean_PAR2_s"]/baseline-1),3) for mode in MODES}
 report={"protocol":"R42_ONE_FORMULA_CAUSAL_HINT_DOSE",
  "official_formula":CID,"sha256":item["sha256"],"official_label":item["official_label"],
  "manifest_sha256":sha(manifest),"native_sha256":sha(exe),"cpu_core":core,
  "cap_s":CAP,"n_formulas":1,"repetitions":REPS,"native_attempts":len(rows),
  "checkpoint_prefix_equal_by_rep":REPS,"modes":by_mode,"change_vs_nohint_control_pct":delta,
  "raw":rows,"limitations":["One previously observed formula, not a holdout",
    "Two deterministic paired attempts, no reliable confidence interval",
    "Timeouts are PAR2 20s, not measured solve time",
    "Tests dose of R40 early-resume hints, not effect on all SAT formulas",
    "UNSAT is cross-checked with published official label, no independent DRAT/LRAT proof"]}
 (out/"r42-results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R42_AUDIT_PASS",json.dumps({key:report[key] for key in
   ("n_formulas","native_attempts","checkpoint_prefix_equal_by_rep",
    "change_vs_nohint_control_pct")},sort_keys=True),flush=True)
 print("R42_MODE_SUMMARY",json.dumps(by_mode,sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--manifest",required=True)
 p.add_argument("--native",required=True);p.add_argument("--out",required=True)
 a=p.parse_args();run(Path(a.manifest),Path(a.native),Path(a.out))

#!/usr/bin/env python3
"""C1: preregistered source-locked CDCL gap forensic, no algorithm modifications."""
import collections, hashlib, json, os, pathlib, re, subprocess, sys, time
sys.path.insert(0,"research")
import mre11b_prospective_benchmark as bench
import mre11b_prospective_freeze as freeze
OUT=pathlib.Path("c1_out")
IDS=("a9c0f64594a3eaede246b31eb3bc839b","5ac44f542fd2cd4492067deb7791629a","028d0cc7af63e9bba5795f20e24db4f6","220bb8aa093e502c47afcdac3140d67c","01d142c43f3ce9a8c5ef7a1ecdbb6cba")
MODES=("cadical","cpp_native","cpp_clean","cpp_joint")
CAP=35
def need(v,msg):
 if not v:raise RuntimeError("C1_FAIL_CLOSED "+msg)
def main():
 m=freeze.verify(); cases={x["gbd"]:x for x in m["source_cases"]}
 need(all(x in cases for x in IDS),"missing frozen SHA case")
 OUT.mkdir(exist_ok=True)
 rows=[]
 for gbd in IDS:
  c=cases[gbd];source=freeze.ROOT/c["filename"]
  need(hashlib.sha256(source.read_bytes()).hexdigest()==c["sha256"],"source SHA drift")
  for rep in range(2):
   for mode in MODES:
    x=bench.trial(c,rep,mode,"mre10/bin/native","built/bin/kissat_4_0_4","/usr/bin/cadical")
    need(x["source_sha256"]==c["sha256"],"trial SHA mismatch")
    x["c1_protocol"]="C1-5FROZEN-SHA-4ARM-2REP-35S-CAUSAL-GAP-v1"
    x["c1_selected_before_run"]=True
    rows.append(x);print("C1_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
 # The external CaDiCaL binary emits detailed solver counters when its verbose option is used.
 # Instrument it separately; never substitute this diagnostic timing for paired PAR2.
 diagnostics=[]
 for gbd in IDS:
  c=cases[gbd];source=freeze.ROOT/c["filename"]
  cmd=["/usr/bin/cadical","-v",str(source.resolve())]
  start=time.perf_counter()
  try:
   p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=CAP,check=False)
   stdout=p.stdout;returncode=p.returncode;status="COMPLETE"
  except subprocess.TimeoutExpired as e:
   stdout=(e.stdout or b"").decode(errors="replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
   returncode=None;status="TIMEOUT"
  elapsed=time.perf_counter()-start
  # Preserve all reported CaDiCaL c-lines for independent analysis, without parsing undocumented labels.
  lines=[s for s in stdout.splitlines() if s.startswith("c ")]
  item=dict(gbd=gbd,source_sha256=c["sha256"],status=status,returncode=returncode,
            wall_s=round(elapsed,6),cadical_statistics_lines=lines[-220:])
  diagnostics.append(item)
  print("C1_CADICAL_DIAGNOSTIC",json.dumps(item,sort_keys=True),flush=True)
 (OUT/"cadical_diagnostics.json").write_text(json.dumps(diagnostics,indent=2,sort_keys=True)+"\n")
 need(len(rows)==40 and len({(x["source_sha256"],x["rep"],x["mode"]) for x in rows})==40,"incomplete paired set")
 by=collections.defaultdict(list)
 for x in rows:
  need(x["status"]!="SAT" or x["model_original_verified"],"unverified SAT")
  by[x["mode"]].append(x)
 scores={k:dict(solved=sum(x["status"] in ("SAT","UNSAT") for x in v),
  SAT=sum(x["status"]=="SAT" for x in v),UNSAT=sum(x["status"]=="UNSAT" for x in v),
  timeouts=sum(x["status"]=="TIMEOUT" for x in v),
  par2_s=round(sum(x["par2_s"] for x in v),6)) for k,v in by.items()}
 for gbd in IDS:
  statuses={x["status"] for x in rows if x["gbd"]==gbd and x["status"]!="TIMEOUT"}
  need(len(statuses)<=1,"SAT UNSAT contradiction")
 report=dict(protocol="C1-5FROZEN-SHA-4ARM-2REP-35S-CAUSAL-GAP-v1",
   cohort="preselected development forensic, NOT blind holdout",cases=5,trials=40,
   cap_s=CAP,original_sha=[cases[k]["sha256"] for k in IDS],
   independent_unsat_LRAT=False,external_seed_independence=False,
   cadical_verbose_diagnostics_not_PAR2=True,scores=scores)
 (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
 print("C1_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()

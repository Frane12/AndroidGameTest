#!/usr/bin/env python3
"""R153 same-13 SATCompetition2026 real field rematch; NOT a blind holdout.

Same-runner paired competitors: R153, frozen R28, Kissat4.0.4, CaDiCaL3.0.1,
CryptoMiniSat Ubuntu pinned, and genuine official submitted SC2026 Biere/Kissat.
ALL official Main 2026 solver IDs appear in separate published-score comparison
when score rows are available (different hardware, not same-runner).
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,importlib.util,json,math,os,pathlib,random,statistics,subprocess,sys,time
from collections import defaultdict
ROOT=pathlib.Path("r153field")
PROTO="R153-ALL-COMPETITORS-FROZEN-13-SATCOMP26-20261105-v1"
CAP=20.0;REPS=2;SHARDS=4
MODES=("r153","r28","kissat","cadical","cryptominisat","official_sc2024")
BINARIES={"r153":ROOT/"r153","r28":ROOT/"r28",
 "kissat":pathlib.Path("built/bin/kissat_4_0_4"),
 "cadical":pathlib.Path("built/bin/cadical_3_0_1"),
 "cryptominisat":pathlib.Path("/usr/bin/cryptominisat5"),
 "official_sc2024":ROOT/"sc2024-kissat"}
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r153_unit_bridge_benchmark as base
import r115_world_top_rematch as hist
base.ROOT=ROOT
base.CAP=CAP
base.SHARDS=SHARDS
base.BINARIES=BINARIES

def need(ok,msg):
 if not ok:raise RuntimeError("R153_WORLD_FIELD_FAIL_CLOSED "+str(msg))
def sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open("rb") as f:
  for buf in iter(lambda:f.read(1<<20),b""):h.update(buf)
 return h.hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def write(path,obj):
 p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_suffix(p.suffix+".partial")
 tmp.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n");os.replace(tmp,p)

def frozen():
 m=base.manifest()
 need(m["selected_count"]==13,"selected original formula number changed")
 need(len({x["sha256"] for x in m["cases"]})==13,"duplicate original SHA")
 return m

def official_field():
 """Official published scores on precisely these already selected 13 GBD IDs."""
 m=frozen()
 rows=[]
 for c in m["cases"]:
  need(len(c["id"])==32 and c["official"]["best_verified"]["status"] in
       ("sat-verified","unsat-verified"),"missing official ground truth")
 index={c["id"]:c for c in m["cases"]}
 data,digest,n=hist.score_source()
 need(set(index)<=set(data),"published official score missing one of original source IDs")
 # Parse ALL published solver IDs including alternate main/AI tracks. Only
 # verified SAT/UNSAT count; official times are NOT the same CPU/runner.
 import urllib.request,io
 request=urllib.request.Request(hist.CSV_URL,headers={"User-Agent":"DRNAS-R153-All-Competitor-Score-View/1.0"})
 with urllib.request.urlopen(request,timeout=90) as h: raw=h.read(25_000_000)
 need(hashlib.sha256(raw).hexdigest()==digest,
      "published official CSV changed between two independent downloads")
 reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
 need(set(["solverid","instanceid","runtime","status","vresult"])<=set(reader.fieldnames or []),
      "official column schema changed")
 bysolver=defaultdict(dict)
 for row in reader:
  gid=row["instanceid"].lower()
  if gid not in index:continue
  solver=row["solverid"];record={
    "solver":solver,"id":gid,"status":row["status"],
    "runtime_s":None,"correct_verification":False,
    "track": "main_ai" if solver.endswith("[main-ai]") else
             "main" if solver.endswith("[main]") else "other"}
  if row["runtime"]:
   try:record["runtime_s"]=float(row["runtime"])
   except ValueError:pass
  record["correct_verification"]=row["status"] in ("sat-verified","unsat-verified")
  expected=index[gid]["official"]["best_verified"]["official_result"]
  if record["correct_verification"]:
   need(row["vresult"]==expected,"published verified SAT/UNSAT differs from frozen ground truth")
  # If an exact solverid/instanceid has multiple entries, retain fastest
  # correct verified record; this selection is only for published context.
  old=bysolver[solver].get(gid)
  if old is None or (record["correct_verification"] and not old["correct_verification"]) or (
      record["correct_verification"] and old["correct_verification"] and
      record["runtime_s"] is not None and old["runtime_s"] is not None and
      record["runtime_s"]<old["runtime_s"]):
    bysolver[solver][gid]=record
 ids=sorted(index)
 table=[]
 for solver,items in bysolver.items():
  verified=[x for x in items.values() if x["correct_verification"] and x["runtime_s"] is not None and x["runtime_s"]>0]
  costs=[items[i]["runtime_s"] if i in items and items[i]["correct_verification"] and
            items[i]["runtime_s"] is not None and 0<items[i]["runtime_s"]<=5000. else 10000.
         for i in ids]
  table.append(dict(solver=solver,track=next(iter(items.values()))["track"],
       official_samples_present=len(items),verified=len(verified),
       historical_PAR2_at5000_s=round(sum(costs),6),
       min_verified_s=min((v["runtime_s"] for v in verified),default=None),
       median_verified_s=statistics.median([v["runtime_s"] for v in verified]) if verified else None,
       results_by_formula=items))
 table.sort(key=lambda x:(-x["verified"],x["historical_PAR2_at5000_s"],x["solver"]))
 report=dict(protocol=PROTO,source="SAT Competition 2026 published scores.csv",
  source_url=hist.CSV_URL,source_sha256=digest,source_total_rows=n,
  case_ids=ids,official_solver_entries=len(table),
  main_solver_entries=sum(v["track"]=="main" for v in table),
  main_ai_solver_entries=sum(v["track"]=="main_ai" for v in table),
  historical_time_cap_s=5000,
  STRICTLY_NOT_SAME_RUNNER=True,already_seen_13=True,
  original_cases_SHA256={c["id"]:c["sha256"] for c in m["cases"]},
  disclaimer="All published field entries for these 13 exact competition IDs; not a fresh timed rematch on identical hardware",
  leaderboard=table)
 write(ROOT/"official_all_2026.json",report)
 with (ROOT/"official_all_2026.csv").open("w",newline="") as f:
  fields=["solver","track","official_samples_present","verified","historical_PAR2_at5000_s","min_verified_s","median_verified_s"]
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  w.writerows([{k:x.get(k) for k in fields} for x in table])
 print("R153_ALL_OFFICIAL_FIELD",json.dumps({k:v for k,v in report.items()
      if k!="leaderboard" and k!="original_cases_SHA256"},sort_keys=True),flush=True)
 print("R153_OFFICIAL_TOP12",json.dumps([
  {k:x[k] for k in ("solver","track","verified","historical_PAR2_at5000_s")}
  for x in table[:12]],sort_keys=True),flush=True)

def getpins():
 needed=[*BINARIES.values(),ROOT/"frozen/manifest.json",ROOT/"official-build.json"]
 need(all(x.is_file() for x in needed),"one competitor or frozen manifest missing "+repr([str(x) for x in needed if not x.is_file()]))
 bins={k:sha(v) for k,v in BINARIES.items()}
 official=load(ROOT/"official-build.json")
 need(bins["official_sc2024"]==official["binary_sha256"],
      "not genuine submitted 2026 source binary")
 return bins

def smoke():
 m=frozen()
 bins=getpins()
 # Required startup output SAT/UNSAT verified on original models where possible
 b=ROOT/"smoke";b.mkdir(exist_ok=True)
 sat=b/"SAT.cnf";unsat=b/"UNSAT.cnf"
 sat.write_text("p cnf 2 2\n1 0\n2 0\n");unsat.write_text("p cnf 1 2\n1 0\n-1 0\n")
 for mode in MODES:
  for expected,src in ((10,sat),(20,unsat)):
   cmd=[str(BINARIES[mode].resolve()),str(src.resolve())]
   if mode in ("r153","r28"):cmd.append(str(BINARIES["kissat"].resolve()))
   p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
   need(p.returncode==expected,"unreliable competitor smoke result "+mode+" "+str(p.returncode))
   if expected==10:hist.sat_model_check(src,p.stdout)
 print("R153_SIX_SOLVER_SMOKE_PASS",json.dumps(bins,sort_keys=True),flush=True)

def run(shard):
 need(shard in range(SHARDS),"invalid shard")
 m=frozen();bins=getpins();smoke()
 if hasattr(os,"sched_getaffinity"):
  affinity=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(affinity)})
 cpu=next((x for x in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
          if x.startswith("model name")),"unknown")
 model=sha(ROOT/"frozen/manifest.json")
 result=[]
 for i,c in enumerate(m["cases"]):
  if i%SHARDS!=shard:continue
  for rep in range(REPS):
   modes=list(MODES);random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(modes)
   states=set()
   for mode in modes:
    # Reuses R153 exact original SAT and XOR-UNSAT checkers.
    row=base.trial(c,mode,rep)
    row.update(protocol=PROTO,shard=shard,
               source_manifest_sha256=model,original_CNF_sha256=c["sha256"])
    result.append(row)
    if row["status"] in ("SAT","UNSAT"):
     states.add(row["status"]);need(len(states)<=1,"two solvers disagree on original CNF")
    write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
       original_manifest_sha256=model,binaries=bins,cpu=cpu,rows=result))
    print("R153_WORLD_PAIRED",json.dumps(row,sort_keys=True),flush=True)
 need(len(result)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
      "incomplete same-runner paired matrix")
 print("R153_WORLD_SHARD_PASS",shard,len(result),flush=True)

def bootstrap(per,mode,baseline):
 rng=random.Random(15320261105)
 groups=defaultdict(list)
 for row in per:groups[row["cohort"]].append(row)
 values=[]
 for rep in range(3000):
  sample=[rng.choice(group) for key,group in sorted(groups.items()) for _ in group]
  total=sum(x[baseline] for x in sample)
  values.append(100*(total-sum(x[mode] for x in sample))/total)
 values.sort();return [round(values[74],6),round(values[2924],6)]

def audit():
 m=frozen()
 shards=[load(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
 need(all(s["protocol"]==PROTO and
          s["original_manifest_sha256"]==sha(ROOT/"frozen/manifest.json") for s in shards),
      "original source SHA or protocol mismatch")
 need(len(set(json.dumps(s["binaries"],sort_keys=True) for s in shards))==1,
      "competition solver SHA mismatch across runners")
 rows=[r for sh in shards for r in sh["rows"]]
 need(len(rows)==len(m["cases"])*REPS*len(MODES),"incomplete sixway benchmark")
 keyed={};identities={c["id"]:c for c in m["cases"]}
 for r in rows:
  c=identities.get(r["id"]);need(c and r["sha256"]==c["sha256"],"formula SHA mismatch")
  need(r["mode"] in MODES and r["repeat"] in (0,1),"mode/repetition mismatch")
  need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
  need(0<=r["seconds"]<=CAP,"invalid measured time")
  need(abs(r["par2"]-(CAP*2 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,
      "invalid PAR2 penalty")
  if r["status"]=="SAT":need(r["proof"]=="original_CNF_SAT_model_checked","unvalidated SAT result")
  if r["route"]=="gf2_unsat" and r["mode"]=="r153":
   need(r["proof"]=="independently_replayed_original_XOR_unit_UNSAT","no independently reconstructed XOR proof")
  k=(r["sha256"],r["repeat"],r["mode"]);need(k not in keyed,"duplicate paired measurement")
  keyed[k]=r
 for c in m["cases"]:
  for rep in range(REPS):
   votes={keyed[c["sha256"],rep,mode]["status"] for mode in MODES}-{"TIMEOUT"}
   need(len(votes)<=1,"SAT and UNSAT contradictory answers")
 summary={}
 for mode in MODES:
  subset=[x for x in rows if x["mode"]==mode]
  times=[r["seconds"] for r in subset if r["status"]!="TIMEOUT"]
  summary[mode]=dict(trials=len(subset),solved=len(times),
    SAT=sum(r["status"]=="SAT" for r in subset),
    UNSAT_unverified=sum(r["status"]=="UNSAT" and r["proof"]=="UNSAT_without_independent_LRAT" for r in subset),
    UNSAT_independent_XOR=sum(r["proof"]=="independently_replayed_original_XOR_unit_UNSAT" for r in subset),
    timeouts=len(subset)-len(times),
    PAR2_s=round(sum(r["par2"] for r in subset),6),
    median_solved_s=round(statistics.median(times),6) if times else None)
 bycase=[]
 for c in m["cases"]:
  costs={mode:sum(keyed[c["sha256"],rep,mode]["par2"] for rep in range(REPS)) for mode in MODES}
  bycase.append(dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
    official_best_published_s=c["official"]["best_verified"]["seconds"],
    official_best_published_name=c["official"]["best_verified"]["solver"],
    official_best_published_status=c["official"]["best_verified"]["status"],
    **costs,
    **{mode+"_solved":sum(keyed[c["sha256"],rep,mode]["status"]!="TIMEOUT" for rep in range(REPS))
       for mode in MODES}))
 comps={}
 for mode in MODES:
  if mode=="r153":continue
  a=summary[mode]["PAR2_s"];b=summary["r153"]["PAR2_s"]
  comps[mode]=dict(r153_gain_in_PAR2_pct=round(100*(a-b)/a,6),
     bootstrap95_pct=bootstrap(bycase,"r153",mode),
     formula_wins=sum(c["r153"]+1e-5<c[mode] for c in bycase),
     formula_losses=sum(c["r153"]>c[mode]+1e-5 for c in bycase),
     formula_regressions2x=sum(c["r153"]>=2*max(.001,c[mode]) for c in bycase))
 cohort={co:dict(formulas=sum(c["cohort"]==co for c in m["cases"]),
    by_mode={mode:dict(
       PAR2_s=round(sum(x["par2"] for x in rows if x["cohort"]==co and x["mode"]==mode),6),
       solved=sum(x["status"]!="TIMEOUT" for x in rows if x["cohort"]==co and x["mode"]==mode))
      for mode in MODES}) for co in sorted(set(x["cohort"] for x in m["cases"]))}
 ranking=sorted(MODES,key=lambda mode:summary[mode]["PAR2_s"])
 report=dict(protocol=PROTO,verdict="EXPLORATORY_SAME_RUNNER_REUSED_13_NO_WORLD_RECORD",
    source="frozen R152 13 reused in R153 development",
    source_run_id=42102227483,formulas=13,trials=len(rows),CAP_s=CAP,reps=REPS,
    original_CNF_SHA_verified=True,original_sources_modified=False,
    different_CPUs_across_shards=[x["cpu"] for x in shards],
    pinned_binaries=shards[0]["binaries"],modes=MODES,
    summary=summary,ranking=ranking,comparisons=comps,by_cohort=cohort,
    per_formula=bycase,original_manifest_sha256=sha(ROOT/"frozen/manifest.json"),
    official_world_published_source_sha256=load(ROOT/"official_all_2026.json")["source_sha256"],
    official_world_published_solver_entries=load(ROOT/"official_all_2026.json")["official_solver_entries"],
    caveats=["13 CNFs previously exposed in R152/R153; NOT a fresh blind holdout",
        "20s cap and GitHub hardware differ from official SAT Competition 2026",
        "SAT witnesses independently checked against original full CNF",
        "UNSAT GF2 R153 subset replayed; other UNSAT conclusions lack independent LRAT certificates",
        "Every group/mode pair tested on same runner, CPU may differ across shard groups",
        "official_all_2026.json contains all published competition entries but their times cannot be compared as same-runner speedups",
        "No automatic promotion or world-record claim"])
 write(ROOT/"audit.json",report)
 with (ROOT/"paired.csv").open("w",newline="") as f:
  fields=sorted(set().union(*(set(r.keys()) for r in rows)))
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 with (ROOT/"per_formula.csv").open("w",newline="") as f:
  fields=list(bycase[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(bycase)
 print("R153_WORLD_FINAL",json.dumps({k:report[k] for k in ("formulas","trials","CAP_s","summary","ranking","comparisons","by_cohort","official_world_published_solver_entries")},
       sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("step",choices=("official","run","audit"))
 p.add_argument("--shard",type=int,default=0)
 args=p.parse_args()
 {"official":official_field,"run":lambda:run(args.shard),"audit":audit}[args.step]()

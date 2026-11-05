#!/usr/bin/env python3
"""R127: precommitted cheap complete-XOR prefilter before immutable R118/Kissat.
Every actual solve is paired with *identical* original Kissat on a frozen SHA
source. Prospective external samples are separate from historical R115 control.
No V15.3.1 changes; UNSAT without independent proof remains uncertified.
"""
import argparse, hashlib, json, os, pathlib, random, re, subprocess, time
from collections import Counter,defaultdict
import r126_equivalence_budget as previous

ROOT=pathlib.Path("r127")
ROOT.mkdir(exist_ok=True)
PROTO="DRNAS-R127-CHEAP-EXACT-XOR-FROZEN-20261105-v1"
MODES=("kissat","r118","r127")
CAP=15.0
REPS=2
SHARDS=8
FILTER=pathlib.Path("r127/r127_filter").resolve()
R118=pathlib.Path("r127/r118").resolve()
KISSAT=pathlib.Path("built/bin/kissat_4_0_4").resolve()
R115_SHA="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
SOURCES={
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",12),
 "official2025":("https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",14),
 "official2026":("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",14),
}
PRIOR=("r120","r121","r122","r123","r124","r125","r126")

def need(ok,msg):
 if not ok:raise RuntimeError("R127_STRICT_FAIL "+str(msg))
def digest(data):return hashlib.sha256(data).hexdigest()
def file_sha(p):return digest(pathlib.Path(p).read_bytes())
def check_original_sat(data,cnf):
 from r118_xor_paired_real import parse_cnf,check_sat_model
 n,clauses=parse_cnf(cnf.read_bytes())
 check_sat_model(data,n,clauses)

def freeze():
 dest=ROOT/"frozen";dest.mkdir(exist_ok=True)
 used={R115_SHA};urls_seen=set();identifiers=set()
 old_digest={}
 from r125_native_gate_benchmark import HISTORIC_IDS
 identifiers.update(HISTORIC_IDS)
 for key in PRIOR:
  path=ROOT/"prior"/key/"manifest.json"
  need(path.is_file(),"missing prior source ledger "+key)
  meta=json.loads(path.read_text())
  rows=meta.get("selected") if key in ("r120","r121") else meta.get("cases")
  need(isinstance(rows,list) and bool(rows),"bad prior source ledger "+key)
  old_digest[key]=file_sha(path)
  for r in rows:
   h=r.get("sha256")
   if h:used.add(h)
   for field in ("gbd","url"):
    val=r.get(field)
    if val:
     identifiers.add(str(val).rsplit("/",1)[-1].split("?")[0])
     if field=="url":urls_seen.add(val)
 candidates=[];excluded=[];source_indexes={}
 for cohort,(index,target) in SOURCES.items():
  raw=previous.download(index,4_000_000)
  listings=sorted({x.strip() for x in raw.decode("utf-8").splitlines()
                   if x.strip().startswith(("https://","http://"))})
  need(bool(listings),"empty source URI "+cohort)
  source_indexes[cohort]={"index_url":index,"index_sha256":digest(raw),"urls":len(listings)}
  random.Random(PROTO+"|"+cohort).shuffle(listings)
  count=0
  for url in listings:
   if count>=target:break
   token=url.rsplit("/",1)[-1].split("?")[0]
   if token in identifiers or url in urls_seen:continue
   try:
    data=previous.download(url)
    plain=previous.unpack(data)
    if len(plain)>8_000_000:raise ValueError("over source bound")
    sha=digest(plain)
    if sha in used:continue
    headers=[line.split() for line in plain.splitlines() if line.startswith(b"p cnf ")]
    if len(headers)!=1 or len(headers[0])!=4:raise ValueError("missing DIMACS header")
    n,m=map(int,headers[0][2:])
    if n<1 or m<1:raise ValueError("bad DIMACS dimensions")
    name=f"{cohort}-{count:03d}.cnf"
    (dest/name).write_bytes(plain)
    candidates.append(dict(id=name,cohort=cohort,gbd=token,url=url,sha256=sha,
         download_sha256=digest(data),bytes=len(plain),variables=n,clauses=m,
         exposure="new_external_relative_to_R120_R126"))
    used.add(sha);urls_seen.add(url);identifiers.add(token);count+=1
    print("R127_FROZEN_EXTERNAL",cohort,count,name,sha[:12],flush=True)
   except Exception as e:
    excluded.append({"cohort":cohort,"id":token,"reason":(str(e)[:140])})
   if len(excluded)>800:break
 counts=Counter(c["cohort"] for c in candidates)
 need(len(candidates)>=15 and sum(counts[x]>=4 for x in SOURCES)>=2,
      "too few prospective external formulas "+str(counts))
 # Fully seen R115 competition example: positive control, never unseen.
 raw=previous.download("https://benchmark-database.de/file/75429ff7acb5acb597abe01aa745c2a6")
 plain=previous.unpack(raw)
 need(digest(plain)==R115_SHA,"R115 historic SHA mismatch")
 name="r115-historical-control.cnf";(dest/name).write_bytes(plain)
 candidates.append(dict(id=name,cohort="r115_control",
      gbd="75429ff7acb5acb597abe01aa745c2a6",
      url="https://benchmark-database.de/file/75429ff7acb5acb597abe01aa745c2a6",
      sha256=R115_SHA,download_sha256=digest(raw),bytes=len(plain),
      variables=250,clauses=1000,exposure="historical_previously_seen"))
 m=dict(protocol=PROTO,source_commit="same_run_git_sha",cases=candidates,
      shards=SHARDS,repeats=REPS,cap_seconds=CAP,modes=MODES,source_indexes=source_indexes,
      historical_sha_manifests=old_digest,counts=dict(Counter(c["cohort"] for c in candidates)),
      source_bias="8 MB decompressed limit and URI-order sample; not official contest score",
      selection="frozen strict k=2..4 complete-XOR, >=8 eqs and >=90% covered, input <=262144 bytes",
      no_model_training_from_new_holdout=True,
      excluded_count=len(excluded),excluded=excluded[:100])
 (dest/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
 print("R127_FREEZE_PASS",json.dumps(dict(counts=m["counts"],total=len(candidates))),flush=True)

def probe_control():
 src=ROOT/"controls";src.mkdir(exist_ok=True)
 def cnf(name,clauses):
  p=src/(name+".cnf")
  p.write_text("p cnf 30 "+str(len(clauses))+"\n"+
      "".join(" ".join(str(v) for v in row)+" 0\n" for row in clauses))
  return p
 # Four clauses are the complete encoding of XOR(x,y,z), all sign permutations.
 good=[(1,2,3),(-1,-2,3),(-1,2,-3),(1,-2,-3)]
 g=cnf("complete_3xor",good*10)
 b=cnf("incomplete_3xor",good[:3]*10)
 for file,expected in ((g,"KISSAT"),(b,"KISSAT")):
  p=subprocess.run([str(FILTER),str(file),str(R118),str(KISSAT),"--probe-only"],
                   capture_output=True,text=True,timeout=3)
  need(p.returncode==0 and ("route="+expected) in p.stdout,
       "incomplete negative control must never trigger")
 # Strong positive control with >=8 DISTINCT complete 3-variable XOR equations.
 distinct=[]
 for j in range(9):
  v=3*j+1
  for a,b,c in good:
   distinct.append(tuple((1 if x>0 else -1)*(v+abs(x)-1) for x in (a,b,c)))
 true_pos=cnf("nine_distinct_xors",distinct)
 p=subprocess.run([str(FILTER),str(true_pos),str(R118),str(KISSAT),"--probe-only"],
                  capture_output=True,text=True,timeout=3)
 need(p.returncode==0 and "route=GF2" in p.stdout,
      "complete-XOR positive control must trigger")
 (src/"report.json").write_text(json.dumps(dict(positive=p.stdout.strip(),
    negative="partial clause encodings do not trigger"),indent=2)+"\n")
 print("R127_POSITIVE_NEGATIVE_CONTROLS_PASS",flush=True)

def attempt(case,mode,rep):
 src=ROOT/"frozen"/case["id"]
 need(file_sha(src)==case["sha256"],"modified original CNF")
 cmd={"kissat":[str(KISSAT),str(src)],
      "r118":[str(R118),str(src),str(KISSAT)],
      "r127":[str(FILTER),str(src),str(R118),str(KISSAT)]}[mode]
 start=time.perf_counter();status="TIMEOUT";out=b"";route="timeout"
 try:
  x=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  spent=time.perf_counter()-start
  if x.returncode not in (10,20):
   raise RuntimeError("binary failed "+str(x.returncode)+" "+x.stderr[-350:].decode(errors="replace"))
  status="SAT" if x.returncode==10 else "UNSAT"
  out=x.stdout
  if status=="SAT":check_original_sat(out,src)
  route=("pure_kissat" if mode=="kissat" else
         "GF2_or_fallback" if mode=="r118" else
         ("GF2" if b"c R127_PREFILTER route=GF2" in out else "KISSAT"))
  if mode=="r127":
   need(b"c R127_PREFILTER route=" in out,"missing prefilter route")
  if spent>CAP:status="TIMEOUT";route="timeout"
 except subprocess.TimeoutExpired:
  spent=CAP
 seconds=round(min(CAP,spent),6)
 return dict(id=case["id"],cohort=case["cohort"],sha256=case["sha256"],
             mode=mode,repeat=rep,seconds=seconds,
             status=status,par2=30.0 if status=="TIMEOUT" else seconds,
             route=route,verification=("source_SAT_witness_verified" if status=="SAT"
                   else "UNSAT_not_independently_verified" if status=="UNSAT" else "timeout"))

def benchmark(shard):
 need(0<=shard<SHARDS,"shard range")
 manifest=json.loads((ROOT/"frozen"/"manifest.json").read_text())
 need(manifest["protocol"]==PROTO,"protocol")
 if hasattr(os,"sched_getaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 out=[]
 for i,case in enumerate(manifest["cases"]):
  if i%SHARDS!=shard:continue
  for rep in range(REPS):
   modes=list(MODES);random.Random(PROTO+case["sha256"]+str(rep)).shuffle(modes)
   for mode in modes:
    row=attempt(case,mode,rep)
    out.append(row)
    print("R127_MEASURE",json.dumps(row,sort_keys=True),flush=True)
    (ROOT/f"shard-{shard}.json").write_text(json.dumps(out)+"\n")
 need(len(out)==len(manifest["cases"][shard::SHARDS])*len(MODES)*REPS,"incomplete shard")
 print("R127_SHARD_PASS",shard,len(out),flush=True)

def aggregate():
 m=json.loads((ROOT/"frozen"/"manifest.json").read_text())
 need(m["protocol"]==PROTO and m["modes"]==MODES,"protocol/modes mismatch")
 cases=m["cases"];need(len({c["sha256"] for c in cases})==len(cases),"SHA duplicates")
 seen=set();runs=[];cpus=set();commits=set();bins=set()
 for i in range(SHARDS):
  p=ROOT/f"shard-{i}.json"
  need(p.is_file(),"missing shard "+str(i))
  block=json.loads(p.read_text())
  need(len(block)==len(cases[i::SHARDS])*len(MODES)*REPS,"incomplete raw")
  lineage=json.loads((ROOT/f"pin-{i}.json").read_text())
  commits.add(lineage["commit"]);bins.add(json.dumps(lineage["binaries"],sort_keys=True))
  cpus.add(lineage["cpu"])
  for r in block:
   key=(r["id"],r["repeat"],r["mode"])
   need(key not in seen,"duplicate attempt "+str(key));seen.add(key)
   c=next((x for x in cases if x["id"]==r["id"]),None)
   need(c and c["sha256"]==r["sha256"] and c["cohort"]==r["cohort"],"formula source metadata")
   need(r["repeat"] in (0,1) and r["mode"] in MODES,"mode/repeat")
   need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"status")
   need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<.000001,"PAR2 audit")
   need(r["status"]!="SAT" or r["verification"]=="source_SAT_witness_verified","SAT witness")
  runs.extend(block)
 need(len(runs)==len(cases)*len(MODES)*REPS,"total measurements")
 need(len(commits)==len(bins)==1,"inconsistent commits/binary pins")
 pairs=defaultdict(dict)
 for r in runs:pairs[(r["id"],r["repeat"])][r["mode"]]=r
 need(len(pairs)==len(cases)*REPS and all(set(p)==set(MODES) for p in pairs.values()),"not paired")
 for p in pairs.values():
  answers={r["status"] for r in p.values()}-{"TIMEOUT"}
  need(len(answers)<=1,"SAT/UNSAT disagreement")
 need(any(p["r127"]["route"]=="GF2" for p in pairs.values()
          if p["r127"]["cohort"]=="r115_control"),"R115 control did not activate")
 summary={}
 for cohort in (*SOURCES,"r115_control","new_external","all"):
  sample=[c for c in cases if cohort=="all" or (c["cohort"]!="r115_control" if cohort=="new_external" else c["cohort"]==cohort)]
  cset={c["id"] for c in sample}
  rows=[r for r in runs if r["id"] in cset]
  stats={}
  for mode in MODES:
   filtered=[r for r in rows if r["mode"]==mode]
   stats[mode]=dict(attempts=len(filtered),solved=sum(x["status"]!="TIMEOUT" for x in filtered),
         par2_s=round(sum(x["par2"] for x in filtered),6),
         GF2_activated=sum(x["route"]=="GF2" for x in filtered),
         timeouts=sum(x["status"]=="TIMEOUT" for x in filtered))
  gains={}
  for mode in ("r127","r118"):
   a=stats[mode]["par2_s"];b=stats["kissat"]["par2_s"]
   gains[mode]=round(100*(b/a-1),4) if a else None
  summary[cohort]=dict(formulas=len(sample),stats=stats,gain_percent=gains)
  if cohort=="new_external":
   import random as rnd
   rng=rnd.Random(PROTO+"new_external_bootstrap")
   vals=[]
   for _ in range(1500):
    draw=[rng.choice(sample)["id"] for _ in sample]
    base=sum(pairs[(v,rep)]["kissat"]["par2"] for v in draw for rep in range(REPS))
    solver=sum(pairs[(v,rep)]["r127"]["par2"] for v in draw for rep in range(REPS))
    if solver:vals.append(100*(base/solver-1))
   vals.sort()
   summary[cohort]["bootstrap95_gain_percent"]=[round(vals[int(.025*(len(vals)-1))],4),
       round(vals[int(.975*(len(vals)-1))],4)] if vals else None
 report=dict(protocol=PROTO,run_commits=list(commits),source_manifest_sha256=file_sha(ROOT/"frozen"/"manifest.json"),
   cpu_models=sorted(cpus),binary_pins=json.loads(next(iter(bins))),
   formulas=len(cases),attempts=len(runs),shards=SHARDS,
   full_immutable_pin_and_sha_audit=True, cohorts=summary,
   r115_is_historical_control_not_unseen=True,
   verified_SAT_model_for_every_solved_SAT=True,
   unsat_caveat="Independent UNSAT proof not checked; claimed solver status only",
   method="R127 detects only full XOR signatures; R118 proof checks its own claimed GF2 shortcuts; Kissat otherwise unchanged",
   promotion_allowed=False)
 (ROOT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
 import csv
 with (ROOT/"paired.csv").open("w",newline="") as f:
  w=csv.writer(f);w.writerow(["cohort","source_sha256","rep","r127_par2","r118_par2","kissat_par2","r127_route"])
  for (id,rep),p in sorted(pairs.items()):
   w.writerow([p["r127"]["cohort"],p["r127"]["sha256"],rep,
               p["r127"]["par2"],p["r118"]["par2"],p["kissat"]["par2"],p["r127"]["route"]])
 print("R127_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("command",choices=("freeze","control","benchmark","aggregate"))
 p.add_argument("--shard",type=int,default=0);args=p.parse_args()
 {"freeze":freeze,"control":probe_control,
  "benchmark":lambda:benchmark(args.shard),"aggregate":aggregate}[args.command]()

#!/usr/bin/env python3
"""R124 independent external mixed-circuit SAT transfer with R122 gated fallback.

No runtime-based selection: candidate URI lists are sorted, seeded/shuffled and SHA
frozen before solver execution. The prospective corpus is separate from the R122
generated smoke cases. Report gate activations and fallback overhead, not just
total score. Any direct UNSAT statement needs an independent source-level audit.
"""
from __future__ import annotations
import argparse,bz2,gzip,hashlib,io,json,lzma,os,pathlib,random,re,subprocess,time,urllib.request
from collections import Counter,defaultdict

ROOT=pathlib.Path("r124")
ROOT.mkdir(exist_ok=True)
PROTO="DRNAS-R124-FROZEN-EXTERNAL-MIXED-20261105-v1"
SOURCES={
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",40),
 "official2026":("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",50),
}
CAP=15.0
REPS=2
SHARDS=8
MODES=("r124","r118","kissat","cryptominisat")
RAW_CAP=8_000_000
CNF_CAP=8_000_000
HISTORICAL_GBD={
 "42f1311ce504db8cc0cb590a568da20a", # R117/118 and R120 033
 "75429ff7acb5acb597abe01aa745c2a6", # R115/118 and R32p
 "01d6fa8efd18ebfecd06af408958477b", # R117/118
 "0efcbd10294eb001b16b4d126923372f", # R117/118
 "0e06895600b5cd0b6fadb87e17bf8145",
 "180e6d8b61fe6bab26126b78591e324e",
 "2b7e863462991fd008f9898eca63ebf4",
 "3b0eeddcabf36da8642c5774ac67680c",
 "4e0de894799790b06e8d6c3efd109ade",
 "5f9d0127b390a4686171311d38f3fbf8",
 "860788f93fb766e83e00a29de84180e7",
 "991aec61a2751602d6d7b3e838035610",
 "aa0eadb6c4935468fd6954e23a550504",
 "ba14be209c2fc064726025f017cef17a",
 "d4a6b1a299c7a8ad6ea9769abcc60507",
 "e85fb114c33f450dc2622c78bc6fa019",
 "fd1e0ce3662b9b25d23eb01c6e53a425",
}

def digest(x):return hashlib.sha256(x).hexdigest()
def sha_file(filename):
 h=hashlib.sha256()
 with open(filename,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def fetch(url,maxbytes=RAW_CAP):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R124-Prospective-XOR-AND-OR/1.0"})
 with urllib.request.urlopen(req,timeout=60) as f:
  data=f.read(maxbytes+1)
 if len(data)>maxbytes:raise ValueError("source exceeds precommitted size cap")
 return data

def unpack(raw):
 if raw.startswith(b"\xfd7zXZ"):s=lzma.LZMAFile(io.BytesIO(raw))
 elif raw.startswith(b"\x1f\x8b"):s=gzip.GzipFile(fileobj=io.BytesIO(raw))
 elif raw.startswith(b"BZh"):s=bz2.BZ2File(io.BytesIO(raw))
 else:
  if len(raw)>CNF_CAP:raise ValueError("CNF size limit")
  return raw
 with s:data=s.read(CNF_CAP+1)
 if len(data)>CNF_CAP:raise ValueError("decompressed CNF size limit")
 return data

def candidate_urls(index):
 body=fetch(index,4_000_000).decode("utf-8")
 values=sorted(set(x.strip() for x in body.splitlines() if x.strip().startswith(("https://","http://"))))
 if not values:raise ValueError("INDEX_HAS_NO_URI entries: "+index)
 return values

def inspect_dimacs(data):
 headers=[line for line in data.splitlines() if line.startswith(b"p cnf ")]
 if len(headers)!=1:raise ValueError("expected one DIMACS header")
 h=headers[0].split()
 if len(h)!=4:raise ValueError("malformed DIMACS header")
 n,m=map(int,h[2:])
 if not (0<n<=50_000_000 and 0<m<=100_000_000):raise ValueError("invalid dimensions")
 return n,m

def load_prior():
 manifest_paths={
  "r120":ROOT/"prior-r120/manifest.json",
  "r121":ROOT/"prior-r121/manifest.json",
  "r122":ROOT/"prior-r122/manifest.json",
  "r123":ROOT/"prior-r123/manifest.json",
 }
 prior_ids=set(HISTORICAL_GBD);prior_sha=set();manifest_sha={}
 for key,p in manifest_paths.items():
  if not p.is_file():raise ValueError("Missing required prior source ledger "+str(p))
  manifest_sha[key]=sha_file(p);m=json.loads(p.read_text())
  cases=m["selected"] if key in ("r120","r121") else m["cases"]
  minimum={"r120":150,"r121":150,"r122":192,"r123":160}[key]
  if len(cases)!=minimum:raise ValueError("incomplete historical manifest "+key)
  for c in cases:
   prior_sha.add(c["sha256"])
   if c.get("gbd"):prior_ids.add(c["gbd"])
   if c.get("url"):prior_ids.add(c["url"].rsplit("/",1)[-1])
 return prior_ids,prior_sha,manifest_sha

def freeze():
 ids,hashes,prior_manifest_sha=load_prior()
 selected=[];exclusions=[];lists={}
 for cohort,(index,target) in SOURCES.items():
  urls=candidate_urls(index)
  lists[cohort]=dict(source=index,uri_count=len(urls),sha256=digest("\n".join(urls).encode()),target=target)
  random.Random(PROTO+"-"+cohort).shuffle(urls)
  n=0
  for url in urls:
   if n>=target:break
   identifier=url.rsplit("/",1)[-1].split("?")[0]
   if identifier in ids:
    exclusions.append(dict(cohort=cohort,gbd=identifier,reason="historical_id"))
    continue
   try:
    raw=fetch(url)
    plain=unpack(raw)
    variables,clauses=inspect_dimacs(plain)
    checksum=digest(plain)
    if checksum in hashes:raise ValueError("historical_SHA256")
    if any(x["sha256"]==checksum for x in selected):raise ValueError("new duplicate SHA256")
    name=f"{cohort}-{n:03d}.cnf"
    (ROOT/name).write_bytes(plain)
    selected.append(dict(id=name,cohort=cohort,gbd=identifier,url=url,sha256=checksum,
       raw_sha256=digest(raw),bytes=len(plain),variables=variables,clauses=clauses))
    n+=1
    print("R124_FREEZE_CASE",cohort,n,identifier,checksum[:12],flush=True)
   except Exception as e:
    exclusions.append(dict(cohort=cohort,gbd=identifier,reason=(type(e).__name__+": "+str(e))[:180]))
   if len(exclusions)>1200:break
  print("R124_COHORT_READY",cohort,n,"of",target,flush=True)
 # Positive control: already seen in R115, not a new external sample.
 control="75429ff7acb5acb597abe01aa745c2a6"
 raw=fetch("https://benchmark-database.de/file/"+control)
 plain=unpack(raw);sha=digest(plain)
 if sha!="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83":
  raise RuntimeError("R115 original source digest mismatch")
 variables,clauses=inspect_dimacs(plain)
 if (variables,clauses)!=(250,1000):raise RuntimeError("R115 dimensions mismatch")
 (ROOT/"r115-control.cnf").write_bytes(plain)
 selected.append(dict(id="r115-control.cnf",cohort="r115_control",gbd=control,
   url="https://benchmark-database.de/file/"+control,sha256=sha,raw_sha256=digest(raw),
   bytes=len(plain),variables=variables,clauses=clauses,provenance="KNOWN_R115_CONTROL"))
 counts=Counter(x["cohort"] for x in selected)
 m=dict(protocol=PROTO,source_lists=lists,prior_manifest_sha=prior_manifest_sha,
   cases=selected,exclusions=exclusions,counts=dict(counts),reps=REPS,shards=SHARDS,
   modes=MODES,cap_seconds=CAP,raw_cap_bytes=RAW_CAP,cnf_cap_bytes=CNF_CAP,
   sampling="predeclared family URI order; seeded shuffle before downloads; exclude by source-size/hash/provenance only",
   constraints="External SAT Competition/GBD inputs, not synthetic R122 samples. Mixed-gate presence not guaranteed.",
   novelty="SHA + URL/GBD crosschecked vs R120/R121/R122 and R118/R32p pins; historic exhaustive audit still incomplete")
 (ROOT/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
 print("R124_FREEZE_FINAL",json.dumps(dict(counts=dict(counts),cases=len(selected),exclusions=len(exclusions))),flush=True)
 if len(selected)<85 or counts["official2026"]<45 or counts["miter"]<35:
  raise RuntimeError("FROZEN_CORPUS_INSUFFICIENT: no benchmark on undersized/cohort-biased data")

def bins():
 base=pathlib.Path("r124")
 b={"r124":(base/"r124_probe").resolve(),
    "r118":(base/"r118").resolve(),
    "kissat":pathlib.Path("built/bin/kissat_4_0_4").resolve(),
    "cryptominisat":pathlib.Path(os.environ["CRYPTOMINISAT_BIN"]).resolve()}
 if not all(v.is_file() for v in b.values()):raise RuntimeError("missing solver binary")
 return b

def classify_output(data,solver):
 text=data.decode("utf-8",errors="replace")
 for route in ("certified_gate_anf_equivalent","certified_gate_anf_counterexample",
      "certified_xor_contradiction","certified_pure_xor_sat","fallback"):
  if route in text:return route
 return "baseline" if solver in ("kissat","cryptominisat") else "unknown"

def execute_one(mode,cnf,binaries):
 cmd=([str(binaries["r124"]),str(cnf),str(binaries["r118"]),str(binaries["kissat"])]
       if mode=="r124" else [str(binaries[mode]),str(cnf),str(binaries["kissat"])]
       if mode=="r118" else [str(binaries[mode]),str(cnf)])
 started=time.perf_counter()
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  seconds=time.perf_counter()-started
  if p.returncode not in (10,20):
   raise RuntimeError("solver "+mode+" failed with exit "+str(p.returncode)+
     " stderr="+p.stderr[-300:].decode("utf-8",errors="replace"))
  return dict(status="SAT" if p.returncode==10 else "UNSAT",
    seconds=round(seconds,6),par2=round(seconds,6),
    route=classify_output(p.stdout,mode),stdout=p.stdout)
 except subprocess.TimeoutExpired as e:
  partial=e.stdout or b""
  return dict(status="TIMEOUT",seconds=CAP,par2=2*CAP,
     route=classify_output(partial,mode) if partial else "unclassified_timeout",stdout=b"")

def verify_result(mode,cnf,x):
 if x["status"]=="TIMEOUT":return "timeout"
 # SAT witnesses are validated against the unmodified original source CNF.
 from r118_xor_paired_real import parse_cnf,check_sat_model,check_unsat_cert
 if x["status"]=="SAT":
  n,clauses=parse_cnf(cnf.read_bytes())
  check_sat_model(x["stdout"],n,clauses)
  if x["route"]=="certified_gate_anf_counterexample":
   from r122_mixed_paired import full_gate_proof
   match=re.search(rb"^c R122_ROUTE certified_gate_anf_counterexample inputs=(\d+)",x["stdout"],re.M)
   assert match,"R122 direct SAT did not report input count"
   if int(match.group(1))<=12:
    assert full_gate_proof(cnf.read_bytes(),"SAT")["equivalent"] is False
  return "source_SAT_witness_verified"
 if x["route"]=="certified_xor_contradiction":
  n,clauses=parse_cnf(cnf.read_bytes())
  check_unsat_cert(x["stdout"],clauses,"R118")
  return "source_XOR_UNSAT_cert_verified"
 if x["route"]=="certified_gate_anf_equivalent":
  from r118_xor_paired_real import parse_cnf
  from r122_mixed_paired import full_gate_proof
  n,clauses=parse_cnf(cnf.read_bytes())
  # The independent checker exhaustively enumerates up to 12 primary inputs.
  # Larger recognized netlists remain labelled UNVERIFIED, never "certified".
  match=re.search(rb"^c R122_ROUTE certified_gate_anf_equivalent inputs=(\d+)",x["stdout"],re.M)
  assert match,"R122 direct UNSAT did not report input count"
  if int(match.group(1))>12:return "UNVERIFIED_gate_gt12_inputs"
  proof=full_gate_proof(cnf.read_bytes(),"UNSAT")
  assert proof["equivalent"]
  return "independent_source_gate_truth_table_verified"
 return "UNSAT_not_independently_verified"

def benchmark(shard):
 m=json.loads((ROOT/"manifest.json").read_text())
 assert m["protocol"]==PROTO and 0<=shard<SHARDS
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 b=bins();rows=[]
 for idx,c in enumerate(m["cases"]):
  if idx%SHARDS!=shard:continue
  cnf=ROOT/c["id"]
  assert sha_file(cnf)==c["sha256"]
  for rep in range(REPS):
   order=list(MODES)
   random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
   answers=set()
   for mode in order:
    x=execute_one(mode,cnf,b)
    proof=verify_result(mode,cnf,x)
    if x["status"] in ("SAT","UNSAT"):
     answers.add(x["status"])
     if len(answers)>1:raise RuntimeError("SAT_UNSAT_DISAGREEMENT "+c["id"]+" "+str(answers))
    probe=re.search(rb"^c R124_PROBE exact_xor=(\d+) resolved_xor=(\d+) partial_hypotheses=(\d+) resolution_clauses=(\d+) resolution_pairs=(\d+) source_small_clauses=(\d+) probe_skipped=(\d+)",x["stdout"],re.M)
    if mode=="r124" and x["status"]!="TIMEOUT" and probe is None:raise RuntimeError("missing XOR detector telemetry")
    row=dict(id=c["id"],cohort=c["cohort"],gbd=c["gbd"],sha256=c["sha256"],
       rep=rep,mode=mode,status=x["status"],route=x["route"],proof=proof,
       seconds=x["seconds"],par2=x["par2"],
       xor_exact=int(probe.group(1)) if probe else None,
       xor_resolved=int(probe.group(2)) if probe else None,
       xor_partial_hypotheses=int(probe.group(3)) if probe else None,
       probe_skipped=int(probe.group(7)) if probe else None)
    rows.append(row)
    print("R124_TRIAL",json.dumps(row,sort_keys=True),flush=True)
   # A checkpoint is useful even before the entire shard completes.
   (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows)+"\n")
 print("R124_SHARD_FINAL",shard,len(rows),flush=True)

def aggregate():
 m=json.loads((ROOT/"manifest.json").read_text())
 cases=m["cases"];all_rows=[]
 for shard in range(SHARDS):
  path=ROOT/f"shard-{shard}.json"
  if not path.is_file():raise RuntimeError("missing shard "+str(shard))
  rows=json.loads(path.read_text())
  assert len(rows)==len(cases[shard::SHARDS])*REPS*len(MODES),("incomplete shard",shard)
  all_rows+=rows
 assert len(all_rows)==len(cases)*REPS*len(MODES)
 binary_sets=set();commits=set();cpu_models=set()
 for shard in range(SHARDS):
  pre=ROOT/f"solver-sha256-{shard}.txt"
  commit=ROOT/f"commit-{shard}.txt"
  cpu=ROOT/f"cpu-{shard}.txt"
  assert pre.is_file() and commit.is_file() and cpu.is_file(),("missing hardware/source pin",shard)
  binary_sets.add(pre.read_text().strip())
  commits.add(commit.read_text().strip())
  cpu_models.add(next((x.strip() for x in cpu.read_text().splitlines()
          if x.strip().startswith("Model name:")),"unknown"))
 assert len(binary_sets)==1,("different solver binary SHA sets across runners",len(binary_sets))
 assert len(commits)==1,("different source commits across runners",commits)
 original={c["id"]:c for c in cases}
 seen=set();pairs=defaultdict(dict)
 for r in all_rows:
  assert r["id"] in original and r["sha256"]==original[r["id"]]["sha256"]
  assert r["cohort"]==original[r["id"]]["cohort"]
  k=(r["id"],r["rep"],r["mode"])
  if k in seen:raise RuntimeError("duplicate paired trial "+str(k))
  seen.add(k);pairs[r["id"],r["rep"]][r["mode"]]=r
 for k,p in pairs.items():
  assert set(p)==set(MODES)
  answers={r["status"] for r in p.values()}-{"TIMEOUT"}
  assert len(answers)<=1,("SAT_UNSAT_CONFLICT",k,answers)
  assert all(r["proof"]=="source_SAT_witness_verified" for r in p.values() if r["status"]=="SAT")
  assert all(r["route"]!="unknown" for r in p.values() if r["mode"]=="r124")
 assert len(pairs)==len(cases)*REPS
 summary={}
 for cohort in (*SOURCES,"r115_control","all"):
  identities=[c["id"] for c in cases if cohort=="all" or c["cohort"]==cohort]
  rows=[r for r in all_rows if cohort=="all" or r["cohort"]==cohort]
  stats={}
  per_formula={}
  for name in identities:
   group=[r for r in rows if r["id"]==name]
   per_formula[name]={mode:sum(r["par2"] for r in group if r["mode"]==mode) for mode in MODES}
  for mode in MODES:
   group=[r for r in rows if r["mode"]==mode]
   stats[mode]=dict(attempts=len(group),solved=sum(r["status"]!="TIMEOUT" for r in group),
     timeouts=sum(r["status"]=="TIMEOUT" for r in group),
     par2_s=round(sum(r["par2"] for r in group),6),
     direct_gate=sum(r["route"].startswith("certified_gate_anf_") for r in group),
     direct_xor=sum(r["route"].startswith("certified_xor_") for r in group),
     fallback=sum(r["route"]=="fallback" for r in group),
     verified_direct_unsat=sum(r["proof"] in
       ("independent_source_gate_truth_table_verified","source_XOR_UNSAT_cert_verified") for r in group),
     unverified_unsat=sum(r["proof"].startswith(("UNVERIFIED","UNSAT_not")) for r in group),
     xor_exact_detected=sum((r.get("xor_exact") or 0)>0 for r in group),
     xor_hidden_resolved_detected=sum((r.get("xor_resolved") or 0)>0 for r in group),
     xor_partial_candidates=sum((r.get("xor_partial_hypotheses") or 0)>0 for r in group),
     probe_skipped=sum(r.get("probe_skipped")==1 for r in group))
  wins=regressions=0
  for name in identities:
   a=per_formula[name]["r124"];b=per_formula[name]["kissat"]
   if a>0 and b/a>=2:wins+=1
   elif b>0 and a/b>=2:regressions+=1
  rng=random.Random(PROTO+cohort+"formula-bootstrap")
  ratios=[]
  for _ in range(1500):
   sample=[rng.choice(identities) for _ in identities]
   a=sum(per_formula[x]["r124"] for x in sample)
   b=sum(per_formula[x]["kissat"] for x in sample)
   if a:ratios.append(100*(b/a-1))
  ratios.sort()
  pa=stats["r124"]["par2_s"];pb=stats["kissat"]["par2_s"]
  summary[cohort]=dict(formulas=len(identities),solvers=stats,
     speedup_vs_kissat=round(pb/pa,6) if pa else None,
     gain_percent=round(100*(pb/pa-1),4) if pa else None,
     formula_bootstrap_95_gain_percent=[round(ratios[int(.025*(len(ratios)-1))],4),
       round(ratios[int(.975*(len(ratios)-1))],4)] if ratios else None,
     formula_wins_ge2x=wins,formula_regressions_ge2x=regressions)
 report=dict(protocol=PROTO,formula_count=len(cases),attempts=len(all_rows),
   shards=SHARDS,limit_seconds=CAP,by_cohort=summary,
   exclusion_manifest_count=len(m["exclusions"]),
   binary_set_sha256=digest(next(iter(binary_sets)).encode()),
   source_commits=list(commits),cpu_models=sorted(cpu_models),
   independent_proof_limit="Only source witness for SAT, source XOR contradiction for R118, and independently enumerated <=12 input gate-miter UNSAT are proof-checked",
   no_activation_interpretation="R124 measures additional structurally inferred XOR, but delegates all decisions to unchanged R118 and pinned Kissat; no claim of new live speedup.",
   scope="SHA-excluded new external CNFs plus one previously seen official R115 control. Not official SAT Competition scoring or a world record.")
 import csv
 with (ROOT/"scatter_pairs.csv").open("w",newline="") as f:
  writer=csv.writer(f);writer.writerow(("cohort","formula_sha256","repeat","r124_PAR2","r118_PAR2","kissat_PAR2","cryptominisat_PAR2","r124_resolved_xor","r124_exact_xor"))
  for (name,rep),pair in sorted(pairs.items()):
   writer.writerow((original[name]["cohort"],original[name]["sha256"],rep,
     *(pair[mode]["par2"] for mode in MODES),pair["r124"].get("xor_resolved"),pair["r124"].get("xor_exact")))
 (ROOT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R124_FINAL",json.dumps(report),flush=True)

def smoke():
 cnf=ROOT/"r115-control.cnf"
 assert cnf.is_file() and sha_file(cnf)=="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
 x=execute_one("r124",cnf,bins())
 assert x["status"]=="SAT" and x["route"]=="certified_pure_xor_sat",x["route"]
 assert b"R124_PROBE" in x["stdout"]
 assert verify_result("r124",cnf,x)=="source_SAT_witness_verified"
 print("R124_HISTORICAL_R115_CONTROL_SUCCESS",x["seconds"],flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("command",choices=("freeze","benchmark","aggregate","smoke"))
 p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 {"freeze":freeze,"benchmark":lambda:benchmark(a.shard),
  "aggregate":aggregate,"smoke":smoke}[a.command]()

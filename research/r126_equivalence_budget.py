#!/usr/bin/env python3
"""R126: budget ablation on R125's 84 frozen external cases, then strict blind
external SHA-excluded holdout using the preselected, immutable cap.

Modes: pure Kissat; native detection-only (cap0) + Kissat; and native source-
proven equivalence additions at 4/16/32/128 + Kissat. All preprocessing,
independent proof audit and solver time share the SAME 15-second wall cap.
No modifications to Kissat or V15.3.1. Reused calibration != new holdout.
"""
from __future__ import annotations
import argparse,bz2,csv,gzip,hashlib,io,json,lzma,os,pathlib,random,re,signal,subprocess,time,urllib.request
from collections import Counter,defaultdict
import r125_native_gate_benchmark as old

ROOT=pathlib.Path("r126")
ROOT.mkdir(exist_ok=True)
PROTO="DRNAS-R126-EQUIVALENCE-CAP-20261105-V1"
NATIVE=pathlib.Path("r126/r126_native").resolve()
KISSAT=pathlib.Path("built/bin/kissat_4_0_4").resolve()
CAP=15.0
REPS=2
SHARDS=8
EXPERIMENTAL=("cap0","cap4","cap16","cap32","cap128")
MODES=("kissat",*EXPERIMENTAL)
SOURCES={
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",25),
 "official2025":("https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",35),
}
MAX_INPUT_BYTES=8_000_000

def sha(data):return hashlib.sha256(data).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def ensure_binaries():
 if not NATIVE.is_file() or not KISSAT.is_file():
  raise RuntimeError("required frozen C++ / pinned Kissat binary missing")

def invoke_native(src,cap,out="-",proof="-"):
 p=subprocess.run([str(NATIVE),str(src),str(out),str(proof),str(cap)],
                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3.0)
 if p.returncode:raise RuntimeError("R126_NATIVE_FAILED "+str(p.returncode)+
                            " "+p.stdout[-200:].decode(errors="replace")+
                            " "+p.stderr[-400:].decode(errors="replace"))
 data=re.findall(rb"^R125_SUMMARY (\{.*\})$",p.stdout,re.M)
 if len(data)!=1:raise RuntimeError("R126_NATIVE_SUMMARY_MISSING")
 result=json.loads(data[0])
 assert result["equivalence_pairs"]<=cap,("BUDGET_VIOLATION",cap,result)
 if cap==0:assert result["equivalence_pairs"]==0
 return result

def make_cnf(path,clauses,n):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text("p cnf %d %d\n"%(n,len(clauses))+
    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def controls():
 ensure_binaries()
 root=ROOT/"controls"
 root.mkdir(exist_ok=True)
 tests=[
  ("and_duplicate",old.gate_requirements("A",1,2,3)+
                   old.gate_requirements("A",1,2,4)+
                   old.gate_requirements("A",1,2,5)+
                   old.gate_requirements("A",1,2,6)+
                   old.gate_requirements("A",1,2,7)+
                   old.gate_requirements("A",1,2,8)+
                   old.gate_requirements("A",1,2,9),True),
  ("xor_signed",old.gate_requirements("X",-1,2,3)+
                old.gate_requirements("X",1,2,-4),True),
  ("or_demorgan",old.gate_requirements("O",1,2,3)+
                 old.gate_requirements("A",-1,-2,4),True),
  ("incomplete_gate",old.gate_requirements("A",1,2,3)+
                     old.gate_requirements("A",1,2,4)[:-1],False),
  ("different_gate",old.gate_requirements("A",1,2,3)+
                    old.gate_requirements("A",-1,2,4),False),
 ]
 results=[]
 for name,clauses,expected in tests:
  src=root/(name+".cnf")
  make_cnf(src,clauses+[(11,12,13)],20)
  values={}
  for cap in (0,4,16,32,128):
   dest=root/(name+"-"+str(cap)+".aug.cnf")
   proof=root/(name+"-"+str(cap)+".tsv")
   if dest.exists():dest.unlink()
   if proof.exists():proof.unlink()
   r=invoke_native(src,cap,str(dest) if cap else "-",str(proof) if cap else "-")
   active=r["equivalence_pairs"]>0
   assert active==(expected and cap>0),(name,cap,r)
   if active:
    audit=old.verify_augmentation(src,dest,proof)
    assert audit["derived_pairs"]==r["equivalence_pairs"]
   else:assert not dest.exists()
   values[str(cap)]=r["equivalence_pairs"]
  assert values["4"]<=4 and values["16"]<=16
  results.append(dict(test=name,expected_activation=expected,pairs_by_cap=values))
 assert results[0]["pairs_by_cap"]["4"]==4,results[0]
 assert int(results[0]["pairs_by_cap"]["128"])>=5,results[0]
 (root/"control-results.json").write_text(json.dumps(results,indent=2)+"\n")
 print("R126_CONTROLS_PASS",json.dumps(results),flush=True)

def provenance():
 prior=ROOT/"prior"
 used_sha=set();used_urls=set();identifiers=set(old.HISTORIC_IDS)
 pin={}
 for name,key,expected in (("r120","selected",150),("r121","selected",150),
                           ("r122","cases",192),("r123","cases",160),
                           ("r125","cases",84)):
  path=prior/name/"manifest.json"
  assert path.is_file(),("missing historical source hash manifest",name,str(path))
  meta=json.loads(path.read_text())
  cases=meta[key]
  assert len(cases)==expected,(name,len(cases),expected)
  pin[name]=sha_file(path)
  for c in cases:
   used_sha.add(c["sha256"])
   for k in ("gbd","url"):
    if c.get(k):
     identifiers.add(c[k].rsplit("/",1)[-1].split("?")[0])
     if k=="url":used_urls.add(c[k])
 return used_sha,used_urls,identifiers,pin

def download(url,max_bytes=MAX_INPUT_BYTES):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R126-Blind-External-Source/1.0"})
 with urllib.request.urlopen(req,timeout=60) as r:
  data=r.read(max_bytes+1)
 if len(data)>max_bytes:raise ValueError("compressed source exceeds 8MB limit")
 return data
def unpack(data):
 if data.startswith(b"\xfd7zXZ"):f=lzma.LZMAFile(io.BytesIO(data))
 elif data.startswith(b"\x1f\x8b"):f=gzip.GzipFile(fileobj=io.BytesIO(data))
 elif data.startswith(b"BZh"):f=bz2.BZ2File(io.BytesIO(data))
 else:return data
 with f:plain=f.read(MAX_INPUT_BYTES+1)
 if len(plain)>MAX_INPUT_BYTES:raise ValueError("decompressed CNF beyond 8MB")
 return plain

def freeze():
 used,used_urls,ids,pins=provenance()
 dest=ROOT/"holdout";dest.mkdir(exist_ok=True)
 cases=[];excluded=[];index_meta={}
 for cohort,(index,target) in SOURCES.items():
  body=download(index,4_000_000).decode("utf-8")
  urls=sorted(set(s.strip() for s in body.splitlines()
              if s.strip().startswith(("https://","http://"))))
  if not urls:raise RuntimeError("NO_CANDIDATE_URI "+index)
  index_meta[cohort]=dict(uri=index,sha256=sha("\n".join(urls).encode()),
                           count=len(urls),target=target)
  random.Random(PROTO+"-NEW-"+cohort).shuffle(urls)
  num=0
  for url in urls:
   if num>=target:break
   identifier=url.rsplit("/",1)[-1].split("?")[0]
   if identifier in ids or url in used_urls:
    excluded.append(dict(cohort=cohort,identifier=identifier,reason="historically_known_id_or_url"))
    continue
   try:
    raw=download(url)
    plain=unpack(raw)
    if len(plain)>MAX_INPUT_BYTES:raise ValueError("plain CNF size cap")
    digest=sha(plain)
    if digest in used:raise ValueError("previously_used_SHA256")
    if any(c["sha256"]==digest for c in cases):raise ValueError("duplicate_new_SHA256")
    headers=[l.split() for l in plain.splitlines() if l.startswith(b"p cnf ")]
    if len(headers)!=1 or len(headers[0])!=4:raise ValueError("bad DIMACS header")
    n,m=map(int,headers[0][2:])
    if n<=0 or m<=0:raise ValueError("nonpositive DIMACS dimension")
    label=f"{cohort}-{num:03d}.cnf"
    (dest/label).write_bytes(plain)
    cases.append(dict(id=label,cohort=cohort,gbd=identifier,url=url,
       sha256=digest,download_sha256=sha(raw),size=len(plain),variables=n,clauses=m))
    num+=1
    print("R126_NEW_SOURCE",cohort,num,label,identifier,digest[:12],flush=True)
   except Exception as e:
    excluded.append(dict(cohort=cohort,identifier=identifier,
                         reason=(type(e).__name__+": "+str(e))[:150]))
   if len(excluded)>2000:break
 counts=dict(Counter(x["cohort"] for x in cases))
 m=dict(protocol=PROTO,phase="frozen_untouched_holdout",cases=cases,
   counts=counts,shards=SHARDS,repetitions=REPS,cap_seconds=CAP,
   source_index=index_meta,historical_manifest_sha256=pins,excluded=excluded,
   sampling="precommitted seeded shuffle of public GBD URI indexes, exclude by source SHA and URI, no solver timing filters",
   purpose="Unmeasured external holdout; only evaluate after cap selection from R125 calibration",
   caution="Exclusions cover R120-R125 plus historical pinned IDs; not exhaustively all earlier DRNAS experiments")
 (dest/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
 print("R126_HOLDOUT_FROZEN",json.dumps(dict(counts=counts,cases=len(cases),
                                            excluded=len(excluded))),flush=True)
 if len(cases)<30 or counts.get("miter",0)<12 or counts.get("official2025",0)<15:
  raise RuntimeError("R126_UNDERPOWERED_HOLDOUT_FREEZE")

def timer_handler(signum,frame):
 raise TimeoutError("R126_TOTAL_15_SEC_BUDGET")

def trial(source,mode,key):
 ensure_binaries()
 assert mode in MODES
 cap=0 if mode=="cap0" else int(mode[3:]) if mode.startswith("cap") else None
 wall=time.perf_counter()
 prep=0.0;audit_seconds=0.0;solver_seconds=0.0
 info=dict(status="TIMEOUT",seconds=CAP,par2=CAP*2,solved=False,
           native={},activated=False,derived=0,
           proof="timeout",prep_seconds=0,proof_seconds=0,solver_seconds=0)
 old_handler=signal.signal(signal.SIGALRM,timer_handler)
 signal.setitimer(signal.ITIMER_REAL,CAP)
 try:
  target=source
  if cap is not None:
   work=ROOT/"tmp";work.mkdir(exist_ok=True)
   extra=work/(key+".aug.cnf")
   proof=work/(key+".tsv")
   for p in (extra,proof):
    if p.exists():p.unlink()
   pstart=time.perf_counter()
   native=invoke_native(source,cap,str(extra) if cap else "-",
                               str(proof) if cap else "-")
   info["native"]=native
   count=native["equivalence_pairs"]
   if cap and count>0:
    if not extra.is_file() or not proof.is_file():
     raise RuntimeError("missing necessary proof output")
    astart=time.perf_counter()
    audit=old.verify_augmentation(source,extra,proof)
    audit_seconds=time.perf_counter()-astart
    assert audit["derived_pairs"]==count
    target=extra
    info["proof"]="exhaustive_original_clause_implication_check"
    info["activated"]=True
    info["derived"]=count
   else:
    assert not extra.exists(),("unexpected augmentation",key)
    info["proof"]="fallback_original"
   prep=time.perf_counter()-pstart
  else:
   info["proof"]="raw_kissat"
  remaining=CAP-(time.perf_counter()-wall)
  if remaining<=0:raise TimeoutError("budget exhausted in preprocessing")
  runstart=time.perf_counter()
  p=subprocess.run([str(KISSAT),str(target)],capture_output=True,timeout=remaining)
  solver_seconds=time.perf_counter()-runstart
  if p.returncode not in (10,20):
   raise RuntimeError("KISSAT_ERROR "+str(p.returncode)+" "+
                      p.stderr[-250:].decode(errors="replace"))
  status="SAT" if p.returncode==10 else "UNSAT"
  if status=="SAT":
   from r118_xor_paired_real import parse_cnf,check_sat_model
   n,clauses=parse_cnf(source.read_bytes())
   check_sat_model(p.stdout,n,clauses)
   info["source_witness"]="verified_original_clause_SAT_model"
  else:info["source_witness"]="UNSAT_solver_search_not_independently_proved"
  dt=time.perf_counter()-wall
  if dt>CAP:raise TimeoutError("post-solver proof budget exceeded")
  info.update(status=status,seconds=round(dt,6),par2=round(dt,6),solved=True)
 except (TimeoutError,subprocess.TimeoutExpired):
  info["source_witness"]="timeout"
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  signal.signal(signal.SIGALRM,old_handler)
  info["prep_seconds"]=round(prep,6)
  info["proof_seconds"]=round(audit_seconds,6)
  info["solver_seconds"]=round(solver_seconds,6)
 return info

def case_order(seed,modes):
 order=list(modes)
 random.Random(seed).shuffle(order)
 return order

def execute(phase,shard,selected=None):
 ensure_binaries()
 assert phase in ("calibration","holdout") and 0<=shard<SHARDS
 folder=ROOT/phase
 manifest=json.loads((folder/"manifest.json").read_text())
 cases=manifest["cases"]
 if phase=="calibration":
  assert len(cases)==84,("R125 historical calibration source count mismatch",len(cases))
  modes=MODES
 else:
  assert manifest["protocol"]==PROTO
  selection=json.loads((ROOT/"selection.json").read_text())
  selected=selection["selected_mode"]
  assert selected in EXPERIMENTAL
  modes=("kissat",selected)
 if hasattr(os,"sched_getaffinity"):
  allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
 rows=[]
 for index,c in enumerate(cases):
  if index%SHARDS!=shard:continue
  source=folder/c["id"]
  assert sha_file(source)==c["sha256"],("source tampered",c["id"])
  for rep in range(REPS):
   states=set()
   for mode in case_order(PROTO+phase+c["sha256"]+str(rep),modes):
    key=f"{phase}-{shard}-{c['id']}-{rep}-{mode}"
    result=trial(source,mode,key)
    row=dict(phase=phase,id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
             rep=rep,mode=mode,**result)
    rows.append(row)
    if result["status"]!="TIMEOUT":
     states.add(result["status"])
     if len(states)>1:raise RuntimeError("R126_SAT_UNSAT_CONFLICT "+c["id"]+" "+str(states))
    print("R126_MEASURE",json.dumps(row,sort_keys=True),flush=True)
   (ROOT/f"{phase}-{shard}.json").write_text(json.dumps(rows)+"\n")
 assert len(rows)==len(cases[shard::SHARDS])*REPS*len(modes)
 print("R126_SHARD_PASS",phase,shard,len(rows),flush=True)

def read_complete(phase,modes):
 folder=ROOT/phase
 manifest=json.loads((folder/"manifest.json").read_text())
 cases=manifest["cases"]
 rows=[]
 commits=set();bins=set();cpus=set()
 for i in range(SHARDS):
  p=ROOT/f"{phase}-{i}.json"
  assert p.exists(),("missing shard file",str(p))
  shard=json.loads(p.read_text())
  assert len(shard)==len(cases[i::SHARDS])*REPS*len(modes),("incomplete shard",phase,i)
  rows+=shard
  meta=ROOT/f"{phase}-pin-{i}.json"
  assert meta.is_file(),("missing sha pin",str(meta))
  data=json.loads(meta.read_text())
  commits.add(data["commit"])
  bins.add(json.dumps(data["binaries"],sort_keys=True))
  cpus.add(data["cpu_model"])
 assert len(commits)==len(bins)==1,("mismatched git commit or binaries",commits,len(bins))
 assert len(rows)==len(cases)*REPS*len(modes)
 source={c["id"]:c for c in cases}
 identities=set()
 paired=defaultdict(dict)
 for r in rows:
  assert r["phase"]==phase
  assert r["sha256"]==source[r["id"]]["sha256"]
  assert r["cohort"]==source[r["id"]]["cohort"]
  assert r["mode"] in modes and r["rep"] in (0,1)
  assert r["status"] in ("SAT","UNSAT","TIMEOUT")
  assert abs(r["par2"]-(2*CAP if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4
  key=(r["id"],r["rep"],r["mode"])
  assert key not in identities,("duplicate",key)
  identities.add(key)
  paired[r["id"],r["rep"]][r["mode"]]=r
  assert not r["activated"] or (r["derived"]>0 and r["proof"]=="exhaustive_original_clause_implication_check")
  assert not r["activated"] or r["derived"]<=int(r["mode"][3:])
  if r["status"]=="SAT":
   assert r.get("source_witness")=="verified_original_clause_SAT_model"
 for k,p in paired.items():
  assert set(p)==set(modes),("incomplete paired modes",k)
  assert len({v["status"] for v in p.values()}-{"TIMEOUT"})<=1,("SAT_UNSAT_MISMATCH",k)
 assert len(paired)==len(cases)*REPS
 return cases,rows,paired,dict(commits=list(commits),binary_sha256_file=json.loads(next(iter(bins))),cpu_models=sorted(cpus))

def stats(cases,rows,modes):
 out={}
 for cohort in ("miter","official2025","all"):
  identities=[c["id"] for c in cases if cohort=="all" or c["cohort"]==cohort]
  rs=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
  per={}
  for mode in modes:
   m=[r for r in rs if r["mode"]==mode]
   per[mode]=dict(attempts=len(m),solved=sum(r["status"]!="TIMEOUT" for r in m),
     timeouts=sum(r["status"]=="TIMEOUT" for r in m),
     par2_s=round(sum(r["par2"] for r in m),6),
     activated=sum(r["activated"] for r in m),
     derived=sum(r["derived"] for r in m),
     prep_wall_s=round(sum(r["prep_seconds"] for r in m),6),
     proof_wall_s=round(sum(r["proof_seconds"] for r in m),6),
     solver_wall_s=round(sum(r["solver_seconds"] for r in m),6))
  distribution={c:{mode:sum(r["par2"] for r in rs if r["id"]==c and r["mode"]==mode)
                   for mode in modes} for c in identities}
  comparisons={}
  for mode in modes:
   if mode=="kissat":continue
   baseline=per["kissat"]["par2_s"];current=per[mode]["par2_s"]
   rng=random.Random(PROTO+cohort+mode)
   samples=[]
   for _ in range(1200):
    draw=[rng.choice(identities) for _ in identities]
    baseline_total=sum(distribution[c]["kissat"] for c in draw)
    mode_total=sum(distribution[c][mode] for c in draw)
    if mode_total:samples.append(100*(baseline_total/mode_total-1))
   samples.sort()
   comparisons[mode]=dict(speedup=round(baseline/current,6) if current else None,
     gain_percent=round(100*(baseline/current-1),5) if current else None,
     bootstrap95_gain_percent=[round(samples[int(.025*(len(samples)-1))],4),
                               round(samples[int(.975*(len(samples)-1))],4)] if samples else None,
     formula_wins_ge2x=sum(distribution[c]["kissat"]>=2*distribution[c][mode] for c in identities),
     formula_regressions_ge2x=sum(distribution[c][mode]>=2*distribution[c]["kissat"] for c in identities))
  out[cohort]=dict(formulas=len(identities),by_mode=per,compare=comparisons)
 return out

def calibration_report():
 cases,rows,pairs,pins=read_complete("calibration",MODES)
 by=stats(cases,rows,MODES)
 overall=by["all"]
 best=min(EXPERIMENTAL,key=lambda mode:(overall["by_mode"][mode]["par2_s"],
                                      (0 if mode=="cap0" else int(mode[3:]))))
 bestcmp=overall["compare"][best]
 eligible=(bestcmp["gain_percent"]>0.0 and bestcmp["bootstrap95_gain_percent"][0]>0.0
           and bestcmp["formula_regressions_ge2x"]==0)
 selection=dict(protocol=PROTO,calibration_sha256=sha_file(ROOT/"calibration"/"manifest.json"),
   origin="84 external R125 formulas REUSED for calibration; NOT unseen",
   selected_mode=best,selected_cap=int(best[3:]),
   eligible_for_promotion_on_calibration=eligible,
   decision="lowest total PAR2 among precommitted experimental modes; tie -> smaller cap; no formula-specific or runtime gate",
   promotion_rule="positive gain, positive formula-bootstrap lower bound and no >=2x regressions required",
   source_commits=pins["commits"])
 (ROOT/"selection.json").write_text(json.dumps(selection,indent=2)+"\n")
 report=dict(protocol=PROTO,phase="R125_REUSED_CALIBRATION",formulas=len(cases),
             attempts=len(rows),shards=SHARDS,pins=pins,by_cohort=by,selection=selection)
 (ROOT/"calibration-results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R126_CALIBRATION_FINAL",json.dumps(report),flush=True)
 print("R126_SELECTED_MODE",json.dumps(selection),flush=True)

def holdout_report():
 selection=json.loads((ROOT/"selection.json").read_text())
 mode=selection["selected_mode"]
 assert mode in EXPERIMENTAL
 modes=("kissat",mode)
 cases,rows,pairs,pins=read_complete("holdout",modes)
 by=stats(cases,rows,modes)
 cmp=by["all"]["compare"][mode]
 allowed=(cmp["gain_percent"]>0.0 and cmp["bootstrap95_gain_percent"][0]>0.0
          and cmp["formula_regressions_ge2x"]==0 and
          by["all"]["by_mode"][mode]["solved"]>=by["all"]["by_mode"]["kissat"]["solved"])
 report=dict(protocol=PROTO,phase="NEW_EXTERNAL_UNSEEN_HOLDOUT",
   prospective_formulas=len(cases),attempts=len(rows),shards=SHARDS,
   selected_mode_frozen_from_reused_R125=mode,selected_cap=selection["selected_cap"],
   mode_precommitted_before_holdout_execution=True,
   pins=pins,by_cohort=by,
   verdict=("meets_predeclared_benchmark_acceptance" if allowed else "NOT_PROMOTABLE"),
   source_proof="Every augmentation independently checked against original CNF and all truth combinations of <=4 variables; SAT witness checked against unchanged original",
   unsat_caveat="No independent LRAT proof of Kissat final UNSAT answers",
   scope="Blind only relative to R125 calibration; historical SHA/GBD exclusions not exhaustive across all DRNAS history; external size-biased sample")
 (ROOT/"holdout-results.json").write_text(json.dumps(report,indent=2)+"\n")
 print("R126_FINAL",json.dumps(report),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("command",choices=("controls","freeze","run-calibration","select",
                                    "run-holdout","aggregate-holdout"))
 ap.add_argument("--shard",type=int,default=0)
 args=ap.parse_args()
 {
  "controls":controls,
  "freeze":freeze,
  "run-calibration":lambda:execute("calibration",args.shard),
  "select":calibration_report,
  "run-holdout":lambda:execute("holdout",args.shard),
  "aggregate-holdout":holdout_report,
 }[args.command]()

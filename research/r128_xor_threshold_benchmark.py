#!/usr/bin/env python3
"""R128: precommitted XOR selector thresholds calibrated on R127 reused sources,
then one *frozen* winner on independent SHA-excluded new external CNF.

No changes to V15.3.1, Kissat or frozen R118. SAT witnesses checked against
original CNF. Unproven final UNSAT is explicitly marked unverified.
"""
import argparse, csv, hashlib, json, os, pathlib, random, subprocess, time
from collections import Counter, defaultdict
import r126_equivalence_budget as source_helpers
import r127_early_xor_benchmark as witness_helpers
from r125_native_gate_benchmark import HISTORIC_IDS

ROOT=pathlib.Path("r128")
ROOT.mkdir(exist_ok=True)
PROTO="DRNAS-R128-STRICT-XOR-GATE-CALIBRATE-HOLDOUT-20261105-v1"
CAP=15.0
REPS=2
SHARDS=8
POLICIES=("q8_90","q4_60","q2_25","q1_0")
DEVMODES=("kissat","r118",*POLICIES)
FILTER=pathlib.Path("r128/r128_filter").resolve()
R118=pathlib.Path("r128/r118").resolve()
KISSAT=pathlib.Path("built/bin/kissat_4_0_4").resolve()
CONTROL_SHA="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
SOURCES={
 "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",12),
 "official2025":("https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",14),
 "official2026":("https://satcompetition.github.io/2026/downloads/track_main_2026.uri",14),
}
PRIOR=("r120","r121","r122","r123","r124","r125","r126","r127")

def need(x,msg):
 if not x:raise RuntimeError("R128_AUDIT_REFUSED "+str(msg))
def sha(data):return hashlib.sha256(data).hexdigest()
def shafile(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()
def readjson(p):return json.loads(pathlib.Path(p).read_text())
def writejson(p,data):pathlib.Path(p).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def manifest(phase):return readjson(ROOT/phase/"manifest.json")
def verify_source(m,folder):
 need(m["protocol"] in (PROTO,"DRNAS-R127-CHEAP-EXACT-XOR-FROZEN-20261105-v1"),"manifest protocol")
 cases=m["cases"];sha_set=set();case_ids=set()
 for c in cases:
  path=folder/c["id"];h=c["sha256"]
  need(len(h)==64 and h not in sha_set and c["id"] not in case_ids,"duplicate source SHA or ID")
  need(path.is_file() and shafile(path)==h,"original CNF SHA mismatch "+c["id"])
  sha_set.add(h);case_ids.add(c["id"])
 return cases

def freeze():
 dest=ROOT/"holdout";dest.mkdir(parents=True,exist_ok=True)
 used={CONTROL_SHA};identifiers=set(HISTORIC_IDS);known_urls=set();manifests={}
 for k in PRIOR:
  p=ROOT/"prior"/k/"manifest.json"
  need(p.is_file(),"missing previous SHA ledger "+k)
  d=readjson(p)
  cases=d.get("selected") if k in ("r120","r121") else d.get("cases")
  need(isinstance(cases,list) and bool(cases),"prior manifest invalid "+k)
  manifests[k]=shafile(p)
  for c in cases:
   h=c.get("sha256")
   if h:used.add(h)
   for field in ("gbd","url"):
    val=c.get(field)
    if val:
     val=str(val);identifiers.add(val.rsplit("/",1)[-1].split("?")[0])
     if field=="url":known_urls.add(val)
 old=readjson(ROOT/"prior"/"r127"/"manifest.json")
 need(CONTROL_SHA in {c["sha256"] for c in old["cases"]},"R115 source missing historical ledger")
 candidates=[];excluded=Counter();source_indexes={}
 for cohort,(index,target) in SOURCES.items():
  raw=source_helpers.download(index,4_000_000)
  urls=sorted(set(line.strip() for line in raw.decode("utf-8").splitlines()
                  if line.strip().startswith(("https://","http://"))))
  need(bool(urls),"empty source list "+cohort)
  source_indexes[cohort]=dict(url=index,source_bytes_sha256=sha(raw),uris=len(urls),target=target)
  random.Random(PROTO+"|SOURCE|"+cohort).shuffle(urls)
  count=0
  for url in urls:
   if count>=target:break
   ident=url.rsplit("/",1)[-1].split("?")[0]
   if ident in identifiers or url in known_urls:
    excluded[cohort+"_known_id_or_url"]+=1
    continue
   try:
    raw=source_helpers.download(url);plain=source_helpers.unpack(raw)
    if len(plain)>8_000_000:raise ValueError("size cap")
    h=sha(plain)
    if h in used:raise ValueError("SHA previously seen")
    headers=[x.split() for x in plain.splitlines() if x.startswith(b"p cnf ")]
    if len(headers)!=1 or len(headers[0])!=4:raise ValueError("DIMACS header")
    n,m=map(int,headers[0][2:])
    if min(n,m)<1:raise ValueError("bad dimensions")
    name=cohort+"-"+f"{count:03d}"+".cnf"
    (dest/name).write_bytes(plain)
    candidates.append(dict(id=name,sha256=h,cohort=cohort,gbd=ident,url=url,
       original_raw_sha256=sha(raw),size=len(plain),variables=n,clauses=m,
       novelty="new_external_vs_R120_to_R127"))
    identifiers.add(ident);known_urls.add(url);used.add(h);count+=1
    print("R128_FREEZE_NEW",cohort,name,h[:12],flush=True)
   except Exception as e:
    excluded[cohort+"_download_or_validation"]+=1
   if sum(excluded.values())>3000:break
 counts=Counter(c["cohort"] for c in candidates)
 need(len(candidates)>=16 and sum(counts[x]>=5 for x in SOURCES)>=2,
      "too few SHA-independent holdout formulas "+str(counts))
 need(len({c["sha256"] for c in candidates})==len(candidates),"holdout duplicate SHA")
 need(not {c["sha256"] for c in candidates}&{c["sha256"] for c in old["cases"]},"R127 leakage")
 obj=dict(protocol=PROTO,phase="new_sha_excluded_external_holdout",cases=candidates,
    counts=dict(counts),source_indices=source_indexes,prior_ledger_sha256=manifests,
    excluded_counts=dict(excluded),repetitions=REPS,shards=SHARDS,cap_seconds=CAP,
    precommit="holdout sources frozen without any timing analysis; only development R127 can select thresholds",
    source_limit="8MB compressed/decompressed; external URI sample not official contest scoring")
 writejson(dest/"manifest.json",obj)
 print("R128_HOLDOUT_FROZEN",json.dumps(dict(counts=obj["counts"],formulas=len(candidates))),flush=True)

def controls():
 root=ROOT/"controls";root.mkdir(parents=True,exist_ok=True)
 triples=((1,2,3),(-1,-2,3),(-1,2,-3),(1,-2,-3))
 def make(name,clauses):
  p=root/(name+".cnf")
  p.write_text(f"p cnf 30 {len(clauses)}\n"+"".join(" ".join(map(str,t))+" 0\n" for t in clauses))
  return p
 positive=[]
 for k in range(9):
  offset=3*k
  for cl in triples:
   positive.append(tuple((1 if x>0 else -1)*(abs(x)+offset) for x in cl))
 good=make("nine_distinct_complete_xors",positive)
 neg=make("nine_missing_one_clause",positive[0:3]+positive[4:7]+positive[8:11])
 results=[]
 for file in (good,neg):
  for policy in POLICIES:
   r=subprocess.run([str(FILTER),str(file),str(R118),str(KISSAT),policy,"--probe-only"],
                    capture_output=True,text=True,timeout=4)
   need(r.returncode==0 and "c R128_PREFILTER policy="+policy in r.stdout,"probe execution")
   selected="route=GF2" in r.stdout
   expected=(file==good)
   need(selected==expected,"complete XOR positive or incomplete negative control "+policy)
   results.append(dict(case=file.name,policy=policy,GF2_selected=selected,probe=r.stdout.strip()))
 writejson(root/"controls.json",dict(protocol=PROTO,results=results))
 print("R128_EXACT_XOR_CONTROLS_PASS",len(results),flush=True)

def run_one(src,mode,rep,phase):
 if mode=="kissat":cmd=[str(KISSAT),str(src)]
 elif mode=="r118":cmd=[str(R118),str(src),str(KISSAT)]
 elif mode in POLICIES:cmd=[str(FILTER),str(src),str(R118),str(KISSAT),mode]
 else:raise RuntimeError("unexpected mode")
 t=time.perf_counter();std=b"";status="TIMEOUT";filter_triggered=False;GF2_solved=False;route="timeout";proof="timeout"
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  elapsed=time.perf_counter()-t
  need(p.returncode in (10,20),"solver exit failure "+str(p.returncode)+" "+p.stderr[-400:].decode(errors="replace"))
  std=p.stdout
  if mode in POLICIES:
   need(b"c R128_PREFILTER policy="+mode.encode()+b" route=" in std,"missing prefilter telemetry")
   filter_triggered=(b"c R128_PREFILTER policy="+mode.encode()+b" route=GF2" in std)
  GF2_solved=bool(b"c R118_ROUTE certified_pure_xor_sat" in std or
                   b"c R118_ROUTE certified_xor_contradiction" in std)
  status="SAT" if p.returncode==10 else "UNSAT"
  if status=="SAT":
   witness_helpers.check_original_sat(std,src)
   proof="source_SAT_witness_verified"
  else:proof="UNSAT_without_independent_LRAT_proof"
  if elapsed>CAP:status="TIMEOUT";proof="timeout"
  route=("GF2_verified" if GF2_solved else "selected_R118_fallback" if filter_triggered else
         "KISSAT_fallback_or_direct")
 except subprocess.TimeoutExpired as e:
  elapsed=CAP
  std=e.stdout or b""
  if mode in POLICIES:
   filter_triggered=(b"c R128_PREFILTER policy="+mode.encode()+b" route=GF2" in std)
 elapsed=min(CAP,time.perf_counter()-t if status!="TIMEOUT" else CAP)
 return dict(mode=mode,repeat=rep,status=status,seconds=round(elapsed,6),
   par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
   proof=proof,route=route,selected_R118=filter_triggered,GF2_solved=GF2_solved)

def modes_for(phase):
 if phase=="development":return DEVMODES
 frozen=readjson(ROOT/"selection.json")
 need(frozen["protocol"]==PROTO and frozen["selected_policy"] in POLICIES,"selection not frozen")
 return ("kissat","r118",frozen["selected_policy"])

def benchmark(phase,shard):
 need(phase in ("development","holdout") and 0<=shard<SHARDS,"invalid phase/shard")
 folder=ROOT/phase;m=manifest(phase);cases=verify_source(m,folder)
 modes=modes_for(phase)
 need(len(cases)>10,"too few formula cases")
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 results=[]
 for i,c in enumerate(cases):
  if i%SHARDS!=shard:continue
  src=folder/c["id"]
  for rep in range(REPS):
   policies=list(modes);random.Random(PROTO+phase+c["sha256"]+str(rep)).shuffle(policies)
   votes=set()
   for mode in policies:
    x=run_one(src,mode,rep,phase)
    r=dict(phase=phase,id=c["id"],cohort=c["cohort"],sha256=c["sha256"],**x)
    results.append(r)
    if r["status"]!="TIMEOUT":
     votes.add(r["status"])
     need(len(votes)<=1,"SAT/UNSAT status contradiction across paired solvers")
    print("R128_MEASURE",json.dumps(r,sort_keys=True),flush=True)
    writejson(ROOT/(phase+"-"+str(shard)+".json"),results)
 need(len(results)==len(cases[shard::SHARDS])*REPS*len(modes),"incomplete shard")
 print("R128_SHARD_PASS",phase,shard,len(results),flush=True)

def read_complete(phase):
 folder=ROOT/phase;m=manifest(phase)
 need(m["protocol"] in (PROTO,"DRNAS-R127-CHEAP-EXACT-XOR-FROZEN-20261105-v1"),"phase manifest protocol")
 cases=verify_source(m,folder);modes=modes_for(phase)
 need(len({c["sha256"] for c in cases})==len(cases),"SHA duplicate")
 rows=[];commits=set();binpins=set();cpus=set()
 for i in range(SHARDS):
  p=ROOT/(phase+"-"+str(i)+".json")
  need(p.is_file(),"missing "+phase+" shard "+str(i))
  part=readjson(p)
  need(len(part)==len(cases[i::SHARDS])*REPS*len(modes),"incomplete shard "+str(i))
  pin=readjson(ROOT/(phase+"-pin-"+str(i)+".json"))
  commits.add(pin["commit"]);binpins.add(json.dumps(pin["binaries"],sort_keys=True));cpus.add(pin["cpu"])
  rows.extend(part)
 need(len(commits)==len(binpins)==1,"mismatched source commits or solver binaries")
 need(len(rows)==len(cases)*REPS*len(modes),"total measurements")
 ids={c["id"]:c for c in cases};seen=set();pairs=defaultdict(dict)
 for r in rows:
  c=ids.get(r["id"])
  need(c and c["sha256"]==r["sha256"] and c["cohort"]==r["cohort"],"source SHA/cohort mismatch")
  need(r["phase"]==phase and r["repeat"] in (0,1) and r["mode"] in modes,"mode/rep")
  need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"status invalid")
  need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<0.000001,"PAR2 invalid")
  need(r["status"]!="SAT" or r["proof"]=="source_SAT_witness_verified","SAT model unchecked")
  if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT_proof","UNSAT proof claim not grounded")
  key=(r["id"],r["repeat"],r["mode"])
  need(key not in seen,"duplicate trial");seen.add(key)
  pairs[(r["id"],r["repeat"])][r["mode"]]=r
 need(len(pairs)==len(cases)*REPS and all(set(g)==set(modes) for g in pairs.values()),"paired matrix incomplete")
 for p in pairs.values():
  need(len({r["status"] for r in p.values()}-{"TIMEOUT"})<=1,"paired SAT/UNSAT contradiction")
 return cases,rows,pairs,dict(commits=sorted(commits),bins=json.loads(next(iter(binpins))),cpus=sorted(cpus))

def score(cases,pairs,modes,seed):
 stats={}
 for mode in modes:
  rs=[p[mode] for c in cases for rep in range(REPS) for p in [pairs[(c["id"],rep)]]]
  stats[mode]=dict(attempts=len(rs),solved=sum(r["status"]!="TIMEOUT" for r in rs),
   par2_s=round(sum(r["par2"] for r in rs),6),
   timeout=sum(r["status"]=="TIMEOUT" for r in rs),
   filter_triggered=sum(r["selected_R118"] for r in rs),
   GF2_solved=sum(r["GF2_solved"] for r in rs))
 by_formula={c["id"]:{mode:sum(pairs[(c["id"],rep)][mode]["par2"] for rep in range(REPS)) for mode in modes} for c in cases}
 comp={}
 for mode in modes:
  if mode=="kissat":continue
  base=stats["kissat"]["par2_s"];cur=stats[mode]["par2_s"]
  rng=random.Random(PROTO+"|BOOT|"+seed+"|"+mode)
  bootstrap=[]
  for _ in range(1000):
   sample=[rng.choice(cases)["id"] for c in cases]
   b=sum(by_formula[x]["kissat"] for x in sample)
   t=sum(by_formula[x][mode] for x in sample)
   if t:bootstrap.append(100*(b/t-1))
  bootstrap.sort()
  comp[mode]=dict(gain_percent=round(100*(base/cur-1),5) if cur else None,
   bootstrap95_gain_percent=[round(bootstrap[int(.025*(len(bootstrap)-1))],5),
                              round(bootstrap[int(.975*(len(bootstrap)-1))],5)] if bootstrap else None,
   wins_ge2x=sum(by_formula[c["id"]]["kissat"]>=2*by_formula[c["id"]][mode] for c in cases),
   regressions_ge2x=sum(by_formula[c["id"]][mode]>=2*by_formula[c["id"]]["kissat"] for c in cases))
 return dict(formulas=len(cases),stats=stats,compare=comp)

def select():
 cases,rows,pairs,pins=read_complete("development")
 need(len(cases)==27,"expected 26 R127 reused external + 1 historical R115")
 calibration=[c for c in cases if c["cohort"]!="r115_control"]
 control=[c for c in cases if c["cohort"]=="r115_control"]
 need(len(calibration)==26 and len(control)==1 and control[0]["sha256"]==CONTROL_SHA,
      "R115 control must not influence threshold selection")
 s=score(calibration,pairs,DEVMODES,"reused_r127_dev")
 by_cohort={cohort:score([c for c in calibration if c["cohort"]==cohort],pairs,DEVMODES,cohort)
            for cohort in sorted({c["cohort"] for c in calibration})}
 positives=[name for name in POLICIES if
            s["compare"][name]["gain_percent"]>0 and
            s["compare"][name]["bootstrap95_gain_percent"][0]>0 and
            s["compare"][name]["regressions_ge2x"]==0 and
            s["stats"][name]["solved"]>=s["stats"]["kissat"]["solved"]]
 # Frozen fallback when no independently promising calibration signal exists.
 candidate=min(positives,key=lambda n:(s["stats"][n]["par2_s"],POLICIES.index(n))) if positives else "q8_90"
 chosen=dict(protocol=PROTO,selected_policy=candidate,
    selection_basis="R127 26 reused external examples, not unseen",
    r115_control_excluded=True,
    eligible_for_prospective_trial=True,
    positive_development_candidates=positives,
    development_justifies_promotion=bool(positives),
    development_source_sha256=shafile(ROOT/"development"/"manifest.json"),
    source_commits=pins["commits"],
    rule="only positive development paired PAR2, positive formula-bootstrap lower95, no >=2x regression and no solved loss; otherwise strict q8_90 fallback")
 writejson(ROOT/"selection.json",chosen)
 result=dict(protocol=PROTO,phase="reused_R127_development",
             mode_pins=pins,summary=s,by_cohort=by_cohort,
             control=score(control,pairs,DEVMODES,"historical_R115"),
             selection=chosen,formulas=len(cases),attempts=len(rows))
 writejson(ROOT/"development-results.json",result)
 print("R128_DEVELOPMENT_FINAL",json.dumps(result,sort_keys=True),flush=True)
 print("R128_SELECTED_POLICY",json.dumps(chosen,sort_keys=True),flush=True)

def aggregate():
 cases,rows,pairs,pins=read_complete("holdout")
 dev=readjson(ROOT/"development-results.json")
 selected=readjson(ROOT/"selection.json")
 need(selected==dev["selection"],"development selection differs from pinned holdout")
 mode=selected["selected_policy"]
 need(mode in POLICIES,"unexpected policy")
 modes=("kissat","r118",mode)
 by_cohort={cohort:score([c for c in cases if c["cohort"]==cohort],pairs,modes,cohort)
            for cohort in sorted({c["cohort"] for c in cases})}
 overall=score(cases,pairs,modes,"independent_new_holdout")
 cmp=overall["compare"][mode]
 promoted=cmp["gain_percent"]>0 and cmp["bootstrap95_gain_percent"][0]>0 and \
     cmp["regressions_ge2x"]==0 and overall["stats"][mode]["solved"]>=overall["stats"]["kissat"]["solved"]
 verdict="MEETS_PREDECLARED_METRIC" if promoted else "NOT_PROMOTABLE"
 report=dict(protocol=PROTO,phase="independent_sha_excluded_external_holdout",
    full_complete_shard_and_SHA_audit=True,development_source_sha256=shafile(ROOT/"development"/"manifest.json"),
    holdout_source_sha256=shafile(ROOT/"holdout"/"manifest.json"),
    selection=selected,summary=overall,by_cohort=by_cohort,
    formulas=len(cases),attempts=len(rows),shards=SHARDS,pins=pins,
    verdict=verdict,no_claim_of_official_contest_score=True,
    historical_sha_exclusions_limited_to_R120_through_R127=True,
    verified_sat_model_against_original_cnf=True,
    unverified_unsat_without_independent_LRAT=True,
    V1531_untouched=True)
 writejson(ROOT/"holdout-results.json",report)
 with (ROOT/"paired.csv").open("w",newline="") as f:
  w=csv.writer(f);w.writerow(("cohort","formula_sha256","rep","selected_policy","selected_PAR2_s",
                             "kissat_PAR2_s","r118_PAR2_s","selected_gate_triggered","selected_GF2_solved"))
  idx={c["id"]:c for c in cases}
  for (id,rep),p in sorted(pairs.items()):
   w.writerow((idx[id]["cohort"],idx[id]["sha256"],rep,mode,p[mode]["par2"],
               p["kissat"]["par2"],p["r118"]["par2"],p[mode]["selected_R118"],p[mode]["GF2_solved"]))
 print("R128_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("command",choices=("freeze","controls","development","select","holdout","aggregate"))
 ap.add_argument("--shard",type=int,default=0)
 args=ap.parse_args()
 {"freeze":freeze,"controls":controls,
  "development":lambda:benchmark("development",args.shard),
  "select":select,
  "holdout":lambda:benchmark("holdout",args.shard),
  "aggregate":aggregate}[args.command]()

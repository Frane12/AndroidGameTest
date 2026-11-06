#!/usr/bin/env python3
"""DRNAS R158x: causal native CaDiCaL-GF2 development experiment.

Freeze before solver timing: 4 original mixed (crypto/miter), 2 complete
XOR, 1 XOR+unit and 1 nonxor original R154 SHA CNF; already exposed.
Five modes of SAME native CaDiCaL binary: clean, GF2 shadow,
full R157 direct, boundary direct no gate, boundary component feedback.
Native CaDiCaL Terminator + statistics() recover actual CDCL counters even
after 15-second UNKNOWN: conflicts, decisions, learned, propagations.
No false "GF2 proposal = useful new conflict" inference.
"""
import argparse,collections,hashlib,json,os,pathlib,random,re,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r157_source_certified_xor as cert
ROOT=pathlib.Path("r162");FROZEN=ROOT/"frozen"
PROTO="DRNAS-R162-COMPONENT-FEEDBACK-CAUSAL-20261106-v1"
MODES=("clean","shadow_boundary","direct_full","direct_boundary_nogate","direct_feedback")
SHARDS=4;REPS=2
def need(c,msg):
 if not c:raise RuntimeError("R162_AUDIT_FAIL "+str(msg))
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def rd(p):return json.loads(pathlib.Path(p).read_text())
def wr(p,data):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def sources():
 m=rd(FROZEN/"manifest.json")
 need(len(m["cases"])==25 and m["cohort_counts"].get("mixed_residual")==4,"frozen original source mismatch")
 cohorts=(("mixed_residual",4),("complete_xor",2),("xor_plus_units",1),("nonxor_control",1))
 out=[]
 for cohort,limit in cohorts:
  a=sorted([c for c in m["cases"] if c["cohort"]==cohort],key=lambda c:c["id"])
  need(len(a)>=limit,"cohort source shortage "+cohort)
  out+=a[:limit]
 need(len(out)==8 and len({c["sha256"] for c in out})==8,"distinct originals required")
 for c in out:need(h(FROZEN/(c["id"]+".cnf"))==c["sha256"],"original source SHA mismatch "+c["id"])
 return out
def dimacs(path):
 n=None;wanted=None;cl=[];current=[]
 for line in pathlib.Path(path).read_text().splitlines():
  if not line.strip() or line.lstrip().startswith(("c","%")):continue
  if line.startswith("p "):
   a=line.split();need(len(a)==4 and a[1]=="cnf","source header")
   n,wanted=int(a[2]),int(a[3]);continue
  for val in map(int,line.split()):
   if val:current.append(val)
   else:cl.append(tuple(current));current=[]
 need(n is not None and not current and len(cl)==wanted,"source parse mismatch")
 return n,cl
def independent_cert(c,ev):
 path=FROZEN/(c["id"]+".cnf")
 need(ev["source_sha256"]==h(path),"certificate original SHA mismatch")
 n,clauses=dimacs(path)
 need(n==ev["variables"] and len(clauses)==ev["clauses"],"certificate structure drift")
 groups=collections.defaultdict(set);units={}
 for clause in clauses:
  if len(clause)==1:
   lit=clause[0];var=abs(lit);rhs=int(lit>0)
   need(var not in units or units[var]==rhs,"contradictory source units in certificate subset")
   units[var]=rhs
  if not 2<=len(clause)<=6 or len({abs(v) for v in clause})!=len(clause):continue
  lis=sorted(clause,key=abs);vs=tuple(abs(x) for x in lis)
  groups[vs].add(sum(1<<i for i,x in enumerate(lis) if x<0))
 for e in ev["selected"]:
  vs=tuple(e["source_vars"]);rhs=e["source_rhs"]
  need(2<=len(vs)<=6 and tuple(sorted(set(vs)))==vs,"source XOR row malformed")
  target={i for i in range(1<<len(vs)) if i.bit_count()%2==(1-rhs)}
  need(target<=groups[vs],"GF2 source equation NOT implied")
  rem=tuple(v for v in vs if v not in units)
  altered=rhs
  for v in vs:
   if v in units:altered^=units[v]
  need(tuple(e["vars"])==rem and e["rhs"]==altered,"GF2 unit substitution invalid")
def boundary(ev,limit=32):
 # Source-only greedy diversification: avoid choosing 32 variants all
 # dominated by the same high-degree XOR variable. All are certified.
 chosen=[];seen=set();pool=ev["selected"][:]
 while pool and len(chosen)<limit:
  def score(e):
   vs=e["vars"]
   novelty=sum(1 for v in vs if v not in seen)/len(vs)
   overlap_penalty=sum(1 for v in vs if v in seen)/len(vs)
   return (e["residual_importance"]*(1.+0.25*novelty)/
           (1.+0.70*overlap_penalty),-len(vs),tuple(vs))
  win=max(pool,key=score)
  chosen.append(win);seen.update(win["vars"]);pool.remove(win)
 return chosen
def render(rows):
 return "".join(f'{len(e["vars"])} {e["rhs"]} '+' '.join(map(str,e["vars"]))+"\n" for e in rows)
def prepare(c):
 src=FROZEN/(c["id"]+".cnf")
 f=ROOT/("full-"+c["id"]+".tsv")
 evfile=ROOT/("cert-"+c["id"]+".json")
 t=time.perf_counter()
 ev=cert.extract(src,f,evfile)
 independent_cert(c,ev)
 b=boundary(ev)
 bfile=ROOT/("boundary-"+c["id"]+".tsv")
 bfile.write_text(render(b))
 need(f.read_text()==render(ev["selected"]),"frozen full rows serialization mismatch")
 info=dict(id=c["id"],source_sha256=c["sha256"],full_rows=len(ev["selected"]),
           boundary_rows=len(b),full_tsv_sha=h(f),boundary_tsv_sha=h(bfile),
           certificate_sha=h(evfile),preprocessing_s=round(time.perf_counter()-t,6),
           diverse_boundary_vars=len(set(v for e in b for v in e["vars"])))
 wr(ROOT/("prep-"+c["id"]+".json"),info)
 print("R162_SOURCE_PROOF_PASS",json.dumps(info,sort_keys=True),flush=True)
 return info
def parse_native(output,mode):
 txt=output.decode(errors="replace")
 start=re.search(r"^R162_START mode=(\w+) source_rows=(\d+) derived_rows=(\d+) clauses=(\d+) cap_s=([0-9.]+)$",txt,re.M)
 done=re.search(r"^R162_RESULT ([^\n]+)$",txt,re.M)
 b=re.search(r"^R162_STATS_BEGIN mode=(\w+)$",txt,re.M)
 e=re.search(r"^R162_STATS_END mode=(\w+)$",txt,re.M)
 need(start and done and b and e and b.start()<e.start() and b[1]==e[1]==mode,"native native-CDCL solver stats incomplete")
 stat_block=txt[b.end():e.start()]
 stats={}
 for key in ("conflicts","decisions","learned","propagations"):
  vals=re.findall(r"(?:^|\n)\s*(?:c\s+)?"+key+r":\s+(\d+)\b",stat_block,re.M)
  stats[key]=int(vals[-1]) if vals else None
 telemetry=dict(re.findall(r"(\w+)=([^\s]+)",done[1]))
 need(telemetry.get("mode")==mode and start[1]==mode,"native mode mismatch")
 need(telemetry.get("disabled")=="0","GF2 runtime disabled reason invariant")
 need(telemetry.get("status") in ("SAT","UNSAT","UNKNOWN"),"invalid native status")
 return txt,telemetry,stats,int(start[2]),int(start[3])
def sat_check(path,txt):
 _,clauses=dimacs(path)
 vals={}
 for line in txt.splitlines():
  if not line.startswith("v "):continue
  for val in map(int,line[2:].split()):
   if val:
    need(abs(val) not in vals or vals[abs(val)]==(val>0),"inconsistent source model")
    vals[abs(val)]=(val>0)
 need(vals and all(any(vals.get(abs(v))==(v>0) for v in cl) for cl in clauses),
      "independent SAT witness NOT valid on original SHA CNF")
def trial(c,mode,rep,prep,binary):
 src=FROZEN/(c["id"]+".cnf")
 need(h(src)==c["sha256"],"source altered before solving")
 bound=mode not in ("clean","direct_full")
 tsv=ROOT/(("boundary-" if bound else "full-")+c["id"]+".tsv")
 need(h(tsv)==prep["boundary_tsv_sha" if bound else "full_tsv_sha"],"source row pin changed")
 cap=15.0 if c["cohort"]=="mixed_residual" else 5.0
 charge=0.0 if mode=="clean" else prep["preprocessing_s"]
 need(cap-charge>=1.0,"preprocessing consumed all source budget")
 effective=cap-charge
 begin=time.perf_counter()
 try:
  p=subprocess.run([str(binary.resolve()),mode,str(src.resolve()),str(tsv.resolve()),str(effective)],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+12)
 except subprocess.TimeoutExpired as exc:
  raise RuntimeError("R162_HARD_TIMEOUT: native Terminator did not return or stats inaccessible "+str(c["id"])) from exc
 elapsed=time.perf_counter()-begin+charge
 need(p.returncode in (0,10,20),"fatal C++ error "+str(p.returncode)+" "+p.stderr[-700:].decode(errors="replace"))
 txt,native,stats,nrows,derived=parse_native(p.stdout,mode)
 status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
 need(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"solver exit/result inconsistent")
 need(nrows==(0 if mode=="clean" else prep["boundary_rows"] if bound else prep["full_rows"]),"GF2 source rows provenance mismatch")
 if status=="SAT":
  need(native.get("source_sat_witness_checked")=="1","native SAT source validation missing")
  sat_check(src,txt)
 need(abs(float(native["solver_s"])-(elapsed-charge))<0.5,"native CPU time/outer wall mismatch")
 needed=("assignments","backtracks","rows_scanned","watch_lookups","direct_proposals",
        "reason_clauses_completed","direct_reason_requests","direct_reason_lits",
        "shadow_candidates","adaptive_gate_events","component_count","component_gate_events",
         "blocked_components","suppressed_rows","components_with_reasons","propagate_calls","propagate_ns")
 dt={k:int(native[k]) for k in needed}
 need(dt["reason_clauses_completed"]<=dt["direct_reason_requests"],"reason accounting invalid")
 if mode in ("clean","watch_boundary","shadow_boundary"):
  need(dt["direct_proposals"]==0,"non-direct mode proposed external GF2")
 need(dt["adaptive_gate_events"]==0,"legacy global gate must remain disabled in R162")
 if mode!="direct_feedback":
  need(dt["component_gate_events"]==0 and dt["blocked_components"]==0,"gate activated in control mode")
 else:
  need(dt["component_gate_events"]==dt["blocked_components"],"component gate accounting mismatch")
 need(dt["components_with_reasons"]<=dt["component_count"],"component reason accounting invalid")
 if c["cohort"]=="mixed_residual":
  need(stats["conflicts"] is not None and stats["decisions"] is not None,
    "missing genuine CaDiCaL native conflict/decision metrics on hard mixed")
 return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],family=c["family"],
  mode=mode,repeat=rep,status=status,source_rows=nrows,derived_rows=derived,
  elapsed=round(elapsed,6),charged_preprocess_s=round(charge,6),
  par2=round(2*cap if status=="TIMEOUT" else min(cap,elapsed),6),cap=cap,
  proof="SOURCE_SAT_INDEPENDENT_CHECK" if status=="SAT" else "UNSAT_UNVERIFIED_LRAT" if status=="UNSAT" else "TIMEOUT",
  native_stats=stats,**dt)
def shard(idx,binary):
 need(idx in range(SHARDS),"bad shard")
 sourceset=sources();need(binary.is_file(),"missing pinned native binary")
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 allrows=[]
 for j,c in enumerate(sourceset):
  if j%SHARDS!=idx:continue
  prep=prepare(c)
  for rep in range(REPS):
   modes=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
   for mode in modes:
    row=trial(c,mode,rep,prep,binary)
    allrows.append(row);wr(ROOT/f"shard-{idx}.json",allrows)
    print("R162_TRIAL",json.dumps(row,sort_keys=True),flush=True)
 need(len(allrows)==len([1 for j in range(8) if j%SHARDS==idx])*len(MODES)*REPS,"shard incomplete")
 print("R162_SHARD_PASS",idx,len(allrows),flush=True)
def audit():
 cases=sources();rows=[];keys=set();pins=[];preps={}
 for idx in range(SHARDS):
  shard_rows=rd(ROOT/f"shard-{idx}.json")
  pin=rd(ROOT/f"pin-{idx}.json")
  pins.append(pin)
  need(len(shard_rows)==len(MODES)*REPS*2,"incomplete shard")
  for z in shard_rows:
   c=next((c for c in cases if c["id"]==z["id"]),None)
   need(c is not None and c["sha256"]==z["sha256"],"original SHA changed in benchmark")
   key=(z["id"],z["repeat"],z["mode"])
   need(key not in keys,"duplicate paired trial");keys.add(key)
   need(abs(z["par2"]-(2*z["cap"] if z["status"]=="TIMEOUT" else min(z["cap"],z["elapsed"])))<0.00003,"PAR2 score invalid")
   need(z["status"]!="SAT" or z["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK","missing source SAT evidence")
   rows.append(z)
 for c in cases:
  pr=rd(ROOT/("prep-"+c["id"]+".json"));ev=rd(ROOT/("cert-"+c["id"]+".json"))
  independent_cert(c,ev)
  full=render(ev["selected"]);bd=render(boundary(ev))
  need(h(FROZEN/(c["id"]+".cnf"))==c["sha256"],"original CNF SHA bad at audit")
  need(hashlib.sha256(full.encode()).hexdigest()==pr["full_tsv_sha"],"full exact source rows changed")
  need(hashlib.sha256(bd.encode()).hexdigest()==pr["boundary_tsv_sha"],"boundary chosen from different source")
  preps[c["id"]]=pr
  matching=[z for z in rows if z["id"]==c["id"]]
  need(len(matching)==REPS*len(MODES),"missing same-formula comparisons")
  need(len({z["status"] for z in matching if z["status"]!="TIMEOUT"})<=1,"SAT/UNSAT contradictory solver answers")
 need(len(rows)==8*len(MODES)*REPS and len(keys)==len(rows),"total paired trial count not 80")
 hashes={p["binary_sha256"] for p in pins}
 need(len(hashes)==1 and all(p["binary_sha256"]==rd(ROOT/"build-pin.json")["binary_sha256"] for p in pins),
   "single native binary SHA mismatch across 4 shards")
 need(len({p["commit"] for p in pins})==1,"source commit drift")
 group={}
 for cohort in ["all"]+sorted({c["cohort"] for c in cases}):
  group[cohort]={}
  arr=[z for z in rows if cohort=="all" or z["cohort"]==cohort]
  for mode in MODES:
   v=[z for z in arr if z["mode"]==mode]
   def ss(k):return sum(z["native_stats"][k] or 0 for z in v)
   group[cohort][mode]=dict(trials=len(v),solved=sum(z["status"]!="TIMEOUT" for z in v),
    PAR2_s=round(sum(z["par2"] for z in v),6),
    conflicts=ss("conflicts"),decisions=ss("decisions"),search_propagations=ss("propagations"),
    learned_clauses=ss("learned"),
    proposed_GF2=sum(z["direct_proposals"] for z in v),
    completed_reason_clauses=sum(z["reason_clauses_completed"] for z in v),
    shadow_candidates=sum(z["shadow_candidates"] for z in v),
    adaptive_gate_events=sum(z["adaptive_gate_events"] for z in v),
    source_rows=sum(z["source_rows"] for z in v),
    propagate_ns=sum(z["propagate_ns"] for z in v),
    propagate_calls=sum(z["propagate_calls"] for z in v),
    component_gate_events=sum(z["component_gate_events"] for z in v),
    suppressed_rows=sum(z["suppressed_rows"] for z in v),
    completed_reason_components=sum(z["components_with_reasons"] for z in v))
 for grp in group.values():
  b=grp["clean"]["PAR2_s"]
  for mode in MODES:
   grp[mode]["PAR2_gain_vs_clean_pct"]=round(100*(b-grp[mode]["PAR2_s"])/b,5) if b else None
 report=dict(protocol=PROTO,status="AUDIT_PASS_RESEARCH_ONLY",not_blind=True,
  source_run=42107642696,formulas=len(cases),attempts=len(rows),cap_by_cohort={"mixed_residual":15,"others":5},
  original_source_sha_verified=True,source_GF2_units_independent_replay=True,
  same_single_compiled_native_binary_SHA=next(iter(hashes)),
  pins_by_shard=pins,prepared=preps,summary=group,paired=rows,
  verdict="EXPERIMENT_ONLY_NO_AUTOMATIC_PROMOTION",
  caveats=["Same 8 original R154 source formulas used in prior development; NOT fresh holdout",
   "Native CaDiCaL stats at graceful UNKNOWN show search activity, not direct proof of speedup",
   "Fewer conflicts at equal 15s does not alone mean better solver",
   "R158x chooses rows only from complete CNF parity blocks and source units",
   "UNSAT lacks independent LRAT/FRAT even if same-binary CaDiCaL reports UNSAT",
   "One binary SHA across all shards; CPUs still vary and are recorded",
    "Component gating suppresses optional GF2 work only, not original CNF clauses",
    "Completed reason means CDCL requested a GF2 explanation, not proof of a saved conflict",
    "Callback nanoseconds include measurement overhead in all native modes"])
 wr(ROOT/"report.json",report)
 print("R162_FINAL",json.dumps({"status":report["status"],"formulas":8,"trials":len(rows),"summary":group},sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("action",choices=("shard","audit"));p.add_argument("--shard",type=int,default=0);p.add_argument("--binary")
 args=p.parse_args()
 if args.action=="shard":
  need(args.binary,"no native binary specified")
  shard(args.shard,pathlib.Path(args.binary))
 else:audit()

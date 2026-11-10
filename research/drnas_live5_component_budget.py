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
ROOT=pathlib.Path("live5");FROZEN=ROOT/"frozen"
PROTO="DRNAS-LIVE5-REAL-CDCL-7ARM-3-BUDGETS-8-ORIGINAL-SHA-v1"
MODES=("clean","shadow_boundary","direct_full","direct_boundary_nogate",
       "direct_feedback_512","direct_feedback","direct_feedback_16384")
SHARDS=4;REPS=2
def need(c,msg):
 if not c:raise RuntimeError("LIVE5_AUDIT_FAIL "+str(msg))
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
 print("LIVE5_SOURCE_PROOF_PASS",json.dumps(info,sort_keys=True),flush=True)
 return info
def parse_native(output,mode):
 txt=output.decode(errors="replace")
 start=re.search(r"^LIVE5_START mode=(\w+) source_rows=(\d+) derived_rows=(\d+) clauses=(\d+) cap_s=([0-9.]+)$",txt,re.M)
 done=re.search(r"^LIVE5_RESULT ([^\n]+)$",txt,re.M)
 b=re.search(r"^LIVE5_STATS_BEGIN mode=(\w+)$",txt,re.M)
 e=re.search(r"^LIVE5_STATS_END mode=(\w+)$",txt,re.M)
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
  raise RuntimeError("LIVE5_HARD_TIMEOUT: native Terminator did not return or stats inaccessible "+str(c["id"])) from exc
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
         "blocked_components","suppressed_rows","components_with_reasons","component_scan_threshold",
          "propagate_calls","propagate_ns")
 dt={k:int(native[k]) for k in needed}
 need(dt["reason_clauses_completed"]<=dt["direct_reason_requests"],"reason accounting invalid")
 if mode in ("clean","watch_boundary","shadow_boundary"):
  need(dt["direct_proposals"]==0,"non-direct mode proposed external GF2")
 need(dt["adaptive_gate_events"]==0,"legacy global gate must remain disabled in LIVE5")
 if not mode.startswith("direct_feedback"):
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
def shard(idx,mode,binary):
 need(idx in range(SHARDS) and mode in MODES,"bad source shard/native arm")
 cases=sources()
 need(binary.is_file(),"missing pinned common native executable")
 if hasattr(os,"sched_getaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rows=[]
 for j,c in enumerate(cases):
  if j%SHARDS!=idx:continue
  prep=prepare(c)
  for rep in range(REPS):
   row=trial(c,mode,rep,prep,binary)
   row["shard"]=idx
   rows.append(row)
   wr(ROOT/f"shard-{idx}-{mode}.json",rows)
   print("LIVE5_TRIAL",json.dumps(row,sort_keys=True),flush=True)
 need(len(rows)==4,"2 sources x 2 reps expected per mode+shard")
 print("LIVE5_SHARD_PASS",idx,mode,len(rows),flush=True)

def audit():
 cases=sources()
 rows=[]; seen=set(); pins=[]
 for i in range(SHARDS):
  for mode in MODES:
   fn=ROOT/f"shard-{i}-{mode}.json"
   group=rd(fn)
   need(len(group)==4,"incomplete native GF2 arm/shard "+str(fn))
   pin=rd(ROOT/f"pin-{i}-{mode}.json")
   need(pin["shard"]==i and pin["mode"]==mode,"incorrect job identity pin")
   pins.append(pin)
   for row in group:
    case=next((c for c in cases if c["id"]==row["id"]),None)
    need(case is not None and case["sha256"]==row["sha256"],"wrong original CNF SHA")
    need(row["mode"]==mode and row["shard"]==i and
         0<=row["repeat"]<REPS,"invalid arm/rep/matrix provenance")
    key=(row["id"],row["repeat"],mode)
    need(key not in seen,"duplicate exact source-arm-repetition");seen.add(key)
    need(abs(row["par2"]-(2*row["cap"] if row["status"]=="TIMEOUT" else
         min(row["cap"],row["elapsed"])))<0.00003,"diagnostic PAR2 invalid")
    need(row["status"]!="SAT" or row["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK",
         "native SAT lacks independent original witness")
    need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected solver outcome")
    need(row["component_scan_threshold"]==(
       512 if mode=="direct_feedback_512" else
       16384 if mode=="direct_feedback_16384" else 4096),
       "wrong per-component budget")
    rows.append(row)
 need(len(rows)==len(seen)==8*len(MODES)*REPS,
      "missing observations across 7 x 8 x 2 matrix")
 hashes={p["binary_sha256"] for p in pins}
 need(len(hashes)==1 and
      next(iter(hashes))==rd(ROOT/"build-pin.json")["binary_sha256"],
      "different native executable SHA among parallel matrix arms")
 need(len({p["commit"] for p in pins})==1,
      "incomparable source builds across parallel matrix")
 prepared={}
 for c in cases:
  proof=prepare(c) # rederive source-certified GF2 independently from original SHA
  prepared[c["id"]]=proof
  native_rows=[z for z in rows if z["id"]==c["id"]]
  need(len(native_rows)==len(MODES)*REPS,"unmatched same original CNF")
  reported={z["status"] for z in native_rows if z["status"]!="TIMEOUT"}
  need(len(reported)<=1,"native SAT-v-UNSAT disagreement")
  for z in native_rows:
   need(z["source_rows"]==(
       0 if z["mode"]=="clean" else
       proof["full_rows"] if z["mode"]=="direct_full" else
       proof["boundary_rows"]), "GF2 row provenance changed")
   need(z["cap"]==(15.0 if c["cohort"]=="mixed_residual" else 5.0),
        "wrong cap across cohort")
 # Native CDCL reports UNSAT, but there is NO independent original-CNF
 # LRAT/DRAT from that run. Report it as unverified, and penalize for STRICT PAR2.
 def certified(z):return z["status"]=="SAT" and z["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK"
 def strict_penalty(z):return z["elapsed"] if certified(z) else 2*z["cap"]
 def raw_penalty(z):return z["par2"]
 bykey={(z["id"],z["repeat"],z["mode"]):z for z in rows}
 def compare(a,b):
  delta=[strict_penalty(bykey[(c["id"],r,a)])-
         strict_penalty(bykey[(c["id"],r,b)])
         for c in cases for r in range(REPS)]
  return dict(wins=sum(d<-.02 for d in delta),
      losses=sum(d>.02 for d in delta),ties=sum(abs(d)<=.02 for d in delta),
      net_strict_PAR2_gain_s=round(-sum(delta),6),
      largest_regression_s=round(max(delta),6),
      largest_gain_s=round(-min(delta),6))
 def score(part):
  def ss(k):return sum(z[k] for z in part)
  def ns(k):return sum(z["native_stats"].get(k) or 0 for z in part)
  return dict(trials=len(part),SAT_certified=sum(certified(z) for z in part),
      UNSAT_native_unverified=sum(z["status"]=="UNSAT" for z in part),
      timeouts=sum(z["status"]=="TIMEOUT" for z in part),
      strict_solved=sum(certified(z) for z in part),
      strict_PAR2_s=round(sum(strict_penalty(z) for z in part),6),
      native_status_PAR2_unverified_s=round(sum(raw_penalty(z) for z in part),6),
      native_conflicts=ns("conflicts"),native_decisions=ns("decisions"),
      native_learned=ns("learned"),native_propagations=ns("propagations"),
      GF2_proposals=ss("direct_proposals"),
      GF2_completed_reasons=ss("reason_clauses_completed"),
      GF2_shadow_candidates=ss("shadow_candidates"),
      component_gate_events=ss("component_gate_events"),
      blocked_components=ss("blocked_components"),
      suppressed_rows=ss("suppressed_rows"),
      GF2_callback_ns=ss("propagate_ns"),
      GF2_callback_calls=ss("propagate_calls"),
      original_Gf2_rows=ss("source_rows"))
 summary={}
 for cohort in ["all","mixed_residual","controls"]:
  sub=[z for z in rows if cohort=="all" or
       (z["cohort"]=="mixed_residual" if cohort=="mixed_residual" else z["cohort"]!="mixed_residual")]
  summary[cohort]={mode:score([z for z in sub if z["mode"]==mode]) for mode in MODES}
 for group in summary.values():
  base=group["clean"]["strict_PAR2_s"]
  for mode in MODES:
   v=group[mode]
   v["strict_PAR2_gain_vs_clean_x"]=round(base/v["strict_PAR2_s"],6) if v["strict_PAR2_s"] else None
 report=dict(protocol=PROTO,cohort="eight previously seen R154 ORIGINAL CNF",
   formulas=len(cases),paired_trials=len(rows),native_mode_count=len(MODES),
   one_logical_CPU_per_native_job=True,seven_modes_parallel_matrix=True,
   same_binary_SHA=next(iter(hashes)),real_CaDiCaL_2_1_IPASIR_UP=True,
   source_GF2_independently_certified=True,
   original_SAT_witness_independently_verified=True,
   independent_UNSAT_LRAT=False,UNSAT_not_counted_in_strict_PAR2=True,
   no_auto_promotion=True,not_blind=True,reference_solver="same_binary_clean_CaDiCaL",
   summary=summary,paired_vs_clean={mode:compare(mode,"clean") for mode in MODES if mode!="clean"},
   causal_direct_vs_shadow=compare("direct_boundary_nogate","shadow_boundary"),
   gates_vs_ungated={mode:compare(mode,"direct_boundary_nogate") for mode in MODES if mode.startswith("direct_feedback")},
   per_shard={str(i):{mode:score([z for z in rows if z["shard"]==i and z["mode"]==mode])
                 for mode in MODES} for i in range(SHARDS)},
   pins=pins,prepared=prepared,
   caveats=["Eight known source SHA, not prospective holdout",
    "Reference UNSAT without independent LRAT cannot count as certified E2E",
    "More GF2 proposals or fewer native CDCL conflicts does not alone prove improved solving",
    "Parallel jobs may use different physical hosts despite matched original SHA and pinned logical CPU"])
 wr(ROOT/"report.json",report)
 print("LIVE5_FINAL "+json.dumps({k:v for k,v in report.items() if k not in
             ("pins","prepared","per_shard")},sort_keys=True),flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("action",choices=("shard","audit"))
 p.add_argument("--shard",type=int,default=0)
 p.add_argument("--mode",choices=MODES)
 p.add_argument("--binary")
 args=p.parse_args()
 if args.action=="shard":
  need(args.binary and args.mode,"binary and mode required")
  shard(args.shard,args.mode,pathlib.Path(args.binary))
 else:audit()

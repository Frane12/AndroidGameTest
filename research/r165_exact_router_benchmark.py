#!/usr/bin/env python3
"""R165 auto-XOR router against same-source pinned CaDiCaL clean baseline.

Original R155 25-CNF manifest, source SHA checked. Pure CNF goes through
R164's exhaustive equivalence test and Gaussian solve; MIXED never gets a
GF(2)-only answer. No global record or blind-holdout claim.
For every exact pure XOR formula, repeat native CaDiCaL clean (5s solver
limit) and end-to-end Python exact solver twice, in shuffled paired order.
SAT models independently verified on unchanged original input clauses.
"""
import hashlib,json,os,pathlib,random,re,subprocess,sys,time
ROOT=pathlib.Path("r165")
FROZEN=ROOT/"frozen"
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r164_pure_exact_gf2 as exact
REPS=2
CAP=5.0

def need(ok,why):
 if not ok:raise RuntimeError("R165_ROUTER_AUDIT_FAIL "+str(why))
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,data):pathlib.Path(p).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def native_clean(path,binary,n,clauses):
 beg=time.perf_counter()
 try:
  proc=subprocess.run([str(binary.resolve()),"clean",str(path.resolve()),str((ROOT/"empty-rows.tsv").resolve()),str(CAP)],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP+25)
 except subprocess.TimeoutExpired as err:
  raise RuntimeError("CaDiCaL clean did not honor the source-bound Terminator") from err
 elapsed=time.perf_counter()-beg
 txt=proc.stdout.decode(errors="replace")
 matched=re.search(r"^R165_RESULT mode=clean status=(SAT|UNSAT|UNKNOWN)\b",txt,re.M)
 need(matched is not None and proc.returncode in (0,10,20),
      "native CaDiCaL response or status unavailable "+proc.stderr[-500:].decode(errors="replace"))
 status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[matched[1]]
 need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"native return code not equal status")
 if status=="SAT":
  values={}
  for line in txt.splitlines():
   if not line.startswith("v "):continue
   for v in map(int,line[2:].split()):
    if v:
     need(0<abs(v)<=n and (abs(v) not in values or values[abs(v)]==(v>0)),"malformed SAT model")
     values[abs(v)]=(v>0)
  need(values and all(any(values.get(abs(v))==(v>0) for v in c) for c in clauses),
       "CaDiCaL SAT witness fails ORIGINAL CNF")
 return dict(status=status,elapsed_s=round(elapsed,6),solver_cap_s=CAP,
             proof="ORIGINAL_SOURCE_SAT_VERIFIED" if status=="SAT" else "UNSAT_NOT_INDEPENDENT_NATIVE_PROOF" if status=="UNSAT" else "TIMEOUT")

def main(binary):
 need(binary.is_file(),"no pinned native binary")
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 manifest=json.loads((FROZEN/"manifest.json").read_text())
 cases=manifest["cases"]
 need(len(cases)==25 and len({c["sha256"] for c in cases})==25,"expected 25 distinct SHA sources")
 (ROOT/"empty-rows.tsv").write_text("")
 items=[];paired=[]
 for c in cases:
  src=FROZEN/(c["id"]+".cnf")
  need(h(src)==c["sha256"],"source SHA drift "+c["id"])
  first=exact.solve(src)
  need(first["source_sha256"]==c["sha256"],"router SHA drift")
  items.append(dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],status=first["status"],
                    pure_exact=first["pure_exact"],xor_rows=first["xor_rows"],
                    router_check_s=round(first["elapsed_s"],6),proof=first["proof"]))
  print("R165_ROUTER_CHECK",c["id"],first["status"],flush=True)
  if first["status"]=="NOT_PURE":
   need(not first["pure_exact"],"mixed formula accidentally accepted as pure")
   continue
  n,clauses=exact.parse_dimacs(src)
  for rep in range(REPS):
   modes=["exact","native_clean"]
   random.Random("r165-router-"+c["sha256"]+str(rep)).shuffle(modes)
   trial={}
   for mode in modes:
    if mode=="exact":
     start=time.perf_counter()
     answer=exact.solve(src)
     outer=time.perf_counter()-start
     need(answer["pure_exact"] and answer["status"]==first["status"] and
          answer["model_sha256"]==first["model_sha256"],"exact rerun result changed")
     trial["exact"]=dict(status=answer["status"],elapsed_s=round(outer,6),
       proof=answer["proof"],certificate_rows=answer["certificate_rows"],rank=answer["rank"])
    else:
     trial["native_clean"]=native_clean(src,binary,n,clauses)
   need(trial["native_clean"]["status"] in ("TIMEOUT",first["status"]),
        "CaDiCaL status contradicts pure exact certified answer")
   paired.append(dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
                      repetition=rep,exact=trial["exact"],native_clean=trial["native_clean"]))
   print("R165_ROUTER_PAIRED",json.dumps(paired[-1],sort_keys=True),flush=True)
 need(len([q for q in items if q["pure_exact"]])==13,"R164 pure classification changed")
 need(len(paired)==13*REPS,"missing native+GF2 original source paired measurements")
 counts={k:sum(1 for q in items if q["status"]==k) for k in ("SAT","UNSAT","NOT_PURE")}
 solved_native=sum(z["native_clean"]["status"]!="TIMEOUT" for z in paired)
 exact_total=sum(z["exact"]["elapsed_s"] for z in paired)
 native_total=sum(z["native_clean"]["elapsed_s"] for z in paired)
 # Censored native UNKNOWNs do not establish an exact speed ratio.
 report=dict(status="ROUTER_PAIRED_AUDIT_PASS_RESEARCH_ONLY",input_cases=len(cases),
   cases=items,paired=paired,classification=counts,
   pure_pairs=len(paired),clean_native_solved_pairs=solved_native,
   exact_total_wall_s=round(exact_total,6),native_clean_total_wall_s=round(native_total,6),
   no_false_GF2_answers_on_mixed=True,
   caveats=["Same original 25 R155 sources, development data, NOT blind holdout",
            "Native clean hard caps 5s solver time plus loading; UNKNOWN is censored",
            "Independent original CNF SAT witness checks; UNSAT exact XOR contradiction certificate replays",
            "Exact XOR UNSAT parity proof is not an LRAT/FRAT proof",
            "End-to-end Python code vs native C++ are not hardware-identical implementations",
            "Do not infer world records or uncensored per-case speedup from a native TIMEOUT"])
 save(ROOT/"router-report.json",report)
 print("R165_ROUTER_FINAL",json.dumps({k:report[k] for k in
  ("status","input_cases","classification","pure_pairs","clean_native_solved_pairs",
   "exact_total_wall_s","native_clean_total_wall_s")},sort_keys=True),flush=True)

if __name__=="__main__":
 need(len(sys.argv)==2,"usage: benchmark.py /path/to/native")
 main(pathlib.Path(sys.argv[1]))

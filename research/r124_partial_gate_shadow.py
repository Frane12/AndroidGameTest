#!/usr/bin/env python3
"""R124: frozen-source, shadow-only PARTIAL gate recognition in external SAT CNF.

Detects individually complete Tseitin XOR/AND/OR blocks anywhere in CNF, with
arbitrary variable numbering and signed input/output arcs. No SAT decisions,
unit injection, Kissat changes or solver launches. Independent per-gate
eight-row truth-table audit is required before counting a hit. R123's 160 CNFs
are a REUSED diagnostic corpus, NOT an independent speedup holdout.
"""
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,os,pathlib,random,time
from collections import Counter,defaultdict
P=pathlib.Path("r124");P.mkdir(exist_ok=True)
SOURCE=P/"source"
PROTO="DRNAS-R124-PARTIAL-GATE-SHADOW-20261105-V1"
SEED=12420261105
SHARDS=12
MAX_CANDIDATE_TRIPLES=60000
MAX_GATE_WITNESSES=512
SEARCH_BUDGET_SECONDS=2.0
MAX_CNF_BYTES=8_000_000

def sha(data):return hashlib.sha256(data).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def cl(lits):
 return tuple(sorted(lits))
def clauses_for(op,a,b,z):
 if op=="xor":
  return (cl((a,b,-z)),cl((a,-b,z)),cl((-a,b,z)),cl((-a,-b,-z)))
 if op=="and":
  return (cl((-a,-b,z)),cl((a,-z)),cl((b,-z)))
 if op=="or":
  return (cl((a,b,-z)),cl((-a,z)),cl((-b,z)))
 raise ValueError(op)

def parse_cnf(source):
 """Streaming independent of variable numbering, m/n sparsity and line wrapping."""
 n=None;declared=None;count=0;words=[];two=set();three=set();triples=set();all_len=Counter()
 with open(source,"rt",encoding="ascii",errors="strict") as f:
  for line in f:
   line=line.strip()
   if not line or line.startswith("c"):continue
   if line.startswith("%"):break
   if line.startswith("p "):
    if n is not None:raise ValueError("duplicate CNF header")
    t=line.split()
    if len(t)!=4 or t[1]!="cnf":raise ValueError("bad p cnf header")
    n,declared=int(t[2]),int(t[3])
    if n<=0 or declared<0:raise ValueError("bad dimensions")
    continue
   if n is None:raise ValueError("missing CNF header")
   for token in line.split():
    lit=int(token)
    if lit==0:
     count+=1
     if count>declared:raise ValueError("more clauses than header")
     l=len(words);all_len[min(l,5)]+=1
     if l in (2,3) and len(set(map(abs,words)))==l:
      c=cl(words)
      if l==2:two.add(c)
      else:
       three.add(c)
       triples.add(tuple(sorted(map(abs,words))))
     words=[]
    else:
     if abs(lit)>n:raise ValueError("out of bounds DIMACS literal")
     words.append(lit)
     if len(words)>100000:raise ValueError("absurd source clause width")
 if n is None or words or count!=declared:raise ValueError("incomplete DIMACS source")
 return dict(n=n,m=declared,two=two,three=three,triples=triples,lengths=dict(all_len))

def independent_clause_proof(gate,two,three):
 """Independent semantic check, NOT another call to detection algorithm.

    Clause existence verified against unchanged original; then all eight
    assignments to three variable values exhaustively establish exactly
    the claimed Boolean relation. Sound even if other source clauses exist.
 """
 op,a,b,z=gate["op"],gate["a"],gate["b"],gate["z"]
 required=clauses_for(op,a,b,z)
 if any(c not in (two if len(c)==2 else three) for c in required):return False
 vars_=sorted({abs(a),abs(b),abs(z)})
 if len(vars_)!=3:return False
 for bits in itertools.product((False,True),repeat=3):
  v=dict(zip(vars_,bits))
  va=v[abs(a)]==(a>0);vb=v[abs(b)]==(b>0);vz=v[abs(z)]==(z>0)
  expected=(va!=vb if op=="xor" else va and vb if op=="and" else va or vb)
  sat=all(any(v[abs(l)]==(l>0) for l in clause) for clause in required)
  if sat != (vz==expected):return False
 return True

def detect(source):
 began=time.perf_counter()
 parsed=parse_cnf(source)
 parsed_s=time.perf_counter()-began
 two,three=parsed["two"],parsed["three"]
 triples=sorted(parsed["triples"])
 found={};covered=set()
 start=time.perf_counter()
 inspected=0;limited=False
 for triple in triples:
  if inspected>=MAX_CANDIDATE_TRIPLES or len(found)>=MAX_GATE_WITNESSES:
   limited=True;break
  if inspected%32==0 and time.perf_counter()-start>SEARCH_BUDGET_SECONDS:
   limited=True;break
  inspected+=1
  for zvar in triple:
   inputs=[x for x in triple if x!=zvar]
   for phases in itertools.product((1,-1),repeat=3):
    a=phases[0]*inputs[0];b=phases[1]*inputs[1];z=phases[2]*zvar
    for op in ("xor","and","or"):
     group="xor" if op=="xor" else "andor"
     key=(triple,group)
     if key in found:continue
     required=clauses_for(op,a,b,z)
     if not all(c in (two if len(c)==2 else three) for c in required):
      continue
     witness=dict(op=op,a=a,b=b,z=z,triplet=list(triple),clauses=len(required))
     if not independent_clause_proof(witness,two,three):
      raise RuntimeError("LOCAL_GATE_SOUNDNESS_FAILED "+str(witness))
     found[key]=witness
     covered.update(required)
 time_s=time.perf_counter()-start
 witnesses=list(found.values())
 group_count=Counter("xor" if x["op"]=="xor" else "andor" for x in witnesses)
 graph=defaultdict(set)
 for gate in witnesses:
  a,b,z=abs(gate["a"]),abs(gate["b"]),abs(gate["z"])
  for x,y in ((a,b),(b,z),(z,a)):
   graph[x].add(y);graph[y].add(x)
 sizes=[];visited=set()
 for k in graph:
  if k in visited:continue
  todo=[k];visited.add(k);component=0
  while todo:
   x=todo.pop();component+=1
   for y in graph[x]:
    if y not in visited:visited.add(y);todo.append(y)
  sizes.append(component)
 result=dict(source_bytes=os.path.getsize(source),variables=parsed["n"],
  clauses=parsed["m"],clauses_by_width=parsed["lengths"],candidate_triplets=len(triples),
  inspected_triplets=inspected,partial_xor_blocks=group_count["xor"],
  partial_andor_blocks=group_count["andor"],locally_verified_gate_blocks=len(witnesses),
  covered_clauses=len(covered),covered_fraction=round(len(covered)/max(1,parsed["m"]),8),
  components=len(sizes),largest_component_vars=max(sizes,default=0),
  parse_seconds=round(parsed_s,6),detect_seconds=round(time_s,6),
  total_overhead_seconds=round(time.perf_counter()-began,6),
  budget_limited=limited,proof="independent_source_clause_eight_row_truth_table",
  action="SHADOW_ONLY_NO_SOLVER_MODIFICATION",witnesses=witnesses)
 return result

def make_source(path,n,clauses):
 path.write_text("p cnf %d %d\n"%(n,len(clauses))+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
 return path

def control():
 root=P/"controls-generated";root.mkdir(exist_ok=True)
 rng=random.Random(SEED)
 tests=[]
 for op in ("xor","and","or"):
  for trial in range(12):
   domain=rng.sample(range(1,10),3)
   a,b,z=domain
   signed=[rng.choice((-1,1))*x for x in domain]
   req=list(clauses_for(op,*signed))
   # Additional unrelated noise and arbitrary clause order; original gate
   # must be recognized as only a local part of the CNF.
   noise=[cl((4,5,6,7)),cl((-4,-5,8,9))]
   clauses=req+noise;rng.shuffle(clauses)
   path=make_source(root/f"{op}-{trial}.cnf",9,clauses)
   res=detect(path)
   group="xor" if op=="xor" else "andor"
   if not any((w["op"]=="xor" if group=="xor" else w["op"] in ("and","or"))
              for w in res["witnesses"]):
    raise RuntimeError("R124_POSITIVE_CONTROL_FAIL "+str(path))
   assert res["covered_clauses"]<=len(clauses)
   remove=req[rng.randrange(len(req))]
   path=make_source(root/f"{op}-{trial}-damaged.cnf",9,[q for q in clauses if q!=remove])
   bad=detect(path)
   if bad["locally_verified_gate_blocks"]:
    raise RuntimeError("R124_INCOMPLETE_GATE_FALSE_POSITIVE "+str(path))
   tests.append(dict(op=op,trial=trial,good_blocks=res["locally_verified_gate_blocks"],damaged_blocks=0))
 # Validate recognition on the actual, previously seen synthetic R122
 # controls, while keeping those completely separate from external metrics.
 original=P/"controls-r122"/"r122"/"cnf"
 old=[]
 if original.exists():
  for source in sorted(original.glob("*mixed*.cnf"))[:8]:
   r=detect(source)
   if not r["locally_verified_gate_blocks"]:
    raise RuntimeError("R124_R122_CONTROL_MISSED "+str(source))
   old.append(dict(name=source.name,blocks=r["locally_verified_gate_blocks"]))
 if not old:raise RuntimeError("R124_R122_FROZEN_CONTROL_MISSING")
 result=dict(protocol=PROTO,positive=len(tests),negative=len(tests),
   historical_R122_synthetic_controls=old,source="SYNTHETIC CONTROL ONLY; excluded from external results",
   check="source clause presence and 8-row truth table; shadow only")
 (P/"control-results.json").write_text(json.dumps(result,indent=2)+"\n")
 print("R124_CONTROL_PASS",json.dumps(result),flush=True)

def scan(shard):
 m=json.loads((SOURCE/"manifest.json").read_text())
 assert m["protocol"]=="DRNAS-R123-FROZEN-EXTERNAL-MIXED-20261105-v1"
 cases=m["cases"]
 assert len(cases)==160 and 0<=shard<SHARDS
 rows=[]
 for i,c in enumerate(cases):
  if i%SHARDS!=shard:continue
  original=SOURCE/c["id"]
  if sha_file(original)!=c["sha256"]:raise RuntimeError("R124_SOURCE_SHA_MISMATCH "+c["id"])
  result=detect(original)
  record=dict(id=c["id"],cohort=c["cohort"],source_url=c["url"],gbd=c["gbd"],
    sha256=c["sha256"],source_runner_manifest="R123 frozen inputs",**result)
  rows.append(record)
  print("R124_SHADOW_CASE",json.dumps({k:v for k,v in record.items() if k!="witnesses"}),flush=True)
  (P/f"shard-{shard}.json").write_text(json.dumps(rows)+"\n")
 assert len(rows)==len(cases[shard::SHARDS])
 print("R124_SHARD_COMPLETE",shard,len(rows),flush=True)

def aggregate():
 m=json.loads((SOURCE/"manifest.json").read_text())
 cases=m["cases"]
 assert len(cases)==160
 rows=[];pins=set();cpus=set()
 for shard in range(SHARDS):
  path=P/f"shard-{shard}.json"
  if not path.exists():raise RuntimeError("MISSING_SHARD "+str(shard))
  subset=json.loads(path.read_text())
  assert len(subset)==len(cases[shard::SHARDS]),("INCOMPLETE_SHARD",shard)
  rows+=subset
  pin=(P/f"commit-{shard}.txt")
  cpu=(P/f"cpu-{shard}.txt")
  assert pin.exists() and cpu.exists()
  pins.add(pin.read_text().strip())
  cpus.add(next((x.strip() for x in cpu.read_text().splitlines()
                 if x.strip().startswith("Model name:")),"unknown"))
 assert len(pins)==1
 byid={r["id"]:r for r in rows}
 assert len(byid)==160
 assert {x["id"] for x in cases}==set(byid)
 for c in cases:
  r=byid[c["id"]]
  assert r["sha256"]==c["sha256"] and r["cohort"]==c["cohort"]
  assert r["action"]=="SHADOW_ONLY_NO_SOLVER_MODIFICATION"
  assert r["proof"]=="independent_source_clause_eight_row_truth_table"
  assert r["locally_verified_gate_blocks"]==len(r["witnesses"])
  assert r["partial_xor_blocks"]+r["partial_andor_blocks"]==len(r["witnesses"])
 report={}
 for cohort in ("miter","official2026","all"):
  subset=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
  report[cohort]=dict(formulas=len(subset),
   formulas_with_verified_partial_gates=sum(r["locally_verified_gate_blocks"]>0 for r in subset),
   formulas_with_xor=sum(r["partial_xor_blocks"]>0 for r in subset),
   formulas_with_andor=sum(r["partial_andor_blocks"]>0 for r in subset),
   total_verified_partial_gate_blocks=sum(r["locally_verified_gate_blocks"] for r in subset),
   xor_blocks=sum(r["partial_xor_blocks"] for r in subset),
   andor_blocks=sum(r["partial_andor_blocks"] for r in subset),
   budget_limited=sum(r["budget_limited"] for r in subset),
   parse_seconds_total=round(sum(r["parse_seconds"] for r in subset),6),
   detect_seconds_total=round(sum(r["detect_seconds"] for r in subset),6),
   combined_overhead_seconds_total=round(sum(r["total_overhead_seconds"] for r in subset),6),
   max_single_overhead_seconds=max((r["total_overhead_seconds"] for r in subset),default=0),
   max_source_coverage=max((r["covered_fraction"] for r in subset),default=0))
 result=dict(protocol=PROTO,all_160_SHA_checked=True,shards=SHARDS,
  source_git_commit=sorted(pins),cpu_models=sorted(cpus),
  source="REUSED R123 external 160 SHA-frozen formulas. NOT NEW BLIND HOLDOUT.",
  active_gate=False,sat_calls=0,modified_kissat=False,expected_r122_direct_activations_on_R123=0,
  proof="each reported local Boolean gate audited against original source clauses with all 8 assignments",
  limitation="Complete local gate patterns only; nothing inferred from incomplete gate encodings. CPU overhead measured in Python shadow, not native in-process.",
  by_cohort=report)
 (P/"results.json").write_text(json.dumps(result,indent=2)+"\n")
 with (P/"formula_features.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["id","cohort","gbd","sha256","variables","clauses",
    "candidate_triplets","inspected_triplets","partial_xor_blocks","partial_andor_blocks",
    "locally_verified_gate_blocks","covered_fraction","components","largest_component_vars",
    "parse_seconds","detect_seconds","total_overhead_seconds","budget_limited"])
  w.writeheader()
  for r in rows:w.writerow({k:r.get(k) for k in w.fieldnames})
 print("R124_FINAL",json.dumps(result),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("command",choices=("control","scan","aggregate"))
 ap.add_argument("--shard",type=int,default=0)
 a=ap.parse_args()
 {"control":control,"scan":lambda:scan(a.shard),"aggregate":aggregate}[a.command]()

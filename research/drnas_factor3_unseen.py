#!/usr/bin/env python3
"""FACTOR3: deterministic frozen unseen larger SAT/UNSAT, native A/B.
No predeclared separators passed to solver; known SAT witness by construction;
UNSAT independently certified by contradictory unit clauses.
Records every timeout and does not equate paired agreement to proof.
"""
import json,pathlib,random,re,subprocess,statistics,hashlib
OUT=pathlib.Path("mre_factor3");OUT.mkdir(exist_ok=True)
BIN=OUT/"bin/drnas_factor2"
def gen(seed):
 rng=random.Random(20261110+1000+seed)
 structured=seed<16
 n=24+4*(seed%7)
 witness={v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
 clauses=[]
 if structured:
  # Variable 1 is a genuine separator, but it is not supplied to B.
  # Local blocks 5-10 variables; no cross-block clauses.
  rest=list(range(2,n+1))
  blocks=[rest[i:i+7] for i in range(0,len(rest),7)]
  for block in blocks:
   for _ in range(4*len(block)):
    candidates=[1]+block
    k=min(3,len(candidates))
    vs=rng.sample(candidates,k)
    lits=[v if rng.getrandbits(1) else -v for v in vs]
    if not any(witness[abs(l)]==(l>0) for l in lits):
     lits[0]=abs(lits[0]) if witness[abs(lits[0])] else -abs(lits[0])
    clauses.append(lits)
 else:
  # Globally mixed dense random 3-CNF, planted satisfiable.
  for _ in range(6*n):
   vs=rng.sample(range(1,n+1),3)
   lits=[v if rng.getrandbits(1) else -v for v in vs]
   if not any(witness[abs(l)]==(l>0) for l in lits):
    lits[0]=abs(lits[0]) if witness[abs(lits[0])] else -abs(lits[0])
   clauses.append(lits)
 unsat=seed%4==0
 if unsat:
  v=n
  clauses.extend([[v],[-v]])
 status="UNSAT" if unsat else "SAT"
 return n,clauses,status,structured,witness
def verify_model(clauses,model,n):
 return len(model)==n and all(any(model[abs(l)]==(l>0) for l in c) for c in clauses)
rows=[];sources=[]
for seed in range(32):
 n,cls,expected,structured,witness=gen(seed)
 if expected=="SAT" and not verify_model(cls,witness,n):raise RuntimeError("bad planted model")
 if expected=="UNSAT" and not ([n] in cls and [-n] in cls):raise RuntimeError("bad UNSAT certificate")
 text=f"p cnf {n} {len(cls)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cls)
 sha=hashlib.sha256(text.encode()).hexdigest()
 path=OUT/f"frozen_{seed:02}.cnf";path.write_text(text)
 sources.append(dict(seed=seed,sha256=sha,vars=n,clauses=len(cls),family="separable" if structured else "mixed",expected=expected))
 for rep in range(3):
  for arm in ("A","B"):
   p=subprocess.run([str(BIN.resolve()),str(path.resolve()),"--mode",arm,"--time","2"],
                    capture_output=True,text=True,timeout=5)
   if p.returncode not in (0,10,20):raise RuntimeError(f"run error {seed} {arm}: {p.stderr}")
   line=re.search(r"^FACTOR2_TRIAL (.*)$",p.stdout,re.M)
   if not line:raise RuntimeError(p.stdout)
   met=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
   status=met["status"]
   if status not in ("UNKNOWN",expected):raise RuntimeError(f"wrong status {seed} {arm} {status}")
   if status=="SAT":
    lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ") for x in l[2:].split() if x!="0"]
    model={abs(l):l>0 for l in lits}
    if not verify_model(cls,model,n):raise RuntimeError("bad original witness")
   row=dict(seed=seed,sha256=sha,family="separable" if structured else "mixed",
     expected=expected,arm=arm,rep=rep,status=status,E2E_s=float(met["e2e_s"]),
     PAR2_s=float(met["e2e_s"]) if status!="UNKNOWN" else 4.,
     sep=int(met["sep"]),components=int(met["components"]),
     local_checks=int(met["local_checks"]),fallback=int(met["fallback"]),
     decisions=int(met["decisions"]),conflicts=int(met["conflicts"]))
   rows.append(row)
   print("FACTOR3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={}
for fam in ("separable","mixed","all"):
 summary[fam]={}
 for arm in ("A","B"):
  sub=[r for r in rows if r["arm"]==arm and (fam=="all" or r["family"]==fam)]
  summary[fam][arm]=dict(solved=sum(r["status"]!="UNKNOWN" for r in sub),
   trials=len(sub),PAR2_s=round(sum(r["PAR2_s"] for r in sub),6),
   elapsed_s=round(sum(r["E2E_s"] for r in sub),6),
   fallback=sum(r["fallback"] for r in sub),
   decisions=sum(r["decisions"] for r in sub),
   median_s=round(statistics.median(r["E2E_s"] for r in sub),7))
audit=dict(protocol="FACTOR3-32-FROZEN-UNSEEN-SYNTHETIC-2NATIVE-3REPS-ONECPU",
  sources=sources,source_count=len(sources),trials=len(rows),
  native_same_binary=True,automatic_separator=True,
  SAT_planted_original_witness_and_output_verified=True,
  UNSAT_independent_contradictory_units=True,UNSAT_independent_LRAT=False,
  no_original_official_CNF=True,
  source_selection_does_not_use_solver_timings=True,
  summary=summary,rows=rows)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
print("FACTOR3_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","sources")},sort_keys=True))

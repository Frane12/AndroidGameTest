#!/usr/bin/env python3
"""FACTOR4 frozen challenge, three native arms A CDCL, B unconditional factor,
C cheap structural density gate. SHA frozen generated source.
"""
import importlib.util,json,pathlib,re,subprocess,statistics,hashlib
spec=importlib.util.spec_from_file_location("factor3","research/drnas_factor3_unseen.py")
# Do not import factor3 (it executes benchmark at module level); parse source
# and execute only its generator definitions.
source=pathlib.Path("research/drnas_factor3_unseen.py").read_text()
prefix=source.split("rows=[];sources=[]")[0]
env={"__name__":"factor3_generator"}
exec(compile(prefix,"research/drnas_factor3_unseen.py","exec"),env)
gen=env["gen"];verify_model=env["verify_model"]
OUT=pathlib.Path("mre_factor4");OUT.mkdir(exist_ok=True)
BIN=OUT/"bin/drnas_factor4"
rows=[];sources=[]
for seed in range(32):
 n,cls,expected,structured,witness=gen(seed)
 if expected=="SAT" and not verify_model(cls,witness,n):raise RuntimeError("bad planted witness")
 if expected=="UNSAT" and not ([n] in cls and [-n] in cls):raise RuntimeError("bad UNSAT construction")
 text=f"p cnf {n} {len(cls)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cls)
 sha=hashlib.sha256(text.encode()).hexdigest()
 path=OUT/f"frozen_{seed:02}.cnf";path.write_text(text)
 sources.append(dict(seed=seed,sha256=sha,vars=n,clauses=len(cls),
  family="separable" if structured else "mixed",expected=expected))
 for rep in range(3):
  for arm in ("A","B","C"):
   p=subprocess.run([str(BIN.resolve()),str(path.resolve()),"--mode",arm,"--time","2"],
      capture_output=True,text=True,timeout=5)
   if p.returncode not in (0,10,20):raise RuntimeError(f"run failed {seed} {arm}: {p.stderr}")
   line=re.search(r"^FACTOR2_TRIAL (.*)$",p.stdout,re.M)
   if not line:raise RuntimeError(p.stdout)
   met=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
   status=met["status"]
   if status not in ("UNKNOWN",expected):raise RuntimeError(f"wrong answer {seed} {arm}")
   if status=="SAT":
    lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ") for x in l[2:].split() if x!="0"]
    model={abs(l):l>0 for l in lits}
    if not verify_model(cls,model,n):raise RuntimeError("original witness invalid")
   row=dict(seed=seed,sha256=sha,family="separable" if structured else "mixed",
    arm=arm,rep=rep,status=status,E2E_s=float(met["e2e_s"]),
    PAR2_s=float(met["e2e_s"]) if status!="UNKNOWN" else 4.,
    gate_skip=int(met["gate_skip"]),density=float(met["density"]),
    fallback=int(met["fallback"]),separator_size=int(met["sep"]),
    components=int(met["components"]),local_checks=int(met["local_checks"]),
    decisions=int(met["decisions"]),conflicts=int(met["conflicts"]))
   rows.append(row)
   print("FACTOR4_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={}
for fam in ("separable","mixed","all"):
 summary[fam]={}
 for arm in ("A","B","C"):
  sub=[r for r in rows if r["arm"]==arm and (fam=="all" or r["family"]==fam)]
  summary[fam][arm]=dict(solved=sum(r["status"]!="UNKNOWN" for r in sub),
   trials=len(sub),PAR2_s=round(sum(r["PAR2_s"] for r in sub),7),
   median_s=round(statistics.median(r["E2E_s"] for r in sub),7),
   gate_skip=sum(r["gate_skip"] for r in sub),fallback=sum(r["fallback"] for r in sub),
   decisions=sum(r["decisions"] for r in sub))
audit=dict(protocol="FACTOR4-32-FROZEN-3-NATIVE-ARMS-3-REPS-ONECPU",
 source_count=len(sources),trials=len(rows),gate="source clause/var density >5 => CDCL",
 no_training_on_outcomes=True,original_source_SHA=sources,
 same_binary=True,one_logical_cpu=True,synthetic_nonblind=True,
 SAT_original_witness_verified=True,UNSAT_independent_contradictory_units=True,
 UNSAT_independent_LRAT=False,summary=summary,rows=rows)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
print("FACTOR4_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","original_source_SHA")},sort_keys=True))

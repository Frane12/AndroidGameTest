#!/usr/bin/env python3
"""FACTOR4.1: source-locked flat200 regression plus 32 prior FACTOR3 controls.
A native CDCL, C original unbounded density gate, D bounded structural gate.
All models replayed on original CNF. UNSAT synthetic independently constructed.
"""
import hashlib,io,json,pathlib,re,subprocess,statistics,tarfile,urllib.request
OUT=pathlib.Path("mre_factor41");OUT.mkdir(exist_ok=True)
BIN=OUT/"bin/drnas_factor41"
src=pathlib.Path("research/drnas_factor3_unseen.py").read_text()
env={"__name__":"factor3_generator"}
exec(compile(src.split("rows=[];sources=[]")[0],"research/drnas_factor3_unseen.py","exec"),env)
sources=[]
for seed in range(32):
 n,clauses,status,structured,witness=env["gen"](seed)
 data=(f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
 path=OUT/f"factor3_{seed:02}.cnf";path.write_bytes(data)
 sources.append(dict(id=seed,family="factor3_separable" if structured else "factor3_mixed",
   path=str(path),sha256=hashlib.sha256(data).hexdigest(),expected=status,cap=2))
manifest=json.loads(pathlib.Path("research/drnas-sat-v7-4/frozen_real_medium.json").read_text())
for j,family in enumerate(("flat200-479","planning-logistics")):
 a=next(x for x in manifest["archives"] if x["set"]==family)
 with urllib.request.urlopen(a["url"],timeout=60) as response:raw=response.read(12_000_000)
 if hashlib.sha256(raw).hexdigest()!=a["archive_sha256"]:raise RuntimeError("pinned archive changed")
 with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
  entries=[x for x in t.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")]
  entries.sort(key=lambda x:hashlib.sha256((family+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
  chosen=entries[2 if len(entries)>2 else 0]
  raw_cnf=t.extractfile(chosen).read()
 # Normalize SATLIB comment terminators, preserving original clause content.
 lines=raw_cnf.decode("ascii","replace").splitlines()
 cleaned=[line for line in lines if not line.lstrip().startswith(("%","c edge"))]
 data=("\n".join(cleaned)+"\n").encode()
 path=OUT/f"satlib_{family}.cnf";path.write_bytes(data)
 sources.append(dict(id=32+j,family=family,path=str(path),
   sha256=hashlib.sha256(data).hexdigest(),archive_sha256=a["archive_sha256"],
   archive_entry=chosen.name,expected="SAT",cap=30))
def model_ok(path,stdout):
 a={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line[2:].split():
    lit=int(token)
    if lit:a[abs(lit)]=lit>0
 if not a:return False
 clause=[]
 for line in path.read_text().splitlines():
  if line.startswith(("p","c","%")):continue
  for token in line.split():
   lit=int(token)
   if lit:clause.append(lit)
   else:
    if not any(a.get(abs(x))==(x>0) for x in clause):return False
    clause=[]
 return not clause
rows=[]
for source in sources:
 path=pathlib.Path(source["path"])
 for rep in range(2):
  for arm in ("A","C","D"):
   p=subprocess.run([str(BIN.resolve()),str(path),"--mode",arm,"--time",str(source["cap"])],
     capture_output=True,text=True,timeout=source["cap"]+4)
   if p.returncode not in (0,10,20):raise RuntimeError(f"invalid exit {source['id']} {arm}: {p.stderr}")
   m=re.search(r"^FACTOR2_TRIAL (.*)$",p.stdout,re.M)
   if not m:raise RuntimeError("missing telemetry "+p.stdout)
   d=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
   status=d["status"]
   if status not in ("UNKNOWN",source["expected"]):raise RuntimeError("incorrect status")
   if status=="SAT" and not model_ok(path,p.stdout):raise RuntimeError("invalid original SAT witness")
   row=dict(id=source["id"],family=source["family"],sha256=source["sha256"],
    arm=arm,rep=rep,status=status,E2E_s=float(d["e2e_s"]),
    PAR2_s=float(d["e2e_s"]) if status!="UNKNOWN" else 2*source["cap"],
    gate_skip=int(d["gate_skip"]),fallback=int(d["fallback"]),
    separator_probes=int(d["separator_probes"]),
    separator_search_s=float(d["separator_search_s"]),
    decisions=int(d["decisions"]),conflicts=int(d["conflicts"]))
   rows.append(row);print("FACTOR41_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={}
for family in ("factor3_separable","factor3_mixed","flat200-479","planning-logistics","all"):
 summary[family]={}
 for arm in ("A","C","D"):
  xs=[r for r in rows if r["arm"]==arm and (family=="all" or r["family"]==family)]
  summary[family][arm]=dict(solved=sum(r["status"]!="UNKNOWN" for r in xs),
   trials=len(xs),PAR2_s=round(sum(r["PAR2_s"] for r in xs),6),
   median_s=round(statistics.median(r["E2E_s"] for r in xs),7),
   fallback=sum(r["fallback"] for r in xs),probes=sum(r["separator_probes"] for r in xs))
audit=dict(protocol="FACTOR41-32-FROZEN-SYNTHETIC-2-FROZEN-SATLIB-3ARMS-2REPS-ONECPU",
 cap_s_synthetic=2,cap_s_SATLIB=30,gate_max_candidates=8,gate_max_time_s=.003,
 source=sources,rows=rows,summary=summary,oneCPU=True,
 SAT_original_verified=True,UNSAT_independent_LRAT=False,
 synthetic_UNSAT_by_contradictory_units=True,
 SATLIB_normalized_comments_not_original_SHA=True)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("FACTOR41_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","source")},sort_keys=True),flush=True)

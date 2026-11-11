#!/usr/bin/env python3
"""Deterministic source-disjoint training policy. No holdout labels or results are read."""
import hashlib,json,pathlib,resource,subprocess,time
from importlib.machinery import SourceFileLoader
g=SourceFileLoader("gen","research/drnas_atlas13_generator.py").load_module()
rows=[]
for family in ("random3_unsat","pigeonhole_unsat","mixed_hard","graph3color_unsat"):
 for i in range(40,44):
  n,clauses,seed=g.build(family,i)
  raw=("p cnf %d %d\n"%(n,len(clauses))+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
  sha=hashlib.sha256(raw).hexdigest()
  path=pathlib.Path("mre_atlas15/train.cnf");path.write_bytes(raw)
  for arm in ("C_RANDOM","C4_LBD"):
   cmd=["mre_atlas15/bin/drnas_atlas15",str(path),"--mode",arm,"--time","5","--seed",str(seed)]
   def limit():resource.setrlimit(resource.RLIMIT_CPU,(6,7))
   start=time.monotonic()
   try:p=subprocess.run(cmd,text=True,capture_output=True,timeout=7,preexec_fn=limit)
   except subprocess.TimeoutExpired:p=None
   wall=time.monotonic()-start
   telemetry={}
   if p:
    for line in p.stdout.splitlines():
     if line.startswith("ATLAS13_TRIAL "):telemetry=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
   rows.append(dict(sha256=sha,family=family,arm=arm,wall_s=round(wall,6),status=p.returncode if p else 124,conflicts=int(telemetry.get("conflicts",0)),decisions=int(telemetry.get("decisions",0))))
assert len({r["sha256"] for r in rows})==16
by={a:sum(r["wall_s"] for r in rows if r["arm"]==a) for a in ("C_RANDOM","C4_LBD")}
# Conservative policy changes, selected only from disjoint training.
ratio=by["C_RANDOM"]/max(by["C4_LBD"],1e-9)
explore=1.30 if ratio>1.10 else (0.75 if ratio<0.90 else 1.0)
quality=1.20 if ratio>1.10 else (0.40 if ratio<0.90 else 0.85)
out=dict(version=1,train_sha_count=16,train_index_range=[40,43],holdout_index_range=[64,69],source_disjoint=True,explore=explore,quality=quality,ratio=ratio,rows=rows)
pathlib.Path("ATLAS15_TRAINING.json").write_text(json.dumps(out,indent=2))
pathlib.Path("ATLAS15_POLICY.txt").write_text(f"{explore},{quality}")
print("ATLAS15_TRAINED_POLICY "+json.dumps({k:v for k,v in out.items() if k!="rows"},sort_keys=True),flush=True)

#!/usr/bin/env python3
"""R120 external SAT Competition 2025 smoke benchmark; no cherry-picked performance results."""
import csv,hashlib,json,lzma,os,pathlib,random,subprocess,time,urllib.request
ROOT=pathlib.Path("r120"); ROOT.mkdir(exist_ok=True)
INDEX="https://benchmark-database.de/getinstances?query=track%3Dmain_2025&context=cnf"
SEED=12020261105
CAP=15
def fetch(url,limit=8_000_000):
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R120-external-benchmark/1.0"})
 with urllib.request.urlopen(req,timeout=45) as f:
  b=f.read(limit+1)
  if len(b)>limit:raise ValueError("download exceeds size cap")
  return b
def freeze():
 body=fetch(INDEX,8_000_000).decode("utf-8")
 print("R120_URI_LIST",repr(body[:300]),"bytes",len(body),flush=True)
 links=[x.strip() for x in body.splitlines() if x.strip() and not x.startswith("#")]
 links=[x for x in links if x.startswith(("https://","http://"))]
 assert len(links)>=150,("insufficient official URLs",len(links))
 random.Random(SEED).shuffle(links)
 (ROOT/"candidate_urls.sha256").write_text(hashlib.sha256("\n".join(links).encode()).hexdigest()+"\n")
 selected=[];excluded=[]
 for url in links:
  if len(selected)>=150:break
  try:
   raw=fetch(url)
   if raw.startswith(b"\xfd7zXZ"):raw=lzma.decompress(raw,memlimit=256_000_000)
   if len(raw)>40_000_000:raise ValueError("decompressed size cap")
   header=next((line for line in raw.splitlines() if line.startswith(b"p cnf ")),None)
   if header is None:raise ValueError("not DIMACS")
   sha=hashlib.sha256(raw).hexdigest()
   if sha in {x["sha256"] for x in selected}:raise ValueError("duplicate")
   name=f"{len(selected):03d}.cnf";(ROOT/name).write_bytes(raw)
   selected.append(dict(name=name,url=url,sha256=sha,bytes=len(raw),header=header.decode(errors="replace")))
  except Exception as e:excluded.append(dict(url=url,reason=str(e)[:120]))
  if len(excluded)>=350:break
 (ROOT/"manifest.json").write_text(json.dumps(dict(source=INDEX,seed=SEED,selection="randomized URL order; size/access exclusions logged, no runtime-based selection",selected=selected,excluded=excluded),indent=2))
 print("R120_FREEZE",len(selected),"excluded",len(excluded),flush=True)
 assert len(selected)>=100,"FAIL_CLOSED: fewer than 100 external instances"
def solve(cmd,cnf):
 t=time.perf_counter()
 try:
  p=subprocess.run(cmd+[str(cnf)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  elapsed=time.perf_counter()-t
  status="SAT" if p.returncode==10 else "UNSAT" if p.returncode==20 else "ERROR"
  return status,elapsed,p.stdout
 except subprocess.TimeoutExpired:return "TIMEOUT",CAP,b""
def bench(shard):
 m=json.loads((ROOT/"manifest.json").read_text());out=[]
 bins={"r28":[str((ROOT/"r28").resolve()),"PLACEHOLDER"],"kissat":[str(pathlib.Path("built/bin/kissat_4_0_4").resolve())]}
 bins["r28"][1]=bins["kissat"][0]
 os.sched_setaffinity(0,{sorted(os.sched_getaffinity(0))[0]})
 for i,c in enumerate(m["selected"]):
  if i%8!=shard:continue
  cnf=ROOT/c["name"];assert hashlib.sha256(cnf.read_bytes()).hexdigest()==c["sha256"]
  for rep in range(2):
   for name in (["r28","kissat"] if (i+rep)%2==0 else ["kissat","r28"]):
    status,seconds,stdout=solve(bins[name],cnf)
    if status=="ERROR":raise RuntimeError(f"solver error {name} {c['name']}")
    out.append(dict(id=c["name"],sha256=c["sha256"],rep=rep,solver=name,status=status,seconds=round(seconds,6),par2=round(seconds if status!="TIMEOUT" else 2*CAP,6)))
    print("R120_RESULT",json.dumps(out[-1]),flush=True)
 (ROOT/f"shard-{shard}.json").write_text(json.dumps(out))
def aggregate():
 m=json.loads((ROOT/"manifest.json").read_text());rows=[]
 for i in range(8):rows+=json.loads((ROOT/f"shard-{i}.json").read_text())
 assert len(rows)==len(m["selected"])*4
 pairs={}
 for r in rows:pairs.setdefault((r["id"],r["rep"]),{})[r["solver"]]=r
 assert len(pairs)==len(m["selected"])*2 and all(len(p)==2 for p in pairs.values())
 mismatch=[(k,v["r28"]["status"],v["kissat"]["status"]) for k,v in pairs.items() if set([v["r28"]["status"],v["kissat"]["status"]])=={"SAT","UNSAT"}]
 assert not mismatch,("SAT/UNSAT disagreement",mismatch)
 summary={name:dict(attempts=sum(r["solver"]==name for r in rows),solved=sum(r["solver"]==name and r["status"] in ("SAT","UNSAT") for r in rows),timeouts=sum(r["solver"]==name and r["status"]=="TIMEOUT" for r in rows),par2_total=round(sum(r["par2"] for r in rows if r["solver"]==name),6)) for name in ("r28","kissat")}
 report=dict(corpus="SAT Competition 2025 external mixed categories, NOT exclusively circuit equivalence",cases=len(m["selected"]),exclusions=len(m["excluded"]),cap_seconds=CAP,summary=summary,disagreements=mismatch,limitation="UNSAT proof and SAT witness independent verification not yet implemented; cannot claim certified correctness")
 (ROOT/"results.json").write_text(json.dumps(report,indent=2))
 print("R120_AGGREGATE",json.dumps(report),flush=True)
if __name__=="__main__":
 import sys
 {"freeze":freeze,"bench":lambda:bench(int(sys.argv[2])),"aggregate":aggregate}[sys.argv[1]]()

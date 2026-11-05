#!/usr/bin/env python3
"""Acquisition only: fetch 400 CNF sources, SHA/DIMACS audit; NEVER run a SAT solver."""
import bz2,csv,gzip,hashlib,io,json,lzma,pathlib,random,re,sys,tarfile,time,urllib.request
from collections import Counter
BASE=pathlib.Path("holdout-400");CAP=8_000_000;PROTO="DRNAS-400-PROSPECTIVE-20261105-v1"
ARCH={
"flat200":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/GCP/flat200-479.tar.gz","a27f57132377dc6be4fd11a938c78e6ec245e65fb33fa7a86579ef986c7c242b"),
"logistics":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/PLANNING/Logistics/logistics.tar.gz","dcd3b7abfcf25ddf264d46b6ed95ec597eefcdcad88659877812a427c1c576af"),
"blocks":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/PLANNING/BlocksWorld/blocksworld.tar.gz","f1f2e630f84975857bec6661a459e3bf1220de857fe3b487bcfe1ef8a93ac3a2"),
"quasigroup":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/QG/QG.tar.gz","6b8153ace76d0c0f042ce061360ebd40cdf67429b1477ffbdac631c2e9cc4207"),
"parity":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/DIMACS/PARITY/parity.tar.gz","d18ef13699ec3aafe0e70861fc1b9316205a6264c818cf2f69ebf3478534ba4f"),
"uf250":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/uf250-1065.tar.gz","ebe9b90d674bfd4d3cc76ed048f144e2728b1758cb8aac157c7ce38bb1d1931d"),
"uuf250":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/uuf250-1065.tar.gz","1b6d59619e3c805947c5602703ff3190dfbfeff55d6cb62187838668b0fd4126"),
"uf100":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/uf100-430.tar.gz","7f691acb8c45790ef8178dd01bb362cf50da608d478be9965599131f0a763e59"),
"uuf100":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/uuf100-430.tar.gz","736c6f94fecae346a00501b197c482e146b1c6ab05fb6d2e4666e520b8e8508a"),
"jnh":("https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/DIMACS/JNH/jnh.tar.gz","f2c41a8f11b017649de32ac7ffa377be8e5cc18d1c8601147ece713a9446d3cc")}
SPEC={
"official":{"archives":[],"indexes":[("official2026","https://raw.githubusercontent.com/satcompetition/2026/3e2dee7cf5aa643c77bf946280a3c1c520756ef9/downloads/track_main_2026.uri"),("official2025","https://raw.githubusercontent.com/satcompetition/2025/5f286f4443ab2e1f3c1deded3255d8500ae46e2e/downloads/SC2025.uri"),("official2024","https://benchmark-database.de/getinstances?query=track%3Dmain_2024&context=cnf")]},
"external_application":{"archives":["flat200","logistics","blocks","quasigroup"],"indexes":[(v,"https://benchmark-database.de/getinstances?query=family%3D"+v+"&context=cnf") for v in ["graph-coloring","bounded-model-checking","planning","quasigroup-completion"]]},
"external_xor":{"archives":["parity"],"indexes":[(v,"https://benchmark-database.de/getinstances?query=family%3D"+v+"&context=cnf") for v in ["xor-shifting","cryptography","miter"]]},
"external_nonxor":{"archives":["uf250","uuf250","uf100","uuf100","jnh"],"indexes":[(v,"https://benchmark-database.de/getinstances?query=family%3D"+v+"&context=cnf") for v in ["uniform-random","variable-length-random","random-3sat"]]}}
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(url,cap=10_000_000):
 url=url.replace("http://benchmark-database.de/","https://benchmark-database.de/")
 err=None
 for a in range(2):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-SAT-Prospective-Source-Audit/1.0"})
   with urllib.request.urlopen(req,timeout=38) as r:b=r.read(cap+1)
   if len(b)>cap:raise ValueError("wire_size_limit")
   return b
  except Exception as e:
   err=e
   if a==0:time.sleep(1)
 raise err
def plain(b):
 if b[:2]==b"\x1f\x8b":b=gzip.decompress(b)
 elif b[:3]==b"BZh":b=bz2.decompress(b)
 elif b[:6]==b"\xfd7zXZ\x00":b=lzma.decompress(b)
 if len(b)>CAP:raise ValueError("plain_size_limit")
 return b
def dimacs(b):
 hdr=None;ends=0;maxvar=0
 for line in b.splitlines():
  line=line.strip()
  if not line or line[:1] in (b"c",b"%"):continue
  if line.startswith(b"p "):
   q=line.split()
   if hdr is not None or len(q)!=4 or q[1]!=b"cnf":raise ValueError("bad_header")
   hdr=(int(q[2]),int(q[3]));continue
  if hdr is None:raise ValueError("missing_header")
  for token in line.split():
   v=int(token)
   if not v:ends+=1
   else:maxvar=max(maxvar,abs(v))
 if hdr is None or min(hdr)<=0 or ends!=hdr[1] or maxvar>hdr[0]:raise ValueError("invalid_cnf")
 return hdr
def xor_quartet(b):
 clauses=set()
 for line in b.splitlines():
  if line[:1] in (b"p",b"c",b"%"):continue
  try:v=list(map(int,line.split()))
  except ValueError:continue
  if len(v)==4 and v[-1]==0 and len({abs(x) for x in v[:3]})==3:clauses.add(tuple(sorted(v[:3])))
 for c in clauses:
  vs=sorted(map(abs,c))
  for parity in (0,1):
   patterns={tuple(sorted(-n if mask&(1<<i) else n for i,n in enumerate(vs))) for mask in range(8) if mask.bit_count()%2==parity}
   if patterns<=clauses:return True
 return False
def known_sources():
 sha_seen=set();id_seen=set("75429ff7acb5acb597abe01aa745c2a6 42f1311ce504db8cc0cb590a568da20a 01d6fa8efd18ebfecd06af408958477b 0efcbd10294eb001b16b4d126923372f".split())
 old=pathlib.Path("research/sat-analytics-data/current/formulas.csv")
 if not old.is_file():raise RuntimeError("MISSING HISTORICAL CSV")
 with old.open(newline="") as f:
  for row in csv.DictReader(f):
   for k,v in row.items():
    if "sha" in k.lower() and re.fullmatch("[0-9a-fA-F]{64}",v or ""):sha_seen.add(v.lower())
 ledgers=list(pathlib.Path("prior-ledgers").rglob("*.json"))
 if len(ledgers)<6:raise RuntimeError("INSUFFICIENT PRIOR MANIFESTS: "+str(len(ledgers)))
 for f in ledgers:
  try:stack=[json.loads(f.read_text())]
  except Exception:continue
  while stack:
   x=stack.pop()
   if isinstance(x,list):stack.extend(x)
   elif isinstance(x,dict):
    for k,v in x.items():
     if isinstance(v,(dict,list)):stack.append(v)
     elif isinstance(v,str):
      if "sha" in k.lower() and re.fullmatch("[0-9a-fA-F]{64}",v):sha_seen.add(v.lower())
      if k in ("gbd","url","id"):
       name=v.rsplit("/",1)[-1].split("?",1)[0]
       if re.fullmatch("[0-9a-fA-F]{32}",name):id_seen.add(name.lower())
 return sha_seen,id_seen
def run(category):
 seen,ids=known_sources();new=set();rows=[];reject=Counter();indexes=[]
 target=100;dest=BASE/"raw"/category;dest.mkdir(parents=True,exist_ok=True)
 def record(raw,location,ident,source_sha,family):
  try:
   b=plain(raw);h=sha(b)
   if h in seen or h in new:reject["already_seen_SHA_or_duplicate"]+=1;return
   if category=="external_xor" and family in ("cryptography","miter") and not xor_quartet(b):
    reject["unverified_XOR_structure"]+=1;return
   n,m=dimacs(b)
   name=dest/(h+".cnf.gz")
   with gzip.open(name,"wb",compresslevel=6) as f:f.write(b)
   rows.append(dict(category=category,family=family,id=ident,source_url=location,sha256=h,source_wire_sha256=source_sha,variables=n,clauses=m,bytes=len(b),compressed_file=str(name),proof_status="not_solved",selection="blind_sha_excluded"))
   new.add(h);ids.add(ident);print("ACQUIRED",category,len(rows),h[:16],flush=True)
  except Exception as e:reject["bad_source_"+str(e)[:48]]+=1
 for key in SPEC[category]["archives"]:
  if len(rows)>=target:break
  url,checksum=ARCH[key]
  try:
   raw=fetch(url,80_000_000)
   if sha(raw)!=checksum:raise ValueError("archive SHA256 mismatch")
   indexes.append(dict(url=url,sha256=checksum,kind=key))
   t=tarfile.open(fileobj=io.BytesIO(raw),mode="r:*")
   members=sorted((m for m in t.getmembers() if m.isfile() and m.name.lower().endswith((".cnf",".dimacs"))),key=lambda m:m.name)
   for m in members:
    if len(rows)>=target:break
    if m.size>CAP:reject["large_archive_entry"]+=1;continue
    record(t.extractfile(m).read(CAP+1),url+"#"+m.name,key+"/"+m.name,checksum,key)
  except Exception as e:reject["archive_"+key+"_"+str(e)[:40]]+=1
 for family,index in SPEC[category]["indexes"]:
  if len(rows)>=target:break
  try:
   data=fetch(index,2_000_000)
   urls=sorted(set(m.decode() for m in re.findall(rb'https?://[^\s]+',data)))
   random.Random(PROTO+"|"+category+"|"+family).shuffle(urls)
   indexes.append(dict(url=index,sha256=sha(data),family=family,urls=len(urls)))
  except Exception as e:reject["index_"+family+"_"+str(e)[:48]]+=1;continue
  for u in urls:
   if len(rows)>=target:break
   ident=u.rsplit("/",1)[-1].split("?",1)[0].lower()
   if ident in ids:reject["previous_GBD_ID"]+=1;continue
   try:
    b=fetch(u)
    record(b,u,ident,sha(b),family)
   except Exception as e:reject["download_"+str(e)[:48]]+=1
 manifest=dict(protocol=PROTO,category=category,count=len(rows),goal=target,formulas=rows,source_indexes=indexes,excluded_prior_SHA_count=len(seen),excluded_prior_GBD_ID_count=len(ids),rejected=dict(reject),status="COMPLETE" if len(rows)==target else "INCOMPLETE",benchmark_executed=False)
 BASE.mkdir(exist_ok=True)
 (BASE/(category+".json")).write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
 print("ACQUISITION_AUDIT",category,len(rows),dict(reject),flush=True)
 if len(rows)!=target:sys.exit(2)
if __name__=="__main__":
 if len(sys.argv)!=2 or sys.argv[1] not in SPEC:raise SystemExit("Expected one category in "+str(list(SPEC)))
 run(sys.argv[1])

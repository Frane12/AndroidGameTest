#!/usr/bin/env python3
"""R152: prospective, family-matched LIGHTS-OUT / LINEAR-EQUATIONS
SAT Competition 2026 test of the UNCHANGED R28 vs pinned Kissat/CaDiCaL.
No tuning or test-time selection. Source class and XOR coverage locked
before solver timing. Previously known IDs / available SHA-ledgers excluded.
The target is a CONDITIONAL same-family transfer test, not a global ranking.
"""
import argparse, hashlib, html, importlib.util, json, pathlib, random, re, sys
from collections import Counter, defaultdict

BASE=pathlib.Path("research/r115_world_top_rematch.py")
spec=importlib.util.spec_from_file_location("r115_source",BASE)
orig=importlib.util.module_from_spec(spec);spec.loader.exec_module(orig)
ROOT=pathlib.Path("r152");ROOT.mkdir(exist_ok=True)
orig.ROOT=ROOT
orig.R28=(ROOT/"r28").resolve()
orig.PROTO="DRNAS-R152-NEW-LIGHTSOUT-FAMILY-XOR-20261105-v1"
orig.SHARDS=4
orig.KNOWN=[]
# Existing R115 PAR2 implementation has a fixed 5s cap and 10s PAR2 penalty.
orig.CAP=5.0
PROTO=orig.PROTO
FAMILIES=("lights-out","linear-equations")
QUOTA={"complete_xor":16,"partial_xor":8,"nonxor_control":8}
MAX_CANDIDATES=160
KNOWN_IDS={
 "75429ff7acb5acb597abe01aa745c2a6", # R115 known
 "01d6fa8efd18ebfecd06af408958477b", # R117 seen SAT
 "0efcbd10294eb001b16b4d126923372f", # R117 seen UNSAT
}
# Previously fixed SATComp26 cases also excluded before looking at any timing.
OLD_R32P={
 "0e06895600b5cd0b6fadb87e17bf8145","180e6d8b61fe6bab26126b78591e324e",
 "2b7e863462991fd008f9898eca63ebf4","3b0eeddcabf36da8642c5774ac67680c",
 "4e0de894799790b06e8d6c3efd109ade","5f9d0127b390a4686171311d38f3fbf8",
 "75429ff7acb5acb597abe01aa745c2a6","860788f93fb766e83e00a29de84180e7",
 "991aec61a2751602d6d7b3e838035610","aa0eadb6c4935468fd6954e23a550504",
 "ba14be209c2fc064726025f017cef17a","d4a6b1a299c7a8ad6ea9769abcc60507",
 "e85fb114c33f450dc2622c78bc6fa019","fd1e0ce3662b9b25d23eb01c6e53a425",
}
def need(flag,message):
 if not flag:raise RuntimeError("R152_AUDIT_FAIL "+str(message))
def sha(b):return hashlib.sha256(b).hexdigest()
def scan_prior():
 ids=set(KNOWN_IDS)|OLD_R32P
 shas=set()
 files=list(pathlib.Path("prior").rglob("*.json"))
 need(any("r115" in str(f) for f in files),"R115 previous-source exclusion missing")
 need(any("400" in str(f) for f in files),"400 prior-source exclusion missing")
 for f in files:
  try:data=json.loads(f.read_text())
  except (ValueError,UnicodeError):continue
  def walk(v,k=""):
   if isinstance(v,dict):
    for a,b in v.items():walk(b,a.lower())
   elif isinstance(v,list):
    for a in v:walk(a,k)
   elif isinstance(v,str):
    s=v.strip().lower()
    if re.fullmatch(r"[0-9a-f]{32}",s) and k in ("id","gbd","gbd_id","instanceid","source_id","source_gbd_id"):
     ids.add(s)
    if re.fullmatch(r"[0-9a-f]{64}",s) and (("sha" in k and "256" in k) or k in ("hash","original_sha","source_hash")):
     shas.add(s)
  walk(data)
 need(len(ids)>=15,"prior exclusion IDs implausibly incomplete")
 return ids,shas,[str(x) for x in files]
def normalize(s):
 return " ".join(html.unescape(re.sub(r"(?s)<[^>]*>"," ",s)).split())
def gbd_family(family):
 # Server-rendered Global Benchmark Database metadata, not benchmark run-times.
 url="https://benchmark-database.de/?context=cnf&family="+family+"&track=main_2026"
 raw=orig.fetch(url,16_000_000).decode("utf-8",errors="replace")
 records=[]
 for tr in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>",raw):
  cells=[normalize(x) for x in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>",tr)]
  if len(cells)<10:continue
  id=cells[0].strip().lower()
  if not re.fullmatch(r"[0-9a-f]{32}",id):continue
  if cells[2].strip().lower()!=family:continue
  if "main_2026" not in cells[9]:continue
  records.append(dict(id=id,family=family,filename=cells[8],source_tag=cells[9],gbd_result=cells[4]))
 need(records,"GBD family metadata returned no valid main_2026 rows for "+family)
 return sorted(records,key=lambda x:x["id"]),sha(raw.encode())
def structural_signature(p):
 # Only original CNF clause shapes, no SAT/UNSAT inference or solver execution.
 n,clauses=orig.parse_clauses(p)
 groups=defaultdict(set)
 eligible=0
 for c in clauses:
  k=len(c)
  if k<2 or k>6 or len({abs(x) for x in c})!=k:continue
  literals=sorted(c,key=abs)
  vs=tuple(abs(x) for x in literals)
  mask=sum(1<<i for i,x in enumerate(literals) if x<0)
  groups[vs].add(mask)
  eligible+=1
 recognized={}
 for vs,masks in groups.items():
  k=len(vs)
  even={i for i in range(1<<k) if i.bit_count()%2==0}
  odd={i for i in range(1<<k) if i.bit_count()%2==1}
  present=set()
  if even<=masks:present|=even
  if odd<=masks:present|=odd
  recognized[vs]=present
 covered=0
 for c in clauses:
  k=len(c)
  if not 2<=k<=6 or len({abs(x) for x in c})!=k:continue
  literals=sorted(c,key=abs)
  vs=tuple(abs(x) for x in literals)
  mask=sum(1<<i for i,x in enumerate(literals) if x<0)
  if mask in recognized.get(vs,set()):covered+=1
 frac=covered/len(clauses)
 cohort="complete_xor" if frac>=.999999 else "partial_xor" if frac>=.5 else "nonxor_control"
 return dict(variables=n,clauses=len(clauses),covered=covered,coverage=round(frac,6),
             eligible=eligible,parity_groups=sum(bool(x) for x in recognized.values()),cohort=cohort)
def freeze():
 # Exclude all known source identities first, then order by a fixed seed.
 excluded,prior_sha,prior_files=scan_prior()
 candidate=[];catalog_pins={}
 for family in FAMILIES:
  rows,digest=gbd_family(family)
  catalog_pins[family]=dict(rows=len(rows),html_sha256=digest)
  candidate.extend(x for x in rows if x["id"] not in excluded)
 need(candidate,"No eligible family-matched official CNFs")
 rng=random.Random(PROTO+"|PREREGISTERED-SOURCE-SHUFFLE")
 candidate.sort(key=lambda x:(x["family"],x["id"]))
 rng.shuffle(candidate)
 scores,score_sha,score_rows=orig.score_source()
 candidates=candidate[:MAX_CANDIDATES]
 selected=[];skipped=Counter();seen_sha=set();count=Counter()
 (ROOT/"frozen").mkdir(parents=True,exist_ok=True)
 for item in candidates:
  if all(count[k]>=v for k,v in QUOTA.items()):break
  gbd=item["id"]
  if gbd not in scores:
   skipped["not_official_verified"]+=1
   continue
  try:
   raw,_=orig.source.request_url("https://benchmark-database.de/file/"+gbd,28*1024*1024,seconds=45)
   plain,_=orig.source.decode(raw)
   if len(plain)>12*1024*1024:raise ValueError("source_bytes_limit")
   nv,nc=orig.source.parse_dimacs_metadata(plain)
   if not (1<=nv<=3000 and 1<=nc<=150000):raise ValueError("dimensions_limit")
   digest=sha(plain)
   if digest in prior_sha or digest in seen_sha:
    skipped["seen_SHA"]+=1;continue
   tmp=ROOT/"frozen"/(gbd+".cnf")
   tmp.write_bytes(plain)
   sig=structural_signature(tmp)
   if count[sig["cohort"]]>=QUOTA[sig["cohort"]]:
    tmp.unlink();skipped["quota_"+sig["cohort"]]+=1;continue
   need(nv==sig["variables"] and nc==sig["clauses"],"original CNF mismatch")
   case=dict(id=gbd,cohort=sig["cohort"],family=item["family"],known=False,
             reps=2,sha256=digest,download_sha256=sha(raw),bytes=len(plain),
             structural=sig,official=scores[gbd],catalog_filename=item["filename"])
   selected.append(case);seen_sha.add(digest);count[sig["cohort"]]+=1
   print("R152_FROZEN",gbd,item["family"],sig["cohort"],sig["coverage"],flush=True)
  except Exception as e:
   skipped[type(e).__name__]+=1
   print("R152_SOURCE_REJECT",gbd,type(e).__name__,str(e)[:120],flush=True)
 need(len(selected)>=3,"fewer than 3 new original family-matched CNFs, no benchmark")
 need(len({x["sha256"] for x in selected})==len(selected),"duplicate content")
 manifest=dict(protocol=PROTO,source="GBD main_2026 families lights-out and linear-equations",
  selection="family metadata + predeclared syntactic parity coverage, never solver timing",
  caveats=["Conditional family sample; not random cross-domain SAT","Prior exclusions cover explicitly downloaded audit manifests, not all historical DRNAS research","GBD family and competition labels are prior public information, not performance scores"],
  freeze_before_solver=True,source_catalog_pins=catalog_pins,official_score_sha256=score_sha,
  selected_count=len(selected),target_quota=QUOTA,shards=orig.SHARDS,cap=orig.CAP,
  source_candidates=len(candidate),sources_scanned=len(candidates),
  excluded_ids_count=len(excluded),excluded_sha_count=len(prior_sha),
  exclusion_files=prior_files,skipped=dict(skipped),cohort_counts=dict(count),cases=selected)
 orig.write(ROOT/"frozen"/"manifest.json",manifest)
 print("R152_FREEZE_PASS",json.dumps({"cases":len(selected),"cohort_counts":dict(count),"prior_exclusion_count":len(excluded)}),flush=True)
def aggregate():
 orig.aggregate()
 report=orig.read(ROOT/"results.json")
 manifest=orig.read(ROOT/"frozen"/"manifest.json")
 report["protocol"]=PROTO
 report["historical_controls"]=0
 report["new_random_official_cases"]=len(report["by_formula"])
 report["source_family_selection"]=manifest["selection"]
 report["source_cohorts"]=manifest["cohort_counts"]
 report["old_source_exclusion_ids"]=manifest["excluded_ids_count"]
 report["comparability"]="same runner paired per formula, 5s cap, original R28 unchanged"
 report["is_global_blind_holdout"]=False
 modes=("r28","kissat","cadical")
 summary={}
 for mode in modes:
  summary[mode]=dict(PAR2_total_s=round(sum(x[mode]["avg_par2"]*x["reps"] for x in report["by_formula"]),6),
                     solved=sum(x[mode]["solved"] for x in report["by_formula"]),
                     trials=sum(x["reps"] for x in report["by_formula"]))
 summary["r28"]["gain_vs_kissat_percent"]=round(100*(summary["kissat"]["PAR2_total_s"]-summary["r28"]["PAR2_total_s"])/summary["kissat"]["PAR2_total_s"],4)
 summary["r28"]["gain_vs_cadical_percent"]=round(100*(summary["cadical"]["PAR2_total_s"]-summary["r28"]["PAR2_total_s"])/summary["cadical"]["PAR2_total_s"],4)
 report["summary"]=summary
 orig.write(ROOT/"results.json",report)
 print("R152_FINAL",json.dumps({"summary":summary,"cohorts":manifest["cohort_counts"],"cases":len(report["by_formula"])}),flush=True)
if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("action",choices=("freeze","shard","audit"))
 parser.add_argument("--shard",type=int,default=0)
 args=parser.parse_args()
 {"freeze":freeze,"shard":lambda:orig.runshard(args.shard),"audit":aggregate}[args.action]()

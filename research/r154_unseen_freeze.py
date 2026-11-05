#!/usr/bin/env python3
"""R154 prospective SHA-disjoint real CNFs: structural XOR+unit transfer.
Freeze source identities and source-only structural labels before ANY timing.
Explicitly conditional family sample, not global SAT Competition standing.
"""
from __future__ import annotations
import argparse,hashlib,html,importlib.util,json,pathlib,random,re,sys,urllib.request
from collections import Counter
ROOT=pathlib.Path("r154");ROOT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location("r152","research/r152_lightsout_unseen.py")
r152=importlib.util.module_from_spec(spec);spec.loader.exec_module(r152)
orig=r152.orig
PROTO="DRNAS-R154-UNSEEN-LIGHTSOUT-XOR-UNIT-TRANSFER-20261105-v1"
FAMILIES=("lights-out","linear-equations","xor-chain","cryptography","miter")
TRACKS=("main_2025","main_2026","submissions_2025","submissions_2026")
QUOTA={"xor_plus_units":12,"complete_xor":8,"mixed_residual":12,"nonxor_control":12}
MAX_SOURCE_FETCH=240
RAW_CAP=28*1024*1024
CNF_CAP=12*1024*1024
MAX_VARIABLES=3000
MAX_CLAUSES=150000
def need(v,msg):
 if not v:raise RuntimeError("R154_SOURCE_AUDIT_FAIL "+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def get_catalog(family,track):
 from urllib.parse import urlencode
 url="https://benchmark-database.de/?"+urlencode(dict(context="cnf",family=family,track=track))
 req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R154-SHA-Source-Freeze/1.0"})
 with urllib.request.urlopen(req,timeout=60) as r: raw=r.read(20*1024*1024+1)
 need(len(raw)<=20*1024*1024,"catalog size exceeded "+family+" "+track)
 doc=raw.decode("utf-8",errors="replace")
 rows=[]
 for tr in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>",doc):
  cols=[" ".join(html.unescape(re.sub(r"(?s)<[^>]*>"," ",a)).split()) for a in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>",tr)]
  if len(cols)<10:continue
  ident=cols[0].strip().lower()
  if not re.fullmatch("[a-f0-9]{32}",ident) or cols[2].lower()!=family:continue
  if track not in cols[9].lower().split(","):continue
  rows.append(dict(id=ident,family=family,track=track,filename=cols[8],gbd_status=cols[4].strip().lower()))
 return rows,sha(raw)
def structural(p):
 n,clauses=orig.parse_clauses(p)
 stat=r152.structural_signature(p)
 units=sum(len(c)==1 for c in clauses)
 covered=stat["covered"]
 residual=len(clauses)-covered-units
 need(residual>=0,"double-counted clauses")
 if covered and not residual and units:
  cohort="xor_plus_units"
 elif covered and not residual:
  cohort="complete_xor"
 elif covered:
  cohort="mixed_residual"
 else:
  cohort="nonxor_control"
 return dict(variables=n,clauses=len(clauses),unit_clauses=units,
   original_xor_covered_clauses=covered,uncovered_nonunit_clauses=residual,
   xor_coverage_pct=round(100*covered/len(clauses),3),cohort=cohort,
   parity_groups=stat["parity_groups"])
def freeze():
 prior_ids,prior_sha,prior_files=r152.scan_prior()
 rows=[];metadata=[]
 for family in FAMILIES:
  for track in TRACKS:
   try:
    arr,digest=get_catalog(family,track)
    metadata.append(dict(family=family,track=track,count=len(arr),sha256=digest))
    rows.extend(arr)
    print("R154_SOURCE_CATALOG",family,track,len(arr),flush=True)
   except Exception as e:
    print("R154_CATALOG_WARNING",family,track,type(e).__name__,str(e)[:120],flush=True)
 need(len(rows)>=12,"insufficient matching GBD catalog entries")
 unique={}
 for row in rows:
  if row["id"] not in prior_ids and row["id"] not in unique:unique[row["id"]]=row
 candidates=list(unique.values())
 # Fixed before any benchmark, independent of known performance.
 random.Random(PROTO+"|source-hash-seed").shuffle(candidates)
 selected=[];cohorts=Counter();skips=Counter()
 seen_sha=set()
 (ROOT/"frozen").mkdir(parents=True,exist_ok=True)
 for index,c in enumerate(candidates[:MAX_SOURCE_FETCH]):
  if all(cohorts[k]>=lim for k,lim in QUOTA.items()):break
  try:
   raw,_=orig.source.request_url("https://benchmark-database.de/file/"+c["id"],RAW_CAP,seconds=55)
   plain,_=orig.source.decode(raw)
   if len(plain)>CNF_CAP:raise ValueError("size")
   n,m=orig.source.parse_dimacs_metadata(plain)
   if n>MAX_VARIABLES or m>MAX_CLAUSES or n<1 or m<1:raise ValueError("dimensions")
   h=sha(plain)
   if h in seen_sha or h in prior_sha:
    skips["duplicate_SHA"]+=1;continue
   p=ROOT/"frozen"/(c["id"]+".cnf")
   p.write_bytes(plain)
   s=structural(p)
   if cohorts[s["cohort"]]>=QUOTA[s["cohort"]]:
    p.unlink();skips["cohort_full_"+s["cohort"]]+=1;continue
   need(s["variables"]==n and s["clauses"]==m,"DIMACS metadata mismatch")
   entry=dict(id=c["id"],source_sha256=h,sha256=h,download_sha256=sha(raw),
    family=c["family"],track=c["track"],catalog_filename=c["filename"],
    gbd_status=c["gbd_status"],cohort=s["cohort"],known=False,structural=s)
   selected.append(entry);seen_sha.add(h);cohorts[s["cohort"]]+=1
   print("R154_FROZEN",len(selected),c["id"],c["family"],c["track"],
         s["cohort"],s["xor_coverage_pct"],"units",s["unit_clauses"],flush=True)
  except Exception as e:
   skips[type(e).__name__]+=1
   print("R154_SOURCE_SKIP",c["id"],type(e).__name__,str(e)[:100],flush=True)
 need(len(selected)>=10,"less than 10 genuine source-disjoint CNFs; abort without benchmark")
 need(len({z["source_sha256"] for z in selected})==len(selected),"SHA duplicates")
 m=dict(protocol=PROTO,phase="FROZEN_BEFORE_FIRST_R154_SOLVER_TIMING",
   sample_type="CONDITIONAL family-matched external originals, not random all-SAT",
   reused_previous_sources=False,
   historical_exclusions=dict(prior_ids=len(prior_ids),prior_source_sha=len(prior_sha),
     files=prior_files,disclaimer="Excludes only retrievable historical manifests; cannot certify globally unseen"),
   source_catalog_records=metadata,source_candidates_before_filter=len(candidates),
   source_candidates_examined=min(MAX_SOURCE_FETCH,len(candidates)),
   source_skips=dict(skips),cohort_counts=dict(cohorts),target_quotas=QUOTA,
   solvers=["r153","r28","kissat","cadical"],cap_seconds=15,repetitions=2,
   formula_count=len(selected),cases=selected)
 (ROOT/"frozen/manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
 print("R154_FREEZE_PASS",json.dumps({"cases":len(selected),"cohorts":dict(cohorts),"excluded_ids":len(prior_ids),"excluded_sha":len(prior_sha)}),flush=True)
if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("action",choices=("freeze",));args=parser.parse_args()
 freeze()

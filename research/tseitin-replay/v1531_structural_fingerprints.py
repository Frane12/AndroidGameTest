#!/usr/bin/env python3
"""Structural fingerprints of pinned, real SATLIB CNFs and exploratory hardness.

Original SATLIB archives are checksum verified by the workflow. Formula SHA256
is matched to the original pilot+final benchmark manifest. This is deliberately
exploratory; feature correlations require fresh blind external validation.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,random,statistics,tarfile,tempfile
from pathlib import Path
from itertools import combinations
import v1531_satlib as legacy

FROZEN="fc0e735aff48989326f256121b5ed6fc585858c3"
SHA1={"uf200-860":"e27208778d47d2405a9368cad3ab8dfb41206be8",
 "uf250-1065":"acaf37c9e92694a38974a6a1a9647e0f9bcf80b2",
 "uuf200-860":"05aacf179ed739a8311f2821874183daa5a9b134",
 "uuf250-1065":"138484766c966e3f18395db92cf6d69d3c442a3e"}
FEATURES=["sign_balance_entropy","degree_gini","degree_cv",
 "reused_varpair_fraction","horn_fraction","positive_fraction",
 "xor3_quartets","connected_components"]
SEED=411261101
def gini(v):
 if not v:return 0
 ss=sorted(v);total=sum(ss)
 return sum((2*i-len(ss)-1)*x for i,x in enumerate(ss,1))/(len(ss)*total) if total else 0.
def entropy(x):
 if x<=0 or x>=1:return 0.0
 return -(x*math.log2(x)+(1-x)*math.log2(1-x))
def features(n,clauses):
 occurrences=[0]*(n+1);positives=[0]*(n+1)
 widths=collections.Counter()
 pair_counts=collections.Counter()
 triples=collections.defaultdict(set)
 uf=list(range(n+1))
 def root(x):
  while uf[x]!=x:
   uf[x]=uf[uf[x]]
   x=uf[x]
  return x
 def join(a,b):
  a=root(a);b=root(b)
  if a!=b:uf[a]=b
 horn=0;allpos=0;lit_count=0;pos_count=0
 for cl in clauses:
  pos=sum(l>0 for l in cl);widths[len(cl)]+=1
  horn+=pos<=1;allpos+=pos==len(cl)
  lit_count+=len(cl);pos_count+=pos
  for l in cl:
   occurrences[abs(l)]+=1
   positives[abs(l)]+=l>0
  vs=sorted(set(abs(l) for l in cl))
  if vs:
   for v in vs[1:]:join(vs[0],v)
  if len(vs)<=12:
   for a,b in combinations(vs,2):pair_counts[a,b]+=1
  if len(cl)==3 and len(vs)==3:
   bits=sum(1<<i for i,v in enumerate(vs) if v in cl)
   triples[tuple(vs)].add(bits)
 deg=occurrences[1:]
 mean=statistics.fmean(deg)
 entropy_by_var=[entropy(positives[v]/occurrences[v]) for v in range(1,n+1) if occurrences[v]]
 repeated=sum(c-1 for c in pair_counts.values() if c>1)
 pairs=sum(pair_counts.values())
 xor3=sum(len(s)==4 and len({x.bit_count()%2 for x in s})==1 for s in triples.values())
 return {"variables":n,"clauses":len(clauses),"clause_variable_ratio":len(clauses)/n,
   "mean_clause_width":lit_count/max(len(clauses),1),
   "fraction_binary":widths[2]/max(len(clauses),1),
   "fraction_ternary":widths[3]/max(len(clauses),1),
   "horn_fraction":horn/max(len(clauses),1),
   "positive_fraction":pos_count/max(lit_count,1),
   "sign_balance_entropy":statistics.fmean(entropy_by_var) if entropy_by_var else 0,
   "degree_gini":gini(deg),
   "degree_cv":statistics.pstdev(deg)/mean if mean else 0,
   "reused_varpair_fraction":repeated/pairs if pairs else 0,
   "xor3_quartets":xor3,
   "connected_components":len({root(v) for v in range(1,n+1)}),
   "literal_occurrences":lit_count,
   "frac_pure_variables":sum((positives[i]==0 or positives[i]==occurrences[i]) for i in range(1,n+1) if occurrences[i])/max(sum(bool(x) for x in deg),1)}
def normalize_raw(raw,tmp):
 tmp.write_bytes(raw)
 got,clean,n,clauses,trailer=legacy.normalize_satlib(tmp)
 if got!=raw:raise ValueError("Source modified")
 return clean,n,clauses
def read_archives():
 out={}
 for cat,expected in SHA1.items():
  p=Path("/tmp")/(cat+".tar.gz")
  raw=p.read_bytes()
  if hashlib.sha1(raw).hexdigest()!=expected:raise RuntimeError("SATLIB SHA1 mismatch for "+cat)
  files={}
  with tarfile.open(p,"r:gz") as arc:
   for member in arc:
    if not member.isfile() or not member.name.endswith(".cnf"):continue
    if member.name.startswith("/") or ".." in Path(member.name).parts:
     raise RuntimeError("Unsafe SATLIB archive path")
    name=Path(member.name).name
    if name in files:raise RuntimeError("Duplicate SATLIB basename")
    f=arc.extractfile(member)
    if f is not None:files[name]=f.read()
  out[cat]=files
 return out
def ranks(v):
 order=sorted(range(len(v)),key=lambda i:v[i]);out=[0.0]*len(v)
 i=0
 while i<len(order):
  j=i+1
  while j<len(order) and v[order[j]]==v[order[i]]:j+=1
  for k in range(i,j):out[order[k]]=(i+j+1)/2
  i=j
 return out
def spearman(x,y):
 if len(x)<8:return None
 a=ranks(x);b=ranks(y);ma=statistics.fmean(a);mb=statistics.fmean(b)
 den=math.sqrt(sum((v-ma)**2 for v in a)*sum((v-mb)**2 for v in b))
 return (sum((p-ma)*(q-mb) for p,q in zip(a,b))/den) if den else None
def permutation_p(x,y,corr,seed):
 if corr is None:return None
 r=random.Random(seed)
 count=0;permutations=1200
 for _ in range(permutations):
  p=y[:];r.shuffle(p)
  val=spearman(x,p)
  if val is not None and abs(val)>=abs(corr)-1e-12:count+=1
 return (count+1)/(permutations+1)
def bh_adjust(tests):
 ids=[i for i,x in enumerate(tests) if x["permutation_p"] is not None]
 ids.sort(key=lambda i:tests[i]["permutation_p"])
 m=len(ids);q=1
 for rank,i in reversed(list(enumerate(ids,1))):
  q=min(q,tests[i]["permutation_p"]*m/rank)
  tests[i]["bh_q"]=min(1.,q)
def produce(out,medium_json,short_json):
 medium=json.loads(medium_json.read_text())
 short=json.loads(short_json.read_text())
 archives=read_archives()
 selections={x["sha256_normalized"]:x for x in medium["manifest"]}
 short_by_source={x["source"]:x for x in short["manifest"]}
 short_model={}
 for row in short["results"]:
  if row["solver"] not in ("kissat","v1531"):continue
  short_model.setdefault(row["case"],{})[row["solver"]]=statistics.median(
   x["seconds"] for x in row["runs"])
 short_routes={x["case"]:collections.Counter(y["route"] for y in x["runs"]).most_common(1)[0][0]
      for x in short["results"] if x["solver"]=="v1531"}
 medium_rows=[];short_rows=[]
 with tempfile.TemporaryDirectory() as folder:
  tmp=Path(folder)/"case.cnf"
  for category,pool in medium["all_calibration_records"].items():
   files=archives[category]
   for i,p in enumerate(pool):
    if "sha256_normalized" not in p or "source_path" not in p:continue
    basename=Path(p["source_path"]).name
    raw=files[basename]
    clean,n,clauses=normalize_raw(raw,tmp)
    if hashlib.sha256(raw).hexdigest()!=p["sha256_source"]:
     raise RuntimeError("Medium pilot raw SHA mismatch "+basename)
    if hashlib.sha256(clean).hexdigest()!=p["sha256_normalized"]:
     raise RuntimeError("Medium pilot normalized SHA mismatch "+basename)
    feat=features(n,clauses)
    entry={"dataset":"medium_pilot","category":category,"source":basename,
      "sha256":p["sha256_normalized"],"expected":p["expected"],
      "pilot_s":p.get("pilot_seconds"),"pilot_correct":p.get("pilot_correct"),
      "selected":p["sha256_normalized"] in selections,**feat}
    medium_rows.append(entry)
  root=Path("/tmp/satlib-go/testdata/satlib")
  for source,meta in short_by_source.items():
   raw=(root/source).read_bytes()
   clean,n,clauses=normalize_raw(raw,tmp)
   if hashlib.sha256(raw).hexdigest()!=meta["sha256_source"] or hashlib.sha256(clean).hexdigest()!=meta["sha256_normalized"]:
    raise RuntimeError("Short40 source identity mismatch "+source)
   case=meta["id"]
   entry={"dataset":"short40","category":meta["family"],"source":source,
     "sha256":meta["sha256_normalized"],"expected":meta["expected"],
     "kissat_median_s":short_model[case]["kissat"],
     "v1531_median_s":short_model[case]["v1531"],
     "delta_ms":1000*(short_model[case]["v1531"]-short_model[case]["kissat"]),
     "route":short_routes[case],**features(n,clauses)}
   short_rows.append(entry)
 if len(medium_rows)!=240 or len(short_rows)!=40:
  raise RuntimeError(f"Source audit incomplete: {len(medium_rows)} pilot, {len(short_rows)} short")
 def csvdump(name,items):
  keys=list(dict.fromkeys(k for item in items for k in item.keys()))
  with (out/name).open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(items)
 csvdump("medium_240_pilot_fingerprints.csv",medium_rows)
 csvdump("short40_fingerprints.csv",short_rows)
 tests=[]
 for category in SHA1:
  part=[x for x in medium_rows if x["category"]==category and x.get("pilot_correct") is True and isinstance(x.get("pilot_s"),(int,float))]
  for ix,feature in enumerate(FEATURES):
   x=[z[feature] for z in part];y=[z["pilot_s"] for z in part]
   rho=spearman(x,y)
   p=permutation_p(x,y,rho,SEED+ix*101+list(SHA1).index(category)*10000)
   tests.append({"category":category,"feature":feature,"n":len(part),
     "spearman_rho":rho,"permutation_p":p,"bh_q":None})
 bh_adjust(tests)
 csvdump("exploratory_correlations.csv",tests)
 route_features=[]
 for route in sorted({r["route"] for r in short_rows}):
  rr=[x for x in short_rows if x["route"]==route]
  route_features.append({"route":route,"n":len(rr),
    "median_delta_ms":statistics.median(x["delta_ms"] for x in rr),
    "mean_xor3_quartets":statistics.fmean(x["xor3_quartets"] for x in rr),
    "mean_reused_pair_fraction":statistics.fmean(x["reused_varpair_fraction"] for x in rr),
    "mean_clause_variable_ratio":statistics.fmean(x["clause_variable_ratio"] for x in rr),
    "mean_degree_gini":statistics.fmean(x["degree_gini"] for x in rr)})
 csvdump("route_structural_summary.csv",route_features)
 strong=sorted([x for x in tests if x.get("bh_q") is not None],key=lambda x:x["bh_q"])
 summary={"pilot_count":len(medium_rows),"short_count":len(short_rows),
  "pilot_counts_by_category":dict(collections.Counter(x["category"] for x in medium_rows)),
  "route_structural_summary":route_features,
  "exploratory_correlations":tests,
  "strongest_nominal_correlations":strong[:12],
  "passed_q_0p10":[x for x in strong if x["bh_q"]<.1],
  "warning":"Exploratory multiple-testing; q estimates not external validation, not a mathematical law. Random 3-SAT family and size confound aggregate effects."}
 (out/"structural_audit.json").write_text(json.dumps(summary,indent=2)+"\n")
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  plot=short_rows
  fig,ax=plt.subplots(figsize=(8,5))
  for route in sorted({z["route"] for z in plot}):
   zz=[z for z in plot if z["route"]==route]
   ax.scatter([z["reused_varpair_fraction"] for z in zz],[z["delta_ms"] for z in zz],label=route,alpha=.8)
  ax.axhline(0,ls="--",lw=1)
  ax.set(xlabel="Variable-pair reuse in clauses",ylabel="V15.3.1 - Kissat (ms)",
   title="Structural signature versus observed route (not causal)")
  ax.legend(fontsize=8)
  fig.tight_layout();fig.savefig(out/"structural_pair_reuse.png",dpi=160);plt.close(fig)
  cats=list(SHA1)
  fig,ax=plt.subplots(figsize=(8,5))
  for cat in cats:
   zz=[z for z in medium_rows if z["category"]==cat and z.get("pilot_correct") is True]
   ax.scatter([z["degree_gini"] for z in zz],[z["pilot_s"] for z in zz],label=cat,alpha=.45)
  ax.set(xlabel="Variable occurrence Gini",ylabel="Pilot Kissat seconds",
   title="Prespecified structural signal vs original Kissat hardness")
  ax.legend(fontsize=8);fig.tight_layout();fig.savefig(out/"structural_gini_pilot.png",dpi=160);plt.close(fig)
 except ImportError:pass
 print(json.dumps({"pilot_count":len(medium_rows),"short_count":len(short_rows),
  "route_summary":route_features,"strongest_tests":strong[:12],
  "q_below_0p1":summary["passed_q_0p10"]},indent=2),flush=True)

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--medium",type=Path,required=True)
 ap.add_argument("--short",type=Path,required=True)
 ap.add_argument("--out",type=Path,required=True)
 a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 produce(a.out,a.medium,a.short)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""Append-only cross-run benchmark memory. No held-out result may enter decision training."""
import argparse,io,json,os,pathlib,urllib.request,zipfile
p=argparse.ArgumentParser();p.add_argument("--collected",default="collected");p.add_argument("--out",default="ATLAS14_MEMORY.jsonl");a=p.parse_args()
repo=os.environ.get("GITHUB_REPOSITORY","Frane12/AndroidGameTest")
token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN","")
current=os.environ.get("GITHUB_RUN_ID","")
def get(url):
 req=urllib.request.Request(url,headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","User-Agent":"DRNAS-memory"})
 with urllib.request.urlopen(req,timeout=25) as r:return r.read()
history=[];previous=None
try:
 runs=json.loads(get("https://api.github.com/repos/"+repo+"/actions/workflows/drnas-atlas14-persistent-memory.yml/runs?per_page=30"))["workflow_runs"]
 for run in runs:
  if str(run["id"])==current or run["status"]!="completed" or run["conclusion"]!="success":continue
  arts=json.loads(get("https://api.github.com/repos/"+repo+"/actions/runs/"+str(run["id"])+"/artifacts?per_page=100"))["artifacts"]
  match=next((x for x in arts if x["name"]=="ATLAS14-MEMORY" and not x["expired"]),None)
  if match:
   blob=get(match["archive_download_url"])
   with zipfile.ZipFile(io.BytesIO(blob)) as z:
    history=[json.loads(line) for line in z.read("ATLAS14_MEMORY.jsonl").decode().splitlines() if line.strip()]
   previous=run["id"];break
except Exception as e:
 print("ATLAS14_MEMORY_LOAD_WARNING",str(e),flush=True)
# A missing history is visible, not silently presented as learned experience.
audits=sorted(pathlib.Path(a.collected).glob("audit_*.json"))
assert len(audits)==10,("missing shard audits",len(audits))
new=[];seen=set()
for path in audits:
 data=json.loads(path.read_text())
 for row in data["results"]:
  key=(current,row["sha256"],row["rep"],row["arm"])
  assert key not in seen;seen.add(key)
  new.append(dict(run_id=current,source="benchmark_holdout",**row))
history.extend(new)
pathlib.Path(a.out).write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in history))
# Strict split: these held-out measurements are for evaluation and must not be used as training examples.
report={"previous_run":previous,"history_rows":len(history),"new_rows":len(new),"training_rows":0,"policy_warm_start":False,"reason":"holdout leakage guard; evaluation-only until disjoint training cohort exists"}
pathlib.Path("ATLAS14_MEMORY_STATUS.json").write_text(json.dumps(report,indent=2))
print("ATLAS14_MEMORY_STATUS "+json.dumps(report,sort_keys=True),flush=True)

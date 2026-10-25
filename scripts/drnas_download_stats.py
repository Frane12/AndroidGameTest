#!/usr/bin/env python3
import json, os, urllib.request, datetime, pathlib
REPOS = ["Testturnip","DRNAS-Native-Blender","DRNAS-Native-FreeCAD","DRNAS-Native-SimulIDE","A8XX-Y-TUExperimental","AndroidGameTest","EmuExperimental"]
token=os.environ.get("GH_TOKEN","")
def get(url):
    req=urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","User-Agent":"DRNAS-stats","Authorization":"Bearer "+token} if token else {"Accept":"application/vnd.github+json","User-Agent":"DRNAS-stats"})
    with urllib.request.urlopen(req,timeout=30) as res:return json.load(res)
def releases(repo):
    page=1
    while True:
        batch=get(f"https://api.github.com/repos/Frane12/{repo}/releases?per_page=100&page={page}")
        if not batch:break
        yield from batch
        if len(batch)<100:break
        page+=1
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
result={"timestamp_utc":now,"repositories":{}}
for repo in REPOS:
    try:
        assets=[]
        for rel in releases(repo):
            for a in rel.get("assets",[]):
                assets.append({"id":a["id"],"name":a["name"],"download_count":a["download_count"],"release":rel["tag_name"],"draft":rel["draft"],"prerelease":rel["prerelease"]})
        result["repositories"][repo]={"total":sum(a["download_count"] for a in assets),"public_total":sum(a["download_count"] for a in assets if not a["draft"]),"assets":assets}
    except Exception as e:
        result["repositories"][repo]={"error":str(e)}
pathlib.Path("stats/history").mkdir(parents=True,exist_ok=True)
date=now[:10]
pathlib.Path(f"stats/history/{date}.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
pathlib.Path("stats/latest.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({r:{k:v for k,v in d.items() if k!="assets"} for r,d in result["repositories"].items()},indent=2))

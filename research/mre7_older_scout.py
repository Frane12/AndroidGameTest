#!/usr/bin/env python3
"""Official GBD 2021/2022/2023 source-only scout. Zero DRNAS solver calls."""
from __future__ import annotations
import hashlib,json,pathlib,urllib.parse,urllib.request,re,sys
import mre6b_blind_freeze as prior
ROOT=pathlib.Path("mre7_older")
YEARS=(2021,2022,2023)
BASE="https://benchmark-database.de/getinstances?context=cnf&query="
def ids(query):
    url=BASE+urllib.parse.quote(query,safe="")
    request=urllib.request.Request(url,headers={"User-Agent":"DRNAS-MRE7-Source-Pool-20261108"})
    with urllib.request.urlopen(request,timeout=40) as response:
        raw=response.read(350000)
    rows=[line.strip().rsplit("/",1)[-1] for line in raw.decode().splitlines() if line.strip()]
    if not all(re.fullmatch(r"[0-9a-f]{32}",x) for x in rows):
        raise RuntimeError("GBD_INVALID_SOURCE_INDEX "+url+" "+str(rows[:3]))
    if len(set(rows))!=len(rows):
        raise RuntimeError("GBD_DUPLICATE_SOURCE_INDEX")
    return rows,hashlib.sha256(raw).hexdigest()
def main():
    ROOT.mkdir(exist_ok=True)
    outcomes={}
    universe=set()
    for year in YEARS:
        sets={}
        for key,query in (("all",f"track=main_{year}"),
                           ("minisat1m_yes",f"track=main_{year} and minisat1m=yes")):
            try:
                sources,digest=ids(query)
                sets[key]=dict(count=len(sources),sha256=digest,samples=sources[:15],
                               all_ids=sources)
                universe.update(sources)
            except Exception as ex:
                sets[key]=dict(error=(type(ex).__name__+": "+str(ex))[:350])
        outcomes[str(year)]=sets
        print("MRE7_OLDER_SCOUT_YEAR",json.dumps({k:{z:v for z,v in d.items() if z!="all_ids"}
                for k,d in sets.items()},sort_keys=True),flush=True)
    prior_ids=set(x.strip() for x in prior.PRIOR.read_text().splitlines()
        if re.fullmatch("[0-9a-f]{32}",x.strip()))
    ids_from_repo,_=prior.inspect_repo_ids(universe)
    past=prior_ids|ids_from_repo
    summary=dict(years=YEARS,unique_source_ids=len(universe),
        already_seen_in_visible_git_registry=len(universe&past),
        historical_registry_not_exhaustive=True,
        cohorts=outcomes)
    (ROOT/"scout.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("MRE7_OLDER_FINAL",json.dumps(dict(years=YEARS,
        unique_source_ids=len(universe),
        already_seen_in_visible_git_registry=len(universe&past),
        cohorts={y:{k:{z:v for z,v in d.items() if z!="all_ids"}
                   for k,d in s.items()} for y,s in outcomes.items()}),
        sort_keys=True),flush=True)
if __name__=="__main__":main()

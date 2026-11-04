#!/usr/bin/env python3
"""R117 500-unique-real-CNF precommitted selection audit. Never silently replace missing cases."""
import hashlib,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as source
root=pathlib.Path('r117');root.mkdir(exist_ok=True)
# 2025 and 2026 are published independent official track lists, not generated CNFs.
lists={
 '2026':'https://satcompetition.github.io/2026/downloads/track_main_2026.uri',
 '2025':'https://satcompetition.github.io/2025/downloads/track_main_2025.uri'
}
excluded=set(x for _,x in source.PINS)
# Also exclude R116 structural pilot cases by known fixed source IDs.
excluded.update(['75429ff7acb5acb597abe01aa745c2a6','ad5b80bb4d1b60bee12163df25846801','80b163b706e0a16702173ec27f3d1331','65ee6b49612eccb7d213e4d950f23677'])
entries=[];sources={}
for year,url in lists.items():
 try:
  raw,_=source.request_url(url,150000,seconds=45)
  ids=[u.strip().rsplit('/',1)[-1] for u in raw.decode().splitlines() if u.strip()]
  assert len(ids)>=200 and len(ids)==len(set(ids))
  sources[year]=dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),count=len(ids))
  for id in ids:
   if id not in excluded:entries.append(dict(id=id,year=year,url='https://benchmark-database.de/file/'+id))
 except Exception as e:
  sources[year]=dict(url=url,error=str(e))
unique={e['id']:e for e in entries}
ranked=sorted(unique.values(),key=lambda e:hashlib.sha256(('DRNAS-R117-20261104-FROZEN-BLIND/'+e['id']).encode()).hexdigest())
chosen=ranked[:500]
manifest=dict(protocol='R117-500-REAL-SAT-CANDIDATE-PREFREEZE',sources=sources,
 excluded_count=len(excluded),candidate_count=len(unique),target=500,selected=len(chosen),
 selection='fixed SHA order before any download, structure inspection or solver timing',
 caveat='500 candidate IDs are not yet 500 verified downloaded original CNFs; possible overlap with other historical DRNAS tests',
 cases=chosen)
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('R117_SELECTION',json.dumps({k:v for k,v in manifest.items() if k!='cases'}),flush=True)
assert len(chosen)==500,'Insufficient official distinct candidates: do not claim 500'

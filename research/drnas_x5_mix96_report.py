#!/usr/bin/env python3
import argparse,collections,json,statistics
from pathlib import Path
from drnas_x5_bench import summarize
from drnas_x5_report import comparison

def report(root,out):
    manifests=[json.loads(p.read_text()) for p in root.rglob('manifest.json')]
    assert len(manifests)==4
    assert sorted(m['shard'] for m in manifests)==list(range(4))
    arms=['CORE','X5_NO_MIN','X5','Kissat','CaDiCaL','CMS']
    rows=[];sources=[]
    for p in root.rglob('manifest.json'):
        m=json.loads(p.read_text());rr=[json.loads(l) for l in p.with_name('trials.jsonl').read_text().splitlines()]
        assert m['arms']==arms and m['cap']==5 and m['repeats']==3 and len(m['logical_cpus'])==1
        assert m['total_count']==96 and m['count']==24 and m['shards']==4
        expected={(s['sha256'],a,r) for s in m['sources'] for a in arms for r in range(3)}
        actual={(r['sha256'],r['arm'],r['rep']) for r in rr}
        assert expected==actual and len(rr)==len(actual)==432
        assert all(not r['accepted'] or (r['verified'] and r['e2e_s']<=5) for r in rr)
        rows+=rr;sources+=m['sources']
    for key in ('candidate_sha256','baseline_sha256','model_sha256','checker_sha256','source_offset'):
        assert len({m[key] for m in manifests})==1,key
    assert len({s['sha256'] for s in sources})==96 and len(rows)==1728
    assert collections.Counter(s['level'] for s in sources)=={'small':32,'medium':32,'larger':32}
    assert len({s['family'] for s in sources})==8
    assert all(v==12 for v in collections.Counter(s['family'] for s in sources).values())
    for s in sources:
        outcomes={r['status'] for r in rows if r['sha256']==s['sha256'] and r['verified']}
        assert len(outcomes)<=1,('contradictory verified results',s['sha256'])
    result={'sources':96,'trials':1728,'cap_s':5,'repeats':3,'categories':8,
        'totals':summarize(rows,arms),
        'by_family':{f:summarize([r for r in rows if r['family']==f],arms) for f in sorted({s['family'] for s in sources})},
        'by_level':{f:summarize([r for r in rows if r['level']==f],arms) for f in ('small','medium','larger')},
        'comparisons':{a:{b:comparison(rows,a,b) for b in arms if b!=a} for a in ('X5','X5_NO_MIN')},
        'timing':{a:{'solve_sum_s':sum(r['solve_s'] for r in rows if r['arm']==a),'check_sum_s':sum(r['check_s'] for r in rows if r['arm']==a)} for a in arms},
        'caveat':'Synthetic templates; no outcome screening, no training. Source bootstrap does not imply generalization to industrial formula families.'}
    out.write_text(json.dumps(result,indent=2)+'\n');print('MIX96_SUMMARY',json.dumps(result,sort_keys=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();report(a.root,a.out)

#!/usr/bin/env python3
"""Fail-closed paired aggregation: distinct source CNFs are the bootstrap units."""
import argparse,collections,json,random
from pathlib import Path
from drnas_x5_bench import summarize

def comparison(rows,arm,base,draws=4000):
    pairs=collections.defaultdict(dict)
    for r in rows:
        if r['arm'] in (arm,base):pairs[r['sha256']].setdefault(r['arm'],[]).append(r)
    values=[];wins=losses=0
    for s,x in sorted(pairs.items()):
        assert set(x)=={arm,base}
        assert sorted(r['rep'] for r in x[arm])==sorted(r['rep'] for r in x[base])
        b=sum(r['PAR2'] for r in x[base]);t=sum(r['PAR2'] for r in x[arm])
        values.append((b,t));wins+=t<b*.99;losses+=t>b*1.01
    rng=random.Random(513117);est=[]
    for _ in range(draws):
        sample=[values[rng.randrange(len(values))] for _ in values]
        b=sum(x[0] for x in sample);t=sum(x[1] for x in sample)
        est.append((b-t)/b)
    est.sort();b=sum(x[0] for x in values);t=sum(x[1] for x in values)
    return {'baseline':base,'reduction':(b-t)/b,'speedup':b/t,'source_cluster_95':[est[int(draws*.025)],est[int(draws*.975)]],'sources':len(values),'wins_over_1pct':wins,'losses_over_1pct':losses}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--synthetic',type=int,default=96);p.add_argument('--official',type=int,default=12);a=p.parse_args()
    groups=collections.defaultdict(list);manifests=collections.defaultdict(list)
    for f in a.root.rglob('manifest.json'):
        m=json.loads(f.read_text());rows=[json.loads(l) for l in f.with_name('trials.jsonl').read_text().splitlines()]
        assert len(rows)==m['count']*m['repeats']*len(m['arms'])
        expected={(s['sha256'],rep,arm) for s in m['sources'] for rep in range(m['repeats']) for arm in m['arms']}
        got={(r['sha256'],r['rep'],r['arm']) for r in rows}
        assert got==expected and len(got)==len(rows)
        assert len(m['logical_cpus'])==1
        for r in rows:assert not r['accepted'] or (r['verified'] and r['e2e_s']<=m['cap'])
        groups[m['cohort']]+=rows;manifests[m['cohort']].append(m)
    reports={}
    for cohort,expected in [('synthetic',a.synthetic),('official_retrospective',a.official)]:
        if not expected:continue
        rows=groups[cohort];mm=manifests[cohort];assert rows and mm
        assert len({r['sha256'] for r in rows})==expected
        assert len({(r['sha256'],r['rep'],r['arm']) for r in rows})==len(rows)
        for key in ('candidate_sha256','baseline_sha256','model_sha256','checker_sha256','cap','repeats','total_count'):
            assert len({m[key] for m in mm})==1,key
        assert sorted(m['shard'] for m in mm)==list(range(mm[0]['shards']))
        assert len({tuple(m['arms']) for m in mm})==1
        arms=mm[0]['arms'];totals=summarize(rows,arms)
        comps={b:comparison(rows,'X5',b) for b in arms if b!='X5'}
        families={f:summarize([r for r in rows if r['family']==f],arms) for f in sorted({r['family'] for r in rows})}
        controls=['CORE','X46_LEARNED']
        no_losses=all(v['X5']['solved']>=v[b]['solved'] for v in families.values() for b in controls)
        better=all(comps[b]['reduction']>=.1 and comps[b]['source_cluster_95'][0]>0 for b in controls)
        ref_better=all(comps[b]['reduction']>=.1 and comps[b]['source_cluster_95'][0]>0 for b in ('Kissat','CaDiCaL','CMS') if b in arms)
        reports[cohort]={'sources':expected,'totals':totals,'comparisons_X5':comps,'by_family':families,'no_family_solved_regression':no_losses,'beats_native_controls':better,'beats_external_refs':ref_better if all(b in arms for b in ('Kissat','CaDiCaL','CMS')) else None,'promotion_pass':no_losses and better,'caveat':'Synthetic generated sources and retrospective SAT2024 are reported separately. Repeats are not independent sources.'}
    reports['global_promotion_pass']=bool(reports) and all(reports[k]['promotion_pass'] for k in ('synthetic','official_retrospective') if k in reports)
    a.out.write_text(json.dumps(reports,indent=2)+'\n');print('X5_REPORT',json.dumps(reports,sort_keys=True))
if __name__=='__main__':main()

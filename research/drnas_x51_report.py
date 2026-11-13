#!/usr/bin/env python3
import argparse,collections,json
from pathlib import Path
from drnas_x5_bench import summarize,sha
from drnas_x5_report import comparison
from drnas_x51_bench import ARMS
ROOT=Path(__file__).resolve().parents[1]
def report(root,out):
    protocol=json.loads((ROOT/'experiments/drnas_x51/protocol.json').read_text())
    groups=collections.defaultdict(list);manifests=collections.defaultdict(list)
    for p in root.rglob('manifest.json'):
        m=json.loads(p.read_text());rr=[json.loads(l) for l in p.with_name('trials.jsonl').read_text().splitlines()]
        assert m['arms']==ARMS and m['cap']==5 and m['repeats']==3 and len(m['logical_cpus'])==1
        assert m['total_count']==45 and m['count']==15 and m['shards']==3
        expected={(s['sha256'],a,r) for s in m['sources'] for a in ARMS for r in range(3)}
        assert {(r['sha256'],r['arm'],r['rep']) for r in rr}==expected and len(rr)==270
        for s in m['sources']:
            assert sha(p.parent/'sources'/(s['sha256']+'.cnf'))==s['sha256']
        for r in rr:
            assert not r['accepted'] or (r['verified'] and r['e2e_s']<=5)
            if r['arm'] in ('X51_BOUNDED','X51_ADAPTIVE'):
                assert all(t['max_clause_work']<=256 for t in r['telemetry'])
        groups[m['cohort']]+=rr;manifests[m['cohort']].append(m)
    assert set(groups)=={'diagnostic','holdout'}
    all_manifests=[m for mm in manifests.values() for m in mm]
    for key in ('candidate_sha256','baseline_sha256','frozen_x5_sha256','generator_sha256','model_sha256','checker_sha256','binary_sha256'):
        assert len({json.dumps(m[key],sort_keys=True) for m in all_manifests})==1,key
    results={}
    for split,rows in groups.items():
        mm=manifests[split];assert sorted(m['shard'] for m in mm)==[0,1,2]
        sources=[s for m in mm for s in m['sources']]
        assert len(sources)==45 and len(rows)==810
        assert {s['sha256'] for s in sources}=={s['sha256'] for s in protocol['sources'][split]}
        assert len({(r['sha256'],r['arm'],r['rep']) for r in rows})==810
        for s in sources:
            assert len({r['status'] for r in rows if r['sha256']==s['sha256'] and r['verified']})<=1
        families={f:summarize([r for r in rows if r['family']==f],ARMS) for f in ('cardinality','xor','random4')}
        comps={a:{b:comparison(rows,a,b) for b in ('X5','X5_NO_MIN','X51_PASSIVE','Kissat')} for a in ('X51_BOUNDED','X51_ADAPTIVE')}
        qualifies={a:all(comps[a][b]['reduction']>=.10 and comps[a][b]['source_cluster_95'][0]>0 for b in ('X5','X5_NO_MIN')) and all(v[a]['solved']>=v[b]['solved'] for v in families.values() for b in ('X5','X5_NO_MIN')) for a in comps}
        diagnostics={}
        for a in ARMS:
            rr=[r for r in rows if r['arm']==a];last=[r['telemetry'][-1] for r in rr if r['telemetry']]
            diagnostics[a]={'solve_sum_s':sum(r['solve_s'] for r in rr),'check_sum_s':sum(r['check_s'] for r in rr),
                'reported_unsat_unaccepted':sum(r['status']=='UNSAT' and not r['accepted'] for r in rr),
                'timeout_trials':sum(r['status']=='TIMEOUT' for r in rr),'trials_with_telemetry':len(last),
                'timeout_with_telemetry':sum(r['status']=='TIMEOUT' and bool(r['telemetry']) for r in rr),
                'sampled_totals':{k:sum(t[k] for t in last) for k in ('conflicts','propagations','min_calls','min_work','budget_exhaustions','removed','mode_changes','probes','propagation_s','analysis_s','minimize_s')}}
        results[split]={'sources':45,'trials':810,'totals':summarize(rows,ARMS),'by_family':families,'comparisons':comps,
            'passive_overhead':comparison(rows,'X51_PASSIVE','X5'),'qualifies_on_this_split':qualifies,'diagnostics':diagnostics}
    results['caveat']='Synthetic templates, no training or family inputs to policy. Analysis time includes minimization; telemetry on timeout is a partial snapshot. No automatic promotion.'
    out.write_text(json.dumps(results,indent=2)+'\n');print('X51_SUMMARY',json.dumps(results,sort_keys=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();report(a.root,a.out)

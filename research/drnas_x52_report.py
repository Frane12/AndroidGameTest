#!/usr/bin/env python3
import argparse,collections,json
from pathlib import Path
from drnas_x5_bench import summarize,sha
from drnas_x5_report import comparison
from drnas_x52_bench import ARMS,ROOT
KEYS=('conflicts','decisions','propagations','learnt','restarts','reduce_removed','binary_edges','binary_propagations')
def report(root,out):
    protocol=json.loads((ROOT/'experiments/drnas_x52/protocol.json').read_text());mm=[];rows=[];sources=[]
    for p in root.rglob('manifest.json'):
        m=json.loads(p.read_text());rr=[json.loads(l) for l in p.with_name('trials.jsonl').read_text().splitlines()]
        assert m['arms']==ARMS and m['cap']==5 and m['repeats']==3 and len(m['logical_cpus'])==1
        assert m['total_count']==25 and m['shards']==3 and len(m['sources'])==m['count']
        expect={(s['sha256'],a,rep) for s in m['sources'] for a in ARMS for rep in range(3)}
        assert {(r['sha256'],r['arm'],r['rep']) for r in rr}==expect and len(rr)==len(expect)
        for s in m['sources']:assert sha(p.parent/'sources'/(s['sha256']+'.cnf'))==s['sha256']
        for r in rr:
            assert not r['accepted'] or (r['verified'] and r['e2e_s']<=5)
            if r['arm'] in ('X5','X52_OFF'):assert r['proof_deletions']==0
            if r['arm']=='X52_DELETE' and r['status'] in ('SAT','UNSAT'):
                assert r['proof_deletions']==r['solver_stats']['reduce_removed']
        mm.append(m);rows+=rr;sources+=m['sources']
    assert sorted(m['shard'] for m in mm)==[0,1,2]
    for k in ('source_hashes','binary_hashes'):assert len({json.dumps(m[k],sort_keys=True) for m in mm})==1
    assert len(rows)==300 and len({(r['sha256'],r['arm'],r['rep']) for r in rows})==300
    assert len(sources)==25 and {s['sha256'] for s in sources}=={s['sha256'] for s in protocol['sources']}
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['sha256'],r['rep'])].append(r)
    matched=0
    for pair in groups.values():
        assert len({r['status'] for r in pair if r['verified']})<=1
        native=[r for r in pair if r['arm']!='Kissat' and r['status'] in ('SAT','UNSAT')]
        identities={(r['status'],tuple(r['solver_stats'][k] for k in KEYS),r['addition_sha256']) for r in native}
        assert len(identities)<=1,('search or addition stream changed',pair[0]['sha256'])
        matched+=len(native)>=2
    result={'sources':25,'trials':300,'search_equivalence_matched_pairs':matched,'cohorts':{}}
    for cohort in ('fresh24','known_replay'):
        rr=[r for r in rows if r['cohort']==cohort]
        result['cohorts'][cohort]={'totals':summarize(rr,ARMS),
            'by_family':{f:summarize([r for r in rr if r['family']==f],ARMS) for f in sorted({r['family'] for r in rr})},
            'comparisons':{b:comparison(rr,'X52_DELETE',b) for b in ('X5','X52_OFF','Kissat')} if cohort=='fresh24' else None,
            'timing':{a:{'solve_sum_s':sum(r['solve_s'] for r in rr if r['arm']==a),'check_sum_s':sum(r['check_s'] for r in rr if r['arm']==a),
                        'check_timeouts':sum(r['check_timeout'] for r in rr if r['arm']==a),
                        'checker_maxrss_completed_kib':max((r['checker_maxrss_kib'] or 0 for r in rr if r['arm']==a),default=0),
                        'proof_bytes_sum':sum(r['proof_bytes'] for r in rr if r['arm']==a),
                        'proof_deletions':sum(r['proof_deletions'] for r in rr if r['arm']==a) if a!='Kissat' else None} for a in ARMS}}
    result['known_trials']=[{k:r[k] for k in ('arm','rep','status','accepted','solve_s','check_s','check_timeout','proof_bytes','proof_deletions','checker_maxrss_kib','conflicts')} for r in rows if r['cohort']=='known_replay']
    result['caveat']='Fresh synthetic instances share templates. Known replay is diagnostic only. Verification time is censored on timeout; checker peak RSS is only available for completed checker processes. No automatic promotion.'
    out.write_text(json.dumps(result,indent=2)+'\n');print('X52_SUMMARY',json.dumps(result,sort_keys=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();report(a.root,a.out)

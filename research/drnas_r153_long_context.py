#!/usr/bin/env python3
"""60s paired main study, then 180s on sources no solver reported solved."""
import argparse,collections,json,os,pathlib
import drnas_r153_real_context as R
from drnas_r28_context_memory import Memory,file_sha
ROOT=pathlib.Path('r153_long_context')
SHARDS=3

def read_rows(path):return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines() if x.strip()]
def hard_sources(sources,rows):
    expected={(s['sha256'],arm,rep) for s in sources for arm in R.ARMS for rep in range(R.REPEATS)}
    observed=[(r['sha256'],r['arm'],r['rep']) for r in rows]
    assert len(observed)==len(set(observed)) and set(observed)==expected,'incomplete/duplicate main paired data'
    return [s for s in sources if not any(r['reported_solved'] for r in rows if r['sha256']==s['sha256'])]
def stage(sources,memory,shard,cap):
    R.CAP=float(cap);R.ROOT=ROOT/f'shard-{shard}'/f'cap-{cap}';R.ROOT.mkdir(parents=True,exist_ok=True);R.references.ROOT=R.ROOT
    R.run(sources,memory)
    return read_rows(R.ROOT/'results.jsonl')
def worker(shard,db):
    assert shard in range(SHARDS)
    sources=json.loads(pathlib.Path('r153_real_context/manifest.json').read_text())['sources']
    sources=[s for s in sources if s['id']//4==shard];assert len(sources)==4
    memory=Memory(db);digest=memory.digest()
    try:
        main=stage(sources,memory,shard,60);hard=hard_sources(sources,main)
        selection=dict(rule='No arm reported a solve in either 60s repetition',ids=[s['id'] for s in hard],sha256=[s['sha256'] for s in hard],cap_s=180,repetitions=R.REPEATS)
        (ROOT/f'shard-{shard}'/'hard-selection.json').write_text(json.dumps(selection,indent=2)+'\n')
        R.emit('R153_LONG_HARD_SELECTION',dict(shard=shard,**selection))
        # Same original CNF, seeds, arm list and runner; restart each solver with the larger budget.
        follow=stage(hard,memory,shard,180)
        assert memory.digest()==digest
        R.check_claims(main+follow)
        R.emit('R153_LONG_SHARD_PASS',dict(shard=shard,main_trials=len(main),hard_sources=len(hard),hard_trials=len(follow),memory_frozen=True))
    finally:memory.close()
def audit():
    sources=json.loads(pathlib.Path('r153_real_context/manifest.json').read_text())['sources'];assert len(sources)==12
    for name in ('cms-version.txt','cms.sha256'):
        assert len({(ROOT/f'shard-{s}'/name).read_text() for s in range(SHARDS)})==1,'CMS version differs across runners'
    prior_hashes=set()
    combined=[];all_rows=[]
    for cap in (60,180):
        rows=[]
        for shard in range(SHARDS):
            root=ROOT/f'shard-{shard}'
            report=json.loads((root/f'cap-{cap}'/'report.json').read_text());assert report['complete'] and report['memory_frozen']
            prior_hashes.add(report['memory_before']['stats_sha256'])
            assert report['memory_before']['stats_sha256']==report['memory_after']['stats_sha256']
            chunk=read_rows(root/f'cap-{cap}'/'results.jsonl');assert all(r['cap_s']==cap and r['shard']==shard for r in chunk)
            subset=[s for s in sources if s['id']//4==shard]
            if cap==180:
                main=read_rows(root/'cap-60'/'results.jsonl');subset=hard_sources(subset,main)
                selection=json.loads((root/'hard-selection.json').read_text());assert selection['sha256']==[s['sha256'] for s in subset]
            # Completeness check applies separately at each cap, including an empty hard cohort.
            hard_sources(subset,chunk);rows.extend(chunk)
        R.ROOT=ROOT/f'aggregate-{cap}';R.ROOT.mkdir(exist_ok=True);R.CAP=float(cap)
        R.check_claims(rows);summary=R.summarize(rows,True)
        combined.append(dict(cap_s=cap,sources=len({r['sha256'] for r in rows}),trials=len(rows),totals=summary['totals'],shards=summary['shards'],ratio_reference_over_memory=summary['ratio_reference_over_memory']))
        all_rows.extend(rows)
    R.check_claims(all_rows)
    assert len(prior_hashes)==1,'different memory priors across stages/runners'
    result=dict(complete=True,separate_stages=combined,one_CPU_per_solver=True,paired_same_runner_per_source=True,parallel_independent_runners=SHARDS,memory_frozen=True,promotion=False)
    (ROOT/'final.json').write_text(json.dumps(result,indent=2)+'\n');R.emit('R153_LONG_FINAL',result)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            for s in combined:
                f.write(f"## {s['cap_s']}s stage: {s['sources']} original formulas\n\n|Arm|Verified|Reported|PAR2 verified s|PAR2 reported s|\n|---|---:|---:|---:|---:|\n")
                for arm,m in s['totals'].items():f.write(f"|{arm}|{m['verified']}/{m['trials']}|{m['reported_solved']}|{m['PAR2_verified_s']:.3f}|{m['PAR2_reported_s']:.3f}|\n")
            f.write('\n180s is a conditional hard cohort. Do not pool its PAR2 with the 60s full cohort. Generic UNSAT without an independent certificate is separate.\n')
def selftest():
    sources=[dict(sha256='a'),dict(sha256='b')]
    rows=[dict(sha256=s['sha256'],arm=a,rep=r,reported_solved=False) for s in sources for a in R.ARMS for r in range(R.REPEATS)]
    assert len(hard_sources(sources,rows))==2
    rows[0]['reported_solved']=True;assert hard_sources(sources,rows)==[sources[1]]
    for bad in (rows[:-1],rows+[rows[0]]):
        try:hard_sources(sources,bad)
        except AssertionError:pass
        else:raise AssertionError('incomplete selection accepted')
    assert hard_sources([],[])==[]
    print('R153_LONG_SELECTION_SELFTEST_PASS completeness=true conditional_cohort=true no_duplicate_trials=true',flush=True)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','audit','selftest']);ap.add_argument('--shard',type=int,default=0);ap.add_argument('--db',default='drnas_memory/memory.sqlite');a=ap.parse_args()
    ROOT.mkdir(exist_ok=True)
    if a.action=='selftest':selftest();return
    if a.action=='prepare':
        R.CAP=60.;R.collect(pathlib.Path('real24_source'));return
    if a.action=='audit':audit();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});worker(a.shard,a.db)
if __name__=='__main__':main()

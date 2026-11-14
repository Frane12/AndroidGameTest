#!/usr/bin/env python3
"""Paired original SAT2024 CNFs: BDD / HALL1 / HALL2 / HALL3.

Every proof is checked by separate Python process against byte-exact source.
No DRAT/LRAT claims. Catalog UNSAT labels never replace a checked proof.
"""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time,statistics
ROOT=pathlib.Path(__file__).resolve().parents[2]
ARMS=[('BDD','--pcmax-capacity'),('HALL1','--pcmax-clause-guard'),
      ('HALL2','--pcmax-hall2'),('HALL3','--pcmax-hall3')]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--pcmax20',type=pathlib.Path,required=True)
    p.add_argument('--unseen3',type=pathlib.Path,required=True)
    p.add_argument('--budget-ms',type=int,default=5000)
    p.add_argument('--reps',type=int,default=2)
    args=p.parse_args()
    assert 250<=args.budget_ms<=6000 and args.reps in (1,2,3)
    if hasattr(os,'sched_setaffinity'):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    report20=json.loads((args.pcmax20/'report.json').read_text())['results']
    manifest3=args.unseen3/'source_manifest.json'
    if not manifest3.exists():manifest3=args.unseen3.parent/'source_manifest.json'
    report3=json.loads(manifest3.read_text())
    sources=[]
    for entry in report20:
        if entry.get('status')=='OK':
            sources.append((args.pcmax20/pathlib.Path(entry['path']).name,entry['sha256']))
    for entry in report3:
        sources.append((args.unseen3/entry['name'].removesuffix('.xz'),entry['sha256']))
    assert len(sources)==18,(len(sources),sources)
    assert all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in sources)
    assert len(set(sha for _,sha in sources))==len(sources)
    checks={'pcmax-capacity-v1':'check_capacity.py',
            'pcmax-clause-hall-v1':'check_clause_hall.py',
            'pcmax-hall3-hybrid-v1':'check_hall3_hybrid.py'}
    rows=[]
    for rep in range(args.reps):
        order=sources if rep%2==0 else list(reversed(sources))
        for path,sha in order:
            label=('UNSAT' if '-UNSAT.' in path.name else 'SAT' if '-SAT.' in path.name else 'UNKNOWN')
            arms=ARMS if rep%2==0 else list(reversed(ARMS))
            for name,flag in arms:
                dest=args.out/(path.name+'-'+name+f'-r{rep}.json')
                command=[str(binary),str(path.resolve()),'--mode','core','--time',
                         str(args.budget_ms/1000+1),flag,'--pcmax-only',
                         '--pcmax-budget-ms',str(args.budget_ms),
                         '--pcmax-certificate',str(dest.resolve())]
                start=time.perf_counter()
                child=subprocess.run(command,capture_output=True,text=True,
                                     timeout=args.budget_ms/1000+8)
                elapsed=time.perf_counter()-start
                tele=[json.loads(line[len('c PCMAX_CAPACITY '):]) for line in child.stdout.splitlines()
                      if line.startswith('c PCMAX_CAPACITY ')]
                t=tele[-1] if tele else {}
                verified=False;format=None;check_elapsed=0.0
                if child.returncode==20:
                    assert dest.is_file(),('CERT_MISSING',path.name,name)
                    proof=json.loads(dest.read_text())
                    format=proof.get('format')
                    assert format in checks,(format,name)
                    start_check=time.perf_counter()
                    cert_check=subprocess.run([sys.executable,
                      str((ROOT/'research/pcmax_capacity'/checks[format]).resolve()),
                      str(path.resolve()),str(dest.resolve())],capture_output=True,text=True,timeout=60)
                    check_elapsed=time.perf_counter()-start_check
                    assert cert_check.returncode==0,(path.name,name,format,cert_check.stderr[-1000:],cert_check.stdout[-1000:])
                    verified=True
                    assert label!='SAT',('FALSE_UNSAT_ON_SAT_CONTROL',path.name,name,proof)
                    status='UNSAT_CHECKED'
                else:
                    assert child.returncode==0 and not dest.exists(),('SOLVER_ERROR',child.returncode,path.name,name,child.stderr[-2000:])
                    status='UNKNOWN'
                row={'formula':path.name,'sha256':sha,'catalog_label':label,'arm':name,
                     'rep':rep,'status':status,'certificate_format':format,
                     'independent_check':verified,'wall_s':round(elapsed,6),
                     'checker_s':round(check_elapsed,6),'total_wall_s':round(elapsed+check_elapsed,6),
                     'reason':t.get('reason'),'one_logical_cpu':True,'budget_ms':args.budget_ms}
                rows.append(row)
                print('HALL3_ORIGINAL_TRIAL '+json.dumps(row,sort_keys=True),flush=True)
    stats={}
    for arm,_ in ARMS:
        subset=[r for r in rows if r['arm']==arm]
        stats[arm]={'tested':len(subset),'independently_checked_unsat':sum(r['independent_check'] for r in subset),
                    'unknown':sum(r['status']=='UNKNOWN' for r in subset),
                    'median_wall_s':round(statistics.median(r['wall_s'] for r in subset),6)}
    doc={'protocol':'HALL3-ORIGINAL-SAT2024-PAIRED-V1','original_sources':len(sources),
         'repetitions':args.reps,'trials':len(rows),'cpu_restriction':True,
         'checker_based_structural_proof_not_drat_lrat':True,'rows':rows,'stats':stats}
    (args.out/'report.json').write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n')
    print('HALL3_ORIGINAL_FINAL '+json.dumps({'sources':len(sources),'trials':len(rows),
          'stats':stats,'false_unsat':0},sort_keys=True),flush=True)

if __name__=='__main__':main()

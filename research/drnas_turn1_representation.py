#!/usr/bin/env python3
"""TURN1: fixed bijective representation intervention, one solver, one CPU.
Primary precommitted contrast: kissat_both versus kissat_plain at 60 seconds.
No XOR extraction, learned router, restarts, extra constraints or worker races.
"""
import argparse, collections, hashlib, itertools, json, lzma, os, pathlib
import random, re, signal, subprocess, sys, tempfile, time, urllib.request

ROOT = pathlib.Path('turn1')
SOURCE = ROOT / 'sources'
CAP, REPS = 60.0, 2
PROTO = 'DRNAS-TURN1-NEW12-BIJECTION-6ARMS-2REPS-60S-v1'
MODES = ('kissat_plain','cms_plain','kissat_signed','kissat_order','kissat_both','cms_both')
KISSAT = os.environ.get('TURN1_KISSAT','built/bin/kissat_4_0_4')
CMS = os.environ.get('TURN1_CMS','cryptominisat5')
EXCLUSIONS = ('r189/frozen/manifest.json','r199/candidates.json','ta3/candidates.json',
 'ta3_2026/manifest.json','r200/manifest.json','ta6/manifest.json',
 'ta7exclusions/ta7-manifest.json','ta7h_exclusions/ta7h-manifest.json','ta8/manifest.json')

def need(ok, msg):
    if not ok: raise RuntimeError('TURN1_FAIL_CLOSED '+str(msg))
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p, data):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, sort_keys=True, indent=2)+'\n')
def parse(p):
    n = count = None; clauses = []; pending = []
    for line in pathlib.Path(p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('c'): continue
        if line.startswith('p'):
            fields=line.split(); need(len(fields)==4 and fields[:2]==['p','cnf'],'header')
            n,count=map(int,fields[2:]); continue
        need(n is not None,'missing header')
        for tok in line.split():
            lit=int(tok); need(abs(lit)<=n,'out of bounds literal')
            if lit: pending.append(lit)
            else: clauses.append(pending); pending=[]
    need(n is not None and not pending and len(clauses)==count,'incomplete DIMACS')
    return n,clauses

def mapping(n, variant):
    rng=random.Random('TURN1-SIGNED-BIJECTION-v1')
    labels=list(range(1,n+1))
    if variant in ('signed','both'): rng.shuffle(labels)
    result=[0]+labels
    if variant in ('signed','both'):
        for i in range(1,n+1):
            if rng.getrandbits(1): result[i]=-result[i]
    return result

def transform(n, clauses, variant):
    mp=mapping(n,variant)
    out=[[mp[abs(v)] if v>0 else -mp[abs(v)] for v in c] for c in clauses]
    if variant in ('order','both'):
        rng=random.Random('TURN1-CLAUSE-LITERAL-ORDER-v1')
        for c in out: rng.shuffle(c)
        rng.shuffle(out)
    # Independent inverse replay checks the full clause multiset, retaining duplicates.
    inv={abs(mp[i]): (i if mp[i]>0 else -i) for i in range(1,n+1)}
    restored=[tuple(sorted(inv[abs(v)] if v>0 else -inv[abs(v)] for v in c)) for c in out]
    need(collections.Counter(restored)==collections.Counter(tuple(sorted(c)) for c in clauses),'bijection replay')
    need(len({abs(v) for v in mp[1:]})==n,'not a permutation')
    return out,mp

def write_cnf(p,n,clauses):
    pathlib.Path(p).write_text('p cnf %d %d\n'%(n,len(clauses))+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
def satisfies(clauses,model): return all(any(abs(v) in model and model[abs(v)]==(v>0) for v in c) for c in clauses)
def inverse_model(model,mp):
    return {i: model[abs(mp[i])] == (mp[i]>0) for i in range(1,len(mp)) if abs(mp[i]) in model}

def known():
    hashes=set(); ids=set()
    for p in EXCLUSIONS:
        need(pathlib.Path(p).is_file(),'missing exclusion '+p)
        for c in json.loads(pathlib.Path(p).read_text())['cases']:
            hashes.add(c['sha256']); ids.add(c['id'].split('-')[0])
    hashes.update(json.loads(pathlib.Path('ta3_2026/excluded_hashes.json').read_text())['sha256'])
    return hashes,ids

def fetch():
    previous,ids=known(); queue=json.loads(pathlib.Path('ta3_2026/preregistration.json').read_text())
    need(len(queue['source_queue'])==400,'official source queue')
    cases=[]; skipped=[]; SOURCE.mkdir(parents=True,exist_ok=True)
    for url in queue['source_queue']:
        if len(cases)==12: break
        ident=url.rsplit('/',1)[-1]
        need(re.fullmatch(r'https://benchmark-database\.de/file/[0-9a-f]{32}',url),'source domain')
        if ident in ids: continue
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'DRNAS-TURN1-frozen-source-only/1'})
            with urllib.request.urlopen(req,timeout=45) as response:
                compressed=response.read(queue['max_compressed_bytes']+1)
            need(0<len(compressed)<=queue['max_compressed_bytes'],'compressed size')
            decoder=lzma.LZMADecompressor()
            raw=decoder.decompress(compressed,max_length=queue['max_original_bytes']+1)
            need(decoder.eof and 0<len(raw)<=queue['max_original_bytes'],'raw size')
            header=re.search(rb'(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$',raw[:8192])
            need(header is not None,'CNF header')
            n,m=map(int,header.groups()); need(0<n<=150000 and 0<m<=160000,'size eligibility')
            h=hashlib.sha256(raw).hexdigest()
            need(h not in previous and h not in {c['sha256'] for c in cases},'SHA overlap')
            path=SOURCE/(ident+'.cnf'); path.write_bytes(raw); parse(path)
            cases.append(dict(id=ident,sha256=h,url=url,variables=n,clauses=m,bytes=len(raw)))
            print('TURN1_NEW_SOURCE',ident,h,flush=True)
        except Exception as err:
            skipped.append(dict(id=ident,reason=str(err)[:140]))
            print('TURN1_SOURCE_SKIP',ident,str(err)[:100],flush=True)
    need(len(cases)==12,'not enough new sources')
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=cases,skipped=skipped,
      selection_uses_results=False,globally_blind=False,known_manifest_SHA_disjoint=True))
    print('TURN1_SOURCE_FROZEN',len(cases),sha(ROOT/'manifest.json'),flush=True)

def verify():
    doc=json.loads((ROOT/'manifest.json').read_text()); need(doc['protocol']==PROTO,'protocol')
    cases=doc['cases']; need(len(cases)==12 and len({c['sha256'] for c in cases})==12,'12 sources')
    previous,_=known(); need(not previous.intersection(c['sha256'] for c in cases),'leakage')
    for p,h in json.loads((ROOT/'pins.json').read_text()).items(): need(sha(p)==h,'pin '+p)
    for c in cases: need(sha(SOURCE/(c['id']+'.cnf'))==c['sha256'],'original SHA')
    return sorted(cases,key=lambda c:c['sha256'])

def worker(source,mode,directory):
    start=time.perf_counter(); n,original=parse(source)
    variant=mode.split('_',1)[1]; mp=list(range(n+1)); path=pathlib.Path(source)
    if variant!='plain':
        clauses,mp=transform(n,original,variant)
        path=pathlib.Path(directory)/'transformed.cnf'; write_cnf(path,n,clauses)
    prep=time.perf_counter()-start
    command=([CMS,'--threads','1','--verb','0',str(path)] if mode.startswith('cms') else [KISSAT,str(path)])
    print(json.dumps(dict(event='solver_start',command=command,prep_s=prep,
        transformed_sha256=sha(path))),flush=True)
    # Parent owns one wall deadline and kills the entire process group.
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (pathlib.Path(directory)/'solver.log').write_text(result.stdout)
    verdicts=re.findall(r'^s (SATISFIABLE|UNSATISFIABLE)\s*$',result.stdout,re.M)
    need(len(verdicts)==1,'missing/ambiguous solver verdict')
    status='SAT' if verdicts[0]=='SATISFIABLE' else 'UNSAT'
    need(result.returncode==(10 if status=='SAT' else 20),'exit/verdict mismatch')
    model={}
    for line in result.stdout.splitlines():
        if line.startswith('v '):
            for tok in line[2:].split():
                v=int(tok)
                if v:
                    need(abs(v) not in model or model[abs(v)]==(v>0),'inconsistent model')
                    model[abs(v)]=v>0
    if status=='SAT':
        model=inverse_model(model,mp)
        need(satisfies(original,model),'original SAT witness failed')
        save(pathlib.Path(directory)/'model.json',model)
    print(json.dumps(dict(event='result',status=status,prep_s=prep,
      proof='SAT_ORIGINAL_MODEL_VERIFIED' if status=='SAT' else 'NO_INDEPENDENT_UNSAT_PROOF',
      transformed_sha256=sha(path))),flush=True)

def trial(case,mode,rep,index):
    source=SOURCE/(case['id']+'.cnf'); need(sha(source)==case['sha256'],'trial SHA')
    directory=ROOT/'raw'/str(index)/('%s-%s'%(rep,mode)); directory.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,__file__,'worker','--source',str(source),'--mode',mode,'--directory',str(directory)]
    start=time.perf_counter(); p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
    timed_out=False
    try: output,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-start)))
    except subprocess.TimeoutExpired:
        timed_out=True
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        output,_=p.communicate()
    elapsed=time.perf_counter()-start
    (directory/'worker.log').write_text(output)
    events=[]
    for line in output.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    terminal=[e for e in events if e.get('event')=='result']
    status='TIMEOUT'; proof='WALL_CAP_TIMEOUT'; prep=None; transformed=None
    if not timed_out and elapsed<CAP:
        need(p.returncode==0 and len(terminal)==1,'worker failed '+output[-1500:])
        end=terminal[0]; status=end['status']; proof=end['proof']; prep=end['prep_s']; transformed=end['transformed_sha256']
    if status=='SAT':
        # Outside charged trial, independently recheck saved original model.
        model={int(k):v for k,v in json.loads((directory/'model.json').read_text()).items()}
        need(satisfies(parse(source)[1],model),'parent witness check')
    row=dict(protocol=PROTO,id=case['id'],sha256=case['sha256'],mode=mode,rep=rep,shard=index,
      status=status,proof=proof,elapsed_s=round(min(CAP,elapsed),6),
      par2_s=round(2*CAP if status=='TIMEOUT' else elapsed,6),prep_s=prep,
      transformed_sha256=transformed,single_solver=True)
    print('TURN1_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(index):
    cases=verify(); need(0<=index<12,'shard')
    if hasattr(os,'sched_getaffinity'): os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for rep in range(REPS):
        order=list(MODES); random.Random(PROTO+cases[index]['sha256']+str(rep)).shuffle(order)
        for mode in order:
            rows.append(trial(cases[index],mode,rep,index)); save(ROOT/('shard-%d.json'%index),rows)
    print('TURN1_SHARD_PASS',index,len(rows),flush=True)

def audit():
    cases=verify(); rows=[]; keys=set()
    for i,c in enumerate(cases):
        subset=json.loads((ROOT/('shard-%d.json'%i)).read_text()); need(len(subset)==REPS*len(MODES),'partial shard')
        for r in subset:
            key=(r['sha256'],r['rep'],r['mode']); need(key not in keys,'duplicate'); keys.add(key)
            need(r['protocol']==PROTO and r['sha256']==c['sha256'] and r['id']==c['id'] and r['shard']==i,'source drift')
            need(r['mode'] in MODES and r['rep'] in range(REPS),'unexpected trial')
            need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'bad verdict')
            need(0<=r['elapsed_s']<=CAP,'deadline')
            need(abs(r['par2_s']-(2*CAP if r['status']=='TIMEOUT' else r['elapsed_s']))<.00002,'PAR2')
            need(r['status']!='SAT' or r['proof']=='SAT_ORIGINAL_MODEL_VERIFIED','witness')
        rows+=subset
        need(len({r['status'] for r in subset if r['status']!='TIMEOUT'})<=1,'contradictory verdicts')
    need(len(rows)==144,'144 trials required')
    expected={(c['sha256'],rep,mode) for c in cases for rep in range(REPS) for mode in MODES}
    need(keys==expected,'incomplete pair coverage')
    metrics={}
    bykey={(r['sha256'],r['rep'],r['mode']):r for r in rows}
    for mode in MODES:
        rr=[r for r in rows if r['mode']==mode]
        metrics[mode]=dict(PAR2_s=sum(r['par2_s'] for r in rr),solved=sum(r['status']!='TIMEOUT' for r in rr),attempts=len(rr))
    comparisons={}
    for mode,base in [('kissat_signed','kissat_plain'),('kissat_order','kissat_plain'),('kissat_both','kissat_plain'),('cms_both','cms_plain')]:
        pairs=[(sum(bykey[c['sha256'],rep,base]['par2_s'] for rep in range(REPS)),sum(bykey[c['sha256'],rep,mode]['par2_s'] for rep in range(REPS))) for c in cases]
        rng=random.Random(20261107); dist=[]
        for _ in range(5000):
            picked=rng.choices(pairs,k=len(pairs)); dist.append(sum(a for a,b in picked)/max(1e-9,sum(b for a,b in picked)))
        dist.sort(); regression=sum(b>1.10*a for a,b in pairs)
        comparisons[mode]=dict(base=base,ratio=metrics[base]['PAR2_s']/metrics[mode]['PAR2_s'],
          bootstrap95=[dist[125],dist[4875]],formula_regressions_over_10pct=regression,
          new_solved_sources=sum(a==2*CAP*REPS and b<a for a,b in pairs))
    primary=comparisons['kissat_both']
    signal_ok=primary['ratio']>1.05 and primary['bootstrap95'][0]>1 and primary['formula_regressions_over_10pct']<=1 and metrics['kissat_both']['solved']>=metrics['kissat_plain']['solved']
    report=dict(protocol=PROTO,status='TURN1_AUDIT_PASS',attempts=144,sources=12,cap_s=CAP,
      modes=metrics,comparisons=comparisons,primary='kissat_both versus kissat_plain',
      primary_performance_signal=signal_ok,promotion_allowed=False,independent_UNSAT_proof=False,
      known_manifest_SHA_disjoint=True,globally_blind=False,
      note='Secondary contrasts are exploratory; independent proof validation required before promotion.')
    save(ROOT/'report.json',report); save(ROOT/'all-trials.json',rows)
    lines=['# TURN1 representation intervention','', 'One CPU, one solver per attempt, all preprocessing and witness reconstruction charged.','',
      '| Mode | Solved / 24 | PAR2 seconds |','|---|---:|---:|']
    for mode,m in metrics.items(): lines.append('| %s | %d | %.6f |'%(mode,m['solved'],m['PAR2_s']))
    lines+=['', 'Primary: '+json.dumps(primary), '', 'Primary performance signal: '+str(signal_ok),
      'Generic UNSAT has no independent proof check; no promotion. Fresh against enumerated manifests, not globally blind.']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n'); print('TURN1_FINAL',json.dumps(report,sort_keys=True),flush=True)

def selftest():
    # Exhaustive assignment equivalence for signed renaming and full clause replay.
    rng=random.Random(41)
    for _ in range(60):
        n=5; cs=[[rng.choice((-1,1))*rng.randint(1,n) for _ in range(rng.randrange(5))] for _ in range(rng.randrange(12))]
        for variant in ('signed','order','both'):
            transformed,mp=transform(n,cs,variant)
            for bits in itertools.product((False,True),repeat=n):
                model=dict(enumerate(bits,1)); original=inverse_model(model,mp)
                need(satisfies(cs,original)==satisfies(transformed,model),'truth equivalence')
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/'empty.cnf'; write_cnf(p,2,[[],[1,-1]]); need(parse(p)==(2,[[],[1,-1]]),'empty clause parser')
        need(not satisfies([[1]],{1:False}),'wrong model accepted')
    print('TURN1_SELFTEST_PASS 5760 equivalence assignments plus inverse replay',flush=True)

def smoke():
    selftest()
    with tempfile.TemporaryDirectory() as d:
        for name,cs,expected in [('sat',[[1],[-1,2]],'SAT'),('unsat',[[1],[-1]],'UNSAT')]:
            p=pathlib.Path(d)/(name+'.cnf'); write_cnf(p,3,cs)
            for mode in MODES:
                sub=pathlib.Path(d)/(name+mode); sub.mkdir()
                result=subprocess.run([sys.executable,__file__,'worker','--source',str(p),'--mode',mode,'--directory',str(sub)],capture_output=True,text=True,timeout=10)
                need(result.returncode==0 and json.loads(result.stdout.splitlines()[-1])['status']==expected,'solver smoke '+mode+result.stdout+result.stderr)
    print('TURN1_SMOKE_PASS 12',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['fetch','selftest','smoke','shard','audit','worker'])
    p.add_argument('--shard',type=int,default=0); p.add_argument('--source'); p.add_argument('--mode',choices=MODES); p.add_argument('--directory'); a=p.parse_args()
    if a.action=='worker': worker(a.source,a.mode,a.directory)
    elif a.action=='shard': shard(a.shard)
    else: globals()[a.action]()

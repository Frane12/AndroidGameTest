#!/usr/bin/env python3
"""X47 STRESS: source-grouped, bounded, certificate-aware load benchmark.
No solver/policy edits, no training on test outcomes, no silently discarded crashes.
GNU time records solver CPU and peak RSS; wait4 supervises individual children.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, platform
from pathlib import Path
import random, resource, signal, statistics, subprocess, sys, tempfile, time

FAMILIES = ('planted3','planted4','modular3','xor_sat','color3_sat','php_unsat',
            'binary_sat','cardinality_sat','horn_sat','wide_sat','xor_unsat','random3')
ARMS = ('CORE','X46_8','X46_128','X46_LEARNED_8','X47_RISKGATE_8','KISSAT','CADICAL')
CAPS = (.25, 2., 15.)
PER_FAMILY = 256
SHARDS = 32
REPS = 2
SALT = 'DRNAS_X47_STRESS_20261113_21000000_V1'


def emit(tag, value):
    print(tag+' '+json.dumps(value, sort_keys=True, separators=(',',':')), flush=True)


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')


def canon(clauses):
    return sorted({tuple(sorted(set(c), key=lambda x:(abs(x), x<0))) for c in clauses
                   if not any(-x in c for x in c)})


def xor_clauses(vs, rhs):
    return [tuple(sorted((-v if b else v for v,b in zip(vs,bits)), key=lambda x:(abs(x),x<0)))
            for bits in itertools.product((0,1),repeat=len(vs)) if sum(bits)%2 != rhs]


def tier_for(i):
    return 0 if i<192 else 1 if i<240 else 2


def generate(family, i):
    tier=tier_for(i)
    rng=random.Random(int.from_bytes(hashlib.sha256(f'{SALT}|{family}|{i}'.encode()).digest()[:8],'big'))
    n=(40,120,220)[tier]+rng.randrange((25,55,120)[tier])
    witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    cs=[]; cert=None
    def planted(k, pool=None):
        vs=rng.sample(pool if pool is not None else range(1,n+1), k)
        c=[v*rng.choice((-1,1)) for v in vs]
        if not any(witness[abs(x)]==(x>0) for x in c): c[rng.randrange(k)] *= -1
        return c
    if family in ('planted3','planted4','random3'):
        k=4 if family=='planted4' else 3
        density=rng.uniform(8.5,10.5) if k==4 else rng.uniform(3.9,4.7)
        for _ in range(round(n*density)):
            cs.append(planted(k) if family!='random3' else [v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)])
        if family=='random3': witness=None
    elif family=='modular3':
        for start in range(1,n+1,12):
            pool=list(range(start,min(start+12,n+1)))
            if len(pool)>=3:cs.extend(planted(3,pool) for _ in range(4*len(pool)))
        cs.extend(planted(3) for _ in range(2*n))
    elif family=='xor_sat':
        for _ in range(n+7):
            vs=rng.sample(range(1,n+1),3)
            cs.extend(xor_clauses(vs, sum(witness[v] for v in vs)%2))
        cs.extend(planted(3) for _ in range(n))
    elif family=='color3_sat':
        nodes=(16,40,85)[tier]+rng.randrange(8); n=nodes*3
        colors=[rng.randrange(3) for _ in range(nodes)]
        witness=[False]+[colors[(v-1)//3]==(v-1)%3 for v in range(1,n+1)]
        for v in range(nodes):
            lits=[3*v+k+1 for k in range(3)];cs.append(lits)
            cs.extend([[-a,-b] for a,b in itertools.combinations(lits,2)])
        for a,b in itertools.combinations(range(nodes),2):
            if colors[a]!=colors[b] and rng.random()<(.3,.2,.14)[tier]:
                cs.extend([[-(3*a+k+1),-(3*b+k+1)] for k in range(3)])
    elif family=='php_unsat':
        holes=(4,6,8)[tier]+rng.randrange(2); pigeons=holes+1; core=holes*pigeons
        n=core+12+i%19
        cs.extend([list(range(p*holes+1,(p+1)*holes+1)) for p in range(pigeons)])
        cs.extend([[-(p*holes+h+1),-(q*holes+h+1)] for h in range(holes)
                   for p,q in itertools.combinations(range(pigeons),2)])
        aux={v:bool(rng.getrandbits(1)) for v in range(core+1,n+1)}
        for _ in range(4*(n-core)):
            c=[v*rng.choice((-1,1)) for v in rng.sample(range(core+1,n+1),3)]
            if not any(aux[abs(x)]==(x>0) for x in c):c[0]*=-1
            cs.append(c)
        cert={'type':'PHP','holes':holes,'pigeons':pigeons};witness=None
    elif family in ('binary_sat','horn_sat'):
        n=(120,1800,16000)[tier]+rng.randrange((40,300,2000)[tier])
        if family=='horn_sat':
            witness=[False]*(n+1)
            for _ in range(4*n):
                vs=rng.sample(range(1,n+1),rng.choice((2,3,4)))
                c=[-v for v in vs]
                if rng.random()<.7:c[0]*=-1
                cs.append(c)
        else:
            witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
            cs.extend(planted(2) for _ in range(4*n))
    elif family=='cardinality_sat':
        groups=(10,30,70)[tier];width=4;n=groups*width
        chosen=[rng.randrange(width) for _ in range(groups)]
        witness=[False]+[chosen[(v-1)//width]==(v-1)%width for v in range(1,n+1)]
        for g in range(groups):
            vs=list(range(g*width+1,g*width+width+1));cs.append(vs)
            cs.extend([[-a,-b] for a,b in itertools.combinations(vs,2)])
        for _ in range(3*n):
            a,b=rng.sample(range(1,n+1),2)
            if not(witness[a] and witness[b]):cs.append([-a,-b])
    elif family=='wide_sat':
        n=(90,900,8000)[tier]+rng.randrange((30,100,1000)[tier])
        witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
        cs.extend(planted(rng.choice((6,8,12))) for _ in range(3*n))
        cs.extend(planted(3) for _ in range(n))
    elif family=='xor_unsat':
        # Odd parity on a cycle: xor of all required equations gives 0=1.
        n=(24,90,210)[tier]+rng.randrange(15)
        rhs=[rng.randrange(2) for _ in range(n)]
        if sum(rhs)%2!=1:rhs[-1]^=1
        equations=[]
        for v in range(1,n+1):
            vs=[v,v%n+1];equations.append([vs,rhs[v-1]])
            cs.extend(xor_clauses(vs,rhs[v-1]))
        cert={'type':'GF2','equations':equations};witness=None
    else:raise ValueError(family)
    cs=canon(cs)
    text=f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
    sha=hashlib.sha256(text.encode()).hexdigest()
    source={'family':family,'index':i,'tier':tier,'cap':CAPS[tier],'n':n,'clauses':cs,
            'text':text,'sha':sha,'cert':cert,'cohort':'synthetic'}
    if witness is not None:
        assert all(any(witness[abs(l)]==(l>0) for l in c) for c in cs),'invalid constructed witness'
        source['truth']='SAT'
    elif cert:
        verify_certificate(source);source['truth']='UNSAT_CERTIFIED'
    else:source['truth']='UNKNOWN'
    return source


def verify_certificate(source):
    cert=source.get('cert')
    if not cert:return False
    cs=set(source['clauses'])
    if cert['type']=='PHP':
        h,p=cert['holes'],cert['pigeons'];assert p>h>=1
        for a in range(p): assert tuple(range(a*h+1,(a+1)*h+1)) in cs
        for b in range(h):
            for a,c in itertools.combinations(range(p),2):assert (-(a*h+b+1),-(c*h+b+1)) in cs
        return True
    if cert['type']=='GF2':
        basis={};contradiction=False
        for vs,rhs in cert['equations']:
            assert len(vs)==len(set(vs)) and all(1<=v<=source['n'] for v in vs)
            assert all(c in cs for c in xor_clauses(vs,rhs)), 'certificate row absent from original CNF'
            bits=sum(1<<(v-1) for v in vs)
            while bits:
                pivot=bits.bit_length()-1
                if pivot not in basis: basis[pivot]=(bits,rhs);break
                b,r=basis[pivot];bits^=b;rhs^=r
            else:
                if rhs:contradiction=True
        assert contradiction,'GF2 certificate did not prove contradiction'
        return True
    raise ValueError('unknown certificate')


def verify_sat(source, output):
    model={}
    if 's SATISFIABLE' not in output.splitlines():return False
    for line in output.splitlines():
        if line.startswith(('v ','v\t')):
            for token in line[1:].split():
                lit=int(token)
                if not lit:continue
                if abs(lit)>source['n'] or (abs(lit) in model and model[abs(lit)]!=(lit>0)):return False
                model[abs(lit)]=lit>0
    # Partial models accepted only when each original clause is already satisfied.
    return all(any(model.get(abs(l))==(l>0) for l in c if abs(l) in model) for c in source['clauses'])


def measured_process(cmd, cap, root, memory_mb):
    """Per-child GNU time plus wait4 supervision; no parent-Python RSS contamination."""
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024**2,)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(cap)+1,math.ceil(cap)+2))
        resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    out=root/'stdout.txt';err=root/'stderr.txt';meter=root/'resource.txt';start=time.monotonic();timed=False
    if meter.exists():meter.unlink()
    cmd=['/usr/bin/time','-f','X47_RESOURCE %U %S %M','-o',str(meter)]+cmd
    with out.open('w') as of,err.open('w') as ef:
        proc=subprocess.Popen(cmd,stdout=of,stderr=ef,start_new_session=True,preexec_fn=limits)
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-start>cap:
                timed=True
                # Leave GNU time alive to reap the timed-out solver and emit RSS.
                children=Path(f'/proc/{proc.pid}/task/{proc.pid}/children')
                try:pids=[int(v) for v in children.read_text().split()]
                except FileNotFoundError:
                    scan=subprocess.run(['ps','-o','pid=','--ppid',str(proc.pid)],capture_output=True,text=True,timeout=1)
                    pids=[int(v) for v in scan.stdout.split()]
                for child in pids:
                    try:os.kill(child,signal.SIGKILL)
                    except ProcessLookupError:pass
                until=time.monotonic()+.25
                while time.monotonic()<until:
                    pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
                    if pid:break
                    time.sleep(.001)
                if not pid:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    _,status,usage=os.wait4(proc.pid,0)
                break
            time.sleep(.001)
        proc.returncode=os.waitstatus_to_exitcode(status)
    metering=[x.split() for x in meter.read_text().splitlines() if x.startswith('X47_RESOURCE ')] if meter.exists() else []
    measured=bool(metering)
    cpu=float(metering[-1][1])+float(metering[-1][2]) if measured else usage.ru_utime+usage.ru_stime
    rss=int(metering[-1][3]) if measured else usage.ru_maxrss
    return {'rc':proc.returncode,'timeout':timed,'wall':time.monotonic()-start,
            'cpu':cpu,'rss_kib':rss,'resource_exact':measured,
            'stdout':out.read_text(errors='replace'),'stderr':err.read_text(errors='replace')}


def run_trial(args, source, arm, rep, root):
    cap=source['cap'];binary=args.bin_dir/('drnas' if arm not in ('KISSAT','CADICAL') else arm.lower())
    cnf=root/'original.cnf'
    command=[str(binary.resolve()),str(cnf)]
    if arm in ('KISSAT','CADICAL'):command.insert(1,'-q')
    if arm not in ('KISSAT','CADICAL'):
        command+=['--mode','core','--time',str(max(.01,cap*.98)),'--branch-at','4','--stats']
        if arm!='CORE':command+=['--x46-conflicts','128' if arm=='X46_128' else '8','--x46-probe-ms','2.5']
        if arm in ('X46_LEARNED_8','X47_RISKGATE_8'):command+=['--x46-model',str(args.model.resolve())]
        if arm=='X47_RISKGATE_8':command+=['--x47-guard',str(args.guard.resolve())]
    start=time.monotonic();r=measured_process(command,cap,root,args.memory_mb)
    verified=False;status='UNKNOWN';failure=None
    if r['timeout']:status='TIMEOUT'
    elif r['rc']==10:
        status='SAT';verified=verify_sat(source,r['stdout'])
        if not verified or source['truth']=='UNSAT_CERTIFIED':failure='INVALID_SAT'
    elif r['rc']==20:
        status='UNSAT';verified=verify_certificate(source)
        if source['truth']=='SAT':failure='FALSE_UNSAT'
    elif r['rc'] not in (0,):
        status='RESOURCE_OR_PROCESS_FAILURE';failure='PROCESS_'+str(r['rc'])
    elapsed=time.monotonic()-start
    solved=verified and elapsed<=cap and failure is None
    stats={};pre={};probe={}
    try:
        for line in r['stderr'].splitlines():
            for prefix,target in (('X41_STATS ',stats),('X45_COMPARE ',pre),('X46_PROBE ',probe)):
                if line.startswith(prefix):target.update(json.loads(line[len(prefix):]))
    except ValueError:failure='TELEMETRY_PARSE_FAILURE'
    if arm not in ('KISSAT','CADICAL') and not r['timeout'] and r['rc'] in (0,10,20) and not stats:
        failure='MISSING_NATIVE_TELEMETRY'
    if failure:solved=False
    row={'sha':source['sha'],'family':source['family'],'index':source['index'],'tier':source['tier'],
         'cohort':source['cohort'],'cap':cap,'arm':arm,'rep':rep,'status':status,'verified':verified,
         'solved':solved,'PAR2':elapsed if solved else 2*cap,'e2e_s':elapsed,'cpu_s':r['cpu'],
         'max_rss_kib':r['rss_kib'],'resource_exact':r['resource_exact'],'returncode':r['rc'],'failure':failure,
         'conflicts':stats.get('conflicts'),'decisions':stats.get('decisions'),
         'probe_triggered':probe.get('triggered',False),'probe_skipped':probe.get('skipped',False),
         'probe_ms':probe.get('probe_pair_wall_ms',0),'flip':bool(pre.get('reached') and pre.get('actual_literal')==-pre.get('baseline_literal',0)),
         'pre_hash':pre.get('pre_state_digest') if pre.get('reached') else None}
    if failure:
        evidence=args.out/'failures';evidence.mkdir(exist_ok=True)
        (evidence/(source['sha'][:16]+'.cnf')).write_text(source['text'])
        (evidence/(source['sha'][:16]+'_'+arm+'.log')).write_text(r['stdout'][-8000:]+'\n'+r['stderr'][-8000:])
    return row


def totals(rows):
    ret={}
    for arm in ARMS:
        group=[r for r in rows if r['arm']==arm]
        if not group:continue
        rss=sorted(r['max_rss_kib'] for r in group)
        ret[arm]={'runs':len(group),'solved':sum(r['solved'] for r in group),
          'verified_answers':sum(r['verified'] for r in group),'PAR2_s':sum(r['PAR2'] for r in group),
          'cpu_s':sum(r['cpu_s'] for r in group),'peak_rss_mib':max(rss)/1024,
          'p95_rss_mib':rss[int(.95*(len(rss)-1))]/1024,
          'probe_s':sum(r['probe_ms'] for r in group)/1000,'flips':sum(r['flip'] for r in group),
          'probe_skips':sum(r['probe_skipped'] for r in group),
          'process_failures':sum(bool(r['failure']) for r in group),
          'resource_measurements_fallback':sum(not r['resource_exact'] for r in group),
          'p99_e2e_s':sorted(r['e2e_s'] for r in group)[int(.99*(len(group)-1))],
          'timeouts':sum(r['status']=='TIMEOUT' for r in group),
          'unverified_unsat':sum(r['status']=='UNSAT' and not r['verified'] for r in group)}
    return ret


def run_sources(args, sources):
    args.out.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    model_sha=hashlib.sha256(args.model.read_bytes()).hexdigest();guard_sha=hashlib.sha256(args.guard.read_bytes()).hexdigest()
    unique=set();rows=[];completed=0;errors=0
    dump(args.out/'environment.json',{'platform':platform.platform(),'python':sys.version,'cpus':list(os.sched_getaffinity(0)),
        'memory_limit_mib':args.memory_mb,'model_sha':model_sha,'guard_sha':guard_sha,'repeats':REPS,
        'source_salt':SALT,'cpuinfo':Path('/proc/cpuinfo').read_text()[:1800],
        'native_sha':hashlib.sha256((args.bin_dir/'drnas').read_bytes()).hexdigest()})
    with tempfile.TemporaryDirectory(prefix='drnas-stress-') as d, (args.out/'trials.jsonl').open('w') as log, (args.out/'manifest.jsonl').open('w') as manifest:
        root=Path(d)
        for source in sources:
            if source['sha'] in unique:raise AssertionError('duplicate source SHA')
            unique.add(source['sha'])
            manifest.write(json.dumps({k:v for k,v in source.items() if k not in ('clauses','text','cert')},sort_keys=True)+'\n');manifest.flush()
            (root/'original.cnf').write_text(source['text'])
            assert hashlib.sha256((root/'original.cnf').read_bytes()).hexdigest()==source['sha']
            for rep in range(REPS):
                order=list(ARMS);random.Random(source['sha']+str(rep)).shuffle(order)
                paired=[]
                for arm in order:
                    row=run_trial(args,source,arm,rep,root);rows.append(row);paired.append(row)
                    log.write(json.dumps(row,sort_keys=True)+'\n');log.flush()
                    errors+=bool(row['failure'])
                hashes={r['pre_hash'] for r in paired if r['pre_hash']}
                if len(hashes)>1:raise AssertionError('different pre-intervention state across native arms')
                answers={r['status'] for r in paired if r['verified']}
                if len(answers)>1 or ('SAT' in answers and any(r['status']=='UNSAT' for r in paired)):
                    raise AssertionError('SAT witness contradicts another reported UNSAT')
            completed+=1
            if completed%8==0:emit('X47_STRESS_PROGRESS',{'shard':args.shard,'sources':completed,'runs':len(rows),'errors':errors})
    assert hashlib.sha256(args.model.read_bytes()).hexdigest()==model_sha
    assert hashlib.sha256(args.guard.read_bytes()).hexdigest()==guard_sha
    summary={'sources':completed,'shard':args.shard,'runs':len(rows),'errors':errors,'arms':totals(rows),'complete':True}
    dump(args.out/'summary.json',summary);emit('X47_STRESS_FINAL',summary)
    if errors:raise SystemExit('benchmark recorded process/correctness failures; see retained evidence')


def official_sources(count):
    # Original bytes, not rewritten formula; retrospective, never globally blind.
    import drnas_x47_official_dedup as loader
    cases=loader.official_sources(count)
    for src in cases:
        clauses=[];pending=[]
        for line in src['content'].splitlines():
            if not line.strip() or line.lstrip().startswith(('c','p','%')):continue
            for token in line.split():
                if token in ('c','%'):break
                lit=int(token)
                if lit:pending.append(lit)
                else:clauses.append(tuple(pending));pending=[]
        assert not pending and len(clauses)==src['nclauses']
        yield {'family':src['family'],'index':src['source_id'],'tier':3,'cap':15.,'n':src['nvars'],
               'clauses':clauses,'text':src['content'],'sha':src['sha256'],'cert':None,'truth':'UNKNOWN',
               'cohort':'official_retrospective','archive_path':src['archive_path']}


def aggregate(root, output):
    paths=sorted(root.rglob('trials.jsonl'));cohorts=collections.defaultdict(list)
    for p in paths:
        for line in p.read_text().splitlines():
            r=json.loads(line);cohorts[r['cohort']].append(r)
    report={};failure=False
    for cohort,rows in cohorts.items():
        ids=set();cases=collections.defaultdict(lambda:collections.defaultdict(list))
        for r in rows:
            key=(r['sha'],r['arm'],r['rep']);assert key not in ids,'duplicate trial across shards';ids.add(key)
            cases[r['sha']][r['arm']].append(r)
        complete={s:arms for s,arms in cases.items() if set(arms)==set(ARMS) and all(len(v)==REPS for v in arms.values())}
        result={'observed_sources':len(cases),'paired_complete_sources':len(complete),'partial_sources':len(cases)-len(complete),
                'totals':totals(rows),'by_family':{},'by_tier':{},'comparison':{}}
        for family in sorted({r['family'] for r in rows}):result['by_family'][family]=totals([r for r in rows if r['family']==family])
        for tier in sorted({r['tier'] for r in rows}):result['by_tier'][tier]=totals([r for r in rows if r['tier']==tier])
        for arm in ARMS[1:]:
            pairs=[]
            for sha,arms in complete.items():
                b=statistics.mean(r['PAR2'] for r in arms['CORE']);a=statistics.mean(r['PAR2'] for r in arms[arm])
                pairs.append((sha,b,a,arms['CORE'][0]['family']))
            if not pairs:continue
            bs=sum(p[1] for p in pairs);cs=sum(p[2] for p in pairs);rng=random.Random(470048)
            vals=[]
            for _ in range(2000):
                sample=[pairs[rng.randrange(len(pairs))] for _ in pairs]
                b=sum(p[1] for p in sample);a=sum(p[2] for p in sample);vals.append((b-a)/b)
            vals.sort()
            losses=sorted(pairs,key=lambda p:p[2]-p[1],reverse=True)
            result['comparison'][arm]={'relative_PAR2_reduction':(bs-cs)/bs,'speedup_x':bs/cs,
                'source_cluster_CI95':[vals[49],vals[1949]],'N_sources':len(pairs),
                'top_regressions':[{'sha':p[0],'family':p[3],'core_mean_PAR2':p[1],'arm_mean_PAR2':p[2]} for p in losses[:12]],
                'wins':sum(p[2]<p[1]*.95 for p in pairs),'losses':sum(p[2]>p[1]*1.05 for p in pairs),
                'regression_over_2x':sum(p[2]>2*p[1] for p in pairs)}
        report[cohort]=result
        expected=3072 if cohort=='synthetic' else 32
        if len(complete)!=expected or any(r['failure'] for r in rows):failure=True
    if 'synthetic' not in report or 'official_retrospective' not in report:failure=True
    dump(output,{'cohorts':report,'complete_expected_cohorts':not failure,
        'primary':'X46_LEARNED_8 vs CORE; source-level repeats; no automatic promotion',
        'limits':'Generator-family dependence, correlated repeats, capped runtime and uncertified general UNSAT; report family/tier results separately.'})
    emit('X47_STRESS_AGGREGATE',{'complete':not failure,'sources':{k:v['paired_complete_sources'] for k,v in report.items()}})
    if failure:raise SystemExit('partial or failed benchmark, not a complete success')


def selftest():
    # All 12 families x 3 scales, deterministic re-generation and certificate tests.
    seen=set()
    for family in FAMILIES:
        for i in (0,192,240):
            s=generate(family,i);assert s['sha'] not in seen;seen.add(s['sha'])
            assert s['sha']==generate(family,i)['sha']
            if s['cert']:assert verify_certificate(s)
    tiny={'n':2,'clauses':[(1,2),(-1,2)]}
    assert verify_sat(tiny,'s SATISFIABLE\nv 2 0\n')
    assert not verify_sat(tiny,'s SATISFIABLE\nv -2 0\n')
    with tempfile.TemporaryDirectory() as d:
        p=measured_process(['/usr/bin/python3','-S','-c','print(42)'],3.,Path(d),512)
        assert p['rc']==0 and p['resource_exact'] and p['rss_kib']>0 and '42' in p['stdout']
        p=measured_process(['/usr/bin/python3','-S','-c','import time;time.sleep(2)'],.1,Path(d),512)
        assert p['timeout'] and p['rc']!=0 and p['resource_exact']
    emit('X47_STRESS_SELFTEST_PASS',{'generator_tier_combinations':len(seen),'resource_accounting':True})


def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=('selftest','run','official','aggregate'))
    ap.add_argument('--bin-dir',type=Path,default=Path('bundle/bin'));ap.add_argument('--model',type=Path,default=Path('bundle/model.txt'))
    ap.add_argument('--guard',type=Path,default=Path('bundle/guard.txt'));ap.add_argument('--shard',type=int,default=0)
    ap.add_argument('--out',type=Path,default=Path('stress_results'));ap.add_argument('--root',type=Path,default=Path('results'))
    ap.add_argument('--memory-mb',type=int,default=1536);ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
    if a.command=='selftest':selftest()
    elif a.command=='aggregate':aggregate(a.root,a.out)
    elif a.command=='official':run_sources(a,official_sources(32))
    else:
        assert 0<=a.shard<SHARDS
        if a.smoke:sources=(generate(f,0) for f in FAMILIES)
        else:sources=(generate(f,i) for f in FAMILIES for i in range(PER_FAMILY) if i%SHARDS==a.shard)
        run_sources(a,sources)

if __name__=='__main__':main()

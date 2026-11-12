#!/usr/bin/env python3
"""Serial original-source retrospective replay; reported and independently verified scores."""
import argparse,collections,hashlib,itertools,json,os,pathlib,random,re,signal,statistics,subprocess,time
from drnas_r28_native_check import parse_dimacs,verify
ROOT=pathlib.Path('r28_native_results')
ARMS=['R28_NATIVE_FAST','R28_NATIVE_DIRECT','LTM8_FAST','R28_EXACT','R153_EXACT','R28_CMS','Kissat','CaDiCaL','CryptoMiniSat']
REFS=['Kissat','CaDiCaL','CryptoMiniSat']
EXTREME='243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(tag,obj):print(tag,json.dumps(obj,sort_keys=True),flush=True)
def sources(fixtures):
    manifests=list((fixtures/'r153').rglob('manifest.json'))
    matches=[(p,json.loads(p.read_text())) for p in manifests]
    matches=[(p,m) for p,m in matches if m.get('protocol')=='DRNAS-R154-UNSEEN-LIGHTSOUT-XOR-UNIT-TRANSFER-20261105-v1']
    assert len(matches)==1,('expected original manifest',manifests)
    p,m=matches[0];assert len(m['cases'])==25
    cases=[]
    for c in m['cases']:
        f=p.parent/(c['id']+'.cnf');assert sha(f)==c['sha256'],c
        cases.append(dict(c,path=str(f),dataset='historical25'))
    targets=[p for p in (fixtures/'r115').rglob('*.cnf') if sha(p)==EXTREME]
    assert targets,'exact R32q/R115 original CNF missing'
    cases.append(dict(id='R115_75429ff7',path=str(targets[0]),sha256=EXTREME,cohort='historical_14k',dataset='historical14k'))
    unique={}
    for c in cases:
        if c['sha256'] not in unique:unique[c['sha256']]=c
    return list(unique.values())
def controls():
    root=ROOT/'controls';root.mkdir(exist_ok=True,parents=True);cases=[];rng=random.Random(28153160)
    def add(name,n,cs):
        p=root/(name+'.cnf');p.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
        cases.append(dict(id=name,path=str(p),sha256=sha(p),cohort=name.split('_')[0],dataset='synthetic_controls'))
    for contradiction in (False,True):
        cs=[]
        for i in range(1,80):cs += [[i,-i-1],[-i,i+1]]
        cs += [[1]]
        if contradiction:cs += [[-80]]
        add('xor_'+str(contradiction),80,cs)
    for holes in (4,6):
        n=holes*(holes+1);rows=[list(range(i*holes+1,(i+1)*holes+1)) for i in range(holes+1)]
        cs=rows+ [[-rows[i][k],-rows[j][k]] for i in range(holes+1) for j in range(i+1,holes+1) for k in range(holes)]
        add('php_'+str(holes),n,cs)
    for n in (80,120,180,240):
        witness=[rng.getrandbits(1) for _ in range(n)];cs=[]
        for _ in range(n*5):
            vs=rng.sample(range(1,n+1),3);c=[v if rng.getrandbits(1) else -v for v in vs]
            if not any(witness[abs(v)-1]==(v>0) for v in c):c[0]=-c[0]
            cs.append(c)
        add('planted3sat_'+str(n),n,cs)
    return cases

def command(arm,p,cap,seed):
    if arm.startswith('R28_NATIVE_'):return ['mre_r28_native/drnas_r28_native',p,'--time',str(cap),'--seed',str(seed),'--profile',arm.rsplit('_',1)[1].lower()]
    if arm=='LTM8_FAST':return ['mre_atlas23/bin/drnas_ltm8_base',p,'--mode','LTM8_FAST','--time',str(cap),'--seed',str(seed),'--policy','1.0,0.85']
    if arm in ('R28_EXACT','R153_EXACT','R28_CMS'):
        binary='r153_reference' if arm=='R153_EXACT' else 'r28_reference'
        backend=str((ROOT/'cms-one-thread.sh').resolve()) if arm=='R28_CMS' else '/usr/bin/false'
        return ['mre_r28_native/'+binary,p,backend]
    if arm=='Kissat':return ['built/bin/kissat_4_0_4','--seed='+str(seed),p]
    if arm=='CaDiCaL':return ['built/bin/cadical_3_0_1','--seed='+str(seed),p]
    return ['cryptominisat5','--threads','1','--verb','0','--random',str(seed),p]

def trial(c,arm,stage,rep,cap):
    source=parse_dimacs(c['path']);seed=17+rep*12
    env=dict(os.environ,DRNAS_LTM8_MEMORY='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    for k in ('DRNAS_LTM13_DIRECT','DRNAS_LTM13_FIXED'):env.pop(k,None)
    cmd=command(arm,c['path'],cap,seed);start=time.perf_counter()
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    timed=False
    try:out,err=p.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        timed=True;os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
    elapsed=time.perf_counter()-start
    # Reference and native stages receive the same external deadline, including launch and parsing.
    timed=timed or elapsed>cap
    begin=time.perf_counter();status,valid=('TIMEOUT',False) if timed else verify(source,out,p.returncode)
    verify_s=time.perf_counter()-begin
    if not timed and p.returncode not in (0,10,20) and not (arm in ('R28_EXACT','R153_EXACT') and p.returncode==1):
        raise RuntimeError((arm,p.returncode,err[-1000:],out[-1000:]))
    reported=status.startswith(('SAT_','UNSAT_'))
    telemetry=[x for x in out.splitlines() if any(k in x for k in ('LTM8_LEARNING','LTM13_WINDOW','R28_NATIVE route','ATLAS13_TRIAL'))]
    row=dict(stage=stage,shard=0,id=c['id'],sha256=c['sha256'],cohort=c['cohort'],dataset=c['dataset'],arm=arm,rep=rep,seed=seed,cap_s=cap,status=status,verified=valid,reported_solved=reported,e2e_s=elapsed,verify_s=verify_s,PAR2_reported_s=elapsed if reported else 2*cap,PAR2_verified_s=elapsed if valid else 2*cap,returncode=p.returncode,learning_windows_logged=sum('LTM13_WINDOW' in x for x in telemetry),telemetry=telemetry[-4:])
    # Retain compact mathematical proofs and witnesses, never large generic search proofs.
    if valid:
        proof=ROOT/'certificates'/f'{stage}-{c["sha256"][:16]}-{arm}-{rep}.txt'
        proof.parent.mkdir(exist_ok=True);proof.write_text(out)
    return row

def summary(rows,complete=False):
    groups={};regressions=[];extremes=[]
    for stage in sorted({r['stage'] for r in rows}):
        subset=[r for r in rows if r['stage']==stage]
        for group in ['ALL']+sorted({r['cohort'] for r in subset}):
            rs=[r for r in subset if group=='ALL' or r['cohort']==group];agg={}
            for arm in sorted({r['arm'] for r in rs}):
                a=[r for r in rs if r['arm']==arm]
                agg[arm]={k:sum(r[k] for r in a) for k in ('e2e_s','PAR2_reported_s','PAR2_verified_s','verified','reported_solved')}
                agg[arm].update(trials=len(a),unique_verified=len({r['sha256'] for r in a if r['verified']}))
            groups[stage+'/'+group]=agg
        paired=collections.defaultdict(dict)
        for r in subset:paired[(r['sha256'],r['rep'])][r['arm']]=r
        for arms in paired.values():
            for name in ('R28_NATIVE_FAST','R28_NATIVE_DIRECT'):
                a=arms.get(name)
                if not a:continue
                for ref in REFS+['LTM8_FAST']:
                    b=arms.get(ref)
                    if not b:continue
                    if b['verified'] and (not a['verified'] or a['e2e_s']>b['e2e_s']/0.7):regressions.append(dict(stage=stage,id=a['id'],arm=name,reference=ref,rep=a['rep'],candidate_s=a['e2e_s'],reference_s=b['e2e_s'],candidate_status=a['status']))
                    if a['verified']:
                        if b['verified']:ratio=b['e2e_s']/a['e2e_s'];kind='measured'
                        elif b['status']=='TIMEOUT':ratio=b['cap_s']/a['e2e_s'];kind='timeout_lower_bound'
                        else:continue
                        extremes.append(dict(stage=stage,id=a['id'],arm=name,reference=ref,rep=a['rep'],ratio=ratio,kind=kind))
    result=dict(complete=complete,shards=[0],trials=len(rows),groups=groups,regressions=regressions,extremes=sorted(extremes,key=lambda x:x['ratio'],reverse=True)[:30],promotion='NONE: retrospective selection; require unseen general holdout and >=30% lower PAR2 against best reference')
    (ROOT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixtures',type=pathlib.Path,default=pathlib.Path('r28_fixtures'));ap.add_argument('--local-smoke',action='store_true');a=ap.parse_args()
    ROOT.mkdir(exist_ok=True);cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    emit('R28_NATIVE_SINGLE_CPU',cpu)
    wrapper=ROOT/'cms-one-thread.sh';wrapper.write_text('#!/bin/sh\nexec cryptominisat5 --threads 1 --verb 0 "$1"\n');wrapper.chmod(0o755)
    synthetic=controls();historical=[] if a.local_smoke else sources(a.fixtures)
    allcases=historical+synthetic;assert len({c['sha256'] for c in allcases})==len(allcases)
    (ROOT/'sources.json').write_text(json.dumps(allcases,indent=2)+'\n')
    plans=[('controls',synthetic,1.0 if a.local_smoke else 3.0)]
    if historical:
        spotlight=[c for c in historical if c['sha256']==EXTREME]
        plans=[('screen_original',historical,3.0),('controls',synthetic,3.0),('spotlight_R115',spotlight,60.0)]
        # Two frozen Lights-Out cases selected by source metadata, before observing performance.
        lights=[c for c in historical if 'light' in json.dumps(c).lower()]
        if lights:plans.append(('spotlight_LightsOut',sorted(lights,key=lambda c:c['sha256'])[:2],20.0))
    arms=ARMS[:3] if a.local_smoke else ARMS
    emit('R28_NATIVE_PLAN',dict(arms=arms,repetitions=2,stages=[dict(stage=s,sources=len(cs),cap_s=cap) for s,cs,cap in plans]))
    rows=[];claims=collections.defaultdict(set)
    with (ROOT/'results.jsonl').open('w') as f:
        for stage,cases,cap in plans:
            for c in cases:
                for rep in range(2):
                    order=list(arms);random.Random(c['sha256']+str(rep)).shuffle(order)
                    for arm in order:
                        r=trial(c,arm,stage,rep,cap);rows.append(r)
                        if r['reported_solved']:claims[c['sha256']].add('UNSAT' if r['status'].startswith('UNSAT') else 'SAT')
                        assert len(claims[c['sha256']])<=1,('solver contradiction',c['id'])
                        f.write(json.dumps(r)+'\n');f.flush();emit('R28_NATIVE_TRIAL',r)
                partial=summary(rows);emit('R28_NATIVE_PROGRESS',dict(trials=len(rows),stage=stage,id=c['id']))
    result=summary(rows,True);emit('R28_NATIVE_FINAL',dict(trials=len(rows),groups=result['groups']))
if __name__=='__main__':main()

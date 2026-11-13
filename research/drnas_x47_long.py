#!/usr/bin/env python3
"""30,000-source continual training, persistent audit memory, unchanged native X4.7."""
import argparse,copy,gzip,hashlib,json,os,random,sqlite3,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
import drnas_x47 as X
import x47_long_models as M
from x47_models import write_model

PROTOCOL='X47-LONG-30K-v1'
WORK=50000
DATA_BRANCH='experiment/drnas-x47-memory-store-20261113'
REGIMES=[]
for split,families in [('train',X.TRAIN),('validation',X.VALIDATION),('holdout',X.HOLDOUT)]:
    for f in families:REGIMES.append((split,f,'base',(f,)))
    if split!='holdout':
        for f in families:REGIMES.append((split,f+'_similar','renamed',(f,)))
    mixtures={'train':[('uniform3','xor_mixed'),('community','color3')],'validation':[],'holdout':[('widthmix','circuit')]}[split]
    for a,b in mixtures:REGIMES.append((split,a+'_mix_'+b,'mix',(a,b)))
assert Counter(r[0] for r in REGIMES)=={'train':18,'validation':6,'holdout':6}

def rows_manifest(n,namespace):
    return [dict(id=k*n+i,split=s,regime=name,kind=kind,parents=parents,index=i,namespace=namespace)
            for k,(s,name,kind,parents) in enumerate(REGIMES) for i in range(n)]

def make_case(meta):
    namespace=meta['namespace']+':'+meta['regime']
    a=X.make_case(meta['parents'][0],meta['index'],namespace)
    clauses=[list(c) for c in a['clauses']];n=a['n']
    if meta['kind']=='mix':
        b=X.make_case(meta['parents'][1],meta['index'],namespace+':second')
        clauses += [[(abs(v)+n)*(1 if v>0 else -1) for v in c] for c in b['clauses']];n+=b['n']
    if meta['kind']=='renamed':
        rng=random.Random(meta['id']+47130000);perm=list(range(1,n+1));rng.shuffle(perm)
        signs=[rng.choice((-1,1)) for _ in range(n)]
        clauses=[[perm[abs(v)-1]*signs[abs(v)-1]*(1 if v>0 else -1) for v in c] for c in clauses];rng.shuffle(clauses)
    source=f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    return dict(n=n,clauses=clauses,source=source,sha256=hashlib.sha256(source.encode()).hexdigest(),family=meta['regime'],index=meta['index'])

def emit(tag,data):X.emit('X47LONG_'+tag,data)
def save(path,data):X.save(path,data)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def collect(args):
    args.out.mkdir(parents=True,exist_ok=False);X.WORK_LIMIT=WORK;binary=args.binary.resolve();cnf=args.out/'current.cnf'
    manifest=rows_manifest(args.per_regime,args.namespace)
    mine=[r for r in manifest if r['split']!='holdout' and r['id']%args.shards==args.shard]
    with (args.out/'pairs.jsonl').open('w') as fd:
        for i,meta in enumerate(mine):
            c=make_case(meta);cnf.write_text(c['source']);r=X.pair(binary,cnf,c);r['meta']=meta
            fd.write(json.dumps(r,sort_keys=True)+'\n');fd.flush()
            if (i+1)%100==0:emit('COLLECT',dict(shard=args.shard,done=i+1,total=len(mine)))
    cnf.unlink();save(args.out/'manifest.json',dict(protocol=PROTOCOL,namespace=args.namespace,per_regime=args.per_regime,shard=args.shard,shards=args.shards,count=len(mine),native_sha=sha('src/drnas_x47.cpp'),work_limit=WORK,pairs_sha=sha(args.out/'pairs.jsonl')))

def open_memory(path):
    db=sqlite3.connect(path)
    db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiences(sha TEXT PRIMARY KEY,protocol TEXT,split TEXT,regime TEXT,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS checkpoints(id INTEGER PRIMARY KEY AUTOINCREMENT,cycle INTEGER,model TEXT,tune_cost INTEGER,accepted INTEGER);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sealed_tests(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL);''')
    return db

def publish(args,db,model,stage):
    db.commit()
    with gzip.open(args.out/'memory.sqlite.gz','wb') as fd:fd.write((args.out/'memory.sqlite').read_bytes())
    store=os.environ.get('X47_MEMORY_STORE')
    if not store:return
    root=Path(store).resolve();dest=root/'research/memory/x47';dest.mkdir(parents=True,exist_ok=True)
    (dest/'memory.sqlite.gz').write_bytes((args.out/'memory.sqlite.gz').read_bytes())
    save(dest/'latest.json',dict(protocol=PROTOCOL,namespace=args.namespace,stage=stage,model=model,native_sha=sha('src/drnas_x47.cpp'),source_commit=os.environ.get('GITHUB_SHA'),run=os.environ.get('GITHUB_RUN_ID')))
    def git(*a,check=True):return subprocess.run(['git','-C',str(root),*a],check=check,capture_output=True,text=True)
    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','research/memory/x47')
    if git('diff','--cached','--quiet',check=False).returncode:
        git('commit','-m',f'checkpoint(x47long): {stage}')
        result=git('push','origin',f'HEAD:{DATA_BRANCH}',check=False)
        if result.returncode:raise RuntimeError('Persistent memory push failed; local checkpoint retained: '+result.stderr[-400:])
    emit('MEMORY_SAVED',dict(stage=stage,branch=DATA_BRANCH))

def train(args):
    args.out.mkdir(parents=True,exist_ok=False)
    store=os.environ.get('X47_MEMORY_STORE');restored=False
    if store:
        prior=Path(store)/'research/memory/x47/memory.sqlite.gz'
        if prior.exists():(args.out/'memory.sqlite').write_bytes(gzip.decompress(prior.read_bytes()));restored=True
    db=open_memory(args.out/'memory.sqlite');key=PROTOCOL+':'+args.namespace+':'+str(args.per_regime)
    binding=PROTOCOL+':'+sha('src/drnas_x47.cpp')
    old=db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
    if old and old[0]!=binding:raise RuntimeError('Existing memory protocol differs; preserve it and start a separate memory branch')
    for sealed, in db.execute('SELECT payload FROM sealed_tests'):
        if json.loads(sealed).get('namespace')==args.namespace:
            raise RuntimeError('This namespace has an opened holdout. Use a fresh namespace for further training.')
    db.execute("INSERT OR IGNORE INTO meta VALUES ('binding',?)",(binding,))
    rows=[];seen=set()
    for p in sorted(args.inputs.glob('collect-*/pairs.jsonl')):
        manifest=json.loads((p.parent/'manifest.json').read_text())
        assert manifest['protocol']==PROTOCOL and manifest['native_sha']==sha('src/drnas_x47.cpp') and manifest['work_limit']==WORK
        assert manifest['pairs_sha']==sha(p)
        for line in p.read_text().splitlines():
            r=json.loads(line);meta=r['meta']
            assert meta['namespace']==args.namespace and meta['split']!='holdout'
            assert meta['id'] not in seen;seen.add(meta['id']);rows.append(r)
            prior=db.execute('SELECT split FROM experiences WHERE sha=?',(r['sha256'],)).fetchone()
            if prior and prior[0]!=meta['split']:raise RuntimeError('Cross-split memory contamination')
            db.execute('INSERT OR IGNORE INTO experiences VALUES (?,?,?,?,?)',(r['sha256'],key,meta['split'],meta['regime'],line))
    expected={r['id'] for r in rows_manifest(args.per_regime,args.namespace) if r['split']!='holdout'}
    assert seen==expected and len({r['sha256'] for r in rows})==len(rows)
    rows.sort(key=lambda r:r['meta']['id'])
    # Replay only prior TRAIN evidence. Past validation and sealed tests never enter fitting.
    train=[json.loads(p) for p, in db.execute("SELECT payload FROM experiences WHERE split='train' ORDER BY sha")]
    tune=[r for r in rows if r['meta']['split']=='validation' and r['meta']['index']%2==0]
    audit=[r for r in rows if r['meta']['split']=='validation' and r['meta']['index']%2==1]
    groups=defaultdict(list)
    for r in train:groups[r['meta']['regime']].append(r)
    for rr in groups.values():rr.sort(key=lambda r:(r['base']['work_cost']+r['flip']['work_cost'],r['sha256']))
    previous=None;best=None;active=set(range(24));cycles=[]
    if restored:
        row=db.execute('SELECT model FROM checkpoints WHERE accepted=1 ORDER BY id DESC LIMIT 1').fetchone()
        if row:previous=json.loads(row[0]);best=M.calibrate(previous,tune)
    save(args.out/'protocol.json',dict(protocol=PROTOCOL,key=key,native_sha=sha('src/drnas_x47.cpp'),total_sources=30*args.per_regime,train=18*args.per_regime,validation=6*args.per_regime,holdout=6*args.per_regime,cycles=args.cycles,regimes=REGIMES,work_limit=WORK,timing_target_ms=[10,80],runtime_cap_s=args.cap,restored=restored,holdout_never_read_by_training=True))
    for cycle in range(1,args.cycles+1):
        fraction=min(1.,cycle/6);rr=[r for group in groups.values() for r in group[:max(1,int(len(group)*fraction))]]
        if cycle%4==0:active=set(range(24)) # Reconsider previously unused features, without erasing their history.
        candidate=M.grow(previous,rr,active,add_trees=16 if previous is None else 8)
        candidate=M.calibrate(candidate,tune)
        candidate,retired,used=M.prune(candidate,tune,cycle%2==0)
        candidate=M.calibrate(candidate,tune)
        if cycle%2==0 and used:active=used
        accepted=best is None or candidate['tune_cost']<best['tune_cost']
        if accepted:best=copy.deepcopy(candidate)
        previous=candidate
        item=dict(cycle=cycle,training_sources=len(rr),labeled=candidate['training_pairs'],trees=len(candidate['weights']),active_features=sorted(active),retired_trees=retired,accepted=accepted,tune_cost=candidate['tune_cost'],best_tune_cost=best['tune_cost'])
        cycles.append(item);db.execute('INSERT INTO checkpoints(cycle,model,tune_cost,accepted) VALUES (?,?,?,?)',(cycle,json.dumps(candidate),candidate['tune_cost'],int(accepted)))
        db.execute('INSERT INTO events(payload) VALUES (?)',(json.dumps(item),));db.commit();save(args.out/f'cycle_{cycle:02}.json',item);emit('CYCLE',item)
        if cycle%2==0:publish(args,db,best,f'cycle-{cycle}')
    # Audit partition opened only after model/threshold selection. Never feeds updates.
    audit_cost=M.cost(best,audit);core_audit=sum(r['base']['work_cost'] for r in audit)
    best['audit_work_cost']=audit_cost;best['core_audit_work_cost']=core_audit
    best['deployment_allowed']=audit_cost<core_audit
    save(args.out/'frozen_model.json',best);write_model(args.out/'frozen_model.txt',best)
    baseline_train=sum(r['base']['work_cost'] for r in tune)
    summary=dict(status='FROZEN',namespace=args.namespace,cycles=cycles,model_sha=sha(args.out/'frozen_model.txt'),training_unique_sources=len(train),tune_sources=len(tune),audit_sources=len(audit),core_tune=baseline_train,audit_cost=audit_cost,core_audit=core_audit,deployment_allowed=best['deployment_allowed'],training_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in train)),restored=restored)
    save(args.out/'training_report.json',summary);publish(args,db,best,'frozen-before-holdout');db.close();emit('FROZEN',summary)

def evaluate(args):
    args.out.mkdir(parents=True,exist_ok=False);X.WORK_LIMIT=WORK;binary=args.binary.resolve();cnf=args.out/'current.cnf'
    model_path=args.models/'frozen_model.txt';model=json.loads((args.models/'frozen_model.json').read_text());frozen_sha=sha(model_path)
    old=Path('research/data/x47_original_tree.txt').resolve()
    mine=[r for r in rows_manifest(args.per_regime,args.namespace) if r['split']=='holdout' and r['id']%args.shards==args.shard]
    with (args.out/'trials.jsonl').open('w') as tf,(args.out/'pairs.jsonl').open('w') as pf:
        for i,meta in enumerate(mine):
            c=make_case(meta);cnf.write_text(c['source']);p=X.pair(binary,cnf,c);p['meta']=meta;pf.write(json.dumps(p,sort_keys=True)+'\n');pf.flush()
            for repeat in range(args.repeats):
                order=['core','original','long','fixed','sham'];random.Random(meta['id']*17+repeat).shuffle(order);arms={}
                for arm in order:
                    policy='tree' if arm in ('original','long') else arm
                    mp=old if arm=='original' else model_path if arm in ('long','sham') else None
                    arms[arm]=X.run(binary,cnf,c,policy,args.cap,model=mp)
                for arm in ('long','sham'):
                    a=arms[arm]
                    if a['reached']:
                        score,_=X.predict(model,a['policy']['features']);assert abs(score-a['policy']['score'])<1e-7
                if arms['core']['within_cap'] and arms['sham']['within_cap']:
                    assert all(arms['core'][k]==arms['sham'][k] for k in ('propagations','decisions','conflicts'))
                tf.write(json.dumps(dict(sha256=c['sha256'],meta=meta,repeat=repeat,arms=arms),sort_keys=True)+'\n');tf.flush()
            if (i+1)%100==0:emit('HOLDOUT',dict(shard=args.shard,done=i+1,total=len(mine)))
    assert sha(model_path)==frozen_sha;cnf.unlink();save(args.out/'manifest.json',dict(model_sha=frozen_sha,count=len(mine),repeats=args.repeats,shard=args.shard,trials_sha=sha(args.out/'trials.jsonl'),pairs_sha=sha(args.out/'pairs.jsonl')))

def auc(y,s):
    y=np.asarray(y,bool);s=np.asarray(s,float);positive=int(y.sum());negative=len(y)-positive
    if not positive or not negative:return None
    order=np.argsort(s,kind='stable');ss=s[order];yy=y[order]
    starts=np.r_[0,np.flatnonzero(ss[1:]!=ss[:-1])+1];ends=np.r_[starts[1:],len(ss)]
    ranks=(starts+ends+1)/2
    rank_sum=float(np.dot(np.add.reduceat(yy.astype(float),starts),ranks))
    return (rank_sum-positive*(positive+1)/2)/(positive*negative)

def discrimination(model,rows):
    rr=[r for r in rows if r['label'] is not None and abs(r['label'])>.1]
    y=np.array([r['label']>0 for r in rr],dtype=bool);s=np.array([X.predict(model,r['features'])[0] for r in rr])
    pred=M.decisions(model,rr);bs=[];rng=np.random.default_rng(X.SEED)
    for _ in range(3000 if len(y) else 0):
        ii=rng.integers(len(y),size=len(y));value=auc(y[ii],s[ii])
        if value is not None:bs.append(value)
    return dict(n=len(rr),auc=auc(y,s),auc_formula95=np.quantile(bs,[.025,.975]).tolist() if bs else None,
        balanced_accuracy=float((pred[y].mean()+(~pred[~y]).mean())/2) if y.any() and (~y).any() else None,
        accepted_flips=int(pred.sum()),conditional_on_completed_nontrivial_pairs=True)

def finish(args):
    args.out.mkdir(parents=True,exist_ok=False);rows=[];pairs=[];expected_sha=sha(args.models/'frozen_model.txt')
    for folder in sorted(args.inputs.glob('eval-*')):
        m=json.loads((folder/'manifest.json').read_text());assert m['model_sha']==expected_sha
        assert m['trials_sha']==sha(folder/'trials.jsonl') and m['pairs_sha']==sha(folder/'pairs.jsonl')
        rows.extend(json.loads(x) for x in (folder/'trials.jsonl').read_text().splitlines())
        pairs.extend(json.loads(x) for x in (folder/'pairs.jsonl').read_text().splitlines())
    expected={r['id'] for r in rows_manifest(args.per_regime,args.namespace) if r['split']=='holdout'}
    assert len(pairs)==len(expected) and {r['meta']['id'] for r in pairs}==expected
    groups=defaultdict(list)
    for r in rows:groups[r['sha256']].append(r)
    assert len(groups)==len(expected) and all(len(v)==args.repeats and {r['repeat'] for r in v}==set(range(args.repeats)) for v in groups.values())
    arms=['core','original','long','fixed','sham'];means={a:[np.mean([r['arms'][a]['PAR2'] for r in rr]) for rr in groups.values()] for a in arms}
    totals={a:dict(PAR2_s=sum(r['arms'][a]['PAR2'] for r in rows),verified=sum(r['arms'][a]['within_cap'] for r in rows),trials=len(rows),median_ms=float(np.median([r['arms'][a]['wall_s'] for r in rows])*1000),p95_ms=float(np.quantile([r['arms'][a]['wall_s'] for r in rows],.95)*1000)) for a in arms}
    comps={a:X.effect(means[a],means['long']) for a in ('core','original','fixed','sham')}
    model=json.loads((args.models/'frozen_model.json').read_text())
    fam={f:{a:sum(r['arms'][a]['PAR2'] for r in rows if r['meta']['regime']==f) for a in arms} for f in sorted(set(r['meta']['regime'] for r in rows))}
    prediction=discrimination(model,pairs)
    performance_pass=comps['core']['paired_formula_bootstrap95_pct'][0]>10 and comps['original']['paired_formula_bootstrap95_pct'][0]>10
    learning_pass=bool(performance_pass and comps['fixed']['paired_formula_bootstrap95_pct'][0]>0 and prediction['auc_formula95'] and prediction['auc_formula95'][0]>.5 and model['deployment_allowed'])
    report=dict(status='COMPLETE',namespace=args.namespace,sources=30*args.per_regime,holdout=len(groups),repeats=args.repeats,arms=totals,long_vs=comps,prediction=prediction,families=fam,
        performance_success=performance_pass,learning_success=learning_pass,
        family_uncertainty=X.effect([v['core'] for v in fam.values()],[v['long'] for v in fam.values()]),
        limits=['30 generator regimes, not 30 independent mathematical classes; all performance formulas constructed SAT.',
                'Same native X4.7 solver; training, memory and dataset changed. Duration is measured, not guaranteed to be tens of ms.',
                'Repeated tuning uses tune partition; audit opened once after selection; holdout opened only after freeze.',
                'Prediction excludes work-censored pairs; PAR2 includes every holdout source and overhead.',
                'Retired trees/features are removed only from active models; raw verified evidence and checkpoints retained.',
                'Secondary and family comparisons exploratory; only six holdout regimes; no industrial or external solver claim.'])
    save(args.out/'report.json',report)
    (args.out/'memory.sqlite').write_bytes((args.models/'memory.sqlite').read_bytes());db=open_memory(args.out/'memory.sqlite')
    db.execute('INSERT INTO sealed_tests(payload) VALUES (?)',(json.dumps(report),));publish(args,db,model,'completed-holdout-sealed');db.close();emit('FINAL',report)

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['collect','train','evaluate','finish'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--inputs',type=Path,default=Path('inputs'));p.add_argument('--models',type=Path,default=Path('models'))
    p.add_argument('--binary',type=Path,default=Path('build/drnas-x47'));p.add_argument('--per-regime',type=int,default=1000);p.add_argument('--namespace',default=PROTOCOL)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=8);p.add_argument('--cycles',type=int,default=12);p.add_argument('--repeats',type=int,default=3);p.add_argument('--cap',type=float,default=.08)
    a=p.parse_args()
    if a.per_regime<2 or not 0<=a.shard<a.shards or a.cycles<2 or a.repeats<2:raise ValueError('invalid protocol')
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    globals()[a.command](a)

if __name__=='__main__':main()

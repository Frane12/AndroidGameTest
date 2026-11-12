#!/usr/bin/env python3
"""Small disjoint train/holdout audit of memory transfer, including its overhead."""
import argparse,collections,hashlib,json,os,pathlib,random,statistics,time
from drnas_r28_context_memory import Memory,solve,SCHEMA,file_sha
ROOT=pathlib.Path('r28_context_results')
def emit(tag,data):print(tag,json.dumps(data,sort_keys=True),flush=True)
def cases(kind,generation,count):
    root=ROOT/'cases'/kind;root.mkdir(parents=True,exist_ok=True);out=[]
    for i in range(count):
        label=f'R153CTX1/{kind}/{generation}/{i}';rng=random.Random(label)
        n=(120,180,220,260)[i%4];density=(4,5,6)[(i//4)%3];planted=[rng.getrandbits(1) for _ in range(n)];clauses=[]
        for _ in range(n*density):
            vs=rng.sample(range(1,n+1),3);cl=[v if rng.getrandbits(1) else -v for v in vs]
            if not any(planted[abs(v)-1]==(v>0) for v in cl):cl[0]=-cl[0]
            clauses.append(cl)
        if i%6==0:
            # Sparse binary structure changes the context without losing the planted model.
            for _ in range(n*6):
                vs=rng.sample(range(1,n+1),2);cl=[v if planted[v-1] else -v for v in vs];clauses.append(cl)
        p=root/f'{i:03d}.cnf';p.write_text(f'c {label}\np cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses));out.append(p)
    # Algebraic controls must still take the R153 exact route without fictitious learning samples.
    for unsat in (False,True):
        cs=[]
        for i in range(1,96):cs.extend([[i,-i-1],[-i,i+1]])
        cs.append([1])
        if unsat:cs.append([-96])
        # Distinct variable rename per split and generation, not merely different CNF comments.
        perm=list(range(1,97));random.Random(f'xor/{kind}/{generation}/{unsat}').shuffle(perm)
        cs=[[perm[abs(v)-1]*(1 if v>0 else -1) for v in c] for c in cs]
        p=root/f'xor-{unsat}.cnf';p.write_text('p cnf 96 '+str(len(cs))+'\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs));out.append(p)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--db',default='drnas_memory/memory.sqlite');ap.add_argument('--train',type=int,default=32);ap.add_argument('--holdout',type=int,default=16);ap.add_argument('--cap',type=float,default=1.);a=ap.parse_args()
    ROOT.mkdir(exist_ok=True);cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    memory=Memory(a.db);initial=memory.info();generation=memory.generation()
    train=cases('train',generation,a.train);heldout=cases('holdout',0,a.holdout)
    train_sha={file_sha(p) for p in train};eval_sha={file_sha(p) for p in heldout};assert not train_sha&eval_sha
    for sha in eval_sha:memory.register(sha,'eval')
    emit('R153_CONTEXT_PLAN',dict(single_cpu=cpu,generation=generation,restored=initial,train=len(train),holdout=len(heldout),reps=2,cap_s=a.cap,synthetic=True,algebra_base='R153 exact GF2 + R160-style abstention to native'))
    rows=[]
    with (ROOT/'results.jsonl').open('w') as f:
        def append(row):rows.append(row);f.write(json.dumps(row)+'\n');f.flush();emit('R153_CONTEXT_TRIAL',row)
        for i,p in enumerate(train):
            r,_=solve(memory,p,'train',a.cap,17,True,build=os.getenv('GITHUB_SHA','local'));r.update(id=p.name,arm='TRAIN');append(r)
        memory.advance();frozen=memory.digest();trained=memory.info();emit('R153_CONTEXT_TRAINED',trained)
        arms=['R153_NATIVE_DIRECT','CONTEXT_COLD','CONTEXT_WARM']
        for i,p in enumerate(heldout):
            for rep in range(2):
                order=list(arms);random.Random(f'{i}/{rep}').shuffle(order)
                for arm in order:
                    binary='mre_r28_native/drnas_r28_native' if arm=='R153_NATIVE_DIRECT' else 'mre_r28_context/drnas_r28_context'
                    r,_=solve(memory,p,'eval',a.cap,17+12*rep,arm=='CONTEXT_WARM',binary=binary);r.update(id=p.name,arm=arm,rep=rep);append(r)
        assert memory.digest()==frozen,'evaluation changed training statistics'
    totals={}
    for arm in arms:
        rs=[r for r in rows if r['arm']==arm];totals[arm]=dict(trials=len(rs),verified=sum(r['verified'] for r in rs),reported_solved=sum(r['reported_solved'] for r in rs),PAR2_verified_s=sum(r['PAR2_verified_s'] for r in rs),PAR2_reported_s=sum(r['PAR2_reported_s'] for r in rs),e2e_s=sum(r['e2e_s'] for r in rs),mean_prepare_ms=1000*statistics.mean(r['prepare_s'] for r in rs))
    warm=totals['CONTEXT_WARM'];ratios={arm:totals[arm]['PAR2_verified_s']/warm['PAR2_verified_s'] for arm in arms if arm!='CONTEXT_WARM'}
    # An actual process/database restart must preserve the same knowledge.
    memory.close();reopened=Memory(a.db);assert reopened.digest()==frozen;final=reopened.info();reopened.close()
    result=dict(complete=True,initial_memory=initial,final_memory=final,train_sources=len(train),holdout_sources=len(heldout),synthetic_only=True,holdout_frozen=True,restart_persistence=True,totals=totals,speedup_vs=ratios,promotion=False,reason='Small synthetic diagnostic; general unseen >=30% gain not established')
    (ROOT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    artifact=pathlib.Path(a.db).parent
    manifest=dict(schema=SCHEMA,database_sha256=file_sha(a.db),stats_sha256=frozen,generation=final['generation'],build=os.getenv('GITHUB_SHA','local'),run_id=os.getenv('GITHUB_RUN_ID','local'),info=final)
    (artifact/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    emit('R153_CONTEXT_FINAL',result)
if __name__=='__main__':main()

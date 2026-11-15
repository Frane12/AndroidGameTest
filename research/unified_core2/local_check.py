import concurrent.futures, hashlib, importlib.util, json, multiprocessing, os, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/core2-local-result'
OUT.mkdir(exist_ok=True)
IDS=[0,3,23,25,31,43,44,55]
ARMS=['CORE1','CORE2','Kissat','CaDiCaL','CryptoMiniSat']
def load():
 spec=importlib.util.spec_from_file_location('bench',ROOT/'research/unified_core2/benchmark.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 return mod
def init(q):
 cpu=q.get();os.sched_setaffinity(0,{cpu})
def work(i):
 b=load(); b.affinity()
 src=next(s for s in b.frozen_sources()['sources'] if s['id']==i)
 rows=[]
 with (OUT/f'{i}.jsonl').open('w') as f:
  for rep in range(2):
   arms=ARMS.copy();random.Random(f'core2-local:{i}:{rep}').shuffle(arms)
   for arm in arms:
    r=b.trial(src,arm,rep); rows.append(r);f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
    print('LOCAL',i,rep,arm,r['status'],r['e2e_s'],flush=True)
 return rows
if __name__=='__main__':
 b=load(); cpus=sorted(os.sched_getaffinity(0))[:4]
 if len(cpus)<4: raise SystemExit('Not enough independent CPUs')
 meta={'kind':'retrospective_development_sample_not_holdout','ids':IDS,'arms':ARMS,'repetitions':2,'timeout_s':b.CAP,'pinned_cpus':cpus,'binary_sha256':b.pinned(),'source_manifest_sha256':b.sha(b.DATA/'manifest.json'),'seed':'core2-local:id:rep','selected_because':'known solved cases and four additional mixed original-source controls'}
 (OUT/'protocol.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
 q=multiprocessing.Queue()
 for cpu in cpus:q.put(cpu)
 rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=4,initializer=init,initargs=(q,)) as ex:
  for x in ex.map(work,IDS):rows.extend(x)
 totals={}
 for a in ARMS:
  vals=[r for r in rows if r['arm']==a]
  totals[a]={'trials':len(vals),'solved':sum(r['accepted'] for r in vals),'PAR2_s':round(sum(r['PAR2_s'] for r in vals),4),'strict_PAR2_s':round(sum(r['PAR2_strict_s'] for r in vals),4),'critical':sum(r['critical'] for r in vals)}
 result={'trials':len(rows),'totals':totals,'critical':[r for r in rows if r['critical']]}
 (OUT/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print('LOCAL_FINAL',json.dumps(result,sort_keys=True),flush=True)

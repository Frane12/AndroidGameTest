#!/usr/bin/env python3
"""Frozen selector validation on unused original SC2023 competition instances."""
import argparse,csv,hashlib,io,json,math,os,random,re,resource,statistics,sys,types,zipfile
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/drnas-sat-v7-8'))
sys.path.insert(0,str(ROOT/'research/tseitin-replay'))
from official_shortlong_select import download_and_features
from jerk_r8_holdout import replace_once
from jerk_r9_analysis import paired_stats
MODES=('monitor','stable_v1531','selector','kissat_original')
CAP=15;REPEATS=3;COUNT=12
SALT='DRNAS-fresh-SC2023-selector-frozen-v1'
def sha(data):return hashlib.sha256(data).hexdigest()
def parse(path):
 n=None;clauses=[];pending=[]
 for line in path.read_text().splitlines():
  if not line.strip() or line.lstrip().startswith(('c','%')):continue
  if line.startswith('p '):n=int(line.split()[2]);continue
  for word in line.split():
   lit=int(word)
   if lit:pending.append(lit)
   else:clauses.append(pending);pending=[]
 assert n and not pending
 return n,clauses

def freeze(a):
 a.out.mkdir(parents=True,exist_ok=True)
 reg=a.registry.read_text();seen_ids=set(re.findall(r'\b[0-9a-f]{32}\b',reg));seen_sha=set(re.findall(r'\b[0-9a-f]{64}\b',reg))
 for y in (2024,2025,2026):seen_ids.update(re.findall(r'\b[0-9a-f]{32}\b',(a.sources/f'exclude{y}.txt').read_text()))
 z=zipfile.ZipFile(a.sources/'sc23.zip')
 meta={r['hash']:r for r in csv.DictReader(io.StringIO(z.read('bench_meta.csv').decode()))}
 rows=list(csv.DictReader(io.StringIO(z.read('results_main_detailed.csv').decode())))
 rows=[r for r in rows if r['hash'] not in seen_ids and r['vresult'] in ('sat','unsat') and .5<=float(r['kissat-3.1.0'])<=180]
 rows.sort(key=lambda r:(abs(math.log(float(r['kissat-3.1.0'])/5)),sha((SALT+r['hash']).encode())))
 cases=[];attempts=[];families=Counter();labels=Counter()
 for r in rows:
  label=r['vresult'].upper();fam=meta[r['hash']]['family']
  if labels[label]>=6 or families[fam]>=2:continue
  p=a.out/(r['hash']+'.cnf')
  try:
   info=download_and_features(r['hash'],p);n,clauses=parse(p)
   canonical=sha((f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode())
   if info['sha256'] in seen_sha or canonical in seen_sha:raise ValueError('previously recorded hash')
   case={**info,'formula':r['hash']+'.cnf','canonical_sha256':canonical,'family':fam,'filename':meta[r['hash']]['filename'],'expected':label,'reference_kissat_2023_seconds':float(r['kissat-3.1.0'])}
   cases.append(case);labels[label]+=1;families[fam]+=1;attempts.append({'id':r['hash'],'accepted':True})
   print('ACCEPT',case['id'],fam,label,info['cnf_bytes'],flush=True)
  except Exception as e:
   p.unlink(missing_ok=True);attempts.append({'id':r['hash'],'accepted':False,'reason':str(e)});print('REJECT',r['hash'],str(e),flush=True)
  if len(cases)==COUNT:break
 assert len(cases)==COUNT and labels=={'SAT':6,'UNSAT':6},dict(labels)
 cases.sort(key=lambda c:sha((SALT+'/schedule/'+c['id']).encode()))
 manifest={'name':SALT,'cases':cases,'attempts':attempts,'excluded_ids':sorted(seen_ids),'registry_sha256':sha(a.registry.read_bytes()),'source_hashes':{p.name:sha(p.read_bytes()) for p in a.sources.iterdir() if p.is_file()},'model_threshold':3.2039999961853027,'selector_source_sha256':sha((ROOT/'research/learned-selector/selector.cpp').read_bytes()),'selection':'official Kissat 3.1.0 reference difficulty near 5 seconds, family quota <=2, six SAT and six UNSAT, bounded original files; no new DRNAS timings used','scope':'project-new IDs and hashes; original SC2023 formulas absent from entire SC2024 metadata and SC2025/2026 main URI lists and pinned cumulative registry','cap_seconds':CAP,'repeats':REPEATS,'validation':'official labels and SAT models where emitted; independent Kissat UNSAT proofs not collected'}
 (a.out/'frozen_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

def run(a):
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
 manifest=json.loads((a.inputs/'frozen_manifest.json').read_text());src=a.runner.read_text()
 old='    else:\n        env["DRNAS_V177_MODE"]={'
 new='''    elif mode=="selector":
        env["DRNAS_V177_MODE"]="r5_monitor"
        command=["/tmp/drnas-selector",str(PATCHED),str(STABLE),str(ORIGINAL),str(case["path"].resolve())]
    elif mode=="kissat_original":
        command=[str(ORIGINAL),"-s",str(case["path"].resolve())]
    else:
        env["DRNAS_V177_MODE"]={'''
 src=replace_once(src,old,new)
 src=replace_once(src,'"R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL"','"R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL","DRNAS_SELECTOR"')
 src=replace_once(src,'repeat=rep,mode=mode,points=traces,early=early,gate=gate,','repeat=rep,mode=mode,points=traces,early=early,gate=gate,selection=labels.get("DRNAS_SELECTOR",{}),')
 r=types.ModuleType('frozen_real_runner');r.__file__=str(a.runner);exec(compile(src,str(a.runner),'exec'),r.__dict__)
 r.CAP=CAP;r.ORIGINAL=Path('/tmp/kissat-r9-original/build/kissat');r.PATCHED=Path('/tmp/kissat-r9-patched/build/kissat');r.STABLE=Path('/tmp/drnas-r9-v1531')
 a.out.mkdir(parents=True,exist_ok=True);rows=[];traces=[]
 cases=manifest['cases'][a.shard*2:a.shard*2+2];assert len(cases)==2
 for c in cases:
  p=a.inputs/c['formula'];assert sha(p.read_bytes())==c['sha256'];n,clauses=parse(p)
  case={**c,'path':p,'n':n,'clauses':clauses,'formula_sha256':c['sha256'],'category':c['family'],'dataset_type':'original_SC2023','source':c['source_url'],'source_revision':'e9b22ad1417d58e8c687a75ab897dc067a57d59a','metadata':{}}
  for rep in range(REPEATS):
   modes=list(MODES);random.Random(SALT+c['id']+str(rep)).shuffle(modes)
   for mode in modes:
    row,trace=r.run_one(case,rep,mode,'SC2023 paired worker '+str(a.shard))
    if mode=='selector':
     expected='stable_v1531' if len(clauses)/n<=3.2039999961853027 else 'monitor'
     assert trace['selection'].get('route')==expected,'wrong selector route'
     row['route']=expected
    if mode=='kissat_original':row['route']='kissat_original'
    rows.append(row);traces.append(trace);r.write_csv(a.out/'measurements.csv',rows)
    (a.out/'traces.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in traces))
    print('REAL',c['id'],c['family'],rep,mode,row['status'],row['wall_s'],row['route'],row['error'],flush=True)
    if row['error']:raise RuntimeError(row['error'])
 (a.out/'manifest.json').write_text(json.dumps({'cases':cases,'cpu_affinity':list(os.sched_getaffinity(0)),'memory_limit':3*1024**3,'source_commit':os.getenv('GITHUB_SHA'),'executables':{str(p):sha(p.read_bytes()) for p in (r.ORIGINAL,r.PATCHED,r.STABLE,Path('/tmp/drnas-selector'))}},indent=2)+'\n')
 assert len(rows)==24

def analyze(a):
 rows=[];case_ids=set();manifests=[]
 for shard in range(6):
  folder=a.inputs/f'real-shard-{shard}';rs=list(csv.DictReader((folder/'measurements.csv').open()));m=json.loads((folder/'manifest.json').read_text());assert len(rs)==24 and len(m['cases'])==2;rows+=rs;manifests.append(m)
  for c in m['cases']:assert c['id'] not in case_ids;case_ids.add(c['id'])
 assert len(rows)==144 and len(case_ids)==12
 assert not any(r['error'] for r in rows)
 assert len({(r['formula'],r['mode'],r['repeat']) for r in rows})==144
 summary={}
 for mode in MODES:
  rs=[r for r in rows if r['mode']==mode];solved=[r for r in rs if r['status'] in ('SAT','UNSAT')]
  summary[mode]={'attempts':len(rs),'solved':len(solved),'timeouts':sum(r['status']=='TIMEOUT' for r in rs),'wall_sum':sum(float(r['wall_s']) for r in rs),'par2_sum':sum(float(r['par2_s']) for r in rs),'min_solved_seconds':min([float(r['wall_s']) for r in solved],default=None),'max_solved_seconds':max([float(r['wall_s']) for r in solved],default=None),'sat_models_checked':sum(r['sat_model_checked']=='True' for r in rs),'native_unsat_certificates_checked':sum(r['native_unsat_certificate_checked']=='True' for r in rs)}
 effects=defaultdict(list);pairs=[]
 for name in sorted({r['formula'] for r in rows}):
  rs=[r for r in rows if r['formula']==name];assert len(rs)==12
  med={m:statistics.median(float(r['par2_s']) for r in rs if r['mode']==m) for m in MODES}
  row={'formula':name,'family':rs[0]['category'],'expected':rs[0]['expected'],**med}
  for base in ('monitor','stable_v1531','kissat_original'):
   gain=100*(med[base]-med['selector'])/med[base];effects[base].append(gain);row['gain_pct_vs_'+base]=gain
  pairs.append(row)
 a.out.mkdir(parents=True,exist_ok=True)
 report={'name':SALT,'formulas':12,'attempts':144,'cap_seconds':CAP,'repeats':REPEATS,'summary':summary,'effects':{b:paired_stats(v,20261103+i) for i,(b,v) in enumerate(effects.items())},'formula_medians':pairs,'note':'original official SC2023, known official labels; difficulty- and file-size-selected; no independent Kissat UNSAT proof verification'}
 (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 for filename,rs in [('measurements.csv',rows),('formula_effects.csv',pairs)]:
  with (a.out/filename).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
 print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','run','analyze']);p.add_argument('--sources',type=Path);p.add_argument('--registry',type=Path);p.add_argument('--inputs',type=Path);p.add_argument('--runner',type=Path);p.add_argument('--shard',type=int);p.add_argument('--out',type=Path,required=True);a=p.parse_args();globals()[a.stage](a)

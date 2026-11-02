#!/usr/bin/env python3
"""Append verified R16 native attempts to historical V15.3.1 SQLite; never modify solver."""
import argparse,csv,hashlib,json,math,sqlite3
from pathlib import Path
from collections import defaultdict
RUN='41426664482'
COMMIT='03257cd6dcf3a5e10a53c0360c57933db8b7bc08'
MODEL='d50df624a21ba51c50782d7ecfe592f18420bf833aea9c796646908e0a363b17'
PROTOCOL='f73fd7203c051f1fa47fa090d9cae5614438dffb200ad14754a160a8b685f14c'
HISTORY='a64ed0b644cd0ad3f34b38e0f43a37f77dd21af215b0672ba49e45c5b5338e45'
STABLE='9e2b04e2e32b7320bd89757486b93ad0d5bc0ef10c28bdd54dd98c4bb14fb89c'
KISSAT='8af8e56f174b778aef3aa45af9f739b2a5f492c2'
MODES=('monitor','r11_2048_50','r11_2048_25','r13_rescue50','r14_dual50','r16_live50','r16_live50_strict','r16_snapshot50','original_kissat','stable_v1531')
LIVE=('r16_live50','r16_live50_strict','r16_snapshot50')
SHARDS=[f'n{n}_{fold}{i}' for n in (200,220,240) for fold in ('development','test') for i in (0,1)]+[f'community_n{n}_{fold}0' for n in (220,240) for fold in ('development','test')]
def check(ok,why):
 if not ok:raise ValueError('R16 immutable ingest audit failed: '+why)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rowsha(r):return hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def readcsv(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def num(x):return float(x) if x not in ('',None) else None
def integer(x):return int(x) if x not in ('',None) else None
def flag(x):return 1 if str(x).lower() in ('true','1') else 0 if str(x).lower() in ('false','0') else None
def foldof(cat):return ('community3_' if cat.startswith('community_') else 'random3_')+('development' if '_development' in cat else 'test')
def export(p,rows):
 if rows:
  with p.open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser()
 for k in ('db','input','out'):p.add_argument('--'+k,type=Path,required=True)
 a=p.parse_args();root=a.input;out=a.out;out.mkdir(parents=True,exist_ok=True)
 rp=root/'aggregate/results.json';report=json.loads(rp.read_text())
 check(report['attempts']==4800 and report['formulas']==160 and report['repeats']==3 and report['preintervention_mismatches']==0,'aggregate completeness')
 check(report['r16_protocol_sha256']==PROTOCOL and report['prior_model_sha256']==MODEL and report['r16_history_sha256']==HISTORY,'model/protocol/history SHA')
 check('not replay' in report['status'].lower() and report['random3_test_is_primary'] is True,'real native evaluation')
 src={r['shard']:r for r in report['source_artifacts']};man={r['category']:r for r in report['manifests']}
 check(len(src)==len(man)==16 and set(src)==set(man)==set(SHARDS),'16 source shards')
 index={}
 for line in (root/'artifact_index.tsv').read_text().splitlines():
  name,aid,expired=line.split('\t')[:3]
  check(name not in index and expired=='false','duplicate/expired GitHub artifact '+name)
  index[name]=int(aid)
 check(len(index)==17 and 'DRNAS-R16-Verified-Native-Live-Model-Analysis' in index,'17 source artifacts')
 feats=readcsv(root/'aggregate/formula_features.csv');pairs=readcsv(root/'aggregate/paired.csv');decisions=readcsv(root/'aggregate/native_decisions.csv')
 fidx={(r['shard'],r['formula']):r for r in feats};pidx={(r['shard'],r['formula'],r['mode']):r for r in pairs}
 didx={(r['shard'],r['formula'],int(r['repeat']),r['mode']):r for r in decisions}
 check((len(feats),len(pairs),len(decisions),len(fidx),len(pidx),len(didx))==(160,1440,1440,160,1440,1440),'aggregate unique keys')
 db=sqlite3.connect(a.db)
 try:
  before={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('datasets','formulas','attempts')}
  check(before==dict(datasets=135,formulas=2019,attempts=31730),'historical baseline '+str(before))
  check(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','old SQLite integrity')
  prior={h for (h,) in db.execute('SELECT formula_sha256 FROM formulas') if h}
  db.execute('CREATE TABLE IF NOT EXISTS r16_formula_features(dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,fold TEXT,seed INTEGER,source_revision TEXT,metadata_json TEXT,aggregate_features_sha256 TEXT,PRIMARY KEY(dataset,case_name))')
  db.execute('CREATE TABLE IF NOT EXISTS r16_native_details(dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,cpu_seconds REAL,switch_at INTEGER,raw_row_sha256 TEXT,native_score REAL,python_score REAL,selected INTEGER,threshold REAL,model TEXT,protocol_sha256 TEXT,model_sha256 TEXT,PRIMARY KEY(dataset,case_name,solver,repeat))')
  seen=set();sources=[];pairout=[];decisionout=[];nrows=0;aggregate_sha=sha(rp)
  for cat in SHARDS:
   folder=root/'shards'/cat;s=src[cat];m=json.loads((folder/'manifest.json').read_text())
   rows=readcsv(folder/'measurements.csv')
   traces=[json.loads(x) for x in (folder/'traces.jsonl').read_text().splitlines() if x.strip()]
   artifact='r16-'+cat
   check(artifact in index,'missing raw artifact '+artifact)
   for filename,key in (('measurements.csv','sha256_measurements'),('manifest.json','sha256_manifest'),('traces.jsonl','sha256_traces')):
    check(sha(folder/filename)==s[key],'raw file checksum '+artifact+'/'+filename)
   check(m==man[cat] and m['source_commit']==s['source_commit']==COMMIT,'raw manifest/commit '+cat)
   check(m['runner']==s['runner'] and m['executables']==s['binary_sha256'],'runner/binary SHA '+cat)
   check(m['executables']['stable_v1531']==STABLE and m['kissat_pin']==KISSAT and m['stable_blob'],'frozen solver '+cat)
   check(m['r16_protocol_sha256']==PROTOCOL and m['r16_model_sha256']==s['model_sha256']==MODEL,'model pin '+cat)
   check(m['historical_registry_sha256']==HISTORY and m['repeats']==3 and m['cap_seconds']==12,'historical registry/protocol '+cat)
   check(tuple(m['modes'])==MODES and len(m['cases'])==10 and len(rows)==len(traces)==300,'raw shard matrix '+cat)
   fold=foldof(cat);family=fold.split('_')[0]
   check(m['fold']==fold and m['family']==family,'fold/family '+cat)
   cases={c['formula']:c for c in m['cases']};check(len(cases)==10,'case uniqueness '+cat)
   key=lambda r:(r['formula'],r['mode'],int(r['repeat']))
   expected={(name,mode,rep) for name in cases for mode in MODES for rep in range(3)}
   check(len({key(r) for r in rows})==300 and {key(r) for r in rows}==expected,'attempt matrix '+cat)
   check(len({key(t) for t in traces})==300 and {key(t) for t in traces}==expected,'trace matrix '+cat)
   tmap={key(t):t for t in traces};totals=defaultdict(float);statuses=defaultdict(set)
   for name,c in cases.items():
    h=c['formula_sha256']
    check((folder/name).is_file() and sha(folder/name)==h,'actual CNF SHA '+name)
    check(len(h)==64 and h not in prior and h not in seen,'duplicate SHA '+name)
    check(c['dataset_type']=='generated_prospective' and c['expected']=='UNKNOWN' and c['metadata']['fold'] in fold,'provenance '+name)
    check(c['metadata']['family']==family and c['metadata'].get('seed') is not None,'seed '+name)
    f=fidx[(cat,name)]
    check(f['formula_sha256']==h and f['fold']==fold and f['family']==family and int(f['seed'])==c['metadata']['seed'],'aggregate feature SHA/seed '+name)
    seen.add(h)
   for r in rows:
    name,mode,rep=key(r);c=cases[name];status=r['status'];tr=tmap[(name,mode,rep)]
    check(r['formula_sha256']==c['formula_sha256'] and r['seed']==str(c['metadata']['seed']) and r['runner']==m['runner'] and r['fold']==fold,'attempt lineage '+name)
    check(r['expected']=='UNKNOWN' and not r['error'] and status in ('SAT','UNSAT','TIMEOUT'),'result status '+name)
    check(r['r16_protocol_sha256']==PROTOCOL and r['r16_model_sha256']==MODEL and not r['r16_decision_error'],'R16 parity/error flag '+name)
    wall=float(r['wall_s']);par2=float(r['par2_s'])
    check(math.isfinite(wall) and wall>=0 and math.isfinite(par2) and abs(par2-(24 if status=='TIMEOUT' else wall))<.0011,'PAR-2 '+name)
    if status=='SAT':check(flag(r['sat_model_checked'])==1,'SAT witness '+name)
    if status!='TIMEOUT':statuses[name].add(status)
    check(len(tr['points'])==int(r['trace_points']) and key(tr)==key(r),'trace linkage '+name)
    if r['switch_at']:
     check(mode not in ('monitor','original_kissat','stable_v1531') and int(r['switch_at'])>=2048 and r['learned_before']==r['learned_after'],'restart/learned integrity '+name)
    if mode in LIVE:
     d=didx[(cat,name,rep,mode)]
     check(d['fold']==fold and d['par2_s']==r['par2_s'] and d['actual_switch_at']==r['switch_at'],'native decision row '+name)
     if r['r16_native_ready']=='1':
      check(abs(float(r['r16_native_score'])-float(r['r16_python_score']))<1e-5 and int(r['r16_native_conflict']) in (1024,1025),'C/Python score parity '+name)
      check(abs(float(d['native_score'])-float(d['independent_python_score']))<1e-5 and int(d['selected'])==int(r['r16_selected']),'aggregate score parity '+name)
     else:check(not r['r16_native_score'] and not d['native_score'],'spurious native decision '+name)
     if r['r16_model']:check(r['r16_model']==('snapshot' if mode=='r16_snapshot50' else 'trajectory'),'model type '+name)
     decisionout.append(dict(d))
    totals[(name,mode)]+=par2
   check(all(len(v)<=1 for v in statuses.values()),'SAT/UNSAT contradiction '+cat)
   for name in cases:
    f=fidx[(cat,name)]
    for mode in MODES:
     check(abs(totals[(name,mode)]-float(f[mode]))<.0002,'formula aggregate PAR-2 '+name+'/'+mode)
     if mode!='monitor':
      p=pidx[(cat,name,mode)]
      check(p['formula_sha256']==cases[name]['formula_sha256'] and abs(float(p['monitor_par2_s'])-totals[(name,'monitor')])<.0002 and abs(float(p['treatment_par2_s'])-totals[(name,mode)])<.0002,'paired PAR-2 '+name+'/'+mode)
      pairout.append(dict(p))
   dataset='DRNAS-R16-'+cat
   check(db.execute('SELECT COUNT(*) FROM datasets WHERE dataset=?',(dataset,)).fetchone()[0]==0,'already ingested '+dataset)
   provenance=('generated_community3_' if family=='community3' else 'generated_prospective_')+fold.split('_')[-1]
   db.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)',(dataset,provenance,'Synthetic '+family+' prospective real R16; NOT official; UNSAT uncertified',RUN,COMMIT,m['runner'],12,aggregate_sha))
   for name,c in cases.items():
    meta=c['metadata']
    db.execute('INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)',(dataset,name,fold,'UNKNOWN',c['formula_sha256'],None,c.get('path'),c['n'],meta['features']['clauses']))
    db.execute('INSERT INTO r16_formula_features VALUES (?,?,?,?,?,?,?,?,?)',(dataset,name,c['formula_sha256'],sha(folder/'manifest.json'),fold,meta['seed'],c['source_revision'],json.dumps(meta,sort_keys=True),sha(root/'aggregate/formula_features.csv')))
   for r in rows:
    name,mode,rep=key(r);status=r['status'];sat=flag(r['sat_model_checked']);unsat=flag(r['unsat_certificate_checked'])
    verified=1 if (status=='SAT' and sat==1) or (status=='UNSAT' and unsat==1) else 0 if status=='TIMEOUT' else None
    tier='sat_witness' if sat==1 else 'independent_unsat_certificate' if unsat==1 else 'unsat_label_only' if status=='UNSAT' else 'timeout'
    db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(dataset,name,mode,rep,float(r['wall_s']),status,verified,r.get('expected_action'),sat,unsat,float(r['par2_s']),integer(r['exit_code'])))
    db.execute('INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)',(dataset,name,mode,rep,m['runner'],r['seed'],cases[name]['source_revision'],r['formula_sha256'],rowsha(r),tier))
    db.execute('INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(dataset,name,mode,rep,None,num(r['early_g']),num(r['early_p']),num(r['early_d']),None,int(bool(r['switch_at'])),integer(r['switch_at']),integer(r['final_conflicts']),integer(r['final_restarts']),integer(r['trace_points'])))
    db.execute('INSERT INTO r16_native_details VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(dataset,name,mode,rep,num(r['cpu_s']),integer(r['switch_at']),rowsha(r),num(r['r16_native_score']),num(r['r16_python_score']),integer(r['r16_selected']),num(r['r16_threshold']),r['r16_model'],PROTOCOL,MODEL))
   for t in traces:
    name,mode,rep=key(t)
    for i,pt in enumerate(t['points']):
     db.execute('INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)',(dataset,name,mode,rep,i,None,integer(pt.get('conflict')),integer(pt.get('propagations')),integer(pt.get('restarts')),integer(pt.get('learned')),num(pt.get('glue'))))
   db.execute('INSERT INTO source_artifacts VALUES (?,?,?,?,?,?,?,?,?)',(dataset,RUN,COMMIT,index[artifact],sha(folder/'measurements.csv'),aggregate_sha,m['runner'],provenance,'R16 native; synthetic; UNSAT no independent proof'))
   sources.append(dict(dataset=dataset,run=RUN,commit=COMMIT,runner=m['runner'],artifact_id=index[artifact],fold=fold,formulas=10,attempts=300,measurements_sha256=sha(folder/'measurements.csv'),manifest_sha256=sha(folder/'manifest.json'),traces_sha256=sha(folder/'traces.jsonl'),aggregate_sha256=aggregate_sha))
   nrows+=len(rows)
  check((len(seen),nrows,len(sources),len(pairout),len(decisionout))==(160,4800,16,1440,1440),'final raw counts')
  after={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('datasets','formulas','attempts')}
  check(after==dict(datasets=151,formulas=2179,attempts=36530),'final cumulative counts '+str(after))
  check(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and db.execute('SELECT COUNT(*) FROM r16_native_details').fetchone()[0]==4800,'final DB integrity')
  check(db.execute("SELECT COUNT(*) FROM (SELECT formula_sha256 FROM formulas WHERE dataset LIKE 'DRNAS-R16-%' GROUP BY formula_sha256 HAVING COUNT(*)>1)").fetchone()[0]==0,'R16 SHA dedup')
  db.commit()
  export(out/'r16_source_audit.csv',sources);export(out/'r16_paired.csv',pairout)
  export(out/'r16_native_decisions.csv',decisionout);export(out/'r16_formula_features.csv',feats)
  for table in ('datasets','formulas'):
   q=db.execute('SELECT * FROM '+table+' ORDER BY 1,2');cols=[c[0] for c in q.description]
   export(out/(table+'.csv'),[dict(zip(cols,r)) for r in q])
  try:
   import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
   for fold in ('random3_development','random3_test','community3_development','community3_test'):
    fig,ax=plt.subplots(figsize=(8,6))
    for mode in LIVE:
     rr=[r for r in pairout if r['fold']==fold and r['mode']==mode]
     ax.scatter([float(r['monitor_par2_s']) for r in rr],[float(r['treatment_par2_s']) for r in rr],s=10,alpha=.4,label=mode)
    ax.plot([.0001,24],[.0001,24],'--',linewidth=.7,color='black')
    ax.set(xscale='log',yscale='log',xlabel='monitor paired PAR-2 (s)',ylabel='R16 native PAR-2 (s)',title='R16 '+fold+' synthetic, not official')
    ax.legend();fig.tight_layout();fig.savefig(out/('scatter_r16_'+fold+'.png'),dpi=130);plt.close(fig)
  except ImportError:pass
  audit=dict(status='VERIFIED_R16_NATIVE_INGEST',run=RUN,commit=COMMIT,baseline=before,after=after,unique_new_formula_sha256=160,new_native_attempts=4800,paired_attempts=4320,raw_shards=16,model_sha256=MODEL,protocol_sha256=PROTOCOL,history_sha256=HISTORY,source_artifacts=sources,limitations='Synthetic random3/community3, not official. SAT witnesses checked, UNSAT not independently certified. R16 real native, not R15 replay.')
  (out/'r16_ingest_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
  sp=out/'summary.json';summary=json.loads(sp.read_text()) if sp.exists() else {}
  summary['r16_verified_ingest']={k:v for k,v in audit.items() if k!='source_artifacts'}
  q=db.execute('SELECT * FROM datasets ORDER BY dataset');cols=[c[0] for c in q.description]
  summary['datasets']=[dict(zip(cols,r)) for r in q]
  sp.write_text(json.dumps(summary,indent=2)+'\n')
  print('R16_VERIFIED_CUMULATIVE_SQLITE_SUCCESS',json.dumps({'before':before,'after':after,'new_native_attempts':4800,'unique_new_formula_sha256':160}),flush=True)
 finally:db.close()
if __name__=='__main__':main()

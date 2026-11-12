"""24 original SAT2024 instances, size-stratified family representatives.
Exploratory potentially seen sources, no training or outcome-based selection.
"""
import hashlib,json,os,pathlib,random,shutil,time
import drnas_ltm12_progressive as L
B=L.B
ROOT=pathlib.Path('math14_real24');CAP=8.
ARMS=('MATH14','FIXED0','LTM13_ONLINE','LTM9_FAST','Kissat','CaDiCaL','CryptoMiniSat')
def collect():
 from remotezip import RemoteZip
 (ROOT/'cases').mkdir(parents=True)
 with RemoteZip(B.ARCHIVE,timeout=90) as z:
  pool,_,_=B.choose_archive_entries(z.infolist())
  pool.sort(key=lambda x:(x.file_size,x.filename))
  entries=[pool[int((i+.5)*len(pool)/24)] for i in range(24)]
  random.Random(1424).shuffle(entries);sources=[]
  for i,e in enumerate(entries):
   raw=B.decode(e,z.read(e));sha=hashlib.sha256(raw).hexdigest();p=ROOT/'cases'/f'{i:02d}_{sha[:12]}.cnf';p.write_bytes(raw)
   s=dict(id=i,path=str(p),sha256=sha,split='evaluation',source_file=e.filename,
          family=B.family_key(e.filename),bytes=len(raw),compressed_bytes=e.file_size)
   sources.append(s);L.emit('REAL24_SOURCE',s)
 assert len({s['sha256'] for s in sources})==24
 assert len({s['family'] for s in sources})==24
 (ROOT/'manifest.json').write_text(json.dumps(dict(archive=B.ARCHIVE,sources=sources,original_CNF=True,
   potentially_seen=True,blind=False,cap_s=CAP,repeats=2,selection='compressed-size quantiles across 100 family representatives'),indent=2))
 return sources

def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 for exe in ('kissat','cadical','cryptominisat5'):assert shutil.which(exe),exe
 old=B.command
 def command(a,p,s,c):
  if a in ('MATH14','FIXED0','LTM13_ONLINE'):
   exe='drnas_math14' if a=='MATH14' else 'drnas_ltm13'
   return ['mre_atlas23/bin/'+exe,str(p),'--mode','LTM8_FAST','--time',str(max(.1,c-.3)),'--seed',str(s),'--policy','1.0,0.85']
  return old(a,p,s,c)
 B.command=command;sources=collect();rows=[]
 with (ROOT/'results.jsonl').open('w') as fd:
  for s in sources:
   for rep,seed in enumerate((17,29)):
    shift=(s['id']+rep)%len(ARMS)
    for arm in ARMS[shift:]+ARMS[:shift]:
     os.environ.pop('DRNAS_LTM13_DIRECT',None);os.environ.pop('DRNAS_LTM13_FIXED',None)
     if arm in ('MATH14','FIXED0','LTM13_ONLINE'):
      os.environ['DRNAS_LTM13_DIRECT']='1'
      if arm!='LTM13_ONLINE':os.environ['DRNAS_LTM13_FIXED']='0'
     captured=[];orig=B.subprocess.run
     def capture(*a,**kw):
      p=orig(*a,**kw);captured.append(p.stdout or '');return p
     B.subprocess.run=capture
     try:r=L.run_checked(arm,s,seed,CAP)
     finally:B.subprocess.run=orig
     r.update(rep=rep,shard=s['id']//6,family=s['family'],telemetry=[l for txt in captured for l in txt.splitlines() if l.startswith(('c MATH14','c LTM13_WINDOW','LTM8_LEARNING'))])
     rows.append(r);fd.write(json.dumps(r)+'\n');fd.flush();L.emit('REAL24_TRIAL',r)
   B.check_contradictions(rows)
   L.emit('REAL24_PROGRESS',dict(completed=s['id']+1,totals=B.metrics(rows,CAP,ARMS)))
 totals=B.metrics(rows,CAP,ARMS)
 report=dict(original_official_CNF=True,possibly_seen=True,blind=False,one_CPU=True,cap_s=CAP,repetitions=2,
   totals=totals,shards={str(i):B.metrics([r for r in rows if r['shard']==i],CAP,ARMS) for i in range(4)},
   verified_speedup_vs_math={a:totals[a]['PAR2_verified_s']/totals['MATH14']['PAR2_verified_s'] for a in ARMS},
   verification='SAT original witness; UNSAT only PHP math certified, other UNSAT unverified; reported and verified PAR2 separate')
 (ROOT/'report.json').write_text(json.dumps(report,indent=2));L.emit('REAL24_FINAL',report)
 if os.getenv('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
   f.write('## MATH14 real24 — original SAT2024, possibly seen\n\n24 sources x 7 arms x 2 repeats; 8s; one CPU.\n\n|Arm|Verified solved|Reported solved|Verified PAR2 s|Reported PAR2 s|\n|---|---:|---:|---:|---:|\n')
   for a,m in totals.items():f.write(f"|{a}|{m['SAT_verified']+m['UNSAT_math_certified']}/{m['trials']}|{m['reported_solved']}|{m['PAR2_verified_s']:.3f}|{m['PAR2_reported_s']:.3f}|\n")
if __name__=='__main__':main()

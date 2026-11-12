import os,json,pathlib
import drnas_ltm13_hard600 as H
L,B,G=H.L,H.B,H.G
ROOT=pathlib.Path('math14')
ARMS=('LTM13_MATH','FIXED0','LTM9_FAST','Kissat','CaDiCaL','CryptoMiniSat')
def main():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});L.setup_source()
 H.ROOT=ROOT
 oldgen=H.generate_hard
 H.generate_hard=lambda f,s:oldgen(f,s+17000000)
 sources=H.collect();old=B.command
 def command(a,p,s,c):
  if a in ('LTM13_MATH','FIXED0'):
   exe='drnas_math14' if a=='LTM13_MATH' else 'drnas_ltm13'
   return ['mre_atlas23/bin/'+exe,str(p),'--mode','LTM8_FAST','--time',str(max(.1,c-.3)),'--seed',str(s),'--policy','1.0,0.85']
  return old(a,p,s,c)
 B.command=command;rows=[]
 with (ROOT/'results.jsonl').open('w') as fd:
  for src in sources:
   shift=src['id']%len(ARMS)
   for arm in ARMS[shift:]+ARMS[:shift]:
    r=H.trial(arm,src,17,0);r['shard']=src['id']//100
    rows.append(r);fd.write(json.dumps(r)+'\n');fd.flush()
   if (src['id']+1)%30==0:L.emit('MATH14_PROGRESS',B.metrics(rows,1,ARMS))
 B.check_contradictions(rows)
 report=dict(synthetic=True,learned_policy=False,new_seed_offset=17000000,one_CPU=True,repetitions=1,
             totals=B.metrics(rows,1,ARMS),shards={str(i):B.metrics([r for r in rows if r['shard']==i],1,ARMS) for i in range(6)})
 (ROOT/'report.json').write_text(json.dumps(report,indent=2));L.emit('MATH14_FINAL',report)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""ATLAS4 persistent, causal train/holdout test on similar real CNFs.
Train on 8 source-pinned Pett2021 snapshots, freeze learned decision rule,
then evaluate 8 later source-pinned snapshots. No holdout labels used to train.
Persistent model is JSON, content-hashed and reused unchanged for test.
SAT witness verified on original CNF, UNSAT never credited without proof.
"""
import hashlib,json,lzma,pathlib,resource,statistics,subprocess,time,urllib.request,math
OUT=pathlib.Path("mre_atlas4");OUT.mkdir(exist_ok=True)
COMMIT="de4731f68e5a5bb6629269b3be1d19b44e812763"
TRAIN=(
 ("Pett2021-2007-05-20_21-51-38.cnf.xz","896b650cc9154e3e27cf18ef55d9d8af1df5b283"),
 ("Pett2021-2007-05-21_23-30-54.cnf.xz","8648fbb8ceb2ef10ab030fcb3a49afca7b45ce76"),
 ("Pett2021-2007-06-08_08-02-53.cnf.xz","d2715d119c2d67cea76ca8354e0df276d24d0bf6"),
 ("Pett2021-2007-06-08_13-05-39.cnf.xz","334502066cf592fc1f664ff682d5e061039eb5f3"),
 ("Pett2021-2007-06-10_15-08-44.cnf.xz","ad8d77ab6f08e4a09c4351f6153e3e53616c41fb"),
 ("Pett2021-2007-06-10_17-11-59.cnf.xz","dd82be148723e01f52ae60ba23f2cdfa9ee8dcf5"),
 ("Pett2021-2007-06-11_16-31-55.cnf.xz","ea79ceb1e31aab87c69ddf18add94712a2dbb105"),
 ("Pett2021-2007-06-12_08-12-33.cnf.xz","bb97b7eac36398743c94cf665c692b496dd6ee04"),
)
HOLDOUT=(
 ("Pett2021-2007-06-12_22-04-57.cnf.xz","3d22ce0474d75066d58a577ecc17a3b61128456c"),
 ("Pett2021-2007-06-13_07-34-15.cnf.xz","4a5a3e61efff829f00a30f6ba5861de345e21761"),
 ("Pett2021-2007-06-15_23-43-11.cnf.xz","4daed902c7015100f5f70b4a57a325a6e94dcfdd"),
 ("Pett2021-2007-06-16_13-37-59.cnf.xz","b12c44a2077d01ff3c32109a7e1bbf94cca11d39"),
 ("Pett2021-2007-06-17_19-09-05.cnf.xz","c316de8cebc326da47d9a701a48983f9e5ddcdb0"),
 ("Pett2021-2007-06-19_11-24-47.cnf.xz","a935bf77afac197306269e3dd01bbb59d2de95f9"),
 ("Pett2021-2007-06-19_13-46-24.cnf.xz","5f42a0685148bedb9622fb28b61117bc7745fc1c"),
 ("Pett2021-2007-06-19_22-22-57.cnf.xz","bae52fab3649e9d4fea67e51c37af269110a74b3"),
)
# Correct a pinned hash by immutable upstream directory manifest BEFORE test.
CAP=8;REPS=3;ARMS=("A","ATLAS2","ATLAS3")
def load(entry):
 name,sha=entry
 with urllib.request.urlopen(f"https://raw.githubusercontent.com/Tractables/cnfs/{COMMIT}/feature-models/{name}",timeout=45) as u:raw=u.read(350001)
 assert len(raw)<350001
 blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
 assert blob==sha,(name,blob,sha)
 data=lzma.decompress(raw)
 assert len(data)<5000000
 header=None;clauses=[];current=[]
 for line in data.decode("ascii").splitlines():
  line=line.strip()
  if not line or line.startswith("c"):continue
  if line.startswith("p "):
   p=line.split();header=(int(p[2]),int(p[3]));continue
  if line.startswith("%"):break
  for tok in line.split():
   lit=int(tok)
   if lit==0:clauses.append(current);current=[]
   else:current.append(lit)
 assert header and not current and len(clauses)==header[1]
 assert all(all(abs(l)<=header[0] for l in c) for c in clauses)
 return data,header,clauses,blob
def features(header,clauses):
 n,m=header;hist=[0]*5
 for c in clauses:hist[min(4,len(c))]+=1
 # No labels, names, runtimes, models or SHA values in the predictor.
 return [math.log1p(n),math.log1p(m)]+[x/max(1,m) for x in hist]
def distance(a,b):
 return sum((x-y)**2 for x,y in zip(a,b))
def verify(stdout,n,clauses):
 assign={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line.split()[1:]:
    lit=int(token)
    if lit:
     if not 1<=abs(lit)<=n:return False
     if abs(lit) in assign and assign[abs(lit)]!=(lit>0):return False
     assign[abs(lit)]=lit>0
 return len(assign)==n and all(any(assign[abs(l)]==(l>0) for l in c) for c in clauses)
def execute(mode,path,n,clauses):
 exe=OUT/"bin/drnas_atlas3"
 cmd=[str(exe.resolve()),str(path.resolve()),"--mode",mode,"--time",str(CAP)]
 def limit():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
 t=time.monotonic()
 try:
  p=subprocess.run(cmd,text=True,capture_output=True,timeout=CAP+2,preexec_fn=limit)
  rc,stdout,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:rc,stdout,err=124,"","timeout"
 elapsed=time.monotonic()-t
 if rc==10:
  assert verify(stdout,n,clauses),("INVALID ORIGINAL SAT",mode,err[-400:])
  status="SAT_VERIFIED"
 elif rc==20:status="UNSAT_UNVERIFIED"
 elif rc in (0,124,-9,-24):status="UNKNOWN"
 else:raise RuntimeError((mode,rc,err[-500:]))
 return dict(mode=mode,status=status,e2e=round(elapsed,6),
             par2=round(elapsed if status=="SAT_VERIFIED" else 2*CAP,6))
def sample(entry,phase,index,modes=ARMS):
 data,header,clauses,blob=load(entry)
 p=OUT/"original.cnf";p.write_bytes(data)
 feat=features(header,clauses)
 trials=[]
 for rep in range(REPS):
  for mode in modes[rep%len(modes):]+modes[:rep%len(modes)]:
   x=execute(mode,p,header[0],clauses);x["rep"]=rep;trials.append(x)
   print("ATLAS4_TRIAL "+json.dumps(dict(phase=phase,index=index,file=entry[0],**x),sort_keys=True),flush=True)
 return dict(name=entry[0],blob=blob,sha256=hashlib.sha256(data).hexdigest(),
             vars=header[0],clauses=header[1],features=feat,trials=trials)
def median(row,mode):
 a=[x["par2"] for x in row["trials"] if x["mode"]==mode]
 assert len(a)==REPS
 return statistics.median(a)
def decision(model,feat):
 # Nonparametric persistent memory: nearest 3 source fingerprints,
 # choose atlas only with majority wins and conservative median margin.
 ranked=sorted(model["examples"],key=lambda x:distance(feat,x["features"]))[:3]
 votes=sum(x["winner"]=="ATLAS2" for x in ranked)
 return "ATLAS2" if len(ranked)==3 and votes==3 else "A"
def main():
 assert set(x[0] for x in TRAIN).isdisjoint(x[0] for x in HOLDOUT)
 train=[]
 for i,e in enumerate(TRAIN):
  row=sample(e,"TRAIN",i)
  base=median(row,"A");atlas=median(row,"ATLAS2")
  # Require 5% relative improvement AND 0.5 ms absolute improvement.
  # Conservative to reject noise on very short problems.
  row["winner"]="ATLAS2" if atlas<base*0.95 and base-atlas>0.0005 else "A"
  train.append(row)
  print("ATLAS4_TRAIN "+json.dumps(dict(index=i,winner=row["winner"],base_median=base,atlas_median=atlas),sort_keys=True),flush=True)
 model=dict(version=1,source_commit=COMMIT,training_only=True,
  threshold_relative=0.05,threshold_absolute_s=0.0005,
  examples=[dict(features=r["features"],winner=r["winner"],source_sha256=r["sha256"]) for r in train])
 canonical=json.dumps(model,sort_keys=True,separators=(",",":")).encode()
 (OUT/"learned_model.json").write_bytes(canonical)
 frozen_sha=hashlib.sha256(canonical).hexdigest()
 print("ATLAS4_MODEL_FROZEN "+json.dumps(dict(sha256=frozen_sha,training=len(train),
    atlas_wins=sum(x["winner"]=="ATLAS2" for x in train)),sort_keys=True),flush=True)
 test=[]
 for i,e in enumerate(HOLDOUT):
  assert hashlib.sha256((OUT/"learned_model.json").read_bytes()).hexdigest()==frozen_sha
  row=sample(e,"HOLDOUT",i)
  chosen=decision(model,row["features"])
  row["learned_choice"]=chosen
  row["learned_par2"]=sum(x["par2"] for x in row["trials"] if x["mode"]==chosen)
  row["A_par2"]=sum(x["par2"] for x in row["trials"] if x["mode"]=="A")
  row["ATLAS2_par2"]=sum(x["par2"] for x in row["trials"] if x["mode"]=="ATLAS2")
  row["ATLAS3_par2"]=sum(x["par2"] for x in row["trials"] if x["mode"]=="ATLAS3")
  test.append(row)
  print("ATLAS4_HOLDOUT "+json.dumps(dict(index=i,source_sha256=row["sha256"],
    choice=chosen,learned_PAR2_s=row["learned_par2"],A_PAR2_s=row["A_par2"],
    atlas2_PAR2_s=row["ATLAS2_par2"],atlas3_PAR2_s=row["ATLAS3_par2"]),sort_keys=True),flush=True)
 assert hashlib.sha256((OUT/"learned_model.json").read_bytes()).hexdigest()==frozen_sha
 totals={k:round(sum(r[k+"_par2"] for r in test),6) for k in ("learned","A","ATLAS2","ATLAS3")}
 solved={m:sum(x["status"]=="SAT_VERIFIED" for row in test for x in row["trials"] if x["mode"]==m) for m in ARMS}
 summary=dict(training=len(train),holdout=len(test),repeats=REPS,
  frozen_model_sha256=frozen_sha,learned_atlas_choices=sum(r["learned_choice"]=="ATLAS2" for r in test),
  PAR2_s=totals,solved=solved,
  protocol="single_family_temporal_source_disjoint_holdout_not_generalization_across_families")
 (OUT/"audit.json").write_text(json.dumps(dict(summary=summary,training=train,holdout=test),indent=2,sort_keys=True))
 print("ATLAS4_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()

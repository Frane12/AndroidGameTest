#!/usr/bin/env python3
"""ATLAS13: 24 SHA-unique corrected ATLAS13 holdout CNFs (64..69), 5 native oneCPU arms,
two seeded repeats; source-proof verified XOR UNSAT, original-model SAT verification.
Training 40..63; holdout 64..69, source namespace new. No train/holdout leakage. Actual wall E2E and PAR2, never replayed arm times.
"""
import argparse,collections,hashlib,json,os,pathlib,resource,subprocess,time
from importlib.machinery import SourceFileLoader
gen=SourceFileLoader("atlas7_gen","research/drnas_atlas13_generator.py").load_module()
ARMS=("A","C_RANDOM","C3_ADAPT","C4_LBD","C5_WARM","C5_WARM_GAUSS","C5_CDCL","C5_CDCL_GAUSS")
CAP=60;REPS=2
def dimacs(n,clauses):
 return ("p cnf %d %d\n"%(n,len(clauses))+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
def model_valid(stdout,n,clauses):
 values={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line.split()[1:]:
    literal=int(token)
    if literal==0:continue
    if abs(literal)<1 or abs(literal)>n:return False
    if abs(literal) in values and values[abs(literal)]!=(literal>0):return False
    values[abs(literal)]=literal>0
 return len(values)==n and all(any(values[abs(l)]==(l>0) for l in clause) for clause in clauses)
def source_xors_independent(clauses):
 groups=collections.defaultdict(set)
 for clause in clauses:
  if not (2<=len(clause)<=4):continue
  vs=sorted(set(map(abs,clause)))
  if len(vs)!=len(clause):continue
  mapping={v:i for i,v in enumerate(vs)}
  forbidden=sum((1<<mapping[abs(l)]) for l in clause if l<0)
  groups[tuple(vs)].add(forbidden)
 rows=[]
 for support in sorted(groups):
  k=len(support);have=groups[support]
  for parity in (0,1):
   needed={bits for bits in range(1<<k) if bits.bit_count()%2==parity}
   if needed.issubset(have):
    rows.append((support,1-parity))
 return rows[:1024]
def independently_verify_core(clauses,indices):
 rows=source_xors_independent(clauses)
 if not indices or len(set(indices))!=len(indices):return False
 if any(i<0 or i>=len(rows) for i in indices):return False
 parity=0;support=set()
 for i in indices:
  vs,rhs=rows[i];parity^=rhs;support.symmetric_difference_update(vs)
 return not support and parity==1
def process(arm,path,n,clauses,seed,cap=CAP,policy=None):
 cmd=[str(pathlib.Path("mre_atlas15/bin/drnas_atlas15").resolve()),
      str(path.resolve()),"--mode",arm,"--time",str(cap),"--seed",str(seed)]+(["--policy",policy or (pathlib.Path("training/ATLAS15_POLICY.txt").read_text().strip() if pathlib.Path("training/ATLAS15_POLICY.txt").exists() else "1.0,0.85")] if arm.startswith("C5_WARM") else [])
 def limit():
  resource.setrlimit(resource.RLIMIT_CPU,(cap+1,cap+2))
  resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
 t=time.monotonic()
 try:
  p=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+2,preexec_fn=limit)
  rc,output,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:
  rc,output,err=124,"","wall timeout"
 wall=time.monotonic()-t
 telemetry={}
 for line in output.splitlines():
  if line.startswith("ATLAS13_TRIAL "):
   telemetry=dict(kv.split("=",1) for kv in line.split()[1:] if "=" in kv)
 if rc==10:
  assert model_valid(output,n,clauses),("SAT original model invalid",arm,err[-500:])
  assert telemetry.get("SAT_original_verified")=="1"
  result="SAT_VERIFIED"
 elif rc==20:
  core_line=next((x for x in output.splitlines() if x.startswith("ATLAS13_GF2_CORE")),None)
  if core_line:
   indices=[int(i) for i in core_line.split()[1:]]
   assert independently_verify_core(clauses,indices),("independent GF2 UNSAT core invalid",arm,indices)
   result="GF2_UNSAT_VERIFIED"
  else:result="UNSAT_UNVERIFIED"
 elif rc in (0,124,-9,-24,-25):result="UNKNOWN"
 else:raise RuntimeError(("solver crashed",arm,rc,err[-1000:]))
 return dict(status=result,PAR2_s=round(wall if result in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") else 2*cap,6),
  E2E_s=round(wall,6),telemetry={k:telemetry.get(k,"") for k in
 ("table_matched","table_modules","table_saved_literals","table_s","gauss_s",
 "gauss_rows","gauss_rank","gauss_units","gauss_binaries","gauss_conflict","c_explorations","c_penalties","c_good_lbd","c_bad_lbd",
 "xor_source_rows","xor_derived_rows","xor_implications","conflicts","decisions","atlas15_deleted","atlas15_minimized","atlas15_reductions")})
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--shard",type=int,required=True)
 ap.add_argument("--shards",type=int,default=10)
 ap.add_argument("--smoke",action="store_true")
 ap.add_argument("--replay",action="store_true")
 args=ap.parse_args()
 assert 0<=args.shard<args.shards
 dest=pathlib.Path("mre_atlas15");dest.mkdir(exist_ok=True)
 suite=[]
 for category in ("random3_unsat","pigeonhole_unsat","mixed_hard","graph3color_unsat"):
  for i in range(64,70):
   n,clauses,seed=gen.build(category,i)
   raw=dimacs(n,clauses)
   suite.append(dict(category=category,index=i,seed=seed,sha256=hashlib.sha256(raw).hexdigest(),vars=n,clauses=len(clauses)))
 manifest=dict(seed=20261111,families=list(gen.CATEGORIES),case_count=len(suite),
  train_indices=list(range(40,64)),holdout_indices=list(range(64,70)),
  cap_s=CAP,reps=REPS,arms=list(ARMS),cases=suite,table_file="research/atlas8_reduction_table.jsonl")
 manifest_bytes=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
 (dest/"frozen_manifest.json").write_bytes(manifest_bytes)
 catalog_sha=hashlib.sha256(pathlib.Path("research/atlas8_reduction_table.jsonl").read_bytes()).hexdigest()
 selected=[s for s in suite if ((s["index"]-64)*4+("random3_unsat","pigeonhole_unsat","mixed_hard","graph3color_unsat").index(s["category"]))%args.shards==args.shard]
 if args.smoke:selected=selected[:2]
 assert len({x["sha256"] for x in suite})==len(suite), "holdout SHA collision"
 print("ATLAS15_MANIFEST "+json.dumps(dict(shard=args.shard,shards=args.shards,cases=len(selected),
   full_suite=len(suite),manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),catalog_sha256=catalog_sha)),flush=True)
 prior_index={}
 if args.replay:
  old=json.loads(pathlib.Path(f"firstpass/audit_{args.shard}.json").read_text())
  assert old["manifest"]==manifest,"first pass manifest changed"
  prior_index={(r["sha256"],r["rep"],r["arm"]):r for r in old["results"]}
  assert prior_index,"first pass missing"
 results=[]
 for j,s in enumerate(selected):
  n,clauses,seed=gen.build(s["category"],s["index"])
  raw=dimacs(n,clauses);assert hashlib.sha256(raw).hexdigest()==s["sha256"]
  path=dest/"current.cnf";path.write_bytes(raw)
  for rep in range(REPS):
   order=list(ARMS)
   shift=(j+rep*2)%len(order);order=order[shift:]+order[:shift]
   for arm in order:
    trial_seed=int.from_bytes(hashlib.sha256(("ATLAS13|seed|%s|%d"%(s["sha256"],rep)).encode()).digest()[:8],"big")
    policy=None
    if args.replay and arm.startswith("C5_"):
     old=prior_index.get((s["sha256"],rep,"C5_CDCL"))
     assert old is not None,"unpaired first pass"
     pfile=pathlib.Path("training/ATLAS15_POLICY.txt")
     explore,quality=map(float,(pfile.read_text().strip() if pfile.exists() else "1.0,0.85").split(","))
     if old["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED"):
      explore*=.90;quality*=1.05
     else:
      explore*=1.12;quality*=.90
     policy=f"{min(2,max(.25,explore)):.5f},{min(2,max(0,quality)):.5f}"
    result=process(arm,path,n,clauses,trial_seed,cap=5 if args.smoke else CAP,policy=policy)
    item=dict(category=s["category"],index=s["index"],sha256=s["sha256"],rep=rep,seed=trial_seed,arm=arm,pass_name="replay_learned" if args.replay else "first",applied_policy=policy or "",**result)
    results.append(item)
    print("ATLAS15_TRIAL "+json.dumps(item,sort_keys=True),flush=True)
  print("ATLAS15_PROGRESS "+json.dumps(dict(shard=args.shard,done=j+1,total=len(selected))),flush=True)
 byarm={}
 for arm in ARMS:
  sub=[r for r in results if r["arm"]==arm]
  byarm[arm]=dict(PAR2_s=round(sum(r["PAR2_s"] for r in sub),6),
    solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in sub),
    SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in sub),
    GF2_UNSAT_verified=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in sub),
    UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in sub),
    timeouts=sum(r["status"]=="UNKNOWN" for r in sub),
    table_modules=sum(int(r["telemetry"]["table_modules"] or 0) for r in sub),
    table_literals_saved=sum(int(r["telemetry"]["table_saved_literals"] or 0) for r in sub),
    gauss_units=sum(int(r["telemetry"]["gauss_units"] or 0) for r in sub),
    gauss_binary_rows=sum(int(r["telemetry"]["gauss_binaries"] or 0) for r in sub),
    trials=len(sub),
    E2E_s=round(sum(r["E2E_s"] for r in sub),6),
    decisions=sum(int(r["telemetry"]["decisions"] or 0) for r in sub),
    conflicts=sum(int(r["telemetry"]["conflicts"] or 0) for r in sub),
    c_explorations=sum(int(r["telemetry"]["c_explorations"] or 0) for r in sub),
    c_penalties=sum(int(r["telemetry"]["c_penalties"] or 0) for r in sub),
    c_good_lbd=sum(int(r["telemetry"]["c_good_lbd"] or 0) for r in sub),
    c_bad_lbd=sum(int(r["telemetry"]["c_bad_lbd"] or 0) for r in sub),
    atlas15_deleted=sum(int(r["telemetry"]["atlas15_deleted"] or 0) for r in sub),
    atlas15_minimized=sum(int(r["telemetry"]["atlas15_minimized"] or 0) for r in sub),
    atlas15_reductions=sum(int(r["telemetry"]["atlas15_reductions"] or 0) for r in sub))
 summary=dict(shard=args.shard,shards=args.shards,cases=len(selected),pass_name="replay_learned" if args.replay else "first",arms=byarm,
  source_SHA_locked=True,table_SHA_locked=catalog_sha,
  note="real native oneCPU wall end-to-end, no replay; UNSAT only credited with independently verified GF2 certificate")
 (dest/f"audit_{args.shard}.json").write_text(json.dumps(dict(manifest=manifest,summary=summary,results=results),indent=2))
 print("ATLAS15_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""SRE2C 6 source CNFs x 5 native modes x 3 reps = 90 oneCPU E2E.
Small synthetic nonblind diagnostic; no competition speed claim.
"""
import importlib.util,json,pathlib,re,subprocess,time
spec=importlib.util.spec_from_file_location("sre1","research/drnas_sre1_benchmark.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=pathlib.Path("mre_sre2c");root.mkdir(exist_ok=True)
binary=root/"bin/drnas_sre2c"
def xor3(a,b,c,rhs):
 return [[-a if bits&1 else a,-b if bits&2 else b,-c if bits&4 else c]
    for bits in range(8) if bits.bit_count()%2!=rhs]
def parity_chain(contradiction):
 cls=xor3(1,2,3,0)+xor3(3,4,5,1)+xor3(5,6,7,0)
 cls.extend([[1],[-2],[4],[-6],[(-7 if contradiction else 7)]])
 return 8,cls
def main():
 cases=[("radio_sat",m.radio(False)),("radio_unsat",m.radio(True)),
        ("parity_sat",m.parity(False)),("parity_unsat",m.parity(True)),
        ("xor_chain_sat",parity_chain(False)),
        ("xor_chain_unsat",parity_chain(True))]
 modes=("plain","sre2b","live_raw","live_reduced","live_shadow")
 rows=[]
 for label,(n,cls) in cases:
  path=root/(label+".cnf");path.write_text(m.dimacs(n,cls))
  expected=m.truth(n,cls)
  for mode in modes:
   for rep in range(3):
    t=time.perf_counter()
    p=subprocess.run([str(binary.resolve()),str(path.resolve()),
       "--mode",mode,"--time","3"],capture_output=True,text=True,timeout=5)
    wall=time.perf_counter()-t
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr)
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    if status!=expected:raise RuntimeError(f"truth mismatch {label} {mode}: {status}!={expected}")
    line=re.search(r"^SRE2C_TRIAL (.*)$",p.stdout,re.M)
    if not line:raise RuntimeError("missing native telemetry")
    metrics=dict(x.split("=",1) for x in line.group(1).split() if "=" in x)
    if status=="SAT":
     lits=[int(x) for l in p.stdout.splitlines() if l.startswith("v ")
           for x in l[2:].split() if x!="0"]
     values={abs(x):x>0 for x in lits}
     if len(values)!=n or not all(any(values[abs(l)]==(l>0) for l in c) for c in cls):
      raise RuntimeError("original witness invalid")
    row=dict(source=label,mode=mode,rep=rep,status=status,
       E2E_s=round(wall,6),independent_exhaustive_truth=expected,metrics=metrics)
    rows.append(row)
    print("SRE2C_TRIAL_JSON "+json.dumps(row,sort_keys=True),flush=True)
 scores={}
 for mode in modes:
  r=[x for x in rows if x["mode"]==mode]
  scores[mode]=dict(solved=len(r),PAR2_s=round(sum(x["E2E_s"] for x in r),6),
    live_GF2_implications=sum(int(x["metrics"]["gf2_implications"]) for x in r),
    live_GF2_reasons=sum(int(x["metrics"]["gf2_reasons"]) for x in r),
    GF2_checks=sum(int(x["metrics"]["gf2_checks"]) for x in r),
    native_conflicts=sum(int(x["metrics"]["conflicts"]) for x in r),
    native_decisions=sum(int(x["metrics"]["decisions"]) for x in r))
 result=dict(protocol="DRNAS-SRE2C-6SOURCES-5ARMS-3REPS-ONECPU-v1",
   trials=len(rows),sources=len(cases),one_logical_cpu=True,
   independent_exhaustive_truth=True,original_SAT_witness_verified=True,
   original_UNSAT_independent_LRAT=False,nonblind_synthetic_development=True,
   third_party_solver_calls=0,scores=scores,rows=rows)
 (root/"audit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 print("SRE2C_FINAL "+json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":main()

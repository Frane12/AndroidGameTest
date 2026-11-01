#!/usr/bin/env python3
"""V16.6b exact feature invariance and development-only regression audit."""
import json,math,random,sys
from pathlib import Path
sys.path.insert(0,"experiments/drnas_v16")
from relations_v166b import features,choose,report
from generate_v166b import make

root=Path("v166b_static_property")
root.mkdir(exist_ok=True)
check=[
  (165000,640,"--sat",.5269461078,.226775),
  (165001,640,"default",.4969325153,.228545),
  (165004,480,"default",.4913294798,.237072),
  (165005,480,"--sat",.4838709677,.236402),
]
for seed,n,expected,f4,skew in check:
 path=root/f"dev_{seed}.cnf";make(path,n,seed,4.26)
 f=features(path)
 assert abs(f["signed_cycle_frustration"]-f4)<1e-7,(seed,f)
 assert abs(f["local_polarity_skew"]-skew)<1e-5,(seed,f)
 chosen=" ".join(choose(f)) or "default"
 assert chosen==expected,(seed,chosen,f)
 print("V166B_DEVELOPMENT",seed,"choice",chosen,json.dumps(report(f),sort_keys=True))
 # File relocation and clause ordering cannot change extracted relations.
 lines=path.read_text().splitlines()
 clauses=lines[2:];random.Random(seed).shuffle(clauses)
 perm_path=root/f"shuffled_{seed}.cnf"
 perm_path.write_text(lines[0]+"\n"+lines[1]+"\n"+"\n".join(clauses)+"\n")
 g=features(perm_path)
 for key in ("signed_cycle_frustration","signed_cycle_count","repeated_pair_rate",
             "degree_cv","local_polarity_skew","three_fraction"):
  assert abs(f[key]-g[key])<1e-10,(seed,key,f[key],g[key])
 assert choose(f)==choose(g)
# Verify 2-variable sign-parity 4-cycle counts on a tiny exact original CNF.
p=root/"signed4.cnf"
p.write_text("c test\np cnf 4 3\n1 2 3 0\n-1 2 4 0\n-1 -2 3 0\n")
f=features(p)
# Pair (1,2) parity across occurrences: even/odd/even.
assert f["frustrated_cycles"]>=2,f
assert f["signed_cycle_count"]>=3,f
# Non-3SAT and low dimensional formulas always abstain.
assert choose(f)==()
try:
 bad=root/"invalid.cnf";bad.write_text("p cnf 2 1\n1 3 0\n")
 features(bad)
 raise AssertionError("invalid literal wrongly accepted")
except ValueError: pass
print("V166B_FEATURE_PROPERTY_PASS",len(check)+3,flush=True)

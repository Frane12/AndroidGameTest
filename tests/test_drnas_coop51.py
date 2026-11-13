#!/usr/bin/env python3
"""COOP5.1 hybrid original CNF oracle and proof check against frozen CDCL."""
import json,os,pathlib,random,subprocess,sys,tempfile
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research/drnas_coop1"))
from synthetic import encode,xor,and_xor,oracle,text,model_ok
sys.path.insert(0,str(R/"tests"))
from test_drnas_coop4 import check_rup
CASES=[(0,[]),(0,[[]]),(1,[[1],[-1]]),
       (3,[[1,2],[-1,3],[-2,-3]])]
for mask in range(256):
    CASES.append((3,encode([1,2,3],lambda bits:bool(mask&(1<<sum(v<<i for i,v in enumerate(bits)))))))
rng=random.Random(112603)
for _ in range(50):
    n=rng.randrange(2,11);cs=[]
    for _ in range(rng.randrange(n,5*n)):
        vs=rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))
        cs.append([x*rng.choice((-1,1)) for x in vs])
    CASES.append((n,cs))
CASES +=[(4,xor([1,2,3],0)+xor([1,2,4],1)),
         (4,xor([1,2,3],0)+xor([1,2,4],1)+xor([3,4],0)),
         (5,and_xor([1,2,3,4],0)+and_xor([1,2,4,5],1))]
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins=("hybrid",)
    modes=(("OFF","off","off"),("ALGEBRA","algebra","off"),
           ("SHADOW","on","shadow"),("ON","on","on"))
    checks=0;cert_unsat=0;proof_steps=0
    with tempfile.TemporaryDirectory() as d:
        d=pathlib.Path(d);src=d/"input.cnf";proof=d/"proof.drat"
        for idx,(n,clauses) in enumerate(CASES):
            expected=oracle(n,clauses)
            src.write_text(text(n,clauses))
            results=[]
            for policy in bins:
                binary=R/"build/drnas-coop51-hybrid"
                for arm,mathmode,probe in modes:
                    cmd=[str(binary),str(src),"--mode","core","--time","2","--stats",
                         "--x5-no-minimize","--proof",str(proof),
                         "--coop4",mathmode,"--coop5",probe]
                    p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
                    assert p.returncode==(10 if expected else 20),(
                        idx,policy,arm,p.returncode,p.stderr[-900:])
                    if expected: assert model_ok(n,clauses,p.stdout)
                    proof_steps+=check_rup(clauses,proof.read_text())
                    if not expected:
                        q=subprocess.run([str(R/"build/drat-trim"),str(src),str(proof)],
                                         capture_output=True,text=True,timeout=8)
                        assert "s VERIFIED" in q.stdout,(
                            idx,arm,q.stdout[-400:],q.stderr[-300:])
                        cert_unsat+=1
                    probes=[json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
                            if l.startswith("COOP5_PROBE ")]
                    assert len(probes)==1,(idx,policy,arm,p.stderr[-600:])
                    st=probes[0]
                    assert st["default_policy"]==policy and st["mode"]==probe
                    assert st["hybrid_deep_pairs"]+st["hybrid_shallow_pairs"]==st["attempted_pairs"],(idx,st)
                    assert st["hybrid_deep_pairs"]==st["depth320"],(idx,st)
                    assert st["depth900"]==0,(idx,st)
                    assert st["probe_wall_ms"]<=st["budget_ms"]+2,(idx,st)
                    assert st["actually_overrode"]==0 if probe!="on" else True
                    assert st["attempted_pairs"]>=st["actually_overrode"]
                    assert st["budget_ms"]>0
                    checks+=1
                    results.append((policy,arm,p.returncode))
            assert {x[2] for x in results}==({10} if expected else {20})
    print("COOP51_SAFETY_PASS "+json.dumps({
       "sources":len(CASES),"results":checks,
       "proof_steps_RUP":proof_steps,"independent_unsat_Drat":cert_unsat,
       "builds":["hybrid"],
       "controls":["OFF","ALGEBRA","SHADOW","ON"],
       "no_unverified_results":True},sort_keys=True),flush=True)
if __name__=="__main__":main()

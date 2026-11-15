#!/usr/bin/env python3
"""Preregistered outcome-blind SAT-XOR100 frozen input builder.
100 newly generated SHA-distinct SAT sources, fixed category/size/index choice.
No solver invoked here. No outcome-based filtering.
"""
import hashlib,json,os,random,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"xor_blind1_inputs"
PROTOCOL="DRNAS-XORBLIND1-20261115-FROZEN-V1"
SEED=0x2611157
FAMILIES=("pure_xor3","pure_xor4","mixed_xor3","partial_xor3","nonxor_negative")
EXCLUDED={
 "243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83",
 "fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16",
}
def sha(b):return hashlib.sha256(b).hexdigest()
def satisfies(cs,bits):
    return all(any((x>0)==bits[abs(x)-1] for x in c) for c in cs)
def generate(family,index):
    n=48+12*(index%4)+8*(index//8)
    rng=random.Random(SEED + 1000003*FAMILIES.index(family)+7919*index)
    bits=[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[];metadata={"nvars":n}
    if family=="nonxor_negative":
        for _ in range((42*n)//10):
            variables=rng.sample(range(1,n+1),3)
            while True:
                clause=[v if rng.getrandbits(1) else -v for v in variables]
                if any((l>0)==bits[abs(l)-1] for l in clause):break
            clauses.append(clause)
    else:
        width=4 if family=="pure_xor4" else 3
        eqs=n+14
        missing=0
        for eq in range(eqs):
            variables=sorted(rng.sample(range(1,n+1),width))
            parity=sum(bits[v-1] for v in variables)%2
            forbidden=[]
            for assignment in range(1<<width):
                if assignment.bit_count()%2==parity:continue
                forbidden.append([(-v if (assignment>>i)&1 else v)
                                  for i,v in enumerate(variables)])
            if family=="partial_xor3" and eq%4==0:
                forbidden.pop(rng.randrange(len(forbidden)))
                missing+=1
            clauses.extend(forbidden)
        if family=="mixed_xor3":
            for _ in range(n//2):
                variables=rng.sample(range(1,n+1),5)
                while True:
                    c=[v if rng.getrandbits(1) else -v for v in variables]
                    if any((l>0)==bits[abs(l)-1] for l in c):break
                clauses.append(c)
        metadata.update(equations=eqs,width=width,partial_patterns=missing)
    rng.shuffle(clauses)
    for clause in clauses:rng.shuffle(clause)
    assert satisfies(clauses,bits)
    return n,clauses,metadata

def freeze():
    if OUT.exists():raise RuntimeError("frozen output already exists; no overwrite")
    (OUT/"cnf").mkdir(parents=True)
    records=[];seen=set()
    for family in FAMILIES:
        for index in range(20):
            n,cs,meta=generate(family,index)
            src=f"p cnf {n} {len(cs)}\n"+ "".join(
                " ".join(map(str,c))+" 0\n" for c in cs)
            digest=sha(src.encode())
            assert digest not in seen and digest not in EXCLUDED
            seen.add(digest)
            sid=len(records)
            name=f"{sid:03d}-{digest[:16]}.cnf"
            path=OUT/"cnf"/name
            path.write_text(src)
            assert sha(path.read_bytes())==digest
            records.append(dict(id=sid,family=family,sha256=digest,
              path=str(path.relative_to(ROOT)),nvars=n,clauses=len(cs),
              bytes=len(src.encode()),generator_settings=meta))
    assert len(records)==100 and len(seen)==100
    generator_sha=sha(Path(__file__).read_bytes())
    manifest=dict(protocol=PROTOCOL,source_count=len(records),
      families=list(FAMILIES),family_counts={f:20 for f in FAMILIES},
      seed=SEED,generator_sha256=generator_sha,
      source_selection="fixed family/index/seed, no outcome observation",
      known_sat_by_construction=True,
      classification_is_input_construction_not_solver_result=True,
      previously_tested_sha_excluded=sorted(EXCLUDED),
      prior_art="Gaussian elimination and CNF XOR pattern recognition",
      blind_scope="NEW synthetic source-disjoint cases; not unseen official competition sources",
      no_adaptive_selection=True,solver_evaluation_started=False,
      git_sha=os.environ.get("GITHUB_SHA"),
      sources=records)
    (OUT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("XOR_BLIND_FROZEN "+json.dumps(dict(sources=len(records),
       input_manifest_sha256=sha((OUT/"manifest.json").read_bytes()),
       generator_sha256=generator_sha,
       families=manifest["family_counts"]),sort_keys=True),flush=True)
if __name__=="__main__":freeze()

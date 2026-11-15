#!/usr/bin/env python3
"""XORHARD2 prospective SHA-distinct SAT inputs, frozen BEFORE timing solvers.
Six fixed structural cohorts, 10 instances each. No solver used for selection.
"""
import hashlib,itertools,json,os,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"xor_hard2_inputs"
SEED=0x20261115A
FAMILIES=("pure_xor3","pure_xor4","pure_xor5","pure_xor6",
          "mixed_xor5","partial_xor3")
PROTOCOL="DRNAS-XORHARD2-FROZEN-V1"
EXCLUDED={
 "243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83",
 "fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16",
}
def sha(b):return hashlib.sha256(b).hexdigest()
def generate(family,index):
    fi=FAMILIES.index(family)
    n=160+48*(index%5)+16*(fi%3)
    rng=random.Random(SEED+10000019*fi+15401*index)
    witness=[bool(rng.getrandbits(1)) for _ in range(n)]
    width=int(family[-1]) if family.startswith("pure_xor") else (5 if family=="mixed_xor5" else 3)
    equations=n+10
    clauses=[]
    for eq in range(equations):
        vs=sorted(rng.sample(range(1,n+1),width))
        parity=sum(witness[v-1] for v in vs)&1
        forbidden=[]
        for mask in range(1<<width):
            if mask.bit_count()%2==parity:continue
            forbidden.append([-v if (mask>>k)&1 else v for k,v in enumerate(vs)])
        if family=="partial_xor3" and eq%5==0:
            forbidden.pop(rng.randrange(len(forbidden)))
        clauses.extend(forbidden)
    if family=="mixed_xor5":
        for _ in range(n//3):
            vs=rng.sample(range(1,n+1),7)
            while True:
                c=[v if rng.getrandbits(1) else -v for v in vs]
                if any((lit>0)==witness[abs(lit)-1] for lit in c):break
            clauses.append(c)
    rng.shuffle(clauses)
    for clause in clauses:rng.shuffle(clause)
    assert all(any((l>0)==witness[abs(l)-1] for l in c) for c in clauses)
    return n,clauses,dict(equations=equations,width=width)
def main():
    if OUT.exists():raise RuntimeError("refuse to overwrite frozen source")
    (OUT/"cnf").mkdir(parents=True)
    sources=[];seen=set()
    for family in FAMILIES:
        for index in range(10):
            n,clauses,meta=generate(family,index)
            content=f"p cnf {n} {len(clauses)}\n"+ "".join(
                " ".join(map(str,c))+" 0\n" for c in clauses)
            digest=sha(content.encode())
            assert digest not in seen and digest not in EXCLUDED
            seen.add(digest)
            idx=len(sources)
            path=OUT/"cnf"/f"{idx:03d}-{digest[:16]}.cnf"
            path.write_text(content)
            sources.append(dict(id=idx,family=family,nvars=n,nclauses=len(clauses),
                sha256=digest,path=str(path.relative_to(ROOT)),
                bytes=len(content.encode()),generator_settings=meta))
    assert len(sources)==60 and len(seen)==60
    manifest=dict(protocol=PROTOCOL,seed=SEED,generator_sha256=sha(Path(__file__).read_bytes()),
      source_count=60,families=list(FAMILIES),cohort_sizes={f:10 for f in FAMILIES},
      sources=sources,selection="deterministic structural class and size only",
      known_sat_by_construction=True,no_solver_outcomes_used=True,
      prior_XORBLIND1_never_used_for_instance_selection=True,
      synthetic_not_unseen_official=True,
      git_sha=os.environ.get("GITHUB_SHA"))
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("XOR_HARD2_FROZEN "+json.dumps(dict(sources=len(sources),
      total_bytes=sum(s["bytes"] for s in sources),generator_sha256=manifest["generator_sha256"],
      manifest_sha256=sha((OUT/"manifest.json").read_bytes()),
      families=manifest["cohort_sizes"]),sort_keys=True),flush=True)
if __name__=="__main__":main()

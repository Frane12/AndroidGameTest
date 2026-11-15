#!/usr/bin/env python3
"""ARG3 independent SAT witness checker on genuine original #299 and fixtures.
Full original CNF checked every time; negative controls never accepted as SAT.
"""
import json,random,subprocess,tempfile
from pathlib import Path
from diagnose import ROOT,TARGET_SHA,TARGET,sha,witness_ok
BIN=ROOT/"build/drnas-sat-native-x59"
def generate(seed,n=28,blocked=False):
    rng=random.Random(seed)
    planted={0,3,7,11,16,22}
    attacks=set()
    for target in range(n):
        if target in planted:continue
        attacks.add((rng.choice(sorted(planted)),target))
    for a in range(n):
        for b in range(n):
            if a==b or (a in planted and b in planted):continue
            if rng.random()<.22:attacks.add((a,b))
    attackers=[set() for _ in range(n)]
    for a,b in attacks:attackers[b].add(a)
    # Ensure at least three attackers so every relation clause is wide.
    for i in range(n):
        while len(attackers[i])<3:
            a=rng.randrange(n)
            if a==i or (a in planted and i in planted):continue
            attackers[i].add(a);attacks.add((a,i))
    clauses=[]
    for i in range(n):
        a=i+1;b=n+i+1;c=2*n+i+1
        clauses.extend([[a,b,c],[-a,-b],[-a,-c],[-b,-c]])
        incoming=sorted(attackers[i])
        clauses.append([i+1]+[-n-j-1 for j in incoming])
        clauses.append([-n-i-1]+[j+1 for j in incoming])
    for a,b in sorted(attacks):
        clauses.append([-a-1,n+b+1])
        clauses.append([-b-1,n+a+1])
    clauses.append([i+1 for i in range(n)])
    if blocked:
        # Exclude exactly the planted extension. A different SAT model
        # may exist; the constructor must either verify it or abstain.
        clauses.append([i+1 for i in range(n) if i not in planted])
    rng.shuffle(clauses)
    return 3*n,clauses
def model_check(n,clauses,output):
    values={}
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                lit=int(word)
                if not lit:continue
                if abs(lit) in values and values[abs(lit)]!=(lit>0):
                    return False
                values[abs(lit)]=(lit>0)
    return len(values)==n and all(any(
       values[abs(l)]==(l>0) for l in c) for c in clauses)
def run(path,flags):
    p=subprocess.run([str(BIN),str(path),"--mode","core","--time","2",
        "--stats",*flags],capture_output=True,text=True,timeout=3.5)
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"bad solver rc={p.returncode}: {p.stderr[-350:]}")
    found=None
    for line in p.stderr.splitlines():
        if line.startswith("SAT_ARG3_STATS "):found=json.loads(line.split(" ",1)[1])
    assert found is not None,"ARG3 telemetry missing"
    return p,found
def main():
    assert BIN.is_file()
    manifest=json.loads((ROOT/"sat_real2025_inputs/manifest.json").read_text())
    source=next(x for x in manifest["ready_sources"] if x["gbd"]==TARGET)
    assert source["sha256"]==TARGET_SHA
    original=ROOT/source["path"];assert sha(original)==TARGET_SHA
    verified=0;recognition=0
    with tempfile.TemporaryDirectory() as td:
        for i in range(12):
            n,clauses=generate(0x10292025+i,blocked=bool(i%3==0))
            path=Path(td)/"synthetic.cnf"
            path.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            p,s=run(path,["--arg3-ms","100"])
            recognition+=s["recognized"]
            if p.returncode==10:
                assert model_check(n,clauses,p.stdout),("invalid synthetic SAT",i)
                verified+=1
        for i in range(10):
            # unrelated CNFs must be rejected by ARG3 shape guard
            rng=random.Random(17+i)
            n=90;clauses=[]
            for j in range(100):
                vs=rng.sample(range(1,n+1),3)
                clauses.append([rng.choice([-1,1])*v for v in vs])
            path=Path(td)/"negative.cnf"
            path.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            p,s=run(path,["--arg3-ms","50"])
            assert not s["recognized"] and not s["found"]
            if p.returncode==10:
                assert model_check(n,clauses,p.stdout)
    original_rows=[]
    for rep in range(3):
        p,s=run(original,["--arg3-ms","100"])
        assert p.returncode==10 and "s SATISFIABLE" in p.stdout and s["recognized"] and s["found"]
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/"model";model.write_text(p.stdout)
            assert witness_ok(original,model)
        original_rows.append(dict(repeat=rep,stats=s))
    print("ARG3_SOURCE_CONTROLS "+json.dumps(dict(synthetic=12,
        synthetic_verified=verified,structural_recognized=recognition,
        unrelated_negative=10,original_299_verified=3,
        source_sha256=TARGET_SHA,original_trials=original_rows),
        sort_keys=True),flush=True)
if __name__=="__main__":main()

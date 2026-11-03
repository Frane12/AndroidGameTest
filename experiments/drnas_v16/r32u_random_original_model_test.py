#!/usr/bin/env python3
"""R32u self-contained deterministic 60-source SAT/UNSAT model soundness check.

No external solver needed except clean pinned Kissat and active/passive
versions of the same modified native Kissat. All original parity clause
blocks are complete and each planted model is independently checked.
The 15 UNSAT sources have contradictory original unit clauses; we do not
misattribute trivially UNSAT claims to GF2.
"""
from pathlib import Path
import argparse,itertools,os,random,re,subprocess,time

def check(v,msg):
    if not v:raise RuntimeError("R32U_60_SOURCE_SOUNDNESS_FAILURE "+str(msg))

def generate(seed,n=28):
    rng=random.Random(202611030+seed)
    truth={v:rng.randrange(2) for v in range(1,n+1)}
    clauses=[]
    for j in range(12):
        a=1+(j%3);b=4+(j*2)%17;c=4+(j*2+1)%17
        v=sorted(set((a,b,c)))
        if len(v)!=3:continue
        rhs=truth[v[0]]^truth[v[1]]^truth[v[2]]
        for assignment in itertools.product((0,1),repeat=3):
            if assignment[0]^assignment[1]^assignment[2]!=rhs:
                clauses.append(tuple(-var if bit else var for var,bit in zip(v,assignment)))
    for _ in range(50):
        v=rng.sample(range(1,n+1),3)
        clause=tuple(v[i] if rng.randrange(2) else -v[i] for i in range(3))
        if not any((lit>0)==bool(truth[abs(lit)]) for lit in clause):
            clause=(v[0] if truth[v[0]] else -v[0],clause[1],clause[2])
        clauses.append(clause)
    if seed%4==0:clauses.extend(((n,),(-n,)))
    return n,clauses,seed%4==0

def check_model(out,n,clauses):
    assignment={}
    for line in out.splitlines():
        if line.startswith("v "):
            for i in map(int,line[2:].split()):
                if i:assignment[abs(i)]=i>0
    check(len(assignment)==n,"Incomplete original SAT assignment")
    for clause in clauses:
        check(any((lit>0)==assignment[abs(lit)] for lit in clause),
              "Claimed SAT assignment violates original mixed-XOR CNF")

def run(clean,native,directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    modes={"clean":Path(clean).resolve(),
           "passive":Path(native).resolve(),"active":Path(native).resolve()}
    flags=["--no-luckyearly","--no-luckylate","--no-preprocess"]
    results=[];attached=0;implications=0
    for seed in range(60):
        n,clauses,unsat=generate(seed)
        source=root/f"case_{seed:02d}.cnf"
        source.write_text(f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,clause))+" 0\n" for clause in clauses))
        verdicts={}
        for mode,binary in modes.items():
            env=os.environ.copy()
            env.update(R32B_MODE="r32u",R32U_ACTIVE="1" if mode=="active" else "0",
                       R32S_PASSIVE_TRACE="0")
            p=subprocess.run([str(binary)]+flags+[str(source)],env=env,
                 capture_output=True,text=True,errors="replace",timeout=3)
            check(p.returncode in (10,20),
                  f"Unexpected {seed}/{mode} exit {p.returncode} {p.stderr[-300:]}")
            verdicts[mode]=p.returncode
            if p.returncode==10:check_model(p.stdout,n,clauses)
            if mode in ("active","passive"):
                stats=re.search(r"^c R32U_STATS active=(\d+) rows=(\d+) scans=(\d+)"
                    r" candidates=(\d+) attached=(\d+) conflict_rows=(\d+)",
                    p.stdout,re.M)
                check(stats is not None,"Native reason accounting absent")
                count=int(stats[5])
                if mode=="passive":check(count==0,"Passive mode attached a reason")
                else:
                    attached+=count
                    implications+=int(stats[4])
        check(len(set(verdicts.values()))==1,
             f"Modified Kissat contradicts baseline on original {seed}")
        check((verdicts["clean"]==20)==unsat,
              f"Generated original formula verdict mismatch seed {seed}")
        results.append(verdicts)
    check(attached>0,"No real active XOR assignments on 60 frozen synthetic cases")
    print("R32U_60_GENERATED_MIXED_SAT_UNSAT_VERDICT_PASS",
          len(results),"SAT",sum(r["clean"]==10 for r in results),
          "UNSAT",sum(r["clean"]==20 for r in results),
          "native_live_XOR_reason_clauses",attached,
          "native_XOR_implication_candidates",implications,flush=True)

def main():
    p=argparse.ArgumentParser()
    for f in ("clean","native","out"):p.add_argument("--"+f,required=True)
    a=p.parse_args()
    run(a.clean,a.native,a.out)
if __name__=="__main__":main()

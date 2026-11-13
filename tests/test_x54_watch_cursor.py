#!/usr/bin/env python3
"""X5.4 exact SAT/UNSAT + DRAT oracle, watched-scan control and candidate."""
import itertools,json,pathlib,random,subprocess,tempfile

BINS={"X53":"build/drnas-x53","CONTROL":"build/drnas-x54","ROTATE":"build/drnas-x54"}
TRIM="build/drat-trim"


def brute(clauses,n):
    for bits in itertools.product((-1,1),repeat=n):
        if all(any(bits[abs(lit)-1]==(1 if lit>0 else -1)
                   for lit in c) for c in clauses):
            return True
    return False


def witness(s,clauses,n):
    assignments={}
    for line in s.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit=int(token)
                if lit:
                    if abs(lit)>n or (abs(lit) in assignments and assignments[abs(lit)]!=(lit>0)):
                        return False
                    assignments[abs(lit)]=lit>0
    return all(any(assignments.get(abs(lit))==(lit>0) for lit in c) for c in clauses)


def run(src,clauses,n,expected,arm,td):
    proof=td/("x54_"+arm+".drat")
    cmd=[BINS[arm],str(src),"--mode","core","--time","3","--proof",str(proof),
         "--x52-proof-deletions","--x53-policy","baseline","--stats"]
    if arm=="ROTATE":cmd.append("--x54-rotate-watches")
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    assert p.returncode==(10 if expected else 20), (src,arm,p.returncode,p.stderr[-900:])
    if expected:assert witness(p.stdout,clauses,n),(arm,"incorrect SAT")
    else:
        check=subprocess.run([TRIM,str(src),str(proof)],
                             capture_output=True,text=True,timeout=5)
        assert check.returncode==0 and "s VERIFIED" in check.stdout,(arm,"incorrect UNSAT proof",check.stdout[-400:])
    obj={}
    for line in p.stderr.splitlines():
        if line.startswith("X41_STATS "):obj=json.loads(line[10:])
    assert obj,("missing stats",arm)
    x={}
    for line in p.stderr.splitlines():
        if line.startswith("X53_STATS "):x=json.loads(line[10:])
    assert x,("missing x53 stats",arm)
    assert x["live_learnt"]==x["live_used"]+x["live_unused"]
    if arm!="X53":
        assert x["x54_deleted_never_reused"]+x["x54_deleted_reused"]==(
            x["deleted_unused"]+x["deleted_used"])
    return obj,x


def main():
    rng=random.Random(541113)
    counts={"SAT":0,"UNSAT":0}
    rotations=0
    with tempfile.TemporaryDirectory() as tmp:
        td=pathlib.Path(tmp);src=td/"input.cnf"
        for i in range(90):
            n=5+i%5
            clauses=[]
            for _ in range(4*n+(i%17)):
                k=min(n,2+(i%4))
                vars_=rng.sample(range(1,n+1),k)
                clauses.append([v if rng.getrandbits(1) else -v for v in vars_])
            if i%19==0:clauses.extend([[1],[-1]])
            expected=brute(clauses,n)
            counts["SAT" if expected else "UNSAT"]+=1
            src.write_text(f"p cnf {n} {len(clauses)}\n"+
                           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            baseline,xb=run(src,clauses,n,expected,"X53",td)
            control,xc=run(src,clauses,n,expected,"CONTROL",td)
            # Adding X5.4 counters and cursor storage without enabling cursor
            # must preserve the exact control search counts.
            for key in ("conflicts","decisions","learnt","propagations","reduce_removed"):
                assert baseline[key]==control[key],(i,key,baseline[key],control[key])
            rotate,xr=run(src,clauses,n,expected,"ROTATE",td)
            rotations+=xr.get("x54_rotated_scans",0)
        assert counts["SAT"]>0 and counts["UNSAT"]>0
    print("X54_SELFTEST_PASS "+json.dumps({
        "sources":90,"runs":270,"sat":counts["SAT"],"unsat":counts["UNSAT"],
        "drat_certificates":counts["UNSAT"]*3,
        "control_counts_identical":True,"rotated_scans":rotations
    },sort_keys=True),flush=True)


if __name__=="__main__":main()

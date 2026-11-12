#!/usr/bin/env python3
"""X1 MEMORY1: verified train / frozen-holdout polarity-controller experiment.

Synthetic SHA-disjoint split (NOT family-disjoint and NOT globally unseen).
No solver outcome or holdout result is used to choose the frozen policy.
All claims require independent SAT witness / UNSAT DRUP verification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
import check

HERE = Path(__file__).resolve().parent

def emit(name, row):
    print(name + " " + json.dumps(row, sort_keys=True, separators=(",", ":")), flush=True)

def make_case(i: int):
    rng = random.Random(90120261112 + i * 7907)
    n = 13 + (i * 7) % 19
    kind = ["planted3", "random3", "parity"][i % 3]
    if kind == "parity":
        # Two coupled parity chains with a known final SAT/UNSAT condition.
        from bench import parity_pair
        n, clauses = parity_pair(5 + (i // 3), bool(i % 2))
    else:
        planted = [False] + [bool(rng.randrange(2)) for _ in range(n)]
        clauses = []
        size = (3*n + n//2) if kind == "planted3" else (4*n + n//5)
        for _ in range(size):
            variables = rng.sample(range(1,n+1),3)
            clause = [v * rng.choice((-1,1)) for v in variables]
            if kind == "planted3" and not any(planted[abs(l)] == (l>0) for l in clause):
                clause[0] *= -1
            clauses.append(clause)
    source = f"p cnf {n} {len(clauses)}\n" + "".join(
        " ".join(map(str,clause))+" 0\n" for clause in clauses)
    return {"source":source,"sha256":hashlib.sha256(source.encode()).hexdigest(),
            "kind":kind,"nvars":n,"id":i}

def parse_stats(output):
    for line in output.splitlines():
        if line.startswith("c X1_STATS "):
            return json.loads(line[len("c X1_STATS "):])
    return {}

def trial(binary,cnf,cap,seed,extra,root,tag):
    proof=root/(tag+".proof")
    trace=root/(tag+".jsonl")
    cmd=[str(binary),"--mode","core","--seconds",str(cap),"--seed",str(seed),
         "--proof",str(proof)]
    if "--memory" in extra or "--memory-load" in extra:
        cmd += ["--memory-log",str(trace)]
    cmd+=extra+[str(cnf)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1)
        elapsed=time.monotonic()-start
        if p.returncode not in (0,10,20):
            raise AssertionError(f"native runtime error: {p.returncode} {p.stderr[-800:]}")
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","verified":False,"e2e_s":2*cap,"PAR2":2*cap,"stats":{}}
    status = {0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    checked={"verified":False,"kind":"NOT_SOLVED","check_s":0}
    if status in ("SAT","UNSAT"):
        check_start=time.monotonic()
        try:
            checked=check.verify(cnf,p.stdout,proof,2.0)
        except (TimeoutError,ValueError) as exc:
            checked={"verified":False,"kind":type(exc).__name__}
        checked["check_s"]=time.monotonic()-check_start
    verified=bool(checked["verified"])
    if not verified and status=="SAT":
        raise AssertionError("uncertified SAT witness: "+str(checked))
    stats=parse_stats(p.stdout)
    if status in ("SAT","UNSAT") and not stats:
        raise AssertionError("missing X1 native telemetry")
    if trace.exists():
        events=[json.loads(x) for x in trace.read_text().splitlines()]
        assert events[-1]["event"]=="outcome"
        for e in events[:-1]:
            assert e["event"]=="transition" and "before" in e and "after" in e
            assert e["context"] in range(16)
        assert stats.get("memory_events")==len(events)-1 or stats.get("memory_events",0)>2048
    e2e=elapsed+checked.get("check_s",0)
    return {"status":status,"verified":verified,"solve_s":round(elapsed,6),
            "check_s":round(checked.get("check_s",0),6),"e2e_s":round(e2e,6),
            "PAR2":round(e2e if verified and e2e<=cap else 2*cap,6),
            "stats":stats,"verification":checked.get("kind","unknown")}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-x1"))
    ap.add_argument("--out",type=Path,default=Path("memory1_results"))
    ap.add_argument("--train",type=int,default=18)
    ap.add_argument("--holdout",type=int,default=24)
    ap.add_argument("--repeats",type=int,default=3)
    ap.add_argument("--cap",type=float,default=1.5)
    args=ap.parse_args()
    assert args.train>=4 and args.holdout>=4 and args.repeats>=2 and args.cap>=.5
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    cases=[make_case(i) for i in range(args.train+args.holdout)]
    if len({c["sha256"] for c in cases})!=len(cases):
        raise AssertionError("generated duplicate CNFs")
    train=cases[:args.train];holdout=cases[args.train:]
    memory=args.out/"policy.txt"
    accepted=0
    rows=[]
    with tempfile.TemporaryDirectory(prefix="x1-memory1-") as td:
        root=Path(td)
        for case in train:
            cnf=root/"train.cnf";cnf.write_text(case["source"])
            staged=root/"next-policy.txt"
            options=["--memory","--memory-interval","8","--memory-save",str(staged)]
            if memory.exists(): options+=["--memory-load",str(memory)]
            row=trial(binary,cnf,args.cap,17,options,root,"train")
            # Promotion is controlled by an independent checker, never by X1's UNSAT label.
            if row["verified"] and staged.exists():
                os.replace(staged,memory);accepted+=1
            elif staged.exists():
                staged.unlink()
            emit("X1_MEMORY_TRAIN",{"id":case["id"],"kind":case["kind"],
                "verified":row["verified"],"status":row["status"],
                "events":row["stats"].get("memory_events",0),
                "flips":row["stats"].get("memory_flip_blocks",0)})
        if not memory.exists():
            raise AssertionError("no independently verified training instance")
        policy_before=hashlib.sha256(memory.read_bytes()).hexdigest()
        for case in holdout:
            cnf=root/"holdout.cnf";cnf.write_text(case["source"])
            for rep in range(args.repeats):
                seed=17+rep*13
                for arm,flags in [
                    ("X1_CORE",[]),
                    ("X1_MEMORY_FROZEN",["--memory-load",str(memory),
                         "--memory-frozen","--memory-interval","8"]),
                    ("X1_MEMORY_ONLINE",["--memory-load",str(memory),
                         "--memory-interval","8"])
                ]:
                    trial_row=trial(binary,cnf,args.cap,seed,flags,root,
                                    f"holdout-{arm}-{rep}")
                    row={k:trial_row[k] for k in ("status","verified","solve_s",
                        "check_s","e2e_s","PAR2","verification")}
                    row.update({"id":case["id"],"kind":case["kind"],"nvars":case["nvars"],
                       "sha256":case["sha256"],"rep":rep,"seed":seed,"arm":arm,
                       "decisions":trial_row["stats"].get("decisions"),
                       "conflicts":trial_row["stats"].get("conflicts"),
                       "events":trial_row["stats"].get("memory_events",0),
                       "flipped_blocks":trial_row["stats"].get("memory_flip_blocks",0)})
                    rows.append(row)
                    emit("X1_MEMORY_TRIAL",row)
        assert hashlib.sha256(memory.read_bytes()).hexdigest()==policy_before, "holdout data leaked into persistent training state"
        # The output for a variable-permuted formula should have the same
        # label-free fingerprint, while original CNF identity remains distinct.
        sample=holdout[0]
        perm=list(range(sample["nvars"]+1));perm[1:]=reversed(perm[1:])
        permuted=[]
        for line in sample["source"].splitlines()[1:]:
            permuted.append(" ".join(
                str((1 if int(x)>0 else -1)*perm[abs(int(x))]) if int(x) else "0"
                for x in line.split()))
        left=root/"left.cnf";right=root/"right.cnf"
        left.write_text(sample["source"])
        right.write_text(f"p cnf {sample['nvars']} {len(permuted)}\n"+"\n".join(permuted)+"\n")
        for p in (left,right):
            t=trial(binary,p,args.cap,17,["--memory","--memory-frozen",
                "--memory-load",str(memory),"--memory-interval","8"],root,p.stem)
            assert t["verified"],t
        # Signature check in trace outcomes.
        def signature(prefix):
            x=json.loads((root/(prefix+".jsonl")).read_text().splitlines()[-1])
            return x["signature"]
        assert signature("left")==signature("right"),"renaming changed structural signature"
    summary={}
    for arm in ("X1_CORE","X1_MEMORY_FROZEN","X1_MEMORY_ONLINE"):
        items=[x for x in rows if x["arm"]==arm]
        summary[arm]={"trials":len(items),"verified":sum(x["verified"] for x in items),
            "sat":sum(x["verified"] and x["status"]=="SAT" for x in items),
            "unsat":sum(x["verified"] and x["status"]=="UNSAT" for x in items),
            "PAR2_verified_e2e_s":round(sum(x["PAR2"] for x in items),6),
            "solver_s":round(sum(x["solve_s"] for x in items),6),
            "memory_events":sum(x["events"] for x in items),
            "flipped_blocks":sum(x["flipped_blocks"] for x in items)}
    base=summary["X1_CORE"]["PAR2_verified_e2e_s"]
    mem=summary["X1_MEMORY_FROZEN"]["PAR2_verified_e2e_s"]
    online=summary["X1_MEMORY_ONLINE"]["PAR2_verified_e2e_s"]
    report={"protocol":"synthetic_sha_disjoint_train_holdout_frozen",
        "globally_blind":False,"training_verified_instances":accepted,
        "train_sources":len(train),"holdout_sources":len(holdout),
        "repeats":args.repeats,"cap_s":args.cap,"per_arm":summary,
        "PAR2_speedup_vs_core_x":round(base/max(mem,1e-12),5),
        "PAR2_speedup_online_vs_core_x":round(base/max(online,1e-12),5),
        "holdout_policy_file_unchanged":True,
        "no_unverified_credit":True,"unsat_requires_independent_DRUP":True,
        "structural_rename_test":"PASS"}
    (args.out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    with (args.out/"trials.jsonl").open("w") as f:
        for row in rows:f.write(json.dumps(row,sort_keys=True)+"\n")
    emit("X1_MEMORY_FINAL",report)

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Wide Hall2 signed/permuted UNSAT and SAT near-miss safety tests.

SAT controls are validated with an explicit complete assignment.
Every claimed UNSAT is checked from exact original clauses using a
separate Python certificate checker. No CDCL changes or second solver.
"""
import argparse
import copy
import hashlib
import json
import os
import random
from pathlib import Path
from random_unsat_probe import write_cnf, native_run, satisfied
from check_clause_hall import check, InvalidCertificate

SEED=202611142242

def make_case(rng, width, mode):
    n=width if mode=="SAT_BALANCED" else width+1
    groups=[]
    for row in range(n):
        g=[]
        for col in range(width):
            var=row*width+col+1
            # Both literal signs, independent of row or resource position.
            g.append(var if rng.getrandbits(1) else -var)
        groups.append(g)
    clauses=[tuple(rng.sample(g,len(g))) for g in groups]
    for col in range(width):
        for a in range(n):
            for b in range(a+1,n):
                if mode=="SAT_ONE_MISSING_MUTEX" and col==0 and a==0 and b==1:
                    continue
                clauses.append((-groups[a][col], -groups[b][col]))
    model=None
    if mode.startswith("SAT_"):
        model={}
        for g in groups:
            for lit in g: model[abs(lit)]=(lit<0) # all ALO options initially false
        for row,g in enumerate(groups):
            col=(0 if row<2 else row-1) if mode=="SAT_ONE_MISSING_MUTEX" else row
            lit=g[col]
            model[abs(lit)]=(lit>0)
        assert satisfied(clauses,model),("SAT witness invalid",mode,width)
    # Preserve logical contents but scramble every variable ID and clause order.
    perm=list(range(1,n*width+1))
    rng.shuffle(perm)
    remap={i+1:perm[i] for i in range(n*width)}
    cnf=[tuple(remap[abs(l)] if l>0 else -remap[abs(l)] for l in clause)
         for clause in clauses]
    rng.shuffle(cnf)
    if model is not None:
        model={remap[x]:v for x,v in model.items()}
        assert satisfied(cnf,model)
    return cnf,n*width,model

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--budget-ms",type=int,default=700)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    rng=random.Random(SEED)
    modes=["SAT_BALANCED","SAT_ONE_MISSING_MUTEX","UNSAT_MIXED_SIGN_PERMUTED"]
    rows=[]
    for mode in modes:
        for idx in range(8):
            width=rng.randint(13,29)
            clauses,nvars,model=make_case(rng,width,mode)
            name=f"{mode.lower()}_{idx:02d}_k{width}"
            src=args.out/(name+".cnf")
            cert=args.out/(name+".certificate.json")
            raw=write_cnf(src,clauses,nvars)
            rc,elapsed,tele,stderr=native_run(args.binary,src,cert,args.budget_ms)
            assert rc in (0,20),(name,rc,stderr)
            certified=False
            proof_meta=None
            if rc==20:
                assert cert.exists(),("native claimed UNSAT but no cert",name)
                proof=json.loads(cert.read_text())
                proof_meta=check(raw,proof)
                assert proof_meta["status"]=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED"
                assert model is None,("FALSE UNSAT ON SAT CONTROL",name)
                certified=True
                # Key adversarial: mutate a *source* mutex clause and rehash proof.
                # The independent checker must reject an invalid new instance.
                resources=proof["resource_cliques"]
                resource=next(c for c in resources if len(c)>=2)
                removed=frozenset((-resource[0],-resource[1]))
                mutated=[c for c in clauses if frozenset(c)!=removed]
                assert len(mutated)<len(clauses),(name,"missing original blocking clause")
                tampered=(f"p cnf {nvars} {len(mutated)}\\n"+
                          "".join(" ".join(map(str,c))+" 0\\n" for c in mutated)).encode()
                forged=copy.deepcopy(proof)
                forged["source_sha256"]=hashlib.sha256(tampered).hexdigest()
                try:check(tampered,forged)
                except (InvalidCertificate, ValueError):pass
                else:raise AssertionError(("accepted forged missing binary source",name))
            else:
                assert not cert.exists(),("spurious cert with UNKNOWN",name)
            row={"name":name,"mode":mode,"width":width,"status":"UNSAT_CERTIFIED" if certified else "UNKNOWN",
                 "expected":"SAT" if model is not None else "UNSAT",
                 "reason":tele.get("reason","not_reported"),"seconds":elapsed,
                 "sha256":hashlib.sha256(raw).hexdigest(),"clauses":len(clauses),
                 "certificate":proof_meta}
            rows.append(row)
            print("HALL2_ADVERSARIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={"seed":SEED,"single_cpu":cpu,"total":len(rows),
             "sat_controls":sum(r["expected"]=="SAT" for r in rows),
             "false_unsat":sum(r["expected"]=="SAT" and r["status"]=="UNSAT_CERTIFIED" for r in rows),
             "unsat_certified":sum(r["expected"]=="UNSAT" and r["status"]=="UNSAT_CERTIFIED" for r in rows),
             "unsat_total":sum(r["expected"]=="UNSAT" for r in rows),
             "rows":rows}
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\\n")
    print("HALL2_ADVERSARIAL_SUMMARY "+json.dumps({
        k:summary[k] for k in ("total","sat_controls","false_unsat","unsat_total","unsat_certified")
    },sort_keys=True),flush=True)
    assert summary["false_unsat"]==0
if __name__=="__main__":main()

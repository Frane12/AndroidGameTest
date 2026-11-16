#!/usr/bin/env python3
"""Independent, retrospective TSP-SAT2 proof audit.

Held-Karp appears ONLY here, never in optimization, source selection or proof
generation. Recompute every submitted decision CNF from original coordinates,
re-run independent external DRAT/FRAT/VeriPB checkers for ALL accepted UNSAT
queries, audit every SAT tour, and reject false optimality claims.

A passing audit certifies the generated CNF refutations and a feasible route;
the TSP->CNF encoder is tested but not machine-formally proven.
"""
import collections
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/tsp_sat2"))
import optimizer as o

OUT=o.OUT
CAP_AUDIT_PROOF=40.0

def require(cond,reason):
    if not cond:raise AssertionError("TSP_SAT2_AUDIT_FAIL "+str(reason))

def check_proof(case,trial,step,proofdir):
    B=step["B"]
    metadata=proofdir/f"bound-{B}"/"metadata.json"
    require(metadata.is_file(),("missing verifier evidence",case["name"],B))
    m=json.loads(metadata.read_text())
    require(m["bound"]==B,"bound mismatch")
    path=metadata.parent
    assert step["status"]=="UNSAT_VERIFIED" and step["accepted"]
    require(m["source_sha256"]==step["cnf_sha256"],"source hash differs from run")
    require(m["proof_sha256"]==step["proof_sha256"],"proof hash differs from run")
    cnf=path/"decision.cnf"
    proof=path/m["proof_file"]
    require(cnf.is_file() and proof.is_file(),"proof/CNF files missing")
    require(o.sha(cnf)==m["source_sha256"],"stored CNF changed")
    require(o.sha(proof)==m["proof_sha256"],"stored proof changed")
    with tempfile.TemporaryDirectory(prefix="tsp2-reencode-") as td:
        expected=Path(td)/"expected.cnf"
        producer,meta=o.enc.encode(case["coords"],B)
        producer.output(expected)
        require(o.sha(expected)==o.sha(cnf),"re-generated exact TSP CNF differs")
        require(meta["bound"]==B,"unexpected reconstructed bound")
    kind=m["kind"]
    require(kind in ("DRAT","FRAT","VERIPB_MATH5"),"nonstandard cert credited")
    if kind=="DRAT":
        cmd=[ROOT/"build/drat-trim",cnf,proof]
        expected="VERIFIED"
    elif kind=="FRAT":
        cmd=[ROOT/"build/frat-rs","elab",proof,cnf,"-v"]
        expected="VERIFIED"
    else:
        source_cert=path/"source_cert.json"
        require(source_cert.is_file(),"MATH5 source certificate absent")
        # Separate source check enforces the complete original-CNF premises.
        check=o.run([sys.executable,ROOT/"research/math5/check_math5.py",
             cnf,source_cert],CAP_AUDIT_PROOF)
        require(not check["timeout"] and check["returncode"]==0 and
                "UNSAT_MATH5_CERTIFICATE_VERIFIED" in check["stdout"],
                "source MATH5 certificate rejected")
        cmd=[ROOT/"veripb-tool/bin/veripb","--cnf",cnf,proof]
        expected="s VERIFIED UNSATISFIABLE"
    checked=o.run(cmd,CAP_AUDIT_PROOF)
    require(not checked["timeout"] and checked["returncode"]==0 and
            expected in checked["stdout"]+checked["stderr"],
            ("external checker rejected final proof",case["name"],B,kind,
             checked["stderr"][-250:]))
    return dict(bound=B,kind=kind,sha256=m["proof_sha256"],
        checked_again=True,checker_s=round(checked["wall_s"],6))

def report():
    o.affinity()
    m,p=o.check()
    data=[]
    certified_proofs=[]
    issues=[]
    for i,case in enumerate(m["cases"]):
        resultdir=OUT/f"case-{i}"
        rows=list(map(json.loads,
            (resultdir/"trials.jsonl").read_text().splitlines()))
        require(len(rows)==len(o.ARMS)*o.REPS,"missing case rows")
        data.extend(rows)
        # Independent AFTER-the-fact exact solution; no solver had access to it.
        D=o.enc.euc_distance(case["coords"])
        hk_cost,hk_route=o.enc.held_karp(D)
        require(o.enc.cost(hk_route,D)==hk_cost,"Held-Karp disagreement")
        for row in rows:
            arm=row["arm"]
            rep=row["rep"]
            require(row["name"]==case["name"] and row["n"]==case["n"],
                    "case row mislabelled")
            require(row["source_sha256"]==case["source_sha256"],"source mismatch")
            require(not row["critical"],("critical proof error",row))
            require(row["status"] in ("OPTIMAL_CERTIFIED","FEASIBLE_NOT_CERTIFIED"),
                    "unknown status")
            path=resultdir/f"{arm}-rep{rep}"
            require(json.loads((path/"record.json").read_text())==row,
                    "record differs from full JSONL")
            best=tuple(row["best_route"])
            require(len(best)==case["n"] and set(best)==set(range(case["n"])),
                    "invalid TSP Hamiltonian tour")
            require(best[0]==0,"tour lacks fixed start")
            require(o.enc.cost(best,D)==row["best_cost"],"wrong reported route length")
            require(row["best_cost"]>=hk_cost,"found a route better than exact optimum")
            require(row["final_lower_bound"]<=hk_cost,
                    "unsound claimed lower bound")
            prove=path/"proof"
            observed_bounds=set()
            for step in row["steps"]:
                B=step["B"]
                require(step["status"]!="INVALID_SAT_MODEL" and
                        not step["critical"],"critical SAT result")
                if step["accepted"] and step["status"]=="SAT_VERIFIED":
                    tour=step["model_route"]
                    require(tour is not None and tour[0]==0 and
                            set(tour)==set(range(case["n"])),"invalid SAT step tour")
                    require(o.enc.cost(tour,D)==step["route_cost"]<=B,
                            "SAT witness exceeds TSP budget")
                    require(B>=hk_cost,"SAT claims a solution below Held-Karp")
                if step["accepted"] and step["status"]=="UNSAT_VERIFIED":
                    require(B<hk_cost,"UNSAT claims no route at/above optimum")
                    audit=check_proof(case,row,step,prove)
                    certified_proofs.append(dict(case=case["name"],arm=arm,rep=rep,
                                                 **audit))
                    observed_bounds.add(B)
            certified=row["status"]=="OPTIMAL_CERTIFIED"
            if certified:
                require(row["best_cost"]==hk_cost,
                        ("not actually optimal",case["name"],arm,rep))
                require(row["proof_at_bound"]==row["best_cost"]-1,
                        "missing exact final negation bound")
                require(row["proof_at_bound"] in observed_bounds,
                        "final bound not present in externally reverified proofs")
                md=json.loads((prove/f"bound-{row['proof_at_bound']}"/"metadata.json").read_text())
                require(row["certificate"]==md,"certificate metadata differs")
            else:
                require(row["proof_at_bound"] is None,
                        "unverified optimizer claims a final proof")
            print("TSP_SAT2_AUDIT_CASE "+json.dumps({
                "name":case["name"],"arm":arm,"rep":rep,"held_karp":hk_cost,
                "best":row["best_cost"],"status":row["status"],
                "proofs_reverified":len(observed_bounds)},
                sort_keys=True),flush=True)

    expected={(case["name"],arm,rep) for case in m["cases"] for
              arm in o.ARMS for rep in range(o.REPS)}
    observed={(x["name"],x["arm"],x["rep"]) for x in data}
    require(len(data)==len(expected)==p["trials"] and observed==expected,
            "incomplete or duplicated matrix")
    totals={}
    for arm in o.ARMS:
        selection=[x for x in data if x["arm"]==arm]
        totals[arm]=dict(
            trials=len(selection),
            optimal_certified=sum(x["status"]=="OPTIMAL_CERTIFIED" for x in selection),
            feasible_only=sum(x["status"]=="FEASIBLE_NOT_CERTIFIED" for x in selection),
            total_decision_queries=sum(x["queries"] for x in selection),
            PAR2_case_s=round(sum(
                x["wall_s"] if x["status"]=="OPTIMAL_CERTIFIED" else 2*o.CAP_CASE_S
                for x in selection),6),
            certified_wall_s=round(sum(
                x["wall_s"] for x in selection if x["status"]=="OPTIMAL_CERTIFIED"),6))
    result=dict(status="COMPLETE",trials=len(data),
        independent_Held_Karp_audit=True,
        HK_excluded_during_optimization=True,
        standard_original_CNF_proofs_reverified=len(certified_proofs),
        totals=totals,verified_proofs=certified_proofs,
        cases=[dict(name=c["name"],cities=c["n"],
            held_karp_optimum=o.enc.held_karp(o.enc.euc_distance(c["coords"]))[0])
               for c in m["cases"]],
        caveats=[
            "This is a synthetic seeded small-n research pilot, not a competition benchmark.",
            "The TSP->CNF reduction is independently exhaustively sampled at small n but not machine-formally verified.",
            "The UNSAT standard proof is checked against the generated original decision CNF; the reduction is a separate trusted computation.",
            "Proof-certificate generation and checker are included in search time; audit re-verification is excluded from PAR2."
        ])
    o.save(OUT/"final.json",result)
    print("TSP_SAT2_FINAL "+json.dumps(dict(
        status=result["status"],trials=result["trials"],
        proofs_reverified=len(certified_proofs),cases=result["cases"],
        totals=totals),sort_keys=True),flush=True)

if __name__=="__main__":
    p=__import__("argparse").ArgumentParser()
    p.add_argument("action",choices=("report",))
    a=p.parse_args()
    report()

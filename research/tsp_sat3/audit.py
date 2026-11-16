#!/usr/bin/env python3
"""TSP-SAT3 independent after-the-fact audit.

Do NOT use Held-Karp exact dynamic programming in optimizer or source selection.
Here, and ONLY here, use it to check the claimed optimum. Each mathematical
1-tree lower-bound certificate is independently recomputed via Kruskal, and
each accepted UNSAT bound proof is externally rechecked against an exact
regeneration of the SHA-matched original decision CNF, with symmetry ON/OFF.
"""
import collections
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/tsp_sat3"))
import benchmark as bench
import one_tree
base=bench.base
OUT=bench.OUT

def need(v,message):
    if not v:raise AssertionError("TSP_SAT3_AUDIT_FAIL "+str(message))

def prove_again(case,row,step,folder):
    B=step["B"]
    meta=folder/"proof"/f"bound-{B}"/"metadata.json"
    need(meta.is_file(),("missing original proof",case["name"],row["label"],B))
    m=json.loads(meta.read_text())
    proofdir=meta.parent
    cnf=proofdir/"decision.cnf"
    proof=proofdir/m["proof_file"]
    need(cnf.is_file() and proof.is_file(),"proof or CNF missing")
    need(m["bound"]==B and base.sha(cnf)==step["cnf_sha256"]==
         m["source_sha256"],"proof bound or source SHA mismatch")
    need(base.sha(proof)==step["proof_sha256"]==m["proof_sha256"],
         "proof SHA mismatch")
    with tempfile.TemporaryDirectory(prefix="tsp3-independent-source-") as td:
        independent=Path(td)/"regenerated.cnf"
        expression,info=base.enc.encode(
            case["coords"],B,break_reversal=row["break_reversal"])
        expression.output(independent)
        need(base.sha(independent)==base.sha(cnf),"original TSP/CNF reduction changed")
    kind=m["kind"]
    if kind=="DRAT":
        cmd=[ROOT/"build/drat-trim",cnf,proof]
        token="VERIFIED"
    elif kind=="FRAT":
        cmd=[ROOT/"build/frat-rs","elab",proof,cnf,"-v"]
        token="VERIFIED"
    elif kind=="VERIPB_MATH5":
        cert=proofdir/"source_cert.json"
        need(cert.is_file(),"missing mathematical original-CNF certificate")
        first=base.run([sys.executable,ROOT/"research/math5/check_math5.py",
                   cnf,cert],40)
        need(not first["timeout"] and first["returncode"]==0 and
             "UNSAT_MATH5_CERTIFICATE_VERIFIED" in first["stdout"],
             "MATH5 independent source checker failed")
        cmd=[ROOT/"veripb-tool/bin/veripb","--cnf",cnf,proof]
        token="s VERIFIED UNSATISFIABLE"
    else:
        raise AssertionError("NONSTANDARD_PROOF "+str(kind))
    r=base.run(cmd,40)
    need(not r["timeout"] and r["returncode"]==0 and
         token in r["stdout"]+r["stderr"],
         ("external proof rejected",case["name"],B,kind,r["stderr"][-180:]))
    return dict(B=B,kind=kind,sha256=m["proof_sha256"],sym=row["break_reversal"])

def main():
    bench.check()
    manifest,p=bench.check()
    all_rows=[]
    proof_records=[]
    for i,case in enumerate(manifest["cases"]):
        path=OUT/f"case-{i}"
        rows=[json.loads(v) for v in (path/"trials.jsonl").read_text().splitlines()]
        need(len(rows)==len(bench.ARMS)*bench.REPS,"missing case arms")
        D=base.enc.euc_distance(case["coords"])
        # Only in the independent AFTER-THE-FACT audit.
        exact,_=base.enc.held_karp(D)
        need(case["one_tree_lower"]<=exact,
             "one-tree lower bound violates Held-Karp exact optimum")
        for row in rows:
            label=row["label"];rep=row["rep"]
            solver,mode,sym=bench.ARMS[label]
            folder=path/f"{label}-rep{rep}"
            need(row["arm"]==solver and row["bound_mode"]==mode and
                 row["break_reversal"]==sym,"arm mismatched from protocol")
            need(row["name"]==case["name"] and row["source_sha256"]==case["sha256"],
                 "case mismatch")
            need(json.loads((folder/"record.json").read_text())==row,
                 "trial record changed")
            need(not row["critical"],"critical solver result")
            need(row["status"] in ("OPTIMAL_CERTIFIED","FEASIBLE_NOT_CERTIFIED"),
                 "unknown status string")
            route=row["best_route"]
            need(len(route)==case["n"] and set(route)==set(range(case["n"])) and
                 route[0]==0 and base.enc.cost(route,D)==row["best_cost"],
                 "route invalid or cost drift")
            need(row["best_cost"]>=exact,"proposed route below exact optimum")
            two_opt=base.two_opt(base.nearest_neighbor(D),D)
            U=base.enc.cost(two_opt,D)
            need(U==row["after_two_opt_cost"],"unexpected starting route")
            if mode=="one_tree":
                cert=row["one_tree_certificate"]
                need(type(cert) is dict,"missing one-tree potentials")
                recomputed=one_tree.verify_independent_kruskal(D,cert)
                need(recomputed==cert["one_tree_lower_bound"],
                     "potentials altered")
                need(cert["source_upper_bound"]==U,
                     "invalid one-tree feasible incumbent")
                need(max(recomputed,one_tree.degree_bound(D))
                     ==row["initial_lower_bound"],
                     "claimed initial lower bound isn't verified")
            else:
                need(row["one_tree_certificate"] is None and
                     row["initial_lower_bound"]==base.lower_bound(D),
                     "unexpected baseline lower bound")
            need(row["final_lower_bound"]<=exact,"reported lower bound exceeds exact optimum")
            verified_bounds=set()
            for step in row["steps"]:
                need(not step["critical"],"critical in query log")
                if step["accepted"] and step["status"]=="SAT_VERIFIED":
                    tour=step["model_route"]
                    need(tour is not None and tour[0]==0 and len(tour)==case["n"] and
                         set(tour)==set(range(case["n"])), "invalid SAT witness route")
                    if sym:need(tour[1]<tour[-1],"SAT tour violates reversal break")
                    need(base.enc.cost(tour,D)==step["route_cost"]<=step["B"],
                         "SAT certificate violates tour bound")
                    need(step["B"]>=exact,"SAT witness beats independently verified optimum")
                if step["accepted"] and step["status"]=="UNSAT_VERIFIED":
                    need(step["B"]<exact,"UNSAT denies a feasible optimum")
                    proof_records.append(dict(
                        case=case["name"],label=label,rep=rep,
                        **prove_again(case,row,step,folder)))
                    verified_bounds.add(step["B"])
            complete=row["status"]=="OPTIMAL_CERTIFIED"
            if complete:
                need(row["best_cost"]==exact,"claim of wrong optimal cost")
                need(row["proof_at_bound"]==row["best_cost"]-1 and
                     row["proof_at_bound"] in verified_bounds,
                     "no reverified standard UNSAT proof at exact bound")
                md=json.loads((folder/"proof"/f"bound-{row['proof_at_bound']}"/
                               "metadata.json").read_text())
                need(md==row["certificate"],"final proof metadata mismatch")
            else:
                need(row["proof_at_bound"] is None,
                     "unverified optimality claim")
            all_rows.append(row)
        print("TSP_SAT3_CASE_AUDITED "+json.dumps(
            {"name":case["name"],"cities":case["n"],
             "optimum_checked_Held_Karp":exact,
             "rows":len(rows),
             "optimal_proved":sum(r["status"]=="OPTIMAL_CERTIFIED" for r in rows)},
            sort_keys=True),flush=True)

    expected={(case["name"],label,rep) for case in manifest["cases"]
              for label in bench.ARMS for rep in range(bench.REPS)}
    observed={(x["name"],x["label"],x["rep"]) for x in all_rows}
    need(len(all_rows)==len(expected)==p["trials"] and observed==expected,
         "missing or duplicate trials")
    totals={}
    for label in bench.ARMS:
        selection=[x for x in all_rows if x["label"]==label]
        totals[label]=dict(
            trials=len(selection),
            optimal_certified=sum(x["status"]=="OPTIMAL_CERTIFIED" for x in selection),
            feasible_only=sum(x["status"]=="FEASIBLE_NOT_CERTIFIED" for x in selection),
            queries=sum(x["queries"] for x in selection),
            total_wall_s=round(sum(x["wall_s"] for x in selection),6),
            strict_case_PAR2_s=round(sum(
                x["wall_s"] if x["status"]=="OPTIMAL_CERTIFIED"
                else 2*base.CAP_CASE_S for x in selection),6),
            standard_proofs_rechecked=sum(1 for p in proof_records if p["label"]==label))
    baseline=totals["X59_BASE"]["queries"]
    fast=totals["X59_ONE_TREE"]["queries"]
    fastsym=totals["X59_ONE_TREE_SYM"]["queries"]
    result=dict(status="COMPLETE",trials=len(all_rows),
        totals=totals,standard_proofs_reverified=len(proof_records),
        query_savings_vs_base={
            "one_tree":baseline-fast,
            "one_tree_plus_symmetry":baseline-fastsym},
        cases=[dict(name=c["name"],cities=c["n"],
            one_tree_lower=c["one_tree_lower"],
            upper_from_two_opt=c["two_opt_upper"],
            held_karp_exact_audit_only=base.enc.held_karp(
                base.enc.euc_distance(c["coords"]))[0]) for c in manifest["cases"]],
        limits=[
          "Same previously used TSP-SAT2 seeds; not a source-disjoint blind benchmark",
          "Exact Held-Karp DP used in AFTER-THE-FACT audit only",
          "One-tree bound mathematical valid but is not a standard SAT certificate",
          "Final optimality accepted ONLY with independently reverified DRAT/FRAT/VeriPB at U-1",
          "CNF encoder independently tested, not formally machine-verified"
        ])
    base.save(OUT/"final.json",result)
    print("TSP_SAT3_FINAL "+json.dumps(dict(
        status=result["status"],trials=result["trials"],
        standard_proofs_reverified=result["standard_proofs_reverified"],
        totals=totals,query_savings=result["query_savings_vs_base"],
        cases=result["cases"]),sort_keys=True),flush=True)

if __name__=="__main__":
    main()

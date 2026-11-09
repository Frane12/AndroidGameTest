#!/usr/bin/env python3
"""RIT1: deterministic relation-overlap diagnostics and targeted formula selection.
No SAT/UNSAT claims; source CNF is unchanged. Diagnostic only.
"""
import argparse, collections, csv, importlib.util, json, pathlib

CORE=pathlib.Path(__file__).with_name('drnas_crr1_gf2_scc_rup.py')
spec=importlib.util.spec_from_file_location('crr1_core',CORE)
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

def fingerprint(vs,rhs):
    return (tuple(sorted(vs)),int(rhs))

def inspect(path):
    n,clauses=core.parse(path)
    gf=[fingerprint(*r) for r in core.gf2_rows(clauses)]
    sc=[fingerprint(*r) for r in core.scc_rows(clauses,n)]
    gs=set(gf);ss=set(sc)
    joint=core.eliminate([(set(vs),rhs) for vs,rhs in sorted(gs|ss)])
    joint_only=core.eliminate([(set(vs),rhs) for vs,rhs in sorted(gs)])
    proposed=core.candidate_clauses(joint)
    candidates=proposed[:256]
    proved=[c for c in candidates if core.rup(clauses,c)]
    units=sum(len(c)==1 for c in proved)
    binaries=sum(len(c)==2 for c in proved)
    vars_g=set().union(*(set(vs) for vs,_ in gs)) if gs else set()
    vars_s=set().union(*(set(vs) for vs,_ in ss)) if ss else set()
    overlap_vars=len(vars_g&vars_s)
    same=len(gs&ss)
    opposite=sum((vs,1-rhs) in ss for vs,rhs in gs)
    # This is a *diagnostic* ranking, not a trained prediction of speedup.
    score=10*units+4*binaries+2*overlap_vars+same+5*opposite
    return dict(file=str(path),variables=n,clauses=len(clauses),
                gf2_rows=len(gs),scc_rows=len(ss),exact_relation_overlap=same,
                opposite_relation_overlap=opposite,shared_variables=overlap_vars,
                combined_basis=len(joint),gf2_basis=len(joint_only),
                candidate_lemmas=len(candidates),rup_lemmas=len(proved),
                rup_units=units,rup_binary=binaries,diagnostic_score=score,
                proof='original CNF RUP',outcome='NOT_MEASURED')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('cnf',nargs='+')
    p.add_argument('--json',default='rit1.json')
    p.add_argument('--csv',default='rit1.csv')
    args=p.parse_args()
    rows=[inspect(pathlib.Path(f)) for f in args.cnf]
    rows.sort(key=lambda r:(-r['diagnostic_score'],r['file']))
    pathlib.Path(args.json).write_text(json.dumps(rows,indent=2)+'\n')
    with open(args.csv,'w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    print('RIT1_SUMMARY',json.dumps(dict(formulas=len(rows),with_overlap=sum(r['shared_variables']>0 for r in rows),
         with_rup=sum(r['rup_lemmas']>0 for r in rows),top=rows[:5]),sort_keys=True))
if __name__=='__main__':main()

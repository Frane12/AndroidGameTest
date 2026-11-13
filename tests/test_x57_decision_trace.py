#!/usr/bin/env python3
"""X5.7 decision trace: independent SAT/UNSAT oracle and branch-invariance tests.

All outputs are checked against original CNF truth; UNSAT requires DRAT-trim.
The trace is read by the TEST ONLY, never by the SAT solver.
"""
from __future__ import annotations
import itertools,json,pathlib,random,subprocess,tempfile,math

POLICIES=("vsids","chb","lrb")
ARMS={p:(("build/drnas-x57",False),("build/drnas-x57-decision",False),
        ("build/drnas-x57-decision",True)) for p in POLICIES}

def brute(clauses,n):
    return any(all(any(a[abs(l)-1]==(l>0) for l in c) for c in clauses)
               for a in itertools.product((False,True),repeat=n))

def valid_model(stdout,clauses,n):
    vals={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for word in line[2:].split():
            lit=int(word)
            if lit==0:continue
            if abs(lit)>n or (abs(lit) in vals and vals[abs(lit)]!=(lit>0)):return False
            vals[abs(lit)]=lit>0
    return all(any(vals.get(abs(lit))==(l>0) for lit in c) for c in clauses)

def php(h):
    pigeons=h+1
    lit=lambda i,j:i*h+j+1
    clauses=[[lit(i,j) for j in range(h)] for i in range(pigeons)]
    for i in range(pigeons):
        for j in range(h):
            for k in range(j+1,h):clauses.append([-lit(i,j),-lit(i,k)])
    for j in range(h):
        for i in range(pigeons):
            for k in range(i+1,pigeons):clauses.append([-lit(i,j),-lit(k,j)])
    return pigeons*h,clauses

def run(formula,clauses,n,sat,policy,binary,trace,td,cap=7):
    proof=td/"one.drat"
    output=td/"decision.jsonl"
    proof.unlink(missing_ok=True);output.unlink(missing_ok=True)
    cmd=[binary,str(formula),"--mode","core","--time",str(cap),
         "--stats","--x52-proof-deletions","--x53-policy","baseline",
         "--x57-branch",policy,"--proof",str(proof)]
    if trace:cmd+=["--x57-decision-trace",str(output)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+4)
    assert p.returncode==(10 if sat else 20),(policy,binary,trace,p.returncode,p.stderr[-500:])
    if sat:
        assert valid_model(p.stdout,clauses,n),(policy,"SAT witness incorrect")
    else:
        ck=subprocess.run(["build/drat-trim",str(formula),str(proof)],
                          capture_output=True,text=True,timeout=8)
        assert ck.returncode==0 and "s VERIFIED" in ck.stdout,(policy,"UNSAT proof rejected",ck.stdout[-400:])
    native={}
    for line in p.stderr.splitlines():
        if line.startswith("X41_STATS "):native=json.loads(line.split(" ",1)[1])
    assert native,("missing frozen counters")
    if trace:
        assert output.exists() and output.stat().st_size>0
        lines=[json.loads(line) for line in output.read_text().splitlines()]
        meta,decisions=lines[0],lines[1:]
        assert meta["type"]=="meta"
        assert meta["schema"]=="x57-decision-trace-v1" and meta["policy"]==policy.upper()
        assert meta["observational_only"] and meta["counterfactual_known"] is False
        assert meta["results_externally_verified"] is False
        assert meta["internal_result"]==("SAT" if sat else "UNSAT")
        assert meta["rows_retained"]==len(decisions)
        assert meta["total_decisions"]==native["decisions"]
        assert len(decisions)<=meta["max_rows"]==8192
        prev=0
        for d in decisions:
            assert d["type"]=="decision" and d["decision_id"]>prev
            prev=d["decision_id"]
            assert 1<=d["chosen_variable"]<=n
            assert abs(d["chosen_literal"])==d["chosen_variable"]
            assert d["phase_sign"]==(1 if d["chosen_literal"]>0 else -1)
            assert math.isfinite(d["score_at_selection"])
            assert d["decision_id"]<=4096 or d["decision_id"]%512==0
            assert d["is_causal_effect_known"] is False
            if d["immediate_bcp_result"] in ("conflict","no_conflict","timeout"):
                assert d["immediate_bcp_propagations"]>=1
                assert d["immediate_bcp_implied"]>=0
                assert d["elapsed_after_bcp_s"]>=d["elapsed_before_s"]
            else:
                assert d["immediate_bcp_result"]=="not_observed"
            if d["immediate_conflict_learned_lbd"]>=0:
                assert d["immediate_bcp_result"]=="conflict"
                assert d["immediate_conflict_learned_size"]>=1
        return native,decisions
    assert not output.exists()
    return native,[]

def main():
    rng=random.Random(571713)
    sources=[]
    for i in range(43):
        n=5+i%6
        c=[]
        for k in range(2*n+(i%20)):
            vs=rng.sample(range(1,n+1),min(n,2+(i+k)%3))
            c.append([v if rng.randrange(2) else -v for v in vs])
        if i%13==0:c.extend([[1],[-1]])
        sources.append((n,c,brute(c,n),f"random_{i}"))
    for h in (3,4,5):
        n,c=php(h)
        sources.append((n,c,False,"PHP"+str(h)))
    totals={"SAT":0,"UNSAT":0,"rows":0,"direct_conflicts":0,"direct_with_lbd":0}
    with tempfile.TemporaryDirectory() as tmp:
        td=pathlib.Path(tmp);f=td/"example.cnf"
        for n,c,sat,name in sources:
            f.write_text(f"p cnf {n} {len(c)}\n"+
                         "".join(" ".join(map(str,cl))+" 0\n" for cl in c))
            totals["SAT" if sat else "UNSAT"]+=1
            for policy in POLICIES:
                pairs=[]
                for binary,trace in ARMS[policy]:
                    pairs.append(run(f,c,n,sat,policy,binary,trace,td))
                for metric in ("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations"):
                    assert len({s[0][metric] for s in pairs})==1,(name,policy,metric,[s[0][metric] for s in pairs])
                observations=pairs[-1][1]
                totals["rows"]+=len(observations)
                totals["direct_conflicts"]+=sum(x["immediate_bcp_result"]=="conflict" for x in observations)
                totals["direct_with_lbd"]+=sum(x["immediate_conflict_learned_lbd"]>=0 for x in observations)
    assert totals["SAT"]>0 and totals["UNSAT"]>0
    assert totals["rows"]>0 and totals["direct_conflicts"]>0 and totals["direct_with_lbd"]>0,totals
    print("X57_TRACE_SELFTEST_PASS "+json.dumps({
        "sources":len(sources),"executions":len(sources)*len(POLICIES)*3,
        "SAT":totals["SAT"],"UNSAT":totals["UNSAT"],
        "independent_Drat_checks":totals["UNSAT"]*len(POLICIES)*3,
        "frozen_vs_trace_on_off_search_equal":True,
        "sampled_decision_rows":totals["rows"],
        "direct_conflicts_sampled":totals["direct_conflicts"],
        "direct_learned_clauses_sampled":totals["direct_with_lbd"]
    },sort_keys=True),flush=True)

if __name__=="__main__":main()

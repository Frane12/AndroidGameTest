#!/usr/bin/env python3
"""Proof-first DELTAX conflict-depth test on fully constructed SAT CNFs.

Strictly separate:
  1) independent synchronous unit-propagation WAVE depth and conflict depth
     of original CNF vs addition of a source-RUP one-step resolvent;
  2) actual native-CDCL decisions, conflicts, proof checks and
     DELTAX-origin reason-enqueue events from SAME binary JOIN/SHADOW/ON.
Synchronous wave count is NOT solver runtime, a decision saved, or a new
logical deduction beyond standard BCP closure.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research/drnas_deltax"))
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"tests"))

from conflict_depth_formulas import write
from test_drnas_coop52 import oracle,model_ok
from test_drnas_deltacoop2 import bcp,check_rup
from test_drnas_deltax import validate_alias,canon

BIN=R/"build/drnas-deltax-causal"
CHECK=R/"build/drat-trim"
ARMS=("join","deltax-shadow","deltax")

def clauses_for(path):
    current=[]
    out=[]
    for line in path.read_text().splitlines():
        if not line.strip() or line[0] in ("p","c"):continue
        for x in line.split():
            l=int(x)
            if l:current.append(l)
            else:
                out.append(current)
                current=[]
    assert not current
    return out

def wave_bcp(clauses,assumptions,watch=None):
    """Synchronous parallel unit propagation: snapshot literals per wave.

    Count wave at which watch is assigned or at which a conflict is detected.
    Wave zero is the input assumptions, not a completed full BCP closure.
    """
    values={}
    for lit in assumptions:
        var=abs(lit)
        b=lit>0
        if var in values and values[var]!=b:
            return {"conflict_wave":0,"watch_wave":None,"assigned":len(values)}
        values[var]=b
    observed=0 if watch is not None and values.get(abs(watch))==(watch>0) else None
    for wave in range(256):
        pending={}
        for c in clauses:
            if any(abs(l) in values and values[abs(l)]==(l>0) for l in c):
                continue
            free=[l for l in c if abs(l) not in values]
            if not free:
                return {"conflict_wave":wave,"watch_wave":observed,
                        "assigned":len(values)}
            if len(free)==1:
                lit=free[0]
                v=abs(lit)
                b=lit>0
                if v in pending and pending[v]!=b:
                    return {"conflict_wave":wave+1,"watch_wave":observed,
                            "assigned":len(values)}
                pending[v]=b
        if not pending:
            return {"conflict_wave":None,"watch_wave":observed,
                    "assigned":len(values)}
        for v,b in pending.items():
            values[v]=b
            if watch is not None and abs(watch)==v and b==(watch>0):
                observed=wave+1
    raise AssertionError("WAVE_PROPAGATION_NONTERMINATING")

def derive_short(case,clauses):
    role=case["role"]
    a,z,g,b=(role[v] for v in (1,2,4,5))
    left=[-a,-z,b]
    right=[-a,z,g]
    reverse=[a,-b]
    originals={canon(c) for c in clauses}
    assert all(canon(c) in originals for c in (left,right,reverse)),(
        "MISSING_PINNED_MOTIF",case["name"])
    consequent=[-a,g,b]
    assert canon(consequent) not in originals,("ALREADY_ORIGINAL",case["name"])
    assert bcp(clauses,[-x for x in consequent]) is None,(
        "ORIGINAL_SOURCE_RUP_FAILED",case["name"])
    return consequent

def test_waves(case,clauses):
    if case["group"]=="negative":
        return None
    role=case["role"]
    a,b,g1,g2=(role[v] for v in (1,5,3,4))
    derived=derive_short(case,clauses)
    assume=[-g1,-g2,a]
    base=wave_bcp(clauses,assume,watch=b)
    new=wave_bcp(clauses+[derived],assume,watch=b)
    assert base["conflict_wave"] is None and new["conflict_wave"] is None
    assert new["watch_wave"] is not None and base["watch_wave"] is not None
    assert new["watch_wave"]<=base["watch_wave"],("NO_SAFE_DEPTH_BOUNDS",case["name"])
    conflict_assume=assume+[-b]
    bconf=wave_bcp(clauses,conflict_assume)
    nconf=wave_bcp(clauses+[derived],conflict_assume)
    assert bconf["conflict_wave"] is not None
    assert nconf["conflict_wave"] is not None
    assert nconf["conflict_wave"]<=bconf["conflict_wave"]
    result={"original_forward_wave":base["watch_wave"],
            "with_proved_clause_forward_wave":new["watch_wave"],
            "original_conflict_wave":bconf["conflict_wave"],
            "with_proved_clause_conflict_wave":nconf["conflict_wave"]}
    if case["group"]=="selector_trap":
        # Independent branch assumption, NOT a native CDCL decision.
        sel=6
        trap=wave_bcp(clauses,[sel])
        trapplus=wave_bcp(clauses+[derived],[sel])
        assert trap["conflict_wave"] is not None
        assert trapplus["conflict_wave"] is not None
        assert trapplus["conflict_wave"]<=trap["conflict_wave"]
        result["trap_branch_original_conflict_wave"]=trap["conflict_wave"]
        result["trap_branch_new_conflict_wave"]=trapplus["conflict_wave"]
    return result

def native_trial(case,clauses,mode,root):
    source=R/case["path"]
    expected=oracle(case["n"],clauses)
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"proof.drat"
        cmd=[str(BIN),str(source),"--mode","core","--time","2.0",
             "--stats","--x5-no-minimize","--coop4","gate",
             "--coop4-eager","--coop5","off","--delta2",mode,
             "--proof",str(proof)]
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=4.5)
        assert p.returncode==(10 if expected else 20),(
            "ORACLE_MISMATCH",case["name"],mode,p.returncode,p.stderr[-600:])
        if p.returncode==10:
            assert model_ok(case["n"],clauses,p.stdout)
        else:
            q=subprocess.run([str(CHECK),str(source),str(proof)],
                capture_output=True,text=True,timeout=20)
            assert q.returncode>=0 and "s VERIFIED" in q.stdout,(
                "INVALID_ORIGINAL_UNSAT_PROOF",case["name"],mode,
                q.stdout[-300:],q.stderr[-300:])
        assert proof.exists()
        additions=check_rup(clauses,proof)
        events=[]
        caused=[]
        labels={}
        for line in p.stderr.splitlines():
            tag,sep,data=line.partition(" ")
            if tag=="DELTAX_ALIAS":
                evt=json.loads(data)
                validate_alias(evt,{canon(c) for c in clauses})
                assert evt["installed"]==(mode=="deltax")
                events.append(evt)
            elif tag=="DELTAX_CAUSAL_PROPAGATION":
                caused.append(json.loads(data))
            elif tag in ("DELTAX_STATS","DELTAX_CAUSAL_STATS","X41_STATS"):
                assert tag not in labels,("DUPLICATE_LABEL",tag)
                labels[tag]=json.loads(data)
        assert all(tag in labels for tag in ("DELTAX_STATS",
                    "DELTAX_CAUSAL_STATS","X41_STATS")),(
                        "MISSING_DIAGNOSTIC",case["name"],mode)
        ds=labels["DELTAX_STATS"];cs=labels["DELTAX_CAUSAL_STATS"]
        cd=labels["X41_STATS"]
        assert ds["mode"]==mode
        assert len(caused)<=cs["real_enqueues_with_deltax_reason"]
        if mode!="deltax":
            assert not caused and cs["real_enqueues_with_deltax_reason"]==0
            assert ds["proof_carrying_injected"]==0
        else:
            assert len(events)<=ds["proof_carrying_injected"]
            derived={canon(e["forward"]) for e in events}
            for event in caused:
                assert canon(event["reason_clause"]) in derived
                assert event["literal"] in event["reason_clause"]
        result={
            "name":case["name"],"group":case["group"],"mode":mode,
            "sha256":case["sha256"],
            "status":"SAT_VERIFIED" if p.returncode==10 else "UNSAT_CERTIFIED",
            "decisions":cd["decisions"],
            "conflicts":cd["conflicts"],
            "witnesses":ds["witnesses"],
            "alias_events_checked":len(events),
            "source_rup_clauses_installed":ds["proof_carrying_injected"],
            "deltax_causal_enqueues":cs["real_enqueues_with_deltax_reason"],
            "reason_analysis_uses":ds["cdcl_reason_uses"],
            "conflict_reason_uses":ds["cdcl_conflict_uses"],
            "original_rup_additions_checked":additions,
        }
        (root/(case["name"]+"-"+mode+".json")).write_text(json.dumps({
            "trial":result,"alias_events":events,"causal_events":caused,
        },indent=2,sort_keys=True)+"\n")
        print("DELTAX_DEPTH1_TRIAL",json.dumps(result,sort_keys=True),flush=True)
        return result

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=write("deltax_depth1_inputs")
    root=Path("deltax_depth1_results")
    root.mkdir(parents=True,exist_ok=True)
    waves={}
    rows=[]
    for case in cases:
        clauses=clauses_for(R/case["path"])
        waves[case["name"]]=test_waves(case,clauses)
        for mode in ARMS:
            rows.append(native_trial(case,clauses,mode,root))
    assert len(rows)==len(cases)*3
    pos=[r for r in rows if r["mode"]=="deltax" and r["group"]!="negative"]
    neg=[r for r in rows if r["mode"]=="deltax" and r["group"]=="negative"]
    assert all(r["alias_events_checked"]==0 for r in neg),(
        "NEGATIVE_CONTROL_FALSE_ALIAS",neg)
    injected=sum(r["source_rup_clauses_installed"] for r in pos)
    causal=sum(r["deltax_causal_enqueues"] for r in pos)
    advances=sum(x["with_proved_clause_forward_wave"]<x["original_forward_wave"]
                 for x in waves.values() if x)
    earlier_conflicts=sum(x["with_proved_clause_conflict_wave"]<
                          x["original_conflict_wave"] for x in waves.values() if x)
    trap_advances=sum(x.get("trap_branch_new_conflict_wave",1000)<
                      x.get("trap_branch_original_conflict_wave",1000)
                      for x in waves.values() if x and "trap_branch_original_conflict_wave" in x)
    stats={
        "status":"COMPLETE",
        "sources":len(cases),"trials":len(rows),
        "positive":len(pos),"negative_controls":len(neg),
        "independently_source_rup_guarded_lemmas":injected,
        "true_cdcl_enqueues_with_deltax_reason":causal,
        "forward_wave_improvements":advances,
        "earlier_conflict_wave_cases":earlier_conflicts,
        "selector_trap_branch_conflict_improvements":trap_advances,
        "negative_false_aliases":sum(r["alias_events_checked"]>0 for r in neg),
        "all_full_original_sat_unsat_proofs_checked":True,
        "three_way_same_binary_control":True,
        "wave_depth_is_not_solver_decision_savings":True,
        "no_speed_claim":True,"promotion":False,
    }
    (root/"wave_diagnostics.json").write_text(json.dumps(waves,indent=2,sort_keys=True)+"\n")
    (root/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (root/"report.json").write_text(json.dumps(stats,indent=2,sort_keys=True)+"\n")
    print("DELTAX_DEPTH1_FINAL",json.dumps(stats,sort_keys=True),flush=True)
    assert advances>0 and earlier_conflicts>0,("NO_SEMANTIC_DIFFERENCE",stats)
    assert injected>0 and causal>0,("NO_ACTUAL_CDCL_USE",stats)

if __name__=="__main__":
    main()

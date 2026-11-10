#!/usr/bin/env python3
"""COMBO6: bounded native original-CNF UP novelty *proxy*, not live CDCL trail.
Reuses COMBO5 independently replayed GF(2) relation proof and 29 frozen
source SHA. This cohort is NOT globally blind. No automatic promotion.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,subprocess,tempfile,time
import drnas_combo5_short_relations as base
import drnas_gf2_proof_first_s1 as s1
import drnas_binary_scc2_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_combo6")
NATIVE=ROOT/"bin/smartgate"
ARMS=("cms_plain","cms_prooffirst","cms_pair2",
      "cms_gate","cms_gate_placebo","kissat_plain")
PROTO="DRNAS-COMBO6-NATIVE-UP-GATED-XOR2-SHA29-6ARM-2REP-10S-v1"
GATE_SCAN_CAP=0.28
GATE_NATIVE_CAP=0.14
GATE_PREPASS_CAP=0.5
GATE_MIN_USEFUL=2
original_signature=base.signature
original_one=base.one

base.ROOT=ROOT
base.PROTO=PROTO
base.ARMS=ARMS
base.EXPECTED=base.N*len(ARMS)*base.REPS

def signature():
    p=original_signature()
    p.update(combo6_py=base.sha(__file__),
             combo6_cpp=base.sha("research/drnas_combo6_smartgate_up.cpp"),
             combo6_native=base.sha(NATIVE))
    return p
base.signature=signature

def scan_gate(original):
    start=time.perf_counter()
    empty=dict(proofs=[],scan_s=0,roots=0,reason="gate_scan_abstain",
               candidates=0,strict_pairs=0)
    cmd=["python3",str(pathlib.Path(base.__file__).resolve()),
         "scan",str(original.resolve()),"pair"]
    try:
        p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=GATE_SCAN_CAP)
    except (subprocess.TimeoutExpired,OSError):
        return dict(empty,reason="gate_scanner_time_bound",
                    scan_s=round(time.perf_counter()-start,6))
    if p.returncode:
        return dict(empty,reason="gate_scanner_fail_closed",
                    scan_s=round(time.perf_counter()-start,6))
    lines=[x[len("COMBO5_RELATION_RESULT "):] for x in p.stdout.splitlines()
           if x.startswith("COMBO5_RELATION_RESULT ")]
    if len(lines)!=1:
        return dict(empty,reason="gate_scanner_invalid_output",
                    scan_s=round(time.perf_counter()-start,6))
    try:
        record=json.loads(lines[0])
        verified=base.verify_candidates(original,record["selected"]) if record["selected"] else []
    except Exception:
        return dict(empty,reason="gate_Gf2_replay_failed_closed",
                    scan_s=round(time.perf_counter()-start,6))
    return dict(proofs=verified,scan_s=round(time.perf_counter()-start,6),
                roots=record["roots"],reason=record["reason"],
                candidates=len(record["selected"]),
                strict_pairs=record.get("strict_pair",0),
                novel_binary_pairs=record.get("novel_binary_pairs",0))

def native_probe(original,proofs):
    start=time.perf_counter()
    empty=dict(probes=0,useful_probes=0,new_units=0,new_conflicts=0,
               budget_exceeded=True,reason="native_abstain",probe_s=0.0)
    if not proofs:return dict(empty,reason="no_proofs")
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        rel=pathlib.Path(folder)/"relations.txt"
        rel.write_text("".join(f"{rhs} {' '.join(map(str,vs))} 0\n"
                               for vs,rhs in proofs))
        try:
            p=subprocess.run([str(NATIVE.resolve()),str(original.resolve()),str(rel)],
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     timeout=GATE_NATIVE_CAP)
        except (OSError,subprocess.TimeoutExpired):
            return dict(empty,reason="native_timeout",
                        probe_s=round(time.perf_counter()-start,6))
    if p.returncode:return dict(empty,reason="native_failed_closed",
                                     probe_s=round(time.perf_counter()-start,6))
    lines=[x[len("COMBO6_PROBE "):] for x in p.stdout.splitlines()
           if x.startswith("COMBO6_PROBE ")]
    if len(lines)!=1:return dict(empty,reason="native_bad_output",
                                probe_s=round(time.perf_counter()-start,6))
    try:
        result=json.loads(lines[0])
        base.need(all(k in result for k in
              ("probes","useful_probes","new_units","new_conflicts",
               "budget_exceeded","reason")),"native missing probe fields")
        return dict(result,probe_s=round(time.perf_counter()-start,6))
    except Exception:
        return dict(empty,reason="native_parse_abstain",
                    probe_s=round(time.perf_counter()-start,6))

def selftest():
    base.selftest()
    with tempfile.TemporaryDirectory(prefix="combo6-up-") as folder:
        original=pathlib.Path(folder)/"original.cnf"
        # Complete original XOR(1,2,3)=0 and XOR(1,2,4)=1.
        def eq(vs,rhs):
            return [tuple(-v if mask>>i&1 else v for i,v in enumerate(vs))
                    for mask in range(1<<len(vs)) if mask.bit_count()%2!=rhs]
        clauses=eq((1,2,3),0)+eq((1,2,4),1)
        original.write_text(f"p cnf 4 {len(clauses)}\n"+
           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        verified=base.scan(original,"pair")["proofs"]
        base.need(any(set(vs)=={3,4} and rhs==1 for vs,rhs in verified),
                  "native test missing proven relation")
        measure=native_probe(original,verified)
        base.need(not measure["budget_exceeded"] and measure["useful_probes"]>=2,
                  "bounded native UP toy novelty check failed")
        bad=pathlib.Path(folder)/"incomplete.cnf"
        badclauses=clauses[:-1]
        bad.write_text(f"p cnf 4 {len(badclauses)}\n"+
           "".join(" ".join(map(str,c))+" 0\n" for c in badclauses))
        base.need(not base.scan(bad,"pair")["proofs"],
                  "incomplete CNF fooled proof replay")
    print("COMBO6_SELFTEST_PASS "+json.dumps(measure,sort_keys=True),flush=True)

def freeze():
    base.need(NATIVE.is_file(),"native binary missing")
    base.freeze()
    m=base.read(ROOT/"manifest.json")
    m.update(gate_scan_cap_s=GATE_SCAN_CAP,gate_native_cap_s=GATE_NATIVE_CAP,
             gate_total_prepass_cap_s=GATE_PREPASS_CAP,
             gate_min_useful_probes=GATE_MIN_USEFUL,
             gate_is_preCDCL_UP_proxy_NOT_live_trail=True,
             no_outcome_SHA_training=True,not_globally_blind=True)
    base.save(ROOT/"manifest.json",m);verify()
    print("COMBO6_FROZEN "+json.dumps(dict(original_sha=base.N,
          arms=len(ARMS),trials=base.EXPECTED,globally_blind=False),sort_keys=True),
          flush=True)

def verify():
    m=base.verify()
    base.need(m["gate_scan_cap_s"]==GATE_SCAN_CAP and
        m["gate_native_cap_s"]==GATE_NATIVE_CAP and
        m["gate_total_prepass_cap_s"]==GATE_PREPASS_CAP and
        m["gate_min_useful_probes"]==GATE_MIN_USEFUL and
        m["gate_is_preCDCL_UP_proxy_NOT_live_trail"] and
        m["no_outcome_SHA_training"],"gate configuration drift")
    return m

def one(c,rep,arm):
    if arm not in ("cms_gate","cms_gate_placebo"):
        result=original_one(c,rep,arm)
        return dict(result,gate_reason="not_used",gate_probe_s=0.0,
                    gate_up_novel=0,gate_up_new_units=0)
    base.need(rep in range(base.REPS) and arm in ARMS,"invalid gate trial")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    start=time.perf_counter();parent_cpu=time.process_time()
    child_cpu=e9.x22.child_cpu()
    original=base.src(c)
    proof=s1.scan(original)
    shortcut=bool(proof["proved"])
    relations=[];state=None;probe=None
    gate_reason="original_GF2_shortcut" if shortcut else "no_verified_relation"
    if not shortcut:
        state=scan_gate(original)
        if not state["proofs"]:
            gate_reason=state["reason"]
        elif time.perf_counter()-start>=GATE_PREPASS_CAP:
            gate_reason="prepass_budget_before_UP"
        else:
            probe=native_probe(original,state["proofs"])
            if probe["budget_exceeded"]:
                gate_reason="native_abstain_"+probe["reason"]
            elif probe["useful_probes"]<GATE_MIN_USEFUL:
                gate_reason="insufficient_novel_UP"
            elif time.perf_counter()-start>=GATE_PREPASS_CAP:
                gate_reason="prepass_budget_after_UP"
            else:
                gate_reason="UP_novelty_approved"
                if arm=="cms_gate":relations=state["proofs"]
    status="UNSAT" if shortcut else "TIMEOUT";witness=False;backend=False
    if not shortcut:
        remaining=base.CAP-(time.perf_counter()-start)
        if remaining>.09:
            backend=True
            if relations:
                with tempfile.TemporaryDirectory(dir=ROOT) as folder:
                    altered=pathlib.Path(folder)/"augmented.cnf"
                    base.augmented_cnf(original,altered,relations)
                    remaining=base.CAP-(time.perf_counter()-start)
                    if remaining>.09:status,witness=base.cms(original,altered,remaining)
            else:
                status,witness=base.cms(original,original,remaining)
    wall=time.perf_counter()-start
    if wall>=base.CAP:status="TIMEOUT";witness=False
    base.need(status!="SAT" or witness,"invalid original SAT model")
    base.need(base.sha(original)==c["sha256"],"original SHA drift")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
       cohort=c["source_cohort"],arm=arm,rep=rep,cap_s=base.CAP,
       one_logical_CPU=cpu,one_backend_child_max=True,original_SHA_verified=True,
       status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
       UNSAT_original_GF2_certified=shortcut,UNSAT_standard_LRAT_from_backend=False,
       gf2_cert_terms=proof["proof"]["terms"] if shortcut else 0,
       GF2_original_equations=proof["equations"],
       source_complete_XOR_roots=state["roots"] if state else None,
       candidate_rels=state["candidates"] if state else 0,
       independent_original_GF2_derived_rels=len(state["proofs"]) if state else 0,
       appended_short_rels=len(relations),
       appended_entailed_clauses=sum(1<<(len(vs)-1) for vs,rhs in relations),
       strict_pair_candidates=state.get("strict_pairs",0) if state else 0,
       novel_binary_pair_count=state.get("novel_binary_pairs",0) if state else 0,
       scan_reason=state["reason"] if state else "no_pair_scan",
       gate_reason=gate_reason,gate_probe_s=probe["probe_s"] if probe else 0,
       gate_up_novel=probe["useful_probes"] if probe else 0,
       gate_up_new_units=probe["new_units"] if probe else 0,
       gate_up_new_conflicts=probe["new_conflicts"] if probe else 0,
       original_proof_scan_s=proof["probe_wall_s"],
       short_relation_scan_s=state["scan_s"] if state else 0,
       backend_called=backend,wall_E2E_s=round(wall,6),
       actual_parent_CPU_s=round(time.process_time()-parent_cpu,6),
       actual_child_CPU_s=round(e9.x22.child_cpu()-child_cpu,6))

base.one=one

def shard(index):
    base.need(index in range(base.SHARDS),"invalid shard")
    m=verify()
    cases=[c for i,c in enumerate(m["cases"]) if i%base.SHARDS==index]
    rows=[]
    for c in cases:
        for rep in range(base.REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"COMBO6").shuffle(order)
            for arm in order:
                row=one(c,rep,arm);row["shard"]=index
                base.need(row["wall_E2E_s"]<=base.CAP+0.2,"cap violation")
                rows.append(row);base.save(ROOT/f"shard-{index}.json",rows)
                print("COMBO6_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    base.need(len(rows)==len(cases)*base.REPS*len(ARMS),"missing trial")
    print(f"COMBO6_SHARD_PASS {index} {len(rows)}",flush=True)

def audit():
    verify()
    base.audit()
    report=base.read(ROOT/"report.json")
    rows=[r for i in range(base.SHARDS) for r in base.read(ROOT/f"shard-{i}.json")]
    gate_rows=[r for r in rows if r["arm"].startswith("cms_gate")]
    report["gate_diagnostics"]=dict(
         gate_approved=sum(r["gate_reason"]=="UP_novelty_approved" for r in gate_rows),
         gate_rejected=sum(r["gate_reason"]!="UP_novelty_approved" for r in gate_rows),
         native_UP_new_units=sum(r.get("gate_up_new_units",0) for r in gate_rows),
         native_UP_novel_probes=sum(r.get("gate_up_novel",0) for r in gate_rows),
         total_native_probe_s=round(sum(r.get("gate_probe_s",0) for r in gate_rows),6),
         reasons=dict(collections.Counter(r["gate_reason"] for r in gate_rows)),
         does_NOT_observe_live_CDCL_trail=True)
    report["gate_is_preCDCL_UP_proxy_NOT_live_trail"]=True
    report["gate_uses_no_outcome_or_SHA_training"]=True
    base.save(ROOT/"report.json",report)
    print("COMBO6_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    elif a.action=="verify":verify();print("COMBO6_VERIFY_PASS",flush=True)
    else:globals()[a.action]()

if __name__=="__main__":main()

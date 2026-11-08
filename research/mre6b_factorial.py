#!/usr/bin/env python3
"""DRNAS MRE6b: 2x2 causal CPU factorial to separate variable quotient from XOR effects.

Same SAT2026 original and *same four native seeds* used in MRE6.
Four cells:
  original without imported source XORs
  original with certified source XORs
  certified equality quotient without imported source XORs
  certified equality quotient with transformed source XORs

Two trace-OFF timings + one trace-ON watcher probe per seed per cell.
Matched four-way CPU differences plus difference-in-differences isolate
how the quotient effect interacts with CMS source XOR import.

This is a confirmation/diagnostic ablation on used seeds, NOT a blind holdout.
"""
from __future__ import annotations

import argparse,collections,json,pathlib,random,sqlite3,statistics,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre4_trace_pilot as mre4
import mre6_pilot as pilot
import mre1_cross_representation as mre1

PROTO="DRNAS-MRE6B-2X2-EQUIV-XOR-CPU-INTERACTION-v1"
ROOT=pathlib.Path("mre6b")
MODES=("native_no_xor","xor","quotient_no_xor","quotient")
CAP=26.0

def need(b,msg):
    if not b:raise RuntimeError("MRE6B_FAIL_CLOSED "+str(msg))

def shard(seed_index,binary):
    need(seed_index in range(4),"seed index")
    shared=mre4.setup()
    case,source,n,original,rows,proofs,selected,tags=shared
    with tempfile.TemporaryDirectory(prefix="mre6b-factorial-") as td:
        work=pathlib.Path(td)
        variants,meta=pilot.make_sources(shared,work)
        cnf=work/"original-no-xor.cnf"
        xor=work/"empty-source-xor.tsv"
        mre1.write_cnf(cnf,n,original,[])
        xor.write_text("")
        variants["native_no_xor"]=dict(
            cnf=cnf,xor=xor,clauses=len(original),source_rows=0,
            imported=0,quotient=False,original=True,base_count=len(original))
        records=[]
        for rep in range(2):
            specs=[(m,0) for m in MODES]
            if rep==0: specs += [(m,1) for m in MODES]
            random.Random(PROTO+str(seed_index)+":"+str(rep)).shuffle(specs)
            for mode,tr in specs:
                row=pilot.one(shared,variants,meta["principle"],
                    seed_index,rep,mode,tr,binary)
                need(row["protocol"]==pilot.PROTO,"unexpected pilot protocol")
                row["protocol"]=PROTO
                records.append(row)
                ROOT.mkdir(parents=True,exist_ok=True)
                (ROOT/("seed-%d.json"%seed_index)).write_text(
                    json.dumps(records,sort_keys=True)+"\n")
                print("MRE6B_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(records)==12,"incomplete factorial block")
    print("MRE6B_SHARD_PASS",seed_index,12,flush=True)

def audit():
    rows=[]
    for i in range(4):
        f=ROOT/("seed-%d.json"%i)
        need(f.exists(),"missing factorial shard")
        rows+=json.loads(f.read_text())
    need(len(rows)==48,"expected 48 source-paired trial records")
    by=collections.defaultdict(dict)
    modes=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["status"]=="SAT" and
             r["original_sat_witness_verified"] and r["otf_gauss"] is False,
             "SAT model or OTF failed")
        key=(r["source_sha256"],r["seed"],r["repeat"])
        ident=(r["mode"],r["trace_enabled"])
        need(ident not in by[key],"duplicate mode")
        by[key][ident]=r
        modes[(r["mode"],r["trace_enabled"])].append(r)
    need(len(by)==8,"expected 4 seeds x 2 repeats")
    pairs=[]
    for (sha,seed,rep),d in sorted(by.items()):
        for m in MODES:
            need((m,0) in d,"missing CPU clean arm")
            if rep==0:need((m,1) in d,"missing watcher diagnostic")
        c={m:d[(m,0)]["cpu"]["process_cpu_s"] for m in MODES}
        eq_noX=c["native_no_xor"]-c["quotient_no_xor"]
        eq_withX=c["xor"]-c["quotient"]
        interaction=eq_withX-eq_noX
        pairs.append(dict(sha=sha,seed=seed,repeat=rep,
            native_no_xor_cpu_s=c["native_no_xor"],xor_cpu_s=c["xor"],
            quotient_no_xor_cpu_s=c["quotient_no_xor"],
            quotient_xor_cpu_s=c["quotient"],
            benefit_of_quotient_without_XOR_s=eq_noX,
            benefit_of_quotient_with_XOR_s=eq_withX,
            effect_interaction_difference_s=interaction))
    cells={}
    for mode in MODES:
        a=modes[(mode,0)]
        w=modes[(mode,1)]
        need(len(a)==8 and len(w)==4,"incomplete cell")
        cells[mode]=dict(
            off_trials=8,on_trials=4,
            native_cpu_sum_s=round(sum(x["cpu"]["process_cpu_s"] for x in a),6),
            native_cpu_avg_s=round(statistics.mean(x["cpu"]["process_cpu_s"] for x in a),6),
            native_wall_sum_s=round(sum(x["cpu"]["solve_wall_s"] for x in a),6),
            watcher_scans_mean=round(statistics.mean(x["all_binary_watchers"]["visits"] for x in w),1),
            watcher_satisfied_mean=round(statistics.mean(x["all_binary_watchers"]["satisfied"] for x in w),1),
            watcher_unit_mean=round(statistics.mean(x["all_binary_watchers"]["units"] for x in w),1),
            decisions_mean=round(statistics.mean(x["native_cdcl_decisions"] for x in a),1))
    summary=dict(protocol=PROTO,measurements=48,
        one_reused_source_not_blind=True,
        four_reused_seeds_from_MRE6=True,
        original_SAT_witness_reconstructed_and_verified=True,
        no_independent_UNSAT_proof=False,
        source_vs_quotient_XOR_factorial=True,
        source_input_same_SHA=True,
        native_cpu_solve_excludes_proof_and_CNF_rewriting=True,
        cells=cells,
        interaction_cpu_s_mean=round(statistics.mean(x["effect_interaction_difference_s"] for x in pairs),6),
        quotient_cpu_benefit_without_XOR_s_mean=round(statistics.mean(x["benefit_of_quotient_without_XOR_s"] for x in pairs),6),
        quotient_cpu_benefit_with_XOR_s_mean=round(statistics.mean(x["benefit_of_quotient_with_XOR_s"] for x in pairs),6),
        matched_pairs=pairs)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    # Extend the existing CPU-feedback evidence base, preserving the frozen
    # calibration and the earlier MRE6 observations.
    db=pathlib.Path("mre6/principles.sqlite")
    need(db.exists(),"missing immutable MRE6 training evidence")
    c=sqlite3.connect(db)
    c.executescript("""CREATE TABLE IF NOT EXISTS quotient_xor_interaction(
        source_sha256 TEXT NOT NULL,
        seed INTEGER NOT NULL,
        repeat INTEGER NOT NULL,
        original_no_xor_cpu_s REAL NOT NULL,
        original_with_xor_cpu_s REAL NOT NULL,
        quotient_no_xor_cpu_s REAL NOT NULL,
        quotient_with_xor_cpu_s REAL NOT NULL,
        quotient_benefit_no_xor_s REAL NOT NULL,
        quotient_benefit_with_xor_s REAL NOT NULL,
        cpu_interaction_s REAL NOT NULL,
        PRIMARY KEY(source_sha256,seed,repeat));""")
    for p in pairs:
        c.execute("INSERT INTO quotient_xor_interaction VALUES (?,?,?,?,?,?,?,?,?,?)",
           (p["sha"],p["seed"],p["repeat"],p["native_no_xor_cpu_s"],
            p["xor_cpu_s"],p["quotient_no_xor_cpu_s"],p["quotient_xor_cpu_s"],
            p["benefit_of_quotient_without_XOR_s"],
            p["benefit_of_quotient_with_XOR_s"],
            p["effect_interaction_difference_s"]))
    c.commit()
    c.close()
    print("MRE6B_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    need(len(MODES)==4 and set(MODES)==
         {"native_no_xor","xor","quotient_no_xor","quotient"},
         "not a proper 2x2 factorial")
    print("MRE6B_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--binary",default="mre5/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.seed,a.binary)
    else:audit()

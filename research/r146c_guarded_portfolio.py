#!/usr/bin/env python3
"""R146c guarded selector, paired against frozen R135 on the SAME already-exposed R135 400-CNF set.
Diagnostic replication only; not a new blind holdout.
"""
import pathlib,time,subprocess,random,json,collections
import r135_nonxor_portfolio as base
base.ROOT=pathlib.Path("r146c")
base.PROTO="DRNAS-R146C-COST-GUARD-REUSED-R135-400-20261105-v1"
base.MODES=("kissat","cadical","r118","r135","r146c")
base.R118=pathlib.Path("r146c/r118")
# Sampling budget deliberately fixed BEFORE measurement. Conservative default Kissat.
MAX_BYTES=65536
MAX_CLAUSES=2048
MAX_PROBE_S=0.003
def choose_guard(src):
    st=time.perf_counter()
    binary=horn=clauses=0
    scanned=0
    with src.open("rb") as f:
        for raw in f:
            scanned+=len(raw)
            if scanned>MAX_BYTES or clauses>=MAX_CLAUSES or time.perf_counter()-st>=MAX_PROBE_S:
                break
            line=raw.strip()
            if not line or line[:1] in (b"c",b"p",b"%"):continue
            # Only count completed clauses; a partial scan cannot establish whole-CNF ratios.
            tokens=line.split()
            if tokens and tokens[-1]==b"0":
                lits=[int(t) for t in tokens[:-1]]
                clauses+=1
                binary+=len(lits)==2
                horn+=sum(x>0 for x in lits)<=1
    cost=time.perf_counter()-st
    fraction=scanned/max(1,src.stat().st_size)
    # We do not route based on sampled Horn alone; only a complete, cheap scan
    # with a strong sparse-nonhorn signature can justify CaDiCaL.
    complete=(fraction>=1.0)
    b=binary/max(1,clauses);h=horn/max(1,clauses)
    eligible=complete and clauses>0 and cost<=0.002 and b<0.10 and h<0.30
    target="cadical" if eligible else "kissat"
    reason="complete_strong_sparse" if eligible else ("cost_guard_default" if cost>0.002 else "uncertain_default")
    return target,reason,dict(binary_ratio=round(b,6),horn_ratio=round(h,6),fully_scanned=complete),round(cost,6)
old_invoke=base.invoke
def invoke(src,mode,rep):
    if mode!="r146c":return old_invoke(src,mode,rep)
    start=time.perf_counter()
    target,reason,features,cost=choose_guard(src)
    cmd=[str((base.KISSAT if target=="kissat" else base.CADICAL).resolve()),str(src.resolve())]
    elapsed=time.perf_counter()-start
    try:
        if elapsed>=base.CAP:raise subprocess.TimeoutExpired(cmd,base.CAP)
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(.001,base.CAP-elapsed))
        elapsed=time.perf_counter()-start
        base.need(p.returncode in (10,20),"unexpected solver return "+str(p.returncode))
        status="SAT" if p.returncode==10 else "UNSAT"
        if elapsed>=base.CAP:status="TIMEOUT"
        proof="timeout"
        if status=="SAT":
            base.witness.check_original_sat(p.stdout,src)
            proof="source_SAT_witness_verified"
        elif status=="UNSAT":proof="UNSAT_without_independent_LRAT_proof"
    except subprocess.TimeoutExpired:
        elapsed=base.CAP;status="TIMEOUT";proof="timeout"
    return dict(mode=mode,repeat=rep,status=status,seconds=round(min(elapsed,base.CAP),6),
        par2=30.0 if status=="TIMEOUT" else round(elapsed,6),proof=proof,
        selector_target=target,selector_reason=reason,selector_cost_s=cost,
        binary_ratio=features["binary_ratio"],horn_ratio=features["horn_ratio"],
        fully_scanned=features["fully_scanned"])
base.invoke=invoke
# R135 audit enumerates three comparisons; add R146c comparison to final report after full audit.
old_audit=base.audit
def audit():
    old_audit()
    report_path=base.ROOT/"report.json"
    report=json.loads(report_path.read_text())
    rows=[r for i in range(base.SHARDS) for r in json.loads((base.ROOT/f"shard-{i}.json").read_text())["rows"]]
    idx={(r["sha256"],r["repeat"],r["mode"]):r for r in rows}
    sha=sorted(set(r["sha256"] for r in rows))
    deltas=[sum(idx[(s,rep,"r146c")]["par2"]-idx[(s,rep,"kissat")]["par2"] for rep in range(base.REPS)) for s in sha]
    report["comparisons"]["r146c"]=dict(
        gain_vs_kissat_pct=round(100*(report["summary"]["kissat"]["par2_total_s"]/report["summary"]["r146c"]["par2_total_s"]-1),6),
        faster_formula_pairs=sum(d<-.00001 for d in deltas),
        slower_formula_pairs=sum(d>.00001 for d in deltas))
    report["evaluation_status"]="REUSED_EXPOSED_R135_400_NOT_NEW_BLIND_HOLDOUT"
    report["verdict"]="DIAGNOSTIC_ONLY_NO_PROMOTION"
    base.write(report_path,report)
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("command",choices=("run","audit"));p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    (base.run(a.shard) if a.command=="run" else audit())

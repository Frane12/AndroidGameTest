#!/usr/bin/env python3
"""MRE5 CPU-cost microbenchmark on exactly two previously pinned SAT2026 seeds.

One original CNF; same SOURCE XORs and original SAT witness check. Compare
8 matched combinations of (XOR, clause A, clause B, A+B) × (watch logging ON/OFF).
All use the same pinned modified CMS library, no unpaired solver configurations.

CPU_PROCESS and USER/SYSTEM seconds are measured around native cms.solve()
with CLOCK_PROCESS_CPUTIME_ID/getrusage. The watcher counts classify
watched-binary visits by SAT literal state. A paired CPU difference is an
end-to-end effect of added clauses, NOT isolated CPU cycles per clause.
No artificial per-event timers or million-line logs.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,statistics,subprocess,sys,tempfile,time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre4_trace_pilot as mre4
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE5-CPU-TRUE-BCP-COST-1SAT2026-2SEED-2REP-8ARMS-v1"
ROOT=pathlib.Path("mre5")
MODES=("xor_off","xor_on","a_off","a_on","b_off","b_on","both_off","both_on")
SEEDS=2
REPS=2
CAP=22.0
CMS_SOURCE_SHA="3b709118fd08eb1d15f25e0e239dbc596f967b60"


def need(condition,msg):
    if not condition: raise RuntimeError("MRE5_FAIL_CLOSED "+str(msg))


def parse_native(text):
    status,model,native=r195.parsed_native(text)
    trace,ledger=mre4.parse_trace(text)
    m=re.search(r"^DRNAS_CPU trace_enabled=([01]) process_cpu_s=([\d.]+) user_cpu_s=([\d.]+) sys_cpu_s=([\d.]+) solve_wall_s=([\d.]+)$",text,re.M)
    need(m is not None,"missing actual native process CPU-time record")
    cp=dict(enabled=int(m[1]),process_cpu_s=float(m[2]),
            user_cpu_s=float(m[3]),sys_cpu_s=float(m[4]),
            solve_wall_s=float(m[5]))
    need(abs(cp["process_cpu_s"]-cp["user_cpu_s"]-cp["sys_cpu_s"])<=0.02,
         "native process CPU and user/system are inconsistent")
    w=re.search(r"^DRNAS_WATCH_GLOBAL enabled=([01]) visits=(\d+) units=(\d+) conflicts=(\d+) satisfied=(\d+)$",text,re.M)
    need(w is not None,"missing global native BCP watch telemetry")
    ww=dict(enabled=int(w[1]),visits=int(w[2]),units=int(w[3]),
            conflicts=int(w[4]),satisfied=int(w[5]))
    need(ww["visits"] == ww["units"]+ww["conflicts"]+ww["satisfied"],
         "watcher classification lost events")
    need(ww["enabled"]==cp["enabled"],"trace enabled mismatch")
    return status,model,native,trace,ledger,cp,ww


def trial(shared,seed_index,repeat,mode,binary):
    case,source,n,original,rows,proofs,selected,tags=shared
    started=time.perf_counter()
    prefix,trace_flag=mode.rsplit("_",1)
    enabled=int(trace_flag=="on")
    need(trace_flag in ("on","off") and prefix in ("xor","a","b","both"),
         "invalid experiment mode")
    if prefix=="a": imports=[selected[0]]
    elif prefix=="b": imports=[selected[1]]
    elif prefix=="both": imports=selected
    else: imports=[]
    need(all(len(q["clause"])==2 for q in imports),
         "trace limited to binary certified lemmas")
    seed=int(hashlib.sha256((mre2.PROTO+case["sha256"]+str(seed_index))
                             .encode()).hexdigest()[:8],16)
    native={}
    tags_result=None
    ledger=None
    cp=None
    watchers=None
    status="TIMEOUT"
    native_subprocess_s=None
    with tempfile.TemporaryDirectory(prefix="drnas-mre5-") as td:
        d=pathlib.Path(td)
        cnf,xorf,empty=d/"input.cnf",d/"source.tsv",d/"empty.tsv"
        mre1.write_cnf(cnf,n,original,imports)
        mre1.write_xors(xorf,rows)
        empty.write_text("")
        env=os.environ.copy()
        env["DRNAS_TAG_0"]=",".join(str(q) for q in tags[0])
        env["DRNAS_TAG_1"]=",".join(str(q) for q in tags[1])
        env["DRNAS_ORIG_COUNT"]=str(len(original))
        env["DRNAS_TRACE_ENABLED"]=str(enabled)
        remaining=CAP-(time.perf_counter()-started)
        if remaining>0.1:
            t=time.perf_counter()
            try:
                r=subprocess.run(
                    [str(pathlib.Path(binary).resolve()),str(cnf),
                     str(xorf),str(empty),"source_xor_no_gauss",str(seed)],
                    text=True,capture_output=True,env=env,timeout=remaining,
                    check=False)
            except subprocess.TimeoutExpired: r=None
            native_subprocess_s=time.perf_counter()-t
            if r is not None:
                need(r.returncode==0,
                     "native CMS failed or produced unverified SAT model: "+r.stderr[-1100:])
                status,model,native,tags_result,ledger,cp,watchers=parse_native(r.stdout)
                if status=="SAT":r195.verify_model(source,model)
                need(status==case["expected"],
                     "SAT/UNSAT result changed on original frozen source")
                need(cp["enabled"]==enabled,"native CPU trace mode mismatch")
                need(ledger["original_count"]==len(original) and
                     ledger["total_count"]==len(original)+len(imports),
                     "native imported CNF counts wrong")
                for tag in (0,1):
                    exp=int(prefix in (("a","both") if tag==0 else ("b","both")))
                    need(ledger["marked%d"%tag]==tags_result[tag]["attached"]==exp,
                         "actual binary watched IDs not attached as expected")
                    need(tags_result[tag]["visits"]>=
                         tags_result[tag]["units"]+tags_result[tag]["conflicts"],
                         "tag events corrupted")
                    if not enabled:
                        need(tags_result[tag]["visits"]==0,
                             "disabled trace still counted watcher events")
                if not enabled:
                    need(watchers["visits"]==0,"disabled global watch telemetry not zero")
    wall_s=time.perf_counter()-started
    if wall_s>=CAP:status="TIMEOUT"
    return dict(protocol=PROTO,source_sha256=case["sha256"],rep=seed_index,
                repeat=repeat,seed=seed,mode=mode,status=status,
                trace_enabled=enabled,original_clause_count=len(original),
                imported_lemmas=len(imports),source_xor_rows=len(rows),
                sat_witness_checked=(status=="SAT"),
                native_cdcl_propagations=native.get("propagations"),
                native_cdcl_decisions=native.get("decisions"),
                native_cdcl_conflicts=native.get("conflicts"),
                tag_watchers=tags_result,all_binary_watchers=watchers,
                cpu=cp,trace_input=ledger,wall_s=round(wall_s,6),
                subprocess_wall_s=(round(native_subprocess_s,6) if native_subprocess_s is not None else None),
                par2_s=round(CAP*2 if status=="TIMEOUT" else wall_s,6),
                original_is_development_not_blind=True,otf_gauss=False,
                instrumented_CMS_upstream_sha=CMS_SOURCE_SHA,
                git_sha=os.environ.get("GITHUB_SHA","local"))


def run_shard(seed_index,binary):
    need(seed_index in (0,1),"seed range")
    shared=mre4.setup()
    ROOT.mkdir(parents=True,exist_ok=True)
    records=[]
    for repeat in range(REPS):
        shuffled=list(MODES)
        random.Random(PROTO+str(seed_index)+":"+str(repeat)).shuffle(shuffled)
        for mode in shuffled:
            row=trial(shared,seed_index,repeat,mode,binary)
            records.append(row)
            (ROOT/("seed-%d.json"%seed_index)).write_text(
                json.dumps(records,sort_keys=True)+"\n")
            print("MRE5_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(records)==REPS*len(MODES)==16,"missing seed records")
    print("MRE5_SHARD_PASS",seed_index,len(records),flush=True)


def audit():
    rows=[]
    for rep in range(SEEDS):
        rows+=json.loads((ROOT/("seed-%d.json"%rep)).read_text())
    need(len(rows)==SEEDS*REPS*len(MODES)==32,"incomplete paired 32 trials")
    groups=collections.defaultdict(dict)
    for row in rows:
        need(row["protocol"]==PROTO and row["status"]=="SAT"
             and row["sat_witness_checked"],"invalid source SAT result")
        need(row["instrumented_CMS_upstream_sha"]==CMS_SOURCE_SHA,
             "CMS source build changed")
        need(row["source_sha256"]==mre4.pilot.select_case(0)["sha256"],
             "frozen source drift")
        key=(row["rep"],row["repeat"])
        need(row["mode"] not in groups[key],"duplicate paired arm")
        groups[key][row["mode"]]=row
        need(row["cpu"] is not None and row["all_binary_watchers"] is not None,
             "missing native process CPU or watcher totals")
        need(row["otf_gauss"] is False,"unequal OTF configuration")
        need(row["cpu"]["enabled"]==row["trace_enabled"],"wrong trace toggle")
    paired=[]
    for key,g in sorted(groups.items()):
        need(set(g)==set(MODES),"missing paired modes")
        need(len({x["seed"] for x in g.values()})==1,"unpaired source seed")
        d={}
        for pair in ("xor","a","b","both"):
            on=g[pair+"_on"];off=g[pair+"_off"]
            d[pair]=dict(
              cpu_trace_on_s=on["cpu"]["process_cpu_s"],
              cpu_trace_off_s=off["cpu"]["process_cpu_s"],
              instrument_cpu_overhead_s=round(
                on["cpu"]["process_cpu_s"]-off["cpu"]["process_cpu_s"],6),
              wall_trace_on_s=on["wall_s"],wall_trace_off_s=off["wall_s"],
              tagged_direct_units=sum(x["units"] for x in on["tag_watchers"].values()),
              tagged_direct_conflicts=sum(x["conflicts"] for x in on["tag_watchers"].values()),
              tagged_watch_visits=sum(x["visits"] for x in on["tag_watchers"].values()),
              total_binary_watch_visits=on["all_binary_watchers"]["visits"])
        d["deltas_vs_xor_trace_off_cpu_s"]={
          p:round(d[p]["cpu_trace_off_s"]-d["xor"]["cpu_trace_off_s"],6)
          for p in ("a","b","both")}
        paired.append(dict(seed_index=key[0],repeat=key[1],by_input=d))
    totals={}
    for mode in MODES:
        vals=[x for x in rows if x["mode"]==mode]
        totals[mode]=dict(attempts=len(vals),solved=len([x for x in vals if x["status"]=="SAT"]),
           total_wall_s=round(sum(x["wall_s"] for x in vals),6),
           total_process_cpu_s=round(sum(x["cpu"]["process_cpu_s"] for x in vals),6),
           mean_user_s=round(statistics.mean(x["cpu"]["user_cpu_s"] for x in vals),6),
           mean_sys_s=round(statistics.mean(x["cpu"]["sys_cpu_s"] for x in vals),6),
           mean_cdcl_propagations=round(statistics.mean(
                x["native_cdcl_propagations"] for x in vals),2),
           mean_cdcl_decisions=round(statistics.mean(
                x["native_cdcl_decisions"] for x in vals),2),
           mean_cdcl_conflicts=round(statistics.mean(
                x["native_cdcl_conflicts"] for x in vals),2),
           watch_total_visits=sum(x["all_binary_watchers"]["visits"] for x in vals),
           watch_total_unit=sum(x["all_binary_watchers"]["units"] for x in vals),
           watch_total_conflict=sum(x["all_binary_watchers"]["conflicts"] for x in vals),
           watch_total_satisfied=sum(x["all_binary_watchers"]["satisfied"] for x in vals),
           watch_tag_visits=sum(x["tag_watchers"][str(t)]["visits"] for x in vals for t in (0,1)),
           watch_tag_units=sum(x["tag_watchers"][str(t)]["units"] for x in vals for t in (0,1)),
           watch_tag_conflicts=sum(x["tag_watchers"][str(t)]["conflicts"] for x in vals for t in (0,1)))
    report=dict(protocol=PROTO,source_count=1,measurements=32,
        single_thread_pinned_CMS_version="5.11.15",
        cpu_source="native CLOCK_PROCESS_CPUTIME_ID and getrusage around cms.solve",
        watcher_source="non-inprocessing native PropEngine::prop_bin_cl",
        all_inputs_and_native_library_paired=True,
        conditional_trace_on_off_controls=True,
        cpu_delta_not_exact_per_lemma_cycles=True,
        precomputed_certified_lemmas_cost_not_included=True,
        original_source_NOT_blind=True,
        independent_unsat_LRAT=False,
        rows_by_mode=totals,paired=paired)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE5_FINAL",json.dumps(report,sort_keys=True),flush=True)


def selftest():
    need(SEEDS*REPS*len(MODES)==32,"protocol count")
    sample=('DRNAS_CPU trace_enabled=1 process_cpu_s=2.012345678 user_cpu_s=2.010000000 '
            'sys_cpu_s=0.002345000 solve_wall_s=2.021234567\n'
            'DRNAS_WATCH_GLOBAL enabled=1 visits=5 units=2 conflicts=1 satisfied=2\n')
    m=re.search(r"DRNAS_WATCH_GLOBAL enabled=([01]) visits=(\d+) units=(\d+) conflicts=(\d+) satisfied=(\d+)",sample)
    need(m is not None and int(m[2])==int(m[3])+int(m[4])+int(m[5]),"watch classification")
    print("MRE5_SELFTEST_PASS",PROTO,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--binary",default="mre5/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":run_shard(a.seed,a.binary)
    else:audit()

#!/usr/bin/env python3
"""FUSION1B PAR2: paired, pinned, 40 original CNFs x 2 repeats x 5 arms.

16 original SAT2024 REAL36 sources, 12 archived-source hard synthetic
CNFs (all SHA-disjoint from the prior FUSION1B benchmark), and 12
matched-graph CNFs (one representative of 12 distinct graph groups,
SHA-disjoint from that benchmark). Selection by fixed family/size/seed
metadata BEFORE any new solver runs; this is retrospective, not blind.

PRIMARY metric: solver end-to-end wall PAR2, 6.0s cap, 12.0s penalty
for timeout or unverified result. Independent original SAT model or
UNSAT DRAT checks are required; proof verification is separately timed.
SECONDARY: solver CPU seconds and RSS, verified solved counts.
"""
import argparse,collections,hashlib,json,os,random,resource,signal,subprocess
import sys,tempfile,time,statistics
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research"),str(R/"research/drnas_deltax"),
             str(R/"research/drnas_fusion1")]
import drnas_x55_cpu_real36 as B
import hard_formulas as H
import bench as FIRST

ARMS=("CORE_B","SHADOW_B","FUSION1A","FUSION1B","SIGNAL8_FULL")
REPS=2
SHARDS=4
CAP=6.0
PENALTY=2*CAP
BIN_A=R/"frozen/fusion1a/native/build/drnas-fusion1"
BIN_B=R/"build/drnas-fusion1"
BIN_SIGNAL=R/"build/drnas-deltax-signal"
DRAT=R/"build/drat-trim"
B_EXPECTED_SIGNAL="46252501f59b279165cfcb55b000cb357d5217fde32a94ee693ae47e3bb495e0"

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def emit(tag,x):print(tag+" "+json.dumps(x,sort_keys=True),flush=True)

def check_binaries():
    assert sha(BIN_SIGNAL)==B_EXPECTED_SIGNAL
    assert BIN_A.is_file() and BIN_B.is_file() and DRAT.is_file()
    for pref,binpath in (("A",BIN_A),("B",BIN_B)):
        base=R/("frozen/fusion1a/native" if pref=="A" else ".")
        manifest=base/"build/FUSION1_FROZEN.sha256"
        assert manifest.is_file()
        frozen={}
        for line in manifest.read_text().splitlines():
            digest,name=line.split()
            frozen[name]=digest
        assert frozen["build/drnas-fusion1"]==sha(binpath)
        assert frozen["build/drnas-deltax-signal"]==sha(BIN_SIGNAL)
        assert frozen["build/drat-trim"]==sha(DRAT)

def freeze_sources():
    root=R/"fusion1b_par2_inputs"
    root.mkdir(parents=True,exist_ok=True)
    prior=json.loads((R/"fusion1_inputs/manifest.json").read_text())
    prior_sha={r["sha256"] for r in prior}
    selected=[]
    graph=json.loads((R/"deltax_signal1_inputs/manifest.json").read_text())
    for family in ("planted","k4","odd_wheel","even_wheel"):
        group_ids=sorted({r["graph_id"] for r in graph
                          if r["family"]==family and r["split"]=="holdout"})
        assert len(group_ids)>=3
        for idx,grp in enumerate(group_ids[:3]):
            variant="high1" if idx!=1 else "low1"
            s=next(x for x in graph if x["graph_id"]==grp
                   and x["variant"]==variant)
            p=R/s["path"]
            assert sha(p)==s["sha256"] and s["sha256"] not in prior_sha
            dest=root/"graph"/(s["name"]+".cnf")
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(p.read_bytes())
            selected.append({
                "name":"GRAPH_"+s["name"],"origin":"synthetic-graph-retrospective",
                "family":"graph/"+family,"graph_group":grp,
                "nvars":s["nvars"],"nclauses":s["nclauses"],
                "path":str(dest.relative_to(R)),"sha256":s["sha256"]
            })
    hard=H.write("fusion1b_par2_inputs/hard")
    hard_indices=(1,3,5,9,11,13,15,17,19,21,23,26)
    for i in hard_indices:
        s=hard[i]
        assert s["sha256"] not in prior_sha
        selected.append({
            "name":"HARD_"+s["name"],"origin":"synthetic-hard-retrospective",
            "family":"hard/"+s["family"],"graph_group":None,
            "nvars":s["nvars"],"nclauses":s["nclauses"],
            "path":s["path"],"sha256":s["sha256"]
        })
    real,_=B.official_manifest()
    families=collections.defaultdict(list)
    for s in real:
        if s["sha256"] in prior_sha or s["bytes"]>8500000:continue
        families[s["family"]].append(s)
    for v in families.values():v.sort(key=lambda r:(r["bytes"],r["sha256"]))
    choice=[]
    while len(choice)<16:
        advanced=False
        for family in sorted(families):
            if families[family] and len(choice)<16:
                choice.append(families[family].pop(0));advanced=True
        if not advanced:break
    assert len(choice)==16,("NOT_ENOUGH_REAL_SOURCES",len(choice))
    for s in choice:
        src=R/s["path"]
        assert sha(src)==s["sha256"]
        dest=root/"official"/("original_sat2024_%02d.cnf"%s["id"])
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(src.read_bytes())
        selected.append({
            "name":"REAL_%02d_%s"%(s["id"],s["family"]),
            "origin":"original-SAT2024-retrospective",
            "family":"real/"+s["family"],"graph_group":None,
            "nvars":s["nvars"],"nclauses":s["nclauses"],
            "path":str(dest.relative_to(R)),"sha256":s["sha256"]
        })
    assert len(selected)==40
    assert len({r["sha256"] for r in selected})==40
    assert len({r["graph_group"] for r in selected if r["graph_group"]})==12
    assert all(r["sha256"] not in prior_sha for r in selected)
    for s in selected:
        assert sha(R/s["path"])==s["sha256"]
    selected.sort(key=lambda x:(x["origin"],x["family"],x["sha256"]))
    save(root/"manifest.json",selected)
    meta={
        "status":"FROZEN","CNF_sources":len(selected),
        "source_sha256":sha(root/"manifest.json"),
        "original_SAT2024":16,"synthetic_hard":12,"synthetic_graph":12,
        "disjoint_from_FUSION1B_prior_24_source_shas":True,
        "retrospective_not_blind":True,"selected_without_new_solve_outcomes":True,
        "cap_s":CAP,"PAR2_timeout_s":PENALTY,"repeats":REPS,
        "arms":ARMS,"trials":len(selected)*REPS*len(ARMS),
        "by_family":dict(collections.Counter(r["family"] for r in selected)),
        "binary_shas":{
            "FUSION1A":sha(BIN_A),"FUSION1B":sha(BIN_B),
            "SIGNAL8":sha(BIN_SIGNAL),"DRAT":sha(DRAT)}
    }
    save(root/"freeze.json",meta)
    emit("FUSION1B_PAR2_SOURCES",meta)
    return selected

def sources():
    d=R/"fusion1b_par2_inputs/manifest.json"
    rec=json.loads(d.read_text())
    assert len(rec)==40 and len({r["sha256"] for r in rec})==40
    for r in rec:assert sha(R/r["path"])==r["sha256"],(
        "ORIGINAL_CNF_SOURCE_SHA_MISMATCH",r["name"])
    return rec,sha(d)

def trial(source,arm,rep,dir_path):
    p=R/source["path"]
    raw=p.read_bytes()
    n,clauses=B.parse_cnf(raw)
    assert n==source["nvars"] and len(clauses)==source["nclauses"]
    binary=BIN_A if arm=="FUSION1A" else BIN_SIGNAL if arm=="SIGNAL8_FULL" else BIN_B
    flags={
        "CORE_B":["--fusion-core"],
        "SHADOW_B":["--fusion-shadow"],
        "FUSION1A":["--fusion-guard"],
        "FUSION1B":["--fusion-guard"],
        "SIGNAL8_FULL":["--coop4","gate","--coop4-eager",
                        "--delta2","deltax-signal-8"]
    }[arm]
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        drat=tmp/"proof.drat";usage=tmp/"usage.txt"
        cmd=["/usr/bin/time","-f","%U %S %M","-o",str(usage),
             str(binary.resolve()),str(p.resolve()),
             "--mode","core","--time",str(CAP-0.15),
             "--stats","--x5-no-minimize","--coop5","off",
             "--proof",str(drat),*flags]
        def cap_size():
            resource.setrlimit(resource.RLIMIT_FSIZE,
                               (256*1024*1024,256*1024*1024))
        t0=time.perf_counter()
        process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 text=True,start_new_session=True,preexec_fn=cap_size)
        expired=False
        try:out,err=process.communicate(timeout=CAP+0.25)
        except subprocess.TimeoutExpired:
            expired=True
            os.killpg(process.pid,signal.SIGKILL)
            out,err=process.communicate()
        e2e=time.perf_counter()-t0
        cpu=None;rss=None
        try:
            nums=usage.read_text().strip().split()
            cpu=round(float(nums[0])+float(nums[1]),6)
            rss=int(nums[2])
        except (OSError,ValueError,IndexError):pass
        check_s=0.0
        status="WALL_TIMEOUT" if expired else "UNKNOWN"
        if not expired:
            if process.returncode==10:
                if not B.check_sat(out,clauses,n):
                    raise AssertionError(("INVALID_SAT_MODEL",source["name"],arm,rep))
                status="SAT_VERIFIED"
            elif process.returncode==20:
                assert drat.exists() and drat.stat().st_size>0,(
                    "UNSAT_WITHOUT_ORIGINAL_DRAT",source["name"],arm,rep)
                started=time.perf_counter()
                try:
                    ck=subprocess.run([str(DRAT.resolve()),str(p.resolve()),str(drat)],
                        capture_output=True,text=True,timeout=25)
                    check_s=time.perf_counter()-started
                    assert ck.returncode==0 and "s VERIFIED" in ck.stdout,(
                        "INDEPENDENT_UNSAT_PROOF_INVALID",source["name"],arm,rep,
                        ck.stdout[-400:],ck.stderr[-400:])
                    status="UNSAT_CERTIFIED"
                except subprocess.TimeoutExpired:
                    check_s=time.perf_counter()-started
                    status="UNSAT_CHECK_TIMEOUT"
            elif process.returncode in (0,153):
                status="UNKNOWN"
            elif process.returncode in (1,2) and drat.exists() and \
                 drat.stat().st_size>=256*1024*1024:
                status="PROOF_SIZE_LIMIT"
            else:
                raise RuntimeError(("NATIVE_PROCESS_ERROR",source["name"],arm,rep,
                                    process.returncode,err[-1000:]))
        stats={}
        for line in err.splitlines():
            tag,sep,data=line.partition(" ")
            if tag in ("X41_STATS","DRNAS_FUSION_STATS",
                       "DELTAX_GUARD_STATS","DELTAX_SIGNAL_STATS",
                       "DELTAX_GUARD_SOURCE","DELTAX_STATS"):
                assert tag not in stats,("DUPLICATE_TELEMETRY",tag)
                stats[tag]=json.loads(data)
        if not expired and process.returncode in (0,10,20):
            assert "X41_STATS" in stats,(
                "NATIVE_STATS_MISSING",source["name"],arm,rep,err[-950:])
            if arm in ("CORE_B","SHADOW_B","FUSION1A","FUSION1B"):
                assert "DRNAS_FUSION_STATS" in stats
                fs=stats["DRNAS_FUSION_STATS"]
                if arm in ("CORE_B","SHADOW_B"):
                    assert fs["module_wakeups"]==0 and not fs["cold_originals_loaded"]
                if arm in ("FUSION1A","FUSION1B"):
                    assert stats["DELTAX_GUARD_SOURCE"]["invalid_derivations_rejected"]==0
                    assert stats["DELTAX_GUARD_STATS"]["inconsistent_clones"]==0
        accepted=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and e2e<=CAP
        fusion=stats.get("DRNAS_FUSION_STATS",{})
        core=stats.get("X41_STATS",{})
        result={
            "name":source["name"],"sha256":source["sha256"],
            "family":source["family"],"origin":source["origin"],
            "graph_group":source["graph_group"],
            "rep":rep,"arm":arm,"status":status,"verified":accepted,
            "e2e_wall_s":round(e2e,7),"cpu_s":cpu,"maxrss_kib":rss,
            "par2_wall_s":round(e2e,7) if accepted else PENALTY,
            "verification_s_excluded":round(check_s,6),
            "decisions":core.get("decisions"),"conflicts":core.get("conflicts"),
            "fusion_module_wakeups":fusion.get("module_wakeups",0),
            "fusion_cheap_approvals":fusion.get("cheap_approved",0),
            "fusion_cheap_rejections":fusion.get("cheap_rejected",0),
            "deltax_proof_clauses":stats.get("DELTAX_STATS",{}).get(
                "proof_carrying_injected",0),
            "guard_clone_checks":stats.get("DELTAX_GUARD_STATS",{}).get("checks",0),
            "source_proof_validation":"original_sat_model_or_independent_drat",
        }
        dir_path.mkdir(parents=True,exist_ok=True)
        # logs truncated by design; critical raw counters in JSON.
        (dir_path/(source["name"]+"__"+arm+"__r"+str(rep)+".log")).write_text(err[-40000:])
        emit("FUSION1B_PAR2_TRIAL",{k:v for k,v in result.items() if k not in (
            "sha256","source_proof_validation","graph_group")})
        return result

def smoke():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    check_binaries()
    selected=freeze_sources()
    byfam={s["family"]:s for s in selected}
    fromset=[]
    for prefix in ("real/","hard/","graph/"):
        fromset.append(next(s for s in selected if s["family"].startswith(prefix)))
    chosen=fromset+[next(s for s in selected if s["family"].startswith("hard/php"))]
    rows=[trial(s,arm,0,R/"fusion1b_par2_preflight/raw")
          for s in chosen for arm in ARMS]
    assert len(rows)==20
    assert not any(r["verified"] and r["status"] not in
                   ("SAT_VERIFIED","UNSAT_CERTIFIED") for r in rows)
    by={(r["sha256"],r["arm"]):r for r in rows}
    for s in chosen:
        a=by[(s["sha256"],"CORE_B")];b=by[(s["sha256"],"SHADOW_B")]
        if a["verified"] and b["verified"]:
            assert (a["status"],a["decisions"],a["conflicts"])==(
                b["status"],b["decisions"],b["conflicts"]),(
                "SHADOW_ALTERED_CORE_SEARCH",s["name"])
    save(R/"fusion1b_par2_preflight/report.json",{
        "status":"PASS","sources":len(selected),"pilot_sources":len(chosen),
        "pilot_trials":len(rows),"pilot_verified":sum(r["verified"] for r in rows),
        "original_CNF_SHA_frozen":True,"core_vs_shadow_checked":True,
        "one_cpu":True,"no_promotion":True})
    emit("FUSION1B_PAR2_PREFLIGHT_PASS",{
        "pilot_trials":len(rows),"pilot_verified":sum(r["verified"] for r in rows)})

def shard(i):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows,manifest_sha=sources()
    cases=[s for j,s in enumerate(rows) if j%SHARDS==i]
    assert len(cases)==10
    out=R/f"fusion1b_par2_shards/{i}"
    out.mkdir(parents=True,exist_ok=False)
    save(out/"manifest.json",{
        "shard":i,"cap_s":CAP,"reps":REPS,"arms":ARMS,
        "original_manifest_sha256":manifest_sha,
        "binary_sha256":{
            "FUSION1A":sha(BIN_A),"FUSION1B":sha(BIN_B),
            "SIGNAL8":sha(BIN_SIGNAL),"DRAT":sha(DRAT)},
        "one_logical_cpu":sorted(os.sched_getaffinity(0)),
        "retrospective":True,"no_promotion":True})
    total=0
    with (out/"trials.jsonl").open("w") as dest:
        for source in cases:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(int(source["sha256"][:16],16)+rep*383).shuffle(order)
                for arm in order:
                    row=trial(source,arm,rep,out/"raw")
                    dest.write(json.dumps(row,sort_keys=True)+"\n")
                    dest.flush()
                    total+=1
    assert total==len(cases)*REPS*len(ARMS)
    emit("FUSION1B_PAR2_SHARD_PASS",{
        "shard":i,"sources":len(cases),"trials":total})

def aggregate():
    rows,manifest_sha=sources()
    all_trials=[];manifests=[]
    for i in range(SHARDS):
        p=R/f"fusion1b_par2_downloads/fusion-par2-shard-{i}/fusion1b_par2_shards/{i}"
        manifests.append(json.loads((p/"manifest.json").read_text()))
        all_trials += [json.loads(line) for line in
                       (p/"trials.jsonl").read_text().splitlines()]
    expected={(s["sha256"],r,a) for s in rows for r in range(REPS) for a in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in all_trials]
    assert len(all_trials)==400 and len(set(actual))==400 and set(actual)==expected
    for m in manifests:
        assert m["original_manifest_sha256"]==manifest_sha
        assert m["binary_sha256"]==manifests[0]["binary_sha256"]
        assert m["cap_s"]==CAP and m["reps"]==REPS and tuple(m["arms"])==ARMS
        assert len(m["one_logical_cpu"])==1 and m["retrospective"] and m["no_promotion"]
    verdict=collections.defaultdict(set)
    for row in all_trials:
        assert row["par2_wall_s"]<=PENALTY+0.0000001
        if row["verified"]:
            assert row["status"] in ("SAT_VERIFIED","UNSAT_CERTIFIED")
            verdict[row["sha256"]].add(row["status"])
    assert all(len(x)<=1 for x in verdict.values()),"CONTRADICTORY_VERIFIED_VERDICTS"
    records={(r["sha256"],r["rep"],r["arm"]):r for r in all_trials}
    def summarize(sub):
        result={}
        for arm in ARMS:
            rr=[r for r in sub if r["arm"]==arm]
            result[arm]={
                "attempts":len(rr),
                "sat_verified":sum(r["verified"] and r["status"]=="SAT_VERIFIED" for r in rr),
                "unsat_certified":sum(r["verified"] and r["status"]=="UNSAT_CERTIFIED" for r in rr),
                "verified_solved":sum(r["verified"] for r in rr),
                "timeout_unknown_unverified":sum(not r["verified"] for r in rr),
                "PAR2_sum_s":round(sum(r["par2_wall_s"] for r in rr),6),
                "PAR2_mean_s":round(statistics.mean(r["par2_wall_s"] for r in rr),6),
                "total_solver_cpu_s":round(sum(r["cpu_s"] or 0 for r in rr),6),
                "total_solver_wall_s":round(sum(r["e2e_wall_s"] for r in rr),6),
                "module_wakeups":sum(r["fusion_module_wakeups"] for r in rr),
                "cheap_approvals":sum(r["fusion_cheap_approvals"] for r in rr),
                "deltax_proof_clauses":sum(r["deltax_proof_clauses"] for r in rr),
                "guard_clone_checks":sum(r["guard_clone_checks"] for r in rr),
                "maxrss_peak_kib":max((r["maxrss_kib"] or 0 for r in rr),default=0)
            }
        return result
    overall=summarize(all_trials)
    categories={}
    for cat in ("original-SAT2024-retrospective","synthetic-hard-retrospective",
                "synthetic-graph-retrospective"):
        sub=[r for r in all_trials if r["origin"]==cat]
        categories[cat]=summarize(sub)
    family_summaries={}
    for family in sorted({r["family"] for r in all_trials}):
        family_summaries[family]=summarize([r for r in all_trials if r["family"]==family])
    pairs=[]
    for s in rows:
        for rep in range(REPS):
            arm={a:records[(s["sha256"],rep,a)] for a in ARMS}
            assert arm["CORE_B"]["verified"]==arm["SHADOW_B"]["verified"],(
                "CORE_SHADOW_SOLVED_MISMATCH",s["name"],rep)
            if arm["CORE_B"]["verified"]:
                assert (arm["CORE_B"]["status"],arm["CORE_B"]["decisions"],
                        arm["CORE_B"]["conflicts"])==(
                        arm["SHADOW_B"]["status"],arm["SHADOW_B"]["decisions"],
                        arm["SHADOW_B"]["conflicts"]),(
                        "SHADOW_CORE_SEARCH_DIFFERED",s["name"],rep)
            pairs.append({
                "name":s["name"],"sha256":s["sha256"],"family":s["family"],
                "origin":s["origin"],"rep":rep,
                "status":{a:arm[a]["status"] for a in ARMS},
                "verified":{a:arm[a]["verified"] for a in ARMS},
                "PAR2_s":{a:arm[a]["par2_wall_s"] for a in ARMS},
                "cpu_s":{a:arm[a]["cpu_s"] for a in ARMS},
                "decisions":{a:arm[a]["decisions"] for a in ARMS},
                "conflicts":{a:arm[a]["conflicts"] for a in ARMS},
                "wakeups_B":arm["FUSION1B"]["fusion_module_wakeups"],
            })
    # Correct cluster bootstrap: 40 SOURCE SHA, NOT independent repeated
    # examples. Full PAR2 sums (including censored penalty) are resampled.
    src_means={}
    for s in rows:
        src_means[s["sha256"]]={
            a:statistics.mean(records[(s["sha256"],rep,a)]["par2_wall_s"]
                              for rep in range(REPS))
            for a in ARMS
        }
    rng=random.Random(20261114)
    ratios={}
    for ref in ("CORE_B","FUSION1A","SIGNAL8_FULL"):
        ref_total=overall[ref]["PAR2_sum_s"]
        b_total=overall["FUSION1B"]["PAR2_sum_s"]
        boot=[]
        shas=list(src_means)
        for j in range(2000):
            sample=[shas[rng.randrange(len(shas))] for _ in shas]
            ba=sum(src_means[h]["FUSION1B"] for h in sample)
            ra=sum(src_means[h][ref] for h in sample)
            boot.append(ra/ba if ba>0 else 1.0)
        boot.sort()
        delta_by_source=[
            {"name":s["name"],"family":s["family"],"origin":s["origin"],
             "savings_s":round(src_means[s["sha256"]][ref]-
                               src_means[s["sha256"]]["FUSION1B"],7)}
            for s in rows
        ]
        ratios[ref]={
            "reference_PAR2_sum_s":ref_total,
            "FUSION1B_PAR2_sum_s":b_total,
            "reference_over_FUSION1B_ratio":round(ref_total/b_total,6),
            "paired_source_cluster_bootstrap_95pct_ratio_CI":[
                round(boot[49],6),round(boot[1949],6)],
            "source_means_B_faster_count":sum(x["savings_s"]>0.001 for x in delta_by_source),
            "source_means_B_slower_count":sum(x["savings_s"]<-0.001 for x in delta_by_source),
            "source_means_near_tie_count":sum(abs(x["savings_s"])<=0.001 for x in delta_by_source),
            "top_B_savings":sorted(delta_by_source,key=lambda x:x["savings_s"],reverse=True)[:8],
            "top_B_losses":sorted(delta_by_source,key=lambda x:x["savings_s"])[:8],
        }
    report={
        "status":"COMPLETE","cases":40,"reps":REPS,"arms":list(ARMS),
        "trials":len(all_trials),"cap_s":CAP,"timeout_PAR2_penalty_s":PENALTY,
        "PAR2_definition":"E2E solver wall seconds when independently verified "+
            "original SAT/UNSAT by cap; otherwise 2*cap",
        "proof_checker_wall_excluded":True,
        "source_manifest_sha256":manifest_sha,
        "source_hashes_disjoint_from_prior_FUSION1B_24":True,
        "retrospective_not_blind":True,
        "one_logical_cpu_per_solver":True,
        "independent_model_and_original_unsat_DRAT":True,
        "main_untouched":True,"no_promotion":True,
        "core_SHADOW_CDCL_identical_when_verified":True,
        "units_of_independence":"40 SHA-distinct CNFs, repeats clustered by SHA",
        "overall":overall,"category_summaries":categories,
        "family_summaries":family_summaries,
        "paired_PAR2_vs":ratios,
        "pairs":pairs,
    }
    save(R/"fusion1b_par2_final/report.json",report)
    save(R/"fusion1b_par2_final/trials.json",all_trials)
    emit("FUSION1B_PAR2_FINAL",{k:v for k,v in report.items()
         if k not in ("pairs","family_summaries")})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("smoke","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.stage=="smoke":smoke()
    elif args.stage=="shard":shard(args.shard)
    else:aggregate()

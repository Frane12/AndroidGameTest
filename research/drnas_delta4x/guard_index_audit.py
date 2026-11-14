#!/usr/bin/env python3
"""Proof-first guard-variable-index ablation of frozen DELTA4X.

The ONLY semantic change versus X_ACTIVE is how the read-only guarded-alias
observer receives trail/backtrack updates. CDCL clauses, reasons, resolution,
decision policy, and original-CNF source checks stay identical.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"research"))
from drnas_delta4x import bench as B
from drnas_delta4x import utility_audit as U
from drnas_delta4x.verify import fixtures,oracle,text as dimacs,validate_events
from drnas_x55_cpu_real36 import check_sat,parse_cnf

IDS=(8,19,25,26,28,38)
ARMS=("X_ACTIVE","X_GUARD_INDEX","X_OBSERVER_OFF","X_SHADOW","D4_FIXED")
REPS=3
CAP=3.0

def emit(name,obj):
    print(name+" "+json.dumps(obj,sort_keys=True),flush=True)

def build():
    """Rebuild/pin original, rebuild observer-off, then compile separate indexed variant."""
    U.build_observer_off()
    expected_paths=("build/drnas-delta4x","build/drnas-delta4x-observer-off",
                    "build/drnas-deltacoop4","build/drat-trim",
                    "cross/x59/build/kissat","cross/x59/build/cadical")
    frozen={p:U.digest(R/p) for p in expected_paths}
    assert frozen["build/drnas-delta4x"]==U.BASE_SHA
    assert B.sources()[1]==U.COHORT_SHA

    # Variant includes a private, modified HEADER. Frozen original header is
    # never edited; the C++ solver source points only this variant to the new file.
    h=(R/"research/drnas_delta4x/engine.hpp").read_text()
    h=U.one(h,
      "    std::map<std::vector<int>,Alias> xaliases;",
      """    std::map<std::vector<int>,Alias> xaliases;
    // Read-only observer index: guard-variable -> exact alias clause keys.
    // Original source RUP clauses and CDCL assignments are NEVER changed.
    std::map<int,std::vector<std::vector<int>>> xguard_index;
    std::set<int> xactive_guard_vars;
    int64_t xguard_trail_hits=0,xguard_group_visits=0;
    int64_t xguard_alias_visits=0,xbacktrack_active_visits=0;""")
    h=U.one(h,
      """        xaliases.try_emplace(key,Alias{c.guard,false});
        refresh(values);""",
      """        if(xaliases.try_emplace(key,Alias{c.guard,false}).second)
            xguard_index[std::abs(c.guard)].push_back(key);
        // Rare insertion: full observer refresh preserves original activation
        // semantics even if multiple guards already hold on the live trail.
        refresh(values);""")
    old="""    void refresh(const std::vector<int8_t>& values) {
        for(auto& [key,a]:xaliases){(void)key;const auto v=values[static_cast<size_t>(std::abs(a.guard)-1)];const bool on=v!=0&&((v>0)!=(a.guard>0));
            if(on!=a.active){if(on)++xactivations;else ++xdeactivations;a.active=on;}}
    }
    void trailChange(int lit,const std::vector<int8_t>& values) {
        for(const auto& [key,a]:xaliases){(void)key;if(std::abs(lit)==std::abs(a.guard)){refresh(values);return;}}
    }"""
    new="""    void refreshGuard(int var,const std::vector<int8_t>& values) {
        const auto it=xguard_index.find(var);
        if(it==xguard_index.end())return;
        ++xguard_group_visits;
        bool any=false;
        for(const auto& key:it->second){
            ++xguard_alias_visits;
            auto found=xaliases.find(key);
            if(found==xaliases.end())
                throw std::runtime_error("X_GUARD_INDEX_STALE_KEY");
            auto& a=found->second;
            const auto v=values[static_cast<size_t>(std::abs(a.guard)-1)];
            const bool on=v!=0&&((v>0)!=(a.guard>0));
            if(on!=a.active){
                if(on)++xactivations;
                else ++xdeactivations;
                a.active=on;
            }
            any=any||on;
        }
        if(any)xactive_guard_vars.insert(var);
        else xactive_guard_vars.erase(var);
    }
    // Explicit full refresh is used only at insertion and in lifecycle
    // tests; it must preserve the old public observation semantics.
    void refresh(const std::vector<int8_t>& values) {
        for(const auto& entry:xguard_index)
            refreshGuard(entry.first,values);
    }
    // Called ONLY after CDCL cancelUntil: assigned-false guards can become
    // unassigned, but inactive guards cannot become newly active on rollback.
    // Iterating active guards avoids sweeping all aliases at every backtrack.
    void backtrackRefresh(const std::vector<int8_t>& values) {
        for(auto it=xactive_guard_vars.begin();it!=xactive_guard_vars.end();){
            const int var=*it++;
            ++xbacktrack_active_visits;
            refreshGuard(var,values);
        }
    }
    // One indexed lookup per assignment, rather than scan all aliases.
    void trailChange(int lit,const std::vector<int8_t>& values) {
        if(xguard_index.find(std::abs(lit))==xguard_index.end())return;
        ++xguard_trail_hits;
        refreshGuard(std::abs(lit),values);
    }"""
    h=U.one(h,old,new)
    # Only the indexed binary exposes extra telemetry counters.
    h=U.one(h,
      '          <<",\\"analysis_ms\\":"<<xms<<",\\"structural_not_nonlinearity_proof\\":true}\\n";',
      '          <<",\\"analysis_ms\\":"<<xms'
      '<<",\\"guard_index_trail_hits\\":"<<xguard_trail_hits'
      '<<",\\"guard_index_group_visits\\":"<<xguard_group_visits'
      '<<",\\"guard_index_alias_visits\\":"<<xguard_alias_visits'
      '<<",\\"guard_index_backtrack_active_visits\\":"<<xbacktrack_active_visits'
      '<<",\\"guard_index_groups\\":"<<xguard_index.size()'
      '<<",\\"structural_not_nonlinearity_proof\\":true}\\n";')
    path=R/"build/delta4x_guard_index.hpp"
    path.write_text(h)

    s=(R/"build/drnas_delta4x.cpp").read_text()
    s=U.one(s,'#include "delta4x_engine.hpp"','#include "delta4x_guard_index.hpp"')
    s=U.one(s,'        if(!probing_ && !x46_clone_)coop_.refresh(values_);',
               '        if(!probing_ && !x46_clone_)coop_.backtrackRefresh(values_);')
    assert s.count("coop_.trailChange(lit,values_)")==1
    source=R/"build/drnas_delta4x_guard_index.cpp";source.write_text(s)
    flags=["-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
           "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
           "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1"]
    out=R/"build/drnas-delta4x-guard-index"
    subprocess.run(["g++",*flags,str(source),"-o",str(out)],cwd=R,check=True)
    assert all(U.digest(R/p)==v for p,v in frozen.items()),"FROZEN_REFERENCE_CHANGED"
    report={"base_sha256":U.BASE_SHA,
            "observer_off_sha256":frozen["build/drnas-delta4x-observer-off"],
            "guard_index_sha256":U.digest(out),
            "guard_index_header_sha256":U.digest(path),
            "guard_index_source_sha256":U.digest(source),
            "cohort_sha256":U.COHORT_SHA,
            "same_solver_core":True,
            "only_observer_index_and_backtrack_hook_changed":True,
            "original_models_and_source_proofs_must_be_checked":True,
            "frozen_unchanged":frozen,
            "single_logical_cpu_per_solver":True,
            "main_unchanged":True}
    (R/"delta4x_guard_index_build.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("GUARD_INDEX_BUILD",report)

def preflight():
    """Oracle tests both active implementations + negative controls, including >4096 vars."""
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases={k:(n,c) for k,n,c in fixtures()}
    names=("core","downstream","unguarded","one_guard","missing_reverse",
           "linear","unsat","empty_clause","renamed_0","renamed_5","shifted_5005")
    modes={"X_ACTIVE":"build/drnas-delta4x",
           "X_GUARD_INDEX":"build/drnas-delta4x-guard-index",
           "X_OBSERVER_OFF":"build/drnas-delta4x-observer-off"}
    folder=R/"delta4x_guard_index_preflight"
    folder.mkdir(exist_ok=True)
    rows=[]
    for name in names:
        n,cnf=cases[name]
        src=folder/(name+".cnf")
        src.write_text(dimacs(n,cnf))
        expected=10 if oracle(cnf) else 20
        for mode,exe in modes.items():
            proof=folder/(name+"-"+mode+".drat")
            args=[str(R/exe),str(src),"--mode","core","--time","1.8",
                  "--stats","--x5-no-minimize","--coop4","gate",
                  "--coop4-eager","--coop5","off",
                  "--delta2","d4x","--proof",str(proof)]
            p=subprocess.run(args,cwd=R,capture_output=True,text=True,timeout=9)
            assert p.returncode==expected,(name,mode,"ORACLE_MISMATCH",p.returncode,p.stderr[-600:])
            if expected==10:
                assert check_sat(p.stdout,cnf,n),(name,mode,"MODEL_INVALID")
            else:
                q=subprocess.run([str(R/"build/drat-trim"),str(src),str(proof)],
                                 cwd=R,capture_output=True,text=True,timeout=20)
                assert "s VERIFIED" in q.stdout,(name,mode,"UNSAT_PROOF_INVALID",q.stdout[-500:])
            st,novel,causal=validate_events(p.stderr,cnf)
            rows.append({"case":name,"mode":mode,"status":expected,
                         "installed":st["installed"],
                         "actual_enqueues":st["actual_enqueues"],
                         "activation":st["guard_activations"],
                         "deactivation":st["guard_deactivations"],
                         "source_novel":novel,"causal_logs_checked":causal,
                         "indexed_lookups":st.get("guard_index_trail_hits",0),
                         "indexed_groups":st.get("guard_index_groups",0)})
    for name in names:
        original=next(x for x in rows if x["case"]==name and x["mode"]=="X_ACTIVE")
        indexed=next(x for x in rows if x["case"]==name and x["mode"]=="X_GUARD_INDEX")
        for k in ("status","installed","actual_enqueues","activation","deactivation","source_novel"):
            assert original[k]==indexed[k],("INDEX_TRAJECTORY_OR_OBSERVATION_DRIFT",name,k,original,indexed)
    assert sum(r["actual_enqueues"] for r in rows if r["mode"]=="X_GUARD_INDEX")>0
    assert any(r["indexed_lookups"]>0 for r in rows if r["mode"]=="X_GUARD_INDEX")
    report={"status":"PASS","distinct_oracle_formulas":len(names),"trials":len(rows),
            "models_and_original_unsat_proofs_checked":True,
            "original_source_rup_and_causal_reasons_checked":True,
            "original_vs_index_identical_proof_and_observer_counts":True,
            "high_dimension_guard_supported":True,"records":rows}
    (folder/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("GUARD_INDEX_PREFLIGHT_PASS",report)

def case(src_id,cap=CAP):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert src_id in IDS
    src,manifest=B.sources()
    assert manifest==U.COHORT_SHA
    s=next(x for x in src if x["id"]==src_id)
    assert U.digest(R/s["path"])==s["sha256"]
    build_report=json.loads((R/"delta4x_guard_index_build.json").read_text())
    assert U.digest(R/"build/drnas-delta4x")==U.BASE_SHA
    assert U.digest(R/"build/drnas-delta4x-guard-index")==build_report["guard_index_sha256"]
    assert U.digest(R/"build/drnas-delta4x-observer-off")==build_report["observer_off_sha256"]
    B.BINS.update({"X_ACTIVE":"build/drnas-delta4x",
                   "X_GUARD_INDEX":"build/drnas-delta4x-guard-index",
                   "X_OBSERVER_OFF":"build/drnas-delta4x-observer-off"})
    B.MODES.update({a:"d4x" for a in ("X_ACTIVE","X_GUARD_INDEX","X_OBSERVER_OFF")})
    output=R/"delta4x_guard_index_cases"/str(src_id)
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    original_bytes=(R/s["path"]).read_bytes()
    n,cnf=parse_cnf(original_bytes)
    for rep in range(REPS):
        arms=list(ARMS)
        random.Random(int(s["sha256"][:16],16)+919*rep).shuffle(arms)
        for arm in arms:
            result=B.sample(s,arm,rep,output/"raw",cap=cap)
            if arm in ("X_ACTIVE","X_GUARD_INDEX","X_OBSERVER_OFF") and result["returncode"] in (0,10,20):
                stderr=(output/"raw"/f"{src_id}-{rep}-{arm}.stderr").read_text()
                st,novel,causal=validate_events(stderr,cnf)
                assert st["installed"]==result["x_installed"]
                assert st["actual_enqueues"]==result["x_actual_enqueues"]
                result["x_novel_original_clauses"]=novel
                result["x_causal_logged"]=causal
            result["diagnostic_cap_s"]=cap
            rows.append(result)
    assert len(rows)==REPS*len(ARMS)
    with (output/"trials.jsonl").open("w") as f:
        for x in rows:f.write(json.dumps(x,sort_keys=True)+"\n")
    totals={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        s0=[r["stats"].get("X41_STATS",{}) for r in rr]
        totals[arm]={"trials":len(rr),"verified":sum(r["verified"] for r in rr),
                     "par2":round(sum(r["PAR2_verified_s"] for r in rr),6),
                     "installed":sum(r["x_installed"] for r in rr),
                     "x_enqueues":sum(r["x_actual_enqueues"] for r in rr),
                     "conflicts":sum(t.get("conflicts",0) for t in s0),
                     "decisions":sum(t.get("decisions",0) for t in s0),
                     "propagations":sum(t.get("propagations",0) for t in s0),
                     "cpu_s":round(sum(r["cpu_s"] or 0 for r in rr),5),
                     "mean_rss_kib":round(sum(r["maxrss_kib"] or 0 for r in rr)/len(rr)),
                     "mean_index_trail_hits":round(sum(r["stats"].get("DELTA4X_STATS",{}).get("guard_index_trail_hits",0) for r in rr)/len(rr))}
    emit("GUARD_INDEX_CASE_PASS",{"id":src_id,"family":s["family"],"nvars":n,
                                  "source_sha256":s["sha256"],"cap_s":cap,
                                  "retrospective":True,"verified_speedup_claim":False,
                                  "totals":totals})
    assert all(r["verified"] or r["PAR2_verified_s"]==2*cap for r in rows)
    emit("GUARD_INDEX_CASE_CERTIFIED",{"id":src_id,"trials":len(rows),
                                     "original_formula_verification":True,
                                     "same_single_logical_cpu":True})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("build","preflight","case"))
    p.add_argument("--id",type=int,default=38)
    p.add_argument("--cap",type=float,default=CAP)
    args=p.parse_args()
    if args.stage=="build":build()
    elif args.stage=="preflight":preflight()
    else:case(args.id,args.cap)

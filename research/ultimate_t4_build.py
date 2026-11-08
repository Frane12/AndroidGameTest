#!/usr/bin/env python3
"""Generate isolated T4 research implementations from immutable T2 source.

No change to T1/T2 frozen baseline source or any original CNF.
Every hunk is exactly matched; any drift fails closed before build.
All generated source files are SHA-pinned and uploaded with CI artifacts.
"""
from pathlib import Path

R=Path("research")
def patch(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"T4_SOURCE_DRIFT {label}: found {n}, wanted 1")
    return s.replace(old,new)

def native():
    s=(R/"ultimate_t2_native.cpp").read_text()
    s=patch(s,"    bool incremental_enabled=false;\n",'''
    bool incremental_enabled=false;
    // T4: passive certified source XOR watch before causal opportunity.
    // A currently unassigned implied variable must occur in >=2 residual
    // non-XOR CNF clauses to qualify for active IPASIR-UP delivery.
    bool impact_gate=false, impact_promoted=false;
    vector<unsigned char> impact_vars;
    long impact_hot_candidates=0, impact_filtered_candidates=0, impact_promotions=0;
    void load_impact_vars(const string&path,int n) {
        ifstream in(path);
        if(!in)throw runtime_error("T4_IMPACT_INPUT_MISSING");
        impact_vars.assign(n+1,0);
        string line;
        while(getline(in,line)){
            if(line.empty()||line[0]=='#')continue;
            istringstream ss(line);
            int v=0; string extra;
            if(!(ss>>v)||v<1||v>n||(ss>>extra)||impact_vars[v])
                throw runtime_error("T4_INVALID_IMPACT_VARIABLE");
            impact_vars[v]=1;
        }
        impact_gate=true;
    }
''', "fields")
    s=patch(s,'''            if(mode==SHADOW) {
                // Exact same parity check, but never affect the CDCL trail:
                // isolates work of observing and scanning from utility.
                ++shadow_candidates;
                continue;
            }
            reasons[implied]=std::move(clause);''','''            if(impact_gate) {
                // Certified exact XOR reason on CURRENT CDCL trail.
                // This predicate only identifies an opportunity, NOT a
                // proven counterfactual advantage over clean CDCL.
                if(unassigned<=0 || unassigned>=(int)impact_vars.size())
                    throw runtime_error("T4_IMPACT_VARIABLE_OUTSIDE_ORIGINAL");
                if(!impact_vars[unassigned]) {
                    ++impact_filtered_candidates;
                    ++shadow_candidates;
                    continue;  // passive, no CDCL mutation
                }
                ++impact_hot_candidates;
                if(mode==DIRECT && !impact_promoted) {
                    impact_promoted=true;
                    ++impact_promotions;
                }
            }
            if(mode==SHADOW) {
                ++shadow_candidates; // identical check, no reason delivery
                continue;
            }
            reasons[implied]=std::move(clause);''',"callback")
    s=patch(s,'''        cout<<"R166X_COMPONENT_GATE_SELFTEST_PASS"<<endl;
    }''','''        cout<<"R166X_COMPONENT_GATE_SELFTEST_PASS"<<endl;
        R162Bridge monitor({{{1,2,3},0}},3,DIRECT);
        monitor.watchlazy_enabled=true;
        monitor.impact_gate=true;
        monitor.impact_vars.assign(4,0);
        monitor.notify_new_decision_level();
        monitor.notify_assignment({1,2});
        if(monitor.cb_propagate()!=0 || monitor.direct_proposals!=0 ||
           monitor.impact_filtered_candidates!=1 || !monitor.reasons.empty())
            throw runtime_error("T4_PASSIVE_SELFTEST_FAIL");
        monitor.impact_vars[3]=1;
        monitor.enqueue_ready(0);
        if(monitor.cb_propagate()!=-3 || monitor.impact_promotions!=1 ||
           monitor.impact_hot_candidates!=1)
            throw runtime_error("T4_PROMOTION_SELFTEST_FAIL");
        vector<int> reason;
        while(true) {
            int v=monitor.cb_add_reason_clause_lit(-3);
            if(!v)break;
            reason.push_back(v);
        }
        if(reason!=vector<int>({-3,-1,-2})||
           monitor.reason_clauses_completed!=1)
            throw runtime_error("T4_REASON_SELFTEST_FAIL");
        monitor.notify_assignment({-3});
        monitor.notify_backtrack(0);
        if(monitor.disabled||!monitor.reasons.empty())
            throw runtime_error("T4_BACKTRACK_SELFTEST_FAIL");
        R162Bridge shadow({{{1,2,3},0}},3,SHADOW);
        shadow.impact_gate=true;shadow.watchlazy_enabled=true;
        shadow.impact_vars.assign(4,0);shadow.impact_vars[3]=1;
        shadow.notify_new_decision_level();shadow.notify_assignment({1,2});
        if(shadow.cb_propagate()!=0||shadow.impact_hot_candidates!=1||
           shadow.direct_proposals!=0)
            throw runtime_error("T4_SHADOW_SELFTEST_FAIL");
        cout<<"T4_TRAIL_IMPACT_SELFTEST_PASS"<<endl;
    }''',"selftest")
    s=patch(s,'''    const bool t2_units=(mode=="t2_derived_units");
    const bool needs_units=gauss || t2_units ||''','''    const bool t2_units=(mode=="t2_derived_units");
    const bool impact=(mode=="t4_impact_active"||mode=="t4_impact_shadow");
    const bool needs_units=gauss || t2_units ||''',"detect")
    s=patch(s,'''    if(needs_units==units_path.empty())
        throw runtime_error("T2_UNITS_PROTOCOL_MISMATCH");''','''    if(impact ? units_path.empty() : (needs_units==units_path.empty()))
        throw runtime_error("T4_AUX_INPUT_PROTOCOL_MISMATCH");''',"aux")
    s=patch(s,'''         mode=="td_lazy_source");
    const bool extend=''', '''         mode=="td_lazy_source"||impact);
    const bool extend=''', "t-source")
    s=patch(s,'''(mode=="shadow_boundary"||mode=="t_shadow"||mode=="t2_derived_shadow")?''','''(mode=="shadow_boundary"||mode=="t_shadow"||mode=="t2_derived_shadow"||
          mode=="t4_impact_shadow")?''',"shadow")
    s=patch(s,'''    R162Bridge bridge(std::move(certified),n,m);
    bridge.adaptive_gate=''', '''    R162Bridge bridge(std::move(certified),n,m);
    if(impact)bridge.load_impact_vars(units_path,n);
    bridge.adaptive_gate=''', "load")
    s=patch(s,'''    bridge.incremental_enabled=(mode=="direct_incremental"||(t_source&&mode!="td_lazy_source"));''','''    bridge.incremental_enabled=(mode=="direct_incremental"||
        (t_source&&mode!="td_lazy_source"&&!impact));''',"incremental")
    s=patch(s,'''                              mode=="td_lazy_source");''','''                              mode=="td_lazy_source"||impact);''',"watchlazy")
    s=patch(s,'''mode!="td_lazy_source")
            throw runtime_error("R166X_BAD_MODE");''','''mode!="td_lazy_source"&&
             mode!="t4_impact_active"&&mode!="t4_impact_shadow")
             throw runtime_error("R166X_BAD_MODE");''',"allowed")
    line='<<" shadow_candidates="<<bridge.shadow_candidates'
    if s.count(line)!=2:raise RuntimeError("T4_SOURCE_DRIFT telemetry")
    s=s.replace(line,line+'''
         <<" impact_hot_candidates="<<bridge.impact_hot_candidates
         <<" impact_filtered_candidates="<<bridge.impact_filtered_candidates
         <<" impact_promotions="<<bridge.impact_promotions''')
    (R/"ultimate_t4_native.cpp").write_text(s)

def fallback():
    s=(R/"ultimate_t2_fallback.py").read_text()
    s=patch(s,'ROOT = pathlib.Path("ultimate_t2")','ROOT = pathlib.Path("ultimate_t4")',"root")
    s=patch(s,'''           "t2_derived_incremental", "t2_derived_shadow", "td_lazy_source"}''','''           "t2_derived_incremental", "t2_derived_shadow", "td_lazy_source",
           "t4_impact_shadow", "t4_impact_active"}''',"allowed")
    s=patch(s,'''                 "td_lazy_source": "td_lazy_source"}''','''                 "td_lazy_source": "td_lazy_source",
                 "t4_impact_shadow": "t4_impact_shadow",
                 "t4_impact_active": "t4_impact_active"}''',"native-map")
    s=patch(s,'''def source_replay(cnf, evidence, rows_tsv):''','''def source_replay(cnf, evidence, rows_tsv, impact_path=None):''',"source-replay-signature")
    s=patch(s,'''    _, groups, units = gauss.source_equations(clauses)''','''    equations, groups, units = gauss.source_equations(clauses)''',"equations")
    s=patch(s,'''    return len(verified)

def run_native''','''    if impact_path is not None:
        # An ORIGINAL-CNF-only, proof-independent opportunity predicate.
        # Reconstructed complete parity clauses are excluded from residual.
        residual, _ = gauss.residual_frequencies(clauses, equations)
        hot = sorted(v for v,n in residual.items() if n >= 2)
        pathlib.Path(impact_path).write_text(
            "".join(str(v)+"\\n" for v in hot))
        print("T4_IMPACT_SOURCE_PASS " +
              json.dumps(dict(source_sha256=sha256(cnf),
                              residual_vars=len(residual),
                              hot_vars=len(hot),threshold=2),
                         sort_keys=True),flush=True)
    return len(verified)

def run_native''',"impact-evidence")
    s=patch(s,'''               implied, eligible, prep_s, rows, units, deadline, probe=None):''','''               implied, eligible, prep_s, rows, units, deadline, probe=None,
               impact_count=0):''',"native-args")
    s=patch(s,'''                eligible=eligible, prep_s=round(prep_s, 6), probe=probe or {})''','''                eligible=eligible, prep_s=round(prep_s, 6), probe=probe or {},
                residual_hot_vars=impact_count)''',"gate-stat")
    s=patch(s,'''        argv.append(str(units.resolve()))
    try:''','''        argv.append(str(units.resolve()))
    if native_mode in ("t4_impact_shadow","t4_impact_active"):
        impact_file=rows.parent/"impact-vars.tsv"
        need(impact_file.is_file(),"source-backed T4 impact tag file missing")
        argv.append(str(impact_file.resolve()))
    try:''',"native-impact-tsv")
    s=patch(s,'''    selected = derived = implied = 0''','''    selected = derived = implied = impact_count = 0''',"impact-count")
    s=patch(s,'''                        need(source_replay(src, evidence, base/"source.tsv") == selected,
                             "source parity proof replay failed")
                        rows = base/"source.tsv"''','''                        impact_path=(base/"impact-vars.tsv") if mode in (
                            "t4_impact_shadow","t4_impact_active") else None
                        need(source_replay(src, evidence, base/"source.tsv",
                                           impact_path=impact_path) == selected,
                             "source parity proof replay failed")
                        if impact_path is not None:
                            impact_count=len(impact_path.read_text().split())
                        rows = base/"source.tsv"''',"cert-and-impact")
    s=patch(s,'''                          eligible, prep_s, rows, units, deadline, locals().get("probe", {}))''','''                          eligible, prep_s, rows, units, deadline, locals().get("probe", {}),
                          impact_count=impact_count)''',"gate-return")
    (R/"ultimate_t4_fallback.py").write_text(s)

def benchmark():
    s=(R/"ultimate_t2_benchmark.py").read_text()
    s=patch(s,'ROOT = pathlib.Path("ultimate_t2")','ROOT = pathlib.Path("ultimate_t4")',"root")
    start=s.index('MODES = (')
    end=s.index('\nREPS = 2', start)
    s=s[:start]+'''MODES = ("r153","t_clean","t_shadow","td_lazy_source",
         "t4_impact_shadow","t4_impact_active")'''+s[end:]
    s=patch(s,'''PROTO = "DRNAS-TD-20261107-LAZY-WATCH-11-ARM-SOURCE-ABLATION"''','''PROTO = "DRNAS-T4-20261108-TRAIL-IMPACT-6ARM-SOURCE-PAIRED"''',"proto")
    s=patch(s,'''FALLBACK = pathlib.Path("research/ultimate_t2_fallback.py")''','''FALLBACK = pathlib.Path("research/ultimate_t4_fallback.py")''',"fallback")
    s=patch(s,'''need(len(MODES)==11 and len(cases())==20,"eleven-arm TD protocol")''','''need(len(MODES)==6 and len(cases())==20,"six-arm T4 protocol")''',"selftest")
    s=patch(s,'''        progress_avoided_scans=max_progress("avoided_full_scans"))''','''        progress_avoided_scans=max_progress("avoided_full_scans"),
        impact_hot=max(int(native.get("impact_hot_candidates",0)),
                       max_progress("impact_hot_candidates")),
        impact_filtered=max(int(native.get("impact_filtered_candidates",0)),
                            max_progress("impact_filtered_candidates")),
        impact_promotions=max(int(native.get("impact_promotions",0)),
                              max_progress("impact_promotions")))''',"trial-telemetry")
    s=patch(s,'''need(len(rows)==len(cs)*REPS*len(MODES)==440,"trial count incorrect")''','''need(len(rows)==len(cs)*REPS*len(MODES)==240,"trial count incorrect")''',"count")
    s=patch(s,'''                                     "t2_derived_incremental","t2_derived_shadow","td_lazy_source")''','''                                     "t2_derived_incremental","t2_derived_shadow",
                                     "td_lazy_source","t4_impact_shadow","t4_impact_active")''',"started")
    s=patch(s,'''                frontier_updates=sum(x["progress_frontier_updates"] for x in subset))''','''                frontier_updates=sum(x["progress_frontier_updates"] for x in subset),
                impact_hot=sum(x["impact_hot"] for x in subset),
                impact_filtered=sum(x["impact_filtered"] for x in subset),
                impact_promotions=sum(x["impact_promotions"] for x in subset),
                residual_hot_vars=sum(x["t_gate"].get("residual_hot_vars",0) for x in subset))''',"impact-summary")
    start=s.index('    for ref,cand in ((')
    end=s.index(':\n         deltas=',start)
    s=s[:start]+'''    for ref,cand in (("t_clean","t_shadow"),
                     ("t_clean","td_lazy_source"),
                     ("t_clean","t4_impact_shadow"),
                     ("t_clean","t4_impact_active"),
                     ("t_shadow","t4_impact_shadow"),
                     ("td_lazy_source","t4_impact_active"),
                     ("t4_impact_shadow","t4_impact_active"),
                     ("r153","t4_impact_active"))'''+s[end:]
    s=patch(s,'''status="ULTIMATE_TD_LAZY_SOURCE_AUDIT_PASS_NONBLIND"''','''status="ULTIMATE_T4_TRAIL_IMPACT_AUDIT_PASS_NONBLIND"''',"status")
    s=patch(s,'''20 previously used original CNFs; eleven arms, two reps = 440 attempts. Not blind. Native UNSAT lacks LRAT. Causal factorial isolation.''','''20 previously used original CNFs; 6 arms, 2 reps = 240 attempts. Not blind. Source XOR proofs independently replayed; native UNSAT has no independent LRAT. Pre-registered >=2 residual-clause opportunity gate; cannot prove the clean CDCL counterfactual.''',"summary-note")
    s=patch(s,'''# Ultimate TD — lazy exact two-watch vs eager source XOR incremental frontier''','''# T4 — residual-CNF impact-gated certified XOR trail promotion vs true Shadow''',"title")
    s=patch(s,'''original_r2_run=42346485260,''','''original_r2_run=42346485260,
         original_td_run=42356438634, t4_impact_threshold=2,
         t4_no_original_cnf_rewrite=True,''',"metadata")
    (R/"ultimate_t4_benchmark.py").write_text(s)

def main():
    native()
    fallback()
    benchmark()
    print("T4_GENERATED_SOURCES_PASS",flush=True)

if __name__=="__main__":
    main()

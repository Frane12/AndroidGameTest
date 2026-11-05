// R148 research-only, direct GF(2) user propagation with source-certified reasons.
// Reuses unchanged R133c reversible XOR watches, exact GF(2) pairwise closure,
// original CNF SAT model verification, and pinned CaDiCaL 2.1.0 IPASIR-UP.
// Pure CNF remains unmodified. No claim of independent UNSAT certification.
#define main drnas_r133c_internal_entry
#include "r133c_native_gf2_cdcl_bridge.cpp"
#undef main
#include <map>
#include <cstdint>
#include <iomanip>
#include <memory>

class R148Bridge : public DrnasBridge {
public:
    enum Mode { FREEZE, WATCH, CLAUSE, DIRECT };
    Mode mode;
    std::map<int,std::vector<int>> reasons;
    std::map<int,size_t> reason_pos;
    long direct_proposals=0, direct_reason_requests=0;
    long direct_reason_lits=0, direct_ready_checks=0;
    long direct_no_units=0, direct_expired=0;
    size_t peak_reason_cache=0;

    R148Bridge(vector<XorRow> input, int n, Mode m):
        DrnasBridge(std::move(input),n,m!=FREEZE,m==CLAUSE),mode(m) {}

    void notify_backtrack(size_t level) override {
        DrnasBridge::notify_backtrack(level);
        for(auto it=reasons.begin();it!=reasons.end();) {
            int v=abs(it->first);
            if(v<=0 || v>=(int)assigned.size() || assigned[v]==0) {
                reason_pos.erase(it->first);
                it=reasons.erase(it);
                ++direct_expired;
            } else ++it;
        }
    }

    // For WATCH and DIRECT the original CNF solver handles all conflicts.
    // CLAUSE is the unchanged R133c external-clause baseline.
    bool cb_has_external_clause(bool& forgettable) override {
        if (mode!=CLAUSE) { forgettable=true; return false; }
        return DrnasBridge::cb_has_external_clause(forgettable);
    }
    int cb_add_external_clause_lit() override {
        return mode==CLAUSE ? DrnasBridge::cb_add_external_clause_lit() : 0;
    }

    // IPASIR-UP: return a directly implied literal; the immutable reason
    // is cached before return, rather than reconstructing from a later trail.
    int cb_propagate() override {
        if (mode!=DIRECT || disabled || budget_off) return 0;
        while(next_dirty<dirty.size()) {
            const size_t idx=dirty[next_dirty++];
            if(idx>=rows.size()) {disabled=true;return 0;}
            queued[idx]=0;
            ++direct_ready_checks;
            const auto& row=rows[idx];
            int unknown=0, unassigned=0, assigned_parity=0;
            vector<int> clause;
            clause.reserve(row.vars.size());
            for(int v:row.vars) {
                if(v<=0 || v>=(int)assigned.size()) {disabled=true;return 0;}
                int a=assigned[v];
                ++row_literal_reads;
                if(a==0) { ++unknown; unassigned=v; }
                else {
                    assigned_parity ^= (a>0);
                    clause.push_back(a>0 ? -v : v);
                }
            }
            ++rows_scanned;
            if(unknown!=1) { ++direct_no_units; continue; }
            const int implied=((assigned_parity ^ row.rhs)!=0) ? unassigned : -unassigned;
            // The XOR equation entails this CNF reason under all assignments.
            // The reason starts with the propagated literal as expected by
            // CaDiCaL and includes all negated current row assignments.
            clause.insert(clause.begin(),implied);
            if(clause.size()<2 || clause.size()!=row.vars.size()) {
                disabled=true;return 0;
            }
            reasons[implied]=std::move(clause);
            reason_pos[implied]=0;
            ++direct_proposals;
            peak_reason_cache=max(peak_reason_cache,reasons.size());
            return implied;
        }
        dirty.clear(); next_dirty=0;
        return 0;
    }

    // Called lazily by CaDiCaL for the original, immutable reason.
    int cb_add_reason_clause_lit(int propagated_lit) override {
        if(mode!=DIRECT) return 0;
        auto it=reasons.find(propagated_lit);
        if(it==reasons.end()) {
            // Fail closed on an unexplained external propagation.
            throw runtime_error("R148_MISSING_DIRECT_REASON");
        }
        ++direct_reason_requests;
        size_t& pos=reason_pos[propagated_lit];
        if(pos==it->second.size()) {pos=0;return 0;}
        ++direct_reason_lits;
        return it->second[pos++];
    }

    static void selftest() {
        // 1 xor 2 xor 3 = 0; if 1 and 2 are true then -3 must follow.
        vector<XorRow> x{{{1,2,3},0}};
        R148Bridge b(std::move(x),3,DIRECT);
        b.notify_new_decision_level();
        b.notify_assignment({1,2});
        int imp=b.cb_propagate();
        if(imp!=-3) throw runtime_error("R148_SELFTEST_NO_DIRECT_IMPLICATION");
        vector<int> reason;
        while(true) {int lit=b.cb_add_reason_clause_lit(imp);if(!lit)break;reason.push_back(lit);}
        if(reason.size()!=3 || reason[0]!=-3 || reason[1]!=-1 || reason[2]!=-2)
            throw runtime_error("R148_SELFTEST_WRONG_REASON");
        // Exhaustive source-backed reason tautology over the XOR solutions.
        for(int mask=0;mask<8;++mask) {
            int a=(mask&1)!=0, c=(mask&2)!=0, d=(mask&4)!=0;
            if((a^c^d)!=0)continue;
            if(!(!a||!c||!d))throw runtime_error("R148_REASON_NOT_ENTAILED");
        }
        b.notify_assignment({-3});
        b.notify_backtrack(0);
        if(b.disabled || !b.reasons.empty())
            throw runtime_error("R148_SELFTEST_UNDO_FAILURE");
        b.notify_new_decision_level();
        b.notify_assignment({-1,2});
        int second=b.cb_propagate();
        if(second!=3)throw runtime_error("R148_SELFTEST_REPROPAGATION_FAILURE");
        cout<<"R148_DIRECT_SELFTEST_PASS unit=-3 second=3 reason_length=3 rollback=1"<<endl;
    }
};


// R149: incremental, bounded XOR-pair activation ONLY when existing row
// watches are already close to propagation. No unconstrained global O(n^2)
// closure upfront. Each online equation is XOR of two certified source rows.
class R149Bridge : public R148Bridge {
public:
    const size_t originals;
    vector<vector<size_t>> sources_by_var;
    set<pair<vector<int>,int>> known;
    set<uint64_t> attempted;
    int online_rows=0, pair_checks=0, pair_cap_hit=0;
    long online_callbacks=0, online_short_rows=0;
    double online_time_s=0.0;
    bool online_enabled=true;
    static constexpr int MAX_NEW_ROWS=64;
    static constexpr int MAX_PAIR_CHECKS=256;
    static constexpr double MAX_ONLINE_SECONDS=0.002;

    R149Bridge(vector<XorRow> initial, int n)
      :R148Bridge(std::move(initial),n,DIRECT),
       originals(rows.size()),sources_by_var(n+1) {
        for(size_t i=0;i<originals;++i) {
            known.insert({rows[i].vars,rows[i].rhs});
            for(int v:rows[i].vars)sources_by_var[v].push_back(i);
        }
    }

    void install_row(vector<int> vars,int rhs,int unknown) {
        const size_t idx=rows.size();
        int wa=0,wb=0;
        for(int v:vars)if(assigned[v]==0){ if(!wa)wa=v;else if(!wb){wb=v;break;} }
        if(!wa)wa=vars[0];
        if(!wb)wb=(vars[0]==wa?vars[1]:vars[0]);
        rows.push_back({std::move(vars),rhs});
        watch_a.push_back(wa);watch_b.push_back(wb);
        generation_a.push_back(1);generation_b.push_back(1);
        scan_cursor.push_back(0);
        queued.push_back(0);
        watch_index[wa].push_back({idx,1});
        watch_index[wb].push_back({idx,1});
        if(unknown<=1)enqueue_ready(idx);
        ++online_rows;
    }

    int cb_propagate() override {
        ++online_callbacks;
        if(online_enabled && !disabled && !budget_off && originals>1 &&
           online_rows<MAX_NEW_ROWS && pair_checks<MAX_PAIR_CHECKS) {
            auto start=chrono::steady_clock::now();
            int touched=0;
            const size_t preexisting_dirty=dirty.size();
            for(size_t pos=next_dirty;pos<preexisting_dirty && touched<4;++pos) {
                const size_t i=dirty[pos];
                if(i>=originals)continue;
                ++touched;
                // On-demand adjacency: only equations sharing a variable
                // with the currently watched source row are considered.
                for(int var:rows[i].vars) {
                    for(size_t j:sources_by_var[var]) {
                        if(j==i)continue;
                        const size_t lo=min(i,j),hi=max(i,j);
                        const uint64_t key=(uint64_t(lo)<<32)|uint64_t(hi);
                        if(!attempted.insert(key).second)continue;
                        ++pair_checks;
                        if(pair_checks>MAX_PAIR_CHECKS || online_rows>=MAX_NEW_ROWS)break;
                        vector<int> out;
                        set_symmetric_difference(rows[lo].vars.begin(),rows[lo].vars.end(),
                          rows[hi].vars.begin(),rows[hi].vars.end(),back_inserter(out));
                        if(out.size()<2 || out.size()>8)continue;
                        int unknown=0;
                        for(int v:out) unknown+=(assigned[v]==0);
                        if(unknown!=1 && unknown!=2)continue;
                        ++online_short_rows;
                        int rhs=rows[lo].rhs^rows[hi].rhs;
                        if(known.insert({out,rhs}).second)install_row(std::move(out),rhs,unknown);
                    }
                    if(pair_checks>=MAX_PAIR_CHECKS || online_rows>=MAX_NEW_ROWS)break;
                    if(chrono::duration<double>(chrono::steady_clock::now()-start).count() >
                       MAX_ONLINE_SECONDS-online_time_s)break;
                }
                if(pair_checks>=MAX_PAIR_CHECKS||online_rows>=MAX_NEW_ROWS)break;
                if(chrono::duration<double>(chrono::steady_clock::now()-start).count() >
                   MAX_ONLINE_SECONDS-online_time_s)break;
            }
            online_time_s+=chrono::duration<double>(chrono::steady_clock::now()-start).count();
            if(online_time_s>=MAX_ONLINE_SECONDS || pair_checks>=MAX_PAIR_CHECKS) {
                online_enabled=false;
                pair_cap_hit=1;
            }
        }
        return R148Bridge::cb_propagate();
    }

    static void selftest() {
        vector<XorRow> input={{{1,2,3},0},{{1,2,4},0}};
        R149Bridge bridge(std::move(input),4);
        bridge.notify_new_decision_level();
        bridge.notify_assignment({1,2});
        const int implied=bridge.cb_propagate();
        if(bridge.online_rows<1 || bridge.rows.size()<3 || implied==0)
            throw runtime_error("R149_LAZY_ACTIVATION_SELFTEST");
        bool found=false;
        for(const auto& r:bridge.rows)if(r.vars==vector<int>({3,4})&&r.rhs==0)found=true;
        if(!found)throw runtime_error("R149_LAZY_GAUSSIAN_CONSEQUENCE");
        if(bridge.disabled)throw runtime_error("R149_LAZY_WATCH_DISABLED");
        cout<<"R149_LAZY_SELFTEST_PASS derived="<<bridge.online_rows
            <<" implied="<<implied<<" pairs="<<bridge.pair_checks<<"\n";
    }
};

static int r149_run(const string& mode,const string& src,const string& proof) {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    vector<XorRow> certified=mode=="clean"?vector<XorRow>{}:load_rows(proof,n);
    const size_t source_rows=certified.size();
    const bool all_closure=(mode=="clause"||mode=="watch"||mode=="direct");
    if(all_closure) certified=gf2_pairwise_closure(certified);
    const long upfront_derived=(long)certified.size()-(long)source_rows;
    const R148Bridge::Mode m=(mode=="freeze")?R148Bridge::FREEZE:
        mode=="watch"?R148Bridge::WATCH:mode=="clause"?
        R148Bridge::CLAUSE:R148Bridge::DIRECT;
    std::unique_ptr<R148Bridge> ptr;
    if(mode=="lazy")ptr.reset(new R149Bridge(std::move(certified),n));
    else ptr.reset(new R148Bridge(std::move(certified),n,m));
    auto& bridge=*ptr;
    if(mode!="clean" && !bridge.rows.empty()) {
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto& row:bridge.rows)
            for(int v:row.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    auto t=chrono::steady_clock::now();
    const int result=solver.solve();
    const double secs=chrono::duration<double>(chrono::steady_clock::now()-t).count();
    if(result!=10&&result!=20)throw runtime_error("R149_UNKNOWN_SOLVER_RESULT");
    if(result==10)for(const auto& clause:cnf) {
        bool ok=false;
        for(int lit:clause) {
            const int val=solver.val(abs(lit));
            if(val&&((val>0)==(lit>0))) {ok=true;break;}
        }
        if(!ok)throw runtime_error("R149_ORIGINAL_CNF_SAT_WITNESS_INVALID");
    }
    if(bridge.disabled)throw runtime_error("R149_BRIDGE_INVARIANT");
    R149Bridge* lazy=dynamic_cast<R149Bridge*>(&bridge);
    cout<<fixed<<setprecision(7)
        <<"R149_RESULT mode="<<mode
        <<" status="<<(result==10?"SAT":"UNSAT")
        <<" solver_s="<<secs<<" source_rows="<<source_rows
        <<" upfront_rows="<<upfront_derived
        <<" online_rows="<<(lazy?lazy->online_rows:0)
        <<" pair_checks="<<(lazy?lazy->pair_checks:0)
        <<" online_time_s="<<(lazy?lazy->online_time_s:0.0)
        <<" online_cap_hit="<<(lazy?lazy->pair_cap_hit:0)
        <<" original_clauses="<<cnf.size()
        <<" assignments="<<bridge.notifications
        <<" backtracks="<<bridge.backtracks
        <<" watch_lookups="<<bridge.watch_lookups
        <<" rows_scanned="<<bridge.rows_scanned
        <<" clauses_emitted="<<bridge.clauses_emitted
        <<" direct_proposals="<<bridge.direct_proposals
        <<" direct_reason_requests="<<bridge.direct_reason_requests
        <<" direct_reason_lits="<<bridge.direct_reason_lits
        <<" sat_witness_checked="<<(result==10?1:0)
        <<" disabled="<<bridge.disabled<<"\n";
    return result;
}

int main(int argc,char**argv) {
    try{
        if(argc==2&&string(argv[1])=="selftest") {
            DrnasBridge::watch_selftest();
            gf2_closure_selftest();
            R148Bridge::selftest();
            R149Bridge::selftest();
            return 0;
        }
        if(argc!=4){cerr<<"R149 usage: clean|freeze|watch|clause|direct|lazy CNF CERTS\n";return 2;}
        const string m=argv[1];
        if(m!="clean" && m!="freeze" && m!="watch" && m!="clause" &&
           m!="direct" && m!="lazy")throw runtime_error("R149_BAD_MODE");
        return r149_run(m,argv[2],argv[3]);
    }catch(const exception&e) {
        cerr<<"R149_FAIL_CLOSED "<<e.what()<<"\n";
        return 2;
    }
}

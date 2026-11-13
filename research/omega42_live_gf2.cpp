// DRNAS MATH Ω4: proof-safe online GF(2) elimination on real CaDiCaL
// IPASIR-UP CDCL assignments (not a preprocessing-only SAT claim).
// Sources: only independently source-certified, exact XOR rows from the
// XORABC3 exporter; never infer parity from partial CNF patterns.
// Clean, shadow and live arms all use one identical native binary.
// Experimental, not a new theorem or an independent UNSAT LRAT certificate.
#define main omega4_r133c_unused_main
#include "r133c_native_gf2_cdcl_bridge.cpp"
#undef main
#include <cstdint>
#include <map>
#include <limits>
#include <iomanip>
#include <unordered_map>
#include <numeric>

struct Omega4Row {
    vector<int> remaining; // sorted, currently unassigned variables
    int rhs=0;              // rhs after currently assigned variables are eliminated
    uint64_t ancestors=0;  // exact GF(2) source-row ancestry, <=32 rows
};

class Omega4Bridge final : public DrnasBridge {
public:
    enum Mode { SHADOW, LIVE };
    Mode mode;
    const vector<XorRow> source;
    uint64_t generation=1, scanned_generation=0;
    long scans=0, row_xors=0, callbacks=0, unit_candidates=0, conflicts_seen=0;
    long proposals=0, completed_reasons=0, conflict_clauses=0;
    long reason_replays=0, proof_failures=0, skipped_wide=0;
    long abstentions=0;
    int min_conflict_width=std::numeric_limits<int>::max();
    int max_accepted_reason_width=0;
    long max_scans=12000;
    int max_reason_width=16;
    // Bounded, frozen opportunity-cost policy: no learned parameters.
    // A genuinely used reason is one whose CNF explanation CaDiCaL
    // explicitly requested to completion, NOT merely a proposed literal.
    bool cost_gate=false;
    long gated_skips=0, gate_active_scans=0, gate_low_yield_events=0;
    long sum_reason_width=0, delivered_reason_count=0;
    long sum_proof_depth=0, checked_proof_rows=0;
    uint64_t scan_wall_ns=0;
    // Ω4.2: source-disjoint GF(2) components. Their ranks/utility are
    // HEURISTIC INFORMATION ONLY. They cannot justify a solver clause.
    bool component_mode=false;
    struct Component {
        vector<int> rowids, vars;
        uint64_t epoch=1, seen=0;
        long visits=0, scans=0, skips=0, used=0, accepted=0, conflicts=0;
        uint64_t scan_ns=0;
        int static_rank=0;
    };
    vector<Component> components;
    vector<int> component_by_var;
    map<int,int> reason_component;
    int pending_component=-1;
    int conflict_component=-1;
    long component_scans=0, component_skips=0, component_memo_hits=0;
    long stale_proposals_discarded=0, checked_reason_lits=0;
    long component_heuristic_rejections=0, component_dirty_events=0;
    map<int,vector<int>> explanations;
    map<int,size_t> explanation_positions;
    // outgoing/send_index are inherited and only used for verified conflicts.

    explicit Omega4Bridge(vector<XorRow> originals, int n, Mode m, bool gated=false,
                          bool local=false):
        DrnasBridge(vector<XorRow>{},n,false,false),mode(m),source(std::move(originals)){
        component_mode=local;
        cost_gate=gated && !local;
        if(cost_gate || component_mode) max_scans=6000;
        if(source.size()>32)throw runtime_error("OMEGA4_SOURCE_ROW_CAP");
        for(const auto& r:source) {
            if(r.vars.size()<2 || r.vars.size()>8 || r.rhs<0 || r.rhs>1)
                throw runtime_error("OMEGA4_UNTRUSTED_ROW");
            if(!is_sorted(r.vars.begin(),r.vars.end()) ||
                adjacent_find(r.vars.begin(),r.vars.end())!=r.vars.end())
                throw runtime_error("OMEGA4_UNSORTED_OR_DUPLICATE_ROW");
            for(int v:r.vars)if(v<=0 || v>=int(assigned.size()))
                throw runtime_error("OMEGA4_ROW_VAR_RANGE");
        }
        if(component_mode) build_components();
    }

    void build_components() {
        const int n=int(source.size());
        vector<int> parent(n);
        iota(parent.begin(),parent.end(),0);
        auto root=[&](int x) {
            while(parent[x]!=x){parent[x]=parent[parent[x]];x=parent[x];}
            return x;
        };
        auto unite=[&](int a,int b) {
            a=root(a);b=root(b);
            if(a!=b)parent[b]=a;
        };
        unordered_map<int,int> first;
        for(int i=0;i<n;i++)for(int v:source[i].vars){
            auto old=first.find(v);
            if(old==first.end())first.emplace(v,i);
            else unite(i,old->second);
        }
        map<int,int> comp_ids;
        for(int i=0;i<n;i++){
            int r=root(i),idx;
            auto it=comp_ids.find(r);
            if(it==comp_ids.end()){
                idx=int(components.size());
                comp_ids[r]=idx;components.emplace_back();
            } else idx=it->second;
            components[idx].rowids.push_back(i);
            for(int v:source[i].vars)components[idx].vars.push_back(v);
        }
        component_by_var.assign(assigned.size(),-1);
        for(int i=0;i<int(components.size());i++){
            auto& c=components[i];
            sort(c.vars.begin(),c.vars.end());
            c.vars.erase(unique(c.vars.begin(),c.vars.end()),c.vars.end());
            for(int v:c.vars){
                if(component_by_var[v]!=-1 && component_by_var[v]!=i)
                    throw runtime_error("OMEGA42_COMPONENT_NOT_DISJOINT");
                component_by_var[v]=i;
            }
            map<int,vector<int>> piv;
            for(int id:c.rowids){
                vector<int> left=source[id].vars;
                while(!left.empty()){
                    auto at=piv.find(left.front());
                    if(at==piv.end()){piv.emplace(left.front(),left);break;}
                    vector<int> diff;
                    set_symmetric_difference(left.begin(),left.end(),
                        at->second.begin(),at->second.end(),back_inserter(diff));
                    left=std::move(diff);
                }
            }
            c.static_rank=int(piv.size());
        }
    }
    void dirty_var(int v){
        if(!component_mode || v<=0 || v>=int(component_by_var.size()))return;
        int idx=component_by_var[v];
        if(idx>=0){++components[idx].epoch;++component_dirty_events;}
    }
    void notify_assignment(const vector<int>& lits) override {
        if(component_mode && !lits.empty()) {
            if(next_implied)++stale_proposals_discarded;
            next_implied=0;pending_component=-1;
            outgoing.clear();send_index=0;conflict_component=-1;
        }
        DrnasBridge::notify_assignment(lits);
        for(int lit:lits) dirty_var(abs(lit));
        generation++;
    }
    void notify_backtrack(size_t level) override {
        vector<int> undone;
        if(component_mode && level<marks.size()){
            const size_t start=marks[level];
            for(size_t i=start;i<trail.size();i++)undone.push_back(abs(trail[i]));
        }
        DrnasBridge::notify_backtrack(level);
        for(int v:undone)dirty_var(v);
        generation++;
        outgoing.clear();send_index=0;
        next_implied=0;pending_component=-1;conflict_component=-1;
        for(auto it=explanations.begin();it!=explanations.end();){
            int v=abs(it->first);
            if(v>=int(assigned.size()) || assigned[v]==0 ||
              (assigned[v]>0)!=(it->first>0)) {
                explanation_positions.erase(it->first);
                reason_component.erase(it->first);
                it=explanations.erase(it);
            } else ++it;
        }
    }

    static void xor_row(Omega4Row& a,const Omega4Row& b) {
        vector<int> next;
        set_symmetric_difference(a.remaining.begin(),a.remaining.end(),
                                 b.remaining.begin(),b.remaining.end(),
                                 back_inserter(next));
        a.remaining=std::move(next);
        a.rhs^=b.rhs; a.ancestors^=b.ancestors;
    }

    // Replay immutable source certificates independent from elimination state.
    XorRow source_replay(uint64_t ancestry) {
        XorRow full;
        if(!ancestry) {disabled=true;throw runtime_error("OMEGA4_EMPTY_ANCESTRY");}
        for(size_t i=0;i<source.size();i++)if((ancestry>>i)&1U){
            vector<int> tmp;
            set_symmetric_difference(full.vars.begin(),full.vars.end(),
               source[i].vars.begin(),source[i].vars.end(),back_inserter(tmp));
            full.vars=std::move(tmp);
            full.rhs^=source[i].rhs;
        }
        reason_replays++;
        ++checked_proof_rows;
        sum_proof_depth+=__builtin_popcountll(ancestry);
        return full;
    }

    // A complete assignment to an XOR equation gives a falsified CNF clause.
    // A single free variable gives an implied literal, with ALL currently
    // assigned variables negated. These are entailed by the replayed equation.
    bool make_clause(const Omega4Row& reduced, vector<int>& clause, int& implied) {
        XorRow full=source_replay(reduced.ancestors);
        vector<int> free;
        int rhs=full.rhs;
        for(int v:full.vars){
            if(assigned[v]==0) free.push_back(v);
            else {
                rhs^=(assigned[v]>0);
                clause.push_back(assigned[v]>0 ? -v : v);
            }
        }
        // Two independent representations MUST agree before exporting a reason.
        if(free!=reduced.remaining || rhs!=reduced.rhs) {
            proof_failures++;disabled=true;
            throw runtime_error("OMEGA4_REDUCED_ROW_REPLAY_MISMATCH");
        }
        if(free.size()>1)return false;
        if(free.size()==1){
            implied = rhs ? free[0] : -free[0];
            clause.insert(clause.begin(),implied);
        } else {
            implied=0;
            if(rhs!=1)return false;
        }
        if(clause.empty()){abstentions++;return false;}  // no empty-clause injection
        if(int(clause.size())>max_reason_width){
            skipped_wide++;return false;
        }
        return true;
    }


    // Fast source-structure heuristic: pay only for components touched by
    // new assignments/undos. Score is never a solver truth condition.
    bool worth_component(int idx){
        Component& c=components[idx];
        ++c.visits;
        if(c.visits<=48)return true; // enough initial observations for feedback
        int free_min=1000000;
        for(int id:c.rowids){
            int missing=0;
            for(int v:source[id].vars)missing+=(assigned[v]==0);
            free_min=min(free_min,missing);
        }
        if(free_min<=1)return true; // source-near-unit/conflict; cheap opportunity
        const bool structural_link=c.rowids.size()>1 &&
            c.static_rank<int(c.rowids.size());
        if(structural_link && free_min<=3)return true;
        if((c.used*64 < c.scans) && c.scans>=32){
            // Expensive/low-yield local component: sample 1 in 8 states.
            if((c.visits&7L)!=0L){
                ++c.skips;++component_skips;++component_heuristic_rejections;
                return false;
            }
        }
        return true;
    }

    void scan_components(){
        if(disabled || budget_off)return;
        for(int idx=0;idx<int(components.size());idx++){
            auto& c=components[idx];
            if(c.seen==c.epoch){++component_memo_hits;continue;}
            c.seen=c.epoch;
            if(!worth_component(idx))continue;
            if(++scans>max_scans){budget_off=true;abstentions++;return;}
            ++component_scans;++c.scans;
            auto begin=chrono::steady_clock::now();
            struct Timing {
                Omega4Bridge& b;Component& c;
                chrono::steady_clock::time_point start;
                ~Timing(){
                    uint64_t ns=uint64_t(chrono::duration_cast<chrono::nanoseconds>(
                        chrono::steady_clock::now()-start).count());
                    b.scan_wall_ns+=ns;c.scan_ns+=ns;
                }
            } timing{*this,c,begin};
            map<int,Omega4Row> pivots;
            vector<Omega4Row> contradiction;
            // Eliminate only equations belonging to this source-connected
            // component; other components provably share no source variable.
            for(int id:c.rowids){
                Omega4Row r;r.rhs=source[id].rhs;r.ancestors=1ULL<<id;
                for(int v:source[id].vars){
                    if(assigned[v]==0)r.remaining.push_back(v);
                    else r.rhs^=(assigned[v]>0);
                }
                while(!r.remaining.empty()){
                    auto at=pivots.find(r.remaining.front());
                    if(at==pivots.end()){
                        pivots.emplace(r.remaining.front(),r);break;
                    }
                    xor_row(r,at->second);++row_xors;
                }
                if(r.remaining.empty() && r.rhs)contradiction.push_back(r);
            }
            vector<Omega4Row> basis;
            for(auto& p:pivots)basis.push_back(p.second);
            for(int i=int(basis.size())-1;i>=0;i--){
                int pivot=basis[i].remaining.front();
                for(int j=0;j<i;j++)
                    if(binary_search(basis[j].remaining.begin(),
                         basis[j].remaining.end(),pivot)){
                        xor_row(basis[j],basis[i]);++row_xors;
                    }
            }
            vector<int> best;int implied=0;
            if(!contradiction.empty()){
                for(const auto& r:contradiction){
                    vector<int> cl;int lit=0;
                    if(!make_clause(r,cl,lit))continue;
                    ++conflicts_seen;
                    if(best.empty()||cl.size()<best.size()){
                        best=std::move(cl);implied=0;
                    }
                }
            } else {
                for(const auto& r:basis){
                    if(r.remaining.size()!=1)continue;
                    vector<int> cl;int lit=0;
                    if(!make_clause(r,cl,lit))continue;
                    ++unit_candidates;
                    if(best.empty()||cl.size()<best.size()||
                        (cl.size()==best.size()&&abs(lit)<abs(implied))){
                        best=std::move(cl);implied=lit;
                    }
                }
            }
            if(best.empty())continue;
            if(mode==SHADOW)continue;
            sum_reason_width+=long(best.size());
            ++delivered_reason_count;
            if(implied==0){
                outgoing=std::move(best);send_index=0;
                conflict_component=idx;
                min_conflict_width=min(min_conflict_width,int(outgoing.size()));
                return;
            }
            if(assigned[abs(implied)]==0){
                explanations[implied]=std::move(best);
                explanation_positions[implied]=0;
                reason_component[implied]=idx;
                pending_component=idx;
                next_implied=implied;
                max_accepted_reason_width=max(max_accepted_reason_width,
                                               int(explanations[implied].size()));
                return;
            }
        }
    }

    void scan_live() {
        if(component_mode){scan_components();return;}
        if(disabled || budget_off || generation==scanned_generation)return;
        scanned_generation=generation;
        if(source.empty())return;
        // Cold-start: first 128 distinct trail states always checked.
        // Thereafter, only if accepted reasons per scan are scarce,
        // sample 1 in 8 trail states. Skipping is proof-safe abstention.
        // This rule is computed ONLY from in-solver causal observations.
        if(cost_gate && scans>=128) {
            const long used=completed_reasons+conflict_clauses;
            if(used*64 < scans) {
                ++gate_low_yield_events;
                if((generation&7ULL)!=0ULL){++gated_skips;return;}
            }
        }
        if(++scans>max_scans){budget_off=true;abstentions++;return;}
        if(cost_gate)++gate_active_scans;
        auto scan_start=chrono::steady_clock::now();
        struct ScanTimer{
            Omega4Bridge &b;
            chrono::steady_clock::time_point start;
            ~ScanTimer(){b.scan_wall_ns+=uint64_t(chrono::duration_cast<chrono::nanoseconds>(
                           chrono::steady_clock::now()-start).count());}
        } scan_timer{*this,scan_start};
        // Reduce after substituting real current CDCL trail assignments.
        map<int,Omega4Row> pivots;
        vector<Omega4Row> contradiction;
        for(size_t i=0;i<source.size();i++){
            Omega4Row r;r.rhs=source[i].rhs;r.ancestors=1ULL<<i;
            for(int v:source[i].vars) {
                if(assigned[v]==0)r.remaining.push_back(v);
                else r.rhs^=(assigned[v]>0);
            }
            while(!r.remaining.empty()){
                auto p=pivots.find(r.remaining.front());
                if(p==pivots.end()) {
                    pivots.emplace(r.remaining.front(),r);
                    break;
                }
                xor_row(r,p->second);row_xors++;
            }
            if(r.remaining.empty() && r.rhs) contradiction.push_back(r);
        }
        // Gauss-Jordan back substitution: find implications involving ANY
        // surviving unknown variable, not just direct width-2/3 source rows.
        vector<Omega4Row> basis;
        for(auto& p:pivots)basis.push_back(p.second);
        for(int i=int(basis.size())-1;i>=0;i--){
            int pivot=basis[i].remaining.front();
            for(int j=0;j<i;j++) {
                if(binary_search(basis[j].remaining.begin(),
                                 basis[j].remaining.end(),pivot)){
                    xor_row(basis[j],basis[i]);row_xors++;
                }
            }
        }
        vector<int> best_clause;int best_implied=0;
        if(!contradiction.empty()) {
            for(auto& r:contradiction){
                vector<int> c;int implied=0;
                if(!make_clause(r,c,implied))continue;
                conflicts_seen++;
                if(best_clause.empty() || c.size()<best_clause.size()){
                    best_clause=std::move(c);best_implied=0;
                }
            }
        } else {
            // Unit equations; choose shortest sound explanation.
            for(const auto& r:basis){
                if(r.remaining.size()!=1)continue;
                vector<int> c;int implied=0;
                if(!make_clause(r,c,implied))continue;
                unit_candidates++;
                if(best_clause.empty() || c.size()<best_clause.size() ||
                    (c.size()==best_clause.size() && abs(implied)<abs(best_implied))){
                    best_clause=std::move(c);best_implied=implied;
                }
            }
        }
        if(best_clause.empty())return;
        if(mode==SHADOW)return; // exact same audit, but NEVER affect CDCL.
        sum_reason_width+=long(best_clause.size());
        delivered_reason_count++;
        if(best_implied==0){
            // Every literal is the negation of a currently assigned literal.
            // A CNF conflict clause follows from the source-certified parity.
            outgoing=std::move(best_clause);send_index=0;
            min_conflict_width=min(min_conflict_width,int(outgoing.size()));
        } else if(assigned[abs(best_implied)]==0){
            explanations[best_implied]=std::move(best_clause);
            explanation_positions[best_implied]=0;
            next_implied=best_implied;
            max_accepted_reason_width=max(max_accepted_reason_width,
                                            int(explanations[best_implied].size()));
        }
    }
    int next_implied=0;
    int cb_propagate() override {
        ++callbacks;
        if(mode!=SHADOW && next_implied && assigned[abs(next_implied)]==0){
            int v=next_implied;next_implied=0;proposals++;return v;
        }
        next_implied=0;
        scan_live();
        if(mode==LIVE && next_implied && assigned[abs(next_implied)]==0 &&
           outgoing.empty()){
            int v=next_implied;next_implied=0;proposals++;return v;
        }
        return 0;
    }
    int cb_add_reason_clause_lit(int propagated_lit) override {
        if(mode!=LIVE)return 0;
        auto it=explanations.find(propagated_lit);
        if(it==explanations.end())
            throw runtime_error("OMEGA4_MISSING_REASON_CLAUSE");
        size_t& pos=explanation_positions[propagated_lit];
        if(pos==it->second.size()){
            pos=0;completed_reasons++;
            if(component_mode){
                auto ci=reason_component.find(propagated_lit);
                if(ci!=reason_component.end() && ci->second>=0)
                    ++components[ci->second].used;
            }
            return 0;
        }
        const int lit=it->second[pos++];
        if(component_mode && pos>1){
            // For source-backed reason clauses every antecedent MUST be false
            // on the current CDCL trail when CaDiCaL asks to use the reason.
            const int var=abs(lit);
            if(var<=0||var>=int(assigned.size())||
               assigned[var]==0 || (assigned[var]>0)==(lit>0)){
                ++proof_failures;disabled=true;
                throw runtime_error("OMEGA42_REASON_ANTECEDENT_NOT_FALSE_ON_TRAIL");
            }
            ++checked_reason_lits;
        }
        return lit;
    }
    bool cb_has_external_clause(bool& forgettable) override {
        forgettable=true;
        if(mode==SHADOW || disabled || budget_off)return false;
        if(outgoing.empty())scan_live();
        return !outgoing.empty();
    }
    int cb_add_external_clause_lit() override {
        if(mode!=LIVE)return 0;
        if(send_index<outgoing.size())return outgoing[send_index++];
        if(!outgoing.empty()){
            ++conflict_clauses;
            if(component_mode && conflict_component>=0){
                ++components[conflict_component].used;
                ++components[conflict_component].conflicts;
            }
        }
        outgoing.clear();send_index=0;conflict_component=-1;
        return 0;
    }
};

struct Omega4Terminator final : CaDiCaL::Terminator {
    using Clock=chrono::steady_clock;
    Clock::time_point start=Clock::now();
    double cap_s;
    Omega4Terminator(double cap):cap_s(cap){}
    bool terminate() override {
        return chrono::duration<double>(Clock::now()-start).count()>=cap_s;
    }
};

static void omega4_selftest(){
    // Three rows; no individual source equation or pair determines x1 when
    // x5=1 and x6=0. Their THREE-way XOR yields x1 xor x5 xor x6=0.
    vector<XorRow> src={{{1,2,3},0},{{2,4,5},0},{{3,4,6},0}};
    Omega4Bridge d(src,6,Omega4Bridge::LIVE);
    d.notify_new_decision_level();
    d.notify_assignment({5,-6});
    int first=d.cb_propagate();
    if(first!=1)throw runtime_error("OMEGA4_3WAY_UNIT_MISSING");
    vector<int> reason;
    for(;;){int v=d.cb_add_reason_clause_lit(first);if(!v)break;reason.push_back(v);}
    if(reason!=vector<int>({1,-5,6}))
        throw runtime_error("OMEGA4_3WAY_REASON_WRONG");
    d.notify_assignment({1});d.notify_backtrack(0);
    if(d.disabled || !d.explanations.empty())
        throw runtime_error("OMEGA4_LIVE_BACKTRACK_WRONG");
    d.notify_new_decision_level();d.notify_assignment({-5,-6});
    if(d.cb_propagate()!=-1)
        throw runtime_error("OMEGA4_REASSIGNMENT_WRONG");
    d.notify_backtrack(0);
    d.notify_new_decision_level();d.notify_assignment({-1,5,-6});
    bool forgettable=false;
    if(!d.cb_has_external_clause(forgettable))
        throw runtime_error("OMEGA4_3WAY_CONFLICT_MISSING");
    vector<int> conflict;
    for(;;){int v=d.cb_add_external_clause_lit();if(!v)break;conflict.push_back(v);}
    if(conflict!=vector<int>({1,-5,6}))
        throw runtime_error("OMEGA4_CONFLICT_REASON_WRONG");
    // Independent exhaustive source-equation truth table: both explanations
    // are consequences of ORIGINAL three XOR equations (not solver claims).
    for(int mask=0;mask<64;mask++){
        auto truth=[&](int var){return bool((mask>>(var-1))&1);};
        bool formulas=true;
        for(const auto& r:src){
            int p=0;for(int v:r.vars)p^=truth(v);
            if(p!=r.rhs)formulas=false;
        }
        bool cl=truth(1)||!truth(5)||truth(6);
        if(formulas && !cl)throw runtime_error("OMEGA4_SELFTEST_UNSOUND_REASON");
    }
    Omega4Bridge g(src,6,Omega4Bridge::LIVE,true);
    g.notify_new_decision_level();g.notify_assignment({5,-6});
    if(g.cb_propagate()!=1)throw runtime_error("OMEGA41_GATED_REASON_MISSING");
    g.notify_backtrack(0);
    for(int k=0;k<200;k++){
        g.notify_new_decision_level();
        g.notify_assignment({2});
        g.cb_propagate();
        g.notify_backtrack(0);
    }
    if(g.gated_skips==0)throw runtime_error("OMEGA41_GATING_NOT_TRIGGERED");
    // Source-disjoint fourth equation: assignment to x8 must not invalidate
    // the first component's source-derived reason.
    vector<XorRow> extra=src;
    extra.push_back({{7,8},1});
    Omega4Bridge local(extra,8,Omega4Bridge::LIVE,false,true);
    if(local.components.size()!=2)throw runtime_error("OMEGA42_COMPONENT_SPLIT_WRONG");
    local.notify_new_decision_level();
    local.notify_assignment({5,-6});
    if(local.cb_propagate()!=1)throw runtime_error("OMEGA42_COMPONENT_IMPLICATION_WRONG");
    vector<int> lc;
    for(;;){int v=local.cb_add_reason_clause_lit(1);if(!v)break;lc.push_back(v);}
    if(lc!=vector<int>({1,-5,6}))
        throw runtime_error("OMEGA42_COMPONENT_REASON_WRONG");
    int held=local.components[0].epoch;
    local.notify_assignment({8});
    if(local.components[0].epoch!=uint64_t(held))
        throw runtime_error("OMEGA42_UNRELATED_VARIABLE_DIRTIED_COMPONENT");
    local.notify_backtrack(0);
    if(local.next_implied || !local.explanations.empty())
        throw runtime_error("OMEGA42_BACKTRACK_STALE_REASON");
    local.notify_new_decision_level();
    local.notify_assignment({-1,5,-6});
    bool has=false;bool forget=false;
    has=local.cb_has_external_clause(forget);
    if(!has)throw runtime_error("OMEGA42_COMPONENT_CONFLICT_NOT_FOUND");
    vector<int> cx;
    for(;;){int v=local.cb_add_external_clause_lit();if(!v)break;cx.push_back(v);}
    if(cx!=vector<int>({1,-5,6}))
        throw runtime_error("OMEGA42_COMPONENT_CONFLICT_REASON_WRONG");
    local.notify_backtrack(0);
    Omega4Bridge sh(src,6,Omega4Bridge::SHADOW);
    sh.notify_new_decision_level();sh.notify_assignment({5,-6});
    if(sh.cb_propagate()!=0 || sh.unit_candidates==0 || sh.proposals!=0)
        throw runtime_error("OMEGA4_SHADOW_NOT_MATCHED");
    // No unverified row should ever be accepted or injected.
    cout<<"OMEGA42_SELFTEST_PASS 3way_source_rows=3 unit=1 conflict=1 "
        <<"reason_width=3 rollback=1 shadow=1 gated=1 local_components=2 independent_64_assignments=1\n";
}

static int omega4_run(const string& mode,const string& src,const string& tsv,double cap_s){
    CaDiCaL::Solver solver;int n=0;auto original=load_cnf(src,solver,n);
    vector<XorRow> rows=mode=="clean" ? vector<XorRow>{}:load_rows(tsv,n);
    if(rows.size()>32)throw runtime_error("OMEGA4_TOO_MANY_SOURCE_ROWS");
    bool shadow=(mode=="shadow" || mode=="component_shadow");
    bool local=(mode=="component" || mode=="component_shadow");
    Omega4Bridge bridge(std::move(rows),n,shadow?
                 Omega4Bridge::SHADOW:Omega4Bridge::LIVE,
                 mode=="gated",local);
    if(mode!="clean"&&!bridge.source.empty()){
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto& r:bridge.source)for(int v:r.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    Omega4Terminator timer(cap_s);
    solver.connect_terminator(&timer);
    auto start=chrono::steady_clock::now();
    int result=solver.solve();
    double elapsed=chrono::duration<double>(
        chrono::steady_clock::now()-start).count();
    solver.disconnect_terminator();
    if(result!=10 && result!=20 && result!=0)
        throw runtime_error("OMEGA4_UNEXPECTED_RESULT");
    if(result==10) {
        for(const auto& c:original) {
            bool ok=false;
            for(int lit:c) {
                int val=solver.val(abs(lit));
                if(val && ((val>0)==(lit>0))) {ok=true;break;}
            }
            if(!ok)throw runtime_error("OMEGA4_ORIGINAL_SAT_MODEL_WRONG");
        }
        cout<<"v ";
        for(int v=1;v<=n;v++){
            int val=solver.val(v);
            if(val)cout<<(val>0?v:-v)<<" ";
        }
        cout<<"0\n";
    }
    if(bridge.disabled || bridge.proof_failures)
        throw runtime_error("OMEGA4_PROOF_SAFETY_FAILURE");
    cout<<fixed<<setprecision(6)
        <<"OMEGA42_RESULT mode="<<mode
        <<" status="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
        <<" solve_s="<<elapsed
        <<" source_rows="<<bridge.source.size()
        <<" callback_events="<<bridge.callbacks
        <<" trail_assignments="<<bridge.notifications
        <<" backtracks="<<bridge.backtracks
        <<" online_scans="<<bridge.scans
        <<" gf2_row_xors="<<bridge.row_xors
        <<" unit_candidates="<<bridge.unit_candidates
        <<" conflicts_seen="<<bridge.conflicts_seen
        <<" unit_proposals="<<bridge.proposals
        <<" completed_reasons="<<bridge.completed_reasons
        <<" conflict_clauses="<<bridge.conflict_clauses
        <<" reason_replays="<<bridge.reason_replays
        <<" skipped_wide="<<bridge.skipped_wide
        <<" budget_off="<<bridge.budget_off
        <<" verified_sat="<<(result==10?1:0)
        <<" unsafe_claims="<<bridge.proof_failures
        <<" gate_low_yield_events="<<bridge.gate_low_yield_events
        <<" gated_skips="<<bridge.gated_skips
        <<" gated_scans="<<bridge.gate_active_scans
        <<" scan_wall_ns="<<bridge.scan_wall_ns
        <<" checked_proof_rows="<<bridge.checked_proof_rows
        <<" sum_proof_depth="<<bridge.sum_proof_depth
        <<" sum_reason_width="<<bridge.sum_reason_width
        <<" delivered_reason_count="<<bridge.delivered_reason_count
        <<" component_count="<<bridge.components.size()
        <<" component_scans="<<bridge.component_scans
        <<" component_skips="<<bridge.component_skips
        <<" component_memo_hits="<<bridge.component_memo_hits
        <<" component_dirty_events="<<bridge.component_dirty_events
        <<" component_heuristic_rejections="<<bridge.component_heuristic_rejections
        <<" stale_proposals_discarded="<<bridge.stale_proposals_discarded
        <<" checked_reason_lits="<<bridge.checked_reason_lits<<"\n";
    cout<<"OMEGA4_STATS_BEGIN mode="<<mode<<"\n"<<flush;
    solver.statistics();
    cout<<"OMEGA4_STATS_END mode="<<mode<<"\n"<<flush;
    return result;
}
int main(int argc,char** argv) {
    try{
        if(argc==2 && string(argv[1])=="selftest"){
            omega4_selftest();return 0;
        }
        if(argc!=5)
            throw runtime_error("usage: omega42 clean|shadow|live|gated|component|component_shadow ORIGINAL.cnf CERTIFIED.tsv CAP");
        string mode=argv[1];
        if(mode!="clean"&&mode!="shadow"&&mode!="live"&&mode!="gated"&&
           mode!="component"&&mode!="component_shadow")
            throw runtime_error("OMEGA4_UNKNOWN_MODE");
        double cap=stod(argv[4]);
        if(cap<0.05 || cap>120.0)
            throw runtime_error("OMEGA4_BAD_CAP");
        return omega4_run(mode,argv[2],argv[3],cap);
    }catch(const exception& e) {
        cerr<<"OMEGA4_FAIL_CLOSED "<<e.what()<<"\n";return 2;
    }
}

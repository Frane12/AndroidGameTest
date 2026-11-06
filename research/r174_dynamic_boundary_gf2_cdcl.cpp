// R172: workload-independent GF2 budget backoff, unchanged source CNF/reasons.
// R170: first emitted and actually consumed GF2 reason timestamps; R169 logic unchanged.
// R168: source-certified GF2 Gaussian residual closure and CDCL↔GF2 feedback.
// Every derived reason is reconstructed from an XOR of independently source-certified equations.
// Research only; source CNF untouched. Inherits R165 fail-closed watchers and lazy reasons.
// R165: R165 controls + WATCH-LAZY GF2 fast path + reversible per-component cooldown.
// R158x causal CDCL/GF2: preserve source-certified IPASIR-UP direct reasons.
// All native trial modes compiled ONCE into the same binary; timeout via
// CaDiCaL Terminator exposes genuine conflict/decision/propagation counters.
// R157 live GF(2) CDCL: original R148 proven reason & reversible watch design
// with timeout-surviving propagation progress telemetry. Source rows are
// independently certified from original SHA CNF before solver invocation.
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

class R162Bridge final : public DrnasBridge {
public:
    enum Mode { FREEZE, WATCH, CLAUSE, DIRECT, SHADOW };
    Mode mode;
    std::map<int,std::vector<int>> reasons;
    std::map<int,size_t> reason_pos;
    long direct_proposals=0, direct_reason_requests=0;
    long direct_reason_lits=0, direct_ready_checks=0;
    long direct_no_units=0, direct_expired=0;
    size_t peak_reason_cache=0;
    bool adaptive_gate=false;
    long adaptive_gate_events=0;
    long reason_clauses_completed=0;
    long shadow_candidates=0;
    long source_direct_admissions=0;
    bool component_feedback=false;
    vector<int> component_of_row;
    vector<long> component_scans, component_proposals, component_reasons;
    vector<unsigned char> component_blocked;
    map<int,int> reason_component;
    long component_gate_events=0, suppressed_rows=0;
    long component_scan_gate=4096; // 32768 in R165 full mode: protect sparse but useful GF(2) components
    uint64_t propagate_ns=0, propagate_calls=0;
    size_t component_count=0;
    // R165: two-watch fast rejection eliminates full-row parity scanning
    // without the 504M R165 per-incidence updates. Source-certified rows
    // and complete literal reasons remain unchanged.
    bool watchlazy_enabled=false, cooldown_enabled=false;
    long cheap_watch_rejects=0, watch_invariant_audits=0;
    vector<long> component_sleep_until, component_epoch_start;
    vector<long> component_epoch_proposal_start, component_epoch_reason_start;
    vector<long> component_sleep_episodes;
    long cooldown_wakes=0, cooldown_skips=0;
    uint64_t assignment_notify_ns=0, backtrack_notify_ns=0, incremental_upd_ns=0;
    bool incremental_enabled=false;
    bool two_way_enabled=false, two_way_early=false, two_way_novel_only=false, two_way_shadow=false;
    bool two_way_utility_budget=false;
    // Only scheduling is adaptive; all exported reasons remain certified.
    bool two_way_dynamic=false;
    vector<vector<size_t>> r174_component_rows;
    vector<vector<int>> r174_var_components;
    vector<long> r174_boundary, r174_dirty_epoch, r174_scanned_epoch;
    vector<long> r174_next_notify, r174_misses, r174_sweeps, r174_used, r174_last_used_seen;
    map<int,int> r174_reason_component;
    long r174_dirty_events=0, r174_component_skips=0, r174_boundary_skips=0;
    long r174_sweeps_total=0, r174_feedback_resets=0, r174_last_selected=-1;
    long two_way_sweeps=0, two_way_row_xors=0, two_way_proposals=0;
    long two_way_candidates=0, two_way_multi_source_candidates=0;
    long two_way_source_duplicate_units=0, two_way_shadow_candidates=0;
    long two_way_used_reasons=0, two_way_evidence_samples=0;
    // R170: first event timestamps are measured in the same monotonic clock
    // as solve(); this is event telemetry, not an assertion of speedup.
    chrono::steady_clock::time_point r170_benchmark_start=chrono::steady_clock::now();
    long r170_first_proposal_ms=-1, r170_first_used_ms=-1;
    long r170_first_proposal_notifications=-1, r170_first_used_notifications=-1;
    set<int> two_way_reason_keys;
    long two_way_abstentions=0, last_two_way_notifications=-8192;
    uint64_t two_way_ns=0;
    vector<vector<size_t>> row_incidence;
    vector<int> row_unassigned, row_parity;
    long incremental_row_events=0, incremental_reason_checks=0;
    void initialize_incremental() {
        row_incidence.assign(assigned.size(),{});
        row_unassigned.clear(); row_parity.clear();
        row_unassigned.reserve(rows.size()); row_parity.reserve(rows.size());
        for(size_t idx=0;idx<rows.size();++idx){
            row_unassigned.push_back(int(rows[idx].vars.size()));
            row_parity.push_back(0);
            for(int v:rows[idx].vars) row_incidence[v].push_back(idx);
        }
    }
    void incremental_update(int lit,bool add){
        for(size_t idx:row_incidence[abs(lit)]){
            row_unassigned[idx]+=add?-1:1;
            row_parity[idx]^=(lit>0);
            ++incremental_row_events;
            if(row_unassigned[idx]<0 || row_unassigned[idx]>int(rows[idx].vars.size()))
                throw runtime_error("R165_ROW_STATE_RANGE");
        }
    }
    long components_with_reasons() const {
        return count_if(component_reasons.begin(),component_reasons.end(),[](long x){return x>0;});
    }
    long blocked_components() const {
        return count_if(component_blocked.begin(),component_blocked.end(),[](unsigned char x){return x!=0;});
    }
    void initialize_components() {
        vector<int> parent(assigned.size());
        for(size_t v=0;v<parent.size();++v)parent[v]=int(v);
        auto root=[&parent](int v) {
            while(parent[v]!=v){parent[v]=parent[parent[v]];v=parent[v];}
            return v;
        };
        for(const auto &r:rows) for(size_t k=1;k<r.vars.size();++k)
            parent[root(r.vars[k])]=root(r.vars[0]);
        map<int,int> ids;
        for(const auto &r:rows) {
            const int rt=root(r.vars[0]);
            auto it=ids.find(rt);
            if(it==ids.end())it=ids.emplace(rt,int(ids.size())).first;
            component_of_row.push_back(it->second);
        }
        component_count=ids.size();
        component_scans.assign(component_count,0);
        component_proposals.assign(component_count,0);
        component_reasons.assign(component_count,0);
        component_blocked.assign(component_count,0);
        component_sleep_until.assign(component_count,0);
        component_epoch_start.assign(component_count,0);
        component_epoch_proposal_start.assign(component_count,0);
        component_epoch_reason_start.assign(component_count,0);
        component_sleep_episodes.assign(component_count,0);
        r174_component_rows.assign(component_count,{});
        r174_var_components.assign(assigned.size(),{});
        for(size_t i=0;i<rows.size();++i){
            const int ci=component_of_row[i];
            r174_component_rows[ci].push_back(i);
            for(int v:rows[i].vars)r174_var_components.at(v).push_back(ci);
        }
        for(auto &v:r174_var_components){
            sort(v.begin(),v.end());
            v.erase(unique(v.begin(),v.end()),v.end());
        }
        r174_boundary.assign(component_count,0);
        r174_dirty_epoch.assign(component_count,1);
        r174_scanned_epoch.assign(component_count,0);
        r174_next_notify.assign(component_count,0);
        r174_misses.assign(component_count,0);
        r174_sweeps.assign(component_count,0);
        r174_used.assign(component_count,0);
        r174_last_used_seen.assign(component_count,0);
    }
    void r174_mark_dirty(int lit,bool rollback=false){
        const int v=abs(lit);
        if(v<=0 || v>=(int)r174_var_components.size())
            throw runtime_error("R174_DIRTY_VAR_RANGE");
        for(int ci:r174_var_components[v]){
            ++r174_dirty_epoch[ci];++r174_dirty_events;
            if(rollback){r174_next_notify[ci]=0;r174_misses[ci]=0;}
        }
    }

    unsigned long callback_events=0;
    chrono::steady_clock::time_point last_telemetry=chrono::steady_clock::now();
    void notify_assignment(const vector<int>&lits) override {
        auto notify_begin=chrono::steady_clock::now();
        size_t old_trail=trail.size();
        DrnasBridge::notify_assignment(lits);
        auto before_incremental=chrono::steady_clock::now();
        if(incremental_enabled && !disabled)
            for(size_t k=old_trail;k<trail.size();++k) incremental_update(trail[k],true);
        if(two_way_dynamic && !disabled)
            for(size_t k=old_trail;k<trail.size();++k)r174_mark_dirty(trail[k]);
        auto notify_end=chrono::steady_clock::now();
        assignment_notify_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(notify_end-notify_begin).count();
        if(incremental_enabled)
            incremental_upd_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(notify_end-before_incremental).count();
        // A bounded, low-cost telemetry checkpoint that survives external
        // timeout, so real mixed SAT search activity can be measured.
        if(mode!=DIRECT && mode!=SHADOW) return;
        if((++callback_events & 4095UL)!=0) return;
        auto now=chrono::steady_clock::now();
        if(now-last_telemetry < chrono::seconds(1))return;
        last_telemetry=now;
        cout<<"R157_PROGRESS mode=direct assignments="<<notifications
            <<" backtracks="<<backtracks
            <<" rows_scanned="<<rows_scanned
            <<" direct_proposals="<<direct_proposals
            <<" reason_requests="<<direct_reason_requests
            <<" budget_off="<<budget_off
            <<" disabled="<<disabled<<"\n"<<flush;
    }

    R162Bridge(vector<XorRow> input, int n, Mode m):
        DrnasBridge(std::move(input),n,m!=FREEZE,m==CLAUSE),mode(m) {initialize_components();}

    void notify_backtrack(size_t level) override {
        auto backtrack_start=chrono::steady_clock::now();
        vector<int> undone;
        if((incremental_enabled || two_way_dynamic) && level<marks.size()){
            size_t start=marks[level];
            if(start>trail.size()) throw runtime_error("R165_BAD_BACKTRACK_MARK");
            undone.assign(trail.begin()+start,trail.end());
        }
        DrnasBridge::notify_backtrack(level);
        // CDCL trail changed: invalidate residual basis schedule after rollback.
        if(two_way_enabled)last_two_way_notifications=-8192;
        if(incremental_enabled && !disabled)
            for(auto it=undone.rbegin();it!=undone.rend();++it)
                incremental_update(*it,false);
        if(two_way_dynamic && !disabled)
            for(auto it=undone.rbegin();it!=undone.rend();++it)
                r174_mark_dirty(*it,true);
        for(auto it=reasons.begin();it!=reasons.end();) {
            int v=abs(it->first);
            if(v<=0 || v>=(int)assigned.size() || assigned[v]==0) {
                reason_pos.erase(it->first);
                reason_component.erase(it->first);
                two_way_reason_keys.erase(it->first);
                r174_reason_component.erase(it->first);
                it=reasons.erase(it);
                ++direct_expired;
            } else ++it;
        }
        backtrack_notify_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
            chrono::steady_clock::now()-backtrack_start).count();
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


    // R168: compute a sparse echelon basis after actual CDCL assignments.
    // A basis row carries a GF(2) provenance bitset over *original*, independently
    // source-certified equations. A residual unit is converted to a clause by
    // reconstructing the full XOR sum, never from a guessed parity pattern.
    // CDCL callbacks update assigned[] and backtracking restores it; we never
    // publish an unproved row or change a source clause.
    int propagate_gaussian_residual() {
        if(!two_way_enabled || disabled || rows.empty() || rows.size()>512)
            return 0;
        // R174 scans only newly affected residual-linked XOR components.
        // R172 controls retain their original global scheduling unchanged.
        int chosen=-1;
        vector<size_t> scan_ids;
        if(two_way_dynamic){
            if(two_way_sweeps>=256)return 0;
            long best=-9223372036854775807LL;
            for(size_t ci=0;ci<component_count;++ci){
                if(r174_component_rows[ci].empty())continue;
                if(r174_boundary[ci]==0 && r174_used[ci]==0){
                    ++r174_boundary_skips;continue;
                }
                if(r174_dirty_epoch[ci]<=r174_scanned_epoch[ci] ||
                   notifications<r174_next_notify[ci]){
                    ++r174_component_skips;continue;
                }
                const long score=32L*min(32L,r174_boundary[ci])+
                    16L*min(16L,r174_used[ci])+
                    min(64L,r174_dirty_epoch[ci]-r174_scanned_epoch[ci])-
                    8L*min(16L,r174_misses[ci]);
                if(score>best){best=score;chosen=int(ci);}
            }
            if(chosen<0)return 0;
            r174_last_selected=chosen;
            scan_ids=r174_component_rows[chosen];
            if(scan_ids.size()>256)return 0; // fail-closed work budget
            if(r174_sweeps[chosen]){
                if(r174_used[chosen]>r174_last_used_seen[chosen]){
                    r174_misses[chosen]=0;++r174_feedback_resets;
                } else r174_misses[chosen]=min(8L,r174_misses[chosen]+1);
            }
            r174_last_used_seen[chosen]=r174_used[chosen];
            r174_scanned_epoch[chosen]=r174_dirty_epoch[chosen];
            r174_next_notify[chosen]=notifications+
                min(8192L,32L<<min(8L,r174_misses[chosen]));
            ++r174_sweeps[chosen];++r174_sweeps_total;
        }else{
            const bool backoff=two_way_utility_budget && two_way_sweeps>=16 &&
                               two_way_used_reasons==0;
            const long gap=backoff?8192L:(two_way_early?512L:8192L);
            const long max_sweeps=backoff?64L:256L;
            if(two_way_sweeps>=max_sweeps || (last_two_way_notifications>=0 &&
               notifications-last_two_way_notifications<gap))return 0;
            for(size_t i=0;i<rows.size();++i)scan_ids.push_back(i);
        }
        auto start=chrono::steady_clock::now();
        ++two_way_sweeps;last_two_way_notifications=notifications;
        struct Residual {
            vector<int> free_vars;
            int rhs=0;
            vector<uint64_t> provenance;
        };
        const size_t words=(rows.size()+63)/64;
        map<int,Residual> basis;
        for(size_t i:scan_ids){
            Residual x;
            x.rhs=rows[i].rhs;
            x.provenance.assign(words,0);
            x.provenance[i/64]|=uint64_t(1)<<(i%64);
            for(int v:rows[i].vars){
                const int a=assigned.at(v);
                if(a==0)x.free_vars.push_back(v);
                else x.rhs^=(a>0);
            }
            while(!x.free_vars.empty()){
                const int pivot=x.free_vars.front();
                auto it=basis.find(pivot);
                if(it==basis.end()){
                    basis.emplace(pivot,std::move(x));
                    break;
                }
                vector<int> reduced;
                set_symmetric_difference(x.free_vars.begin(),x.free_vars.end(),
                    it->second.free_vars.begin(),it->second.free_vars.end(),
                    back_inserter(reduced));
                x.free_vars=std::move(reduced);
                x.rhs^=it->second.rhs;
                for(size_t w=0;w<words;++w)
                    x.provenance[w]^=it->second.provenance[w];
                ++two_way_row_xors;
            }
            // A zero-variable contradiction is left to native CDCL, whose
            // original CNF is complete; no unsupported conflict is emitted.
        }
        for(const auto& entry:basis){
            const Residual& x=entry.second;
            if(x.free_vars.size()!=1)continue;
            const int target=x.free_vars[0];
            if(assigned[target]!=0)continue;
            const int implied=x.rhs?target:-target;
            if(reasons.count(implied))continue;
            ++two_way_candidates;
            long proof_rows=0;
            for(uint64_t word:x.provenance)proof_rows+=__builtin_popcountll(word);
            if(proof_rows>=2)++two_way_multi_source_candidates;
            if(two_way_novel_only && proof_rows<2){
                ++two_way_source_duplicate_units;continue;
            }
            vector<int> original;
            int original_rhs=0;
            for(size_t j=0;j<rows.size();++j){
                if(!(x.provenance[j/64]&(uint64_t(1)<<(j%64))))continue;
                vector<int> next;
                set_symmetric_difference(original.begin(),original.end(),
                    rows[j].vars.begin(),rows[j].vars.end(),
                    back_inserter(next));
                original=std::move(next);
                original_rhs^=rows[j].rhs;
            }
            // Independently replay the provenance using current assignment;
            // refusing an inconsistency is safer than fabricating a reason.
            int free_count=0, assigned_parity=0, only=0;
            vector<int> clause{implied};
            for(int v:original){
                int a=assigned.at(v);
                if(a==0){++free_count;only=v;}
                else {assigned_parity^=(a>0);clause.push_back(a>0?-v:v);}
            }
            if(free_count!=1 || only!=target ||
               ((assigned_parity^original_rhs)!=x.rhs))
                throw runtime_error("R168_DERIVED_REASON_REPLAY_MISMATCH");
            // Bound explanation size; do not claim benefit where the derived
            // XOR is too wide for this research mode.
            if(clause.size()<2 || clause.size()>32){
                ++two_way_abstentions;
                continue;
            }
            // Strict novel-only: no certified single source row can already
            // yield this literal under the current CDCL trail.
            if(two_way_novel_only){
                bool duplicate=false;
                for(const auto& row:rows){
                    int remaining=0, free_var=0, parity=0;
                    for(int v:row.vars){
                        int a=assigned.at(v);
                        if(!a){++remaining;free_var=v;if(remaining>1)break;}
                        else parity^=(a>0);
                    }
                    if(remaining==1 && free_var==target &&
                       (((parity^row.rhs)!=0)?target:-target)==implied){
                        duplicate=true;break;
                    }
                }
                if(duplicate){++two_way_source_duplicate_units;continue;}
            }
            if(two_way_shadow){
                ++two_way_shadow_candidates;
                two_way_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
                    chrono::steady_clock::now()-start).count();
                return 0;
            }
            if(two_way_evidence_samples<8){
                ++two_way_evidence_samples;
                cout<<"R169_PROOF_CANDIDATE multi_source_rows="<<proof_rows
                    <<" residual_free_vars="<<x.free_vars.size()
                    <<" reason_len="<<clause.size()
                    <<" source_certified=1\n"<<flush;
            }
            reasons[implied]=std::move(clause);
            reason_pos[implied]=0;
            two_way_reason_keys.insert(implied);
            if(two_way_dynamic && chosen>=0)r174_reason_component[implied]=chosen;
            ++direct_proposals;
            ++two_way_proposals;
            if(r170_first_proposal_ms<0){
                r170_first_proposal_ms=long(chrono::duration<double,milli>(
                    chrono::steady_clock::now()-r170_benchmark_start).count());
                r170_first_proposal_notifications=notifications;
            }
            peak_reason_cache=max(peak_reason_cache,reasons.size());
            two_way_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
                chrono::steady_clock::now()-start).count();
            return implied;
        }
        ++two_way_abstentions;
        two_way_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
            chrono::steady_clock::now()-start).count();
        return 0;
    }

    // IPASIR-UP: return a directly implied literal; the immutable reason
    // is cached before return, rather than reconstructing from a later trail.
    int cb_propagate() override {
        struct ScopeNs {
            uint64_t &total;
            chrono::steady_clock::time_point begin;
            ~ScopeNs() {total+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
                chrono::steady_clock::now()-begin).count();}
        } scope{propagate_ns,chrono::steady_clock::now()};
        ++propagate_calls;
        if ((mode!=DIRECT && mode!=SHADOW) || disabled || budget_off) return 0;
        while(next_dirty<dirty.size()) {
            const size_t idx=dirty[next_dirty++];
            if(idx>=rows.size()) {disabled=true;return 0;}
            queued[idx]=0;
            const int ci=component_of_row[idx];
            if(component_feedback && component_blocked[ci]) {
                ++suppressed_rows; continue;
            }
            // R165: NEVER permanently disable an XOR component. Skip
            // work for bounded notification epochs, then wake and probe.
            if(cooldown_enabled && component_sleep_until[ci]!=0){
                if(notifications < component_sleep_until[ci]){
                    ++cooldown_skips; ++suppressed_rows; continue;
                }
                component_sleep_until[ci]=0;
                component_epoch_start[ci]=component_scans[ci];
                component_epoch_proposal_start[ci]=component_proposals[ci];
                component_epoch_reason_start[ci]=component_reasons[ci];
                ++cooldown_wakes;
            }
            ++component_scans[ci];
            // Fail-safe per-component abstention; original CNF remains intact.
            if(component_feedback && component_scans[ci]>=component_scan_gate &&
               component_proposals[ci]<2 && component_reasons[ci]==0) {
                component_blocked[ci]=1;
                ++component_gate_events; ++suppressed_rows;
                continue;
            }
            if(cooldown_enabled && component_scans[ci]-component_epoch_start[ci]>=32768 &&
               component_proposals[ci]-component_epoch_proposal_start[ci]<2 &&
               component_reasons[ci]-component_epoch_reason_start[ci]==0) {
                // Exponential but BOUNDED cooldown, not a permanent veto.
                const long shift=min(5L,component_sleep_episodes[ci]);
                component_sleep_until[ci]=notifications+(65536L<<shift);
                ++component_sleep_episodes[ci];
                ++component_gate_events; ++suppressed_rows;
                continue;
            }
            ++direct_ready_checks;
            // R165 fast filter: no full-row scan until an actual XOR unit
            // is possible. Each (un)assignment updates only incident rows.
            if(incremental_enabled && row_unassigned[idx]!=1){
                ++rows_scanned; ++direct_no_units; continue;
            }
            if(watchlazy_enabled){
                // Exact two-watch invariant: when a row has exactly one
                // unassigned variable, exactly one of its TWO watches is
                // unassigned. If both watch states match, no unit exists.
                // Audit a deterministic sample against the full source row.
                const bool a=(assigned[watch_a[idx]]==0);
                const bool b=(assigned[watch_b[idx]]==0);
                if(a==b){
                    ++cheap_watch_rejects;
                    if((cheap_watch_rejects & 16383L)==1){
                        ++watch_invariant_audits;
                        int nfree=0;
                        for(int v:rows[idx].vars)nfree+=(assigned[v]==0);
                        if(nfree==1)throw runtime_error("R165_WATCH_UNIT_INVARIANT");
                    }
                    ++rows_scanned; ++direct_no_units; continue;
                }
            }
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
            if(incremental_enabled){
                ++incremental_reason_checks;
                if(unknown!=row_unassigned[idx] || assigned_parity!=row_parity[idx])
                    throw runtime_error("R165_INCREMENTAL_PARITY_MISMATCH");
            }
            // Runtime budget is ONLY a selective abstention; already-proven
            // source equations and existing reasons are never altered.
            if(adaptive_gate && rows_scanned>=100000 && direct_proposals<3) {
                ++adaptive_gate_events;
                budget_off=true;
                dirty.clear(); next_dirty=0;
                fill(queued.begin(),queued.end(),0);
                return 0;
            }
            if(unknown!=1) { ++direct_no_units; continue; }
            const int implied=((assigned_parity ^ row.rhs)!=0) ? unassigned : -unassigned;
            // The XOR equation entails this CNF reason under all assignments.
            // The reason starts with the propagated literal as expected by
            // CaDiCaL and includes all negated current row assignments.
            clause.insert(clause.begin(),implied);
            if(clause.size()<2 || clause.size()!=row.vars.size()) {
                disabled=true;return 0;
            }
            if(mode==SHADOW) {
                // Exact same parity check, but never affect the CDCL trail:
                // isolates work of observing and scanning from utility.
                ++shadow_candidates;
                continue;
            }
            reasons[implied]=std::move(clause);
            reason_pos[implied]=0;
            ++direct_proposals;
            ++component_proposals[ci];
            reason_component[implied]=ci;
            peak_reason_cache=max(peak_reason_cache,reasons.size());
            return implied;
        }
        dirty.clear(); next_dirty=0;
        if(two_way_enabled)return propagate_gaussian_residual();
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
        if(pos==it->second.size()) {
            ++reason_clauses_completed;
            if(two_way_reason_keys.erase(propagated_lit)>0){
                ++two_way_used_reasons;
                auto where=r174_reason_component.find(propagated_lit);
                if(where!=r174_reason_component.end()){
                    ++r174_used[where->second];
                    r174_next_notify[where->second]=0;
                    r174_reason_component.erase(where);
                }
                if(r170_first_used_ms<0){
                    r170_first_used_ms=long(chrono::duration<double,milli>(
                        chrono::steady_clock::now()-r170_benchmark_start).count());
                    r170_first_used_notifications=notifications;
                }
            }
            auto c=reason_component.find(propagated_lit);
            if(c!=reason_component.end())++component_reasons[c->second];
            pos=0;
            return 0;
        }
        ++direct_reason_lits;
        return it->second[pos++];
    }

    static void selftest() {
        // 1 xor 2 xor 3 = 0; if 1 and 2 are true then -3 must follow.
        vector<XorRow> x{{{1,2,3},0}};
        R162Bridge b(std::move(x),3,DIRECT);
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
        R162Bridge wake({{{1,2,3},0}},3,DIRECT);
        wake.watchlazy_enabled=true;
        wake.cooldown_enabled=true;
        wake.component_scans[0]=32767;
        wake.notify_new_decision_level();
        wake.notify_assignment({1,2});
        if(wake.cb_propagate()!=0 || wake.component_gate_events!=1 ||
           wake.component_sleep_until[0]<=wake.notifications)
            throw runtime_error("R165_COOLDOWN_SLEEP_SELFTEST_FAIL");
        wake.enqueue_ready(0);
        if(wake.cb_propagate()!=0 || wake.cooldown_skips!=1)
            throw runtime_error("R165_COOLDOWN_SKIP_SELFTEST_FAIL");
        wake.notifications=wake.component_sleep_until[0];
        wake.enqueue_ready(0);
        if(wake.cb_propagate()!=-3 || wake.cooldown_wakes!=1)
            throw runtime_error("R165_COOLDOWN_WAKE_SELFTEST_FAIL");
        cout<<"R165_COOLDOWN_REAWAKEN_SELFTEST_PASS"<<endl;
        R162Bridge lazy({{{1,2,3},0}},3,DIRECT);
        lazy.watchlazy_enabled=true;
        lazy.notify_new_decision_level();
        lazy.notify_assignment({1,2});
        if(lazy.cb_propagate()!=-3)throw runtime_error("R165_LAZY_UNIT_TEST_FAIL");
        lazy.notify_assignment({-3});
        lazy.notify_backtrack(0);
        if(lazy.disabled)throw runtime_error("R165_LAZY_BACKTRACK_TEST_FAIL");
        cout<<"R165_LAZY_SOURCE_REASON_SELFTEST_PASS"<<endl;
        R162Bridge gate({{{1,2,3},0}},3,DIRECT);
        gate.component_feedback=true;
        gate.component_scans[0]=4095;
        gate.notify_new_decision_level();
        gate.notify_assignment({1,2});
        if(gate.cb_propagate()!=0 || gate.component_gate_events!=1 ||
           gate.disabled || gate.reasons.size()!=0)
            throw runtime_error("R165_COMPONENT_GATE_SELFTEST_FAIL");
        cout<<"R165_COMPONENT_GATE_SELFTEST_PASS"<<endl;
    }
};


struct R162Clock final : CaDiCaL::Terminator {
    using Clock=chrono::steady_clock;
    Clock::time_point start=Clock::now();
    Clock::time_point last=start;
    double cap_s;
    const R162Bridge& bridge;
    string mode;
    R162Clock(double cap,const R162Bridge&b,string m):
        cap_s(cap),bridge(b),mode(move(m)) {}
    bool terminate() override {
        const auto now=Clock::now();
        const double secs=chrono::duration<double>(now-start).count();
        if(chrono::duration<double>(now-last).count()>=1.0){
            last=now;
            cout<<"R165_PROGRESS mode="<<mode
                <<" elapsed="<<fixed<<setprecision(3)<<secs
                <<" assignments="<<bridge.notifications
                <<" backtracks="<<bridge.backtracks
                <<" rows_scanned="<<bridge.rows_scanned
                <<" watch_lookups="<<bridge.watch_lookups
                <<" proposals="<<bridge.direct_proposals
                <<" completed_reasons="<<bridge.reason_clauses_completed
                <<" shadow_candidates="<<bridge.shadow_candidates
                <<" adaptive_gate_events="<<bridge.adaptive_gate_events
                <<" disabled="<<bridge.disabled
                <<"\n"<<flush;
        }
        return secs>=cap_s;
    }
};
static int r162_run(const string& mode,const string& src,
                     const string& proof,double cap_s) {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    const bool clean=mode=="clean";
    vector<XorRow> certified=clean?vector<XorRow>{}:load_rows(proof,n);
    const size_t source_rows=certified.size();
    const bool extend=!clean;
    const size_t max_extra=(mode=="direct_full"||mode=="direct_full_feedback"||
                            mode=="direct_incremental"||mode=="direct_watchlazy"||
                            mode=="direct_cooldown"||mode=="direct_two_way"||
                            mode=="direct_two_way_early"||
                            mode=="direct_two_way_newonly"||
                            mode=="direct_two_way_budget"||
                            mode=="direct_two_way_shadow")?128:32;
    if(extend)certified=gf2_pairwise_closure(certified,max_extra);
    const long derived=(long)certified.size()-(long)source_rows;
    R162Bridge::Mode m=clean?R162Bridge::FREEZE:
         mode=="watch_boundary"?R162Bridge::WATCH:
         mode=="shadow_boundary"?R162Bridge::SHADOW:R162Bridge::DIRECT;
    R162Bridge bridge(std::move(certified),n,m);
    bridge.adaptive_gate=(mode=="direct_boundary");
    bridge.component_feedback=(mode=="direct_feedback"||mode=="direct_full_feedback");
    bridge.component_scan_gate=(mode=="direct_full_feedback"?32768:4096);
    bridge.incremental_enabled=(mode=="direct_incremental");
    bridge.two_way_enabled=(mode=="direct_two_way"||
                            mode=="direct_two_way_early"||
                            mode=="direct_two_way_newonly"||
                            mode=="direct_two_way_budget"||
                            mode=="direct_two_way_shadow");
    bridge.two_way_early=(mode=="direct_two_way_early"||
                          mode=="direct_two_way_newonly"||
                          mode=="direct_two_way_budget"||
                          mode=="direct_two_way_shadow");
    bridge.two_way_novel_only=(mode=="direct_two_way_newonly"||
                               mode=="direct_two_way_budget"||
                               mode=="direct_two_way_shadow");
    bridge.two_way_utility_budget=(mode=="direct_two_way_budget");
    bridge.two_way_shadow=(mode=="direct_two_way_shadow");
    bridge.watchlazy_enabled=(mode=="direct_watchlazy"||mode=="direct_cooldown");
    bridge.cooldown_enabled=(mode=="direct_cooldown");
    if(bridge.incremental_enabled)bridge.initialize_incremental();
    if(!clean && !bridge.rows.empty()){
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto&row:bridge.rows)
            for(int v:row.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    R162Clock clock(cap_s,bridge,mode);
    solver.connect_terminator(&clock);
    cout<<"R165_START mode="<<mode<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" clauses="<<cnf.size()
        <<" cap_s="<<cap_s<<"\n"<<flush;
    auto start=chrono::steady_clock::now();
    bridge.r170_benchmark_start=start;
    const int result=solver.solve();
    const double secs=chrono::duration<double>(
        chrono::steady_clock::now()-start).count();
    solver.disconnect_terminator();
    if(result!=10 && result!=20 && result!=0)
        throw runtime_error("R165_UNKNOWN_SOLVER_EXIT");
    if(result==10){
        for(const auto&clause:cnf){
            bool ok=false;
            for(int lit:clause){
                int val=solver.val(abs(lit));
                if(val && ((val>0)==(lit>0))){ok=true;break;}
            }
            if(!ok)throw runtime_error("R165_ORIGINAL_SAT_WITNESS_INVALID");
        }
    }
    // An independent benchmark checker replays this PARTIAL source model
    // against every original clause. Auxiliary variables are never assumed.
    if(result==10){
        int on_line=0;
        cout<<"v ";
        for(int v=1;v<=n;v++){
            const int val=solver.val(v);
            if(!val)continue;
            cout<<(val>0?v:-v)<<" ";
            if(++on_line==32){cout<<"0\nv ";on_line=0;}
        }
        cout<<"0\n"<<flush;
    }
    if(bridge.disabled)throw runtime_error("R165_WATCH_REASON_INVARIANT");
    cout<<fixed<<setprecision(6)
        <<"R165_RESULT mode="<<mode
        <<" status="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
        <<" solver_s="<<secs<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" original_clauses="<<cnf.size()
        <<" assignments="<<bridge.notifications
        <<" backtracks="<<bridge.backtracks
        <<" rows_scanned="<<bridge.rows_scanned
        <<" watch_lookups="<<bridge.watch_lookups
        <<" direct_proposals="<<bridge.direct_proposals
        <<" reason_clauses_completed="<<bridge.reason_clauses_completed
        <<" direct_reason_requests="<<bridge.direct_reason_requests
        <<" direct_reason_lits="<<bridge.direct_reason_lits
        <<" shadow_candidates="<<bridge.shadow_candidates
        <<" adaptive_gate_events="<<bridge.adaptive_gate_events
        <<" component_count="<<bridge.component_count
        <<" component_gate_events="<<bridge.component_gate_events
        <<" blocked_components="<<bridge.blocked_components()
        <<" suppressed_rows="<<bridge.suppressed_rows
        <<" components_with_reasons="<<bridge.components_with_reasons()
        <<" propagate_calls="<<bridge.propagate_calls
        <<" propagate_ns="<<bridge.propagate_ns
        <<" incremental_row_events="<<bridge.incremental_row_events
        <<" incremental_reason_checks="<<bridge.incremental_reason_checks
        <<" cheap_watch_rejects="<<bridge.cheap_watch_rejects
        <<" watch_invariant_audits="<<bridge.watch_invariant_audits
        <<" cooldown_wakes="<<bridge.cooldown_wakes
        <<" cooldown_skips="<<bridge.cooldown_skips
        <<" assignment_notify_ns="<<bridge.assignment_notify_ns
        <<" backtrack_notify_ns="<<bridge.backtrack_notify_ns
        <<" incremental_upd_ns="<<bridge.incremental_upd_ns
        <<" two_way_utility_budget="<<bridge.two_way_utility_budget
        <<" two_way_sweeps="<<bridge.two_way_sweeps
        <<" two_way_row_xors="<<bridge.two_way_row_xors
        <<" two_way_proposals="<<bridge.two_way_proposals
        <<" two_way_candidates="<<bridge.two_way_candidates
        <<" two_way_multi_source_candidates="<<bridge.two_way_multi_source_candidates
        <<" two_way_source_duplicate_units="<<bridge.two_way_source_duplicate_units
        <<" two_way_shadow_candidates="<<bridge.two_way_shadow_candidates
        <<" two_way_used_reasons="<<bridge.two_way_used_reasons
        <<" r170_first_proposal_ms="<<bridge.r170_first_proposal_ms
        <<" r170_first_used_ms="<<bridge.r170_first_used_ms
        <<" r170_first_proposal_notifications="<<bridge.r170_first_proposal_notifications
        <<" r170_first_used_notifications="<<bridge.r170_first_used_notifications
        <<" two_way_abstentions="<<bridge.two_way_abstentions
        <<" two_way_ns="<<bridge.two_way_ns
        <<" r174_dirty_events="<<bridge.r174_dirty_events
        <<" r174_component_skips="<<bridge.r174_component_skips
        <<" r174_boundary_skips="<<bridge.r174_boundary_skips
        <<" r174_sweeps_total="<<bridge.r174_sweeps_total
        <<" r174_feedback_resets="<<bridge.r174_feedback_resets
        <<" source_sat_witness_checked="<<(result==10?1:0)
        <<" disabled="<<bridge.disabled<<"\n"<<flush;
    // On 2.1.0 these native statistics include actual CDCL conflicts,
    // decisions, search propagations and learned clauses. The in-solver
    // Terminator guarantees they survive a normal UNKNOWN time cap.
    cout<<"R165_STATS_BEGIN mode="<<mode<<"\n"<<flush;
    solver.statistics();
    cout<<"R165_STATS_END mode="<<mode<<"\n"<<flush;
    return result;
}

int main(int argc,char**argv) {
    try {
        if(argc==2 && string(argv[1])=="selftest"){
            DrnasBridge::watch_selftest();
            gf2_closure_selftest();
            R162Bridge::selftest();
            {
                R162Bridge inc({{{1,2,3},0}},3,R162Bridge::DIRECT);
                inc.incremental_enabled=true;
                inc.initialize_incremental();
                inc.notify_new_decision_level();
                inc.notify_assignment({1,2});
                if(inc.row_unassigned[0]!=1 || inc.row_parity[0]!=0 ||
                   inc.cb_propagate()!=-3)throw runtime_error("R165_INCREMENTAL_UNIT_TEST_FAIL");
                inc.notify_backtrack(0);
                if(inc.row_unassigned[0]!=3 || inc.row_parity[0]!=0 ||
                   inc.incremental_row_events!=4)
                    throw runtime_error("R165_INCREMENTAL_BACKTRACK_TEST_FAIL");
                cout<<"R165_INCREMENTAL_SELFTEST_PASS"<<"\n";
            }
            {
                R162Bridge two({{{1,2,3},0},{{1,2,4},0}},4,R162Bridge::DIRECT);
                two.two_way_enabled=true;
                two.notify_new_decision_level();
                two.notify_assignment({3});
                int lit=two.cb_propagate();
                if(lit!=4 || two.two_way_proposals!=1)
                    throw runtime_error("R168_DERIVED_UNIT_FAILED");
                vector<int> reason;
                for(int v;(v=two.cb_add_reason_clause_lit(lit))!=0;)reason.push_back(v);
                if(reason!=vector<int>({4,-3}))
                    throw runtime_error("R168_DERIVED_REASON_WRONG");
                for(int mask=0;mask<16;++mask){
                    auto holds=[&](const XorRow& row){int x=0;for(int v:row.vars)x^=(mask>>(v-1))&1;return x==row.rhs;};
                    if(holds(two.rows[0])&&holds(two.rows[1]) &&
                       !(((mask>>3)&1)||!((mask>>2)&1)))
                        throw runtime_error("R168_UNSOUND_REASON");
                }
                two.notify_assignment({4});
                two.notify_backtrack(0);
                if(two.disabled||!two.reasons.empty()||two.assigned[3]!=0||two.assigned[4]!=0)
                    throw runtime_error("R168_BACKTRACK_INVALID");
                two.notify_new_decision_level();
                two.notify_assignment({-3});
                if(two.cb_propagate()!=-4)
                    throw runtime_error("R168_REPROPAGATION_FAILED");
                cout<<"R168_TWO_WAY_SELFTEST_PASS consequence=x3_xor_x4_0 reason_replayed=1 rollback=1\n";
            }
            {
                vector<XorRow> source{{{1,2,3},0},{{1,2,4},0}};
                R162Bridge early(source,4,R162Bridge::DIRECT);
                early.two_way_enabled=early.two_way_early=early.two_way_novel_only=true;
                early.notify_new_decision_level();
                early.notify_assignment({3});
                const int lit=early.cb_propagate();
                if(lit!=4 || early.two_way_proposals!=1 ||
                   early.two_way_multi_source_candidates!=1)
                    throw runtime_error("R169_NOVEL_GF2_UNIT_FAIL");
                vector<int> reason;
                for(int v;(v=early.cb_add_reason_clause_lit(lit))!=0;)reason.push_back(v);
                if(reason!=vector<int>({4,-3})||early.two_way_used_reasons!=1)
                    throw runtime_error("R169_GAUSS_REASON_NOT_USED");
                early.notify_assignment({4});
                early.notify_backtrack(0);
                if(early.disabled||!early.reasons.empty()||!early.two_way_reason_keys.empty())
                    throw runtime_error("R169_GAUSS_ROLLBACK_FAIL");
                R162Bridge shadow(source,4,R162Bridge::DIRECT);
                shadow.two_way_enabled=shadow.two_way_early=true;
                shadow.two_way_novel_only=shadow.two_way_shadow=true;
                shadow.notify_new_decision_level();
                shadow.notify_assignment({3});
                if(shadow.cb_propagate()!=0 || shadow.two_way_shadow_candidates!=1 ||
                   shadow.direct_proposals!=0 || !shadow.reasons.empty())
                    throw runtime_error("R169_SHADOW_NOT_INERT");
                cout<<"R169_CAUSAL_GAUSSIAN_SELFTEST_PASS multi_source=1"
                      " consumed=1 shadow_inert=1 rollback=1\n";
            }
            {
                R162Bridge probe({{{1,2,3},0},{{1,2,4},0}},4,R162Bridge::DIRECT);
                probe.two_way_enabled=probe.two_way_early=
                    probe.two_way_novel_only=probe.two_way_utility_budget=true;
                probe.two_way_sweeps=16;
                probe.last_two_way_notifications=0;
                probe.notifications=512;
                if(probe.propagate_gaussian_residual()!=0 || probe.two_way_sweeps!=16)
                    throw runtime_error("R172_BUDGET_EARLY_BACKOFF_FAIL");
                probe.notifications=8192;
                if(probe.propagate_gaussian_residual()!=0 || probe.two_way_sweeps!=17)
                    throw runtime_error("R172_BUDGET_8192_PROBE_FAIL");
                probe.two_way_used_reasons=1;
                probe.notifications=8704;
                if(probe.propagate_gaussian_residual()!=0 || probe.two_way_sweeps!=18)
                    throw runtime_error("R172_BUDGET_REACTIVATION_FAIL");
                cout<<"R172_BUDGET_SELFTEST_PASS backoff=8192 reactivation=512\n";
            }
            return 0;
        }
        if(argc!=5) {
            cerr<<"R165_USAGE clean|watch_boundary|shadow_boundary|"
                   "direct_full|direct_full_feedback|direct_incremental|direct_two_way|direct_two_way_early|direct_two_way_newonly|direct_two_way_budget|direct_two_way_shadow|direct_watchlazy|direct_cooldown|direct_boundary_nogate|direct_boundary|direct_feedback"
                   " ORIGINAL.cnf SOURCE-CERTIFIED.tsv CAP_SECONDS\n";
            return 2;
        }
        const string mode=argv[1];
        if(mode!="clean"&&mode!="watch_boundary"&&mode!="shadow_boundary"&&
           mode!="direct_full"&&mode!="direct_boundary_nogate"&&
           mode!="direct_boundary"&&mode!="direct_feedback"&&
           mode!="direct_full_feedback"&&mode!="direct_incremental"&&
           mode!="direct_watchlazy"&&mode!="direct_cooldown"&&mode!="direct_two_way"&&
           mode!="direct_two_way_early"&&mode!="direct_two_way_newonly"&&
           mode!="direct_two_way_budget"&&
           mode!="direct_two_way_shadow")
            throw runtime_error("R165_BAD_MODE");
        const double cap=stod(argv[4]);
        if(!(cap>=1.0&&cap<=180.0))
            throw runtime_error("R165_BAD_CAP");
        return r162_run(mode,argv[2],argv[3],cap);
    }catch(const exception&e){
        cerr<<"R165_FAIL_CLOSED "<<e.what()<<"\n";
        return 2;
    }
}

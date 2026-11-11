// DRNAS Native Core R3C — original self-contained CDCL + source-certified XOR / GF(2).
// Copyright (c) 2026 Frane Drnas. All rights reserved.
// Does NOT link to Kissat, CaDiCaL, CryptoMiniSat, or another SAT solver.
// DIMACS -> watched-literal BCP -> 1-UIP learning -> nonchronological backtrack
// -> activity-based branching -> restarts -> SAT, UNSAT or resource-limited UNKNOWN.
// UNSAT proof logging is NOT implemented; independently validate UNSAT externally.
#include <algorithm>
#include <queue>
#include <array>
#include <map>
#include <set>
#include <iterator>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace drnas {
using Clock = std::chrono::steady_clock;
struct CNF {
    int vars = 0;
    std::vector<std::vector<int>> clauses;
};
static void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}
static CNF read_dimacs(const std::string& filename) {
    std::ifstream file(filename);
    require(bool(file), "cannot open original CNF file");
    CNF f;
    std::string word;
    bool header = false;
    size_t declared = 0;
    std::vector<int> current;
    while (file >> word) {
        if (word == "c") { std::string comment; std::getline(file, comment); continue; }
        if (word == "p") {
            require(!header, "duplicate DIMACS header");
            std::string fmt;
            file >> fmt >> f.vars >> declared;
            require(bool(file) && fmt == "cnf" && f.vars >= 0 && f.vars <= 1000000,
                    "invalid or excessive DIMACS header");
            require(declared <= 10000000, "excessive DIMACS clause count");
            header = true;
            continue;
        }
        require(header, "DIMACS clause before header");
        size_t used = 0;
        long long num = 0;
        try { num = std::stoll(word, &used); }
        catch (...) { throw std::runtime_error("invalid integer in original DIMACS"); }
        require(used == word.size() && num >= -f.vars && num <= f.vars,
                "literal out of DIMACS declared range");
        if (!num) {
            f.clauses.push_back(std::move(current));
            current.clear();
            require(f.clauses.size() <= declared, "extra DIMACS clause");
        } else {
            current.push_back(static_cast<int>(num));
            require(current.size() <= 2000000, "excessively long DIMACS clause");
        }
    }
    require(header && current.empty() && f.clauses.size() == declared,
            "missing terminator or DIMACS clause count mismatch");
    return f;
}

struct Clause {
    std::vector<int> lits;
    bool learned = false;
};
// Source-certified XOR equations. A row is accepted only when the ORIGINAL
// CNF contains every forbidden assignment clause of the same parity and
// variable set. CRR pair rows are exact GF(2) symmetric differences of two
// already certified rows, never independently guessed or heuristic.
struct XorRowR2 {
    std::vector<int> vars;
    int rhs=0;
    bool derived=false;
};
static std::vector<XorRowR2> extract_source_xors(const CNF& cnf) {
    // A complete XOR-k encoding has 2^(k-1) CNF clauses of width k.
    // No other constraints need be assumed. Exact masks eliminate false
    // positives from incomplete or mixed-sign parity candidates.
    std::map<std::vector<int>, std::array<uint32_t,2>> groups;
    size_t considered=0;
    for(const auto& clause:cnf.clauses){
        if(clause.size()<2 || clause.size()>4)continue;
        if(++considered>250000)break; // bounded deterministic source scan
        std::vector<std::pair<int,int>> vars;
        vars.reserve(clause.size());
        for(int lit:clause)vars.push_back({std::abs(lit),lit<0?1:0});
        std::sort(vars.begin(),vars.end());
        bool repeated=false;
        for(size_t i=1;i<vars.size();++i)
            if(vars[i-1].first==vars[i].first){repeated=true;break;}
        if(repeated)continue;
        std::vector<int> key;uint32_t mask=0;
        for(size_t j=0;j<vars.size();++j){
            key.push_back(vars[j].first);
            if(vars[j].second)mask|=(1u<<j);
        }
        groups[key][__builtin_popcount(mask)&1u]|=(1u<<mask);
    }
    std::vector<XorRowR2> output;
    for(const auto&group:groups){
        const int width=(int)group.first.size();
        const uint32_t total=1u<<width;
        for(int forbidden_parity=0;forbidden_parity<2;++forbidden_parity){
            uint32_t required=0;
            for(uint32_t mask=0;mask<total;++mask)
                if((__builtin_popcount(mask)&1)==forbidden_parity)
                    required|=(1u<<mask);
            if((group.second[forbidden_parity]&required)==required)
                output.push_back({group.first,1-forbidden_parity,false});
            // Original source parity must be certified before selecting active
            // rows. The former first-128 lexicographic gate lost useful
            // cancellations whose input rows appeared later.
            if(output.size()>=1024)return output;
        }
    }
    return output;
}
static std::vector<XorRowR2> derive_reductive_xors(
    const std::vector<XorRowR2>&source) {
    std::vector<XorRowR2> rows=source;
    std::set<std::pair<std::vector<int>,int>> seen;
    for(const auto&row:source)seen.insert({row.vars,row.rhs});
    struct Candidate{std::vector<int> vars;int rhs;};
    std::vector<Candidate> candidates;
    for(size_t i=0;i<source.size();++i)
        for(size_t j=i+1;j<source.size();++j){
            std::vector<int> sum;
            std::set_symmetric_difference(source[i].vars.begin(),source[i].vars.end(),
                source[j].vars.begin(),source[j].vars.end(),std::back_inserter(sum));
            if(sum.empty()||sum.size()>4 ||
               sum.size()>=std::max(source[i].vars.size(),source[j].vars.size()))
                continue;
            const int rhs=source[i].rhs^source[j].rhs;
            if(!seen.count({sum,rhs}))candidates.push_back({std::move(sum),rhs});
        }
    // Prefer short, high-information rows. Limit memory and callback cost.
    std::sort(candidates.begin(),candidates.end(),[](const Candidate&a,const Candidate&b){
        if(a.vars.size()!=b.vars.size())return a.vars.size()<b.vars.size();
        if(a.vars!=b.vars)return a.vars<b.vars;
        return a.rhs<b.rhs;
    });
    for(const auto&row:candidates){
        if(rows.size()-source.size()>=64)break;
        if(seen.insert({row.vars,row.rhs}).second)
            rows.push_back({row.vars,row.rhs,true});
    }
    return rows;
}
struct Statistics {
    uint64_t conflicts = 0, decisions = 0, propagations = 0;
    uint64_t watch_visits = 0, learned_clauses = 0, restarts = 0;
    uint64_t xor_source_rows=0, xor_derived_rows=0, xor_checks=0;
    uint64_t xor_certified_candidates=0;
    uint64_t xor_implications=0, xor_derived_implications=0;
    uint64_t xor_conflicts=0, xor_reasons=0, xor_budget_off=0;
    uint64_t xor_events_enqueued=0, xor_events_processed=0;
    uint64_t heap_pops=0, heap_pushes=0, heap_bumps=0, heap_removals=0;
#ifdef DRNAS_ARL3_DIAG
    uint64_t arl3_width_sum=0,arl3_lbd_sum=0,arl3_short=0,arl3_stall_windows=0;
    uint64_t arl3_window_decisions=0,arl3_window_short=0;
#endif
#ifdef DRNAS_ARL4_RESTART
    uint64_t arl4_adaptive_restarts=0,arl4_stall_windows=0;
    uint64_t arl4_lbd_window_sum=0,arl4_width_window_sum=0,arl4_window_count=0;
    uint64_t arl4_last_window_short=0,arl4_last_window_decisions=0;
    uint64_t arl4_last_window_conflicts=0;
#ifdef DRNAS_ARL3_DIAG
#endif

};
class NativeCDCL {
    const int n_;
    std::vector<Clause> clauses_;
#ifdef DRNAS_ONE2_BLOCKER
    // Every cached blocker must be a literal of its permanent clause.
    // TRUE cache => clause satisfied, no clause-vector access required.
    struct WatchEntry { int cid; int blocker; };
    std::vector<std::vector<WatchEntry>> watches_;
#else
    std::vector<std::vector<int>> watches_;
#endif
    std::vector<int8_t> values_, phases_;
    std::vector<int> levels_, reasons_, trail_;
    std::vector<size_t> decision_marks_;
    std::vector<double> activity_;
    size_t propagation_head_ = 0;
    bool root_contradiction_ = false;
    double bump_ = 1.0, decay_ = 0.95;
    uint64_t next_restart_ = 100, restart_window_ = 100;
#ifdef DRNAS_ARL4_RESTART
    uint64_t arl4_last_lbd_=0,arl4_last_width_=0;
    bool arl4_armed_=false;
#endif
    Clock::time_point start_;
    double cap_s_ = 10.0;
    bool resource_limit_ = false;
    Statistics stats_;
#ifdef DRNAS_PROGRESS1
    // Passive cycle-level telemetry; does not change assignments or heuristics.
    uint64_t progress_last_prop_=0,progress_last_watch_=0,progress_last_decisions_=0;
    uint64_t progress_last_root_=0,progress_last_short_=0;
    uint64_t progress_reported_=0;
    uint64_t progress_short_learned_=0;
    uint64_t progress_zero_root_=0;
    void progress_emit(int before_level,int backjump,const std::vector<int>& learned) {
        uint64_t root=0;
        for(int lit:trail_)if(levels_[var(lit)]==0)++root;
        const uint64_t prop=stats_.propagations,watch=stats_.watch_visits,dec=stats_.decisions;
        std::vector<int> distinct_levels;
        for(int lit:learned) {
            int lev=levels_[var(lit)];
            if(std::find(distinct_levels.begin(),distinct_levels.end(),lev)==distinct_levels.end())
                distinct_levels.push_back(lev);
        }
        const size_t width=learned.size();
        if(width<=2)++progress_short_learned_;
        if(root==progress_last_root_)++progress_zero_root_;
        if(++progress_reported_<=2500)
            std::cerr<<"DRNAS_PROGRESS1 cycle="<<stats_.conflicts
                 <<" decisions_delta="<<(dec-progress_last_decisions_)
                 <<" propagations_delta="<<(prop-progress_last_prop_)
                 <<" watch_delta="<<(watch-progress_last_watch_)
                 <<" root_assignments="<<root
                 <<" root_delta="<<int64_t(root)-int64_t(progress_last_root_)
                 <<" learned_width="<<width
                 <<" learned_lbd="<<distinct_levels.size()
                 <<" backjump="<<(before_level-backjump)
                 <<" learned_total="<<stats_.learned_clauses+1
                 <<" short_learned_total="<<progress_short_learned_
                 <<" repeat_root_count="<<progress_zero_root_
                 <<" note=pre_backjump"<<"\n";
        progress_last_prop_=prop; progress_last_watch_=watch;
        progress_last_decisions_=dec;progress_last_root_=root;
    }
#endif
#ifdef DRNAS_MICRO_TRACE
    uint64_t micro_events_=0;
    void micro_log(const std::string& line) {
        if (micro_events_++ < 10000)
            std::cerr<<"MICRO_EVENT seq="<<micro_events_<<" "<<line<<"\n";
    }
#endif
#ifdef DRNAS_WATCH_DIAG
    // Diagnostic counters only. The CDCL algorithm and watched-literal data
    // structures are unchanged, so R3C and WATCH1 execute the same search.
    struct WatchDiag {
        uint64_t trail_lits=0, watchlist_nonempty=0, watchlist_entries=0, watchlist_peak=0;
        uint64_t visits_original=0, visits_learned=0, binary_visits=0, long_visits=0;
        uint64_t blocker_satisfied=0, cache_hit=0, candidate_scans=0, candidate_probes=0;
        uint64_t watch_moves=0, scan_exhausted=0, unit_implications=0, clause_conflicts=0;
        std::array<uint64_t,7> width_visits{};
    } watch_diag_;
public:
    void print_watch_diag() const {
        const auto& w=watch_diag_;
        std::cout<<"DRNAS_WATCH1"
            <<" trail_lits="<<w.trail_lits
            <<" watchlist_nonempty="<<w.watchlist_nonempty
            <<" watchlist_entries="<<w.watchlist_entries
            <<" watchlist_peak="<<w.watchlist_peak
            <<" visits_original="<<w.visits_original
            <<" visits_learned="<<w.visits_learned
            <<" binary_visits="<<w.binary_visits
            <<" long_visits="<<w.long_visits
            <<" blocker_satisfied="<<w.blocker_satisfied<<" cache_hit="<<w.cache_hit
            <<" candidate_scans="<<w.candidate_scans
            <<" candidate_probes="<<w.candidate_probes
            <<" watch_moves="<<w.watch_moves
            <<" scan_exhausted="<<w.scan_exhausted
            <<" unit_implications="<<w.unit_implications
            <<" clause_conflicts="<<w.clause_conflicts;
        for(size_t i=0;i<w.width_visits.size();++i)
            std::cout<<" width_bucket_"<<i<<"="<<w.width_visits[i];
        std::cout<<"\n";
    }
private:
#endif
#ifdef DRNAS_PROFILE
    double profile_bcp_s_=0,profile_xor_s_=0,profile_analyze_s_=0,profile_select_s_=0,profile_update_s_=0,profile_clock_s_=0;
    uint64_t profile_samples_=0;
    double profile_clock(){auto a=Clock::now();auto b=Clock::now();profile_clock_s_+=std::chrono::duration<double>(b-a).count();++profile_samples_;return std::chrono::duration<double>(a.time_since_epoch()).count();}
    double profile_now(){return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();}
public:
    void print_profile() const {
      std::cout<<std::fixed<<std::setprecision(8)<<"DRNAS_PROFILE bcp_s="<<profile_bcp_s_
      <<" xor_s="<<profile_xor_s_<<" analyze_s="<<profile_analyze_s_
      <<" select_s="<<profile_select_s_<<" update_s="<<profile_update_s_
      <<" clock_probe_s="<<profile_clock_s_<<" clock_samples="<<profile_samples_
      <<" measured_s="<<(profile_bcp_s_+profile_xor_s_+profile_analyze_s_+profile_select_s_+profile_update_s_)
      <<" profile_overhead_lower_bound_s="<<profile_clock_s_<<"\n";
    }
private:
#endif
    std::vector<XorRowR2> xor_rows_;
    // Variable-to-XOR incidence avoids scanning all rows at every BCP fixpoint.
    std::vector<std::vector<int>> xor_incidence_;
    std::vector<int> xor_pending_;
    std::vector<uint8_t> xor_dirty_;
    size_t xor_head_=0;
    // One indexed binary heap entry per UNASSIGNED variable.
    // O(log n) increase-key and insert/remove, no stale duplicates.
    std::vector<int> heap_,heap_position_;
    bool heap_ready_=false;
    bool gf2_enabled_=false, gf2_budget_exhausted_=false;
    static constexpr uint64_t kGF2MaxChecks = 500000;

    static int var(int lit) { return std::abs(lit); }
    static int watch_index(int lit) {
        return 2 * (std::abs(lit) - 1) + (lit < 0 ? 1 : 0);
    }
    int level() const { return static_cast<int>(decision_marks_.size()); }
    bool higher_heap(int a,int b) const {
        return activity_[a]!=activity_[b] ?
            activity_[a]>activity_[b] : a<b;
    }
    void heap_swap(size_t a,size_t b){
        std::swap(heap_[a],heap_[b]);
        heap_position_[heap_[a]]=int(a);
        heap_position_[heap_[b]]=int(b);
    }
    void heap_up(size_t pos){
        while(pos>0){
            size_t parent=(pos-1)/2;
            if(!higher_heap(heap_[pos],heap_[parent]))break;
            heap_swap(pos,parent);
            pos=parent;
        }
    }
    void heap_down(size_t pos){
        while(true){
            const size_t left=pos*2+1,right=left+1;
            size_t best=pos;
            if(left<heap_.size()&&higher_heap(heap_[left],heap_[best]))
                best=left;
            if(right<heap_.size()&&higher_heap(heap_[right],heap_[best]))
                best=right;
            if(best==pos)break;
            heap_swap(pos,best);
            pos=best;
        }
    }
    void heap_push(int v){
        if(!heap_ready_||heap_position_[v]>=0)return;
        require(!values_[v],"cannot insert assigned variable into R3C heap");
        heap_position_[v]=int(heap_.size());
        heap_.push_back(v);
        heap_up(heap_.size()-1);
        ++stats_.heap_pushes;
    }
    void heap_remove(int v){
        if(!heap_ready_||heap_position_[v]<0)return;
        const size_t pos=size_t(heap_position_[v]);
        heap_position_[v]=-1;
        const int moved=heap_.back();
        heap_.pop_back();
        if(pos<heap_.size()){
            heap_[pos]=moved;
            heap_position_[moved]=int(pos);
            heap_up(pos);
            heap_down(size_t(heap_position_[moved]));
        }
        ++stats_.heap_removals;
    }
    void heap_initialize(){
        heap_ready_=true;
        heap_.clear();
        for(int v=1;v<=n_;++v)
            if(!values_[v]){
                heap_position_[v]=int(heap_.size());
                heap_.push_back(v);
                ++stats_.heap_pushes;
            }
        for(size_t i=heap_.size()/2;i>0;--i)heap_down(i-1);
    }
    void schedule_xor(int row){
        if(xor_dirty_[size_t(row)])return;
        xor_dirty_[size_t(row)]=1;
        xor_pending_.push_back(row);
        ++stats_.xor_events_enqueued;
    }

    int lit_value(int lit) const {
        int value = values_[var(lit)];
        return lit > 0 ? value : -value;
    }
    bool enqueue(int lit, int from_clause) {
        int v = var(lit);
        int8_t desired = lit > 0 ? 1 : -1;
        if (values_[v]) return values_[v] == desired;
        values_[v] = desired;
        phases_[v] = desired;
        levels_[v] = level();
        reasons_[v] = from_clause;
        trail_.push_back(lit);
#ifdef DRNAS_MICRO_TRACE
        micro_log("kind=assign lit="+std::to_string(lit)+
                  " level="+std::to_string(level())+
                  " reason="+std::to_string(from_clause));
#endif
        heap_remove(v);
        if(gf2_enabled_&&!gf2_budget_exhausted_)
            for(int row:xor_incidence_[v])schedule_xor(row);
        return true;
    }
    void attach(int index) {
        const auto& c = clauses_[index].lits;
        if (c.size() >= 2) {
#ifdef DRNAS_ONE2_BLOCKER
            watches_[watch_index(c[0])].push_back({index,c[1]});
            watches_[watch_index(c[1])].push_back({index,c[0]});
#else
            watches_[watch_index(c[0])].push_back(index);
            watches_[watch_index(c[1])].push_back(index);
#endif
        }
    }
    void bump_variable(int v) {
        activity_[v] += bump_;
        ++stats_.heap_bumps;
        if (activity_[v] > 1e100) {
            for (int i = 1; i <= n_; ++i) activity_[i] *= 1e-100;
            bump_ *= 1e-100;
            // Global positive scaling preserves activity ordering, so
            // existing heap topology remains valid without reinsertions.
        }
        if(heap_ready_ && heap_position_[v]>=0)
            heap_up(size_t(heap_position_[v]));
    }
    bool timed_out() const {
        return std::chrono::duration<double>(Clock::now() - start_).count() >= cap_s_;
    }
    // Watch the two front literals in each nonunit clause. Every original or
    // learned clause is stored explicitly, not outsourced to any solver.
    // Return -1: no conflict; -2: timed out; otherwise conflicting clause ID.
    int propagate() {
        while (propagation_head_ < trail_.size()) {
            if ((stats_.propagations & 1023ULL) == 0 && timed_out()) return -2;
            const int true_lit = trail_[propagation_head_++];
            ++stats_.propagations;
            auto& list = watches_[watch_index(-true_lit)];
#ifdef DRNAS_WATCH_DIAG
            ++watch_diag_.trail_lits;
            if(!list.empty())++watch_diag_.watchlist_nonempty;
            watch_diag_.watchlist_entries+=list.size();
            watch_diag_.watchlist_peak=std::max<uint64_t>(watch_diag_.watchlist_peak,list.size());
#endif
            size_t read = 0, write = 0;
            while (read < list.size()) {
#ifdef DRNAS_ONE2_BLOCKER
                WatchEntry entry = list[read++];
                ++stats_.watch_visits;
                // Safe on backtracking: cached blocker is still a clause
                // literal; when it is TRUE this clause cannot propagate.
                if (lit_value(entry.blocker) == 1) {
#ifdef DRNAS_WATCH_DIAG
                    ++watch_diag_.cache_hit;
#endif
                    list[write++] = entry;
                    continue;
                }
                const int cid = entry.cid;
#else
                const int cid = list[read++];
                ++stats_.watch_visits;
#endif
                auto& clause = clauses_[cid].lits;
                require(clause.size() >= 2, "broken watch on unit clause");
#ifdef DRNAS_WATCH_DIAG
                if(clauses_[cid].learned) ++watch_diag_.visits_learned;
                else ++watch_diag_.visits_original;
                const size_t width=clause.size();
                if(width==2) ++watch_diag_.binary_visits;
                else ++watch_diag_.long_visits;
                const size_t bucket=(width==2 ? 0 : width==3 ? 1 : width==4 ? 2 :
                                    width<=8 ? 3 : width<=16 ? 4 : width<=32 ? 5 : 6);
                ++watch_diag_.width_visits[bucket];
#endif
                if (clause[0] == -true_lit) std::swap(clause[0], clause[1]);
                require(clause[1] == -true_lit, "watch invariant violated");
                if (lit_value(clause[0]) == 1) {
#ifdef DRNAS_WATCH_DIAG
                    ++watch_diag_.blocker_satisfied;
#endif
#ifdef DRNAS_ONE2_BLOCKER
                    entry.blocker=clause[0];
                    list[write++]=entry;
#else
                    list[write++] = cid;
#endif
                    continue;
                }
#ifdef DRNAS_WATCH_DIAG
                if(clause.size()>2) ++watch_diag_.candidate_scans;
#endif
                size_t candidate = clause.size();
                for (size_t k = 2; k < clause.size(); ++k) {
#ifdef DRNAS_WATCH_DIAG
                    ++watch_diag_.candidate_probes;
#endif
                    if (lit_value(clause[k]) != -1) { candidate = k; break; }
                }
                if (candidate != clause.size()) {
#ifdef DRNAS_WATCH_DIAG
                    ++watch_diag_.watch_moves;
#endif
                    std::swap(clause[1], clause[candidate]);
#ifdef DRNAS_ONE2_BLOCKER
                    watches_[watch_index(clause[1])].push_back({cid,clause[0]});
#else
                    watches_[watch_index(clause[1])].push_back(cid);
#endif
                    continue;
                }
#ifdef DRNAS_WATCH_DIAG
                if(clause.size()>2) ++watch_diag_.scan_exhausted;
                const int other_value=lit_value(clause[0]);
                if(other_value==-1)++watch_diag_.clause_conflicts;
                else if(other_value==0)++watch_diag_.unit_implications;
#endif
#ifdef DRNAS_ONE2_BLOCKER
                entry.blocker=clause[0];
                list[write++]=entry;
#else
                list[write++] = cid;
#endif
                if (lit_value(clause[0]) == -1 || !enqueue(clause[0], cid)) {
                    // The remaining watcher IDs must stay installed even when
                    // propagation exits early on this conflict.
                    while (read < list.size()) list[write++] = list[read++];
                    list.resize(write);
                    return cid;
                }
            }
            list.resize(write);
        }
        return -1;
    }
    // This is an INTEGRATED inference step in our own CDCL engine. No
    // external propagator/solver code or library. Each XOR implication is
    // justified by a permanent original-CNF-entailed explanation clause.
    // -1: no GF2 consequence; -2: timeout; -3: newly enqueued literal;
    // >=0: conflict clause ID, returned into OUR OWN 1-UIP analyzer.
    int propagate_xor() {
        if(!gf2_enabled_||gf2_budget_exhausted_)return -1;
        while(xor_head_<xor_pending_.size()){
            if((stats_.xor_checks&1023u)==0 && timed_out())return -2;
            if(stats_.xor_checks>=kGF2MaxChecks){
                gf2_budget_exhausted_=true;
                xor_pending_.clear();xor_dirty_.clear();xor_head_=0;
                ++stats_.xor_budget_off;
                return -1;
            }
            const int row_id=xor_pending_[xor_head_++];
            xor_dirty_[size_t(row_id)]=0;
            const auto&row=xor_rows_[size_t(row_id)];
            ++stats_.xor_checks;++stats_.xor_events_processed;
            int parity=0,unknown=0,unknown_var=0;
            std::vector<int> reason;
            reason.reserve(row.vars.size()+1);
            for(int v:row.vars){
                if(!values_[v]){++unknown;unknown_var=v;}
                else {
                    parity^=(values_[v]>0);
                    reason.push_back(values_[v]>0?-v:v);
                }
            }
            if(!unknown && parity!=row.rhs){
                require(!reason.empty(),"GF2 empty conflict not representable");
                int cid=int(clauses_.size());
                clauses_.push_back({std::move(reason),true});
                attach(cid);
                ++stats_.xor_conflicts;++stats_.xor_reasons;
                return cid;
            }
            if(unknown!=1)continue;
            int implied=(row.rhs^parity)?unknown_var:-unknown_var;
            reason.insert(reason.begin(),implied);
            int cid=int(clauses_.size());
            clauses_.push_back({std::move(reason),true});
            attach(cid);
            require(enqueue(implied,cid),"GF2 source-entailed implication failed");
            ++stats_.xor_implications;
            if(row.derived)++stats_.xor_derived_implications;
            ++stats_.xor_reasons;
            return -3;
        }
        xor_pending_.clear();xor_head_=0;
        return -1;
    }
    void cancel_to(int target_level) {
        if (level() <= target_level) return;
        require(target_level >= 0, "negative backtrack level");
        const size_t target = decision_marks_[target_level];
        for (size_t i = trail_.size(); i > target; --i) {
            const int v = var(trail_[i - 1]);
            values_[v] = 0;
            reasons_[v] = -1;
            levels_[v] = 0;
            if(heap_ready_)heap_push(v);
            // Unassigning a variable cannot by itself increase an XOR
            // row's propagation strength; the next assertion schedules
            // every row it touches, including those pending across backjump.
        }
        trail_.resize(target);
        decision_marks_.resize(target_level);
        propagation_head_ = std::min(propagation_head_, target);
    }
#ifdef DRNAS_MICRO_TRACE
    // Frozen diagnostic only: walk the ACTUAL implication reasons at a conflict.
    // This emits the clause graph as it existed BEFORE CDCL learns the new clause.
    void micro_reason_graph(int conflict) {
        if (!(n_<=50 && (stats_.conflicts<=5 || (stats_.conflicts>=16 && stats_.conflicts<=20))))return;
        const uint64_t number=stats_.conflicts;
        std::vector<int> stack{conflict};
        std::vector<uint8_t> visited(clauses_.size(),0);
        size_t steps=0;
        while(!stack.empty() && steps++ < 2000) {
            int cid=stack.back();stack.pop_back();
            if(cid<0 || size_t(cid)>=clauses_.size() || visited[size_t(cid)])continue;
            visited[size_t(cid)]=1;
            const auto& c=clauses_[size_t(cid)];
            std::cerr<<"REDUCE2_NODE conflict="<<number<<" cid="<<cid
                     <<" learned="<<int(c.learned)<<" clause=";
            for(size_t i=0;i<c.lits.size();++i) {
                if(i)std::cerr<<",";
                std::cerr<<c.lits[i];
            }
            std::cerr<<"\n";
            for(int lit:c.lits) {
                int v=var(lit);
                if(lit_value(lit)!=-1)continue;
                int parent=reasons_[v];
                if(parent<0)continue;
                std::cerr<<"REDUCE2_EDGE conflict="<<number<<" from="<<cid
                         <<" to="<<parent<<" var="<<v<<"\n";
                if(size_t(parent)<visited.size()&&!visited[size_t(parent)])
                    stack.push_back(parent);
            }
        }
        require(stack.empty(),"micro reason graph exceeded diagnostic bound");
    }
#endif
    // Resolve the conflict with reasons until precisely one literal comes
    // from the current decision level: the asserting 1-UIP clause.
    std::pair<std::vector<int>, int> analyze(int conflict) {
        std::vector<uint8_t> seen(n_ + 1, 0);
        std::vector<int> learned(1, 0);
        int pending = 0, resolved_lit = 0;
        size_t reverse_pos = trail_.size();
        do {
            require(conflict >= 0 && conflict < static_cast<int>(clauses_.size()),
                    "broken conflict reason in 1-UIP");
            for (int lit : clauses_[conflict].lits) {
                const int v = var(lit);
                if (v == var(resolved_lit) || seen[v] || levels_[v] == 0) continue;
                seen[v] = 1;
                bump_variable(v);
                if (levels_[v] == level()) ++pending;
                else learned.push_back(lit);
            }
            require(pending > 0, "1-UIP has no current-level conflict path");
            do {
                require(reverse_pos > 0, "1-UIP trail unexpectedly exhausted");
                resolved_lit = trail_[--reverse_pos];
            } while (!seen[var(resolved_lit)]);
            seen[var(resolved_lit)] = 0;
            --pending;
            if (pending) conflict = reasons_[var(resolved_lit)];
        } while (pending);
        learned[0] = -resolved_lit;
        int backtrack_level = 0;
        if (learned.size() >= 2) {
            size_t best = 1;
            for (size_t i = 2; i < learned.size(); ++i) {
                if (levels_[var(learned[i])] > levels_[var(learned[best])])
                    best = i;
            }
            std::swap(learned[1], learned[best]);
            backtrack_level = levels_[var(learned[1])];
        }
        return {std::move(learned), backtrack_level};
    }
    int pick_branch_variable() {
        if(heap_.empty())return 0;
        const int v=heap_[0];
        require(!values_[v]&&heap_position_[v]==0,
                "indexed heap top must be unassigned and at position zero");
        ++stats_.heap_pops;
        // enqueue() removes the selected variable in O(log n).
        return v;
    }

public:
    explicit NativeCDCL(int n) : n_(n), watches_(size_t(n) * 2),
          values_(n + 1, 0), phases_(n + 1, 1),
          levels_(n + 1, 0), reasons_(n + 1, -1),
          activity_(n + 1, 0),heap_position_(n+1,-1) {
        require(n >= 0 && n <= 1000000, "invalid SAT variable count");
    }
    void add_original(const std::vector<int>& input) {
        require(trail_.size() == 0 || level() == 0,
                "input clauses can only be added at decision level zero");
        if (root_contradiction_) return;
        std::vector<int> lits = input;
        std::sort(lits.begin(), lits.end(), [](int a, int b) {
            return var(a) < var(b) || (var(a) == var(b) && a < b);
        });
        std::vector<int> normal;
        for (int lit : lits) {
            require(lit && var(lit) <= n_, "original literal outside declared range");
            if (!normal.empty() && var(normal.back()) == var(lit)) {
                if (normal.back() != lit) return;  // exact tautology: ignore clause
                continue;                          // identical duplicate literal
            }
            normal.push_back(lit);
        }
        if (normal.empty()) { root_contradiction_ = true; return; }
        for (int lit : normal) activity_[var(lit)] += 1.0;
        const int cid = static_cast<int>(clauses_.size());
        clauses_.push_back({std::move(normal), false});
        attach(cid);
        if (clauses_[cid].lits.size() == 1 &&
            !enqueue(clauses_[cid].lits[0], cid)) root_contradiction_ = true;
    }
    void add_cnf(const CNF& cnf) {
        require(n_ == cnf.vars, "input variable count drift");
        for (const auto& clause : cnf.clauses) add_original(clause);
    }
    void enable_gf2_from_original(const CNF& cnf) {
        require(trail_.empty()||level()==0,
                "GF2 source certification only before CDCL search");
        require(cnf.vars==n_,"GF2 source variable count mismatch");
        auto source=extract_source_xors(cnf);
        stats_.xor_certified_candidates=source.size();
        // Exact GF(2) sums of every certified source row are entailed
        // by ORIGINAL CNF, even when source parents are not active.
        auto closed=derive_reductive_xors(source);
        const size_t active=std::min<size_t>(128,source.size());
        xor_rows_.assign(source.begin(),source.begin()+active);
        for(size_t i=source.size();i<closed.size();++i)
            xor_rows_.push_back(closed[i]);
        stats_.xor_source_rows=active;
        stats_.xor_derived_rows=closed.size()-source.size();
        xor_incidence_.clear();xor_incidence_.resize(size_t(n_)+1);
        xor_dirty_.assign(xor_rows_.size(),0);
        xor_pending_.clear();xor_head_=0;
        for(size_t i=0;i<xor_rows_.size();++i)
            for(int v:xor_rows_[i].vars)
                xor_incidence_[size_t(v)].push_back(int(i));
        gf2_enabled_=true;
        // Seed all rows once: covers root units assigned before GF2 setup.
        for(size_t i=0;i<xor_rows_.size();++i)schedule_xor(int(i));
    }
    int solve(double time_limit_s) {
        require(std::isfinite(time_limit_s) && time_limit_s > 0,
                "positive time limit required");
        cap_s_ = time_limit_s;
        start_ = Clock::now();
        if (root_contradiction_) return 20;
        heap_initialize();
        while (true) {
            if (timed_out()) return 0;
            if (clauses_.size() > 1500000 || stats_.learned_clauses > 500000) {
                resource_limit_ = true;
                return 0;
            }
#ifdef DRNAS_PROFILE
            double p0=profile_clock();
#endif
            int conflicting = propagate();
#ifdef DRNAS_PROFILE
            profile_bcp_s_+=profile_now()-p0;
#endif
            if (conflicting == -2) return 0;
            if (conflicting == -1) {
#ifdef DRNAS_PROFILE
                p0=profile_clock();
#endif
                conflicting=propagate_xor();
#ifdef DRNAS_PROFILE
                profile_xor_s_+=profile_now()-p0;
#endif
                if(conflicting==-2)return 0;
                if(conflicting==-3)continue; // run our own watched BCP again
            }
            if (conflicting >= 0) {
                ++stats_.conflicts;
#ifdef DRNAS_MICRO_TRACE
                micro_reason_graph(conflicting);
                micro_log("kind=conflict cid="+std::to_string(conflicting)+
                          " level="+std::to_string(level())+
                          " number="+std::to_string(stats_.conflicts)+
                          " decisions="+std::to_string(stats_.decisions)+
                          " propagations="+std::to_string(stats_.propagations)+
                          " visits="+std::to_string(stats_.watch_visits)+
                          " trail="+std::to_string(trail_.size()));
#endif
                if (level() == 0) return 20;
#ifdef DRNAS_PROFILE
                p0=profile_clock();
#endif
                auto [learned, target] = analyze(conflicting);
#ifdef DRNAS_ARL4_RESTART
                // Causal, bounded restart-only intervention: no clause deletion.
                // Diagnose the previous 256 conflicts; arm one earlier restart
                // only when learned LBD >= 8, width >= 12 and no short clauses.
                // No repeated intervention until the next 256-conflict window.
                {
                    std::set<int> distinct;
                    for(int lit:learned)distinct.insert(levels_[var(lit)]);
                    stats_.arl4_lbd_window_sum+=distinct.size();
                    stats_.arl4_width_window_sum+=learned.size();
                    ++stats_.arl4_window_count;
                    if(stats_.conflicts%256==0 && stats_.arl4_window_count>=256){
                        const bool stalled=stats_.arl4_lbd_window_sum>=8*stats_.arl4_window_count
                            && stats_.arl4_width_window_sum>=12*stats_.arl4_window_count
                            && stats_.arl3_short==stats_.arl4_last_window_short
                            && stats_.decisions-stats_.arl4_last_window_decisions>=128;
                        if(stalled){
                            ++stats_.arl4_stall_windows;
                            arl4_armed_=true;
                        } else arl4_armed_=false;
                        stats_.arl4_last_window_short=stats_.arl3_short;
                        stats_.arl4_last_window_decisions=stats_.decisions;
                        stats_.arl4_lbd_window_sum=0;
                        stats_.arl4_width_window_sum=0;
                        stats_.arl4_window_count=0;
                    }
                }
#endif
#ifdef DRNAS_ARL3_DIAG
                // Passive 1-UIP LBD/width and 256-conflict windows; no search change.
                stats_.arl3_width_sum+=learned.size();
                std::set<int> levels_seen;
                for(int lit:learned)levels_seen.insert(levels_[var(lit)]);
                stats_.arl3_lbd_sum+=levels_seen.size();
                if(learned.size()<=2)++stats_.arl3_short;
                if(stats_.conflicts%256==0){
                    const uint64_t short_delta=stats_.arl3_short-stats_.arl3_window_short;
                    const uint64_t dec_delta=stats_.decisions-stats_.arl3_window_decisions;
                    if(short_delta==0 && dec_delta>=128)++stats_.arl3_stall_windows;
                    stats_.arl3_window_decisions=stats_.decisions;
                    stats_.arl3_window_short=stats_.arl3_short;
                }
#endif
#ifdef DRNAS_PROGRESS1
                progress_emit(level(),target,learned);
#endif
#ifdef DRNAS_MICRO_TRACE
                {std::string lits; for(int lit:learned){if(!lits.empty())lits+=",";lits+=std::to_string(lit);}
                 micro_log("kind=learn from="+std::to_string(level())+
                           " backjump="+std::to_string(target)+
                           " width="+std::to_string(learned.size())+" clause="+lits);}
#endif
#ifdef DRNAS_PROFILE
                profile_analyze_s_+=profile_now()-p0;
#endif
#ifdef DRNAS_PROFILE
                p0=profile_clock();
#endif
                cancel_to(target);
                const int cid = static_cast<int>(clauses_.size());
                const int assertion = learned[0];
                clauses_.push_back({std::move(learned), true});
                attach(cid);
                ++stats_.learned_clauses;
                require(enqueue(assertion, cid), "learned 1-UIP clause not asserting");
                bump_ /= decay_;
#ifdef DRNAS_PROFILE
                profile_update_s_+=profile_now()-p0;
#endif
                if (stats_.conflicts >= next_restart_ && level() > 0) {
                    cancel_to(0);
                    ++stats_.restarts;
#ifdef DRNAS_ARL4_RESTART
                    if(arl4_armed_){
                        ++stats_.arl4_adaptive_restarts;
                        // Limit future restart interval to 128 conflicts;
                        // no changes to 1-UIP, clause database or branching.
                        restart_window_=128;
                        arl4_armed_=false;
                    } else
#endif
                    restart_window_ = std::min<uint64_t>(restart_window_ * 3 / 2 + 1,
                                                          30000);
                    next_restart_ = stats_.conflicts + restart_window_;
                }
            } else {
#ifdef DRNAS_PROFILE
                p0=profile_clock();
#endif
                const int v = pick_branch_variable();
#ifdef DRNAS_PROFILE
                profile_select_s_+=profile_now()-p0;
#endif
                if (!v) return 10;
                ++stats_.decisions;
#ifdef DRNAS_MICRO_TRACE
                micro_log("kind=decision variable="+std::to_string(v)+
                          " number="+std::to_string(stats_.decisions));
#endif
                decision_marks_.push_back(trail_.size());
                require(enqueue(phases_[v] >= 0 ? v : -v, -1),
                        "selected decision variable was already assigned");
            }
        }
    }
    const Statistics& statistics() const { return stats_; }
    bool hit_resource_limit() const { return resource_limit_; }
    double solve_elapsed_s() const {
        return std::chrono::duration<double>(Clock::now() - start_).count();
    }
    const std::vector<int8_t>& assignments() const { return values_; }
    bool verify_original(const CNF& cnf) const {
        require(cnf.vars == n_, "model validation on different original CNF");
        for (const auto& clause : cnf.clauses) {
            bool satisfied = false;
            for (int lit : clause) if (lit_value(lit) == 1) { satisfied = true; break; }
            if (!satisfied) return false;
        }
        return true;
    }
};

// These correctness tests enumerate every assignment of small CNFs and compare
// to the independently computed SAT truth table; no external solver runs.
static bool brute_sat(const CNF& f) {
    require(f.vars <= 15 && f.vars >= 0, "brute SAT intended for small CNF only");
    for (unsigned mask = 0; mask < (1u << f.vars); ++mask) {
        bool all = true;
        for (const auto& clause : f.clauses) {
            bool sat = false;
            for (int lit : clause) {
                bool value = bool(mask & (1u << (std::abs(lit) - 1)));
                if (value == (lit > 0)) { sat = true; break; }
            }
            if (!sat) { all = false; break; }
        }
        if (all) return true;
    }
    return false;
}
static CNF pigeonhole(int pigeons, int holes) {
    CNF f;
    f.vars = pigeons * holes;
    auto cell = [holes](int p, int h) { return p * holes + h + 1; };
    for (int p = 0; p < pigeons; ++p) {
        std::vector<int> at_least_one;
        for (int h = 0; h < holes; ++h) at_least_one.push_back(cell(p, h));
        f.clauses.push_back(at_least_one);
    }
    for (int h = 0; h < holes; ++h)
        for (int a = 0; a < pigeons; ++a)
            for (int b = a + 1; b < pigeons; ++b)
                f.clauses.push_back({-cell(a, h), -cell(b, h)});
    return f;
}
static void gf2_selftest() {
    const auto parity=[](const std::vector<int>& vars,int rhs){
        CNF f;f.vars=4;
        for(int mask=0;mask<(1<<(int)vars.size());++mask){
            if((__builtin_popcount((unsigned)mask)&1)==rhs)continue;
            std::vector<int> forbid;
            for(size_t k=0;k<vars.size();++k)
                forbid.push_back((mask&(1<<k))?-vars[k]:vars[k]);
            f.clauses.push_back(std::move(forbid));
        }
        return f;
    };
    CNF first=parity({1,2,3},0), second=parity({1,2,4},0);
    CNF f;f.vars=4;f.clauses=first.clauses;
    f.clauses.insert(f.clauses.end(),second.clauses.begin(),second.clauses.end());
    f.clauses.push_back({3});
    auto source=extract_source_xors(f);
    auto closure=derive_reductive_xors(source);
    require(source.size()==2,"native R2 source complete parity detection wrong");
    require(closure.size()>=3 && closure[2].vars==std::vector<int>({3,4}) &&
            closure[2].rhs==0,"native R2 cross-row XOR cancellation missing");
    // Reject partial XOR blocks: their parity is not entailed by original CNF.
    CNF partial=f;
    partial.clauses.erase(partial.clauses.begin());
    require(extract_source_xors(partial).size()==1,
            "native R2 accepted incomplete source XOR clause block");
    // Verify each inferred row across all assignments satisfying ORIGINAL CNF.
    for(unsigned mask=0;mask<16;++mask){
        bool sat=true;
        for(const auto&clause:f.clauses){
            bool clause_sat=false;
            for(int lit:clause){
                const bool value=bool(mask&(1u<<(std::abs(lit)-1)));
                if(value==(lit>0)){clause_sat=true;break;}
            }
            sat &= clause_sat;
        }
        if(!sat)continue;
        for(const auto&row:closure){
            int sum=0;
            for(int v:row.vars)sum^=bool(mask&(1u<<(v-1)));
            require(sum==row.rhs,"GF2 row not entailed by original CNF");
        }
    }
    NativeCDCL plain(f.vars),gf2(f.vars);
    plain.add_cnf(f);gf2.add_cnf(f);
    gf2.enable_gf2_from_original(f);
    require(plain.solve(3.0)==10 && gf2.solve(3.0)==10,
            "GF2 synthetic original did not solve SAT");
    require(gf2.verify_original(f),"GF2 synthetic SAT witness invalid");
    require(gf2.statistics().xor_derived_implications>=1,
            "derived GF2 implication did not enter native CDCL");
    require(gf2.statistics().xor_reasons>=1,
            "GF2 source-entailed clause reason missing");
    std::cout<<"DRNAS_NATIVE_R3C_GF2_SELFTEST_PASS source_rows="
             <<source.size()<<" derived_rows="<<closure.size()-source.size()
             <<" derived_implications="
             <<gf2.statistics().xor_derived_implications
             <<" algebraic_assignments_checked=16"
             <<" third_party_solver_calls=0\n";
}
static void selftest() {
    gf2_selftest();
    std::mt19937 rng(0xD123A71u);
    unsigned checked = 0, verified_sat = 0, verified_unsat = 0;
    const auto one = [&](const CNF& f) {
        const bool expected=brute_sat(f);
        for(int mode=0;mode<2;++mode){
            NativeCDCL s(f.vars);
            s.add_cnf(f);
            if(mode==1)s.enable_gf2_from_original(f);
            int got=s.solve(12.0);
            require(got==(expected?10:20),"R2 exhaustive status disagreement");
            if(expected) {
                require(s.verify_original(f),"R2 invalid original SAT assignment");
                ++verified_sat;
            } else ++verified_unsat;
            ++checked;
        }
    };
    one({0, {}});      // vacuously SAT
    one({1, {{}}});    // empty clause UNSAT
    one({1, {{1}, {-1}}});
    one({2, {{1, -1}, {-2, -2}, {2}}});
    one({3, {{1, 2, 3}, {-1, -2, 3}, {1, -3}}});
    one(pigeonhole(3, 2));
    one(pigeonhole(4, 3));
    // All eight 3-variable assignments forbidden: strict UNSAT conflict tree.
    CNF all_forbidden;
    all_forbidden.vars = 3;
    for (unsigned m = 0; m < 8; ++m) {
        std::vector<int> c;
        for (int v = 1; v <= 3; ++v)
            c.push_back((m & (1u << (v - 1))) ? -v : v);
        all_forbidden.clauses.push_back(std::move(c));
    }
    one(all_forbidden);
    // Many generated formulas contain unit clauses, duplicates, tautologies,
    // arbitrary long clauses, and conflicting paths.
    for (int n = 1; n <= 9; ++n) {
        for (int sample = 0; sample < 90; ++sample) {
            CNF f; f.vars = n;
            const int count = 1 + int(rng() % (4 * n + 3));
            for (int k = 0; k < count; ++k) {
                const int width = int(rng() % (n + 4));
                std::vector<int> clause;
                for (int j = 0; j < width; ++j) {
                    const int v = int(rng() % unsigned(n)) + 1;
                    clause.push_back((rng() & 1u) ? v : -v);
                }
                f.clauses.push_back(std::move(clause));
            }
            one(f);
        }
    }
    std::cout << "DRNAS_NATIVE_R3C_SELFTEST_PASS cases=" << checked
              << " independently_bruteforced_sat=" << verified_sat
              << " independently_bruteforced_unsat=" << verified_unsat
              << " external_solver_dependencies=0\n";
}
}  // namespace drnas

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--selftest") {
            drnas::selftest();
            return 0;
        }
        if (!(argc == 6 && std::string(argv[2]) == "--mode" &&
              std::string(argv[4]) == "--time")) {
            std::cerr << "Usage: drnas-native-core-r3c FORMULA.cnf --mode plain|gf2 --time SECONDS\n"
                      << "       drnas-native-core-r3c --selftest\n";
            return 2;
        }
        const std::string mode=argv[3];
        drnas::require(mode=="plain"||mode=="gf2","unknown R2 mode");
        double seconds = std::stod(argv[5]);
        drnas::require(seconds > 0 && seconds <= 3600 && std::isfinite(seconds),
                       "time cap must be 0 < seconds <= 3600");
        const auto overall_start = drnas::Clock::now();
        const auto input = drnas::read_dimacs(argv[1]);
        const auto parse_s = std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        drnas::NativeCDCL solver(input.vars);
        solver.add_cnf(input);
        if(mode=="gf2")solver.enable_gf2_from_original(input);
        double remaining = seconds - std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        int status = remaining > 0 ? solver.solve(remaining) : 0;
        if (status == 10) {
            drnas::require(solver.verify_original(input),
                           "invalid original CNF SAT model, refuse SAT");
        }
        const auto e2e_s = std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        std::cout << std::fixed << std::setprecision(6);
        const auto& s = solver.statistics();
        std::cout << "c DRNAS_NATIVE_R3C_RESULT mode="<<mode<<" status="
                  << (status == 10 ? "SAT" : status == 20 ? "UNSAT" : "UNKNOWN")
                  << " solver_s=" << (remaining > 0 ? solver.solve_elapsed_s() : 0)
                  << " e2e_s=" << e2e_s << " input_parse_s=" << parse_s
                  << " conflicts=" << s.conflicts << " decisions=" << s.decisions
                  << " propagations=" << s.propagations
                  << " learned=" << s.learned_clauses
                  << " restarts=" << s.restarts
                  << " watch_visits=" << s.watch_visits
                  << " resource_limited=" << int(solver.hit_resource_limit())
                  << " original_model_checked=" << int(status == 10)
                  << " UNSAT_independent_LRAT=0"
                  << " xor_certified_candidates=" << s.xor_certified_candidates
                  << " xor_source_rows=" << s.xor_source_rows
                  << " xor_derived_rows=" << s.xor_derived_rows
                  << " xor_checks=" << s.xor_checks
                  << " xor_implications=" << s.xor_implications
                  << " xor_derived_implications=" << s.xor_derived_implications
                  << " xor_conflicts=" << s.xor_conflicts
                  << " xor_reasons=" << s.xor_reasons
                  << " xor_events_enqueued=" << s.xor_events_enqueued
                  << " xor_events_processed=" << s.xor_events_processed
                  << " heap_pops=" << s.heap_pops
                  << " heap_pushes=" << s.heap_pushes
                  << " heap_bumps=" << s.heap_bumps
                  << " heap_removals=" << s.heap_removals
                  << " xor_budget_off=" << s.xor_budget_off
                  << " third_party_solver_calls=0\n";
        if (status == 10) {
            std::cout << "s SATISFIABLE\nv ";
            const auto& model = solver.assignments();
            for (int v = 1; v <= input.vars; ++v) {
                std::cout << (model[v] == -1 ? -v : v) << " ";
                if (v % 30 == 0) std::cout << "0\nv ";
            }
            std::cout << "0\n";
        } else if (status == 20) std::cout << "s UNSATISFIABLE\n";
        else std::cout << "s UNKNOWN\n";
        return status == 10 ? 10 : status == 20 ? 20 : 0;
    } catch (const std::exception& e) {
        std::cerr << "DRNAS_NATIVE_R3C_FAIL_CLOSED " << e.what() << "\n";
        return 2;
    }
}

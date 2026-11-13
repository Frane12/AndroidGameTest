// DRNAS X5 -- minimized conflict learning, protected clause tiers, compact storage.
// Derived from frozen X47 1670a8fd; no external solver linked.
// Pilot phase: trace is observational ONLY; policy identical to X3 core.
// Original implementation. No external SAT solver is linked or invoked.
#include <algorithm>
#include <chrono>
#include <bit>
#include <charconv>
#include <string_view>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;

enum class Result { SAT = 10, UNSAT = 20, UNKNOWN = 0 };
enum class PropResult { OK, CONFLICT, LIMIT, TIMEOUT };

struct Clause {
    std::vector<int> lits;
    bool learnt = false;
    bool deleted = false;
    double activity = 0.0;
    int glue = 0;
    int64_t last_used = 0;
};
struct Watch { int clause; int blocker; };
struct Prop { PropResult result = PropResult::OK; int conflict = -1; int inspected = 0; };
struct Stats {
    int64_t conflicts = 0, decisions = 0, propagations = 0;
    int64_t restarts = 0, learnt = 0, horizon_probes = 0;
    int64_t horizon_conflicts = 0, horizon_inspections = 0;
    int64_t reduce_removed = 0;
    int64_t minimized_literals=0, minimize_visits=0, compacted_clauses=0;
    int64_t collections=0, heap_rebuilds=0, protected_clauses=0;
    int64_t binary_edges = 0, binary_propagations = 0;
    int64_t backdoor_checks = 0, backdoor_leaves = 0, backdoor_sat = 0;
    int64_t backdoor_unsat = 0, backdoor_nogoods = 0;
    int64_t depth_probes = 0, depth_conflicts = 0;
    int64_t depth_positive_gain = 0;
    int64_t pattern_samples = 0, prefilter_rejects = 0, prefilter_attempts = 0;
    int64_t controller_probed_decisions = 0, controller_feedback = 0;
    int64_t controller_positive = 0, controller_conflict_feedback = 0;
    int64_t controller_cooldowns = 0, controller_gained_long = 0;
    int64_t controller_actual_implied = 0;
    int64_t trace_samples_total=0, trace_samples_retained=0;
    int64_t trace_conflicts=0, trace_implied=0, trace_evicted=0;
    int64_t x58_blocker_write_skips=0;
    int64_t x59_stamp_glue_calls=0, x59_stamp_seen_levels=0;

};
struct Entry {
    double score;
    int variable;
    uint64_t generation;
    bool operator<(const Entry& rhs) const {
        if (score != rhs.score) return score < rhs.score;
        return variable > rhs.variable;
    }
};

class Solver {
  public:
    struct BranchProbeCost {
        int result=0;
        int64_t conflicts=0,decisions=0,propagations=0;
        double wall_ms=0.0;
    };
    explicit Solver(int n, std::string mode, double seconds, Clock::time_point started, bool trace_trail=false, int compare_at=0, bool flip_sign=false)
        : n_(n), mode_(std::move(mode)),
          use_backdoor_(false),
          use_depth_(false),
          trace_enabled_(mode_ == "trace"), trace_trail_(trace_trail),
          compare_at_(compare_at), compare_flip_(flip_sign),
          watches_(2 * static_cast<size_t>(n)),
          binary_implications_(2 * static_cast<size_t>(n)),
          values_(n, 0), phase_(n, 1), levels_(n, 0), reasons_(n, -1),
          seen_(n, 0), activity_(n, 0), base_(n, 0), positive_(n, 0),
          negative_(n, 0), binary_(n, 0), generation_(n, 0), timeout_s_(seconds), begun_(started) {
        if (n < 0 || n > 20000000) throw std::runtime_error("unsupported DIMACS variable count");
    }

    void configureX5(bool minimize, bool retain, bool gc, bool restarts, std::ostream* proof) {
        x5_minimize_=minimize; x5_retain_=retain; x5_gc_=gc;
        x5_restarts_=restarts; proof_=proof;
    }
    void configureX58(bool enabled) { x58_blocker_compact_skip_=enabled; }
    void configureX59(bool enabled) { x59_stamp_glue_=enabled; }
    void writeProofClause(const std::vector<int>& lits) {
        if (!proof_ || x46_clone_) return;
        for (int lit:lits) *proof_ << lit << ' ';
        *proof_ << "0\n";
        if (!*proof_) throw std::runtime_error("proof write failed");
    }
    void addOriginal(std::vector<int> lits) {
        ++original_count_;
        std::sort(lits.begin(), lits.end(), [](int a, int b) {
            if (std::abs(a) != std::abs(b)) return std::abs(a) < std::abs(b);
            return a < b;
        });
        std::vector<int> clean;
        clean.reserve(lits.size());
        for (int lit : lits) {
            if (lit == 0 || std::abs(static_cast<int64_t>(lit)) > n_) {
                throw std::runtime_error("DIMACS literal outside declared variable range");
            }
            if (!clean.empty() && clean.back() == lit) continue;
            if (!clean.empty() && clean.back() == -lit) { --original_count_; return; } // tautology
            clean.push_back(lit);
        }
        if (clean.empty()) root_unsat_ = true;
        for (int lit : clean) {
            (lit > 0 ? positive_ : negative_)[std::abs(lit)-1]++;
            if (clean.size() == 2) binary_[std::abs(lit)-1]++;
        }
        const int cid = storeClause(std::move(clean), false);
        if (clauses_[cid].lits.size() == 1) units_.push_back(cid);
    }

    void finishParsing() {
        for (int v=0; v<n_; ++v) {
            double count = static_cast<double>(positive_[v] + negative_[v]);
            double balance = 1.0 - std::abs(static_cast<double>(positive_[v] - negative_[v])) / std::max(1.0, count);
            base_[v] = 0.05*std::log1p(count) + 0.10*balance + 0.10*binary_[v]/std::max(1.0,count);
            phase_[v] = positive_[v] >= negative_[v] ? 1 : -1;
            offer(v);
        }
        for (int cid : units_) {
            if (!enqueue(clauses_[cid].lits[0], cid)) root_unsat_ = true;
        }
    }

    enum class Backdoor { SKIP, SAT, UNSAT, LEARNED };

    // Exact detection of a short strong backdoor into 2-SAT.
    // A residual clause is evaluated under the current CDCL trail.
    // If all residual widths are <=2, implication SCC determines SAT exactly.
    // For an UNSAT leaf, D_1 & ... & D_k is impossible, so the nogood
    // (~D_1 | ... | ~D_k) is entailed by the ORIGINAL CNF.
    Backdoor tryTwoSat() {
        if (!use_backdoor_ || n_>12000 || original_count_>90000 ||
            decisionLevel()>12 || timedOut()) return Backdoor::SKIP;
        if (stats_.decisions == last_backdoor_decisions_ && decisionLevel()!=0)
            return Backdoor::SKIP;
        if (decisionLevel()>=4 && stats_.decisions%4!=0) return Backdoor::SKIP;
        last_backdoor_decisions_ = stats_.decisions;
        // A sampled unresolved clause of residual width >=3 proves that
        // we are NOT yet at a 2-SAT leaf. This is a one-way, sound gate;
        // passing the filter never assumes that the residual is 2-SAT.
        ++stats_.prefilter_attempts;
        if (structuralDistance(1) > 0) {
            ++stats_.prefilter_rejects;
            return Backdoor::SKIP;
        }
        ++stats_.backdoor_checks;
        std::vector<std::pair<int,int>> residual;
        residual.reserve(std::min(original_count_,60000));
        for (const Clause& c : clauses_) {
            if (c.learnt) continue;
            int a=0,b=0, cnt=0;
            bool satisfied=false;
            for (int lit : c.lits) {
                const int val=value(lit);
                if (val==1) {satisfied=true;break;}
                if (val==0) {
                    if (cnt==0) a=lit;
                    else if (cnt==1) b=lit;
                    ++cnt;
                    if (cnt>2) break;
                }
            }
            if (satisfied) continue;
            if (cnt>2) return Backdoor::SKIP;
            if (cnt==0) return learnBackdoorNogood();
            residual.emplace_back(a,b);
        }
        ++stats_.backdoor_leaves;
        const int N=2*n_;
        std::vector<std::vector<int>> g(static_cast<size_t>(N));
        std::vector<std::vector<int>> reverse(static_cast<size_t>(N));
        auto node=[](int l) {return (std::abs(l)-1)*2+(l<0);};
        auto edge=[&](int u,int v) {
            g[u].push_back(v);
            reverse[v].push_back(u);
        };
        for (const auto& [a,b] : residual) {
            const int na=node(a);
            if (!b) edge(na^1,na);
            else {
                const int nb=node(b);
                edge(na^1,nb);
                edge(nb^1,na);
            }
        }
        std::vector<uint8_t> visited(static_cast<size_t>(N),0);
        std::vector<int> order;
        order.reserve(static_cast<size_t>(N));
        for (int start=0;start<N;++start) if (!visited[start]) {
            std::vector<std::pair<int,size_t>> st;
            st.emplace_back(start,0);
            visited[start]=1;
            while (!st.empty()) {
                int x=st.back().first;
                size_t& j=st.back().second;
                if (j<g[x].size()) {
                    int y=g[x][j++];
                    if (!visited[y]) {visited[y]=1; st.emplace_back(y,0);}
                } else {order.push_back(x);st.pop_back();}
            }
        }
        std::vector<int> comp(static_cast<size_t>(N),-1);
        int cc=0;
        for (auto it=order.rbegin();it!=order.rend();++it) {
            if (comp[*it]!=-1) continue;
            std::vector<int> st{*it};
            comp[*it]=cc;
            while (!st.empty()) {
                int x=st.back();st.pop_back();
                for (int y:reverse[x]) if (comp[y]==-1) {
                    comp[y]=cc;st.push_back(y);
                }
            }
            ++cc;
        }
        for (int v=0;v<n_;++v) {
            if (comp[2*v]==comp[2*v+1]) {
                ++stats_.backdoor_unsat;
                return learnBackdoorNogood();
            }
        }
        leaf_model_.resize(static_cast<size_t>(n_));
        for (int v=0;v<n_;++v)
            leaf_model_[v]=values_[v]!=0?values_[v]:(comp[2*v]>comp[2*v+1]?1:-1);
        if (!verifyModel()) throw std::runtime_error("invalid 2SAT SCC model");
        ++stats_.backdoor_sat;
        return Backdoor::SAT;
    }
    Backdoor learnBackdoorNogood() {
        const int depth=decisionLevel();
        if (depth==0) return Backdoor::UNSAT;
        std::vector<int> nogood;
        nogood.reserve(static_cast<size_t>(depth));
        for (int k=depth-1;k>=0;--k) {
            const int at=trail_lim_[static_cast<size_t>(k)];
            nogood.push_back(-trail_[static_cast<size_t>(at)]);
        }
        // The last decision disappears; the new clause is asserting.
        cancelUntil(depth-1);
        const int cid=storeClause(std::move(nogood),true);
        ++stats_.learnt;
        ++stats_.backdoor_nogoods;
        if (!enqueue(clauses_[cid].lits[0],cid))
            throw std::runtime_error("backdoor nogood did not assert");
        return Backdoor::LEARNED;
    }

    Result solve() {
        if (timedOut()) return Result::UNKNOWN;
        if (root_unsat_) return Result::UNSAT;
        Prop p;
        if (!x46_clone_) {
            p = propagate(-1);
            if (p.result == PropResult::CONFLICT) return Result::UNSAT;
            if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
        }
        while (true) {
            if (timedOut() || x46CloneBudgetReached()) return Result::UNKNOWN;
            p = propagate(-1);
            if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
            if (p.result == PropResult::CONFLICT) {
                endTransition(true);
                settleFeedback(true);
                ++stats_.conflicts;
                if (decisionLevel() == 0) return Result::UNSAT;
                std::vector<int> learned;
                int level = analyze(p.conflict, learned);
                const int glue=computeGlue(learned);
                fast_glue_+=(glue-fast_glue_)/32.0;
                slow_glue_+=(glue-slow_glue_)/4096.0;
                cancelUntil(level);
                const int cid = storeClause(std::move(learned), true);
                clauses_[cid].glue=glue;
                clauses_[cid].last_used=stats_.conflicts;
                clause_inc_/=0.999;
                ++stats_.learnt;
                if (!enqueue(clauses_[cid].lits[0], cid)) {
                    throw std::runtime_error("internal asserting-clause invariant violated");
                }
                var_inc_ /= 0.95;
                const bool dynamic_restart=x5_restarts_ && stats_.conflicts-last_restart_>=64 &&
                    (fast_glue_>1.25*slow_glue_ || stats_.conflicts-last_restart_>=2000);
                if ((!x5_restarts_ && stats_.conflicts >= next_restart_) || dynamic_restart) {
                    cancelUntil(0);
                    ++stats_.restarts;
                    last_restart_=stats_.conflicts;
                    fast_glue_=slow_glue_;
                    restart_interval_ = std::min<int64_t>(2000, static_cast<int64_t>(static_cast<double>(restart_interval_) * 1.45) + 1);
                    next_restart_ = stats_.conflicts + restart_interval_;
                }
                if (stats_.conflicts >= next_reduce_) {
                    reduceLearnts();
                    next_reduce_ = stats_.conflicts + 1400;
                }
                continue;
            }
            endTransition(false);
            settleFeedback(false);
            const Backdoor backdoor=tryTwoSat();
            if (backdoor==Backdoor::SAT) return Result::SAT;
            if (backdoor==Backdoor::UNSAT) return Result::UNSAT;
            if (backdoor==Backdoor::LEARNED) continue;
            if (timedOut()) return Result::UNKNOWN;
            int v = selectVariable();
            if (v == -1) {
                if (!verifyModel()) throw std::runtime_error("internal model verification failed");
                return Result::SAT;
            }
            const int64_t next_decision=stats_.decisions+1;
            const int baseline_lit=phase_[v]*(v+1);
            int chosen_lit=baseline_lit;
            // Two detached snapshots have identical selected-variable,
            // watch lists, heap, phases, learnt clauses, and restart schedule.
            // Work done by either probe is NEVER committed to the real solver.
            if (!x46_clone_ && x46_enabled_ && compare_at_>0 &&
                next_decision==compare_at_) {
                x46_probe_digest_=stateDigestAtDecision(v);
                if ((timeout_s_>0.0 && elapsed()>0.55*timeout_s_) ||
                    clauses_.size()>60000 || n_>2500 ||
                    (x47_enabled_ &&
                     (n_<x47_min_vars_||original_count_<x47_min_clauses_||
                      compare_at_>x47_max_k_))) {
                    if(x47_enabled_)x47_gate_skipped_=true;
                    x46_skipped_=true;
                } else {
                    x46_triggered_=true;
                    const auto start=Clock::now();
                    x46_base_=shortProbeBranch(baseline_lit);
                    x46_alt_=shortProbeBranch(-baseline_lit);
                    x46_probes_wall_ms_=std::chrono::duration<double,std::milli>(
                        Clock::now()-start).count();
                    bool want_flip=x46_model_loaded_?learnedAlternate(x46_base_,x46_alt_):preferAlternate(x46_base_,x46_alt_);
                    if(x47_enabled_ && want_flip){
                        const double prob=x46_model_probability_;
                        x47_expected_saving_=prob*x47_avg_win_-
                            (1-prob)*(x47_avg_regret_+x47_risk_weight_*x47_tail_regret_);
                        if(prob<x47_probability_floor_||
                            x47_expected_saving_<x47_min_expected_saving_) {
                            want_flip=false;
                            x47_rejected_after_probe_=true;
                        }
                    }
                    x46_chose_flip_=want_flip;
                    if (want_flip && !x46_shadow_)chosen_lit=-baseline_lit;
                }
            }
            if(compare_at_>0 && next_decision==compare_at_) {
                compare_reached_=true;
                compare_pre_hash_=stateDigestAtDecision(v);
                compare_baseline_literal_=baseline_lit;
                if (compare_flip_) chosen_lit=-baseline_lit;
                compare_actual_literal_=chosen_lit;
                compare_prefix_conflicts_=stats_.conflicts;
                compare_prefix_learnt_=stats_.learnt;
                compare_prefix_propagations_=stats_.propagations;
                compare_prefix_elapsed_=elapsed();
            }
            ++stats_.decisions;
            beginTransition(chosen_lit);
            newDecisionLevel();
            if (!enqueue(chosen_lit, -1)) {
                throw std::runtime_error("internal decision invariant violated");
            }
        }
    }

    bool verifyModel() const {
        for (const Clause& c : clauses_) {
            if (c.learnt) continue;
            if (c.lits.empty()) return false;
            bool satisfied = false;
            for (int lit : c.lits) {
                int v = std::abs(lit)-1;
                int x = !leaf_model_.empty() ? leaf_model_[v] : values_[v];
                if (x == (lit>0 ? 1 : -1)) { satisfied = true; break; }
            }
            if (!satisfied) return false;
        }
        return true;
    }

    // A bounded, observational record of chosen decisions and their immediate
    // BCP outcomes. This is NOT a distance-to-solution estimate, and is NEVER
    // read by the branching policy.  Uncertified UNSAT is labelled as such.
    void writeTransitions(const std::string& path, Result result, double solve_finish_elapsed) const {
        if (!trace_enabled_ || path.empty()) return;
        std::ofstream fd(path);
        if (!fd) throw std::runtime_error("cannot create trace file: "+path);
        fd<<std::fixed<<std::setprecision(7);
        const char* outcome=result==Result::SAT?"SAT_INTERNAL_WITNESS_VERIFIED":
               result==Result::UNSAT?"UNSAT_INTERNAL_ONLY":"UNKNOWN";
        fd<<"{\"type\":\"meta\",\"version\":2,\"policy\":\"x4_core_unmodified\","
             "\"observational_only\":true,\"result\":\""<<outcome<<"\","
             "\"sampled_total\":"<<stats_.trace_samples_total<<",\"retained\":"<<trace_records_.size()
             <<",\"source_nvars\":"<<n_<<",\"source_clauses\":"<<original_count_<<"}\n";
        auto snap=[&](const Snapshot& a) {
            fd<<"{\"decisions\":"<<a.decisions<<",\"conflicts\":"<<a.conflicts
              <<",\"learnt\":"<<a.learnt<<",\"propagations\":"<<a.propagations
              <<",\"assigned\":"<<a.assigned<<",\"level\":"<<a.level
              <<",\"sample_unresolved_long\":"<<a.long_open
              <<",\"sampled_total\":"<<a.sampled_total
              <<",\"sample_open_unit\":"<<a.sampled_open_unit
              <<",\"sample_open_binary\":"<<a.sampled_open_binary
              <<",\"sample_satisfied\":"<<a.sampled_satisfied
              <<",\"sample_falsified\":"<<a.sampled_falsified
              <<",\"elapsed_s\":"<<a.elapsed_s<<"}";
        };
        // Chronological output (ring buffer may wrap). Each row represents a
        // single real decision, not a speculative probe, and a real BCP outcome.
        const size_t count=trace_records_.size();
        for (size_t i=0;i<count;++i) {
            const TraceRecord& record=trace_records_[(trace_records_start_+i)%count];
            fd<<"{\"type\":\"transition\",\"decision_literal\":"<<record.decision_literal
              <<",\"propagation_conflict\":"<<(record.conflict?"true":"false")
              <<",\"before\":";
            snap(record.before);
            fd<<",\"after\":";
            snap(record.after);
            if (trace_trail_) {
                auto write_trail=[&](const std::vector<int>& lit){
                    fd<<"[";
                    for (size_t k=0;k<lit.size();++k){if(k)fd<<",";fd<<lit[k];}
                    fd<<"]";
                };
                fd<<",\"trail_before\":";write_trail(record.trail_before);
                fd<<",\"trail_after\":";write_trail(record.trail_after);
            }
            const int bcp_units=std::max(0, record.after.assigned-record.before.assigned-1);
            // *Logic*: every counted unit follows from the current assumptions
            // and CNF; an assumption-relative conflict is NOT a global UNSAT proof.
            fd<<",\"logic\":{\"unit_propagations_under_assumptions\":"<<bcp_units
              <<",\"conflict_under_assumptions\":"<<(record.conflict?"true":"false")
              <<",\"global_unsat_certificate\":false}";
            // *Structure*: sampled residual clause widths, NOT answer distance.
            fd<<",\"structure\":{\"sample_original_clauses\":"<<record.before.sampled_total
              <<",\"delta_open_long\":"<<(record.before.long_open-record.after.long_open)
              <<",\"delta_open_binary\":"<<(record.before.sampled_open_binary-record.after.sampled_open_binary)
              <<",\"delta_satisfied\":"<<(record.after.sampled_satisfied-record.before.sampled_satisfied)
              <<",\"exact_backdoor_proven\":false}";
            // *Forecast*: a retrospective, policy-conditional runtime label.
            // Only internally verified SAT has a concrete target; external
            // witness verification is still REQUIRED before model training.
            const bool sat=(result==Result::SAT);
            fd<<",\"future\":{\"causal_effect_known\":false,\"label_origin\":\""
              <<(sat?"internal_verified_sat":"unverified_or_censored")<<"\"}"
              <<",\"remaining_finish_wall_s\":";
            if (sat) fd<<std::max(0.0,solve_finish_elapsed-record.before.elapsed_s);
            else fd<<"null";
            fd<<"}\n";
        }
    }
    void loadX46CostModel(const std::string& path) {
        std::ifstream input(path);
        if(!input)throw std::runtime_error("cannot open X46 learned model");
        std::string version;int dimensions=0;
        if(!(input>>version>>dimensions)||version!="X46COST1"||dimensions!=12)
            throw std::runtime_error("incompatible X46 learned model");
        if(!(input>>x46_model_threshold_>>x46_model_bias_)||
           !std::isfinite(x46_model_threshold_)||x46_model_threshold_<0.5||
           x46_model_threshold_>0.99||!std::isfinite(x46_model_bias_))
            throw std::runtime_error("invalid X46 model threshold");
        x46_model_mean_.clear();x46_model_scale_.clear();x46_model_weight_.clear();
        for(int i=0;i<dimensions;++i) {
            double u=0,s=0,w=0;
            if(!(input>>u>>s>>w)||!std::isfinite(u)||!std::isfinite(s)||
                !std::isfinite(w)||s<1e-8||s>1e6||std::abs(w)>100)
                throw std::runtime_error("corrupt X46 learned model");
            x46_model_mean_.push_back(u);x46_model_scale_.push_back(s);
            x46_model_weight_.push_back(w);
        }
        std::string extra;if(input>>extra)
            throw std::runtime_error("unexpected trailing X46 model data");
        x46_model_loaded_=true;
    }
    void loadX47Guard(const std::string& path) {
        std::ifstream input(path);
        if(!input)throw std::runtime_error("X47 guard model missing");
        std::string version;int format=0;
        if(!(input>>version>>format) || version!="X47GUARD1"||format!=1)
            throw std::runtime_error("incompatible X47 guard");
        if(!(input>>x47_min_vars_>>x47_min_clauses_>>x47_max_k_>>
             x47_probability_floor_>>x47_min_expected_saving_>>
             x47_avg_win_>>x47_avg_regret_>>x47_tail_regret_>>x47_risk_weight_))
            throw std::runtime_error("incomplete X47 guard");
        if(x47_min_vars_<0||x47_min_vars_>20000000||x47_min_clauses_<0||
           x47_min_clauses_>10000000||x47_max_k_<1||x47_max_k_>100000||
           !std::isfinite(x47_probability_floor_)||x47_probability_floor_<.5||
           x47_probability_floor_>1.0||
           !std::isfinite(x47_min_expected_saving_)||x47_min_expected_saving_<0||
           !std::isfinite(x47_avg_win_)||x47_avg_win_<0||
           !std::isfinite(x47_avg_regret_)||x47_avg_regret_<0||
           !std::isfinite(x47_tail_regret_)||x47_tail_regret_<0||
           !std::isfinite(x47_risk_weight_)||x47_risk_weight_<0||
           x47_risk_weight_>20)
            throw std::runtime_error("invalid X47 risk guard bounds");
        std::string extra;if(input>>extra)throw std::runtime_error("X47 guard trailing data");
        x47_enabled_=true;
    }
    void configureX46(int conflicts,bool shadow,double probe_ms) {
        if(conflicts!=8 && conflicts!=32 && conflicts!=128)
            throw std::runtime_error("X46 conflicts must be 8, 32 or 128");
        if(probe_ms<=0.0 || probe_ms>25.0 || !std::isfinite(probe_ms))
            throw std::runtime_error("X46 probe wall budget invalid");
        x46_enabled_=true;x46_shadow_=shadow;
        x46_probe_conflict_cap_=conflicts;
        x46_probe_wall_ms_=probe_ms;
    }
    bool x46Triggered() const{return x46_triggered_;}
    bool x46Skipped() const{return x46_skipped_;}
    bool x46ChosenFlip() const{return x46_chose_flip_;}
    bool x46Shadow() const{return x46_shadow_;}
    bool x46ModelLoaded() const{return x46_model_loaded_;}
    bool x47Enabled() const{return x47_enabled_;}
    bool x47PreProbeEligible() const {
        return !x47_enabled_ || (n_>=x47_min_vars_ &&
            original_count_>=x47_min_clauses_ && compare_at_<=x47_max_k_);
    }
    bool x47SkippedByGate() const{return x47_gate_skipped_;}
    double x47PredictedNetConflicts() const{return x47_expected_saving_;}
    bool x47RejectedAfterProbe() const{return x47_rejected_after_probe_;}
    double x46ModelProbability() const{return x46_model_probability_;}
    double x46ProbesWallMs() const{return x46_probes_wall_ms_;}
    uint64_t x46ProbesHash() const{return x46_probe_digest_;}
    const BranchProbeCost& x46Base() const{return x46_base_;}
    const BranchProbeCost& x46Alt() const{return x46_alt_;}
    uint64_t comparePreHash() const{return compare_pre_hash_;}
    bool compareReached() const{return compare_reached_;}
    int compareAt() const{return compare_at_;}
    bool compareFlipped() const{return compare_flip_;}
    int compareBaselineLiteral() const{return compare_baseline_literal_;}
    int compareActualLiteral() const{return compare_actual_literal_;}
    int64_t comparePrefixConflicts() const{return compare_prefix_conflicts_;}
    int64_t comparePrefixLearnt() const{return compare_prefix_learnt_;}
    int64_t comparePrefixPropagations() const{return compare_prefix_propagations_;}
    double comparePrefixElapsed() const{return compare_prefix_elapsed_;}
    int nvars() const { return n_; }
    int nclauses() const { return original_count_; }
    int assignment(int v) const { return !leaf_model_.empty() ? leaf_model_[v] : (values_[v] == 0 ? phase_[v] : values_[v]); }
    const Stats& stats() const { return stats_; }
    double probeSeconds() const { return probing_seconds_; }
    double elapsed() const { return std::chrono::duration<double>(Clock::now() - begun_).count(); }
    const char* mode() const { return mode_.c_str(); }

  private:
    bool x5_minimize_=true, x5_retain_=false, x5_gc_=true, x5_restarts_=false;
    bool x58_blocker_compact_skip_=false;
    bool x59_stamp_glue_=false;
    std::vector<uint32_t> x59_level_stamps_;
    uint32_t x59_epoch_=0;
    std::ostream* proof_=nullptr; // externally owned; speculative clones cannot log
    double clause_inc_=1.0,fast_glue_=8.0,slow_glue_=8.0;
    int64_t last_restart_=0;
    std::vector<uint8_t> minimize_marks_;
    std::vector<int> minimize_touched_;
    const int n_;
    const std::string mode_;
    const bool use_backdoor_;
    const bool use_depth_;
    const bool trace_enabled_;
    const bool trace_trail_;
    const int compare_at_;
    const bool compare_flip_;
    bool compare_reached_=false;
    uint64_t compare_pre_hash_=0;
    int compare_baseline_literal_=0;
    int compare_actual_literal_=0;
    int64_t compare_prefix_conflicts_=0,compare_prefix_learnt_=0,compare_prefix_propagations_=0;
    double compare_prefix_elapsed_=0.0;
    // X4.6 experimental probe parameters. Always scoped to ONE designated
    // checkpoint decision; never used to assert clauses, SAT, or UNSAT.
    bool x46_enabled_=false,x46_shadow_=false,x46_clone_=false;
    bool x46_triggered_=false,x46_skipped_=false,x46_chose_flip_=false;
    bool x46_model_loaded_=false;
    bool x47_enabled_=false,x47_gate_skipped_=false,x47_rejected_after_probe_=false;
    int x47_min_vars_=0,x47_min_clauses_=0,x47_max_k_=8;
    double x47_probability_floor_=0.8,x47_min_expected_saving_=8;
    double x47_avg_win_=0,x47_avg_regret_=0,x47_tail_regret_=0,x47_risk_weight_=1;
    double x47_expected_saving_=-1;
    double x46_model_threshold_=0.75,x46_model_bias_=0.0,x46_model_probability_=-1.0;
    std::vector<double> x46_model_mean_,x46_model_scale_,x46_model_weight_;
    int x46_probe_conflict_cap_=0, x46_clone_conflict_cap_=0;
    int x46_clone_decision_cap_=0;
    double x46_probe_wall_ms_=1.5,x46_probes_wall_ms_=0.0;
    double x46_clone_wall_limit_ms_=0.0;
    uint64_t x46_probe_digest_=0;
    int64_t x46_clone_origin_conflicts_=0,x46_clone_origin_decisions_=0;
    Clock::time_point x46_clone_started_=Clock::now();
    BranchProbeCost x46_base_{},x46_alt_{};
    // The original solve's restart/reduction schedule is retained in
    // copied states; clones no longer silently reset it.
    int64_t restart_interval_=96,next_restart_=96,next_reduce_=2200;
    struct Snapshot {
        int64_t decisions=0, conflicts=0, learnt=0, propagations=0;
        int assigned=0, level=0, long_open=0;
        int sampled_total=0, sampled_open_unit=0, sampled_open_binary=0;
        int sampled_satisfied=0, sampled_falsified=0;
        double elapsed_s=0;
    };
    struct TraceRecord {
        int decision_literal=0;
        bool conflict=false;
        Snapshot before,after;
        std::vector<int> trail_before,trail_after;
    };
    static constexpr size_t MAX_TRACE_ROWS=512;
    std::vector<TraceRecord> trace_records_;
    size_t trace_records_start_=0;
    bool trace_pending_=false;
    TraceRecord trace_pending_row_;
    std::vector<Clause> clauses_;
    std::vector<std::vector<Watch>> watches_;
    std::vector<std::vector<std::pair<int,int>>> binary_implications_;
    std::vector<int8_t> values_, phase_;
    std::vector<int> levels_, reasons_, trail_, trail_lim_, units_;
    std::vector<uint8_t> seen_;
    std::vector<double> activity_, base_;
    std::vector<int> positive_, negative_, binary_;
    std::vector<uint64_t> generation_;
    std::priority_queue<Entry> heap_;
    int qhead_ = 0, original_count_ = 0;
    bool root_unsat_ = false, probing_ = false;
    double var_inc_ = 1.0, timeout_s_;
    Clock::time_point begun_ = Clock::now();
    Stats stats_;
    std::vector<int8_t> leaf_model_; // nonempty only for a verified 2-SAT leaf
    int64_t last_backdoor_decisions_ = -1;
    double probing_seconds_ = 0.0;
    // Online controller state; only information from the CURRENT solve.
    // No benchmark labels, file names, hashes or ground truth reach it.
    int64_t cooldown_until_decision_ = 0;
    int feedback_window_count_ = 0, feedback_window_good_ = 0;
    bool feedback_pending_ = false;
    int feedback_before_long_ = 0, feedback_before_trail_ = 0;


    // Snapshot of a deterministic 64-clause sample from the ORIGINAL CNF.
    // Observations under a partial assignment are not claims of proximity to SAT.
    struct ClauseSample {
        int total=0, open_unit=0, open_binary=0, open_long=0;
        int satisfied=0, falsified=0;
    };
    ClauseSample sampleStructure() const {
        ClauseSample result;
        const int limit=std::min(64,original_count_);
        for (int i=0;i<limit;++i) {
            const Clause& c=clauses_[static_cast<size_t>((static_cast<int64_t>(i)*original_count_)/limit)];
            ++result.total;
            int open=0; bool satisfied=false;
            for (int lit:c.lits) {
                const int x=value(lit);
                if (x==1) {satisfied=true;break;}
                if (x==0) ++open;
            }
            if (satisfied) ++result.satisfied;
            else if (open==0) ++result.falsified;
            else if (open==1) ++result.open_unit;
            else if (open==2) ++result.open_binary;
            else ++result.open_long;
        }
        return result;
    }
    Snapshot snapshot() const {
        Snapshot a;
        a.decisions=stats_.decisions;
        a.conflicts=stats_.conflicts;
        a.learnt=stats_.learnt;
        a.propagations=stats_.propagations;
        a.assigned=static_cast<int>(trail_.size());
        a.level=decisionLevel();
        const ClauseSample sm=sampleStructure();
        a.sampled_total=sm.total;
        a.sampled_open_unit=sm.open_unit;
        a.sampled_open_binary=sm.open_binary;
        a.long_open=sm.open_long;
        a.sampled_satisfied=sm.satisfied;
        a.sampled_falsified=sm.falsified;
        a.elapsed_s=elapsed();
        return a;
    }
    void beginTransition(int literal) {
        if (!trace_enabled_) return;
        const int64_t d=stats_.decisions;
        if ((!trace_trail_ || d>128) && d>16 && (d&(d-1))!=0 && d%4096!=0) return;
        trace_pending_=true;
        trace_pending_row_=TraceRecord{};
        trace_pending_row_.decision_literal=literal;
        trace_pending_row_.before=snapshot();
        if (trace_trail_) trace_pending_row_.trail_before=trail_;
        ++stats_.trace_samples_total;
    }
    void endTransition(bool conflict) {
        if (!trace_pending_) return;
        trace_pending_=false;
        trace_pending_row_.conflict=conflict;
        trace_pending_row_.after=snapshot();
        if (trace_trail_) trace_pending_row_.trail_after=trail_;
        stats_.trace_conflicts+=conflict;
        stats_.trace_implied+=std::max(0,trace_pending_row_.after.assigned-trace_pending_row_.before.assigned-1);
        if (trace_records_.size()<MAX_TRACE_ROWS) trace_records_.push_back(trace_pending_row_);
        else {
            trace_records_[trace_records_start_]=trace_pending_row_;
            trace_records_start_=(trace_records_start_+1)%MAX_TRACE_ROWS;
            ++stats_.trace_evicted;
        }
        stats_.trace_samples_retained=static_cast<int64_t>(trace_records_.size());
    }
    static size_t litIndex(int lit) {
        return static_cast<size_t>((std::abs(lit)-1)*2 + (lit<0));
    }
    static uint64_t stateMix(uint64_t hash,uint64_t value){
        hash ^= value; return hash * 1099511628211ULL;
    }
    uint64_t stateDigestAtDecision(int variable) const {
        uint64_t hash=1469598103934665603ULL;
        hash=stateMix(hash,static_cast<uint64_t>(n_));
        hash=stateMix(hash,static_cast<uint64_t>(original_count_));
        hash=stateMix(hash,static_cast<uint64_t>(stats_.decisions));
        hash=stateMix(hash,static_cast<uint64_t>(stats_.conflicts));
        hash=stateMix(hash,static_cast<uint64_t>(stats_.learnt));
        hash=stateMix(hash,static_cast<uint64_t>(stats_.propagations));
        hash=stateMix(hash,static_cast<uint64_t>(decisionLevel()));
        hash=stateMix(hash,static_cast<uint64_t>(variable+1));
        for(int x:trail_)hash=stateMix(hash,static_cast<uint64_t>(static_cast<int64_t>(x)));
        for(int x:trail_lim_)hash=stateMix(hash,static_cast<uint64_t>(x));
        for(int8_t x:phase_)hash=stateMix(hash,static_cast<uint64_t>(static_cast<int64_t>(x)));
        for(double x:activity_)hash=stateMix(hash,std::bit_cast<uint64_t>(x));
        hash=stateMix(hash,clauses_.size());
        for(const Clause& c:clauses_) {
            hash=stateMix(hash,c.lits.size());
            hash=stateMix(hash,c.deleted?1:0);
            hash=stateMix(hash,c.learnt?1:0);
            for(int lit:c.lits)hash=stateMix(hash,static_cast<uint64_t>(static_cast<int64_t>(lit)));
        }
        return hash;
    }
    int decisionLevel() const { return static_cast<int>(trail_lim_.size()); }
    int value(int lit) const {
        const int val = values_[std::abs(lit)-1];
        return lit < 0 ? -val : val;
    }
    bool timedOut() const {
        return timeout_s_ > 0 && elapsed() >= timeout_s_;
    }
    bool x46CloneBudgetReached() const {
        if(!x46_clone_)return false;
        if(stats_.conflicts-x46_clone_origin_conflicts_ >=x46_clone_conflict_cap_)
            return true;
        if(stats_.decisions-x46_clone_origin_decisions_ >=x46_clone_decision_cap_)
            return true;
        return std::chrono::duration<double,std::milli>(
                   Clock::now()-x46_clone_started_).count()>=x46_clone_wall_limit_ms_;
    }
    BranchProbeCost shortProbeBranch(int literal) const {
        const auto begin=Clock::now();
        Solver cp(*this);
        cp.x46_clone_=true;
        cp.x46_enabled_=false;
        cp.x46_clone_origin_conflicts_=cp.stats_.conflicts;
        cp.x46_clone_origin_decisions_=cp.stats_.decisions;
        cp.x46_clone_conflict_cap_=x46_probe_conflict_cap_;
        cp.x46_clone_decision_cap_=std::max(12,4*x46_probe_conflict_cap_);
        cp.x46_clone_wall_limit_ms_=x46_probe_wall_ms_;
        cp.x46_clone_started_=Clock::now();
        ++cp.stats_.decisions;
        cp.newDecisionLevel();
        if(!cp.enqueue(literal,-1))
            throw std::runtime_error("X46 first probe decision not free");
        const Result r=cp.solve();
        const double ms=std::chrono::duration<double,std::milli>(
            Clock::now()-begin).count();
        return {static_cast<int>(r),
            cp.stats_.conflicts-x46_clone_origin_conflicts_,
            cp.stats_.decisions-x46_clone_origin_decisions_,
            cp.stats_.propagations-stats_.propagations,ms};
    }
    bool learnedAlternate(const BranchProbeCost& normal,
                          const BranchProbeCost& flipped) {
        const double nc=static_cast<double>(normal.conflicts);
        const double fc=static_cast<double>(flipped.conflicts);
        const double nd=static_cast<double>(normal.decisions);
        const double fd=static_cast<double>(flipped.decisions);
        const double np=static_cast<double>(normal.propagations);
        const double fp=static_cast<double>(flipped.propagations);
        const std::vector<double> features={
            std::log1p(nc),std::log1p(fc),std::log1p(nd),std::log1p(fd),
            std::log1p(np),std::log1p(fp),
            (nc-fc)/(nc+fc+1.0),(nd-fd)/(nd+fd+1.0),(np-fp)/(np+fp+1.0),
            normal.result==10?1.0:0.0,flipped.result==10?1.0:0.0,
            std::log1p(static_cast<double>(compare_at_))};
        double value=x46_model_bias_;
        for(size_t i=0;i<features.size();++i) {
            const double z=std::clamp((features[i]-x46_model_mean_[i])/
                                    x46_model_scale_[i],-5.0,5.0);
            value+=z*x46_model_weight_[i];
        }
        value=std::clamp(value,-40.0,40.0);
        x46_model_probability_=1.0/(1.0+std::exp(-value));
        return x46_model_probability_>x46_model_threshold_;
    }
    static bool preferAlternate(const BranchProbeCost& normal,
                                const BranchProbeCost& flip) {
        // A short, independently verified SAT witness is stronger evidence
        // than nonterminal proxy scores. UNSAT is NEVER accepted as a proof.
        if(flip.result==10 && normal.result!=10)return true;
        if(normal.result==10 && flip.result!=10)return false;
        const auto score=[](const BranchProbeCost& p){
            return 4.0*p.conflicts+0.55*p.decisions+0.003*p.propagations;
        };
        const double a=score(normal),b=score(flip);
        // Avoid tiny proxy differences and cap-only undecided signals.
        return a>=6.0 && (a-b)>std::max(1.0,0.20*a)
               && flip.conflicts <=normal.conflicts+4;
    }
    int storeClause(std::vector<int> lits, bool learnt) {
        const int cid = static_cast<int>(clauses_.size());
        if (learnt) writeProofClause(lits);
        clauses_.push_back(Clause{std::move(lits),learnt,false,0.0,0,stats_.conflicts});
        if (clauses_.back().lits.size() == 2) {
            const auto& c = clauses_.back().lits;
            binary_implications_[litIndex(-c[0])].push_back({c[1],cid});
            binary_implications_[litIndex(-c[1])].push_back({c[0],cid});
            stats_.binary_edges += 2;
        } else if (clauses_.back().lits.size() > 2) {
            const auto& c = clauses_.back().lits;
            watches_[litIndex(-c[0])].push_back({cid,c[1]});
            watches_[litIndex(-c[1])].push_back({cid,c[0]});
        }
        return cid;
    }
    void offer(int v) {
        ++generation_[v];
        if (values_[v] == 0) heap_.push({activity_[v] + base_[v],v,generation_[v]});
    }
    void bump(int v) {
        activity_[v] += var_inc_;
        if (activity_[v] > 1.e100) {
            for (double& a : activity_) a *= 1.e-100;
            var_inc_ *= 1.e-100;
            while (!heap_.empty()) heap_.pop();
            for (int x=0;x<n_;++x) offer(x);
        } else offer(v);
    }
    bool enqueue(int lit, int reason) {
        const int v = std::abs(lit)-1;
        const int desired = lit > 0 ? 1 : -1;
        if (values_[v] != 0) return values_[v] == desired;
        values_[v] = static_cast<int8_t>(desired);
        levels_[v] = decisionLevel();
        reasons_[v] = reason;
        if (x5_retain_ && reason>=0 && clauses_[reason].learnt)
            clauses_[reason].last_used=stats_.conflicts;
        if (!probing_) phase_[v] = static_cast<int8_t>(desired);
        trail_.push_back(lit);
        return true;
    }
    void newDecisionLevel() { trail_lim_.push_back(static_cast<int>(trail_.size())); }
    void cancelUntil(int target) {
        if (decisionLevel() <= target) return;
        const int first = trail_lim_[target];
        for (int i=static_cast<int>(trail_.size())-1; i>=first; --i) {
            const int v = std::abs(trail_[i])-1;
            values_[v] = 0; reasons_[v] = -1; levels_[v] = 0;
            offer(v);
        }
        trail_.resize(first);
        trail_lim_.resize(target);
        qhead_ = static_cast<int>(trail_.size());
    }
    // Watched literals: watch[-lit] holds clauses visited when lit becomes true.
    Prop propagate(int max_inspections) {
        Prop ret;
        while (qhead_ < static_cast<int>(trail_.size())) {
            const int p = trail_[qhead_++];
            if (probing_) ++stats_.horizon_inspections; else ++stats_.propagations;
            // Binary implications are an O(1) edge traversal, not general watches.
            // During an incomplete bounded probe we roll back the whole probe.
            for (const auto& [implied, reason] : binary_implications_[litIndex(p)]) {
                ++ret.inspected;
                if (max_inspections >= 0 && ret.inspected > max_inspections) {
                    ret.result = PropResult::LIMIT;
                    return ret;
                }
                ++stats_.binary_propagations;
                if (!enqueue(implied,reason)) {
                    ret.result = PropResult::CONFLICT;
                    ret.conflict = reason;
                    return ret;
                }
            }
            auto& ws = watches_[litIndex(p)];
            size_t i = 0, j = 0;
            while (i < ws.size()) {
                if ((max_inspections >= 0 && ret.inspected >= max_inspections) ||
                    ((ret.inspected & 8191) == 8191 && !probing_ && timedOut())) {
                    const bool limit = max_inspections >= 0 && ret.inspected >= max_inspections;
                    while (i < ws.size()) ws[j++] = ws[i++];
                    ws.resize(j);
                    ret.result = limit ? PropResult::LIMIT : PropResult::TIMEOUT;
                    return ret;
                }
                Watch w = ws[i++];
                ++ret.inspected;
                Clause& c = clauses_[w.clause];
                if (c.deleted) continue;
                if (value(w.blocker) == 1) {
                    // X5.8: a retained watcher already in the correct slot
                    // does not need a redundant write. If an earlier watch
                    // moved/deleted, preserve the original compaction write.
                    if (x58_blocker_compact_skip_ && j == i-1) {
                        ++stats_.x58_blocker_write_skips;
                    } else {
                        ws[j] = w;
                    }
                    ++j;
                    continue;
                }
                const int false_lit = -p;
                if (c.lits[0] == false_lit) std::swap(c.lits[0],c.lits[1]);
                if (c.lits[1] != false_lit) {
                    throw std::runtime_error("invalid watched-literal invariant");
                }
                if (value(c.lits[0]) == 1) {
                    ws[j++] = {w.clause,c.lits[0]};
                    continue;
                }
                bool found = false;
                for (size_t k=2; k<c.lits.size(); ++k) {
                    ++ret.inspected;
                    if (value(c.lits[k]) != -1) {
                        c.lits[1] = c.lits[k];
                        c.lits[k] = false_lit;
                        watches_[litIndex(-c.lits[1])].push_back({w.clause,c.lits[0]});
                        found = true;
                        break;
                    }
                }
                if (found) continue;
                ws[j++] = {w.clause,c.lits[0]};
                if (value(c.lits[0]) == -1) {
                    while (i < ws.size()) ws[j++] = ws[i++];
                    ws.resize(j);
                    ret.result = PropResult::CONFLICT;
                    ret.conflict = w.clause;
                    return ret;
                }
                if (!enqueue(c.lits[0],w.clause)) {
                    throw std::runtime_error("propagation failed without identified conflict");
                }
            }
            ws.resize(j);
        }
        return ret;
    }
    int analyze(int conflict, std::vector<int>& learned) {
        learned.clear(); learned.push_back(0);
        std::vector<int> touched;
        touched.reserve(64);
        int pending=0, p=0, index=static_cast<int>(trail_.size())-1;
        do {
            Clause& c = clauses_[conflict];
            c.activity += x5_retain_?clause_inc_:1.0;
            if (x5_retain_) {
                c.last_used=stats_.conflicts;
                if (c.learnt && c.glue>2) c.glue=std::min(c.glue,computeGlue(c.lits));
                if(c.activity>1e100) {
                    for(auto& q:clauses_)q.activity*=1e-100;
                    clause_inc_*=1e-100;
                }
            }
            for (int lit : c.lits) {
                const int v=std::abs(lit)-1;
                if (p != 0 && std::abs(p) == std::abs(lit)) continue;
                if (seen_[v] || levels_[v] == 0) continue;
                seen_[v] = 1; touched.push_back(v); bump(v);
                if (levels_[v] == decisionLevel()) ++pending;
                else learned.push_back(lit);
            }
            while (index >= 0 && !seen_[std::abs(trail_[index])-1]) --index;
            if (index < 0) throw std::runtime_error("1-UIP analysis invariant violated");
            p=trail_[index--];
            seen_[std::abs(p)-1] = 0;
            --pending;
            conflict = reasons_[std::abs(p)-1];
            if (pending > 0 && conflict == -1) {
                throw std::runtime_error("decision reason reached before UIP");
            }
        } while (pending > 0);
        learned[0] = -p;
        for (int v : touched) seen_[v] = 0;
        if (x5_minimize_ && learned.size()>1) minimizeClause(learned);
        if (learned.size() == 1) return 0;
        size_t best=1;
        for (size_t k=2;k<learned.size();++k)
            if (levels_[std::abs(learned[k])-1] > levels_[std::abs(learned[best])-1]) best=k;
        std::swap(learned[1],learned[best]);
        return levels_[std::abs(learned[1])-1];
    }
    int computeGlue(const std::vector<int>& lits) {
        if (!x59_stamp_glue_) {
            // Frozen X5 implementation, unchanged for same-binary A/B.
            std::vector<int> levels;
            levels.reserve(lits.size());
            for(int lit:lits)levels.push_back(levels_[std::abs(lit)-1]);
            std::sort(levels.begin(),levels.end());
            return static_cast<int>(std::unique(levels.begin(),levels.end())-levels.begin());
        }
        // X5.9: a per-solver level stamp counts distinct decision levels
        // without a per-conflict allocation or sorting. This yields exactly
        // the same LBD as the original implementation, including level 0.
        if (++x59_epoch_ == 0) {
            std::fill(x59_level_stamps_.begin(), x59_level_stamps_.end(), 0);
            x59_epoch_=1;
        }
        const size_t needed=static_cast<size_t>(decisionLevel())+1;
        if (x59_level_stamps_.size()<needed)
            x59_level_stamps_.resize(std::max(needed, x59_level_stamps_.size()*2+64),0);
        int glue=0;
        for(int lit:lits) {
            const auto level=static_cast<size_t>(levels_[std::abs(lit)-1]);
            if (level>=x59_level_stamps_.size())
                throw std::runtime_error("X59 LBD level exceeds current decision depth");
            if (x59_level_stamps_[level]!=x59_epoch_) {
                x59_level_stamps_[level]=x59_epoch_;
                ++glue;
            }
        }
        ++stats_.x59_stamp_glue_calls;
        stats_.x59_stamp_seen_levels+=glue;
        return glue;
    }
    // A literal is redundant only if its reason DAG ends at root facts or
    // literals already in the learned clause. Budget exhaustion keeps it.
    bool redundant(int v,int depth,int& budget) {
        if(depth>=128 || --budget<0)return false;
        ++stats_.minimize_visits;
        if(minimize_marks_[v]==2)return true;
        if(minimize_marks_[v]==1 || reasons_[v]<0)return false;
        minimize_marks_[v]=1;
        minimize_touched_.push_back(v);
        for(int lit:clauses_[reasons_[v]].lits) {
            int u=std::abs(lit)-1;
            if(u==v || levels_[u]==0 || seen_[u])continue;
            if(!redundant(u,depth+1,budget)) {minimize_marks_[v]=0;return false;}
        }
        minimize_marks_[v]=2;
        return true;
    }
    void minimizeClause(std::vector<int>& lits) {
        if(minimize_marks_.size()!=static_cast<size_t>(n_))minimize_marks_.resize(n_);
        minimize_touched_.clear();
        for(int lit:lits)seen_[std::abs(lit)-1]=1;
        int budget=4000;
        size_t out=1;
        std::vector<int> original=lits;
        for(size_t i=1;i<lits.size();++i) {
            int v=std::abs(lits[i])-1;
            seen_[v]=0;
            if(redundant(v,0,budget))++stats_.minimized_literals;
            else {seen_[v]=1;lits[out++]=lits[i];}
        }
        lits.resize(out);
        for(int lit:original)seen_[std::abs(lit)-1]=0;
        for(int v:minimize_touched_)minimize_marks_[v]=0;
    }
    void rebuildHeapIfNeeded() {
        if(heap_.size()<=static_cast<size_t>(4*n_+1024))return;
        std::vector<Entry> entries;
        entries.reserve(n_);
        for(int v=0;v<n_;++v)if(values_[v]==0)
            entries.push_back({activity_[v]+base_[v],v,generation_[v]});
        heap_=std::priority_queue<Entry>(std::less<Entry>(),std::move(entries));
        ++stats_.heap_rebuilds;
    }
    std::vector<int> topCandidates(int max_count) {
        std::vector<Entry> saved;
        std::vector<int> vars;
        while (!heap_.empty() && static_cast<int>(vars.size()) < max_count) {
            Entry e=heap_.top();heap_.pop();
            if (values_[e.variable] != 0 || generation_[e.variable] != e.generation) continue;
            saved.push_back(e);
            vars.push_back(e.variable);
        }
        for (const Entry& e : saved) heap_.push(e);
        return vars;
    }
    // PATTERN: count unresolved long clauses in a fixed, SHA-independent
    // evenly-spaced sample of the ORIGINAL input.  A negative prefilter is
    // SOUND: if even one original clause has >2 unassigned literals and is
    // unsatisfied, the residual formula is not 2-CNF.  A nonnegative
    // prefilter is only a hint and is followed by complete exact checking.
    int structuralDistance(int stop_at=std::numeric_limits<int>::max()) {
        ++stats_.pattern_samples;
        const int limit=std::min(96,original_count_);
        int long_count=0;
        for (int k=0;k<limit;++k) {
            const int cid=static_cast<int>((static_cast<int64_t>(k)*original_count_)/limit);
            const Clause& c=clauses_[cid];
            if (c.lits.size()<3) continue;
            int free=0;
            bool satisfied=false;
            for (int lit:c.lits) {
                const int x=value(lit);
                if (x==1) {satisfied=true;break;}
                if (x==0) ++free;
            }
            if (!satisfied && free>2 && ++long_count>=stop_at) break;
        }
        return long_count;
    }
    // STEP: measure the actual propagations and structural reduction after
    // the chosen speculative move.  Feedback gates FUTURE probing only;
    // heuristics cannot change satisfiability or UNSAT derivations.
    void settleFeedback(bool conflict) {
        if (!feedback_pending_) return;
        feedback_pending_=false;
        const int implied=std::max(0,static_cast<int>(trail_.size())-feedback_before_trail_-1);
        const int after=conflict?feedback_before_long_:structuralDistance();
        const int gain=std::max(0,feedback_before_long_-after);
        const bool good=conflict || gain>=1 || implied>=6;
        ++stats_.controller_feedback;
        stats_.controller_gained_long+=gain;
        stats_.controller_actual_implied+=implied;
        if (conflict) ++stats_.controller_conflict_feedback;
        if (good) {++stats_.controller_positive;++feedback_window_good_;}
        if (++feedback_window_count_>=8) {
            // Discontinue expensive speculation if it rarely helps or if its
            // total measured cost is already too high. Re-probe later.
            if (feedback_window_good_<2 ||
                (probing_seconds_>0.010 && probing_seconds_>0.08*elapsed())) {
                cooldown_until_decision_=stats_.decisions+192;
                ++stats_.controller_cooldowns;
            }
            feedback_window_count_=0;
            feedback_window_good_=0;
        }
    }
    struct Probe { bool contradiction=false; int implied=0; int inspected=0;
                   int remaining_long=0; };
    Probe probe(int lit) {
        const int original_level=decisionLevel();
        const int original_trail=static_cast<int>(trail_.size());
        probing_=true;
        newDecisionLevel();
        if (!enqueue(lit,-1)) throw std::runtime_error("probe requires free variable");
        const Prop p=propagate(900);
        Probe r;
        r.contradiction=p.result==PropResult::CONFLICT;
        r.implied=static_cast<int>(trail_.size())-original_trail-1;
        r.inspected=p.inspected;
        r.remaining_long=structuralDistance();
        ++stats_.depth_probes;
        if (r.contradiction) ++stats_.depth_conflicts;
        cancelUntil(original_level);
        probing_=false;
        return r;
    }
    int selectVariable() {
        rebuildHeapIfNeeded();
        // Fast path preserves frozen score and variable-ID tie breaking.
        if (!use_depth_) {
            while(!heap_.empty()) {
                const Entry& e=heap_.top();
                if(values_[e.variable]==0 && generation_[e.variable]==e.generation)return e.variable;
                heap_.pop();
            }
            return -1;
        }
        if (heap_.empty()) return -1;
        if (!use_depth_ || (stats_.decisions%32)!=0 ||
            stats_.decisions<cooldown_until_decision_ ||
            (stats_.decisions>=256 && stats_.conflicts*3>stats_.decisions*2) ||
            (timeout_s_>0 && elapsed()>timeout_s_*0.88) ||
            (probing_seconds_>std::max(0.007,0.07*elapsed()))) {
            const auto v=topCandidates(1);
            return v.empty()?-1:v[0];
        }
        const auto candidates=topCandidates(3);
        if (candidates.empty()) return -1;
        const auto tick=Clock::now();
        const int distance_before=structuralDistance();
        int best=candidates[0], best_sign=phase_[best];
        double best_score=-1e100;
        for (int v:candidates) {
            Probe yes=probe(v+1);
            Probe no=probe(-v-1);
            int sign=phase_[v];
            double score=0;
            if (yes.contradiction!=no.contradiction) {
                // Failed literal: branching into the contradictory polarity
                // is wrong. Prefer the OTHER polarity; this fixes X1.
                sign=yes.contradiction?-1:1;
                score=10000;
            } else if (yes.contradiction && no.contradiction) {
                // Both phases fail under the trail. Let ordinary CDCL
                // derive the conflict safely; never assert SAT/UNSAT here.
                score=500;
            } else {
                double gain_yes=distance_before-yes.remaining_long;
                double gain_no=distance_before-no.remaining_long;
                double s_yes=2.0*gain_yes+0.12*yes.implied/(1.+yes.inspected/400.);
                double s_no=2.0*gain_no+0.12*no.implied/(1.+no.inspected/400.);
                if (s_yes>s_no) sign=1;
                else if (s_no>s_yes) sign=-1;
                score=std::max(s_yes,s_no);
                if (score>0) ++stats_.depth_positive_gain;
            }
            score+=0.000001*activity_[v];
            if (score>best_score) {best_score=score;best=v;best_sign=sign;}
        }
        probing_seconds_+=std::chrono::duration<double>(Clock::now()-tick).count();
        ++stats_.controller_probed_decisions;
        // After THIS branch is actually propagated, compare the resulting
        // residual against this pre-branch snapshot (not the best probe's
        // predicted gain). This is a genuine outcome-feedback signal.
        feedback_pending_=true;
        feedback_before_long_=distance_before;
        feedback_before_trail_=static_cast<int>(trail_.size());
        phase_[best]=static_cast<int8_t>(best_sign);
        return best;
    }
    void collectGarbage() {
        size_t dead=0;
        for(const auto& c:clauses_)dead+=c.deleted;
        if(!x5_gc_ || dead<512 || dead*4<clauses_.size())return;
        std::vector<int> remap(clauses_.size(),-1);
        size_t out=0;
        for(size_t i=0;i<clauses_.size();++i)if(!clauses_[i].deleted) {
            remap[i]=static_cast<int>(out);
            if(out!=i)clauses_[out]=std::move(clauses_[i]);
            ++out;
        }
        clauses_.resize(out);
        for(int& r:reasons_)if(r>=0) {
            r=remap[r];
            if(r<0)throw std::runtime_error("collected a locked reason");
        }
        for(int& u:units_)u=remap[u];
        for(auto& ws:watches_) {
            size_t j=0;
            for(auto w:ws)if(remap[w.clause]>=0) {w.clause=remap[w.clause];ws[j++]=w;}
            ws.resize(j);
        }
        for(auto& edges:binary_implications_)for(auto& e:edges)e.second=remap[e.second];
        ++stats_.collections;stats_.compacted_clauses+=dead;
    }
    void reduceLearnts() {
        std::vector<int> candidates;
        std::vector<uint8_t> locked(clauses_.size(),0);
        for(int v=0;v<n_;++v)if(values_[v]!=0 && reasons_[v]>=0)locked[reasons_[v]]=1;
        for(int cid=0;cid<static_cast<int>(clauses_.size());++cid) {
            const Clause& c=clauses_[cid];
            if(!c.learnt || c.deleted || c.lits.size()<=2 || locked[cid])continue;
            if(x5_retain_ && (c.glue<=2 || stats_.conflicts-c.last_used<1000 ||
                (c.glue<=6 && stats_.conflicts-c.last_used<30000))) {
                ++stats_.protected_clauses;continue;
            }
            candidates.push_back(cid);
        }
        if(candidates.size()>=128) {
            std::sort(candidates.begin(),candidates.end(),[&](int a,int b) {
                if(x5_retain_ && clauses_[a].glue!=clauses_[b].glue)
                    return clauses_[a].glue>clauses_[b].glue;
                if(clauses_[a].activity!=clauses_[b].activity)
                    return clauses_[a].activity<clauses_[b].activity;
                if(clauses_[a].lits.size()!=clauses_[b].lits.size())
                    return clauses_[a].lits.size()>clauses_[b].lits.size();
                return a<b;
            });
            for(size_t k=0;k<candidates.size()/(x5_retain_?3:2);++k) {
                clauses_[candidates[k]].deleted=true;
                ++stats_.reduce_removed;
            }
        }
        collectGarbage();
    }
};

int run(int argc, char** argv) {
    const auto process_start=Clock::now();
    std::string input, mode="trace", trace_file;
    double seconds=5.0;
    bool show_stats=false, trace_trail=false, compare_flip=false,x46_shadow=false;
    bool x58_hotwatch=false;
    bool x59_stamp_glue=false;
    int compare_at=0,x46_conflicts=0;
    double x46_probe_ms=1.5;
    std::string x46_model_path,x47_guard_path,proof_path;
    bool x5_minimize=true,x5_retain=false,x5_gc=true,x5_restarts=false;
    for (int i=1;i<argc;++i) {
        std::string opt=argv[i];
        if (opt=="--mode" && i+1<argc) mode=argv[++i];
        else if (opt=="--time" && i+1<argc) seconds=std::stod(argv[++i]);
        else if (opt=="--transitions" && i+1<argc) trace_file=argv[++i];
        else if (opt=="--proof" && i+1<argc) proof_path=argv[++i];
        else if (opt=="--x5-no-minimize") x5_minimize=false;
        else if (opt=="--x5-no-retain") x5_retain=false;
        else if (opt=="--x5-retain") x5_retain=true;
        else if (opt=="--x5-no-gc") x5_gc=false;
        else if (opt=="--x5-restarts") x5_restarts=true;
        else if (opt=="--x58-hotwatch") x58_hotwatch=true;
        else if (opt=="--x59-stamp-glue") x59_stamp_glue=true;
        else if (opt=="--stats") show_stats=true;
        else if (opt=="--trace-trail") trace_trail=true;
        else if (opt=="--branch-at" && i+1<argc) compare_at=std::stoi(argv[++i]);
        else if (opt=="--flip-branch") compare_flip=true;
        else if (opt=="--x46-conflicts" && i+1<argc) x46_conflicts=std::stoi(argv[++i]);
        else if (opt=="--x46-probe-ms" && i+1<argc) x46_probe_ms=std::stod(argv[++i]);
        else if (opt=="--x46-shadow") x46_shadow=true;
        else if (opt=="--x46-model" && i+1<argc) x46_model_path=argv[++i];
        else if (opt=="--x47-guard" && i+1<argc) x47_guard_path=argv[++i];
        else if (opt=="--help") {
            std::cout<<"Usage: drnas-x41 <file.cnf> [--mode core|trace] [--time seconds] [--stats] [--transitions path] [--trace-trail (n<=18)] [--branch-at 1..100000] [--flip-branch] [--x46-conflicts 8|32|128] [--x46-probe-ms N] [--x46-shadow] [--x46-model FILE] [--x47-guard FILE] [--proof FILE] [--x5-no-minimize] [--x5-retain] [--x5-no-gc] [--x5-restarts]\n";
            return 0;
        } else if (opt.rfind("-",0)==0) throw std::runtime_error("unknown argument: "+opt);
        else if (input.empty()) input=opt;
        else throw std::runtime_error("multiple input files");
    }
    if (input.empty() || (mode!="core" && mode!="trace") || !std::isfinite(seconds) || seconds<0)
        throw std::runtime_error("invalid input/mode/time");
    if (!trace_file.empty() && mode!="trace") throw std::runtime_error("--transitions requires --mode trace");
    if (compare_flip && compare_at==0)throw std::runtime_error("--flip-branch requires --branch-at");
    if(x46_conflicts>0 && (compare_at<=0 || compare_flip))
        throw std::runtime_error("X46 short probes require --branch-at and no --flip-branch");
    if(!x46_model_path.empty() && x46_conflicts==0)throw std::runtime_error("--x46-model requires --x46-conflicts");
    if(!x47_guard_path.empty() && (x46_model_path.empty()||x46_conflicts==0||x46_shadow))
        throw std::runtime_error("--x47-guard requires active X46 model and short probes");
    if(x46_shadow && x46_conflicts==0)
        throw std::runtime_error("--x46-shadow requires --x46-conflicts");
    if (compare_at<0 || compare_at>100000)throw std::runtime_error("invalid --branch-at");
    if (trace_trail && (mode!="trace" || trace_file.empty()))
        throw std::runtime_error("--trace-trail requires trace mode and --transitions");
    std::ofstream proof;
    if(!proof_path.empty()) {
        if(proof_path==input)throw std::runtime_error("proof would overwrite input");
        proof.open(proof_path);
        if(!proof)throw std::runtime_error("cannot create proof");
    }
    std::ifstream fd(input);
    if (!fd) throw std::runtime_error("cannot open CNF: "+input);
    int declared_vars=-1, declared_clauses=-1;
    std::optional<Solver> solver;
    int seen_clauses=0;
    std::vector<int> clause;
    // Buffered getline + from_chars: avoids per-literal stream parsing and
    // allocation, while still supporting DIMACS clauses spanning many lines.
    std::string line;
    while (std::getline(fd,line)) {
        const char* at=line.data();
        const char* end=line.data()+line.size();
        auto skip=[&](){while (at<end && (*at==' ' || *at=='\t' || *at=='\r')) ++at;};
        skip();
        if (at==end || *at=='c' || *at=='%') continue;
        if (*at=='p' && (at+1==end || at[1]==' ' || at[1]=='\t')) {
            std::istringstream header(line);
            std::string word,fmt,extra;
            if (solver || !(header>>word>>fmt>>declared_vars>>declared_clauses) ||
                word!="p" || fmt!="cnf" || declared_vars<0 || declared_vars>20000000 ||
                declared_clauses<0 || (header>>extra))
                throw std::runtime_error("invalid DIMACS header");
            if (trace_trail && declared_vars>18) throw std::runtime_error("--trace-trail only supported for at most 18 variables");
            solver.emplace(declared_vars,mode,seconds,process_start,trace_trail,compare_at,compare_flip);
            solver->configureX5(x5_minimize,x5_retain,x5_gc,x5_restarts,
                                proof_path.empty()?nullptr:&proof);
            solver->configureX58(x58_hotwatch);
            solver->configureX59(x59_stamp_glue);
            if(x46_conflicts>0)solver->configureX46(x46_conflicts,x46_shadow,x46_probe_ms);
            if(!x47_guard_path.empty())solver->loadX47Guard(x47_guard_path);
            continue;
        }
        if (!solver) throw std::runtime_error("missing DIMACS header");
        while (at<end) {
            skip();
            if (at==end || *at=='c' || *at=='%') break;
            if (*at=='+') ++at;
            int val=0;
            const auto parsed=std::from_chars(at,end,val);
            if (parsed.ec!=std::errc{} || parsed.ptr==at ||
                (parsed.ptr!=end && *parsed.ptr!=' ' && *parsed.ptr!='\t' && *parsed.ptr!='\r') ||
                val < -declared_vars || val > declared_vars)
                throw std::runtime_error("invalid or out-of-range DIMACS literal");
            at=parsed.ptr;
            if (val==0) {
                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;
                if (seen_clauses>declared_clauses)
                    throw std::runtime_error("extra DIMACS clause");
            } else clause.push_back(val);
        }
    }
    if (!solver || !clause.empty() || seen_clauses!=declared_clauses)
        throw std::runtime_error("incomplete or mismatched DIMACS clause count");
    solver->finishParsing();
    // Fast fallback: if the frozen risk gate rejects this source before
    // any probe, do not even open or deserialize the learned cost model.
    // The original C++ CDCL search is left intact. The guard itself still
    // loads and validates so corrupted files fail closed.
    if(!x46_model_path.empty() && solver->x47PreProbeEligible())
        solver->loadX46CostModel(x46_model_path);
    const Result r=solver->solve();
    if(r==Result::UNSAT)solver->writeProofClause({});
    if(proof.is_open()) {
        proof.flush();
        if(!proof)throw std::runtime_error("proof flush failed");
    }
    const double solve_finish_elapsed=solver->elapsed();
    if (r==Result::SAT) {
        std::cout<<"s SATISFIABLE\n";
        for (int v=0;v<solver->nvars();++v) {
            if (v%20==0) std::cout<<"v ";
            std::cout<<solver->assignment(v)*(v+1)<<" ";
            if (v%20==19) std::cout<<"0\n";
        }
        if (solver->nvars()%20) std::cout<<"0\n";
        if (!solver->nvars()) std::cout<<"v 0\n";
    } else if (r==Result::UNSAT) std::cout<<"s UNSATISFIABLE\n";
    else std::cout<<"s UNKNOWN\n";
    solver->writeTransitions(trace_file,r,solve_finish_elapsed);
    if(x46_conflicts>0){
        const auto& a=solver->x46Base();
        const auto& b=solver->x46Alt();
        std::cerr<<"X46_PROBE {\"conflict_cap\":"<<x46_conflicts
                 <<",\"per_probe_ms_limit\":"<<x46_probe_ms
                 <<",\"triggered\":"<<(solver->x46Triggered()?"true":"false")
                 <<",\"skipped\":"<<(solver->x46Skipped()?"true":"false")
                 <<",\"shadow\":"<<(solver->x46Shadow()?"true":"false")
                 <<",\"recommend_flip\":"<<(solver->x46ChosenFlip()?"true":"false")
                 <<",\"learned_model\":"<<(solver->x46ModelLoaded()?"true":"false")
                 <<",\"x47_enabled\":"<<(solver->x47Enabled()?"true":"false")
                 <<",\"x47_preprobe_skipped\":"<<(solver->x47SkippedByGate()?"true":"false")
                 <<",\"x47_rejected_after_probe\":"<<(solver->x47RejectedAfterProbe()?"true":"false")
                 <<",\"x47_expected_net_conflicts\":"<<solver->x47PredictedNetConflicts()
                 <<",\"predicted_flip_probability\":"<<solver->x46ModelProbability()
                 <<",\"probe_pair_wall_ms\":"<<std::fixed<<std::setprecision(7)<<solver->x46ProbesWallMs()
                 <<",\"pre_state_digest\":\""<<std::hex<<solver->x46ProbesHash()<<std::dec
                 <<"\",\"original\":{\"status\":"<<a.result
                 <<",\"conflicts\":"<<a.conflicts<<",\"decisions\":"<<a.decisions
                 <<",\"propagations\":"<<a.propagations<<",\"wall_ms\":"<<a.wall_ms
                 <<"},\"opposite\":{\"status\":"<<b.result
                 <<",\"conflicts\":"<<b.conflicts<<",\"decisions\":"<<b.decisions
                 <<",\"propagations\":"<<b.propagations<<",\"wall_ms\":"<<b.wall_ms<<"}}\n";
    }
    if(compare_at>0) {
        std::cerr<<"X45_COMPARE {\"decision_index\":"<<solver->compareAt()
                 <<",\"reached\":"<<(solver->compareReached()?"true":"false")
                 <<",\"flip\":"<<(solver->compareFlipped()?"true":"false")
                 <<",\"pre_state_digest\":\""<<std::hex<<solver->comparePreHash()<<std::dec
                 <<"\",\"baseline_literal\":"<<solver->compareBaselineLiteral()
                 <<",\"actual_literal\":"<<solver->compareActualLiteral()
                 <<",\"prefix_conflicts\":"<<solver->comparePrefixConflicts()
                 <<",\"prefix_learnt\":"<<solver->comparePrefixLearnt()
                 <<",\"prefix_propagations\":"<<solver->comparePrefixPropagations()
                 <<",\"prefix_elapsed_s\":"<<std::fixed<<std::setprecision(7)<<solver->comparePrefixElapsed()
                 <<"}\n";
    }
    if (show_stats) {
        const Stats& s=solver->stats();
        std::cerr<<"X58_STATS {\"hotwatch\":"<<(x58_hotwatch?"true":"false")
                 <<",\"redundant_writes_skipped\":"<<s.x58_blocker_write_skips<<"}\n";
        std::cerr<<"X59_STATS {\"stamp_glue\":"<<(x59_stamp_glue?"true":"false")
                 <<",\"calls\":"<<s.x59_stamp_glue_calls
                 <<",\"sum_distinct_levels\":"<<s.x59_stamp_seen_levels<<"}\n";
        std::cerr<<"X5_STATS {\"minimized_literals\":"<<s.minimized_literals
            <<",\"minimize_visits\":"<<s.minimize_visits
            <<",\"compacted_clauses\":"<<s.compacted_clauses
            <<",\"collections\":"<<s.collections
            <<",\"heap_rebuilds\":"<<s.heap_rebuilds
            <<",\"protected_clauses\":"<<s.protected_clauses<<"}\n";
        std::cerr<<"X41_STATS {\"mode\":\""<<solver->mode()<<"\",\"status\":\""
                 <<(r==Result::SAT?"SAT":r==Result::UNSAT?"UNSAT":"UNKNOWN")
                 <<"\",\"vars\":"<<solver->nvars()<<",\"clauses\":"<<solver->nclauses()
                 <<",\"elapsed_s\":"<<std::fixed<<std::setprecision(6)<<solver->elapsed()
                 <<",\"decisions\":"<<s.decisions<<",\"conflicts\":"<<s.conflicts
                 <<",\"propagations\":"<<s.propagations<<",\"learnt\":"<<s.learnt
                 <<",\"restarts\":"<<s.restarts<<",\"horizon_probes\":"<<s.horizon_probes
                 <<",\"horizon_conflicts\":"<<s.horizon_conflicts
                 <<",\"horizon_inspections\":"<<s.horizon_inspections
                 <<",\"reduce_removed\":"<<s.reduce_removed
                 <<",\"binary_edges\":"<<s.binary_edges
                 <<",\"binary_propagations\":"<<s.binary_propagations
                 <<",\"backdoor_checks\":"<<s.backdoor_checks
                 <<",\"backdoor_leaves\":"<<s.backdoor_leaves
                 <<",\"backdoor_sat\":"<<s.backdoor_sat
                 <<",\"backdoor_unsat\":"<<s.backdoor_unsat
                 <<",\"backdoor_nogoods\":"<<s.backdoor_nogoods
                 <<",\"depth_probes\":"<<s.depth_probes
                 <<",\"depth_conflicts\":"<<s.depth_conflicts
                 <<",\"depth_positive_gain\":"<<s.depth_positive_gain
                 <<",\"pattern_samples\":"<<s.pattern_samples
                 <<",\"prefilter_attempts\":"<<s.prefilter_attempts
                 <<",\"prefilter_rejects\":"<<s.prefilter_rejects
                 <<",\"controller_probed_decisions\":"<<s.controller_probed_decisions
                 <<",\"controller_feedback\":"<<s.controller_feedback
                 <<",\"controller_positive\":"<<s.controller_positive
                 <<",\"controller_conflict_feedback\":"<<s.controller_conflict_feedback
                 <<",\"controller_cooldowns\":"<<s.controller_cooldowns
                 <<",\"controller_gained_long\":"<<s.controller_gained_long
                 <<",\"controller_actual_implied\":"<<s.controller_actual_implied
                 <<",\"probe_seconds\":"<<solver->probeSeconds()
                 <<",\"trace_samples_total\":"<<s.trace_samples_total
                 <<",\"trace_samples_retained\":"<<s.trace_samples_retained
                 <<",\"trace_conflicts\":"<<s.trace_conflicts
                 <<",\"trace_implied\":"<<s.trace_implied
                 <<",\"trace_evicted\":"<<s.trace_evicted<<"}\n";
    }
    return static_cast<int>(r);
}
} // namespace

int main(int argc,char** argv) {
    try {return run(argc,argv);}
    catch(const std::exception& e) {std::cerr<<"X41_ERROR "<<e.what()<<"\n";return 1;}
}

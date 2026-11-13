// DRNAS X4.5 -- read-only structural features at same-state polarity interventions.
// Pilot phase: trace is observational ONLY; policy identical to X3 core.
// Original implementation. No external SAT solver is linked or invoked.
#include <algorithm>
#include <chrono>
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
};
struct Watch { int clause; int blocker; };
struct Prop { PropResult result = PropResult::OK; int conflict = -1; int inspected = 0; };
struct Stats {
    int64_t conflicts = 0, decisions = 0, propagations = 0;
    int64_t restarts = 0, learnt = 0, horizon_probes = 0;
    int64_t horizon_conflicts = 0, horizon_inspections = 0;
    int64_t reduce_removed = 0;
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
    explicit Solver(int n, std::string mode, double seconds, Clock::time_point started, int checkpoint, int intervention)
        : n_(n), mode_(std::move(mode)),
          use_backdoor_(false),
          use_depth_(false),
          trace_enabled_(mode_ == "trace"),
          watches_(2 * static_cast<size_t>(n)),
          binary_implications_(2 * static_cast<size_t>(n)),
          occurrence_(2 * static_cast<size_t>(n)),
          values_(n, 0), phase_(n, 1), levels_(n, 0), reasons_(n, -1),
          seen_(n, 0), activity_(n, 0), base_(n, 0), positive_(n, 0),
          negative_(n, 0), binary_(n, 0), generation_(n, 0), checkpoint_(checkpoint), intervention_(intervention), timeout_s_(seconds), begun_(started) {
        if (n < 0 || n > 20000000) throw std::runtime_error("unsupported DIMACS variable count");
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
        Prop p = propagate(-1);
        if (p.result == PropResult::CONFLICT) return Result::UNSAT;
        if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
        int64_t restart_interval = 96;
        int64_t next_restart = restart_interval;
        int64_t next_reduce = 2200;
        while (true) {
            if (timedOut()) return Result::UNKNOWN;
            p = propagate(-1);
            if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
            if (p.result == PropResult::CONFLICT) {
                endTransition(true);
                settleFeedback(true);
                ++stats_.conflicts;
                if (decisionLevel() == 0) return Result::UNSAT;
                std::vector<int> learned;
                int level = analyze(p.conflict, learned);
                cancelUntil(level);
                const int cid = storeClause(std::move(learned), true);
                ++stats_.learnt;
                if (!enqueue(clauses_[cid].lits[0], cid)) {
                    throw std::runtime_error("internal asserting-clause invariant violated");
                }
                var_inc_ /= 0.95;
                if (stats_.conflicts >= next_restart) {
                    cancelUntil(0);
                    ++stats_.restarts;
                    restart_interval = std::min<int64_t>(2000, static_cast<int64_t>(static_cast<double>(restart_interval) * 1.45) + 1);
                    next_restart = stats_.conflicts + restart_interval;
                }
                if (stats_.conflicts >= next_reduce) {
                    reduceLearnts();
                    next_reduce = stats_.conflicts + 1400;
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
            if (checkpoint_>=0 && stats_.decisions==checkpoint_) recordCheckpoint(v);
            int sign = (checkpoint_hit_ && stats_.decisions==checkpoint_ && intervention_!=0)
                ? intervention_ : phase_[v];
            ++stats_.decisions;
            beginTransition(sign*(v+1));
            newDecisionLevel();
            if (!enqueue(sign * (v+1), -1)) {
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
    // The CHECKPOINT is a deterministic replay of the entire search prefix.
    // Two independent processes have the SAME state (fingerprint, candidate,
    // decisions, conflict history) before one intervention changes only sign.
    void writeCheckpoint(std::ostream& os) const {
        if (!checkpoint_hit_) return;
        os << std::fixed << std::setprecision(8);
        os << "X45_CHECKPOINT {\"decision_index\":" << checkpoint_
           << ",\"selected_var\":" << checkpoint_var_
           << ",\"default_sign\":" << checkpoint_default_sign_
           << ",\"assigned_fraction\":" << checkpoint_assigned_fraction_
           << ",\"depth_fraction\":" << checkpoint_depth_fraction_
           << ",\"conflict_ratio\":" << checkpoint_conflict_ratio_
           << ",\"learned_ratio\":" << checkpoint_learned_ratio_
           << ",\"open_long_fraction\":" << checkpoint_open_long_fraction_
           << ",\"positive_fraction\":" << checkpoint_positive_fraction_
           << ",\"binary_fraction\":" << checkpoint_binary_fraction_
           << ",\"phase_is_positive\":" << (checkpoint_default_sign_>0?1:0)
           << ",\"prestate_fingerprint\":\"" << std::hex << std::setw(16)
           << std::setfill('0') << checkpoint_hash_ << std::dec << std::setfill(' ')
           << "\",\"prefix_elapsed_s\":" << checkpoint_elapsed_
           << ",\"local_pos_occ\":"<<checkpoint_local_.pos_occ
           << ",\"local_neg_occ\":"<<checkpoint_local_.neg_occ
           << ",\"local_pos_bin\":"<<checkpoint_local_.pos_bin
           << ",\"local_neg_bin\":"<<checkpoint_local_.neg_bin
           << ",\"local_pos_tri\":"<<checkpoint_local_.pos_tri
           << ",\"local_neg_tri\":"<<checkpoint_local_.neg_tri
           << ",\"local_pos_long\":"<<checkpoint_local_.pos_long
           << ",\"local_neg_long\":"<<checkpoint_local_.neg_long
           << ",\"local_pos_imp_edges\":"<<checkpoint_local_.pos_imp_edges
           << ",\"local_neg_imp_edges\":"<<checkpoint_local_.neg_imp_edges
           << ",\"probe_pos_implied\":"<<checkpoint_local_.plus.implied
           << ",\"probe_neg_implied\":"<<checkpoint_local_.minus.implied
           << ",\"probe_pos_conflict\":"<<checkpoint_local_.plus.conflict
           << ",\"probe_neg_conflict\":"<<checkpoint_local_.minus.conflict
           << ",\"probe_pos_inspected\":"<<checkpoint_local_.plus.inspected
           << ",\"probe_neg_inspected\":"<<checkpoint_local_.minus.inspected
           << ",\"probe_pos_cutoff\":"<<checkpoint_local_.plus.cutoff
           << ",\"probe_neg_cutoff\":"<<checkpoint_local_.minus.cutoff
           << ",\"feature_elapsed_s\":"<<checkpoint_feature_seconds_
           << ",\"feature_read_only\":true"
           << ",\"intervention_sign\":" << intervention_ << "}\n";
    }
    bool checkpointHit() const {return checkpoint_hit_;}
    double checkpointElapsed() const {return checkpoint_elapsed_;}

    int nvars() const { return n_; }
    int nclauses() const { return original_count_; }
    int assignment(int v) const { return !leaf_model_.empty() ? leaf_model_[v] : (values_[v] == 0 ? phase_[v] : values_[v]); }
    const Stats& stats() const { return stats_; }
    double probeSeconds() const { return probing_seconds_; }
    double elapsed() const { return std::chrono::duration<double>(Clock::now() - begun_).count(); }
    const char* mode() const { return mode_.c_str(); }

  private:
    const int n_;
    const std::string mode_;
    const bool use_backdoor_;
    const bool use_depth_;
    const bool trace_enabled_;
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
    };
    static constexpr size_t MAX_TRACE_ROWS=512;
    std::vector<TraceRecord> trace_records_;
    size_t trace_records_start_=0;
    bool trace_pending_=false;
    TraceRecord trace_pending_row_;
    std::vector<Clause> clauses_;
    std::vector<std::vector<Watch>> watches_;
    std::vector<std::vector<std::pair<int,int>>> binary_implications_;
    std::vector<std::vector<int>> occurrence_;
    std::vector<int8_t> values_, phase_;
    std::vector<int> levels_, reasons_, trail_, trail_lim_, units_;
    std::vector<uint8_t> seen_;
    std::vector<double> activity_, base_;
    std::vector<int> positive_, negative_, binary_;
    std::vector<uint64_t> generation_;
    std::priority_queue<Entry> heap_;
    int qhead_ = 0, original_count_ = 0;
    const int checkpoint_ = -1;
    const int intervention_ = 0;
    bool checkpoint_hit_ = false;
    int checkpoint_var_ = -1, checkpoint_default_sign_ = 0;
    uint64_t checkpoint_hash_ = 0;
    double checkpoint_elapsed_ = 0.0;
    double checkpoint_assigned_fraction_ = 0.0, checkpoint_depth_fraction_ = 0.0;
    double checkpoint_conflict_ratio_ = 0.0, checkpoint_learned_ratio_ = 0.0;
    double checkpoint_open_long_fraction_ = 0.0, checkpoint_positive_fraction_ = 0.0;
    double checkpoint_binary_fraction_ = 0.0;
    // Only observations available BEFORE the chosen decision: no outcome or SHA.
    // Read-only: these measurements must not perturb CDCL trail, phase, heap,
    // learned clauses, activity, watchers or future search path.
    struct Look {
        int implied=0, conflict=0, inspected=0, cutoff=0;
    };
    struct Local {
        int pos_occ=0, neg_occ=0;
        int pos_bin=0, neg_bin=0;
        int pos_tri=0, neg_tri=0;
        int pos_long=0, neg_long=0;
        int pos_imp_edges=0, neg_imp_edges=0;
        Look plus, minus;
    } checkpoint_local_;
    double checkpoint_feature_seconds_=0.0;
    // Limited read-only BCP: an exact implication from the inspected clauses,
    // but a cut-off is NOT an assertion that propagation is complete.
    Look lookReadOnly(int lit) const {
        constexpr int MAX_INSPECT=384, MAX_IMPLIED=96;
        Look r;
        std::vector<int8_t> hypothetical=values_; // fully isolated local state
        std::vector<int> q;
        const int v=std::abs(lit)-1;
        if(hypothetical[v]!=0) throw std::runtime_error("lookahead candidate already assigned");
        hypothetical[v]=lit>0?1:-1;
        q.push_back(lit);
        for(size_t head=0; head<q.size() && !r.conflict; ++head) {
            int becoming_false=-q[head];
            for(int cid : occurrence_[litIndex(becoming_false)]) {
                if(r.inspected>=MAX_INSPECT) {r.cutoff=1;return r;}
                ++r.inspected;
                const Clause& c=clauses_[static_cast<size_t>(cid)];
                if(c.deleted) continue;
                int free_lit=0, free_count=0;
                bool satisfied=false;
                for(int x : c.lits) {
                    const int a=hypothetical[static_cast<size_t>(std::abs(x)-1)];
                    if(a==(x>0?1:-1)) {satisfied=true;break;}
                    if(a==0) {++free_count;free_lit=x;}
                }
                if(satisfied) continue;
                if(free_count==0) {r.conflict=1;return r;}
                if(free_count==1) {
                    const int u=std::abs(free_lit)-1;
                    if(hypothetical[static_cast<size_t>(u)]!=0) {
                        if(hypothetical[static_cast<size_t>(u)]!=(free_lit>0?1:-1)) {
                            r.conflict=1;return r;
                        }
                    } else {
                        hypothetical[static_cast<size_t>(u)]=free_lit>0?1:-1;
                        ++r.implied;
                        q.push_back(free_lit);
                        if(r.implied>=MAX_IMPLIED) {r.cutoff=1;return r;}
                    }
                }
            }
        }
        return r;
    }
    Local localBefore(int v) const {
        Local r;
        const auto scan=[&](int literal, int& occ, int& bin, int& tri, int& lng) {
            for(int cid : occurrence_[litIndex(literal)]) {
                const Clause& c=clauses_[static_cast<size_t>(cid)];
                if(c.deleted) continue;
                bool satisfied=false; int open=0;
                for(int l : c.lits) {
                    int val=value(l);
                    if(val==1) {satisfied=true;break;}
                    if(val==0) ++open;
                }
                if(satisfied || open==0)continue;
                ++occ;
                if(open<=2)++bin;else if(open==3)++tri;else ++lng;
            }
        };
        scan(v+1,r.pos_occ,r.pos_bin,r.pos_tri,r.pos_long);
        scan(-v-1,r.neg_occ,r.neg_bin,r.neg_tri,r.neg_long);
        auto countEdges=[&](int lit) {
            int count=0;
            for(const auto& e:binary_implications_[litIndex(lit)])
                if(!clauses_[static_cast<size_t>(e.second)].deleted && value(e.first)==0) ++count;
            return count;
        };
        r.pos_imp_edges=countEdges(v+1);
        r.neg_imp_edges=countEdges(-v-1);
        r.plus=lookReadOnly(v+1);
        r.minus=lookReadOnly(-v-1);
        return r;
    }

    uint64_t stateFingerprint(int candidate) const {
        uint64_t h=14695981039346656037ULL;
        auto mix=[&](uint64_t x) {h^=x;h*=1099511628211ULL;};
        mix(static_cast<uint64_t>(n_));mix(static_cast<uint64_t>(original_count_));
        mix(static_cast<uint64_t>(candidate));
        mix(static_cast<uint64_t>(stats_.conflicts));
        mix(static_cast<uint64_t>(stats_.decisions));
        mix(static_cast<uint64_t>(stats_.learnt));
        mix(static_cast<uint64_t>(stats_.restarts));
        mix(static_cast<uint64_t>(qhead_));
        for (int x:trail_)mix(static_cast<uint64_t>(static_cast<int64_t>(x)));
        for (int x:trail_lim_)mix(static_cast<uint64_t>(static_cast<int64_t>(x)));
        for (size_t i=0;i<values_.size();++i) {
            mix(static_cast<uint64_t>(static_cast<int64_t>(values_[i])));
            mix(static_cast<uint64_t>(static_cast<int64_t>(phase_[i])));
            mix(static_cast<uint64_t>(static_cast<int64_t>(levels_[i])));
            mix(static_cast<uint64_t>(static_cast<int64_t>(reasons_[i])));
            mix(generation_[i]);
        }
        for (const Clause& c:clauses_) {
            mix(static_cast<uint64_t>(c.learnt));
            mix(static_cast<uint64_t>(c.deleted));
            mix(static_cast<uint64_t>(c.lits.size()));
            for (int lit:c.lits)mix(static_cast<uint64_t>(static_cast<int64_t>(lit)));
        }
        return h;
    }
    void recordCheckpoint(int v) {
        checkpoint_hit_=true;
        checkpoint_var_=v+1;
        checkpoint_default_sign_=phase_[v];
        checkpoint_hash_=stateFingerprint(v);
        checkpoint_elapsed_=elapsed();
        const double N=std::max(1,n_);
        checkpoint_assigned_fraction_=static_cast<double>(trail_.size())/N;
        checkpoint_depth_fraction_=static_cast<double>(decisionLevel())/N;
        checkpoint_conflict_ratio_=static_cast<double>(stats_.conflicts)/std::max<int64_t>(1,stats_.decisions);
        checkpoint_learned_ratio_=static_cast<double>(stats_.learnt)/std::max(1,original_count_);
        const ClauseSample sm=sampleStructure();
        checkpoint_open_long_fraction_=static_cast<double>(sm.open_long)/std::max(1,sm.total);
        const int pos=positive_[v],neg=negative_[v];
        checkpoint_positive_fraction_=static_cast<double>(pos)/std::max(1,pos+neg);
        checkpoint_binary_fraction_=static_cast<double>(binary_[v])/std::max(1,pos+neg);
        // Measure once at the exact checkpoint before applying either sign.
        // Timer starts AFTER prestate fingerprint, and full cost is included
        // in solver wall time / post-checkpoint continuation time.
        const auto tick=Clock::now();
        checkpoint_local_=localBefore(v);
        checkpoint_feature_seconds_=std::chrono::duration<double>(Clock::now()-tick).count();
    }
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
        if (d>16 && (d&(d-1))!=0 && d%4096!=0) return;
        trace_pending_=true;
        trace_pending_row_=TraceRecord{};
        trace_pending_row_.decision_literal=literal;
        trace_pending_row_.before=snapshot();
        ++stats_.trace_samples_total;
    }
    void endTransition(bool conflict) {
        if (!trace_pending_) return;
        trace_pending_=false;
        trace_pending_row_.conflict=conflict;
        trace_pending_row_.after=snapshot();
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
    int decisionLevel() const { return static_cast<int>(trail_lim_.size()); }
    int value(int lit) const {
        const int val = values_[std::abs(lit)-1];
        return lit < 0 ? -val : val;
    }
    bool timedOut() const {
        return timeout_s_ > 0 && elapsed() >= timeout_s_;
    }
    int storeClause(std::vector<int> lits, bool learnt) {
        const int cid = static_cast<int>(clauses_.size());
        clauses_.push_back(Clause{std::move(lits),learnt,false,0.0});
        for(int lit : clauses_.back().lits)
            occurrence_[litIndex(lit)].push_back(cid);
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
                if (value(w.blocker) == 1) { ws[j++] = w; continue; }
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
            c.activity += 1.0;
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
        if (learned.size() == 1) return 0;
        size_t best=1;
        for (size_t k=2;k<learned.size();++k)
            if (levels_[std::abs(learned[k])-1] > levels_[std::abs(learned[best])-1]) best=k;
        std::swap(learned[1],learned[best]);
        return levels_[std::abs(learned[1])-1];
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
    void reduceLearnts() {
        std::vector<int> candidates;
        std::vector<uint8_t> locked(clauses_.size(),0);
        for (int v=0; v<n_; ++v) if (values_[v]!=0 && reasons_[v]>=0) locked[reasons_[v]]=1;
        for (int cid=0; cid<static_cast<int>(clauses_.size()); ++cid) {
            const Clause& c=clauses_[cid];
            if (c.learnt && !c.deleted && c.lits.size()>2 && !locked[cid]) candidates.push_back(cid);
        }
        if (candidates.size()<128) return;
        std::sort(candidates.begin(), candidates.end(), [&](int a,int b) {
            if (clauses_[a].activity != clauses_[b].activity)
                return clauses_[a].activity < clauses_[b].activity;
            return clauses_[a].lits.size()>clauses_[b].lits.size();
        });
        for (size_t k=0;k<candidates.size()/2;++k) {
            clauses_[candidates[k]].deleted=true;
            ++stats_.reduce_removed;
        }
    }
};

int run(int argc, char** argv) {
    const auto process_start=Clock::now();
    std::string input, mode="core", trace_file;
    int checkpoint=-1,intervention=0;
    double seconds=5.0;
    bool show_stats=false;
    for (int i=1;i<argc;++i) {
        std::string opt=argv[i];
        if (opt=="--mode" && i+1<argc) mode=argv[++i];
        else if (opt=="--time" && i+1<argc) seconds=std::stod(argv[++i]);
        else if (opt=="--checkpoint" && i+1<argc) checkpoint=std::stoi(argv[++i]);
        else if (opt=="--force-polarity" && i+1<argc) intervention=std::stoi(argv[++i]);
        else if (opt=="--transitions" && i+1<argc) trace_file=argv[++i];
        else if (opt=="--stats") show_stats=true;
        else if (opt=="--help") {
            std::cout<<"Usage: drnas-x45 <file.cnf> [--mode core|trace] [--time seconds] [--stats] [--checkpoint index] [--force-polarity -1|0|1]\n";
            return 0;
        } else if (opt.rfind("-",0)==0) throw std::runtime_error("unknown argument: "+opt);
        else if (input.empty()) input=opt;
        else throw std::runtime_error("multiple input files");
    }
    if (input.empty() || (mode!="core" && mode!="trace") || !std::isfinite(seconds) || seconds<0 ||
        checkpoint < -1 || (intervention!=-1 && intervention!=0 && intervention!=1) ||
        (intervention!=0 && checkpoint<0))
        throw std::runtime_error("invalid input/mode/time/checkpoint/polarity");
    if (!trace_file.empty() && mode!="trace") throw std::runtime_error("--transitions requires --mode trace");
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
            solver.emplace(declared_vars,mode,seconds,process_start,checkpoint,intervention);
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
    const Result r=solver->solve();
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
    if (show_stats) solver->writeCheckpoint(std::cerr);
    if (show_stats) {
        const Stats& s=solver->stats();
        std::cerr<<"X45_STATS {\"mode\":\""<<solver->mode()<<"\",\"status\":\""
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
                 <<",\"trace_evicted\":"<<s.trace_evicted
                 <<",\"checkpoint_hit\":"<<(solver->checkpointHit()?"true":"false")
                 <<",\"post_checkpoint_s\":"<<(solver->checkpointHit()?std::max(0.0,solver->elapsed()-solver->checkpointElapsed()):0.0)
                 <<"}\n";
    }
    return static_cast<int>(r);
}
} // namespace

int main(int argc,char** argv) {
    try {return run(argc,argv);}
    catch(const std::exception& e) {std::cerr<<"X45_ERROR "<<e.what()<<"\n";return 1;}
}

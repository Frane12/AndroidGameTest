// DRNAS X1 -- independent, native C++20 CDCL SAT solver.
// Original implementation. No external SAT solver is linked or invoked.
#include <algorithm>
#include <chrono>
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
    explicit Solver(int n, bool horizon, double seconds)
        : n_(n), horizon_(horizon), watches_(2 * static_cast<size_t>(n)),
          values_(n, 0), phase_(n, 1), levels_(n, 0), reasons_(n, -1),
          seen_(n, 0), activity_(n, 0), base_(n, 0), positive_(n, 0),
          negative_(n, 0), binary_(n, 0), generation_(n, 0), timeout_s_(seconds) {
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
            if (!clean.empty() && clean.back() == -lit) return; // tautology
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

    Result solve() {
        begun_ = Clock::now();
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
            int v = selectVariable();
            if (v == -1) {
                if (!verifyModel()) throw std::runtime_error("internal model verification failed");
                return Result::SAT;
            }
            ++stats_.decisions;
            newDecisionLevel();
            if (!enqueue(phase_[v] * (v+1), -1)) {
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
                if (value(lit) == 1) { satisfied = true; break; }
            }
            if (!satisfied) return false;
        }
        return true;
    }

    int nvars() const { return n_; }
    int nclauses() const { return original_count_; }
    int assignment(int v) const { return values_[v] == 0 ? phase_[v] : values_[v]; }
    const Stats& stats() const { return stats_; }
    double elapsed() const { return std::chrono::duration<double>(Clock::now() - begun_).count(); }
    const char* mode() const { return horizon_ ? "horizon" : "baseline"; }

  private:
    const int n_;
    const bool horizon_;
    std::vector<Clause> clauses_;
    std::vector<std::vector<Watch>> watches_;
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
        if (clauses_.back().lits.size() >= 2) {
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
    struct Probe { bool contradiction=false; int implied=0; int inspected=0; };
    Probe probe(int lit) {
        const int original_level=decisionLevel();
        const int original_trail=static_cast<int>(trail_.size());
        probing_=true;
        newDecisionLevel();
        if (!enqueue(lit,-1)) throw std::runtime_error("probe must start on free variable");
        const Prop p = propagate(1200);
        Probe r{p.result==PropResult::CONFLICT,
                static_cast<int>(trail_.size())-original_trail-1,p.inspected};
        ++stats_.horizon_probes;
        if (r.contradiction) ++stats_.horizon_conflicts;
        cancelUntil(original_level);
        probing_=false;
        return r;
    }
    int selectVariable() {
        if (heap_.empty()) return -1;
        if (!horizon_ || stats_.decisions%32 != 0 || (timeout_s_>0 && elapsed()>timeout_s_*0.93)) {
            std::vector<int> v=topCandidates(1);
            return v.empty() ? -1 : v[0];
        }
        std::vector<int> candidates=topCandidates(4);
        if (candidates.empty()) return -1;
        int best=candidates[0];
        double best_score=-1.e100;
        int8_t best_phase=phase_[best];
        for (int v:candidates) {
            const Probe yes=probe(v+1);
            const Probe no=probe(-v-1);
            // Empirical 'distance to obstruction': genuine contradiction on a
            // short implication path is strongest; otherwise prefer reach.
            double score=0;
            int8_t sign=phase_[v];
            if (yes.contradiction || no.contradiction) {
                if (yes.contradiction && (!no.contradiction || yes.inspected<=no.inspected)) sign=1;
                else sign=-1;
                score=1000.0-0.2*(sign>0?yes.inspected:no.inspected);
            } else {
                const double yes_reach=static_cast<double>(yes.implied)/(1.0+yes.inspected/250.0);
                const double no_reach=static_cast<double>(no.implied)/(1.0+no.inspected/250.0);
                if (yes_reach>no_reach) sign=1;
                else if (no_reach>yes_reach) sign=-1;
                score=std::max(yes_reach,no_reach);
            }
            score+=0.00001*(activity_[v]+base_[v]);
            if (score > best_score) {best_score=score;best=v;best_phase=sign;}
        }
        phase_[best]=best_phase;
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
    std::string input, mode="baseline";
    double seconds=5.0;
    bool show_stats=false;
    for (int i=1;i<argc;++i) {
        std::string opt=argv[i];
        if (opt=="--mode" && i+1<argc) mode=argv[++i];
        else if (opt=="--time" && i+1<argc) seconds=std::stod(argv[++i]);
        else if (opt=="--stats") show_stats=true;
        else if (opt=="--help") {
            std::cout<<"Usage: drnas-x1 <file.cnf> [--mode baseline|horizon] [--time seconds] [--stats]\n";
            return 0;
        } else if (opt.rfind("-",0)==0) throw std::runtime_error("unknown argument: "+opt);
        else if (input.empty()) input=opt;
        else throw std::runtime_error("multiple input files");
    }
    if (input.empty() || (mode!="baseline" && mode!="horizon") || !std::isfinite(seconds) || seconds<0)
        throw std::runtime_error("invalid input/mode/time");
    std::ifstream fd(input);
    if (!fd) throw std::runtime_error("cannot open CNF: "+input);
    int declared_vars=-1, declared_clauses=-1;
    std::optional<Solver> solver;
    int seen_clauses=0;
    std::vector<int> clause;
    std::string line;
    while(std::getline(fd,line)) {
        std::istringstream ss(line);
        std::string token;
        if (!(ss>>token)) continue;
        if (token=="c" || token=="%") continue;
        if (token=="p") {
            std::string fmt,extra;
            if (solver || !(ss>>fmt>>declared_vars>>declared_clauses) || fmt!="cnf" ||
                declared_vars<0 || declared_vars>20000000 || declared_clauses<0 || (ss>>extra))
                throw std::runtime_error("invalid DIMACS header");
            solver.emplace(declared_vars,mode=="horizon",seconds);
            continue;
        }
        if (!solver) throw std::runtime_error("missing DIMACS header");
        do {
            if (token=="c") break;
            size_t end=0;
            long long val=0;
            try {val=std::stoll(token,&end);} catch (...) {throw std::runtime_error("invalid DIMACS literal: "+token);}
            if (end!=token.size() || val < -declared_vars || val > declared_vars)
                throw std::runtime_error("out-of-range DIMACS literal");
            if (val==0) {solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;}
            else clause.push_back(static_cast<int>(val));
        } while (ss>>token);
    }
    if (!solver || !clause.empty() || seen_clauses!=declared_clauses)
        throw std::runtime_error("incomplete or mismatched DIMACS clause count");
    solver->finishParsing();
    const Result r=solver->solve();
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
    if (show_stats) {
        const Stats& s=solver->stats();
        std::cerr<<"X1_STATS {\"mode\":\""<<solver->mode()<<"\",\"status\":\""
                 <<(r==Result::SAT?"SAT":r==Result::UNSAT?"UNSAT":"UNKNOWN")
                 <<"\",\"vars\":"<<solver->nvars()<<",\"clauses\":"<<solver->nclauses()
                 <<",\"elapsed_s\":"<<std::fixed<<std::setprecision(6)<<solver->elapsed()
                 <<",\"decisions\":"<<s.decisions<<",\"conflicts\":"<<s.conflicts
                 <<",\"propagations\":"<<s.propagations<<",\"learnt\":"<<s.learnt
                 <<",\"restarts\":"<<s.restarts<<",\"horizon_probes\":"<<s.horizon_probes
                 <<",\"horizon_conflicts\":"<<s.horizon_conflicts
                 <<",\"horizon_inspections\":"<<s.horizon_inspections
                 <<",\"reduce_removed\":"<<s.reduce_removed<<"}\n";
    }
    return static_cast<int>(r);
}
} // namespace

int main(int argc,char** argv) {
    try {return run(argc,argv);}
    catch(const std::exception& e) {std::cerr<<"X1_ERROR "<<e.what()<<"\n";return 1;}
}

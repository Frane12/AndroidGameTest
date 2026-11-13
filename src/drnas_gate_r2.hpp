#ifndef DRNAS_GATE_R2_HPP
#define DRNAS_GATE_R2_HPP
// GATE-R2: budgeted relay with hysteresis, NOT a causal runtime predictor.
// State and estimates are reset for each solver process. No CNF IDs or labels.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <ostream>
#include <stdexcept>

namespace drnas {
class GateR2 {
public:
    enum class State { Sleep=0, Check=1, Active=2 };
    struct Counters {
        int64_t calls=0, skipped_schedule=0, skipped_cost=0, skipped_timeout=0;
        int64_t permits=0, observations=0, good=0, bad=0, switches=0;
        int64_t active_entries=0, sleep_entries=0, check_entries=0;
        int64_t periodic_wakes=0, shock_wakes=0, decay_events=0;
        int64_t rounds=0;
    };
    // Cheap check; no clock read when there is no pending decision to make.
    bool due(int64_t decisions, int64_t conflicts, bool adaptive) {
        ++c_.calls;
        shock_pending_=adaptive && state_==State::Sleep &&
            decisions>=last_probe_+256 && conflicts>=last_conflicts_+128;
        if (decisions<next_ && !shock_pending_) {
            ++c_.skipped_schedule;
            return false;
        }
        return true;
    }
    // Predicted cost is reserved before entry. A round can exceed its estimate;
    // actual overshoot is logged, and further work is refused until affordable.
    bool affordable(int64_t decisions, int64_t conflicts, double elapsed,
                    double limit, double spent, bool adaptive) {
        if (!std::isfinite(elapsed) || !std::isfinite(limit) ||
            !std::isfinite(spent) || elapsed<0.0 || limit<0.0 || spent<0.0)
            throw std::runtime_error("Invalid GateR2 cost observation");
        next_=decisions+192;
        if (limit>0.0 && elapsed>=0.80*limit) {
            ++c_.skipped_timeout;
            return false;
        }
        const double budget=0.0005+0.02*std::max(0.0,elapsed-spent);
        const double reserve=std::max(0.000002,1.25*cost_ewma_);
        if (spent+reserve>budget) {
            ++c_.skipped_cost;
            return false;
        }
        adaptive_=adaptive;
        if (adaptive && state_==State::Sleep) {
            if (shock_pending_) ++c_.shock_wakes; else ++c_.periodic_wakes;
            // Stale evidence is moved halfway toward neutral on a new check.
            usefulness_=0.5*usefulness_+0.25;
            ++c_.decay_events;
            transition(State::Check);
        }
        last_probe_=decisions;
        last_conflicts_=conflicts;
        next_=decisions+(adaptive?stride():192);
        ++c_.permits;
        return true;
    }
    void cost(double seconds, double total_elapsed, double total_spent) {
        if (!std::isfinite(seconds) || seconds<0.0 ||
            !std::isfinite(total_elapsed) || !std::isfinite(total_spent) ||
            total_elapsed<0.0 || total_spent<0.0)
            throw std::runtime_error("Invalid GateR2 round cost");
        cost_ewma_=c_.rounds==0?seconds:0.8*cost_ewma_+0.2*seconds;
        ++c_.rounds;
        const double ceiling=0.0005+0.02*std::max(0.0,total_elapsed-total_spent);
        max_overshoot_=std::max(max_overshoot_,std::max(0.0,total_spent-ceiling));
    }
    void feedback(bool useful, int64_t decisions) {
        ++c_.observations;
        if (useful) ++c_.good; else ++c_.bad;
        usefulness_=0.8*usefulness_+0.2*(useful?1.0:0.0);
        ++state_observations_;
        if (!adaptive_) return; // cost-only ablation never changes its schedule
        // At least four real outcomes before changing CHECK/ACTIVE state.
        if (state_observations_<4) return;
        if (state_==State::Check && usefulness_>=0.65) {
            sleep_stride_=512;
            transition(State::Active);
        } else if ((state_==State::Active && usefulness_<=0.35) ||
                   (state_==State::Check &&
                    (usefulness_<=0.35 || state_observations_>=8))) {
            const bool was_active=state_==State::Active;
            sleep_stride_=was_active?512:std::min(4096,sleep_stride_*2);
            transition(State::Sleep);
        }
        next_=decisions+stride();
    }
    int64_t next() const { return next_; }
    State state() const { return state_; }
    double usefulness() const { return usefulness_; }
    const Counters& counters() const { return c_; }
    void write(std::ostream& out) const {
        out<<"GATER2_GATE {\"calls\":"<<c_.calls
          <<",\"skipped_schedule\":"<<c_.skipped_schedule
          <<",\"skipped_cost\":"<<c_.skipped_cost
          <<",\"skipped_timeout\":"<<c_.skipped_timeout
          <<",\"permits\":"<<c_.permits<<",\"rounds\":"<<c_.rounds
          <<",\"proxy_good\":"<<c_.good<<",\"proxy_bad\":"<<c_.bad
          <<",\"observations\":"<<c_.observations<<",\"state_switches\":"<<c_.switches
          <<",\"active_entries\":"<<c_.active_entries
          <<",\"sleep_entries\":"<<c_.sleep_entries
          <<",\"check_entries\":"<<c_.check_entries
          <<",\"periodic_wakes\":"<<c_.periodic_wakes
          <<",\"shock_wakes\":"<<c_.shock_wakes
          <<",\"decay_events\":"<<c_.decay_events
          <<",\"final_state\":"<<static_cast<int>(state_)
          <<",\"usefulness_ewma\":"<<usefulness_
          <<",\"cost_ewma_s\":"<<cost_ewma_
          <<",\"max_budget_overshoot_s\":"<<max_overshoot_
          <<",\"proxy_not_causal_reward\":true}\n";
    }
private:
    State state_=State::Check;
    Counters c_;
    bool adaptive_=true, shock_pending_=false;
    int64_t next_=64, last_probe_=0, last_conflicts_=0;
    int state_observations_=0, sleep_stride_=512;
    double usefulness_=0.5, cost_ewma_=0.000020, max_overshoot_=0.0;
    int stride() const {
        if (state_==State::Active) return 96;
        if (state_==State::Check) return 128;
        return sleep_stride_;
    }
    void transition(State state) {
        if (state==state_) return;
        state_=state;
        state_observations_=0;
        ++c_.switches;
        if (state==State::Active) ++c_.active_entries;
        if (state==State::Sleep) ++c_.sleep_entries;
        if (state==State::Check) ++c_.check_entries;
    }
};
}
#endif

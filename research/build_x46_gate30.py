#!/usr/bin/env python3
"""Build X4.6 from an exact audited X4.5 source. No external solver code.

X46_SPARSE and X46_GATE share the X45 online scoring update. The gate learns
only a local proxy usefulness rate, NOT causal time saved or distance to SAT.
Assignment rollback does not restore watch order: neither arm is a matched
full-state counterfactual experiment. Original X45 is compiled unchanged.
"""
from pathlib import Path
import hashlib

source = Path('src/drnas_x45.cpp').read_text()
blob = hashlib.sha1(b'blob ' + str(len(source.encode())).encode() + b'\0' + source.encode()).hexdigest()
if blob != '50649c98e9edb371f8da57cfaf5b8e644315cfc5':
    raise RuntimeError('Unexpected X45 source: ' + blob)


def replace(old, new, count=1):
    global source
    if source.count(old) != count:
        raise RuntimeError('Patch anchor mismatch: ' + old[:100])
    source = source.replace(old, new)


replace('// DRNAS X4.5 -- native decision-level counterfactual BCP probes and within-solve online feedback.',
        '// DRNAS X4.6 GATE30 -- local usefulness/cost probe scheduling; prospective 30-category test.')
replace('    double x45_selected_gain_ = 0.0, x45_selected_units_ = 0.0;', r'''
    double x45_selected_gain_ = 0.0, x45_selected_units_ = 0.0;
    // Conservative cold start, identical for fixed sparse and adaptive gate.
    int64_t x46_next_ = 64, x46_last_probe_ = 0, x46_last_conflicts_ = 0;
    int x46_stride_ = 192, x46_window_ = 0, x46_good_window_ = 0;
    int64_t x46_calls_ = 0, x46_skips_ = 0, x46_budget_skips_ = 0;
    int64_t x46_good_ = 0, x46_bad_ = 0, x46_throttles_ = 0;
    int64_t x46_accelerations_ = 0, x46_shocks_ = 0;
    double x46_pending_gap_ = 0.0;
    bool x46_pending_changed_ = false;

    bool isX46() const {
        return mode_=="x46_gate" || mode_=="x46_sparse";
    }
    bool x46Permit() {
        ++x46_calls_;
        if (stats_.decisions<x46_next_) {
            // A new conflict burst permits a re-check, never bypasses budget.
            const bool shock=mode_=="x46_gate" &&
                stats_.decisions>=x46_last_probe_+128 &&
                stats_.conflicts>=x46_last_conflicts_+96;
            if (!shock) { ++x46_skips_; return false; }
            ++x46_shocks_;
        }
        x46_next_=stats_.decisions+(mode_=="x46_sparse"?192:x46_stride_);
        const double now=elapsed();
        // Approximate cumulative ceiling; may overshoot by one bounded round.
        // All checks, scoring, and feedback are still charged to actual E2E.
        if ((timeout_s_>0 && now>timeout_s_*0.80) ||
            probing_seconds_>0.0005+0.02*now) {
            ++x46_budget_skips_; return false;
        }
        x46_last_probe_=stats_.decisions;
        x46_last_conflicts_=stats_.conflicts;
        return true;
    }
    void x46Feedback(int gain, int implied, bool conflict) {
        if (!isX46()) return;
        // This is explicitly a usefulness PROXY, not seconds saved.
        const bool useful=x46_pending_changed_ && x46_pending_gap_>0.20 &&
            (gain>=1 || implied>=8 || conflict);
        if (useful) ++x46_good_; else ++x46_bad_;
        ++x46_window_; x46_good_window_+=useful;
        if (mode_=="x46_gate" && x46_window_>=4) {
            const int old=x46_stride_;
            if (x46_good_window_>=3) x46_stride_=std::max(48,x46_stride_/2);
            else if (x46_good_window_<=1) x46_stride_=std::min(1536,x46_stride_*2);
            if (x46_stride_>old) ++x46_throttles_;
            if (x46_stride_<old) ++x46_accelerations_;
            x46_next_=stats_.decisions+x46_stride_;
            x46_window_=0; x46_good_window_=0;
        }
    }
''')
condition='mode_=="x45_sham" || mode_=="x45_fixed" || mode_=="x45_online"'
replace(condition, condition+' || isX46()', 2)
replace('            if (mode_=="x45_online") {',
        '            x46Feedback(gain,implied,conflict);\n            if (mode_=="x45_online" || isX46()) {')
replace('    int selectX45Variable() {\n        const auto candidates=topCandidates(3);', r'''
    int selectX45Variable() {
        const bool gated=isX46();
        if (gated && !x46Permit()) {
            const auto first=topCandidates(1);
            return first.empty()?-1:first.front();
        }
        const auto candidates=topCandidates(3);''')
replace('        if (stats_.decisions%24!=0 ||\n            (timeout_s_>0 && elapsed()>timeout_s_*0.78) ||\n            (probing_seconds_>std::max(0.004,0.08*elapsed()))) {',
        '        if (!gated && (stats_.decisions%24!=0 ||\n            (timeout_s_>0 && elapsed()>timeout_s_*0.78) ||\n            (probing_seconds_>std::max(0.004,0.08*elapsed())))) {')
replace('        double core_gain=0.0, core_units=0.0;',
        '        double core_gain=0.0, core_units=0.0, core_score=0.0;')
replace('            const double s_pos=score(pos), s_neg=score(neg);',
        '            const double s_pos=score(pos), s_neg=score(neg);\n            if (v==core) core_score=default_sign>0?s_pos:s_neg;')
replace('        const int selected=sham?core:best;',
        '        const int selected=sham?core:best;\n        x46_pending_changed_=best!=core || sign_best!=default_sign;\n        x46_pending_gap_=std::clamp(best_score-core_score,0.0,200.0);')
replace('(mode!="core" && mode!="trace" && mode!="x45_sham" && mode!="x45_fixed" && mode!="x45_online")',
        '(mode!="core" && mode!="trace" && mode!="x45_sham" && mode!="x45_fixed" && mode!="x45_online" && mode!="x46_sparse" && mode!="x46_gate")')
replace('(mode.rfind("x45_",0)==0?"X45_STATS ":"X41_STATS ")',
        '(mode.rfind("x46_",0)==0?"X46_STATS ":(mode.rfind("x45_",0)==0?"X45_STATS ":"X41_STATS "))')
replace('    double x45UnitWeight() const { return x45_unit_weight_; }', r'''
    double x45UnitWeight() const { return x45_unit_weight_; }
    void writeGateStats() const {
        if (!isX46()) return;
        std::cerr<<"X46_GATE {\"calls\":"<<x46_calls_
          <<",\"skipped_schedule\":"<<x46_skips_
          <<",\"skipped_cost\":"<<x46_budget_skips_
          <<",\"proxy_good\":"<<x46_good_
          <<",\"proxy_bad\":"<<x46_bad_
          <<",\"throttles\":"<<x46_throttles_
          <<",\"accelerations\":"<<x46_accelerations_
          <<",\"shock_checks\":"<<x46_shocks_
          <<",\"final_stride\":"<<x46_stride_
          <<",\"proxy_not_causal_reward\":true}\n";
    }
''')
replace('    return static_cast<int>(r);',
        '    if (show_stats) solver->writeGateStats();\n    return static_cast<int>(r);')
Path('build').mkdir(exist_ok=True)
Path('build/drnas_x46_gate30.cpp').write_text(source)
print('X46_PATCH_PASS', blob, 'output_bytes', len(source.encode()))

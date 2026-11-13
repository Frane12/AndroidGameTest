#!/usr/bin/env python3
"""DRNAS COOP5.2: more conservative matched BCP evidence + configurable probe cap.

Build from frozen X5 via the existing COOP5.1 generator; only COOP5.2
changes the gate. All inference/proof code and previous binaries are frozen.
"""
import hashlib,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parents[2]
subprocess.run(["python3",str(R/"research/drnas_coop51/build.py")],cwd=R,check=True)
s=(R/"build/drnas_coop51.cpp").read_text()
def rep(a,b):
    global s
    if s.count(a)!=1:
        raise RuntimeError(("nonunique source anchor",a[:100],s.count(a)))
    s=s.replace(a,b)
rep('    bool coop51_hybrid_=COOP5_DYNAMIC_DEFAULT==2;',
'''    bool coop51_hybrid_=COOP5_DYNAMIC_DEFAULT==2;
    double coop52_budget_override_=-1.0;
    int64_t coop52_unmatched_rejected_=0,coop52_strong_rejected_=0;
    int64_t coop52_strong_accepted_=0,coop52_conflict_rejected_=0;
    void configureCoop52Budget(double ms) {
        if(!(ms>=0.05 && ms<=25.0) || !std::isfinite(ms))
            throw std::runtime_error("COOP52 budget must be 0.05..25ms");
        coop52_budget_override_=ms;
        coop5_budget_ms_=std::min(coop5_budget_ms_,ms);
    }''')
rep('''        if(normal.contradiction || guided.contradiction) {
            ++coop5_conflict_probes_;''',
'''        if(normal.contradiction || guided.contradiction) {
            ++coop52_conflict_rejected_;
            ++coop5_conflict_probes_;''')
rep('''        const bool recommend=confident && score>=2.4 &&
              ((normal.completed && guided.completed) ||
               (better_long>=3 && better_implied>=4));
        if(!recommend) {''',
'''        // COOP5.2 matched-evidence gate:
        // Reject unequal probe completion: such comparisons do not reflect
        // equal BCP work and can spuriously favor algebra over VSIDS.
        // With two full BCP prefixes, require a material improvement.
        // With both incomplete prefixes, require an even stronger margin,
        // so a partial result cannot look like a reliable quality win.
        const bool matched_completion=(normal.completed==guided.completed);
        if(!matched_completion)++coop52_unmatched_rejected_;
        const bool full=normal.completed && guided.completed;
        const bool conservative_full=full && score>=3.0 &&
             ((better_long>=2 && better_implied>=0) ||
              (better_long>=0 && better_implied>=8));
        const bool conservative_partial=(!normal.completed && !guided.completed) &&
             (better_long>=4 && better_implied>=8 && score>=6.0);
        const bool recommend=matched_completion &&
                            (conservative_full||conservative_partial);
        if(!recommend) {
            if(confident && score>=2.4)++coop52_strong_rejected_;''')
rep('''        ++coop5_recommend_;
        if(coop51_hybrid_ && depth==320)++coop51_deep_advice_;''',
'''        ++coop5_recommend_;
        ++coop52_strong_accepted_;
        if(coop51_hybrid_ && depth==320)++coop51_deep_advice_;''')
rep(r'''                 <<",\"cadence_final\":"<<coop5_gap_
                 <<"}\\n";''',
r'''                 <<",\"cadence_final\":"<<coop5_gap_
                 <<",\"quality_unmatched_rejected\":"<<coop52_unmatched_rejected_
                 <<",\"quality_strong_rejected\":"<<coop52_strong_rejected_
                 <<",\"quality_accepted\":"<<coop52_strong_accepted_
                 <<",\"quality_conflict_rejected\":"<<coop52_conflict_rejected_
                 <<"}\\n";''')
rep('''    std::string input, mode="trace", trace_file,coop_mode="off",coop4_policy="keep",coop5_mode="off";''',
'''    std::string input, mode="trace", trace_file,coop_mode="off",coop4_policy="keep",coop5_mode="off";
    double coop52_budget_ms=25.0;''')
rep('''        else if (opt=="--coop5" && i+1<argc) coop5_mode=argv[++i];''',
'''        else if (opt=="--coop5" && i+1<argc) coop5_mode=argv[++i];
        else if (opt=="--coop52-budget-ms" && i+1<argc)
            coop52_budget_ms=std::stod(argv[++i]);''')
rep('''            solver->configureCoop5(coop5_mode);
            solver->configureX5(''',
'''            solver->configureCoop5(coop5_mode);
            solver->configureCoop52Budget(coop52_budget_ms);
            solver->configureX5(''')
build=R/"build"
src=build/"drnas_coop52.cpp"
src.write_text(s)
out=build/"drnas-coop52-quality"
subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=2",
                str(src),"-o",str(out)],cwd=R,check=True)
print("COOP52_QUALITY_BUILD "+hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)

#!/usr/bin/env python3
"""Generate a diagnostic-only X5 source; the frozen production source is untouched."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def generate():
    source=(ROOT/'src/drnas_x5.cpp').read_text()
    def replace(old,new):
        nonlocal source
        assert source.count(old)==1, ('patch anchor drift',old[:80],source.count(old))
        source=source.replace(old,new)
    replace('#include <vector>','#include <vector>\n#include <array>\n#include <sys/resource.h>')
    replace('using Clock = std::chrono::steady_clock;',r'''using Clock = std::chrono::steady_clock;
struct DiagTimes {
    std::array<double,4> seconds{};
    std::array<Clock::time_point,4> active{};
    std::array<bool,4> running{};
    const char* phase="parse";
    double parse_seconds=0.0;
    double next_sample=0.0;
} diag;
struct DiagScope {
    int id;
    Clock::time_point start=Clock::now();
    explicit DiagScope(int value):id(value) {diag.active[id]=start;diag.running[id]=true;}
    ~DiagScope() {diag.seconds[id]+=std::chrono::duration<double>(Clock::now()-start).count();diag.running[id]=false;}
};
double diagSeconds(int id) {
    return diag.seconds[id]+(diag.running[id]?std::chrono::duration<double>(Clock::now()-diag.active[id]).count():0.0);
}''')
    replace('    const Stats& stats() const { return stats_; }',r'''    const Stats& stats() const { return stats_; }
    void progress(bool force=false) const {
        const double t=elapsed();
        if (!force && t<diag.next_sample) return;
        diag.next_sample=t+1.0;
        struct rusage usage{};
        getrusage(RUSAGE_SELF,&usage);
        std::cerr<<"X5_PROGRESS {\"elapsed_s\":"<<std::setprecision(9)<<t
            <<",\"phase\":\""<<diag.phase<<"\",\"parse_s\":"<<diag.parse_seconds
            <<",\"conflicts\":"<<stats_.conflicts<<",\"decisions\":"<<stats_.decisions
            <<",\"propagations\":"<<stats_.propagations<<",\"restarts\":"<<stats_.restarts
            <<",\"learnt_total\":"<<stats_.learnt<<",\"deleted_total\":"<<stats_.reduce_removed
            <<",\"learnt_active\":"<<stats_.learnt-stats_.reduce_removed
            <<",\"clause_slots\":"<<clauses_.size()<<",\"heap_entries\":"<<heap_.size()
            <<",\"gc_count\":"<<stats_.collections<<",\"maxrss_kib\":"<<usage.ru_maxrss
            <<",\"bcp_s\":"<<diagSeconds(0)<<",\"analysis_s\":"<<diagSeconds(1)
            <<",\"select_s\":"<<diagSeconds(2)<<",\"reduce_s\":"<<diagSeconds(3)
            <<"}\n"<<std::flush;
    }''')
    for anchor,num in [('    Prop propagate(int max_inspections) {',0),
                       ('    int analyze(int conflict, std::vector<int>& learned) {',1),
                       ('    int selectVariable() {',2),('    void reduceLearnts() {',3)]:
        replace(anchor,anchor+f'\n        DiagScope diagnostic_scope({num});')
    replace('    bool timedOut() const {\n        return timeout_s_ > 0 && elapsed() >= timeout_s_;',
            '    bool timedOut() const {\n        progress();\n        return timeout_s_ > 0 && elapsed() >= timeout_s_;')
    replace('                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;',
            '                solver->addOriginal(std::move(clause));clause.clear();++seen_clauses;\n                if ((seen_clauses & 511)==0) solver->progress();')
    replace('    solver->finishParsing();',
            '    solver->finishParsing();\n    diag.parse_seconds=solver->elapsed();diag.phase="search";solver->progress(true);')
    replace('    const Result r=solver->solve();',
            '    const Result r=solver->solve();\n    diag.phase="finished";solver->progress(true);')
    target=ROOT/'build/x5-telemetry.cpp';target.parent.mkdir(exist_ok=True);target.write_text(source)
    print('X5_TELEMETRY_SOURCE',hashlib.sha256(source.encode()).hexdigest())
    return target
if __name__=='__main__':generate()

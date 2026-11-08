#!/usr/bin/env python3
"""MRE5: extend MRE4 source-pinned CMS with global BCP watcher counts and CPU accounting.

All callbacks exist in the SAME patched CMS 5.11.15 binary on all arms.
Zero-I/O watcher counters: no per-event log. Enable and disable telemetry
at runtime without changing CNF or CDCL algorithm.

Process CPU and solve wall time are measured around cms.solve() in native C++.
Paired instrument-on/off arms expose overhead of the tracing probe itself.
"""
import pathlib
import sys
import mre4_patch_cms as old

def replace(s, before, after):
    assert s.count(before) == 1, "MRE5 source patch anchor not uniquely present: "+before[:140]
    return s.replace(before, after, 1)

def patch(root: pathlib.Path, native_out: pathlib.Path):
    old.patch_cms(root)
    old.bridge(pathlib.Path("research/r195_cms_native_bridge.cpp"), native_out)

    solver = root/"src"/"solver.cpp"
    text = solver.read_text()
    text = replace(text,
        '''    uint64_t conflicts[2] = {0, 0};
};''',
        '''    uint64_t conflicts[2] = {0, 0};
    uint64_t all_visits = 0;
    uint64_t all_units = 0;
    uint64_t all_conflicts = 0;
    uint64_t all_satisfied = 0;
    bool enabled = true;
};''')
    text = replace(text,
        '''extern "C" __attribute__((visibility("default")))
void drnas_trace_watch(uint64_t id, int outcome) {
    for (int t = 0; t < 2; ++t) {''',
        '''extern "C" __attribute__((visibility("default")))
void drnas_trace_set_enabled(int on) {
    drnas_trace.enabled = (on != 0);
}
extern "C" __attribute__((visibility("default")))
void drnas_trace_watch(uint64_t id, int outcome) {
    if (!drnas_trace.enabled) return;
    ++drnas_trace.all_visits;
    if (outcome == 1) ++drnas_trace.all_units;
    else if (outcome == 2) ++drnas_trace.all_conflicts;
    else if (outcome == 0) ++drnas_trace.all_satisfied;
    else __builtin_trap();
    for (int t = 0; t < 2; ++t) {''')
    text = replace(text,
        '''void drnas_trace_dump(void) {
    for (int t = 0; t < 2; ++t) {''',
        '''void drnas_trace_dump(void) {
    std::printf("DRNAS_WATCH_GLOBAL enabled=%d visits=%llu units=%llu conflicts=%llu satisfied=%llu\\n",
        drnas_trace.enabled ? 1 : 0,
        (unsigned long long)drnas_trace.all_visits,
        (unsigned long long)drnas_trace.all_units,
        (unsigned long long)drnas_trace.all_conflicts,
        (unsigned long long)drnas_trace.all_satisfied);
    for (int t = 0; t < 2; ++t) {''')
    solver.write_text(text)

    s=native_out.read_text()
    s=replace(s,'#include <sstream>\n',
        '#include <sstream>\n#include <chrono>\n#include <ctime>\n#include <sys/resource.h>\n#include <iomanip>\n')
    s=replace(s,
        'extern "C" void drnas_trace_dump(void);\n',
        'extern "C" void drnas_trace_dump(void);\n'
        'extern "C" void drnas_trace_set_enabled(int);\n')
    s=replace(s,'''        SATSolver cms;
        cms.set_num_threads(1);''',
        '''        const char* trace_raw=getenv("DRNAS_TRACE_ENABLED");
        check(trace_raw && (string(trace_raw)=="0" || string(trace_raw)=="1"),
              "must set DRNAS_TRACE_ENABLED to 0/1");
        const bool tracing = string(trace_raw)=="1";
        drnas_trace_set_enabled(tracing?1:0);
        SATSolver cms;
        cms.set_num_threads(1);''')
    s=replace(s,'''        const lbool status=cms.solve();
        string result="TIMEOUT";''',
        '''        struct timespec cpu_begin{},cpu_end{};
        struct rusage usage_before{},usage_after{};
        check(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&cpu_begin)==0,
              "failed to start process CPU time");
        check(getrusage(RUSAGE_SELF,&usage_before)==0,
              "failed to start rusage");
        const auto wall_begin=std::chrono::steady_clock::now();
        const lbool status=cms.solve();
        const auto wall_end=std::chrono::steady_clock::now();
        check(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&cpu_end)==0,
              "failed to stop process CPU time");
        check(getrusage(RUSAGE_SELF,&usage_after)==0,
              "failed to stop rusage");
        const double process_cpu_s=
            (double)(cpu_end.tv_sec-cpu_begin.tv_sec)+
            (double)(cpu_end.tv_nsec-cpu_begin.tv_nsec)/1e9;
        const auto seconds=[](const timeval& v) {
            return (double)v.tv_sec+(double)v.tv_usec/1e6;
        };
        const double usr_s=seconds(usage_after.ru_utime)-seconds(usage_before.ru_utime);
        const double sys_s=seconds(usage_after.ru_stime)-seconds(usage_before.ru_stime);
        const double solver_wall_s=std::chrono::duration<double>(wall_end-wall_begin).count();
        check(process_cpu_s>=0 && usr_s>=0 && sys_s>=0 &&
              solver_wall_s>=0,"negative CPU or wall clock");
        cout<<fixed<<setprecision(9)
            <<"DRNAS_CPU trace_enabled="<<(tracing?1:0)
            <<" process_cpu_s="<<process_cpu_s
            <<" user_cpu_s="<<usr_s
            <<" sys_cpu_s="<<sys_s
            <<" solve_wall_s="<<solver_wall_s<<"\\n";
        string result="TIMEOUT";''')
    native_out.write_text(s)
    print("MRE5_SOURCE_AND_NATIVE_CPU_PATCH_PASS",root,native_out,flush=True)

if __name__=="__main__":
    assert len(sys.argv)==3, "usage: mre5_patch_cms.py CMS_DIR BRIDGE_OUT"
    patch(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))

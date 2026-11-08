#!/usr/bin/env python3
"""Patch ONLY pinned CryptoMiniSat 5.11.15 for two tagged binary CRR clauses.

Records actual binary-watcher hits, unit propagations and conflicts from
PropEngine::prop_bin_cl() during non-inprocessing CDCL propagation, keyed by
CryptoMiniSat's stable clause watch ID attached at insertion time.

NOT a general CMS plugin, NOT proof of all influences of a transformed
clause after CMS inprocessing; reported attached count distinguishes
unsuccessful tagging. Source patch anchors are strict and fail closed.
"""
import pathlib, sys

def once(s, old, new):
    if s.count(old) != 1:
        raise RuntimeError("MRE4_PATCH_FAIL expected one anchor, got %d: %r"
                           % (s.count(old), old[:115]))
    return s.replace(old,new,1)

TRACE = r'''
// DRNAS-MRE4 WATCH-ID TELEMETRY (2 tags, one CMS thread, experiment only)
#include <cstdint>
#include <cstdio>
namespace {
struct DrnasTraceState {
    int pending = -1;
    uint64_t id[2] = {0, 0};
    uint64_t attached[2] = {0, 0};
    uint64_t visited[2] = {0, 0};
    uint64_t units[2] = {0, 0};
    uint64_t conflicts[2] = {0, 0};
};
DrnasTraceState drnas_trace;
}
extern "C" __attribute__((visibility("default")))
void drnas_trace_mark_next(int tag) {
    drnas_trace.pending = tag;
}
extern "C" __attribute__((visibility("default")))
void drnas_trace_watch(uint64_t id, int outcome) {
    for (int t = 0; t < 2; ++t) {
        if (drnas_trace.attached[t] && id == drnas_trace.id[t]) {
            ++drnas_trace.visited[t];
            if (outcome == 1) ++drnas_trace.units[t];
            if (outcome == 2) ++drnas_trace.conflicts[t];
        }
    }
}
extern "C" __attribute__((visibility("default")))
void drnas_trace_dump(void) {
    for (int t = 0; t < 2; ++t) {
        std::printf("DRNAS_TRACE tag=%d attached=%llu id=%llu visits=%llu units=%llu conflicts=%llu\n",
            t,
            (unsigned long long)drnas_trace.attached[t],
            (unsigned long long)drnas_trace.id[t],
            (unsigned long long)drnas_trace.visited[t],
            (unsigned long long)drnas_trace.units[t],
            (unsigned long long)drnas_trace.conflicts[t]);
    }
    std::fflush(stdout);
}
// END DRNAS-MRE4 WATCH-ID TELEMETRY
'''

def patch_cms(root):
    solver=root/"src"/"solver.cpp"
    prop=root/"src"/"propengine.cpp"
    text=solver.read_text()
    text=once(text, 'using namespace CMSat;\n',
              TRACE+'\nusing namespace CMSat;\n')
    text=once(text,
              '        case 2:\n            attach_bin_clause(ps[0], ps[1], red, ID);\n            return NULL;',
              '''        case 2:
            // Called only while loading a marked certified CNF lemma.
            // ID is the actual binary-watcher clause ID, not input index.
            if (drnas_trace.pending >= 0 && drnas_trace.pending < 2) {
                const int tag = drnas_trace.pending;
                drnas_trace.id[tag] = static_cast<uint64_t>(ID);
                ++drnas_trace.attached[tag];
                drnas_trace.pending = -1;
            }
            attach_bin_clause(ps[0], ps[1], red, ID);
            return NULL;''')
    solver.write_text(text)
    src=prop.read_text()
    src=once(src,'using namespace CMSat;\n',
             'extern "C" void drnas_trace_watch(uint64_t id, int outcome);\n'
             'using namespace CMSat;\n')
    src=once(src,
             '    const lbool val = value(i->lit2());\n    if (val == l_Undef) {\n',
             '''    const lbool val = value(i->lit2());
    // Real CDCL watcher event; distinguish unit implication and conflict.
    // Exclude inprocessing propagation; counters carry attached watch IDs.
    if constexpr (!inprocess) {
        drnas_trace_watch(i->get_ID(), val == l_Undef ? 1 :
                           (val == l_False ? 2 : 0));
    }
    if (val == l_Undef) {
''')
    prop.write_text(src)
    print('MRE4_CMS_SOURCE_PATCH_PASS', solver, prop,flush=True)

def bridge(src_path, dst_path):
    s=src_path.read_text()
    s=once(s,'#include <algorithm>\n',
           '#include <algorithm>\n#include <cstdlib>\n#include <sstream>\n')
    s=once(s,'using namespace CMSat;\n',
           '''using namespace CMSat;
extern "C" void drnas_trace_mark_next(int);
extern "C" void drnas_trace_dump(void);

static vector<int> tagged_literals(const char* key) {
    const char* raw=getenv(key);
    if(!raw || !*raw) return {};
    string value(raw);
    replace(value.begin(),value.end(),',',' ');
    istringstream in(value);
    vector<int> lits;
    int lit;
    while(in>>lit) lits.push_back(lit);
    check(lits.size()==2,"tagged lemma must be two literals");
    sort(lits.begin(),lits.end());
    return lits;
}
'''.replace('    check(lits.size()==2,"tagged lemma must be two literals");',
            '    if(lits.size()!=2) throw runtime_error("wrong tagged binary clause");'))
    s=once(s,'''        for(const auto& c:clauses) {
            vector<Lit> lits;''',
        '''        const char* raw_n=getenv("DRNAS_ORIG_COUNT");
        check(raw_n!=nullptr,"DRNAS_ORIG_COUNT missing");
        const size_t original_count=stoul(raw_n);
        check(original_count<=clauses.size(),"original clause count invalid");
        const auto tag0=tagged_literals("DRNAS_TAG_0");
        const auto tag1=tagged_literals("DRNAS_TAG_1");
        unsigned marked[2]={0,0};
        for(size_t ci=0;ci<clauses.size();ci++) {
            const auto& c=clauses[ci];
            int trace_tag=-1;
            if(ci>=original_count && c.size()==2) {
                auto normalized=c;
                sort(normalized.begin(),normalized.end());
                if(normalized==tag0) trace_tag=0;
                if(normalized==tag1) {
                    check(trace_tag==-1,"same clause used as both tags");
                    trace_tag=1;
                }
                if(trace_tag>=0) marked[trace_tag]++;
            }
            drnas_trace_mark_next(trace_tag);
            vector<Lit> lits;''')
    s=once(s,'''            if(!cms.add_clause(lits)) {
                cout<<"R195_RESULT status=UNSAT''',
           '''            if(!cms.add_clause(lits)) {
                drnas_trace_mark_next(-1);
                cout<<"R195_RESULT status=UNSAT''')
    s=once(s,'''            }
        }
        Stats stats;''',
           '''            }
            drnas_trace_mark_next(-1);
        }
        check(marked[0]<=1 && marked[1]<=1,"duplicate trace lemma");
        cout<<"DRNAS_TRACE_INPUT marked0="<<marked[0]
            <<" marked1="<<marked[1]
            <<" original_count="<<original_count
            <<" total_count="<<clauses.size()<<"\\n";
        Stats stats;''')
    s=once(s,'        cout<<"R195_RESULT status="<<result\n',
           '        drnas_trace_dump();\n        cout<<"R195_RESULT status="<<result\n')
    dst_path.parent.mkdir(parents=True,exist_ok=True)
    dst_path.write_text(s)
    print('MRE4_BRIDGE_PATCH_PASS',dst_path,flush=True)

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: mre4_patch_cms.py CMS_SRC_DIR BRIDGE_OUT")
    root=pathlib.Path(sys.argv[1])
    patch_cms(root)
    bridge(pathlib.Path("research/r195_cms_native_bridge.cpp"),
           pathlib.Path(sys.argv[2]))

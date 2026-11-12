#!/usr/bin/env python3
"""Isolated BCP ablation on the frozen R153/native composite. No policy changes."""
import hashlib,json,os,pathlib,shutil,subprocess
P=pathlib.Path
BASE=P('mre_r28_native'); OUT=P('mre_bcp1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def one(s,a,b):
    assert s.count(a)==1,('patch drift',a[:100],s.count(a))
    return s.replace(a,b,1)
def main():
    assert (BASE/'drnas_r28_native').exists(),'build frozen R28 native first'
    before={str(p):sha(p) for p in BASE.iterdir() if p.is_file()}
    OUT.mkdir(exist_ok=True)
    for p in BASE.iterdir():
        if p.suffix in ('.hpp','.cpp'):shutil.copy2(p,OUT/p.name)
    core=(OUT/'drnas_native_core_c.hpp').read_text()
    core=one(core,'    void atlas16_compact(){\n        const size_t before=clauses_.size();',
        '''    void atlas16_compact(){
        // A no-op compaction must return BEFORE moving any clause vectors.
        // Production reduction normally calls only with tombstones; keep the API safe too.
        if(std::none_of(clauses_.begin(),clauses_.end(),
                       [](const drnas::Clause& c){return c.lits.empty();}))return;
        const size_t before=clauses_.size();''')
    core=one(core,'    bool learned = false;','''    bool learned = false;
#ifdef DRNAS_BCP1_CIRCULAR
    // Stored with the clause, so compaction carries the cursor with its literals.
    uint32_t scan_from = 2;
#endif''')
    old='''                for (size_t k = 2; k < clause.size(); ++k) {
#ifdef DRNAS_WATCH_DIAG
                    ++watch_diag_.candidate_probes;
#endif
                    if (lit_value(clause[k]) != -1) { candidate = k; break; }
                }'''
    core=one(core,old,'''#ifdef DRNAS_BCP1_CIRCULAR
                // Complete circular scan: never skip a literal, even after backtracking.
                if (clause.size() > 2) {
                    auto& cursor = clauses_[cid].scan_from;
                    size_t k = (cursor >= 2 && cursor < clause.size()) ? cursor : 2;
                    for (size_t left = clause.size() - 2; left; --left) {
#ifdef DRNAS_WATCH_DIAG
                        ++watch_diag_.candidate_probes;
#endif
                        if (lit_value(clause[k]) != -1) { candidate = k; break; }
                        if (++k == clause.size()) k = 2;
                    }
                    if (candidate != clause.size())
                        cursor = candidate + 1 < clause.size() ? candidate + 1 : 2;
                }
#else
'''+old+'''
#endif''')
    (OUT/'drnas_native_core_c.hpp').write_text(core)
    native=(OUT/'native.cpp').read_text()
    native=one(native,'  const auto &st=solver.statistics();','''#ifdef DRNAS_PROFILE
  solver.print_profile();
#endif
#ifdef DRNAS_WATCH_DIAG
  solver.print_watch_diag();
#endif
  const auto &st=solver.statistics();''')
    (OUT/'native.cpp').write_text(native)
    flags=[os.getenv('CXX','g++'),'-O3','-std=c++17','-Iresearch','-Imre_bcp1','-Imre_atlas15']
    variants={'BLOCKER':['-DDRNAS_ONE2_BLOCKER'],
              'CIRCULAR':['-DDRNAS_ONE2_BLOCKER','-DDRNAS_BCP1_CIRCULAR']}
    for name,defs in variants.items():
        subprocess.run(flags+defs+['research/drnas_r28_native_main.cpp',str(OUT/'exact.cpp'),str(OUT/'native.cpp'),'-o',str(OUT/name)],check=True)
    # Test-only access to internals exercises deletion/compaction. Never linked into measured binaries.
    audit=core.replace('#include "ltm8_members.hpp"',(OUT/'ltm8_members.hpp').read_text())
    audit=audit.replace('class NativeCDCL {','class NativeCDCL {\npublic:').replace('private:','public:')
    (OUT/'audit_core.hpp').write_text(audit)
    for name,defs in variants.items():
        subprocess.run(flags+defs+['-O1','-g','-fsanitize=undefined','-fno-sanitize-recover=all',
            'research/drnas_bcp1_core_test.cpp','-o',str(OUT/('test_'+name))],check=True)
    assert before=={str(p):sha(p) for p in BASE.iterdir() if p.is_file()},'frozen base changed'
    pins=dict(frozen=before,candidate={str(p):sha(p) for p in OUT.iterdir() if p.is_file()},
              variants=variants,compiler=subprocess.check_output([flags[0],'--version'],text=True).splitlines()[0])
    (OUT/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    print('BCP1_BUILD_PASS baseline_unchanged=true variants=BLOCKER,CIRCULAR',flush=True)
if __name__=='__main__':main()

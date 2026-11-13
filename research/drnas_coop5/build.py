#!/usr/bin/env python3
"""Build TWO distinct COOP5 solver executables from one frozen CDCL-derived source.

drnas-coop5-fixed: strict 25ms aggregate gate, fixed depth/cadence
drnas-coop5-dynamic: online adaptive probing depth/cadence, <=25ms cap
In either binary, modes --coop5 off/shadow/on isolate inference from probing.
"""
import hashlib,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parents[2]
subprocess.run(["python3",str(R/"research/drnas_coop4/build.py")],cwd=R,check=True)
s=(R/"build/drnas_coop4.cpp").read_text()
def rep(a,b):
    global s
    assert s.count(a)==1,(a[:100],s.count(a))
    s=s.replace(a,b)
probe_code=(R/"research/drnas_coop5/probe_methods.inc").read_text()
rep("    int coop_hint_=-1;", "    int coop_hint_=-1;\n"+probe_code)
rep('    void reportCoop() const { coop_.report(); }',
    '    void reportCoop() const { coop_.report(); coop5Report(); }')
rep('''            if(coop_.mode=="on" && coop_hint_>=0 && values_[coop_hint_]==0 && v>=0) {
                if(v!=coop_hint_){offer(v);v=coop_hint_;++coop_.applied_hints;}
            }''','''            if(coop_.mode=="on" && coop_hint_>=0 &&
               values_[coop_hint_]==0 && v>=0) {
                if(coop5_mode_=="off") {
                    if(v!=coop_hint_){offer(v);v=coop_hint_;++coop_.applied_hints;}
                } else {
                    v=coop5Choose(v);
                }
            }''')
rep('''    struct Probe { bool contradiction=false; int implied=0; int inspected=0;''',
    '''    struct Probe { bool contradiction=false,completed=false; int implied=0; int inspected=0;''')
rep('    Probe probe(int lit) {',
    '    Probe probe(int lit,int max_inspections=900) {')
rep('        const Prop p=propagate(900);',
    '        const Prop p=propagate(max_inspections);')
rep('        r.contradiction=p.result==PropResult::CONFLICT;',
    '        r.contradiction=p.result==PropResult::CONFLICT;\n        r.completed=p.result==PropResult::OK;')
rep('''            p = propagate(-1);
            if (p.result == PropResult::OK) p=cooperate();''',
    '''            p = propagate(-1);
            coop5Settle(p.result == PropResult::CONFLICT);
            if (p.result == PropResult::OK) p=cooperate();''')
rep('''    std::string input, mode="trace", trace_file,coop_mode="off",coop4_policy="keep";''',
    '''    std::string input, mode="trace", trace_file,coop_mode="off",coop4_policy="keep",coop5_mode="off";''')
rep('''        else if (opt=="--coop4-policy" && i+1<argc) coop4_policy=argv[++i];''',
    '''        else if (opt=="--coop4-policy" && i+1<argc) coop4_policy=argv[++i];
        else if (opt=="--coop5" && i+1<argc) coop5_mode=argv[++i];''')
rep('''            solver->configureCoop4Policy(coop4_policy);
            solver->configureX5(''',
    '''            solver->configureCoop4Policy(coop4_policy);
            solver->configureCoop5(coop5_mode);
            solver->configureX5(''')
src=R/"build/drnas_coop5.cpp"
src.write_text(s)
for policy,macro in (("fixed","0"),("dynamic","1")):
    binary=R/"build"/("drnas-coop5-"+policy)
    cmd=["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
         "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT="+macro,
         str(src),"-o",str(binary)]
    subprocess.run(cmd,check=True,cwd=R)
    print("COOP5_BUILD "+policy+" "+hashlib.sha256(binary.read_bytes()).hexdigest(),flush=True)

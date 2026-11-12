#!/usr/bin/env python3
"""One self-contained C++ DRNAS R153->LTM7 solver with guarded Gaussian reductions.

The original exact-source R153 from a pinned historical commit is embedded as
the fast path. On R153 abstention, NO external process is invoked: its
fallback throws into the native LTM7 CDCL implementation in the same binary.

Two isolated modes:
 R153_LTM7_DIRECT : R153 certified complete GF(2)/unit pre-solver -> LTM7 CDCL.
 R153_LTM7_GAUSS  : identical, plus selective bounded Gaussian RREF on source-
                    certified XOR equations, feeding only implied units and
                    binaries into native CDCL; never guessed CNF clauses.

Neither default CDCL nor historic R153 source is changed in the repository.
"""
from pathlib import Path

root=Path("mre_atlas23")
source=root/"native.cpp"
r153src=Path("frozen_r153/research/r153_exact_units_gf2.cpp")
assert r153src.is_file(), "Missing frozen R153 source checkout"
r153=r153src.read_text()
needle='static int fallback(const string& filename,const string& kissat,'
assert r153.count(needle)==1
begin=r153.index(needle)
end=r153.index('int main(int argc,char** argv){',begin)
assert "execv(args[0],args)" in r153[begin:end],"Historical fallback drift"
new_fallback=r'''struct R153NativeAbstain {};
static int fallback(const string&,const string&,
                    const string& reason,int total,int covered,int neq,bool) {
  r153_trace_decision("fallback",total,covered,0);
  cout<<"c R28_ROUTE fallback reason="<<reason<<" clauses="<<total
      <<" covered="<<covered<<" equations="<<neq<<"\\n"<<flush;
  throw R153NativeAbstain{}; // native CDCL takes over in the SAME process
}
'''
# Raw python text has \\n from JS serialization; normalize to one C++ escape.
new_fallback=new_fallback.replace('\\\\n','\\n')
r153=r153[:begin]+new_fallback+r153[end:]
assert r153.count('int main(int argc,char** argv){')==1
r153=r153.replace('int main(int argc,char** argv){',
                   'int r153_embedded_main(int argc,char** argv){',1)
assert 'execv(' not in r153[r153.index('struct R153NativeAbstain'):], "External fallback still reachable"
(root/"r153_embedded.hpp").write_text("// Embedded original R153, pinned historic commit, fallback replaced by exception.\n"+r153)

s=source.read_text()
anchor='mode=="LTM7_SELECT"'
count=s.count(anchor)
assert count>=6,("LTM7 dispatch drift",count)
s=s.replace(anchor,'(mode=="LTM7_SELECT"||mode=="R153_LTM7_DIRECT"||mode=="R153_LTM7_GAUSS")')

# LTM6 source graph gate is now computed for both R153+LTM7 variants.
# Gaussian activation is independent of live propagator activation, and strictly
# source certified: only exact-XOR extracted rows are eliminated.
target='const bool use_gauss='
assert s.count(target)==1,("Gauss dispatch drift",s.count(target))
s=s.replace(target,
'''const bool use_gauss=(mode=="R153_LTM7_GAUSS"
      && ltm6_screen.rows>=2 && ltm6_screen.rows<=128
      && ltm6_screen.short_pairs>0
      && orig.vars<=2000 && orig.clauses.size()<=12000) || ''',1)

# Rename original native entry point before injecting the independent original
# R153 source and an outer wrapper. This avoids any second process/exec.
oldmain='int main(int argc,char**argv){'
assert s.count(oldmain)==1,("Native main drift",s.count(oldmain))
s=s.replace(oldmain,'static int drnas_cdcl_embedded_main(int argc,char**argv){',1)
header='''#include "r153_embedded.hpp"
#include <iomanip>
'''
s=header+s

wrapper=r'''
int main(int argc,char**argv){
    if(argc<8 || std::string(argv[2])!="--mode"
       || std::string(argv[4])!="--time")
        return drnas_cdcl_embedded_main(argc,argv);
    const std::string mode=argv[3];
    if(mode!="R153_LTM7_DIRECT" && mode!="R153_LTM7_GAUSS")
        return drnas_cdcl_embedded_main(argc,argv);
    using Clk=std::chrono::steady_clock;
    const auto begin=Clk::now();
    const double budget=std::stod(argv[5]);
    if(!(budget>0) || !(budget<=120) || !std::isfinite(budget))
        return drnas_cdcl_embedded_main(argc,argv);
    char* rargv[]={const_cast<char*>("r153_embedded"),
                   argv[1], const_cast<char*>("native_cdcl_no_exec"), nullptr};
    try{
        const int outcome=r153_embedded_main(3,rargv);
        if(outcome!=10 && outcome!=20) return 2;
        std::cout<<"R153_LTM7_GATE route=R153_VERIFIED"
                 <<" gauss_enabled=0"
                 <<" e2e_s="<<std::chrono::duration<double>(Clk::now()-begin).count()
                 <<std::endl;
        return outcome;
    }catch(const R153NativeAbstain&){
        const double elapsed=std::chrono::duration<double>(Clk::now()-begin).count();
        const double remaining=budget-elapsed;
        std::cout<<"R153_LTM7_GATE route=CDCL_FALLBACK"
                 <<" screen_elapsed_s="<<elapsed
                 <<" remaining_s="<<remaining<<std::endl;
        if(remaining<=0.001){std::cout<<"s UNKNOWN"<<std::endl;return 0;}
        std::ostringstream cap;cap<<std::fixed<<std::setprecision(6)<<remaining;
        std::string time_arg=cap.str();
        std::vector<char*> args(argv,argv+argc);
        args[5]=time_arg.data();
        return drnas_cdcl_embedded_main(argc,args.data());
    }
}
'''
s += "\n"+wrapper
source.write_text(s)
print("R153_LTM7_GAUSS_PATCH_PASS single_binary=true no_external_exec=true "
      f"ltm7_sites={count} gf2_certified_only=true gaussian_gate=short_pairs",flush=True)

// R190: same CaDiCaL-2.1 native solver, three documented configurations.
// No extra clauses, no modified input and no access to expected SAT/UNSAT labels.
#include "cadical.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace std;
struct Deadline : CaDiCaL::Terminator {
  chrono::steady_clock::time_point start=chrono::steady_clock::now();
  double limit;
  explicit Deadline(double s):limit(s){}
  bool terminate() override {
    return chrono::duration<double>(chrono::steady_clock::now()-start).count()>=limit;
  }
};
int main(int argc,char**argv) {
  try {
    if(argc!=4) throw runtime_error("usage CNF CAP_SECONDS default|sat|unsat");
    const string profile=argv[3];
    if(profile!="default" && profile!="sat" && profile!="unsat")
      throw runtime_error("unsupported configuration");
    const double cap=stod(argv[2]);
    if(cap<0.1 || cap>120) throw runtime_error("bad time limit");
    CaDiCaL::Solver solver;
    if(profile!="default" && !solver.configure(profile.c_str()))
      throw runtime_error("CaDiCaL refused configuration");
    int n=0;
    const char*error=solver.read_dimacs(argv[1],n,1);
    if(error) throw runtime_error(error);
    Deadline deadline(cap);
    solver.connect_terminator(&deadline);
    const auto tick=chrono::steady_clock::now();
    const int result=solver.solve();
    const double seconds=chrono::duration<double>(chrono::steady_clock::now()-tick).count();
    solver.disconnect_terminator();
    if(result!=0 && result!=10 && result!=20) throw runtime_error("invalid status");
    cout<<fixed<<setprecision(7)<<"R182_STATUS status="
        <<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
        <<" solver_s="<<seconds<<" variables="<<n<<"\n";
    cout<<"R190_PROFILE "<<profile<<"\n";
    if(result==10) {
      for(int v=1;v<=n;++v) {
        const int lit=solver.val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    solver.statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  } catch(const exception &e) {
    cerr<<"R190_DRIVER_FAIL "<<e.what()<<"\n";
    return 2;
  }
}

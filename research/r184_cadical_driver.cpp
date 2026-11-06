// R184: pinned clean CaDiCaL executor, no source label or policy inputs.
// Returns SAT/UNSAT/UNKNOWN; SAT model independently checked by Python.
#include "cadical.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace std;
struct Stop : CaDiCaL::Terminator {
  chrono::steady_clock::time_point start=chrono::steady_clock::now();
  double cap;explicit Stop(double c):cap(c){}
  bool terminate()override{
    return chrono::duration<double>(chrono::steady_clock::now()-start).count()>=cap;
  }
};
int main(int argc,char **argv){
 try{
  if(argc!=3)throw runtime_error("usage CNF CAP_SECONDS");
  double cap=stod(argv[2]);if(cap<0.1||cap>120)throw runtime_error("bad cap");
  CaDiCaL::Solver solver;
  int n=0;const char*err=solver.read_dimacs(argv[1],n,1);
  if(err)throw runtime_error(err);
  Stop stop(cap);solver.connect_terminator(&stop);
  const auto tick=chrono::steady_clock::now();
  int res=solver.solve();
  double seconds=chrono::duration<double>(chrono::steady_clock::now()-tick).count();
  solver.disconnect_terminator();
  if(res!=0&&res!=10&&res!=20)throw runtime_error("bad status");
  cout<<fixed<<setprecision(7)<<"R182_STATUS status="
      <<(res==10?"SAT":res==20?"UNSAT":"TIMEOUT")
      <<" solver_s="<<seconds<<" variables="<<n<<"\n";
  if(res==10){
    for(int v=1;v<=n;++v){
      int lit=solver.val(v);if(lit){
        cout<<"v "<<lit<<" 0\n";
      }
    }
  }
  cout.flush();return 0;
 }catch(const exception&e){cerr<<"R182_DRIVER_FAIL "<<e.what()<<"\n";return 2;}
}

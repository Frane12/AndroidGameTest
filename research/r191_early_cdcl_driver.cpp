// DRNAS R191 - bounded first-conflict probing and genuine in-process continuation.
// All arms use the SAME pinned CaDiCaL 2.1 source and solver binary.
// The IPASIR learner is telemetry only: never injects or alters clauses.
#include "cadical.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <algorithm>
using namespace std;

struct Stop : CaDiCaL::Terminator {
  chrono::steady_clock::time_point start = chrono::steady_clock::now();
  double cap;
  explicit Stop(double seconds) : cap(seconds) {}
  bool terminate() override {
    return chrono::duration<double>(chrono::steady_clock::now()-start).count()>=cap;
  }
};

struct LearnStats : CaDiCaL::Learner {
  long long clauses=0, short3=0, binary=0, total_literals=0;
  bool learning(int size) override {
    ++clauses;total_literals+=size;
    if(size<=3)++short3;
    if(size<=2)++binary;
    return false; // do not request clause literals; observable only
  }
  void learn(int) override {}
};
int main(int argc,char**argv) {
  try {
    if(argc!=4)throw runtime_error("usage CNF CAP_SECONDS default|sat|probe|continue");
    string mode(argv[3]);
    if(mode!="default" && mode!="sat" && mode!="probe" && mode!="continue")
      throw runtime_error("invalid R191 mode");
    double cap=stod(argv[2]);
    if(cap<0.10||cap>120)throw runtime_error("invalid cap");
    CaDiCaL::Solver solver;
    if(mode=="sat" && !solver.configure("sat"))
      throw runtime_error("sat config refused");
    int n=0;
    const char *e=solver.read_dimacs(argv[1],n,1);
    if(e)throw runtime_error(e);
    LearnStats learner;
    bool telemetry=(mode=="probe"||mode=="continue");
    if(telemetry)solver.connect_learner(&learner);
    const int original_active=solver.active();
    const int original_irred=solver.irredundant();
    Stop clock(cap);
    solver.connect_terminator(&clock);
    const auto begin=chrono::steady_clock::now();
    int result=0;
    if(telemetry){
      if(!solver.limit("conflicts",256))throw runtime_error("conflict probe unsupported");
      result=solver.solve();
      if(result!=0&&result!=10&&result!=20)throw runtime_error("bad probe status");
      double probe_s=chrono::duration<double>(
        chrono::steady_clock::now()-begin).count();
      cout<<fixed<<setprecision(6)
          <<"R191_PROBE result="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
          <<" seconds="<<probe_s
          <<" active_before="<<original_active
          <<" active_after="<<solver.active()
          <<" irred_before="<<original_irred
          <<" irred_after="<<solver.irredundant()
          <<" learned="<<learner.clauses
          <<" short3="<<learner.short3
          <<" binary="<<learner.binary
          <<" mean_len="<<(learner.clauses?
                   double(learner.total_literals)/learner.clauses:0.0)
          <<"\n";
      if(mode=="continue"&&result==0){
        // The next solve resumes the SAME solver (learned clauses are retained).
        // Limit is reset by solve(); no second solver/preprocessing is created.
        result=solver.solve();
      }
    }else{
      result=solver.solve();
    }
    double elapsed=chrono::duration<double>(
        chrono::steady_clock::now()-begin).count();
    solver.disconnect_terminator();
    if(telemetry)solver.disconnect_learner();
    if(result!=0&&result!=10&&result!=20)throw runtime_error("bad final status");
    cout<<fixed<<setprecision(7)<<"R182_STATUS status="
        <<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
        <<" solver_s="<<elapsed<<" variables="<<n<<"\n";
    if(result==10){
      for(int v=1;v<=n;++v){
        int lit=solver.val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    solver.statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  }catch(const exception&e){
    cerr<<"R191_DRIVER_FAIL "<<e.what()<<"\n";
    return 2;
  }
}

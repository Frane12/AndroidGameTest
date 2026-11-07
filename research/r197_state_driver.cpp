// DRNAS R197 — CaDiCaL 2.1 isolated internal CDCL schedule-resumption controls.
// Branch modes: baseline, split256 (original), and independently preserve one
// of restart/rephase/stabilization schedules on the second solve() call.
#include "cadical.hpp"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;
struct Deadline final : CaDiCaL::Terminator {
  Clock::time_point started; double cap;
  Deadline(Clock::time_point t,double s):started(t),cap(s){}
  bool terminate() override {
    return chrono::duration<double>(Clock::now()-started).count()>=cap;
  }
};
static unique_ptr<CaDiCaL::Solver> build(const string &path, int seed,
                                         Deadline &deadline, int &vars) {
  auto s=make_unique<CaDiCaL::Solver>();
  if (!s->set("seed",seed))throw runtime_error("bad seed option");
  const char *error=s->read_dimacs(path.c_str(),vars,1);
  if (error)throw runtime_error(error);
  s->connect_terminator(&deadline);
  return s;
}
static string state(int v) {
  return v==10?"SAT":v==20?"UNSAT":v==0?"TIMEOUT":"INVALID";
}
int main(int argc,char **argv) {
  try{
    if(argc!=5)throw runtime_error("usage ORIGINAL_CNF CAP MODE SEED");
    const string path=argv[1],mode=argv[3];
    double cap=stod(argv[2]);int seed=stoi(argv[4]);
    if(!isfinite(cap)||cap<1||cap>180||seed<0||seed>1000000)
      throw runtime_error("invalid cap/seed");
    if(mode!="default"&&mode!="split256"&&mode!="split128_twice"&&
       mode!="split256_keep_restart"&&mode!="split256_keep_rephase"&&
       mode!="split256_keep_stabilize"&&mode!="split256_keep_all")
      throw runtime_error("unknown R197 mode");
    const string keep=mode=="split256_keep_restart"?"restart":
                      mode=="split256_keep_rephase"?"rephase":
                      mode=="split256_keep_stabilize"?"stabilize":
                      mode=="split256_keep_all"?"all":"none";
    if(setenv("DRNAS_R197_KEEP",keep.c_str(),1))
      throw runtime_error("setenv failed");
    const auto start=Clock::now();Deadline deadline(start,cap);
    int vars=0,rc=0,calls=0,pilots=0;double pilot_s=0;
    auto solver=build(path,seed,deadline,vars);
    if(mode!="default"){
      int rounds=mode=="split128_twice"?2:1;
      int bound=mode=="split128_twice"?128:256;
      for(int w=0;w<rounds&&!deadline.terminate();w++){
        auto t=Clock::now();
        if(!solver->limit("conflicts",bound))
          throw runtime_error("CaDiCaL conflict limit unavailable");
        rc=solver->solve();calls++;pilots++;
        pilot_s+=chrono::duration<double>(Clock::now()-t).count();
        if(rc!=0&&rc!=10&&rc!=20)throw runtime_error("bad probe status");
        cout<<fixed<<setprecision(7)<<"R197_PILOT mode="<<mode
            <<" seed="<<seed<<" window="<<w
            <<" bound="<<bound<<" status="<<state(rc)
            <<" conflicts_boundary="<<solver->redundant()
            <<" pilot_time_s="<<pilot_s<<"\n"<<flush;
        if(rc)break;
      }
    }
    if(!rc&&!deadline.terminate()){rc=solver->solve();calls++;}
    if(rc!=0&&rc!=10&&rc!=20)throw runtime_error("invalid final result");
    const double duration=chrono::duration<double>(Clock::now()-start).count();
    cout<<fixed<<setprecision(7)<<"R197_POLICY mode="<<mode
        <<" seed="<<seed<<" keep="<<keep
        <<" calls="<<calls<<" pilots="<<pilots
        <<" pilot_s="<<pilot_s
        <<" active="<<solver->active()
        <<" redundant="<<solver->redundant()
        <<" irredundant="<<solver->irredundant()
        <<" internal_time_s="<<duration<<"\n";
    cout<<"R182_STATUS status="<<state(rc)
        <<" solver_s="<<duration<<" variables="<<vars<<"\n"<<flush;
    if(rc==10){
      for(int i=1;i<=vars;i++){
        const int lit=solver->val(i);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R197_STATS_BEGIN\n"<<flush;
    solver->statistics();
    cout<<"R197_STATS_END\n"<<flush;
    solver->disconnect_terminator();
    return 0;
  }catch(const exception &e) {
    cerr<<"R197_DRIVER_FAIL "<<e.what()<<"\n";return 2;
  }
}

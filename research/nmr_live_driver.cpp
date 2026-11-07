// DRNAS New Horizon R2: interactive, in-process feedback windows.
// Observations are solver-telemetry, not a proof of periodic formula structure.
// Neither model nor driver injects learned clauses; CaDiCaL owns soundness.
#include "cadical.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;

struct Deadline final : CaDiCaL::Terminator {
  Clock::time_point start;
  double seconds;
  Deadline(Clock::time_point s,double limit):start(s),seconds(limit){}
  bool terminate() override {
    return chrono::duration<double>(Clock::now()-start).count()>=seconds;
  }
};
struct Observer final : CaDiCaL::Learner {
  long long offers=0,short3=0,small2=0,literals=0;
  bool learning(int size) override {
    ++offers; literals+=size;
    if(size<=3)++short3;
    if(size<=2)++small2;
    return false;
  }
  void learn(int) override {}
};
struct Engine {
  unique_ptr<CaDiCaL::Solver> solver;
  Observer observer;
  int n=0;
};
static void status(CaDiCaL::Solver&solver,int result,int n,
                   Clock::time_point start) {
  if(result!=0&&result!=10&&result!=20)throw runtime_error("bad result");
  cout<<fixed<<setprecision(8)
      <<"NMR_STATUS status="<<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
      <<" native_wall_s="<<chrono::duration<double>(Clock::now()-start).count()
      <<" variables="<<n<<"\n";
  if(result==10){
    for(int i=1;i<=n;++i){
      int lit=solver.val(i);
      if(lit)cout<<"v "<<lit<<" 0\n";
    }
  }
  cout<<"NMR_END\n"<<flush;
}
int main(int argc,char**argv){
  try {
    if(argc!=3)throw runtime_error("usage: CNF CAP_SECONDS");
    double cap=stod(argv[2]);
    if(cap<0.2||cap>180.0)throw runtime_error("bad wall cap");
    auto start=Clock::now();
    Deadline end(start,cap);
    Engine e[2];
    const char*names[2]={"default","sat"};
    for(int i=0;i<2;++i){
      e[i].solver=make_unique<CaDiCaL::Solver>();
      if(i==1&&!e[i].solver->configure("sat"))
        throw runtime_error("CaDiCaL SAT profile unsupported");
      const char*error=e[i].solver->read_dimacs(argv[1],e[i].n,1);
      if(error)throw runtime_error(error);
      e[i].solver->connect_terminator(&end);
      e[i].solver->connect_learner(&e[i].observer);
    }
    if(e[0].n!=e[1].n)throw runtime_error("input mismatch");
    cout<<"NMR_READY variables="<<e[0].n<<"\n"<<flush;
    string command;
    int steps=0;
    while(getline(cin,command)){
      if(command.rfind("STEP ",0)==0){
        int which=-1,conflicts=0;
        if(sscanf(command.c_str(),"STEP %d %d",&which,&conflicts)!=2
             ||which<0||which>1||conflicts<16||conflicts>8192
             ||steps>=48)throw runtime_error("invalid feedback step");
        auto &s=*e[which].solver;
        auto &o=e[which].observer;
        const long long a=o.offers,b=o.short3,c=o.small2,d=o.literals;
        auto tick=Clock::now();
        if(!s.limit("conflicts",conflicts))
          throw runtime_error("conflict limiter unsupported");
        int result=end.terminate()?0:s.solve();
        if(result!=0&&result!=10&&result!=20)
          throw runtime_error("invalid step status");
        ++steps;
        cout<<fixed<<setprecision(8)
            <<"NMR_WINDOW index="<<steps
            <<" profile="<<names[which]
            <<" conflict_budget="<<conflicts
            <<" dt_s="<<chrono::duration<double>(Clock::now()-tick).count()
            <<" offers="<<o.offers-a
            <<" short3="<<o.short3-b
            <<" small2="<<o.small2-c
            <<" literals="<<o.literals-d
            <<" active="<<s.active()
            <<" result="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
            <<"\n"<<flush;
        if(result || end.terminate()){
          status(s,result,e[which].n,start);
          return 0;
        }
      }else if(command.rfind("FINISH ",0)==0){
        int which=-1;
        if(sscanf(command.c_str(),"FINISH %d",&which)!=1||which<0||which>1)
          throw runtime_error("invalid final policy");
        auto &s=*e[which].solver;
        s.disconnect_learner();
        // Loser work is counted. Winner keeps ALL its learned clauses.
        const int loser=1-which;
        e[loser].solver->disconnect_learner();
        e[loser].solver->disconnect_terminator();
        e[loser].solver.reset();
        int result=end.terminate()?0:s.solve();
        status(s,result,e[which].n,start);
        s.disconnect_terminator();
        return 0;
      }else throw runtime_error("unknown NMR command");
    }
    throw runtime_error("controller disconnected");
  }catch(const exception&x){
    cerr<<"NMR_DRIVER_FAIL "<<x.what()<<"\n";
    return 2;
  }
}

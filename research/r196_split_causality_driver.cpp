// DRNAS R196 — causal dissection of CaDiCaL split256 speedups.
// CaDiCaL 2.1 fixed commit 31f9aae; original CNF, no solver modifications.
// DO NOT treat this as a novel CDCL algorithm. Modes isolate: (1) setting
// a conflict limit; (2) stopping/re-entering solve(); (3) preserved state;
// (4) stop timing / number; (5) statistics instrumentation cost.
#include "cadical.hpp"
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;
struct Deadline final:CaDiCaL::Terminator {
  Clock::time_point start;
  double cap;
  Deadline(Clock::time_point t,double c):start(t),cap(c){}
  bool terminate()override{
    return chrono::duration<double>(Clock::now()-start).count()>=cap;
  }
};
static unique_ptr<CaDiCaL::Solver> fresh(const string &path,int seed,
                                         Deadline &deadline,int &n) {
  auto s=make_unique<CaDiCaL::Solver>();
  if(!s->set("seed",seed))throw runtime_error("solver refused seed");
  const char *error=s->read_dimacs(path.c_str(),n,1);
  if(error)throw runtime_error(error);
  s->connect_terminator(&deadline);
  return s;
}
static string status_name(int x) {
  return x==10?"SAT":x==20?"UNSAT":x==0?"TIMEOUT":"INVALID";
}
static void dump(CaDiCaL::Solver &s,const string &stage){
  // Diagnostics only; a whole statistics snapshot may perturb execution.
  cout<<"R196_STATS_BEGIN stage="<<stage<<"\n"<<flush;
  s.statistics();
  cout<<"R196_STATS_END stage="<<stage<<"\n"<<flush;
}
int main(int argc,char**argv){
  try{
    if(argc!=5)throw runtime_error("usage CNF CAP MODE SEED");
    string cnf=argv[1], mode=argv[3];
    double cap=stod(argv[2]);
    int seed=stoi(argv[4]);
    if(!std::isfinite(cap)||cap<1||cap>120||seed<0||seed>1000000)
      throw runtime_error("invalid R196 cap or seed");
    if(mode!="default"&&mode!="limit_cancel"&&
       mode!="split128_twice"&&mode!="split256"&&
       mode!="split512"&&mode!="split256_rebuild"&&
       mode!="split256_trace")
      throw runtime_error("R196 unknown mode");
    auto begin=Clock::now();
    Deadline limit(begin,cap);
    int n=0,rc=0;
    auto sol=fresh(cnf,seed,limit,n);
    bool preserve=true;
    int calls=0,budget=0;
    double pilot_seconds=0, rebuild_seconds=0;
    int probe_status=0;
    if(mode=="limit_cancel"){
      // Control: manipulate exactly the same limit API but do not
      // interrupt a solve call. Negative conflict limit = unbounded.
      if(!sol->limit("conflicts",256)||!sol->limit("conflicts",-1))
        throw runtime_error("CaDiCaL limit-cancel unsupported");
      budget=256;
    }
    if(mode=="split128_twice"||mode=="split256"||mode=="split512"||
       mode=="split256_rebuild"||mode=="split256_trace"){
      const int windows=mode=="split128_twice"?2:1;
      budget=mode=="split512"?512:mode=="split128_twice"?128:256;
      for(int k=0;k<windows&&!limit.terminate();k++){
        auto start=Clock::now();
        if(!sol->limit("conflicts",budget))
          throw runtime_error("conflict limit unsupported");
        probe_status=sol->solve();
        pilot_seconds+=chrono::duration<double>(Clock::now()-start).count();
        calls++;
        if(probe_status!=0&&probe_status!=10&&probe_status!=20)
          throw runtime_error("invalid pilot solver status");
        cout<<fixed<<setprecision(7)
            <<"R196_PILOT window="<<k<<" bound="<<budget
            <<" status="<<status_name(probe_status)
            <<" time_s="<<chrono::duration<double>(Clock::now()-start).count()
            <<" active="<<sol->active()
            <<" redundant="<<sol->redundant()
            <<" irredundant="<<sol->irredundant()<<"\n"<<flush;
        if(mode=="split256_trace"){
          dump(*sol,"after_pilot");
        }
        if(probe_status){rc=probe_status;break;}
      }
      if(mode=="split256_rebuild"&&rc==0&&!limit.terminate()){
        // Deliberate loss of all learned clauses AND all other internal
        // solver state. Compared to split256, not an isolated clause ablation.
        auto t=Clock::now();
        sol->disconnect_terminator();
        sol.reset();
        int nn=0;
        sol=fresh(cnf,seed,limit,nn);
        if(nn!=n)throw runtime_error("source dimension changed on rebuild");
        preserve=false;
        rebuild_seconds=chrono::duration<double>(Clock::now()-t).count();
      }
    }
    if(rc==0&&!limit.terminate()){
      calls++;
      rc=sol->solve();
    }
    if(rc!=0&&rc!=10&&rc!=20)throw runtime_error("invalid solver outcome");
    const double elapsed=chrono::duration<double>(Clock::now()-begin).count();
    cout<<fixed<<setprecision(7)
        <<"R196_POLICY mode="<<mode
        <<" seed="<<seed<<" windows="<<calls
        <<" bound="<<budget<<" preserved="<<(preserve?1:0)
        <<" pilot_s="<<pilot_seconds
        <<" rebuild_s="<<rebuild_seconds
        <<" active_final="<<sol->active()
        <<" redundant_final="<<sol->redundant()
        <<" irredundant_final="<<sol->irredundant()
        <<" native_elapsed_s="<<elapsed<<"\n";
    cout<<"R182_STATUS status="<<status_name(rc)
        <<" solver_s="<<elapsed<<" variables="<<n<<"\n"<<flush;
    if(rc==10){
      for(int i=1;i<=n;i++){
        int lit=sol->val(i);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    // Final native statistics are diagnostic. The Python wall-clock
    // measurement also charges this output, the process and witness check.
    dump(*sol,"final");
    sol->disconnect_terminator();
    return 0;
  }catch(const exception &e){
    cerr<<"R196_DRIVER_FAIL "<<e.what()<<"\n";return 2;
  }
}

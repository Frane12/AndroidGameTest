// DRNAS R193 — dual live CDCL race, fixed first 2x128 conflict probes.
// Both candidates are instantiated from exactly the same original CNF.
// Each keeps its learned clauses; selected instance continues IN PROCESS.
// Pilot phases run sequentially and alternate order, to avoid CPU contention.
// Probe overhead, loading both candidates, and loser work are ALL wall charged.
// CaDiCaL 2.1 exact commit pinned in CI; learner callback counts offers,
// not full CDCL proof clauses, LBD or true propagations.
#include "cadical.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <array>
using namespace std;
using Clock=chrono::steady_clock;
struct Deadline final : CaDiCaL::Terminator {
  Clock::time_point start;
  double cap;
  Deadline(Clock::time_point s,double c):start(s),cap(c){}
  bool terminate()override{
    return chrono::duration<double>(Clock::now()-start).count()>=cap;
  }
};
struct Offer final : CaDiCaL::Learner {
  long long count=0,short3=0,binary=0,lits=0;
  bool learning(int size)override{
    ++count;lits+=size;
    if(size<=3)++short3;
    if(size<=2)++binary;
    return false;
  }
  void learn(int)override{}
};
struct Progress {
  double window_seconds[2]={0,0};
  long long offers[2]={0,0},short3[2]={0,0};
  int completed=0,active_first=0,active_last=0;
  double seconds()const{return window_seconds[0]+window_seconds[1];}
  long long total_short()const{return short3[0]+short3[1];}
  long long total_offers()const{return offers[0]+offers[1];}
};
static unique_ptr<CaDiCaL::Solver> new_solver(
    const string&filename,const string&profile,int &n){
  auto s=make_unique<CaDiCaL::Solver>();
  if(profile=="sat" && !s->configure("sat"))
    throw runtime_error("CaDiCaL SAT profile unsupported");
  const char*err=s->read_dimacs(filename.c_str(),n,1);
  if(err)throw runtime_error(err);
  return s;
}
int main(int argc,char **argv){
  try{
    if(argc!=5)
      throw runtime_error("usage CNF CAP_SECONDS MODE COUNTERBALANCE_0_OR_1");
    const string filename=argv[1],mode=argv[3];
    const int parity=stoi(argv[4]);
    const bool dual=mode.rfind("dual_",0)==0;
    if(mode!="default" && mode!="sat" &&
       mode!="dual_fast" && mode!="dual_learning" &&
       mode!="dual_keep_default" && mode!="dual_keep_sat")
      throw runtime_error("bad R193 mode");
    if(parity!=0&&parity!=1)throw runtime_error("bad parity");
    double cap=stod(argv[2]);
    if(cap<0.12||cap>120)throw runtime_error("bad cap");
    const auto start=Clock::now();
    Deadline end(start,cap);
    array<unique_ptr<CaDiCaL::Solver>,2> solvers;
    array<Offer,2> observed;
    array<Progress,2> progress;
    int dims[2]={0,0}, selected=0,result=0;
    const string profiles[2]={"default","sat"};
    solvers[0]=new_solver(filename,mode=="sat"?"sat":"default",dims[0]);
    solvers[0]->connect_terminator(&end);
    if(dual) {
      // Replace baseline candidate with default if this is a dual mode.
      solvers[1]=new_solver(filename,"sat",dims[1]);
      if(dims[0]!=dims[1])throw runtime_error("dual source mismatch");
      solvers[1]->connect_terminator(&end);
      for(int i=0;i<2;i++){
        solvers[i]->connect_learner(&observed[i]);
        progress[i].active_first=solvers[i]->active();
      }
      bool done=false;
      for(int window=0;window<2 && !done;window++){
        for(int pass=0;pass<2 && !done;pass++){
          const int i=(parity+window+pass)%2;
          if(end.terminate()){done=true;break;}
          long long last_offers=observed[i].count;
          long long last_short=observed[i].short3;
          auto tick=Clock::now();
          if(!solvers[i]->limit("conflicts",128))
            throw runtime_error("no conflicts limiter");
          int code=solvers[i]->solve();
          if(code!=0&&code!=10&&code!=20)
            throw runtime_error("invalid dual candidate outcome");
          auto &s=progress[i];
          s.window_seconds[window]=chrono::duration<double>(
                         Clock::now()-tick).count();
          s.offers[window]=observed[i].count-last_offers;
          s.short3[window]=observed[i].short3-last_short;
          s.completed++;
          s.active_last=solvers[i]->active();
          cout<<fixed<<setprecision(7)
              <<"R193_PILOT profile="<<profiles[i]
              <<" window="<<window
              <<" elapsed_s="<<s.window_seconds[window]
              <<" offers="<<s.offers[window]
              <<" short3="<<s.short3[window]
              <<" active_after="<<s.active_last
              <<" status="<<(code==10?"SAT":code==20?"UNSAT":"UNKNOWN")
              <<"\n"<<flush;
          if(code!=0){selected=i;result=code;done=true;}
        }
      }
      string policy_reason="pilot_solved";
      if(result==0){
        const double t0=progress[0].seconds();
        const double t1=progress[1].seconds();
        if(mode=="dual_keep_default"){
          selected=0;policy_reason="fixed_default_control";
        }else if(mode=="dual_keep_sat"){
          selected=1;policy_reason="fixed_sat_control";
        }else if(progress[0].completed==2&&progress[1].completed==2){
          // Preregistered policies; no outcome labels or instance identity.
          if(mode=="dual_fast"){
            // Fixed equal conflict budgets: faster completed windows => higher rate.
            if(t0>1e-7 && t1>1e-7 && t1<=0.90*t0){
              selected=1;policy_reason="sat_10pct_faster_pilot";
            }else{
              selected=0;policy_reason="conservative_default";
            }
          }else if(mode=="dual_learning"){
            // Relative offered short-clause yield per second, with margin.
            const double score0=(progress[0].total_short()+1.0)/
                                     (t0+0.001);
            const double score1=(progress[1].total_short()+1.0)/
                                     (t1+0.001);
            if(score1>=1.25*score0){
              selected=1;policy_reason="sat_short_yield_25pct";
            }else{
              selected=0;policy_reason="conservative_default";
            }
          }
        }else{
          selected=0;policy_reason="incomplete_probe_fallback_default";
        }
      }
      cout<<"R193_DUAL choice="<<profiles[selected]
          <<" reason="<<policy_reason
          <<" pilot_default_s="<<fixed<<setprecision(7)
              <<progress[0].seconds()
          <<" pilot_sat_s="<<progress[1].seconds()
          <<" offers_default="<<progress[0].total_offers()
          <<" offers_sat="<<progress[1].total_offers()
          <<" short_default="<<progress[0].total_short()
          <<" short_sat="<<progress[1].total_short()
          <<" completed_default="<<progress[0].completed
          <<" completed_sat="<<progress[1].completed
          <<" preserved=1\n"<<flush;
      for(int i=0;i<2;i++)solvers[i]->disconnect_learner();
      // Destroy losing candidate, retaining learned clauses in the winner.
      const int losing=1-selected;
      solvers[losing]->disconnect_terminator();
      solvers[losing].reset();
      if(result==0&&!end.terminate())
        result=solvers[selected]->solve();  // SAME surviving solver.
    }else{
      selected=0;
      if(!end.terminate())result=solvers[0]->solve();
    }
    solvers[selected]->disconnect_terminator();
    const double elapsed=chrono::duration<double>(Clock::now()-start).count();
    if(result!=0&&result!=10&&result!=20)
      throw runtime_error("unexpected result");
    cout<<fixed<<setprecision(7)
        <<"R182_STATUS status="<<(result==10?"SAT":
                                      result==20?"UNSAT":"TIMEOUT")
        <<" solver_s="<<elapsed<<" variables="<<dims[0]<<"\n";
    if(result==10){
      for(int v=1;v<=dims[0];v++){
        int lit=solvers[selected]->val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    solvers[selected]->statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  }catch(const exception&e){
    cerr<<"R193_DRIVER_FAIL "<<e.what()<<"\n";return 2;
  }
}

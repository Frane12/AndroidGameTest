// DRNAS New Horizon SAT R6: in-process default/UNSAT CaDiCaL dual-live.
// Original CNF is identical for both solvers. All parse, pilot and loser
// time is included in a single wall clock. The selected *same live solver*
// continues without restart. No source changes and no access to true labels.
//
// Source of solver algorithm: CaDiCaL 2.1 commit pinned in GitHub CI.
// This is strategy selection across EXISTING solver configs, not new CDCL.
#include "cadical.hpp"
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;

struct Deadline final : CaDiCaL::Terminator {
  Clock::time_point begin;
  double cap;
  Deadline(Clock::time_point s,double c):begin(s),cap(c){}
  bool terminate() override {
    return chrono::duration<double>(Clock::now()-begin).count()>=cap;
  }
};
struct Offers final : CaDiCaL::Learner {
  long long total=0,short3=0;
  bool learning(int size) override {
    ++total;
    if(size<=3) ++short3;
    return false; // observe only; never inject clauses
  }
  void learn(int) override {}
};
struct Measurement {
  double time_s=0.0;
  long long offers=0,short3=0;
  int windows=0;
};
static unique_ptr<CaDiCaL::Solver> init(const string &path,
                                        const string &profile,int &n) {
  auto solver=make_unique<CaDiCaL::Solver>();
  if(profile=="unsat" && !solver->configure("unsat"))
    throw runtime_error("UNSAT profile refused by solver");
  const char*err=solver->read_dimacs(path.c_str(),n,1);
  if(err)throw runtime_error(err);
  return solver;
}
static const char*profile(int i){return i==0?"default":"unsat";}
static const char*label(int code){return code==10?"SAT":code==20?"UNSAT":"UNKNOWN";}
int main(int argc,char **argv) {
  try{
    if(argc!=5)
      throw runtime_error("usage original.cnf CAP_SECONDS MODE PILOT_ORDER_0_OR_1");
    const string input=argv[1],mode=argv[3];
    double cap=stod(argv[2]);
    int order=stoi(argv[4]);
    if(order!=0&&order!=1)throw runtime_error("invalid order");
    if(!std::isfinite(cap)||cap<0.2||cap>120)
      throw runtime_error("invalid wall-clock cap");
    const bool dual=(mode.rfind("dual_",0)==0);
    if(mode!="default"&&mode!="unsat"&&
       mode!="dual_keep_default"&&mode!="dual_keep_unsat"&&
       mode!="dual_fast"&&mode!="dual_learning"&&mode!="dual_interleave")
      throw runtime_error("invalid mode");
    const auto begin=Clock::now();
    Deadline deadline(begin,cap);
    array<unique_ptr<CaDiCaL::Solver>,2> candidates;
    array<Offers,2> observations;
    array<Measurement,2> metrics;
    int n[2]={0,0};
    int chosen=(mode=="unsat")?1:0;
    int result=0;
    string why="fixed_native_profile";
    if(dual){
      // Parse original CNF twice. No policy has access to filename/class labels.
      candidates[0]=init(input,"default",n[0]);
      candidates[1]=init(input,"unsat",n[1]);
      if(n[0]!=n[1])throw runtime_error("original CNF dimensions changed");
      for(int i=0;i<2;i++){
        candidates[i]->connect_terminator(&deadline);
        candidates[i]->connect_learner(&observations[i]);
      }
      bool ended=false;
      // Two rounds of bounded conflicts, counterbalanced by caller.
      // Same source/ordering, both candidates preserve internal state.
      for(int round=0;round<2&&!ended;round++){
        for(int j=0;j<2&&!ended;j++){
          int i=(order+round+j)%2;
          if(deadline.terminate()){ended=true;break;}
          const auto prev_total=observations[i].total;
          const auto prev_short=observations[i].short3;
          auto tick=Clock::now();
          if(!candidates[i]->limit("conflicts",128))
            throw runtime_error("CaDiCaL refused bounded conflicts");
          const int code=candidates[i]->solve();
          if(code!=0&&code!=10&&code!=20)throw runtime_error("bad pilot result");
          double seconds=chrono::duration<double>(Clock::now()-tick).count();
          metrics[i].time_s+=seconds;
          metrics[i].offers+=observations[i].total-prev_total;
          metrics[i].short3+=observations[i].short3-prev_short;
          metrics[i].windows++;
          cout<<fixed<<setprecision(7)
              <<"NH_R6_PILOT profile="<<profile(i)
              <<" round="<<round
              <<" time_s="<<seconds
              <<" offers="<<observations[i].total-prev_total
              <<" short3="<<observations[i].short3-prev_short
              <<" status="<<label(code)
              <<"\n"<<flush;
          if(code!=0){
            chosen=i;result=code;why="pilot_decided";
            ended=true;
          }
        }
      }
      if(result==0){
        if(mode=="dual_keep_unsat"){chosen=1;why="fixed_unsat_control";}
        else if(mode=="dual_keep_default"){chosen=0;why="fixed_default_control";}
        else if(mode=="dual_interleave"){chosen=0;why="bounded_round_robin";}
        else if(metrics[0].windows==2&&metrics[1].windows==2){
          if(mode=="dual_fast" && metrics[0].time_s>1e-7 &&
             metrics[1].time_s<=0.85*metrics[0].time_s){
            chosen=1;why="unsat_probe_15pct_faster";
          }else if(mode=="dual_learning"){
            const double base=(metrics[0].short3+1.0)/(metrics[0].time_s+0.001);
            const double candidate=(metrics[1].short3+1.0)/
                                             (metrics[1].time_s+0.001);
            if(candidate>=1.30*base){
              chosen=1;why="unsat_30pct_short_offer_gain";
            }else{chosen=0;why="conservative_default";}
          }else{chosen=0;why="conservative_default";}
        }else{chosen=0;why="insufficient_pilot_default";}
      }
      if(mode=="dual_interleave" && result==0) {
        // Causal control: keep BOTH live after pilot and alternate
        // bounded search windows until one conclusively solves.
        // This uses additional CPU; all is wall-charged.
        int turn=0;
        while(!deadline.terminate()&&result==0){
          const int i=(order+turn)%2;
          if(!candidates[i]->limit("conflicts",4096))
            throw runtime_error("interleave conflict limit failed");
          const int code=candidates[i]->solve();
          if(code!=0&&code!=10&&code!=20)
            throw runtime_error("bad interleave candidate result");
          if(code!=0){chosen=i;result=code;why="interleave_first_solved";}
          ++turn;
        }
      }
      cout<<fixed<<setprecision(7)
          <<"NH_R6_DUAL selected="<<profile(chosen)
          <<" reason="<<why
          <<" default_pilot_s="<<metrics[0].time_s
          <<" unsat_pilot_s="<<metrics[1].time_s
          <<" offers_default="<<metrics[0].offers
          <<" offers_unsat="<<metrics[1].offers
          <<" short_default="<<metrics[0].short3
          <<" short_unsat="<<metrics[1].short3
          <<" windows_default="<<metrics[0].windows
          <<" windows_unsat="<<metrics[1].windows
          <<" preserved=1"
          <<" source_original=1\n"<<flush;
      for(int i=0;i<2;i++)candidates[i]->disconnect_learner();
      if(result==0 && mode!="dual_interleave" && !deadline.terminate()){
        // Destroy the losing candidate; continue selected state in place.
        const int loser=1-chosen;
        candidates[loser]->disconnect_terminator();
        candidates[loser].reset();
        result=candidates[chosen]->solve();
      }
      if(candidates[1-chosen]){
        candidates[1-chosen]->disconnect_terminator();
        candidates[1-chosen].reset();
      }
    }else{
      candidates[chosen]=init(input,profile(chosen),n[chosen]);
      candidates[chosen]->connect_terminator(&deadline);
      if(!deadline.terminate())
        result=candidates[chosen]->solve();
    }
    candidates[chosen]->disconnect_terminator();
    const double elapsed=chrono::duration<double>(Clock::now()-begin).count();
    if(result!=0 && result!=10 && result!=20)throw runtime_error("bad final result");
    cout<<fixed<<setprecision(7)
        <<"R182_STATUS status="<<label(result)
        <<" solver_s="<<elapsed
        <<" variables="<<n[chosen]<<"\n";
    cout<<"NH_R6_MODE "<<mode<<" profile="<<profile(chosen)<<"\n";
    if(result==10){
      for(int v=1;v<=n[chosen];v++){
        const int lit=candidates[chosen]->val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    candidates[chosen]->statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  }catch(const exception &e){
    cerr<<"NH_R6_DRIVER_FAIL "<<e.what()<<"\n";
    return 2;
  }
}

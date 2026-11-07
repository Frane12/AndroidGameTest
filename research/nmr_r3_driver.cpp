// DRNAS NMR R3 - lazy competing expert, feedback windows on retained CDCL state.
// Each action is initiated by the controller. SAT configuration is only loaded
// after ACTIVATE. No approximate neural inference can add logical clauses.
#include "cadical.hpp"
#include <chrono>
#include <cstdio>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;
struct Deadline : CaDiCaL::Terminator {
  Clock::time_point start;
  double seconds;
  const bool *callback_pending=nullptr;
  Deadline(Clock::time_point s,double n):start(s),seconds(n){}
  bool terminate() override {
    return chrono::duration<double>(Clock::now()-start).count()>=seconds ||
           (callback_pending&&*callback_pending);
  }
};
struct Observer : CaDiCaL::Learner {
  long long offers=0,short3=0,small2=0,literals=0;
  long long callback_checks=0,callback_events=0;
  int window_offers=0,window_short=0,previous_short=-1;
  bool watch_armed=false,callback_pending=false;
  void begin_watch(){
    window_offers=window_short=0;
    previous_short=-1;
    callback_pending=false;
    watch_armed=true;
  }
  void end_watch(){watch_armed=false;callback_pending=false;}
  bool learning(int n) override {
    ++offers; literals+=n; if(n<=3)++short3; if(n<=2)++small2;
    // O(1) event aggregation; NO neural inference inside callback.
    if(watch_armed && !callback_pending){
      ++window_offers;
      if(n<=3)++window_short;
      if(window_offers==64){
        ++callback_checks;
        if(previous_short>=0 &&
           (window_short-previous_short>=24 ||
            previous_short-window_short>=24)){
          callback_pending=true;
          ++callback_events;
        }
        previous_short=window_short;
        window_offers=window_short=0;
      }
    }
    return false; // Observe only; never export guessed clauses.
  }
  void learn(int) override {}
};
struct Agent {
  unique_ptr<CaDiCaL::Solver> s;
  Observer o;
  int n=0,steps=0;
};
int main(int argc,char**argv){
  try {
    if(argc!=3)throw runtime_error("usage CNF CAP_SECONDS");
    const string cnf=argv[1];
    double cap=stod(argv[2]);
    if(cap<0.2||cap>120)throw runtime_error("cap out of bounds");
    auto start=Clock::now();
    Deadline deadline(start,cap);
    Agent agents[2];
    auto open=[&](int i){
      auto &a=agents[i];
      a.s=make_unique<CaDiCaL::Solver>();
      if(i==1&&!a.s->configure("sat"))
        throw runtime_error("SAT expert config refused");
      const char*err=a.s->read_dimacs(cnf.c_str(),a.n,1);
      if(err)throw runtime_error(err);
      if(i==1&&a.n!=agents[0].n)throw runtime_error("dim mismatch");
      a.s->connect_terminator(&deadline);
      a.s->connect_learner(&a.o);
    };
    open(0);
    cout<<"NMR3_READY n="<<agents[0].n<<"\n"<<flush;
    string command;
    int count=0;
    auto finish=[&](int arm,int result) {
      auto &a=agents[arm];
      if(result!=10&&result!=20&&result!=0)
        throw runtime_error("bad final result");
      cout<<fixed<<setprecision(8)<<"NMR3_STATUS status="
          <<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
          <<" arm="<<arm
          <<" wall_s="<<chrono::duration<double>(Clock::now()-start).count()
          <<"\n";
      if(result==10)
        for(int i=1;i<=a.n;i++){int v=a.s->val(i);if(v)cout<<"v "<<v<<" 0\n";}
      cout<<"NMR3_END\n"<<flush;
    };
    while(getline(cin,command)){
      if(command=="ACTIVATE"){
        if(agents[1].s)throw runtime_error("double activation");
        if(deadline.terminate())throw runtime_error("activation after deadline");
        open(1);
        cout<<"NMR3_ACTIVATED n="<<agents[1].n<<"\n"<<flush;
      }else if(command.rfind("STEP ",0)==0 || command.rfind("WATCH ",0)==0){
        int arm=-1,budget=-1;
        const bool watch=command.rfind("WATCH ",0)==0;
        if(sscanf(command.c_str(),watch?"WATCH %d %d":"STEP %d %d",&arm,&budget)!=2 ||
           arm<0||arm>1||budget<32||budget>16384 || ++count>32 ||
           !agents[arm].s)
          throw runtime_error("invalid step");
        auto &a=agents[arm];
        long long before[4]={a.o.offers,a.o.short3,a.o.small2,a.o.literals};
        long long before_cb=a.o.callback_events;
        long long before_checks=a.o.callback_checks;
        auto begin=Clock::now();
        if(!a.s->limit("conflicts",budget))
          throw runtime_error("unsupported conflict limit");
        if(watch){
          a.o.begin_watch();
          deadline.callback_pending=&a.o.callback_pending;
        }
        int result=deadline.terminate()?0:a.s->solve();
        const bool callback_requested=a.o.callback_pending;
        deadline.callback_pending=nullptr;
        a.o.end_watch();
        if(result!=0&&result!=10&&result!=20)
          throw runtime_error("invalid code");
        a.steps++;
        cout<<fixed<<setprecision(8)
            <<"NMR3_WINDOW arm="<<arm
            <<" conflict_budget="<<budget
            <<" dt_s="<<chrono::duration<double>(Clock::now()-begin).count()
            <<" offers="<<a.o.offers-before[0]
            <<" short3="<<a.o.short3-before[1]
            <<" small2="<<a.o.small2-before[2]
            <<" literals="<<a.o.literals-before[3]
            <<" active="<<a.s->active()
            <<" callback_checks="<<a.o.callback_checks-before_checks
            <<" callback_events="<<a.o.callback_events-before_cb
            <<" wakeup="<<(callback_requested?"callback":watch?"budget":"manual")
            <<" result="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
            <<"\n"<<flush;
        if(result!=0||deadline.terminate()) {
          finish(arm,result);
          return 0;
        }
      }else if(command.rfind("FINISH ",0)==0){
        int arm=-1;
        if(sscanf(command.c_str(),"FINISH %d",&arm)!=1||arm<0||
           arm>1||!agents[arm].s)throw runtime_error("bad final arm");
        int loser=1-arm;
        if(agents[loser].s) {
          agents[loser].s->disconnect_learner();
          agents[loser].s->disconnect_terminator();
          agents[loser].s.reset();
        }
        agents[arm].s->disconnect_learner();
        int result=deadline.terminate()?0:agents[arm].s->solve();
        finish(arm,result);
        agents[arm].s->disconnect_terminator();
        return 0;
      }else throw runtime_error("unknown command");
    }
    throw runtime_error("controller disconnected without FINISH");
  }catch(const exception&e){
    cerr<<"NMR3_DRIVER_FAIL "<<e.what()<<"\n";
    return 2;
  }
}

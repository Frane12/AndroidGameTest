// DRNAS R192: frozen three-window CDCL trajectory ablation, CaDiCaL 2.1.
// 3x128-conflict probes on SAME solver; conditional RESTART is explicitly
// a new solver and loses learned clauses. Every stage charges wall clock.
// IPASIR learner gives learned-clause LENGTH, not LBD or propagations.
#include "cadical.hpp"
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;

struct Deadline : CaDiCaL::Terminator {
  Clock::time_point start;
  double cap;
  explicit Deadline(Clock::time_point t,double seconds):start(t),cap(seconds){}
  bool terminate()override{
    return chrono::duration<double>(Clock::now()-start).count()>=cap;
  }
};
struct Learned : CaDiCaL::Learner{
  long long count=0,short3=0,binary=0,literals=0;
  bool learning(int size)override{
    ++count;literals+=size;
    if(size<=3)++short3;
    if(size<=2)++binary;
    return false;
  }
  void learn(int)override{}
};
struct Win{
  long long learned=0,short3=0,binary=0,literals=0;
  double seconds=0;
  int active_before=0,active_after=0,result=0;
};
static double rate(long long a,long long b){
  return b>0?double(a)/double(b):0;
}
static bool choose_sat(const vector<Win>&w,string&reason){
  if(w.size()!=3){reason="insufficient_windows";return false;}
  const Win&a=w.front(),&b=w.back();
  // Fixed pre-registration: two signs of worsening learning efficiency.
  // Do not consult formula labels, expectations, witness, or prior scores.
  const bool enough=(a.learned>=20&&b.learned>=20);
  const bool fewer_short=rate(b.short3,b.learned)<
                         0.65*rate(a.short3,a.learned);
  const bool slower=(b.seconds>=1.25*a.seconds);
  const bool longer=rate(b.literals,b.learned)>
                     1.25*rate(a.literals,a.learned);
  const bool change=enough&&fewer_short&&slower&&longer;
  reason=change?"deteriorating_short_clause_yield":"conservative_continue";
  return change;
}
static unique_ptr<CaDiCaL::Solver> load(const string&path,
                                        const string&profile,int &n){
  auto solver=make_unique<CaDiCaL::Solver>();
  if(profile=="sat"&&!solver->configure("sat"))
    throw runtime_error("CaDiCaL SAT profile refused");
  const char *error=solver->read_dimacs(path.c_str(),n,1);
  if(error)throw runtime_error(error);
  return solver;
}
int main(int argc,char **argv){
  try{
    if(argc!=4)throw runtime_error("usage CNF CAP_SECONDS MODE");
    string path=argv[1],mode=argv[3];
    if(mode!="default"&&mode!="sat"&&mode!="windows_continue"&&
       mode!="windows_shadow"&&mode!="windows_restart_sat"&&
       mode!="windows_restart_default"&&mode!="windows_adaptive")
      throw runtime_error("unrecognized mode");
    double cap=stod(argv[2]);
    if(cap<0.12||cap>120)throw runtime_error("bad cap");
    const auto start=Clock::now();
    Deadline end(start,cap);
    const bool measured=mode.rfind("windows_",0)==0;
    const string profile=(mode=="sat")?"sat":"default";
    int n=0;
    auto solver=load(path,profile,n);
    solver->connect_terminator(&end);
    Learned learned;
    if(measured)solver->connect_learner(&learned);
    vector<Win>windows;
    int result=0;
    bool restarted=false;string decision="no_windows";
    if(!measured)result=solver->solve();
    else {
      for(int index=0;index<3;index++){
        const auto t=Clock::now();
        const long long prev_count=learned.count;
        const long long prev_short=learned.short3;
        const long long prev_binary=learned.binary;
        const long long prev_lits=learned.literals;
        const int active_before=solver->active();
        if(!solver->limit("conflicts",128))
          throw runtime_error("conflict windows unsupported");
        result=solver->solve();
        Win x;
        x.learned=learned.count-prev_count;
        x.short3=learned.short3-prev_short;
        x.binary=learned.binary-prev_binary;
        x.literals=learned.literals-prev_lits;
        x.seconds=chrono::duration<double>(Clock::now()-t).count();
        x.active_before=active_before;
        x.active_after=solver->active();
        x.result=result;
        windows.push_back(x);
        cout<<fixed<<setprecision(7)<<"R192_WINDOW"
            <<" index="<<index
            <<" status="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
            <<" seconds="<<x.seconds
            <<" learned="<<x.learned
            <<" short3="<<x.short3
            <<" binary="<<x.binary
            <<" mean_len="<<rate(x.literals,x.learned)
            <<" active_before="<<x.active_before
            <<" active_after="<<x.active_after
            <<"\n"<<flush;
        if(result!=0||end.terminate())break;
      }
      string suggested;
      bool recommended=choose_sat(windows,suggested);
      if(mode=="windows_shadow")
        decision="shadow_"+suggested;
      else if(mode=="windows_adaptive")
        decision=suggested;
      else decision="control_"+mode;
      if(result==0&&!end.terminate()){
        bool restart_sat=mode=="windows_restart_sat"||
                         (mode=="windows_adaptive"&&recommended);
        bool restart_default=mode=="windows_restart_default";
        if(restart_sat||restart_default){
          // Explicit destructive restart; never pretend learned clauses survived.
          solver->disconnect_learner();
          solver->disconnect_terminator();
          solver.reset();
          int new_n=0;
          solver=load(path,restart_sat?"sat":"default",new_n);
          if(new_n!=n)throw runtime_error("restart dimension mismatch");
          restarted=true;
          solver->connect_terminator(&end);
        }else{
          solver->disconnect_learner();
        }
        if(!end.terminate())result=solver->solve();
      }else{
        solver->disconnect_learner();
      }
    }
    solver->disconnect_terminator();
    const double elapsed=chrono::duration<double>(Clock::now()-start).count();
    if(result!=0&&result!=10&&result!=20)
      throw runtime_error("invalid SAT solver status");
    cout<<"R192_POLICY suggested="
        <<((mode=="windows_adaptive"&&decision=="deteriorating_short_clause_yield")?
           "sat":decision)
        <<" restarted="<<(restarted?1:0)
        <<" windows="<<windows.size()<<"\n";
    cout<<fixed<<setprecision(7)<<"R182_STATUS status="
        <<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
        <<" solver_s="<<elapsed<<" variables="<<n<<"\n";
    if(result==10){
      for(int v=1;v<=n;v++){
        int lit=solver->val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    solver->statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  }catch(const exception &e){
    cerr<<"R192_DRIVER_FAIL "<<e.what()<<"\n";
    return 2;
  }
}

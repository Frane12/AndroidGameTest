// DRNAS R195: causal optimized dual-keep on original SAT Competition CNFs.
// Same pinned CaDiCaL 2.1 code and predeclared seeds on all seven arms.
// Probe costs, second CNF import and loser work are included in wall time.
// Probes preserve their owning solver's learned clauses, except the loser.
#include "cadical.hpp"
#include <array>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
using namespace std;
using Clock=chrono::steady_clock;
struct Deadline:CaDiCaL::Terminator{
  Clock::time_point t;double cap;
  Deadline(Clock::time_point x,double c):t(x),cap(c){}
  bool terminate()override{
    return chrono::duration<double>(Clock::now()-t).count()>=cap;
  }
};
struct Learning:CaDiCaL::Learner{
  long long offers=0,short3=0;
  bool learning(int len)override{offers++;if(len<=3)short3++;return false;}
  void learn(int)override{}
};
static unique_ptr<CaDiCaL::Solver> build(const string &path,bool sat,int seed,int &vars){
  auto out=make_unique<CaDiCaL::Solver>();
  if(sat && !out->configure("sat"))throw runtime_error("SAT profile rejected");
  if(!out->set("seed",seed))throw runtime_error("seed option rejected");
  const char*error=out->read_dimacs(path.c_str(),vars,1);
  if(error)throw runtime_error(error);
  return out;
}
static pair<long long,long long> dimacs_header(const string &path){
  ifstream f(path);if(!f)throw runtime_error("missing CNF");
  string line,extra;
  long long n=0,m=0;
  while(getline(f,line)){
    if(line.size()>0&&line[0]=='p'){
      istringstream in(line);string p,cnf;
      if(!(in>>p>>cnf>>n>>m)||p!="p"||cnf!="cnf"||n<1||m<1)
        throw runtime_error("invalid CNF header");
      return {n,m};
    }
  }
  throw runtime_error("DIMACS header absent");
}
int main(int argc,char**argv){
  try{
    if(argc!=6)throw runtime_error("usage CNF CAP MODE ORDER SEED");
    const string cnf=argv[1],mode=argv[3];
    double cap=stod(argv[2]);int order=stoi(argv[4]),seed=stoi(argv[5]);
    if(cap<1||cap>180||order<0||order>1||seed<0||seed>1000000)
      throw runtime_error("bad budget/order/seed");
    if(mode!="default"&&mode!="sat"&&mode!="split128"&&mode!="split256"&&
       mode!="dual_keep_default"&&mode!="dual_keep_sat"&&
       mode!="dual_keep_guarded")
      throw runtime_error("invalid R195 mode");
    const auto start=Clock::now();
    Deadline deadline(start,cap);
    auto [declared_n,declared_m]=dimacs_header(cnf);
    // Predeclared guard, source header only, NEVER expected answer/family/ID.
    // On very small instances, avoid paying for a second solver and use SAT.
    const bool guard=(mode=="dual_keep_guarded") &&
                     (declared_n<400||declared_m<1200);
    const bool dual=mode.rfind("dual_",0)==0&&!guard;
    int n=0,n2=0,result=0,sel=0;
    array<unique_ptr<CaDiCaL::Solver>,2> s;
    array<Learning,2> learning;
    array<double,2> pilot_s{0,0};
    const bool sat_first=(mode=="sat"||guard);
    s[0]=build(cnf,sat_first,seed,n);
    s[0]->connect_terminator(&deadline);
    string choice=sat_first?"sat":"default";
    string reason=guard?"small_source_guard":"baseline";
    int windows=0;
    if(dual){
      s[1]=build(cnf,true,seed,n2);
      if(n!=n2)throw runtime_error("two source dimensions differ");
      s[1]->connect_terminator(&deadline);
      for(int i=0;i<2;i++)s[i]->connect_learner(&learning[i]);
      bool done=false;
      for(int w=0;w<2&&!done;w++){
        for(int pass=0;pass<2&&!done;pass++){
          int i=(order+w+pass)%2;
          if(deadline.terminate()){done=true;break;}
          auto tick=Clock::now();
          if(!s[i]->limit("conflicts",128))throw runtime_error("pilot limit unsupported");
          const int status=s[i]->solve();
          if(status!=0&&status!=10&&status!=20)
            throw runtime_error("bad pilot status");
          double took=chrono::duration<double>(Clock::now()-tick).count();
          pilot_s[i]+=took;windows++;
          cout<<fixed<<setprecision(7)<<"R195_PILOT profile="<<(i?"sat":"default")
              <<" window="<<w<<" seconds="<<took
              <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
              <<" offers="<<learning[i].offers<<" short3="<<learning[i].short3
              <<"\n"<<flush;
          if(status){sel=i;result=status;reason="pilot_terminal";done=true;}
        }
      }
      if(!result){
        sel=mode=="dual_keep_sat"?1:0;
        reason=sel?"fixed_sat_after_dual":"fixed_default_after_dual";
      }
      choice=sel?"sat":"default";
      for(int i=0;i<2;i++)s[i]->disconnect_learner();
      int losing=1-sel;
      s[losing]->disconnect_terminator();
      s[losing].reset();
      if(result==0&&!deadline.terminate())result=s[sel]->solve();
    }else if(mode=="split128"||mode=="split256"){
      const int rounds=(mode=="split128"?2:1);
      const int budget=(mode=="split128"?128:256);
      for(int w=0;w<rounds;w++){
        if(deadline.terminate())break;
        auto tick=Clock::now();
        if(!s[0]->limit("conflicts",budget))
          throw runtime_error("split probe limit unsupported");
        result=s[0]->solve();
        pilot_s[0]+=chrono::duration<double>(Clock::now()-tick).count();
        windows++;
        if(result)break;
      }
      reason="single_solver_split_control";
      if(!result&&!deadline.terminate())result=s[0]->solve();
    }else{
      if(!deadline.terminate())result=s[0]->solve();
    }
    s[sel]->disconnect_terminator();
    if(result!=0&&result!=10&&result!=20)
      throw runtime_error("invalid result code");
    double seconds=chrono::duration<double>(Clock::now()-start).count();
    cout<<fixed<<setprecision(7)<<"R195_POLICY choice="<<choice
        <<" reason="<<reason<<" actual_dual="<<(dual?1:0)
        <<" pilot_s="<<(pilot_s[0]+pilot_s[1])<<" windows="<<windows
        <<" declared_vars="<<declared_n<<" declared_clauses="<<declared_m
        <<" learned_preserved="<<(dual||mode=="split128"||mode=="split256"?1:0)
        <<"\n";
    cout<<"R182_STATUS status="<<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
        <<" solver_s="<<seconds<<" variables="<<n<<"\n";
    if(result==10){
      for(int i=1;i<=n;i++){
        int lit=s[sel]->val(i);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    }
    cout<<"R185_STATS_BEGIN\n"<<flush;
    s[sel]->statistics();
    cout<<"R185_STATS_END\n"<<flush;
    return 0;
  }catch(const exception&e){
    cerr<<"R195_FAIL "<<e.what()<<"\n";return 2;
  }
}

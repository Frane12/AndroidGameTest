// DRNAS SEARCH2 -- native patched CaDiCaL 3.0.1 driver.
// Changes INITIAL internal VMTF/EVSIDS activities, not DIMACS variables.
// Output is standard SAT/UNSAT plus original-variable SAT model and
// independent search metrics even for TIMEOUT. No proof is invented.
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
struct Stop final:CaDiCaL::Terminator {
  Clock::time_point start;double limit;
  explicit Stop(double cap):start(Clock::now()),limit(cap){}
  bool terminate()override{
    return chrono::duration<double>(Clock::now()-start).count()>=limit;
  }
};
static void check(bool ok,const string& reason) {
  if(!ok)throw runtime_error("SEARCH2_DRIVER_FAIL_CLOSED "+reason);
}
static vector<int> load_rank(const string &path,int n) {
  ifstream in(path);check(bool(in),"open rank map");
  string p,perm;int gotn=0;
  in>>p>>perm>>gotn;
  check(p=="p"&&perm=="perm"&&gotn==n,"rank map header");
  vector<int> ranks(n+1,-1);vector<unsigned char> used(n+1,0);
  for(int i=1;i<=n;i++){
    int old=0,rank=0;check(bool(in>>old>>rank),"incomplete rank map");
    check(old==i && rank>=1 && rank<=n && !used[rank],
          "not a bijective rank map");
    used[rank]=1;ranks[old]=rank;
  }
  string extra;check(!(in>>extra),"trailing rank data");
  vector<pair<int,int>> ordered;
  for(int v=1;v<=n;v++)ordered.emplace_back(-ranks[v],v);
  sort(ordered.begin(),ordered.end()); // low priority first (large rank)
  vector<int> out;out.reserve(n);
  for(const auto& x:ordered)out.push_back(x.second);
  return out;
}
int main(int argc,char**argv){
  try{
    check(argc==4,"usage: search2_cadical source_original.cnf rank_file_or_NONE solver_cap_s");
    double cap=stod(argv[3]);
    check(cap>=.15 && cap<=20.0,"invalid solver cap");
    CaDiCaL::Solver solver;
    solver.set("quiet",1);
    int vars=0;
    const char* error=solver.read_dimacs(argv[1],vars,1);
    check(!error,error?error:"parse");
    int seeded=0;
    if(string(argv[2])!="NONE"){
      auto low_to_high=load_rank(argv[2],vars);
      solver.drnas_seed_initial_order(low_to_high);
      seeded=int(low_to_high.size());
    }
    Stop stop(cap);solver.connect_terminator(&stop);
    auto start=Clock::now();
    int res=solver.solve();
    const auto duration=chrono::duration<double>(Clock::now()-start).count();
    solver.disconnect_terminator();
    check(res==0||res==10||res==20,"bad CDCL verdict");
    auto stats=solver.drnas_search2_telemetry();
    cout<<fixed<<setprecision(8);
    cout<<"SEARCH2_METRICS {\"status\":\""<<(res==10?"SAT":res==20?"UNSAT":"TIMEOUT")
        <<"\",\"solver_wall_s\":"<<duration
        <<",\"conflicts\":"<<stats.conflicts
        <<",\"decisions\":"<<stats.decisions
        <<",\"search_propagations\":"<<stats.search_propagations
        <<",\"search_plus_probe_propagations\":"<<stats.total_propagations
        <<",\"initial_internal_priority_seed_count\":"<<seeded
        <<",\"source_is_original_DIMACS\":true}\n";
    if(res==10) {
      cout<<"s SATISFIABLE\n";
      for(int v=1;v<=vars;v++){
        const int lit=solver.val(v);
        if(lit)cout<<"v "<<lit<<" 0\n";
      }
    } else if(res==20)cout<<"s UNSATISFIABLE\n";
    else cout<<"s UNKNOWN\n";
    cout.flush();
    return res==10?10:res==20?20:0;
  }catch(const exception &e){cerr<<e.what()<<"\n";return 78;}
}

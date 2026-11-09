// DRNAS X17: genuine one-way, in-process learned clause transfer between
// two independent incremental CaDiCaL engines (same original DIMACS).
// Scout -> leader ONLY; the scout result is never credited as an asym-arm win.
// All imports originate from CaDiCaL's learned-clause callback; NO assumptions.
// Nonzero clauses of length <=3 are transferred at explicit solve boundaries.
// Do not claim LRAT certification from this interface alone.
#include <cadical.hpp>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <climits>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <memory>
#include <pthread.h>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
using Time=Clock::time_point;
static void need(bool x,const string& m){if(!x)throw runtime_error("X17_FAIL_CLOSED "+m);}
struct CNF{int vars=0;vector<vector<int>> clauses;};
static CNF load(const string& path){
 ifstream in(path);need(bool(in),"missing DIMACS");CNF cnf;
 string tok;int declared=-1;vector<int> current;
 while(in>>tok){
  if(tok=="c"){string line;getline(in,line);continue;}
  if(tok=="%")break;
  if(tok=="p"){
   string format;need(declared<0 && bool(in>>format>>cnf.vars>>declared),"invalid DIMACS header");
   need(format=="cnf" && cnf.vars>0 && cnf.vars<=2000000 && declared>=0 && declared<=10000000,"DIMACS range");continue;
  }
  need(declared>=0,"literal before header");
  size_t end=0;long lit=stol(tok,&end);need(end==tok.size() && lit>=INT_MIN+1 && lit<=INT_MAX,"invalid DIMACS literal");
  if(!lit){cnf.clauses.push_back(move(current));current.clear();}
  else {need(abs(int(lit))<=cnf.vars,"DIMACS literal out of range");current.push_back(int(lit));}
 }
 need(declared>=0 && current.empty() && int(cnf.clauses.size())==declared,"CNF count incomplete");
 return cnf;
}
static void load_into(CaDiCaL::Solver& s,const CNF& f){
 for(const auto& c:f.clauses){for(int l:c)s.add(l);s.add(0);}
}
static void pin(int cpu){
 cpu_set_t mask;CPU_ZERO(&mask);need(cpu>=0 && cpu<CPU_SETSIZE,"cpu beyond affinity range");CPU_SET(cpu,&mask);
 need(pthread_setaffinity_np(pthread_self(),sizeof(mask),&mask)==0,"pthread affinity failed");
 cpu_set_t got;CPU_ZERO(&got);need(pthread_getaffinity_np(pthread_self(),sizeof(got),&got)==0 &&
      CPU_ISSET(cpu,&got) && CPU_COUNT(&got)==1,"thread cpu affinity not exclusive");
}
struct Stop:CaDiCaL::Terminator{
 Time window,global;atomic<bool>& requested;
 Stop(Time w,Time g,atomic<bool>& r):window(w),global(g),requested(r){}
 bool terminate()override {return requested.load(memory_order_relaxed)||Clock::now()>=window||Clock::now()>=global;}
};
struct Export:CaDiCaL::Learner{
 mutex mu;vector<vector<int>> pending;vector<int> cur;
 int exported=0,discarded=0,limit=3;
 bool learning(int size)override{return size>=1 && size<=limit;}
 void learn(int lit)override{
  if(lit){cur.push_back(lit);return;}
  if(!cur.empty()){
   lock_guard<mutex> g(mu);
   if(pending.size()<512 && exported<4096){pending.push_back(move(cur));++exported;}
   else ++discarded;
  }
  cur.clear();
 }
 vector<vector<int>> drain(){lock_guard<mutex> g(mu);vector<vector<int>> ret;ret.swap(pending);return ret;}
};
static string clause_key(const vector<int>& c){
 string out;for(int l:c){out+=to_string(l);out.push_back(',');}return out;
}
int main(int argc,char**argv){
 try{
  need(argc==7,"usage: DRIVER ORIGINAL.cnf ARM SEED CAP_S LEADER_CPU SCOUT_CPU");
  string path=argv[1],arm=argv[2];
  need(arm=="cadical1"||arm=="placebo2"||arm=="asym2"||arm=="asym3"||arm=="asym1", "unknown arm");
  int seed=stoi(argv[3]);double cap=stod(argv[4]);int leadercpu=stoi(argv[5]),scoutcpu=stoi(argv[6]);
  need(seed>0 && cap>0.2 && cap<=30 && leadercpu>=0 && scoutcpu>=0,"invalid arguments");
  const bool solo=arm=="cadical1";
  const bool onecpu=arm=="asym1"||solo;
  const bool share=arm=="asym2"||arm=="asym3"||arm=="asym1";
  const int max_width=(arm=="asym2"?2:3);
  const Time begin=Clock::now();const Time deadline=begin+chrono::duration_cast<Clock::duration>(chrono::duration<double>(cap));
  const CNF cnf=load(path);
  CaDiCaL::Solver leader;need(leader.set("seed",seed),"CaDiCaL seed unavailable");
  load_into(leader,cnf);
  Export exported;exported.limit=3;
  atomic<bool> stop{false};atomic<int> scout_status{0};
  unique_ptr<CaDiCaL::Solver> scout;
  if(!solo){
   scout.reset(new CaDiCaL::Solver());
   int alt=(seed^0x35c789ab)&INT_MAX;if(alt==0)alt=1;
   need(scout->set("seed",alt),"CaDiCaL scout seed unavailable");
   load_into(*scout,cnf);
   scout->connect_learner(&exported);
  }
  int imported=0,rejected=0,windows=0,leader_status=0;
  vector<int> model;unordered_set<string> seen;
  thread worker;
  if(!solo){
   worker=thread([&](){
    try{
     pin(onecpu?leadercpu:scoutcpu);
     Stop term(deadline,deadline,stop);scout->connect_terminator(&term);
     int st=scout->solve();scout_status.store(st);
     scout->disconnect_terminator();
    }catch(...){scout_status.store(-1);stop.store(true);}
   });
  }
  pin(leadercpu);
  while(Clock::now()<deadline && !stop.load()){
   ++windows;
   Time window=min(deadline,Clock::now()+chrono::milliseconds(150));
   Stop term(window,deadline,stop);leader.connect_terminator(&term);
   int st=leader.solve();leader.disconnect_terminator();
   if(st==10||st==20){leader_status=st;break;}
   need(st==0,"unknown leader status");
   auto candidates=exported.drain();
   // Identical callback / queue mechanics for placebo, with import disabled.
   if(!share)continue;
   stable_sort(candidates.begin(),candidates.end(),[](const auto& a,const auto& b){return a.size()<b.size();});
   int this_round=0;
   for(auto& c:candidates){
    if(int(c.size())>max_width || imported>=128 || this_round>=16){++rejected;continue;}
    sort(c.begin(),c.end());c.erase(unique(c.begin(),c.end()),c.end());
    bool valid=!c.empty();
    for(int lit:c){if(abs(lit)>cnf.vars||binary_search(c.begin(),c.end(),-lit)) {valid=false;break;}}
    if(!valid || !seen.insert(clause_key(c)).second){++rejected;continue;}
    // Exported clauses are logical consequences of the EXACT original CNF,
    // learned by the scout with NO assumptions or foreign clauses.
    for(int lit:c)leader.add(lit);
    leader.add(0);
    ++imported;++this_round;
   }
  }
  if(leader_status==10){
   model.reserve(cnf.vars);
   for(int v=1;v<=cnf.vars;v++){
    int assignment=leader.val(v);
    // The Python audit verifies EVERY original clause independently.
    model.push_back(assignment>0?v:-v);
   }
  }
  stop.store(true);
  if(worker.joinable())worker.join();
  if(scout){scout->disconnect_learner();}
  need(scout_status.load()!=-1,"scout thread failed");
  string status=leader_status==10?"SAT":leader_status==20?"UNSAT":"TIMEOUT";
  cout<<"X17_RESULT arm="<<arm<<" status="<<status<<" imported="<<imported
      <<" exported="<<exported.exported<<" rejected="<<rejected
      <<" dropped="<<exported.discarded<<" windows="<<windows
      <<" scout_status="<<scout_status.load()<<" scout_cpu="<<(onecpu?leadercpu:scoutcpu)
      <<" leader_cpu="<<leadercpu<<"\n";
  if(leader_status==10){
   for(size_t i=0;i<model.size();i+=32){cout<<"v ";for(size_t j=i;j<min(model.size(),i+32);j++)cout<<model[j]<<" ";cout<<"0\n";}
  }
  return 0;
 }catch(const exception& e){cerr<<e.what()<<"\n";return 2;}
}
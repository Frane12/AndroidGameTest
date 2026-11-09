// DRNAS DMD5-Ablation: independently proved ANF lemma counterfactual and real CDCL instrumentation.
// CaDiCaL 2.1.0 IPASIR-UP ExternalPropagator assignments/backtracks.
// Learned local ANF lemmas are never asserted via callback: active variants
// explicitly add independently locally proved clauses before solving.
// An observed unit opportunity is NOT a proof of a new CDCL implication.
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
using Clause=vector<int>;
struct Formula {int n=0;vector<Clause> cs;};
static Formula read_cnf(const string& p){
 ifstream f(p);if(!f)throw runtime_error("cannot open CNF");
 Formula z;string line;int declared=-1;Clause cur;
 while(getline(f,line)){
  istringstream ss(line);string first;if(!(ss>>first)||first=="c")continue;
  if(first=="%")break;
  if(first=="p"){
   string fmt;ss>>fmt>>z.n>>declared;
   if(fmt!="cnf"||z.n<1||z.n>150000||declared<0||declared>160000)
    throw runtime_error("bad header");
   continue;
  }
  if(declared<0)throw runtime_error("missing header");
  istringstream s(line);int lit;
  while(s>>lit){
   if(lit==0){z.cs.push_back(cur);cur.clear();}
   else {if(abs(lit)>z.n)throw runtime_error("bad literal");cur.push_back(lit);}
  }
 }
 if(declared<0||!cur.empty()||(int)z.cs.size()!=declared)
  throw runtime_error("clause count mismatch");
 return z;
}
class Watch final : public CaDiCaL::ExternalPropagator {
 public:
 vector<Clause> candidates;
 vector<signed char> assigns;
 vector<int> trail;
 vector<size_t> marks;
 vector<int> status;
 vector<bool> touched;
 long observed_assignments=0,backtracks=0,unit_events=0,conflict_events=0;
 long first_unit_at=-1,first_conflict_at=-1;
 int first_unit_depth=-1,first_conflict_depth=-1;
 long max_depth=0;
 long first_100=0,first_1000=0;
 bool violation=false;
 chrono::steady_clock::time_point t0=Clock::now();
 double first_unit_s=-1.,first_conflict_s=-1.;
 Watch(int n,vector<Clause> c):candidates(std::move(c)),assigns(n+1,0),
     status(candidates.size(),0),touched(candidates.size(),false){}
 int state(const Clause& c)const{
  bool sat=false;int unknown=0;
  for(int l:c){
    int v=assigns[abs(l)];if(v==0){unknown++;continue;}
    if(v==(l>0?1:-1)){sat=true;break;}
  }
  if(sat)return 0;
  return unknown==0?2:unknown==1?1:0;
 }
 void scan(bool count) {
   for(size_t i=0;i<candidates.size();i++){
    int s=state(candidates[i]);
    if(count && s!=status[i] && s>0){
      if(s==1){
       ++unit_events;
       if(observed_assignments<=100)++first_100;
       if(observed_assignments<=1000)++first_1000;
       touched[i]=true;
       if(first_unit_at<0){
         first_unit_at=observed_assignments;
         first_unit_depth=(int)marks.size();
         first_unit_s=chrono::duration<double>(Clock::now()-t0).count();
       }
      }else{
       ++conflict_events;
       if(first_conflict_at<0){
         first_conflict_at=observed_assignments;
         first_conflict_depth=(int)marks.size();
         first_conflict_s=chrono::duration<double>(Clock::now()-t0).count();
       }
      }
    }
    status[i]=s;
   }
 }
 void notify_assignment(const vector<int>& lits) override {
   for(int lit:lits){
    int v=abs(lit);
    if(v<1||v>=(int)assigns.size()){violation=true;continue;}
    signed char val=lit>0?1:-1;
    if(assigns[v]==val)continue;
    if(assigns[v]!=0){violation=true;continue;}
    assigns[v]=val;trail.push_back(lit);
    ++observed_assignments;scan(true);
   }
 }
 void notify_new_decision_level() override {
   marks.push_back(trail.size());
   max_depth=max(max_depth,(long)marks.size());
 }
 void notify_backtrack(size_t level) override {
   ++backtracks;
   if(level>marks.size()){violation=true;return;}
   while(marks.size()>level){
     size_t start=marks.back();marks.pop_back();
     while(trail.size()>start){
       int lit=trail.back();trail.pop_back();
       assigns[abs(lit)]=0;
     }
   }
   scan(false);
 }
 bool cb_check_found_model(const vector<int>&) override{return true;}
 int cb_propagate() override{return 0;}
 bool cb_has_external_clause(bool& forgettable)override{
   forgettable=true;return false;
 }
 int cb_add_external_clause_lit()override{return 0;}
 int touched_count()const{
  return (int)count(touched.begin(),touched.end(),true);
 }
};
class Timer final : public CaDiCaL::Terminator {
 Clock::time_point deadline;
 public:
 explicit Timer(double cap):deadline(Clock::now()+chrono::duration_cast<Clock::duration>(chrono::duration<double>(cap))){}
 bool terminate()override{return Clock::now()>=deadline;}
};
static void check_model(CaDiCaL::Solver& s,const Formula& f){
 for(const auto &c:f.cs){
  bool sat=false;
  for(int lit:c){
   int v=s.val(abs(lit));
   if(v && (v>0)==(lit>0)){sat=true;break;}
  }
  if(!sat)throw runtime_error("SAT model fails ORIGINAL CNF");
 }
}
static void selftest(){
 vector<Clause> clauses={{1,2,3}};
 Watch w(3,clauses);
 w.notify_new_decision_level();
 w.notify_assignment({-1});
 if(w.unit_events!=0)throw runtime_error("premature unit");
 w.notify_assignment({-2});
 if(w.unit_events!=1||w.first_unit_at!=2||w.first_unit_depth!=1)
  throw runtime_error("missing live unit");
 w.notify_backtrack(0);
 if(w.assigns[1]!=0||w.assigns[2]!=0)throw runtime_error("backtrack failed");
 w.notify_new_decision_level();
 w.notify_assignment({-1,-2});
 if(w.unit_events!=2)throw runtime_error("trail reactivation failed");
 cout<<"DMD5_TRAIL_SELFTEST_PASS {\"unit_events\":2,\"backtracked\":true}\n";
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
  if(argc!=5)throw runtime_error(
    "usage: dmd3test_live original.cnf candidate_lemmas.cnf clean|clauses_only|observer_control|shadow|gate_active|all_active CAP_S");
  string src=argv[1],cand=argv[2],mode=argv[3];
  // Documented signature: binary original candidates mode cap.
  if(mode!="clean"&&mode!="clauses_only"&&mode!="observer_control"&&mode!="shadow"&&mode!="gate_active"&&mode!="all_active")
   throw runtime_error("bad mode");
  double cap=stod(argv[4]);
  if(cap<0.2||cap>120)throw runtime_error("bad cap");
  Formula original=read_cnf(src);
  Formula annotated=read_cnf(cand);
  if(annotated.n!=original.n||annotated.cs.size()<original.cs.size()||
    !equal(original.cs.begin(),original.cs.end(),annotated.cs.begin()))
   throw runtime_error("original prefix changed");
  vector<Clause> lemmas(annotated.cs.begin()+original.cs.size(),annotated.cs.end());
  if(lemmas.size()>24)throw runtime_error("unbounded candidate set");
  CaDiCaL::Solver solver;
  for(const auto& c:original.cs){for(int l:c)solver.add(l);solver.add(0);}
  if(mode=="gate_active"||mode=="all_active"||mode=="clauses_only"){
    for(const auto& c:lemmas){for(int l:c)solver.add(l);solver.add(0);}
  }
  Watch observer(original.n,mode=="observer_control"?vector<Clause>{}:lemmas);
  if(mode!="clean"&&mode!="clauses_only"&&!lemmas.empty()){
    solver.connect_external_propagator(&observer);
    set<int> vars;
    for(const auto& c:lemmas)for(int l:c)vars.insert(abs(l));
    // The observer-only placebo watches exactly the same variable set
    // as the matching shadow/active gate arms but never scans lemmas.
    for(int v:vars)solver.add_observed_var(v);
  }
  Timer terminator(cap);
  solver.connect_terminator(&terminator);
  observer.t0=Clock::now();
  auto begin=Clock::now();
  int result=solver.solve();
  double elapsed=chrono::duration<double>(Clock::now()-begin).count();
  solver.disconnect_terminator();
  if(result!=0&&result!=10&&result!=20)
   throw runtime_error("unknown CaDiCaL solver exit");
  if(result==10)check_model(solver,original);
  if(observer.violation)throw runtime_error("invalid external trail callback");
  if(result==10){
    cout<<"v ";int n=0;
    for(int i=1;i<=original.n;i++){
      int val=solver.val(i);
      if(val)cout<<(val>0?i:-i)<<" ";
      if(++n==32){cout<<"0\nv ";n=0;}
    }
    cout<<"0\n";
  }
  cout<<fixed<<setprecision(6);
  cout<<"DMD5_RESULT {\"mode\":\""<<mode
      <<"\",\"status\":\""<<(result==10?"SAT":result==20?"UNSAT":"TIMEOUT")
      <<"\",\"solver_s\":"<<elapsed
      <<",\"candidate_lemmas\":"<<lemmas.size()
      <<",\"observed_assignments\":"<<observer.observed_assignments
      <<",\"backtracks\":"<<observer.backtracks
      <<",\"live_unit_opportunities\":"<<observer.unit_events
      <<",\"live_clause_falsifications\":"<<observer.conflict_events
      <<",\"unique_lemmas_activated\":"<<observer.touched_count()
      <<",\"first_unit_assignment_index\":"<<observer.first_unit_at
      <<",\"first_unit_depth\":"<<observer.first_unit_depth
      <<",\"first_unit_elapsed_s\":"<<observer.first_unit_s
      <<",\"first_unit_in_first_100\":"<<observer.first_100
      <<",\"first_unit_in_first_1000\":"<<observer.first_1000
      <<",\"max_depth\":"<<observer.max_depth
      <<",\"model_original_verified\":"<<(result==10?"true":"false")
      <<",\"callback_error\":"<<(observer.violation?"true":"false")<<"}\n"<<flush;
  cout<<"DMD5_STATS_BEGIN mode="<<mode<<"\n"<<flush;
  solver.statistics();
  cout<<"DMD5_STATS_END mode="<<mode<<"\n"<<flush;
  return result;
 }catch(const exception& e){
  cerr<<"DMD5_FAIL_CLOSED "<<e.what()<<"\n";return 2;
 }
}

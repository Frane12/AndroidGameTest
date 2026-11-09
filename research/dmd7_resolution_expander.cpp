// DRNAS DMD7 -- bounded proof-first binary/ternary original-clause resolution.
// Each candidate cites TWO unmodified original CNF clause indices and a pivot.
// A separate Python replayer independently checks the resolution step and
// exhaustively checks every assignment over the <=5 involved variables.
// No candidate is a SAT/UNSAT proof; no learned clause is accepted unchecked.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
using Clause=vector<int>;
struct Timeout:runtime_error{Timeout():runtime_error("budget"){}};
struct Timer {
 Clock::time_point end;
 explicit Timer(int ms):end(Clock::now()+chrono::milliseconds(ms)){}
 void check()const {if(Clock::now()>=end)throw Timeout();}
};
struct Formula {int n=0;vector<Clause> cs;};
static void need(bool ok,const string& msg){if(!ok)throw runtime_error(msg);}
static Formula readcnf(const string& path,const Timer& t){
 ifstream in(path);
 need(bool(in),"source DIMACS missing");
 string line;Formula f;int declared=-1;Clause cur;
 while(getline(in,line)){
  if((f.cs.size()&1023)==0)t.check();
  istringstream s(line);
  string first;if(!(s>>first)||first=="c")continue;
  if(first=="%")break;
  if(first=="p"){
   string type;int n,m;s>>type>>n>>m;
   need(type=="cnf"&&n>0&&n<=250000&&m>=0&&m<=500000&&declared==-1,
        "bad DIMACS header");
   f.n=n;declared=m;continue;
  }
  need(declared>=0,"DIMACS missing header");
  istringstream values(line);
  int v;
  while(values>>v){
   if(v==0){need(f.cs.size()<size_t(declared),"too many clauses");f.cs.push_back(cur);cur.clear();}
   else {need(v!=INT32_MIN&&abs(v)<=f.n,"bad literal");cur.push_back(v);}
  }
 }
 need(declared>=0&&cur.empty()&&f.cs.size()==size_t(declared),"DIMACS incomplete");
 return f;
}
static Clause norm(Clause c) {
 sort(c.begin(),c.end(),[](int a,int b){return abs(a)==abs(b)?a<b:abs(a)<abs(b);});
 c.erase(unique(c.begin(),c.end()),c.end());
 return c;
}
static bool tautology(const Clause& c) {
 for(size_t i=1;i<c.size();i++)if(c[i]==-c[i-1])return true;
 return false;
}
static string arr(const vector<int>& x){
 ostringstream s;s<<'[';
 for(size_t i=0;i<x.size();i++){if(i)s<<',';s<<x[i];}
 s<<']';return s.str();
}
struct Candidate{Clause clause;int a,b,pivot,score;};
struct Result{
 vector<Candidate> chosen;
 int checks=0,vars=0,pool=0,original_bin=0,original_ternary=0;
 bool exhausted=false;
};
static Result expand(const Formula& f,const Timer& t){
 Result r;vector<array<vector<int>,2>> occurrences(f.n+1);
 vector<int> literal_frequency(2*f.n+2,0);
 set<Clause> existing,found;
 for(size_t id=0;id<f.cs.size();id++){
  if((id&511)==0)t.check();
  const auto& c=f.cs[id];
  if(c.size()==2)r.original_bin++;
  if(c.size()==3)r.original_ternary++;
  if(c.empty()||c.size()>3)continue;
  Clause n=norm(c);if(tautology(n))continue;
  existing.insert(n);
  for(int lit:n){
   auto& occ=occurrences[abs(lit)][lit>0?0:1];
   if(occ.size()<18)occ.push_back(int(id));
   literal_frequency[2*abs(lit)+(lit<0)]++;
  }
 }
 vector<int> pivots;
 for(int v=1;v<=f.n;v++)if(!occurrences[v][0].empty()&&!occurrences[v][1].empty())
    pivots.push_back(v);
 stable_sort(pivots.begin(),pivots.end(),[&](int x,int y){
  int ax=min(occurrences[x][0].size(),occurrences[x][1].size());
  int ay=min(occurrences[y][0].size(),occurrences[y][1].size());
  return ax!=ay?ax>ay:x<y;
 });
 vector<Candidate> pool;
 for(int v:pivots){
  if(r.vars>=384||r.checks>=16000||pool.size()>=512)break;
  t.check();r.vars++;
  int local=0;
  for(int a:occurrences[v][0]){
   if(local>=10||r.checks>=16000||pool.size()>=512)break;
   for(int b:occurrences[v][1]){
    if(local>=10||r.checks>=16000||pool.size()>=512)break;
    if((r.checks++&255)==0)t.check();
    Clause out;
    for(int l:f.cs[a])if(l!=v)out.push_back(l);
    for(int l:f.cs[b])if(l!=-v)out.push_back(l);
    out=norm(move(out));
    if(out.empty()||out.size()>3||tautology(out))continue;
    if(existing.count(out)||!found.insert(out).second)continue;
    // SOURCE-ONLY rank: shorter clauses, fewer parent source clauses,
    // higher occurrence of their literals. No benchmark labels or outcomes.
    int occ_score=0;
    for(int lit:out)occ_score+=min(8,literal_frequency[2*abs(lit)+(lit<0)]);
    int score=(out.size()==2?200:(out.size()==1?250:100))
       +min(40,occ_score)*2
       -(int(f.cs[a].size()+f.cs[b].size())-4)*4;
    pool.push_back({move(out),a,b,v,score});local++;
   }
  }
 }
 stable_sort(pool.begin(),pool.end(),[](const Candidate& a,const Candidate& b){
  if(a.score!=b.score)return a.score>b.score;
  if(a.clause.size()!=b.clause.size())return a.clause.size()<b.clause.size();
  if(a.a!=b.a)return a.a<b.a;
  if(a.b!=b.b)return a.b<b.b;
  return a.clause<b.clause;
 });
 r.pool=int(pool.size());
 // Keep a proof-bounded diversity roster: at most 48 sound clauses.
 set<int> unique_pivots;
 for(const auto& c:pool){
  if(r.chosen.size()>=48)break;
  if(unique_pivots.size()<12||unique_pivots.count(c.pivot)||r.chosen.size()<8){
   r.chosen.push_back(c);
   unique_pivots.insert(c.pivot);
  }
 }
 return r;
}
static bool holds(const Clause& clause,const map<int,bool>& assignment){
 for(int l:clause){
  auto it=assignment.find(abs(l));
  if(it!=assignment.end()&&it->second==(l>0))return true;
 }
 return false;
}
static void selftest(){
 Timer t(3000);Formula f;f.n=5;
 f.cs={{-1,2},{-2,3},{1,4,5},{-1,-4},{-3,5}};
 auto r=expand(f,t);
 need(!r.chosen.empty(),"no resolvents found");
 bool has_path=false,has_ternary=false;
 for(const auto& c:r.chosen){
  if(c.clause==norm({-1,3}))has_path=true;
  if(c.clause.size()==3)has_ternary=true;
  vector<int> vars;
  for(int lit:f.cs[c.a])vars.push_back(abs(lit));
  for(int lit:f.cs[c.b])vars.push_back(abs(lit));
  sort(vars.begin(),vars.end());vars.erase(unique(vars.begin(),vars.end()),vars.end());
  need(vars.size()<=5,"too many source variables");
  for(int mask=0;mask<(1<<int(vars.size()));mask++){
   map<int,bool> state;
   for(size_t j=0;j<vars.size();j++)state[vars[j]]=bool(mask&(1<<j));
   need(!holds(f.cs[c.a],state)||!holds(f.cs[c.b],state)||holds(c.clause,state),
        "local resolvent not entailed");
  }
 }
 need(has_path&&has_ternary,"did not cover binary paths and ternary resolution");
 cout<<"DMD7_SELFTEST_PASS {\"binary_path_resolvent\":true,"
       "\"ternary_resolvent\":true,\"independent_truth_tables\":true,"
       "\"candidates\":"<<r.chosen.size()<<"}\n";
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
  need(argc==4,"usage: dmd7_expand ORIGINAL.cnf OUT_CERT.json BUDGET_MS");
  int budget=stoi(argv[3]);need(budget>=10&&budget<=1000,"bad budget");
  Timer t(budget);
  bool abstain=false;
  Result result;Formula src;
  try{
   need(filesystem::file_size(argv[1])<=12ull*1024*1024,"source too large");
   src=readcnf(argv[1],t);
   result=expand(src,t);
  }catch(const Timeout&){abstain=true;result=Result{};}
  catch(const exception& e){
   if(string(e.what())=="source too large"){abstain=true;result=Result{};}
   else throw;
  }
  ostringstream out;
  out<<"{\"protocol\":\"DMD7-RESOLUTION-SOURCE-PAIR-v1\","
     <<"\"abstained\":"<<(abstain?"true":"false")
     <<",\"source_vars\":"<<src.n
     <<",\"source_clauses\":"<<src.cs.size()
     <<",\"selected\":"<<result.chosen.size()
     <<",\"pool\":"<<result.pool
     <<",\"pivot_variables_scanned\":"<<result.vars
     <<",\"parent_pairs_checked\":"<<result.checks
     <<",\"original_binary\":"<<result.original_bin
     <<",\"original_ternary\":"<<result.original_ternary
     <<",\"certificates\":[";
  for(size_t i=0;i<result.chosen.size();i++){
   if(i)out<<',';
   const auto& c=result.chosen[i];
   out<<"{\"clause\":"<<arr(c.clause)
      <<",\"parent_a\":"<<c.a<<",\"parent_b\":"<<c.b
      <<",\"pivot\":"<<c.pivot
      <<",\"score\":"<<c.score<<"}";
  }
  out<<"]}";
  ofstream file(argv[2]);
  need(bool(file),"cannot save certificate");
  file<<out.str()<<"\n";
  need(bool(file),"failed writing proof");
  cout<<"DMD7_EXPAND "<<out.str()<<"\n";
  return 0;
 }catch(const exception& e){
  cerr<<"DMD7_FAIL_CLOSED "<<e.what()<<"\n";return 2;
 }
}

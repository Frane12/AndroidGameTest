// DRNAS DMD8: bounded source-only synchronous unit-propagation probe.
// The candidate CNF contains only independently proof-replayed DMD7 resolvents.
// For each candidate, SAME deterministic assumptions are tested with and without
// that candidate. We count EARLIER BCP implications at rounds 1/2 and earlier
// conflicts. This is NOT the actual CaDiCaL trail or a new logical consequence.
// The E2E benchmark measures actual solver conflicts/decisions separately.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
using Clause=vector<int>;
struct TimedOut:exception{};
struct ClockCap{
 Clock::time_point end;
 explicit ClockCap(int ms):end(Clock::now()+chrono::milliseconds(ms)){}
 void check() const {if(Clock::now()>=end)throw TimedOut();}
};
static void need(bool ok,const string& msg){if(!ok)throw runtime_error(msg);}
struct Formula {int n=0;vector<Clause> clauses;};
static Formula parse(const string& path,const ClockCap& timer){
 ifstream f(path);need(bool(f),"cannot open DIMACS");
 string line;Formula a;long expected=-1;
 Clause current;
 size_t seen_lines=0;
 while(getline(f,line)){
  if((++seen_lines&255)==0)timer.check();
  istringstream head(line);
  string word;if(!(head>>word)||word=="c")continue;
  if(word=="%")break;
  if(word=="p"){
   string tag;long n,m;
   need(bool(head>>tag>>n>>m)&&tag=="cnf"&&expected<0&&
        n>0&&n<=250000&&m>=0&&m<=500000,"bad DIMACS header");
   a.n=int(n);expected=m;
   continue;
  }
  need(expected>=0,"missing DIMACS header");
  istringstream input(line);long v=0;
  while(input>>v){
   if(v==0){
    need(a.clauses.size()<size_t(expected),"extra DIMACS clauses");
    a.clauses.push_back(move(current));current.clear();
   }else{
    need(v>=-a.n&&v<=a.n,"DIMACS literal out of range");
    current.push_back(int(v));
   }
  }
 }
 need(expected>=0&&a.clauses.size()==size_t(expected)&&current.empty(),"truncated DIMACS");
 return a;
}
struct UP {
 array<int,3> assigned{{0,0,0}};
 int first_conflict=0;  // 0 => none in first two synchronous rounds
};
static UP propagate(const Formula& source,const Clause* extra,const vector<int>& assumptions,const ClockCap& t){
 UP out;
 vector<signed char> values(source.n+1,0);
 int count=0;
 for(int lit:assumptions){
  signed char val=lit>0?1:-1;
  if(values[abs(lit)]&&values[abs(lit)]!=val){
   out.first_conflict=1;return out;
  }
  if(!values[abs(lit)]){values[abs(lit)]=val;++count;}
 }
 out.assigned[0]=count;
 for(int round=1;round<=2;round++){
  vector<int> pending;
  size_t checked=0;
  auto inspect=[&](const Clause& c)->bool {
   bool sat=false;int unknown=0,last=0;
   for(int lit:c){
     signed char v=values[abs(lit)];
     if(v==0){++unknown;last=lit;}
     else if(v==(lit>0?1:-1)){sat=true;break;}
   }
   if(sat)return true;
   if(unknown==0)return false;
   if(unknown==1)pending.push_back(last);
   return true;
  };
  for(const auto& c:source.clauses){
   if((++checked&1023)==0)t.check();
   if(!inspect(c)){out.first_conflict=round;out.assigned[round]=count;return out;}
  }
  if(extra&&!inspect(*extra)){
   out.first_conflict=round;out.assigned[round]=count;return out;
  }
  for(int lit:pending){
   int var=abs(lit);signed char val=lit>0?1:-1;
   if(values[var]&&values[var]!=val){
      out.first_conflict=round;out.assigned[round]=count;return out;
   }
   if(!values[var]){values[var]=val;++count;}
  }
  out.assigned[round]=count;
  if(pending.empty()){
   for(int rest=round+1;rest<=2;rest++)out.assigned[rest]=count;
   break;
  }
 }
 return out;
}
struct Score{
 int index=0,score=0,early_round1=0,early_round2=0;
 int earlier_conflicts=0,tests=0;
};
static vector<Score> analyze(const Formula& source,const Formula& candidate,
                            const ClockCap& t,int cap){
 need(source.n==candidate.n,"original/candidate var count mismatch");
 vector<Score> scores;
 int n=min(cap,int(candidate.clauses.size()));
 for(int i=0;i<n;i++){
  if((i&3)==0)t.check();
  const Clause& c=candidate.clauses[i];
  need(c.size()>=1&&c.size()<=3,"invalid candidate length");
  Score s;s.index=i;
  int limit=min(2,int(c.size()));
  for(int leave=0;leave<limit;leave++){
   vector<int> assumptions;
   for(size_t k=0;k<c.size();k++)
      if(int(k)!=leave)assumptions.push_back(-c[k]);
   UP base=propagate(source,nullptr,assumptions,t);
   UP added=propagate(source,&c,assumptions,t);
   // Strong candidate implies earlier contradiction under identical probes.
   bool earlier=added.first_conflict>0 &&
       (!base.first_conflict||added.first_conflict<base.first_conflict);
   int one=max(0,added.assigned[1]-base.assigned[1]);
   int two=max(0,added.assigned[2]-base.assigned[2]);
   // If either run conflicted in a round, counts after that point are
   // not comparable as final closures. Count only earlier conflict.
   if(base.first_conflict||added.first_conflict){one=0;two=0;}
   s.earlier_conflicts+=earlier;
   s.early_round1+=one;
   s.early_round2+=two;
   s.tests++;
  }
  s.score=25*s.earlier_conflicts+4*s.early_round1+s.early_round2;
  scores.push_back(s);
 }
 return scores;
}
static void print_result(const vector<Score>& scores,int count,int cap,bool abstained){
 vector<Score> positive;
 if(!abstained)for(auto s:scores)if(s.score>0)positive.push_back(s);
 sort(positive.begin(),positive.end(),[](const Score& a,const Score& b){
  if(a.score!=b.score)return a.score>b.score;
  return a.index<b.index;
 });
 cout<<"DMD8_PROBE {\"protocol\":\"DMD8-SYNC-UP-TWO-ROUND-v1\","
     <<"\"candidate_count\":"<<count
     <<",\"max_candidates\":"<<cap
     <<",\"scored\":"<<(abstained?0:scores.size())
     <<",\"abstained\":"<<(abstained?"true":"false")
     <<",\"probe_rounds\":2,\"per_candidate_max_probes\":2"
     <<",\"selected_indices\":[";
 for(size_t i=0;i<positive.size()&&i<4;i++){
  if(i)cout<<',';
  cout<<positive[i].index;
 }
 cout<<"],\"features\":[";
 if(!abstained)for(size_t i=0;i<scores.size();i++){
  if(i)cout<<',';
  auto& s=scores[i];
  cout<<"{\"index\":"<<s.index<<",\"score\":"<<s.score
      <<",\"early_round1\":"<<s.early_round1
      <<",\"early_round2\":"<<s.early_round2
      <<",\"earlier_conflicts\":"<<s.earlier_conflicts
      <<",\"probes\":"<<s.tests<<"}";
 }
 cout<<"]}\n";
}
static void selftest(){
 ClockCap t(2000);
 Formula src;src.n=4;src.clauses={{-1,2},{-2,3},{-4,1}};
 Formula c;c.n=4;c.clauses={{-1,3}};
 auto p=analyze(src,c,t,16);
 need(p.size()==1&&p[0].score>0&&p[0].early_round1>=1,
      "failed first-round shortcut detection");
 auto baseline=propagate(src,nullptr,{1},t);
 auto augmented=propagate(src,&c.clauses[0],{1},t);
 need(baseline.assigned[1]<augmented.assigned[1]&&
      baseline.assigned[2]==augmented.assigned[2],
      "source and augmented BCP final closure must agree");
 cout<<"DMD8_SELFTEST_PASS {\"early_unit_round1\":"
     <<p[0].early_round1
     <<",\"same_closure_by_round2\":true,\"probe_is_not_CDCL\":true}\n";
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
  need(argc==4,"usage: dmd8_probe ORIGINAL.cnf CANDIDATE_ONLY.cnf BUDGET_MS");
  int budget=stoi(argv[3]);need(budget>=15&&budget<=1000,"invalid budget");
  ClockCap t(budget);
  int original_count=0;
  int cand_count=0;
  bool abstained=false;
  vector<Score> scored;
  try{
   Formula f=parse(argv[1],t);
   Formula c=parse(argv[2],t);
   original_count=int(f.clauses.size());
   cand_count=int(c.clauses.size());
   scored=analyze(f,c,t,16);
  }catch(const TimedOut&){abstained=true;scored.clear();}
  print_result(scored,cand_count,16,abstained);
  return 0;
 }catch(const exception& e){cerr<<"DMD8_FAIL_CLOSED "<<e.what()<<"\n";return 2;}
}

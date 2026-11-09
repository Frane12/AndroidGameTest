#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock = chrono::steady_clock;
using Clause = vector<int>;
static constexpr int MAX_CANDIDATES=80;
static constexpr int MAX_ADDED=32;
static int ix(int lit){return 2*(abs(lit)-1)+(lit<0);}
struct Timeout:runtime_error {Timeout():runtime_error("budget"){}};
struct Timer{
  Clock::time_point start,limit;
  explicit Timer(int ms):start(Clock::now()),limit(start+chrono::milliseconds(ms)){}
  void check()const{if(Clock::now()>=limit)throw Timeout();}
  double elapsed()const{return chrono::duration<double>(Clock::now()-start).count();}
};
struct CNF{
 int n=0,declared=-1;
 vector<Clause> cs;
};
static CNF readcnf(const string &p,const Timer &tim){
 ifstream f(p);if(!f)throw runtime_error("missing original CNF");
 CNF a;string s;Clause partial;
 while(getline(f,s)){
   if((a.cs.size()&1023)==0)tim.check();
   istringstream in(s);string first;if(!(in>>first))continue;
   if(first=="c"||first=="%")continue;
   if(first=="p"){
     string type;int n,m;in>>type>>n>>m;
     if(type!="cnf"||n<0||m<0||a.declared!=-1)throw runtime_error("bad header");
     a.n=n;a.declared=m;continue;
   }
   if(a.declared<0)throw runtime_error("clauses before header");
   istringstream ints(s);int v;
   while(ints>>v){
     if(v==0){a.cs.push_back(partial);partial.clear();}
     else{
       if(abs(v)>a.n||v==INT32_MIN)throw runtime_error("bad literal");
       partial.push_back(v);
     }
   }
 }
 if(a.declared<0||!partial.empty()||a.cs.size()!=size_t(a.declared))
    throw runtime_error("bad DIMACS count");
 return a;
}

struct WatchedRUP{
 int n;vector<Clause> clauses;
 vector<array<int,2>> watch;
 vector<vector<int>> watchers;
 vector<int> units;
 vector<int8_t> value;
 vector<int> trail;
 bool empty=false,expired=false;
 explicit WatchedRUP(int nv):n(nv),watchers(2*nv),value(nv+1){}
 void add(const Clause &c){
   int id=clauses.size();clauses.push_back(c);
   watch.push_back({0,int(c.size()>1)});
   if(c.empty()){empty=true;return;}
   watchers[ix(c[0])].push_back(id);
   if(c.size()>1)watchers[ix(c[1])].push_back(id);
   else units.push_back(c[0]);
 }
 int eval(int lit)const {return value[abs(lit)]*(lit>0?1:-1);}
 bool put(int lit){
   auto &v=value[abs(lit)];int b=lit>0?1:-1;
   if(v==b)return true;
   if(v==-b)return false;
   v=b;trail.push_back(lit);return true;
 }
 // -1: conflict, -2: deadline; 0: target not forced; 1: target forced;
 // 2: target forced false. All probes use an untouched source-only CNF.
 int propagate(const vector<int> &assumptions,const Timer &tim,int target=0){
   expired=false;
   if(empty)return -1;
   fill(value.begin(),value.end(),0);
   trail.clear();
   for(int lit:assumptions)if(!put(lit))return -1;
   for(int lit:units)if(!put(lit))return -1;
   unsigned loops=0;
   for(size_t q=0;q<trail.size();++q){
     if((q&1023)==0&&Clock::now()>=tim.limit){expired=true;return -2;}
     int false_lit=-trail[q];
     auto &bucket=watchers[ix(false_lit)];
     for(size_t pos=0;pos<bucket.size();){
       if((++loops&4095)==0&&Clock::now()>=tim.limit){expired=true;return -2;}
       int id=bucket[pos];
       auto &c=clauses[id];auto &w=watch[id];
       int side=c[w[0]]==false_lit?0:(c[w[1]]==false_lit?1:-1);
       if(side<0){bucket[pos]=bucket.back();bucket.pop_back();continue;}
       int other=c[w[1-side]];
       if(eval(other)>0){++pos;continue;}
       bool moved=false;
       for(int k=0;k<int(c.size());++k){
         if(k==w[0]||k==w[1])continue;
         if(eval(c[k])>=0){
           w[side]=k;
           watchers[ix(c[k])].push_back(id);
           bucket[pos]=bucket.back();bucket.pop_back();
           moved=true;break;
         }
       }
       if(moved)continue;
       if(eval(other)<0)return -1;
       if(!put(other))return -1;
       ++pos;
     }
   }
   if(!target)return 0;
   int result=eval(target);
   return result>0?1:(result<0?2:0);
 }
 bool rup(const Clause &lemma,const Timer &tim){
   vector<int> assumptions;
   assumptions.reserve(lemma.size());
   for(int lit:lemma)assumptions.push_back(-lit);
   return propagate(assumptions,tim)==-1;
 }
 // A sound shortcut for score measurement: the candidate clause would
 // immediately imply its other literal, but original unit propagation did not.
 // This is a heuristic utility score, NOT a proof and NOT a SAT result.
 // A positive score must still pass separate sequential RUP.
 int novel_directions(const Clause &c,const Timer &tim){
   // Under falsification of all OTHER clause literals, how many fresh
   // implications would this exact clause give versus unit propagation
   // over the untouched original source? Empty clauses are only selected
   // when the source is not already UP-inconsistent.
   if(c.empty())return propagate({},tim)==0?1:0;
   if(c.size()>3)return 0;
   int gain=0;
   for(size_t i=0;i<c.size();++i){
     vector<int> assumptions;
     for(size_t j=0;j<c.size();++j)if(i!=j)assumptions.push_back(-c[j]);
     int result=propagate(assumptions,tim,c[i]);
     if(expired)return 0;
     if(result==0)++gain;
   }
   return gain;
 }

};


static string family(const Clause &c){
 if(c.empty())return "empty";
 int pos=0;
 for(int lit:c)if(lit>0)++pos;
 return "length"+to_string(c.size())+"_pos"+to_string(pos);
}
static void write_output(const CNF &original,const vector<Clause> &extra,const string &path){
 ofstream out(path);if(!out)throw runtime_error("cannot create filtered CNF");
 out<<"p cnf "<<original.n<<" "<<(original.cs.size()+extra.size())<<"\n";
 for(const auto& c:original.cs){for(int l:c)out<<l<<' ';out<<"0\n";}
 for(const auto& c:extra){for(int l:c)out<<l<<' ';out<<"0\n";}
 if(!out)throw runtime_error("cannot write filtered CNF");
}
static void selftest(){
 Timer t(2000);
 CNF a; a.n=3;a.cs={{1,2,3},{1,2,-3}};
 WatchedRUP up(a.n);for(const auto &c:a.cs)up.add(c);
 if(up.novel_directions({1,2},t)!=2)throw runtime_error("missed novel resolvent");
 if(up.novel_directions({1,2,3},t)!=0)throw runtime_error("duplicated original clause scored positive");
 if(up.novel_directions({},t)!=1)throw runtime_error("empty-clause novelty");
 WatchedRUP unit(3);unit.add({1});
 if(unit.novel_directions({1},t)!=0)throw runtime_error("already implied unit scored positive");
 if(unit.novel_directions({-1},t)!=0)throw runtime_error("contradictory assumption scored positive");
 cout<<"DMD2_GATE_SELFTEST_PASS {\"novel_resolvent_directions\":2,\"redundant_clauses_rejected\":true}\n";
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
  if(argc!=5)throw runtime_error("usage: dmd2_gate original.cnf DMD1_augmented.cnf output.cnf budget_ms");
  int budget=stoi(argv[4]);if(budget<1||budget>5000)throw runtime_error("invalid gate budget");
  Timer tim(budget);
  CNF orig=readcnf(argv[1],tim);
  CNF augmented=readcnf(argv[2],tim);
  if(augmented.n!=orig.n||augmented.cs.size()<orig.cs.size())
    throw runtime_error("augmented source geometry invalid");
  if(!equal(orig.cs.begin(),orig.cs.end(),augmented.cs.begin()))
    throw runtime_error("original prefix modified");
  if(augmented.cs.size()-orig.cs.size()>24)
    throw runtime_error("unbounded candidate lemmas");
  WatchedRUP original(orig.n);
  for(const auto &c:orig.cs)original.add(c);
  vector<Clause> selected;
  vector<int> selected_indices;
  map<string,int> seen,positive,rejected,accepted;
  int count=0,sum=0;bool expired=false;
  for(size_t i=orig.cs.size();i<augmented.cs.size();++i){
    if(Clock::now()>=tim.limit){expired=true;break;}
    const Clause &c=augmented.cs[i];
    string key=family(c);
    ++seen[key];
    int score=original.novel_directions(c,tim);
    if(original.expired){expired=true;break;}
    ++count;
    if(score>0){
      ++positive[key];sum+=score;
      // Score measures a possible newly forced literal, NOT an UNSAT proof.
      // DMD1's separately replayed local proof is the justification for c.
      selected.push_back(c);selected_indices.push_back(int(i-orig.cs.size()));
      ++accepted[key];
    } else ++rejected[key];
  }
  if(!selected.empty())write_output(orig,selected,argv[3]);
  cout<<"DMD2_GATE {\"considered\":"<<count<<",\"candidates\":"<<(augmented.cs.size()-orig.cs.size())
      <<",\"selected\":"<<selected.size()<<",\"novel_directions\":"<<sum
      <<",\"timed_out\":"<<(expired?"true":"false")
      <<",\"budget_ms\":"<<budget<<",\"wall_s\":"<<tim.elapsed()
      <<",\"seen_types\":{";
  bool first=true;for(auto &p:seen){if(!first)cout<<",";first=false;cout<<"\""<<p.first<<"\":"<<p.second;}
  cout<<"},\"selected_types\":{";first=true;
  for(auto &p:accepted){if(!first)cout<<",";first=false;cout<<"\""<<p.first<<"\":"<<p.second;}
  cout<<"},\"selected_indices\":[";
  for(size_t i=0;i<selected_indices.size();i++){if(i)cout<<",";cout<<selected_indices[i];}
  cout<<"]}\n";
  return 0;
 }catch(const Timeout&){cerr<<"DMD2_GATE_FAIL_CLOSED timeout\n";return 75;}
  catch(const exception& e){cerr<<"DMD2_GATE_ERROR "<<e.what()<<"\n";return 1;}
}

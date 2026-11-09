// DRNAS DMD3X-C: select already proved ANF lemmas by CONDITIONAL UP novelty.
// A clause can be useless at root yet eliminate future branch decisions.
// This is an offline sound source-only filter, NOT live CDCL trail telemetry.
#define main dmd2_gate_historical_main
#include "dmd2_propagation_gate.cpp"
#undef main
#include <unordered_set>
#include <iomanip>
struct Rated {
 int idx=0,novel=0,degree=0,weight=0;
 Clause c;
};
static string to_json_array(const vector<int>& a){
 ostringstream s;s<<"[";
 for(size_t i=0;i<a.size();++i){if(i)s<<",";s<<a[i];}
 s<<"]";return s.str();
}
static bool same_clause(const Clause& a,const Clause& b){
 Clause x=a,y=b;sort(x.begin(),x.end());sort(y.begin(),y.end());
 return x==y;
}
static void test_dmd3xc() {
 ::selftest();
 Timer t(1000);
 CNF base;base.n=3;base.cs={{1,2,3},{1,2,-3}};
 WatchedRUP original(3);
 for(auto& c:base.cs)original.add(c);
 if(original.novel_directions({1,2},t)!=2)
   throw runtime_error("conditional example not detected");
 if(original.novel_directions({1,2,3},t)!=0)
   throw runtime_error("already BCP-visible clause not rejected");
 CNF second; second.n=2;second.cs={{1}};
 WatchedRUP known(2);known.add({1});
 if(known.novel_directions({1},t)!=0)
   throw runtime_error("root already forces unit");
 cout<<"DMD3XC_SELFTEST_PASS {\"conditional_resolvent_novelty\":2,"
     <<"\"existing_clause_rejected\":true,\"root_redundancy_rejected\":true}\n";
}
int main(int argc,char** argv){
 try {
  if(argc==2 && string(argv[1])=="selftest"){
    test_dmd3xc();return 0;
  }
  if(argc!=7)throw runtime_error(
    "usage: dmd3xc_gate original.cnf all_proved.cnf selected.cnf metrics.json budget_ms max_selected");
  string op=argv[1],cp=argv[2],sel=argv[3],meta=argv[4];
  int budget=stoi(argv[5]),k=stoi(argv[6]);
  if(budget<20||budget>3000||k<1||k>24)
    throw runtime_error("invalid gate budget/selection size");
  Timer tim(budget);
  CNF orig=readcnf(op,tim);
  CNF full=readcnf(cp,tim);
  if(orig.n!=full.n||full.cs.size()<orig.cs.size()||
     full.cs.size()-orig.cs.size()>24)
    throw runtime_error("candidate source geometry mismatch");
  if(!equal(orig.cs.begin(),orig.cs.end(),full.cs.begin()))
    throw runtime_error("original prefix modified");
  int nc=int(full.cs.size()-orig.cs.size());
  vector<Rated> rated;
  bool budget_expired=false;
  int scanned=0,novel_total=0,excluded_zero=0;
  {
   WatchedRUP up(orig.n);
   for(const auto& c:orig.cs) {
     if(Clock::now()>=tim.limit){budget_expired=true;break;}
     up.add(c);
   }
   if(!budget_expired)for(int i=0;i<nc;++i){
     if(Clock::now()>=tim.limit){budget_expired=true;break;}
     const Clause& c=full.cs[orig.cs.size()+i];
     int novel=up.novel_directions(c,tim);
     if(up.expired){budget_expired=true;break;}
     ++scanned;
     novel_total+=novel;
     if(novel<=0){++excluded_zero;continue;}
     int score=novel*1000+int(4-min<size_t>(4,c.size()))*20;
     rated.push_back({i,novel,int(c.size()),score,c});
   }
  }
  // All-or-nothing if soft budget is exhausted; no unstable partial subsets.
  if(budget_expired){rated.clear();}
  sort(rated.begin(),rated.end(),[](const Rated& a,const Rated& b){
    if(a.weight!=b.weight)return a.weight>b.weight;
    return a.idx<b.idx;
  });
  vector<int> indices;
  vector<Clause> extra;
  unordered_set<int> already;
  int selected_directions=0;
  while(!rated.empty()&&(int)indices.size()<k){
   int best=-1,best_score=numeric_limits<int>::min();
   for(int i=0;i<(int)rated.size();++i){
     int repeat=0;
     for(int l:rated[i].c)repeat+=already.count(abs(l))?1:0;
     int score=rated[i].weight-85*repeat;
     if(score>best_score||(score==best_score&&
                           (best==-1||rated[i].idx<rated[best].idx))) {
       best=i;best_score=score;
     }
   }
   Rated v=rated[best];
   rated.erase(rated.begin()+best);
   indices.push_back(v.idx);
   extra.push_back(move(v.c));
   selected_directions+=v.novel;
   for(int l:extra.back())already.insert(abs(l));
  }
  if(!extra.empty())write_output(orig,extra,sel);
  else ifstream z(sel); // no write when no lemma (caller must use a fresh path)
  auto elapsed=tim.elapsed();
  ostringstream out;
  out<<fixed<<setprecision(6)
     <<"{\"protocol\":\"DMD3XC-CONDITIONAL-UP-v1\""
     <<",\"candidates\":"<<nc
     <<",\"considered\":"<<scanned
     <<",\"positive_candidates\":"<<(budget_expired?0:(scanned-excluded_zero))
     <<",\"novel_directions_total\":"<<novel_total
     <<",\"selected\":"<<extra.size()
     <<",\"selected_directions\":"<<selected_directions
     <<",\"max_selected\":"<<k
     <<",\"budget_ms\":"<<budget
     <<",\"budget_exhausted\":"<<(budget_expired?"true":"false")
     <<",\"selection_reason\":\""<<(budget_expired?"abstain_budget":
       (nc==0?"no_candidates":(extra.empty()?"no_conditional_novelty":"conditional_up_novelty")))<<"\""
     <<",\"wall_s\":"<<elapsed
     <<",\"selected_indices\":"<<to_json_array(indices)
     <<"}";
  ofstream file(meta);if(!file)throw runtime_error("cannot write conditional gate metrics");
  file<<out.str()<<"\n";
  cout<<"DMD3XC_GATE "<<out.str()<<"\n";
  return 0;
 }catch(const Timeout&){cerr<<"DMD3XC_FAIL_CLOSED source parse timeout\n";return 75;}
 catch(const exception& e){cerr<<"DMD3XC_ERROR "<<e.what()<<"\n";return 1;}
}

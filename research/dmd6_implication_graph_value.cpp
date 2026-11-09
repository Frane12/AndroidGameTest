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


static void write_output(const CNF &original,const vector<Clause> &extra,const string &path){
 ofstream out(path);if(!out)throw runtime_error("cannot create filtered CNF");
 out<<"p cnf "<<original.n<<" "<<(original.cs.size()+extra.size())<<"\n";
 for(const auto& c:original.cs){for(int l:c)out<<l<<' ';out<<"0\n";}
 for(const auto& c:extra){for(int l:c)out<<l<<' ';out<<"0\n";}
 if(!out)throw runtime_error("cannot write filtered CNF");
}

struct ImplicationGraph {
 int n;
 vector<vector<int>> adj,rev;
 vector<int> scc,scc_size,occ,marks;
 int ncomponents=0,stamp=0,edges=0;
 explicit ImplicationGraph(const CNF& f,const Timer &t)
  :n(f.n),adj(2*f.n),rev(2*f.n),scc(2*f.n,-1),occ(2*f.n,0),marks(2*f.n,0) {
  for(size_t i=0;i<f.cs.size();++i){
   if((i&511)==0)t.check();
   const Clause& c=f.cs[i];
   for(int lit:c)occ[ix(lit)]++;
   if(c.size()==2 && c[0]!=c[1] && c[0]!=-c[1]){
     edge(-c[0],c[1]);edge(-c[1],c[0]);
   }
  }
  t.check();
  build_scc(t);
 }
 void edge(int from,int to){
   int a=ix(from),b=ix(to);
   adj[a].push_back(b);rev[b].push_back(a);
   ++edges;
 }
 void build_scc(const Timer& t){
  int N=2*n;
  vector<uint8_t> seen(N,0);
  vector<int> order;order.reserve(N);
  for(int s=0;s<N;++s){
   if(seen[s])continue;
   if((s&4095)==0)t.check();
   vector<pair<int,size_t>> st{{s,0}};
   seen[s]=1;
   while(!st.empty()){
    auto& top=st.back();
    if(top.second<adj[top.first].size()){
      int v=adj[top.first][top.second++];
      if(!seen[v]){seen[v]=1;st.push_back({v,0});}
    }else{order.push_back(top.first);st.pop_back();}
   }
  }
  for(auto it=order.rbegin();it!=order.rend();++it){
   int root=*it;if(scc[root]>=0)continue;
   vector<int> st{root};scc[root]=ncomponents;
   int size=0;
   while(!st.empty()){
    int v=st.back();st.pop_back();size++;
    for(int x:rev[v])if(scc[x]<0){scc[x]=ncomponents;st.push_back(x);}
   }
   scc_size.push_back(size);ncomponents++;
  }
 }
 // Path length is bounded; this measures a SOURCE-only structural
 // proxy, not a guaranteed CDCL propagation benefit.
 pair<int,bool> breadth(int src,int dest,int max_depth=3,int max_nodes=256){
   ++stamp; if(stamp==INT32_MAX){fill(marks.begin(),marks.end(),0);stamp=1;}
   vector<pair<int,int>> q{{src,0}};marks[src]=stamp;
   int visited=0;bool reaches=src==dest;
   for(size_t i=0;i<q.size()&&visited<max_nodes;i++){
     int v=q[i].first,depth=q[i].second;
     if(depth>=max_depth)continue;
     for(int w:adj[v]){
       if(marks[w]==stamp)continue;
       marks[w]=stamp;
       q.push_back({w,depth+1});visited++;
       if(w==dest)reaches=true;
       if(visited>=max_nodes)break;
     }
   }
   return {visited,reaches};
 }
 struct Feature {
   int novelty=0,fanout=0,bridge=0,shortcut=0,scc_join=0,score=0;
 };
 Feature feature(const Clause& clause,int novelty,const Timer& tim){
   (void)tim;
   Feature x;x.novelty=novelty;
   if(clause.size()!=2||clause[0]==clause[1]||clause[0]==-clause[1])
      return x;
   for(int k=0;k<2;k++){
     int src=ix(-clause[k]),dst=ix(clause[1-k]);
     const auto fan=breadth(dst,src,2,128);
     const auto path=breadth(src,dst,4,256);
     x.fanout+=min(16,fan.first);
     if(scc[src]!=scc[dst]){
       x.scc_join++;
       if(!path.second)x.bridge++;
       else x.shortcut++;
     }else if(scc_size[scc[src]]>1){
       x.shortcut++;
     }
   }
   // FIXED, PRECOMMITTED source-only heuristic; no outcome data enters.
   // Binary clauses are ranked; tertiary clauses retained as DMD2 control.
   x.score=20*min(2,x.novelty)+8*x.bridge+3*x.shortcut
      +2*min(32,x.fanout)+min(10,occ[ix(clause[0])])
      +min(10,occ[ix(clause[1])]);
   return x;
 }
};
static string json_feature(const ImplicationGraph::Feature& f,int i){
 ostringstream x;
 x<<"{\"index\":"<<i<<",\"novel_up\":"<<f.novelty
  <<",\"graph_fanout_2hop\":"<<f.fanout
  <<",\"binary_scc_bridges\":"<<f.bridge
  <<",\"binary_scc_shortcuts\":"<<f.shortcut
  <<",\"candidate_score\":"<<f.score<<"}";
 return x.str();
}
static void selftest6(){
 Timer t(3000);
 CNF c;c.n=3;c.cs={{-1,2},{-2,3},{1,2,3}};
 ImplicationGraph g(c,t);
 auto a=g.breadth(ix(1),ix(3),4,256);
 if(!a.second||g.ncomponents<=0||g.edges!=4)
    throw runtime_error("binary implication graph directed path broken");
 auto f=g.feature({-1,3},0,t);
 if(f.shortcut==0||f.score<=0)
    throw runtime_error("failed to rank an existing 2-hop shortcut");
 WatchedRUP rup(3);for(auto& q:c.cs)rup.add(q);
 if(rup.novel_directions({1,3},t)!=1)
    throw runtime_error("unexpected UP probing score");
 cout<<"DMD6_SELFTEST_PASS {\"directed_edges\":4,\"shortcut_score\":"
     <<f.score<<",\"novel_up_consequences\":1}\n";
}
int main(int argc,char** argv){
 try{
   if(argc==2&&string(argv[1])=="selftest"){selftest6();return 0;}
   if(argc!=6)throw runtime_error(
     "usage: dmd6_graph original.cnf DMD1_augmented.cnf output.cnf top1|top3|up1 budget_ms");
   string policy=argv[4];
   if(policy!="top1"&&policy!="top3"&&policy!="up1")
     throw runtime_error("unknown policy");
   int ms=stoi(argv[5]);if(ms<1||ms>5000)throw runtime_error("bad budget");
   Timer t(ms);
   CNF original=readcnf(argv[1],t);
   CNF aug=readcnf(argv[2],t);
   if(original.n!=aug.n||aug.cs.size()<original.cs.size()||
       !equal(original.cs.begin(),original.cs.end(),aug.cs.begin()))
     throw runtime_error("source prefix changed");
   const int count=int(aug.cs.size()-original.cs.size());
   if(count>24)throw runtime_error("unexpected candidate count");
   ImplicationGraph graph(original,t);
   WatchedRUP up(original.n);
   for(const auto& c:original.cs)up.add(c);
   vector<ImplicationGraph::Feature> features;
   vector<pair<int,int>> eligible;int positive_up=0;
   bool expired=false;
   for(int i=0;i<count;i++){
     if(Clock::now()>=t.limit){expired=true;break;}
     const Clause& c=aug.cs[original.cs.size()+i];
     int novelty=up.novel_directions(c,t);
     if(up.expired){expired=true;break;}
     auto f=graph.feature(c,novelty,t);
     features.push_back(f);positive_up+=(novelty>0);
     // Favor structural usefulness, NOT shape-only transfer.
     // Graph-only policies may use a non-UP-novel graph shortcut.
     bool eligible_now=c.size()==2&&c[0]!=-c[1]&&
        (f.bridge>0||f.shortcut>0||novelty>0);
     if(policy=="up1"&&novelty==0)eligible_now=false;
     if(eligible_now)eligible.push_back({-f.score,i});
   }
   if(expired){
     // If the complete candidate list was not scored, abstain rather than
     // accidentally condition the solver on a partial graph.
     eligible.clear();
   }
   sort(eligible.begin(),eligible.end());
   int cap=(policy=="top3"?3:1);
   vector<int> ids;vector<Clause> chosen;
   for(const auto& item:eligible){
     if(int(ids.size())>=cap)break;
     int index=item.second;
     const auto& c=aug.cs[original.cs.size()+index];
     // Reject shared-variable duplicates for top3 diversity.
     bool overlaps=false;
     if(policy=="top3")for(auto& prior:chosen){
       for(int a:prior)for(int b:c)if(abs(a)==abs(b))overlaps=true;
     }
     if(overlaps)continue;
     ids.push_back(index);chosen.push_back(c);
   }
   if(!chosen.empty())write_output(original,chosen,argv[3]);
   cout<<"DMD6_GRAPH {\"policy\":\""<<policy
      <<"\",\"source_only\":true,\"source_vars\":"<<original.n
      <<",\"source_clauses\":"<<original.cs.size()
      <<",\"binary_implication_edges\":"<<graph.edges
      <<",\"binary_scc_components\":"<<graph.ncomponents
      <<",\"candidate_count\":"<<count
      <<",\"scored_candidates\":"<<features.size()
      <<",\"positive_up_candidates\":"<<positive_up
      <<",\"selected\":"<<ids.size()
      <<",\"abstained\":"<<(expired?"true":"false")
      <<",\"budget_ms\":"<<ms<<",\"wall_s\":"<<t.elapsed()
      <<",\"candidate_features\":[";
   for(size_t i=0;i<features.size();i++){
      if(i)cout<<',';
      cout<<json_feature(features[i],int(i));
   }
   cout<<"],\"selected_indices\":[";
   for(size_t i=0;i<ids.size();i++){if(i)cout<<',';cout<<ids[i];}
   cout<<"]}\n";
   return 0;
 }catch(const Timeout&){cerr<<"DMD6_GRAPH_FAIL_CLOSED budget exhausted\n";return 75;}
 catch(const exception& e){cerr<<"DMD6_GRAPH_ERROR "<<e.what()<<"\n";return 1;}
}

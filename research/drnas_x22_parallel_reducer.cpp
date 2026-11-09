// DRNAS X22 — exact signed-SCC quotient from ORIGINAL source binary clauses.
// Standalone C++ helper: no solver-state mutation, no guessed XOR relations.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;
static void require(bool ok,const string& why){if(!ok)throw runtime_error("X22_FAIL_CLOSED "+why);}
struct Cnf{int n=0;vector<vector<int>> clauses;};
static Cnf parse(const string& file){
  ifstream f(file);require(bool(f),"input open");Cnf x;string tok;int declared=-1;
  vector<int> current;uint64_t count=0;
  while(f>>tok){
    if(tok=="c"){string s;getline(f,s);continue;}
    if(tok=="%")break;
    if(tok=="p"){
      string kind;require(declared<0 && current.empty() && bool(f>>kind>>x.n>>declared),"header");
      require(kind=="cnf" && x.n>=0 && x.n<=200000 &&
              declared>=0 && declared<=700000,"geometry guard");continue;
    }
    require(declared>=0,"missing header");
    size_t pos=0;int lit;
    try{lit=stoi(tok,&pos);}catch(...){throw runtime_error("bad token");}
    require(pos==tok.size(),"bad numeric token");
    if(!lit){x.clauses.push_back(move(current));current.clear();
             require(int(x.clauses.size())<=declared,"excess clauses");}
    else{
      require(lit!=(-2147483647-1) && abs(lit)<=x.n,"invalid literal");
      current.push_back(lit);require(++count<=8000000,"literal guard");
    }
  }
  require(declared>=0 && current.empty() && int(x.clauses.size())==declared,"clause count");
  return x;
}
static int node(int lit){return 2*(abs(lit)-1)+(lit<0);}
static int signed_literal(int v){return (v/2+1)*(v%2?-1:1);}
static vector<int> equivalences(const Cnf& x){
  int nodes=2*x.n;
  vector<vector<int>> g(nodes),rev(nodes);
  for(const auto& clause:x.clauses)
    if(clause.size()==2 && clause[0]!=clause[1] && clause[0]!=-clause[1]){
      int a=clause[0],b=clause[1];
      for(auto e:vector<pair<int,int>>{{-a,b},{-b,a}}){
        int from=node(e.first),to=node(e.second);
        g[from].push_back(to);rev[to].push_back(from);
      }
    }
  vector<char> seen(nodes,false);vector<int> order;order.reserve(nodes);
  for(int s=0;s<nodes;++s)if(!seen[s]){
    vector<pair<int,size_t>> stack{{s,0}};seen[s]=true;
    while(!stack.empty()){
      auto& t=stack.back();
      if(t.second<g[t.first].size()){
        int v=g[t.first][t.second++];
        if(!seen[v]){seen[v]=true;stack.push_back({v,0});}
      }else{order.push_back(t.first);stack.pop_back();}
    }
  }
  vector<int> component(nodes,-1);int count=0;
  for(auto it=order.rbegin();it!=order.rend();++it)if(component[*it]<0){
    vector<int> stack{*it};component[*it]=count;
    while(!stack.empty()){
      int v=stack.back();stack.pop_back();
      for(int to:rev[v])if(component[to]<0){component[to]=count;stack.push_back(to);}
    }++count;
  }
  vector<int> minimum(count,0);
  for(int i=0;i<nodes;++i){
    int v=signed_literal(i),&m=minimum[component[i]];
    if(!m || abs(v)<abs(m) || (abs(v)==abs(m) && v>m))m=v;
  }
  vector<int> map(x.n+1,0);
  for(int v=1;v<=x.n;++v)
    if(component[node(v)]==component[node(-v)])return map;
  int used=0;
  for(int v=1;v<=x.n && used<64;++v){
    int target=minimum[component[node(v)]];
    if(abs(target)<v){map[v]=target;++used;}
  }
  return map;
}
static void emit(const Cnf& x,const vector<int>& alias,bool enabled,
                 const string& destination,const string& mapping){
  vector<vector<int>> reduced;reduced.reserve(x.clauses.size());
  unordered_set<string> unique;unique.reserve(x.clauses.size()*2+1);
  uint64_t taut=0,dup=0,local_dup=0;
  for(const auto& clause:x.clauses){
    unordered_set<int> literals;vector<int> c;c.reserve(clause.size());bool skip=false;
    for(int lit:clause){
      int rep=(enabled && alias[abs(lit)])?alias[abs(lit)]:abs(lit);
      int replaced=lit>0?rep:-rep;
      if(literals.count(-replaced)){skip=true;break;}
      if(!literals.insert(replaced).second){++local_dup;continue;}
      c.push_back(replaced);
    }
    if(skip){++taut;continue;}
    auto key_lits=c;sort(key_lits.begin(),key_lits.end());
    string key;for(int l:key_lits){key+=to_string(l);key.push_back(',');}
    if(!unique.insert(key).second){++dup;continue;}
    reduced.push_back(move(c));
  }
  // The same short-clause-first ordering applies to clean and quotient.
  stable_sort(reduced.begin(),reduced.end(),
    [](const vector<int>& a,const vector<int>& b){return a.size()<b.size();});
  ofstream out(destination),map(mapping);require(bool(out)&&bool(map),"write open");
  out<<"p cnf "<<x.n<<" "<<reduced.size()<<"\n";
  for(const auto& c:reduced){for(int l:c)out<<l<<" ";out<<"0\n";}
  int aliases=0;
  for(int v=1;v<=x.n;++v)if(enabled && alias[v])++aliases;
  map<<"p map "<<x.n<<" "<<aliases<<"\n";
  if(enabled)for(int v=1;v<=x.n;++v)if(alias[v])map<<v<<" "<<alias[v]<<"\n";
  require(bool(out)&&bool(map),"write error");
  cout<<"X22_REDUCER {\"input_clauses\":"<<x.clauses.size()
      <<",\"output_clauses\":"<<reduced.size()<<",\"aliases\":"<<aliases
      <<",\"tautologies\":"<<taut<<",\"duplicate_clauses\":"<<dup
      <<",\"duplicate_literals\":"<<local_dup<<",\"source_binary_only\":true}\n";
}
int main(int argc,char**argv){
  try{
    require(argc==5,"usage: x22reducer clean|quotient src.cnf out.cnf alias.map");
    string mode=argv[1];require(mode=="clean"||mode=="quotient","mode");
    Cnf original=parse(argv[2]);auto map=equivalences(original);
    emit(original,map,mode=="quotient",argv[3],argv[4]);
    return 0;
  }catch(const exception& e){cerr<<e.what()<<"\n";return 78;}
}

// DRNAS R31: exact binary implication-path certificates and optional complete
// 2-SAT SCC solve. Original R29 XOR solver remains byte-identical, used as
// fallback; all other motifs are ANALYSIS ONLY, never unproved solver answers.
// "Active" uses a certificate only if original binary clauses alone prove UNSAT,
// or when the ENTIRE original CNF is 2-CNF and a verified SAT model is found.
#define main r29_inherited_main
#include "r29_hidden_partial.cpp"
#undef main
#include <functional>
#include <queue>
#include <set>
#include <unordered_set>

struct ImpEdge {int to, clause;};
static int index_lit(int lit){return 2*(abs(lit)-1)+(lit<0);}
static int unindex(int node){return (node%2)?-(node/2+1):(node/2+1);}
static bool rl_match(const vector<int>& clause,int from,int to) {
  if(clause.size()==1)return from==-clause[0] && to==clause[0];
  if(clause.size()!=2)return false;
  return (from==-clause[0] && to==clause[1]) ||
         (from==-clause[1] && to==clause[0]);
}
static vector<pair<int,int>> r31_path(
    const vector<vector<ImpEdge>>& edges,int start,int goal,int component,
    const vector<int>& comp) {
  vector<int> parent(edges.size(),-1),via(edges.size(),-1);
  queue<int> q;q.push(start);parent[start]=start;
  while(!q.empty() && parent[goal]==-1){
    int x=q.front();q.pop();
    for(const auto& e:edges[x]){
      if(comp[e.to]!=component || parent[e.to]!=-1)continue;
      parent[e.to]=x;via[e.to]=e.clause;q.push(e.to);
    }
  }
  vector<pair<int,int>> path;
  if(parent[goal]==-1)return path;
  for(int node=goal;node!=start;node=parent[node])
    path.push_back({node,via[node]});
  reverse(path.begin(),path.end());
  return path;
}
static int r31_exec_r29(const string& original,const string& inherited,
                         const string& kissat,const string& reason) {
  cout<<"c R31_ROUTE fallback reason="<<reason<<"\n"<<flush;
  char* args[]={const_cast<char*>(inherited.c_str()),
                const_cast<char*>(original.c_str()),
                const_cast<char*>(kissat.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R31_EXEC_FAILURE "<<strerror(errno)<<"\n";return 77;
}
static void r31_model(const vector<int>& truth,int n) {
  cout<<"s SATISFIABLE\n";
  for(int v=1;v<=n;v++){
    if((v-1)%20==0)cout<<"v ";
    cout<<(truth[v]?v:-v)<<" ";
    if(v%20==0)cout<<"0\n";
  }
  if(n%20)cout<<"0\n";
  cout<<flush;
}
int main(int argc,char** argv){
  if(argc!=4) {
    cerr<<"Usage: r31 INPUT R29_BINARY KISSAT_BINARY\n";return 2;
  }
  const string input=argv[1],inherited=argv[2],kissat=argv[3];
  // 1 = active certified SCC accelerator; 0 = frozen shadow overhead control.
  const bool active=[](){const char* x=getenv("R31_MODE");
                        return x && string(x)=="active";}();
  int n=0; vector<vector<int>> clauses;
  if(!read_cnf(input,n,clauses))
    return r31_exec_r29(input,inherited,kissat,"input_guard");
  if(n>3000 || clauses.size()>150000)
    return r31_exec_r29(input,inherited,kissat,"size_guard");
  const int N=2*n;
  vector<vector<ImpEdge>> edges(N);
  vector<vector<int>> reverse_edges(N);
  size_t binary=0,units=0;
  bool entire_binary=true;
  set<pair<int,int>> binary_clauses;
  for(size_t i=0;i<clauses.size();i++){
    const auto& c=clauses[i];
    if(c.size()>2)entire_binary=false;
    if(c.size()==0) {
      entire_binary=false; // R29 handles base contradiction.
      continue;
    }
    if(c.size()==1){units++;}
    else if(c.size()==2){
      binary++;
      binary_clauses.insert(minmax(c[0],c[1]));
    }
    else continue;
    const int a=c[0], b=c.size()==2?c[1]:c[0];
    const int p=index_lit(-a),q=index_lit(b);
    edges[p].push_back({q,int(i)});
    reverse_edges[q].push_back(p);
    if(c.size()==2){
      const int r=index_lit(-b),s=index_lit(a);
      edges[r].push_back({s,int(i)});
      reverse_edges[s].push_back(r);
    }
  }
  // Certified full 3-clause AND/OR gate signature: a binary half for both
  // inputs and the exact ternary covering clause. ANALYTICS ONLY.
  int gates_and=0,gates_or=0;
  if(clauses.size()<=30000){
    for(const auto& c:clauses) if(c.size()==3){
      for(int i=0;i<3;i++){
        int o=c[i];
        int x=c[(i+1)%3],y=c[(i+2)%3];
        if(binary_clauses.count(minmax(-o,-x)) &&
           binary_clauses.count(minmax(-o,-y))){
          if(o>0)gates_and++; else gates_or++;
        }
      }
    }
  }
  vector<int> used(N,0),order,comp(N,-1);
  function<void(int)> first=[&](int v){
    used[v]=1;
    for(const auto& e:edges[v])if(!used[e.to])first(e.to);
    order.push_back(v);
  };
  for(int v=0;v<N;v++)if(!used[v])first(v);
  int component_count=0;
  function<void(int)> second=[&](int v) {
    comp[v]=component_count;
    for(int w:reverse_edges[v])if(comp[w]<0)second(w);
  };
  for(auto it=order.rbegin();it!=order.rend();++it)if(comp[*it]<0){
    second(*it);component_count++;
  }
  vector<int> component_size(component_count,0);
  for(int c:comp)component_size[c]++;
  int linked=0;
  for(int s:component_size)if(s>1)linked+=s;
  cout<<"c R31_FEATURES n="<<n<<" clauses="<<clauses.size()
      <<" binary="<<binary<<" units="<<units
      <<" scc="<<component_count<<" linked_literals="<<linked
      <<" and_motifs="<<gates_and<<" or_motifs="<<gates_or
      <<" entirely_2cnf="<<int(entire_binary)<<"\n"<<flush;
  if(active){
    for(int v=1;v<=n;v++){
      const int pos=index_lit(v),neg=index_lit(-v);
      if(comp[pos]!=comp[neg])continue;
      auto p1=r31_path(edges,pos,neg,comp[pos],comp);
      auto p2=r31_path(edges,neg,pos,comp[pos],comp);
      if(p1.empty() || p2.empty())return r31_exec_r29(input,inherited,kissat,"proof_guard");
      int x=pos;
      cout<<"c R31_ROUTE certified_binary_unsat var="<<v<<"\n";
      for(const auto& step:p1){
        const int to=step.first,id=step.second;
        if(id<0 || size_t(id)>=clauses.size() ||
           !rl_match(clauses[id],unindex(x),unindex(to)))
          return r31_exec_r29(input,inherited,kissat,"edge_proof_guard");
        cout<<"c R31_EDGE path=1 from="<<unindex(x)
            <<" to="<<unindex(to)<<" clause="<<id<<"\n";
        x=to;
      }
      x=neg;
      for(const auto& step:p2){
        const int to=step.first,id=step.second;
        if(id<0 || size_t(id)>=clauses.size() ||
           !rl_match(clauses[id],unindex(x),unindex(to)))
          return r31_exec_r29(input,inherited,kissat,"edge_proof_guard");
        cout<<"c R31_EDGE path=2 from="<<unindex(x)
            <<" to="<<unindex(to)<<" clause="<<id<<"\n";
        x=to;
      }
      cout<<"s UNSATISFIABLE\n"<<flush;
      return 20;
    }
    if(entire_binary){
      vector<int> truth(size_t(n)+1,0);
      for(int v=1;v<=n;v++)
        truth[v]=comp[index_lit(v)]>comp[index_lit(-v)];
      if(valid_model(clauses,truth)){
        cout<<"c R31_ROUTE certified_entire_2sat_sat\n";
        r31_model(truth,n);return 10;
      }
    }
  }
  return r31_exec_r29(input,inherited,kissat,active?"no_provable_binary_gain":"shadow");
}

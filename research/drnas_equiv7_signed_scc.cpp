// DRNAS EQUIV7: diagnostic only, original-CNF binary implication SCC.
// Never changes a clause, produces SAT status, or claims independent UNSAT LRAT.
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
static double ms(Clock::time_point t) {
  return chrono::duration<double,milli>(Clock::now()-t).count();
}
static int id(int lit) {return 2*(abs(lit)-1)+(lit<0);}
int main(int argc,char**argv) {
  if(argc!=2) {cerr<<"usage: equiv7_scc original.cnf\n";return 2;}
  auto total=Clock::now();
  ifstream in(argv[1]);if(!in) {cerr<<"failed to open CNF\n";return 2;}
  string tok;int n=0,decl=0,clauses=0,binary=0,units=0;
  vector<int> clause;
  vector<vector<int>> adj,rev;
  long long edges=0;
  while(in>>tok) {
    if(tok=="c"||tok=="%") {string ignored;getline(in,ignored);continue;}
    if(tok=="p") {
      string fmt;
      if(!(in>>fmt>>n>>decl)||fmt!="cnf"||n<=0||n>1000000||decl<0) {
        cerr<<"bad header\n";return 2;
      }
      adj.resize(2*n);rev.resize(2*n);
      continue;
    }
    if(n<=0) {cerr<<"missing header\n";return 2;}
    int lit;
    try {
      size_t pos;lit=stoi(tok,&pos);
      if(pos!=tok.size())throw invalid_argument("nonint");
    }catch(...) {cerr<<"nonint\n";return 2;}
    if(lit!=0) {
      if(abs(lit)>n) {cerr<<"bad literal\n";return 2;}
      clause.push_back(lit);
    }else {
      clauses++;
      if(clause.size()==1)units++;
      if(clause.size()==2) {
        binary++;int a=clause[0],b=clause[1];
        if(a==b) {
          int u=id(-a),v=id(a);
          adj[u].push_back(v);rev[v].push_back(u);edges++;
        }else if(a!=-b) {
          int u=id(-a),v=id(b),w=id(-b),z=id(a);
          adj[u].push_back(v);rev[v].push_back(u);
          adj[w].push_back(z);rev[z].push_back(w);edges+=2;
        }
      }
      clause.clear();
    }
  }
  if(!clause.empty()||clauses!=decl) {
    cerr<<"DIMACS declared clauses mismatch\n";return 2;
  }
  double parse_ms=ms(total);
  auto start=Clock::now();
  int N=2*n;
  vector<char> seen(N,0);
  vector<int> order;order.reserve(N);
  vector<pair<int,size_t>> st;st.reserve(N);
  for(int node=0;node<N;node++)if(!seen[node]) {
    seen[node]=1;st.emplace_back(node,0);
    while(!st.empty()) {
      auto &t=st.back();int v=t.first;
      if(t.second<adj[v].size()) {
        int to=adj[v][t.second++];
        if(!seen[to]) {seen[to]=1;st.emplace_back(to,0);}
      }else {order.push_back(v);st.pop_back();}
    }
  }
  vector<int> component(N,-1),sizes;
  vector<int> q;q.reserve(N);
  for(int k=N-1;k>=0;k--) {
    int v=order[k];if(component[v]>=0)continue;
    int cid=(int)sizes.size(),sz=0;
    component[v]=cid;q.push_back(v);
    while(!q.empty()) {
      int node=q.back();q.pop_back();sz++;
      for(int to:rev[node])if(component[to]<0) {
        component[to]=cid;q.push_back(to);
      }
    }
    sizes.push_back(sz);
  }
  int nontrivial=0,maxsz=0,literals=0,cycles3=0,conflicts=0,alias_candidates=0;
  for(int size:sizes) {
    maxsz=max(maxsz,size);
    if(size>1) {nontrivial++;literals+=size;}
    if(size>=3)cycles3++;
  }
  for(int var=0;var<n;var++) {
    if(component[2*var]==component[2*var+1])conflicts++;
    if(sizes[component[2*var]]>1)alias_candidates++;
  }
  cout<<"SCC7_DIAGNOSTIC {\"vars\":"<<n<<",\"clauses\":"<<clauses
      <<",\"binary_clauses\":"<<binary<<",\"unit_clauses\":"<<units
      <<",\"directed_edges\":"<<edges<<",\"scc_count\":"<<sizes.size()
      <<",\"nontrivial_scc\":"<<nontrivial<<",\"max_scc_size\":"<<maxsz
      <<",\"scc_size_ge3\":"<<cycles3<<",\"scc_nontrivial_literals\":"<<literals
      <<",\"positive_alias_candidate_vars\":"<<alias_candidates
      <<",\"binary_unsat_conflicting_vars\":"<<conflicts
      <<",\"cnf_parse_ms\":"<<parse_ms<<",\"scc_ms\":"<<ms(start)
      <<",\"total_ms\":"<<ms(total)<<"}\n";
}

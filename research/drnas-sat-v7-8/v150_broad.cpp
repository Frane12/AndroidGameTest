// DRNAS SAT V15.0 BROAD: sound structural routes on arbitrary DIMACS CNF.
// No labels or filenames used for solver selection. Every result is implied
// by the entire original CNF, otherwise invoke untouched Kissat.
// Non-affine supported routes: certified unit propagation, binary implication
// SCC, exact pigeonhole; affine: 2..8-variable parity with redundant clauses.
#include "v142_fastgate.cpp"
#include <bitset>
#include <queue>
#include <numeric>
#include <functional>
#include <limits>
#include <sys/stat.h>

static int lit_node(int lit) {
 return 2*(abs(lit)-1)+(lit<0?1:0);
}
static int node_lit(int node) {
 int v=node/2+1;
 return (node&1)?-v:v;
}
static bool verify_model(const Cnf &f,const vector<int>& model) {
 if(int(model.size())!=f.n)return false;
 vector<char> values(f.n+1,0),seen(f.n+1,0);
 for(int lit:model){
   int v=abs(lit);
   if(v<1||v>f.n||seen[v])return false;
   seen[v]=1;values[v]=(lit>0);
 }
 for(const auto& cl:f.clauses) {
   bool ok=false;
   for(int lit:cl)if(values[abs(lit)]==(lit>0)){ok=true;break;}
   if(!ok)return false;
 }
 return true;
}
static void emit_sat(const Cnf &f,const vector<int>& model,const string& path) {
 Answer a;a.status="SAT";a.model=model;
 if(!verify_model(f,a.model))throw runtime_error("SAT witness failed full CNF check");
 json_answer(a,f.n,0,path.c_str());
}
static void emit_unsat_simple(const string& path) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\",\"path\":\""<<path
     <<"\",\"verified\":true}\n";
}
struct UpProof {
 bool unsat=false,has_unit=false;
 int conflict_clause=-1;
 vector<pair<int,int>> trace;
 vector<int> model;
};
static bool verify_unit_proof(const Cnf& f,const UpProof& p) {
 if(!p.unsat || p.conflict_clause<0 ||
    p.conflict_clause>=int(f.clauses.size()))return false;
 vector<int8_t> value(f.n+1,-1);
 for(const auto& item:p.trace) {
   int lit=item.first,reason=item.second,v=abs(lit);
   if(v<1||v>f.n||reason<0||reason>=int(f.clauses.size()))return false;
   if(value[v]!=-1)return false;
   bool found=false;
   for(int x:f.clauses[reason]){
     if(x==lit){found=true;continue;}
     if(value[abs(x)]<0||value[abs(x)]==(x>0))return false;
   }
   if(!found)return false;
   value[v]=(lit>0);
 }
 for(int x:f.clauses[p.conflict_clause])
   if(value[abs(x)]<0||value[abs(x)]==(x>0))return false;
 return true;
}
static UpProof unit_propagate(const Cnf& f) {
 UpProof result;
 const int n=f.n;
 vector<vector<int>> occurrences(2*n);
 vector<pair<int,int>> queue;
 for(int i=0;i<int(f.clauses.size());i++) {
   const auto& cl=f.clauses[i];
   if(cl.size()==1) {queue.push_back({cl[0],i});result.has_unit=true;}
   for(int lit:cl) occurrences[lit_node(lit)].push_back(i);
 }
 if(!result.has_unit)return result;
 vector<int8_t> value(n+1,-1);
 for(size_t head=0;head<queue.size();head++) {
   int lit=queue[head].first,reason=queue[head].second,v=abs(lit);
   if(value[v]!=-1) {
     if(value[v]!=(lit>0)) {
       result.unsat=true;result.conflict_clause=reason;
       return result;
     }
     continue;
   }
   value[v]=(lit>0);
   result.trace.push_back({lit,reason});
   for(int ci:occurrences[lit_node(-lit)]) {
     const auto& cl=f.clauses[ci];
     int open=0,last=0;bool satisfied=false;
     for(int x:cl) {
       const int8_t a=value[abs(x)];
       if(a<0){open++;last=x;}
       else if(a==(x>0)){satisfied=true;break;}
     }
     if(satisfied)continue;
     if(open==0){
       result.unsat=true;result.conflict_clause=ci;return result;
     }
     if(open==1)queue.push_back({last,ci});
   }
 }
 // A partial assignment may already satisfy all clauses. Fill unused vars
 // with false and validate the full DIMACS formula independently.
 result.model.reserve(n);
 for(int v=1;v<=n;v++)result.model.push_back(value[v]>0?v:-v);
 if(!verify_model(f,result.model))result.model.clear();
 return result;
}
static void emit_unit_proof(const UpProof& p) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v150_unit_propagation\","
     <<"\"verified\":true,\"conflict_clause\":"<<p.conflict_clause
     <<",\"unit_trace\":[";
 for(size_t i=0;i<p.trace.size();i++) {
   if(i)cout<<",";
   cout<<"["<<p.trace[i].first<<","<<p.trace[i].second<<"]";
 }
 cout<<"]}\n";
}
struct ImplicationProof {
 int variable=0;
 vector<int> path_pos_to_neg,path_neg_to_pos;
 int binary_count=0;
};
static vector<int> implication_path(int start,int target,
                                    const vector<vector<int>>& graph) {
 vector<int> prev(graph.size(),-1);
 queue<int> q;q.push(start);prev[start]=start;
 while(!q.empty() && prev[target]<0) {
   int u=q.front();q.pop();
   for(int v:graph[u])if(prev[v]<0) {
     prev[v]=u;q.push(v);
   }
 }
 if(prev[target]<0)return {};
 vector<int> result;
 for(int at=target;at!=start;at=prev[at])result.push_back(node_lit(at));
 result.push_back(node_lit(start));
 reverse(result.begin(),result.end());
 return result;
}
static ImplicationProof binary_scc_conflict(const Cnf& f) {
 ImplicationProof proof;
 if(f.n>4096)return proof;
 const int N=2*f.n;
 vector<vector<int>> g(N),gr(N);
 auto edge=[&](int a,int b){
   int i=lit_node(a),j=lit_node(b);
   g[i].push_back(j);gr[j].push_back(i);
 };
 for(const auto& cl:f.clauses) {
   if(cl.size()==2) {
     edge(-cl[0],cl[1]);edge(-cl[1],cl[0]);
     proof.binary_count++;
   } else if(cl.size()==1)edge(-cl[0],cl[0]);
 }
 if(proof.binary_count==0)return {};
 vector<uint8_t> seen(N,0);
 vector<int> order;order.reserve(N);
 for(int root=0;root<N;root++)if(!seen[root]) {
   vector<pair<int,size_t>> dfs;dfs.push_back({root,0});seen[root]=1;
   while(!dfs.empty()) {
     auto& fr=dfs.back();int u=fr.first;
     if(fr.second<g[u].size()) {
       int v=g[u][fr.second++];
       if(!seen[v]){seen[v]=1;dfs.push_back({v,0});}
     } else {order.push_back(u);dfs.pop_back();}
   }
 }
 vector<int> comp(N,-1);int comp_id=0;
 for(auto it=order.rbegin();it!=order.rend();++it) {
   int v=*it;if(comp[v]>=0)continue;
   vector<int> stack={v};comp[v]=comp_id;
   while(!stack.empty()) {
     int u=stack.back();stack.pop_back();
     for(int w:gr[u])if(comp[w]<0) {comp[w]=comp_id;stack.push_back(w);}
   }
   comp_id++;
 }
 for(int v=1;v<=f.n;v++)if(comp[lit_node(v)]==comp[lit_node(-v)]) {
   proof.variable=v;
   proof.path_pos_to_neg=implication_path(lit_node(v),lit_node(-v),g);
   proof.path_neg_to_pos=implication_path(lit_node(-v),lit_node(v),g);
   if(proof.path_pos_to_neg.empty()||proof.path_neg_to_pos.empty())
     throw runtime_error("SCC path proof failed");
   // Verify every implication is licensed by an original binary/unit clause
   // by comparing against edges derived above.
   auto verify_path=[&](const vector<int>& path){
     for(size_t j=1;j<path.size();j++) {
       int src=lit_node(path[j-1]),dst=lit_node(path[j]);
       if(find(g[src].begin(),g[src].end(),dst)==g[src].end())return false;
     }
     return true;
   };
   if(!verify_path(proof.path_pos_to_neg)||!verify_path(proof.path_neg_to_pos))
     throw runtime_error("Invalid implication proof");
   return proof;
 }
 return {};
}
static void emit_binary_proof(const ImplicationProof& p) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v150_binary_scc\","
     <<"\"verified\":true,\"variable\":"<<p.variable
     <<",\"path_pos_to_neg\":[";
 for(size_t i=0;i<p.path_pos_to_neg.size();i++)
   cout<<(i?",":"")<<p.path_pos_to_neg[i];
 cout<<"],\"path_neg_to_pos\":[";
 for(size_t i=0;i<p.path_neg_to_pos.size();i++)
   cout<<(i?",":"")<<p.path_neg_to_pos[i];
 cout<<"]}\n";
}
struct Xor8Result {
 vector<Eq> equations;
 vector<int> exhaustive_support;
 int candidate_groups=0;
 int widest=0;
};
static Xor8Result extract_xor8(const Cnf& f) {
 Xor8Result res;
 if(f.n>4096||f.clauses.size()>100000)return res;
 map<array<int,8>,bitset<256>> patterns;
 for(const auto& cl:f.clauses) {
   if(cl.size()<2||cl.size()>8)continue;
   auto literals=cl;
   sort(literals.begin(),literals.end(),[](int a,int b){return abs(a)<abs(b);});
   array<int,8> support{};unsigned mask=0;bool valid=true;
   for(size_t j=0;j<literals.size();j++) {
     support[j]=abs(literals[j]);
     if(j && support[j]==support[j-1]){valid=false;break;}
     if(literals[j]<0)mask|=1u<<j;
   }
   if(!valid)continue;
   patterns[support].set(mask);
   if(patterns.size()>12000)return {};
 }
 const int words=(f.n+63)/64;
 for(const auto& item:patterns) {
   const auto& support=item.first;
   const auto& forbidden=item.second;
   int width=0;while(width<8 && support[width])width++;
   const unsigned count=1u<<width;
   if(forbidden.count() < count/2)continue;
   res.candidate_groups++;
   if(forbidden.count()==count) {
     res.exhaustive_support.assign(support.begin(),support.begin()+width);
     return res;
   }
   int parity=-1;bool valid=true;
   for(unsigned assignment=0;assignment<count;assignment++) {
     if(forbidden.test(assignment))continue;
     int p=__builtin_popcount(assignment)&1;
     if(parity<0)parity=p;
     else if(parity!=p){valid=false;break;}
   }
   if(!valid||parity<0)continue;
   Eq eq;eq.bits.assign(words,0);eq.rhs=parity;
   for(int j=0;j<width;j++) {
     int v=support[j]-1;eq.bits[v/64]|=1ULL<<(v%64);
   }
   res.equations.push_back(move(eq));
   res.widest=max(res.widest,width);
   if(res.equations.size()>4096)return {};
 }
 return res;
}
static void emit_exhaustive_proof(const vector<int>& vars) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v150_exhaustive_support\","
     <<"\"verified\":true,\"support\":[";
 for(size_t i=0;i<vars.size();i++)cout<<(i?",":"")<<vars[i];
 cout<<"],\"certificate\":\"all_support_assignments_excluded\"}\n";
}
static int kissat_fallback(char **argv) {
 char *av[]={argv[2],argv[1],nullptr};
 cout<<"DRNAS_V150_ROUTE\tkissat_direct\n"<<flush;
 execv(av[0],av);
 cerr<<"DRNAS_V150_ERROR Kissat exec failure\n";
 return 3;
}
int main(int argc,char**argv) {
 if(!(argc==4||(argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v150_broad INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   struct stat st{};
   if(stat(argv[1],&st)!=0 || st.st_size<=0 || st.st_size>16*1024*1024)
     return argc==5?(cout<<"DRNAS_V150_ROUTE\tkissat_direct\n",0):kissat_fallback(argv);
   Cnf f=parse(argv[1]);
   if(f.n>4096)
     return argc==5?(cout<<"DRNAS_V150_ROUTE\tkissat_direct\n",0):kissat_fallback(argv);
   // Classification is side-effect free and has no SAT/UNSAT answer.
   if(argc==5) {
     cout<<"DRNAS_V150_ROUTE\tstructural_analysis\n";
     return 0;
   }
   UpProof up=unit_propagate(f);
   if(up.unsat) {
     if(!verify_unit_proof(f,up))throw runtime_error("UP proof replay failed");
     emit_unit_proof(up);return 0;
   }
   if(up.has_unit && !up.model.empty()) {
     emit_sat(f,up.model,"v150_unit_model");return 0;
   }
   ImplicationProof implication=binary_scc_conflict(f);
   if(implication.variable>0) {
     emit_binary_proof(implication);return 0;
   }
   Xor8Result xr=extract_xor8(f);
   if(!xr.exhaustive_support.empty()) {
     emit_exhaustive_proof(xr.exhaustive_support);return 0;
   }
   if(!xr.equations.empty()) {
     try {
       Answer a=solve_exact(f,xr.equations);
       json_answer(a,f.n,int(xr.equations.size()),
                   a.status=="UNSAT"?"v150_affine_unsat":"v150_affine_sat_verified");
       return 0;
     } catch(const exception&) {
       // A free-variable assignment can fail the residual CNF.
       // Never turn such a failure into a SAT/UNSAT classification.
     }
   }
   int holes=0,birds=0;
   if(complete_php_proof(f,holes,birds)) {
     json_php(holes,birds);return 0;
   }
 } catch(const exception& e) {
   cerr<<"DRNAS_V150_FALLBACK "<<e.what()<<"\n";
 }
 return kissat_fallback(argv);
}

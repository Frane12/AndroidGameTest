// DRNAS SAT V15.3.2 PREFIX SKIP (V15.3.1 BASE) — V15.3 UNIFIED CORE WITH BOUNDED STRUCTURAL WORK: sound structural routes on arbitrary DIMACS CNF.
// No labels or filenames used for solver selection. Every result is implied
// by the entire original CNF, otherwise invoke untouched Kissat.
// Non-affine supported routes: certified unit propagation, binary implication
// SCC, exact pigeonhole; affine: 2..10-variable parity with redundant clauses.
#include "v142_fastgate.cpp"
#include <set>
#include <cstdio>
#include <bitset>
#include <queue>
#include <numeric>
#include <functional>
#include <limits>
#include <sys/stat.h>
#include <chrono>
#include <unordered_set>
#include <climits>

// Fast, conservative gate: all expensive structural routines are activated
// only if their necessary CNF signatures occur. A missed structural route
// always falls back to unmodified Kissat, never guesses SAT/UNSAT.
struct V1531Signals {
 bool units=false, binary=false, xor_candidate=false;
 bool hall_candidate=false, php_candidate=false;
 size_t clause_count=0, literal_count=0;
};
static V1531Signals v1531_signals(const Cnf& f) {
 V1531Signals g;
 g.clause_count=f.clauses.size();
 size_t all_positive=0, negative_binary=0, hall_positive=0;
 bool php_shape=true;
 std::unordered_set<uint64_t> seen;
 // Reserve a bounded amount: no unbounded memory growth on hostile CNF.
 seen.reserve(std::min<size_t>(f.clauses.size(),4096));
 for(const auto& cl:f.clauses) {
   g.literal_count+=cl.size();
   const size_t w=cl.size();
   if(w==1)g.units=true;
   if(w==2)g.binary=true;
   bool all_pos=(w>=2), all_neg=(w==2);
   for(int lit:cl){all_pos=all_pos && lit>0;all_neg=all_neg && lit<0;}
   if(all_pos)all_positive++;
   if(all_pos && w>=3 && w<=32)hall_positive++;
   if(all_neg)negative_binary++;
   if(!all_pos&&!all_neg)php_shape=false;
   if(!g.xor_candidate && w>=2 && w<=10) {
     std::array<int,10> support{};
     for(size_t i=0;i<w;i++)support[i]=abs(cl[i]);
     std::sort(support.begin(),support.begin()+w);
     bool valid=true;
     for(size_t i=1;i<w;i++)if(support[i]==support[i-1])valid=false;
     if(valid) {
       uint64_t h=1469598103934665603ULL;
       h^=w;h*=1099511628211ULL;
       for(size_t i=0;i<w;i++){h^=uint64_t(support[i]);h*=1099511628211ULL;}
       if(!seen.insert(h).second)g.xor_candidate=true;
     }
   }
 }
 g.hall_candidate=(hall_positive>=3 && hall_positive<=512 && negative_binary>0);
 g.php_candidate=(php_shape && all_positive>=2 && negative_binary>0);
 return g;
}
// V15.3.2: a very cheap, bounded *prefix-only* stream check, BEFORE DIMACS
// parsing. It only decides whether to try V15.3 structural routines.
// A negative decision execs ORIGINAL Kissat on the original file. Hence
// inaccurate classification can cost speed, but cannot misclassify SAT/UNSAT.
// A malformed/ambiguous prefix always goes through the normal safe path.
static bool v1532_prefix_maybe_structured(const char* path) {
 std::ifstream in(path);
 if(!in)return true;
 bool header=false,possible_repeat=false;
 int clauses=0,units=0,binaries=0,negative_binary=0,alo=0;
 size_t bytes=0;
 std::unordered_set<uint64_t> supports;
 supports.reserve(192);
 std::vector<int> clause;
 clause.reserve(16);
 std::string line;
 while(clauses<128 && bytes<65536 && std::getline(in,line)) {
   bytes+=line.size()+1;
   std::istringstream ss(line);
   std::string token;
   if(!(ss>>token))continue;
   if(token=="c" || token=="%")continue;
   if(token=="p") {
     if(header)return true;
     std::string kind; int vars=0,count=0;
     if(!(ss>>kind>>vars>>count) || kind!="cnf" || vars<1 || count<0)
       return true;
     header=true;
     continue;
   }
   if(!header)return true;
   do {
     if(token=="c")break;
     char* end=nullptr;
     errno=0;
     long lit=strtol(token.c_str(),&end,10);
     if(errno || end==token.c_str() || *end || lit>INT_MAX || lit<=INT_MIN)
       return true;
     if(lit!=0) {
       clause.push_back(int(lit));
       if(clause.size()>64)return true;
       continue;
     }
     if(clause.empty())return true;
     const size_t width=clause.size();
     clauses++;
     if(width==1)units++;
     if(width==2) {
       binaries++;
       if(clause[0]<0 && clause[1]<0)negative_binary++;
     }
     bool all_pos=(width>=3);
     for(int x:clause)all_pos=all_pos && x>0;
     if(all_pos && width<=32)alo++;
     if(width>=2 && width<=10 && !possible_repeat) {
       std::array<int,10> vars{};
       for(size_t i=0;i<width;i++)vars[i]=abs(clause[i]);
       std::sort(vars.begin(),vars.begin()+width);
       bool distinct=true;
       for(size_t i=1;i<width;i++)if(vars[i]==vars[i-1])distinct=false;
       if(distinct) {
         uint64_t h=1469598103934665603ULL;
         h^=width;h*=1099511628211ULL;
         for(size_t i=0;i<width;i++){
           h^=uint64_t(vars[i]);h*=1099511628211ULL;
         }
         if(!supports.insert(h).second)possible_repeat=true;
       }
     }
     clause.clear();
   } while(ss>>token);
 }
 // Keep the full structural solver for short/uncertain prefixes. This
 // protects small, highly structured Hall/XOR instances from coarse gates.
 if(!header || clauses<48)return true;
 // Units: UP/affine; repeats: encoded XOR; positives+negative binary:
 // Hall / PHP; mostly binary: SCC.
 if(units>0 || possible_repeat)return true;
 if(alo>=3 && negative_binary>0)return true;
 if(alo>=3 && binaries>=8)return true;
 if(binaries*3>=clauses*2)return true;
 // The remaining prefix has too little evidence for any V15.3 proof route.
 return false;
}
static uint64_t v1531_unit_work_cap() {
 // Cap clause-literal visits; this is an algorithmic budget rather than a
 // hard deadline for the external SAT solver.
 return 400000;
}
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
 uint64_t clause_literal_visits=0;
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
     if(clause_literal_visits>v1531_unit_work_cap())
       return UpProof{}; // No answer; caller safely falls back to other routes.

     int open=0,last=0;bool satisfied=false;
     for(int x:cl) {
       if(++clause_literal_visits>v1531_unit_work_cap())return UpProof{};
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
     <<"\"path\":\"v153_unit_propagation\","
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
 vector<int> candidate_model;
 vector<pair<int,int>> equivalence_links;
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
 // Every pair of literals in the same SCC is equivalent under the
 // original binary/unit clauses. Record canonical links for augmentation.
 map<int,int> representatives;
 for(int node=0;node<N;node++){
   int component=comp[node];
   auto it=representatives.find(component);
   if(it==representatives.end() ||
      abs(node_lit(node))<abs(node_lit(it->second)))
     representatives[component]=node;
 }
 for(int node=0;node<N;node++){
   int representative=representatives[comp[node]];
   if(node!=representative &&
      abs(node_lit(node))!=abs(node_lit(representative)) &&
      proof.equivalence_links.size()<512)
     proof.equivalence_links.push_back(
       {node_lit(representative),node_lit(node)});
 }
 // If the binary/units subset is satisfiable, its SCC topological
 // assignment may also satisfy all higher-arity clauses. Never return SAT
 // until the original complete CNF is checked.
 proof.candidate_model.reserve(f.n);
 for(int v=1;v<=f.n;v++) {
   bool truth=comp[lit_node(v)]>comp[lit_node(-v)];
   proof.candidate_model.push_back(truth?v:-v);
 }
 return proof;
}
static void emit_binary_proof(const ImplicationProof& p) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v153_binary_scc\","
     <<"\"verified\":true,\"variable\":"<<p.variable
     <<",\"path_pos_to_neg\":[";
 for(size_t i=0;i<p.path_pos_to_neg.size();i++)
   cout<<(i?",":"")<<p.path_pos_to_neg[i];
 cout<<"],\"path_neg_to_pos\":[";
 for(size_t i=0;i<p.path_neg_to_pos.size();i++)
   cout<<(i?",":"")<<p.path_neg_to_pos[i];
 cout<<"]}\n";
}
struct Xor10Result {
 vector<Eq> equations;
 vector<int> exhaustive_support;
 int candidate_groups=0;
 int widest=0;
};
static Xor10Result extract_xor10(const Cnf& f) {
 Xor10Result res;
 if(f.n>4096||f.clauses.size()>100000)return res;
 map<array<int,10>,bitset<1024>> patterns;
 for(const auto& cl:f.clauses) {
   if(cl.size()<2||cl.size()>10)continue;
   auto literals=cl;
   sort(literals.begin(),literals.end(),[](int a,int b){return abs(a)<abs(b);});
   array<int,10> support{};unsigned mask=0;bool valid=true;
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
   int width=0;while(width<10 && support[width])width++;
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
     <<"\"path\":\"v153_exhaustive_support\","
     <<"\"verified\":true,\"support\":[";
 for(size_t i=0;i<vars.size();i++)cout<<(i?",":"")<<vars[i];
 cout<<"],\"certificate\":\"all_support_assignments_excluded\"}\n";
}
// Exact complete pigeonhole/injection CNF for *any* birds/holes ratio.
// For birds>holes: impossibility certificate. For birds<=holes: construct
// one injective assignment using verified hole-clique components.
struct PhpGeneral {
 bool recognized=false,unsat=false;
 int holes=0,birds=0;
 vector<int> model;
};
static PhpGeneral pigeonhole_general(const Cnf& f) {
 PhpGeneral a;
 if(f.n>4096||f.clauses.size()>100000)return a;
 vector<vector<int>> positive;
 vector<array<int,2>> negative;
 for(const auto& cl:f.clauses){
   if(cl.size()>=2 && all_of(cl.begin(),cl.end(),[](int v){return v>0;}))
     positive.push_back(cl);
   else if(cl.size()==2 && cl[0]<0 && cl[1]<0 && cl[0]!=cl[1])
     negative.push_back({-cl[0],-cl[1]});
   else return a;
 }
 if(positive.size()<2)return a;
 const int birds=int(positive.size()),holes=int(positive[0].size());
 if(birds<2||holes<2||f.n!=birds*holes)return a;
 const size_t expected=size_t(holes)*birds*(birds-1)/2;
 if(negative.size()!=expected||negative.size()+positive.size()!=f.clauses.size())
   return a;
 vector<int> bird_of(f.n+1,-1);
 for(int b=0;b<birds;b++){
   if(int(positive[b].size())!=holes)return a;
   for(int v:positive[b]) {
     if(v<1||v>f.n||bird_of[v]>=0)return a;
     bird_of[v]=b;
   }
 }
 for(int v=1;v<=f.n;v++)if(bird_of[v]<0)return a;
 UnionFind uf(f.n);
 vector<int> degree(f.n+1,0);
 vector<uint64_t> edges;edges.reserve(negative.size());
 for(const auto& e:negative){
   int x=e[0],y=e[1];
   if(x<1||x>f.n||y<1||y>f.n||x==y||bird_of[x]==bird_of[y])return a;
   uf.join(x,y);degree[x]++;degree[y]++;
   edges.push_back((uint64_t(min(x,y))<<32)|uint64_t(max(x,y)));
 }
 sort(edges.begin(),edges.end());
 if(adjacent_find(edges.begin(),edges.end())!=edges.end())return a;
 for(int v=1;v<=f.n;v++)if(degree[v]!=birds-1)return a;
 map<int,vector<int>> components;
 for(int v=1;v<=f.n;v++)components[uf.find(v)].push_back(v);
 if(int(components.size())!=holes)return a;
 vector<vector<int>> groups;
 for(const auto& item:components){
   const auto& vars=item.second;
   if(int(vars.size())!=birds)return a;
   vector<char> seen(birds,0);
   for(int v:vars){
     int b=bird_of[v];
     if(seen[b])return a;
     seen[b]=1;
   }
   groups.push_back(vars);
 }
 a.recognized=true;a.birds=birds;a.holes=holes;
 if(birds>holes){a.unsat=true;return a;}
 vector<int> model;model.reserve(f.n);
 vector<char> is_true(f.n+1,0);
 // Hole h is unique; choose bird h's variable from each of the first
 // 'birds' hole cliques. Distinct cliques guarantee distinct holes.
 for(int b=0;b<birds;b++){
   int chosen=0;
   for(int v:groups[b])if(bird_of[v]==b){chosen=v;break;}
   if(!chosen)throw runtime_error("No hole matching variable");
   is_true[chosen]=1;
 }
 for(int v=1;v<=f.n;v++)model.push_back(is_true[v]?v:-v);
 if(!verify_model(f,model))throw runtime_error("PHP injection model not valid");
 a.model=move(model);
 return a;
}

// V15.2: generalized all-different/cardinality via Hall's theorem.
// The positive ALO clauses are disjoint "birds"; every all-negative
// binary clique is a "hole" with capacity 1. Domains may be unequal.
// Detection accepts extra residual CNF clauses, but any emitted UNSAT
// proof uses only the original ALO and original negative binary clauses.
// Successful matching produces SAT only after full-model validation.
struct HallResult {
 bool recognized=false,unsat=false;
 int birds=0,holes=0;
 vector<int> hall_birds,model;
};
static HallResult generalized_hall(const Cnf& f) {
 HallResult ans;
 if(f.n>4096||f.clauses.size()>100000)return ans;
 vector<vector<int>> birds;
 for(const auto& cl:f.clauses) {
   if(cl.size()>=3 && cl.size()<=32 &&
      all_of(cl.begin(),cl.end(),[](int x){return x>0;}))
     birds.push_back(cl);
 }
 if(birds.size()<3||birds.size()>512)return ans;
 vector<int> bird_of(f.n+1,-1),variables;
 for(int b=0;b<int(birds.size());b++) {
   for(int v:birds[b]) {
     if(v<1||v>f.n||bird_of[v]>=0)return ans;
     bird_of[v]=b;variables.push_back(v);
   }
 }
 if(variables.size()>4096)return ans;
 UnionFind uf(f.n);
 vector<pair<int,int>> negatives;
 for(const auto& cl:f.clauses) {
   if(cl.size()!=2||cl[0]>=0||cl[1]>=0)continue;
   int a=-cl[0],b=-cl[1];
   if(a==b||bird_of[a]<0||bird_of[b]<0)continue;
   if(bird_of[a]==bird_of[b])return ans;
   negatives.push_back({min(a,b),max(a,b)});
   uf.join(a,b);
 }
 sort(negatives.begin(),negatives.end());
 negatives.erase(unique(negatives.begin(),negatives.end()),negatives.end());
 map<int,vector<int>> resources;
 for(int v:variables)resources[uf.find(v)].push_back(v);
 if(resources.size()>4096)return ans;
 map<int,int> group_id;
 vector<vector<int>> groups;
 for(const auto& item:resources) {
   int index=int(groups.size());group_id[item.first]=index;
   groups.push_back(item.second);
   const auto& members=item.second;
   vector<int> used(birds.size(),0);
   for(int v:members)if(used[bird_of[v]]++)return ans;
 }
 // A connected negative component is a capacity-one hole ONLY if all
 // its original-variable pairs have explicit negative binary clauses.
 for(const auto& members:groups) {
   if(members.size()<2)continue;
   if(members.size()>64)return ans;
   for(size_t i=0;i<members.size();i++) {
     for(size_t j=i+1;j<members.size();j++) {
       int a=min(members[i],members[j]),b=max(members[i],members[j]);
       if(!binary_search(negatives.begin(),negatives.end(),make_pair(a,b)))
         return ans;
     }
   }
 }
 const int B=int(birds.size()),H=int(groups.size());
 vector<vector<int>> domain(B);
 vector<vector<int>> picked(B,vector<int>(H,0));
 for(int b=0;b<B;b++) {
   for(int v:birds[b]) {
     int h=group_id.at(uf.find(v));
     if(picked[b][h])return ans;
     picked[b][h]=v;domain[b].push_back(h);
   }
 }
 // Maximal bipartite matching proves a Hall deficiency when size < B.
 vector<int> owner(H,-1),match(B,-1);
 function<bool(int,vector<char>&)> dfs=[&](int b,vector<char>&seen) {
   for(int h:domain[b]) {
     if(seen[h])continue;
     seen[h]=1;
     if(owner[h]<0||dfs(owner[h],seen)) {
       owner[h]=b;match[b]=h;return true;
     }
   }
   return false;
 };
 int matched=0;
 for(int b=0;b<B;b++){
   vector<char> seen(H,0);
   if(dfs(b,seen))matched++;
 }
 ans.recognized=true;ans.birds=B;ans.holes=H;
 if(matched<B) {
   ans.unsat=true;
   vector<char> visited_b(B,0),visited_h(H,0);
   queue<int> q;
   for(int b=0;b<B;b++)if(match[b]<0){q.push(b);visited_b[b]=1;}
   while(!q.empty()) {
     int b=q.front();q.pop();
     for(int h:domain[b]) {
       if(visited_h[h])continue;
       visited_h[h]=1;
       if(owner[h]>=0 && !visited_b[owner[h]]) {
         visited_b[owner[h]]=1;q.push(owner[h]);
       }
     }
   }
   int covered=0;
   for(int b=0;b<B;b++)if(visited_b[b])ans.hall_birds.push_back(b);
   for(int h=0;h<H;h++)covered+=visited_h[h];
   if(ans.hall_birds.empty()||int(ans.hall_birds.size())<=covered)
     throw runtime_error("Hall witness extraction failed");
   return ans;
 }
 vector<char> is_true(f.n+1,0);
 for(int b=0;b<B;b++) {
   int h=match[b],v=picked[b][h];
   if(h<0||v<=0)throw runtime_error("Invalid matching choice");
   is_true[v]=1;
 }
 ans.model.reserve(f.n);
 for(int v=1;v<=f.n;v++)ans.model.push_back(is_true[v]?v:-v);
 if(!verify_model(f,ans.model))ans.model.clear();
 return ans;
}
static void emit_hall(const HallResult& h) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v153_hall_unsat\",\"verified\":true,"
     <<"\"birds\":"<<h.birds<<",\"holes\":"<<h.holes
     <<",\"hall_birds\":[";
 for(size_t i=0;i<h.hall_birds.size();i++)
   cout<<(i?",":"")<<h.hall_birds[i];
 cout<<"]}\n";
}

// Derive unit and binary parity clauses from a REDUCED GF(2) basis.
// Every new clause is implied by full-support XOR encodings in original CNF.
// Only a low-cost, bounded experiment on mixed CNF: never replace an
// original clause or trust an unverified SAT model.
static vector<vector<int>> xor_shortcuts(const vector<Eq>& equations,int n){
 vector<vector<int>> clauses;
 if(equations.size()<2||n>512||equations.size()>1024)return clauses;
 const int words=(n+63)/64;
 vector<Eq> pivot(n);
 vector<char> present(n,0);
 for(const Eq& source:equations){
   vector<uint64_t> bits=source.bits;
   int rhs=source.rhs;
   for(;;){
     int hi=highest(bits);
     if(hi<0)break;
     if(!present[hi]) {
       present[hi]=1;pivot[hi].bits=move(bits);
       pivot[hi].rhs=rhs;
       break;
     }
     xor_inplace(bits,pivot[hi].bits);
     rhs^=pivot[hi].rhs;
   }
 }
 // Clear pivot columns from higher rows; descending order ensures any
 // newly introduced lower pivot bit will be handled later.
 for(int low=n-1;low>=0;low--)if(present[low]){
   for(int high=low+1;high<n;high++)if(present[high]){
     if(bit(pivot[high].bits,low)){
       xor_inplace(pivot[high].bits,pivot[low].bits);
       pivot[high].rhs^=pivot[low].rhs;
     }
   }
 }
 for(int i=0;i<n;i++)if(present[i]){
   vector<int> variables;
   for(int k=0;k<words;k++){
     uint64_t w=pivot[i].bits[k];
     while(w){
       int j=64*k+__builtin_ctzll(w);
       if(j<n)variables.push_back(j+1);
       w&=w-1;
       if(variables.size()>2)break;
     }
     if(variables.size()>2)break;
   }
   if(variables.size()==1){
     int v=variables[0];
     clauses.push_back({pivot[i].rhs?v:-v});
   }else if(variables.size()==2){
     int x=variables[0],y=variables[1];
     if(pivot[i].rhs==0){
       clauses.push_back({-x,y});
       clauses.push_back({x,-y});
     }else{
       clauses.push_back({x,y});
       clauses.push_back({-x,-y});
     }
   }
   if(clauses.size()>=160)break;
 }
 return clauses;
}
static vector<vector<int>> implied_clauses(
       const Cnf& f,const Xor10Result& xr,const ImplicationProof& ip) {
 vector<vector<int>> out;
 if(f.n>512||f.clauses.size()>20000)return out;
 if(xr.equations.size()>=2)out=xor_shortcuts(xr.equations,f.n);
 for(const auto& pair:ip.equivalence_links){
   if(out.size()>200)break;
   int a=pair.first,b=pair.second;
   if(a==b||a==-b)continue;
   out.push_back({-a,b});
   out.push_back({a,-b});
 }
 // No reason to incur disk I/O for fewer than four useful consequences.
 if(out.size()<4)return {};
 set<vector<int>> known,unique;
 for(const auto& cl:f.clauses)
   if(cl.size()<=2){
     vector<int> sorted=cl;
     sort(sorted.begin(),sorted.end());
     known.insert(move(sorted));
   }
 vector<vector<int>> addition;
 for(auto clause:out) {
   sort(clause.begin(),clause.end());
   if(clause.size()==2 && clause[0]==-clause[1])continue;
   if(!known.count(clause)&&unique.insert(clause).second)
     addition.push_back(move(clause));
 }
 return addition.size()>=4?addition:vector<vector<int>>{};
}
// Kissat still sees every ORIGINAL clause. Added clauses only express
// logically implied GF(2) rows or binary SCC equivalences. A SAT output
// is therefore an assignment for the original variable numbering.
static bool try_augmented_kissat(char** argv,const Cnf& f,
                                const vector<vector<int>>& additions){
 if(additions.empty())return false;
 char filename[]="/tmp/drnas-v152-XXXXXX";
 int fd=mkstemp(filename);
 if(fd<0)return false;
 FILE* fp=fdopen(fd,"w");
 if(!fp){close(fd);unlink(filename);return false;}
 bool ok=fprintf(fp,"p cnf %d %zu\n",f.n,
                 f.clauses.size()+additions.size())>0;
 if(ok)for(const auto& cl:f.clauses){
   for(int v:cl)if(fprintf(fp,"%d ",v)<0){ok=false;break;}
   if(!ok||fprintf(fp,"0\n")<0){ok=false;break;}
 }
 if(ok)for(const auto& cl:additions){
   for(int v:cl)if(fprintf(fp,"%d ",v)<0){ok=false;break;}
   if(!ok||fprintf(fp,"0\n")<0){ok=false;break;}
 }
 if(fclose(fp)!=0)ok=false;
 if(!ok){unlink(filename);return false;}
 cout<<"DRNAS_V153_ROUTE\tkissat_augmented\t"<<additions.size()<<"\n"<<flush;
 char* av[]={argv[2],filename,nullptr};
 execv(av[0],av);
 unlink(filename);
 return false;
}

// V15.3: single GF(2) proof system for (1) extracted XOR CNF blocks,
// (2) ORIGINAL unit clauses and (3) equivalent literals proved by 2-SAT
// implication SCC paths. This derives cross-structure contradictions WITHOUT
// invoking Kissat. The proof checker independently validates every origin.
struct UnifiedOrigin {
 string kind;
 vector<int> vars;
 int rhs=0,clause_index=-1,lit_a=0,lit_b=0;
};
struct UnifiedResult {
 bool attempted=false,solved=false;
 Answer answer;
 vector<UnifiedOrigin> origins;
 int equations=0;
};
static vector<int> variables_from_eq(const Eq& eq,int n) {
 vector<int> result;
 for(int v=0;v<n;v++)if(bit(eq.bits,v))result.push_back(v+1);
 return result;
}
static UnifiedResult unified_linear(const Cnf& f,
       const vector<Eq>& xor_equations,const ImplicationProof& ip) {
 UnifiedResult result;
 if(xor_equations.empty()||f.n>512||xor_equations.size()>1024)
   return result;
 vector<Eq> eqs=xor_equations;
 vector<UnifiedOrigin> origins;
 for(const auto& eq:xor_equations) {
   UnifiedOrigin origin;
   origin.kind="xor";origin.vars=variables_from_eq(eq,f.n);
   origin.rhs=eq.rhs;
   origins.push_back(move(origin));
 }
 const int words=(f.n+63)/64;
 int n_units=0,n_equiv=0;
 for(int j=0;j<int(f.clauses.size());j++){
   const auto& cl=f.clauses[j];
   if(cl.size()!=1)continue;
   Eq eq;eq.bits.assign(words,0);
   int v=abs(cl[0])-1;eq.bits[v/64]|=1ULL<<(v%64);
   eq.rhs=(cl[0]>0);
   eqs.push_back(move(eq));
   UnifiedOrigin origin;origin.kind="unit";origin.clause_index=j;
   origins.push_back(move(origin));n_units++;
   if(n_units>=256)break;
 }
 set<pair<int,int>> used;
 for(const auto& link:ip.equivalence_links) {
   int a=link.first,b=link.second;
   if(abs(a)==abs(b))continue;
   pair<int,int> key={min(a,b),max(a,b)};
   if(!used.insert(key).second)continue;
   Eq eq;eq.bits.assign(words,0);
   int va=abs(a)-1,vb=abs(b)-1;
   eq.bits[va/64]^=1ULL<<(va%64);
   eq.bits[vb/64]^=1ULL<<(vb%64);
   eq.rhs=(a<0)^(b<0);
   eqs.push_back(move(eq));
   UnifiedOrigin origin;origin.kind="equiv";
   origin.lit_a=a;origin.lit_b=b;
   origins.push_back(move(origin));n_equiv++;
   if(n_equiv>=256)break;
 }
 if(!n_units&&!n_equiv)return result;
 result.attempted=true;
 try {
   result.answer=solve_exact(f,eqs);
   result.origins=move(origins);
   result.equations=int(eqs.size());
   result.solved=true;
 } catch(const exception&) {
   // SAT models from affine equations alone may violate residual CNF.
   // Never label the instance SAT or UNSAT on such a failure.
 }
 return result;
}
static vector<vector<int>> original_implication_graph(const Cnf& f) {
 vector<vector<int>> graph(f.n*2);
 for(const auto& cl:f.clauses) {
   if(cl.size()==1)
     graph[lit_node(-cl[0])].push_back(lit_node(cl[0]));
   else if(cl.size()==2) {
     graph[lit_node(-cl[0])].push_back(lit_node(cl[1]));
     graph[lit_node(-cl[1])].push_back(lit_node(cl[0]));
   }
 }
 return graph;
}
static void emit_unified_unsat(const Cnf& f,const UnifiedResult& u) {
 if(u.answer.status!="UNSAT"||u.answer.proof_rows.empty())
   throw runtime_error("Missing unified UNSAT GF(2) proof");
 vector<vector<int>> graph=original_implication_graph(f);
 // Do all verification BEFORE emitting an UNSAT result. An exception will
 // safely delegate to the original solver instead of publishing a bad proof.
 struct Row {
   int i=0;
   vector<int> ab,ba;
 };
 vector<Row> rows;
 for(int idx:u.answer.proof_rows){
   if(idx<0||idx>=int(u.origins.size()))
     throw runtime_error("Invalid unified proof origin index");
   Row row;row.i=idx;
   const auto& origin=u.origins[idx];
   if(origin.kind=="equiv"){
     row.ab=implication_path(lit_node(origin.lit_a),
                             lit_node(origin.lit_b),graph);
     row.ba=implication_path(lit_node(origin.lit_b),
                             lit_node(origin.lit_a),graph);
     if(row.ab.empty()||row.ba.empty())
       throw runtime_error("Cannot certify SCC equivalence row");
   }
   rows.push_back(move(row));
 }
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
     <<"\"path\":\"v153_unified_linear_unsat\","
     <<"\"verified\":true,\"rows\":[";
 for(size_t i=0;i<rows.size();i++) {
   const auto& row=rows[i];
   const auto& o=u.origins[row.i];
   if(i)cout<<",";
   if(o.kind=="unit")
     cout<<"{\"kind\":\"unit\",\"clause\":"<<o.clause_index<<"}";
   else if(o.kind=="xor") {
     cout<<"{\"kind\":\"xor\",\"vars\":[";
     for(size_t j=0;j<o.vars.size();j++)cout<<(j?",":"")<<o.vars[j];
     cout<<"],\"rhs\":"<<o.rhs<<"}";
   }else if(o.kind=="equiv"){
     cout<<"{\"kind\":\"equiv\",\"a\":"<<o.lit_a
         <<",\"b\":"<<o.lit_b<<",\"ab\":[";
     for(size_t j=0;j<row.ab.size();j++)
       cout<<(j?",":"")<<row.ab[j];
     cout<<"],\"ba\":[";
     for(size_t j=0;j<row.ba.size();j++)
       cout<<(j?",":"")<<row.ba[j];
     cout<<"]}";
   }else throw runtime_error("Unknown unified origin");
 }
 cout<<"]}\n";
}
static int kissat_fallback(char **argv) {
 char *av[]={argv[2],argv[1],nullptr};
 cout<<"DRNAS_V153_ROUTE\tkissat_direct\n"<<flush;
 execv(av[0],av);
 cerr<<"DRNAS_V153_ERROR Kissat exec failure\n";
 return 3;
}
int main(int argc,char**argv) {
 if(!(argc==4||(argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v1532_prefix INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   struct stat st{};
   if(stat(argv[1],&st)!=0 || st.st_size<=0 || st.st_size>16*1024*1024)
     return argc==5?(cout<<"DRNAS_V153_ROUTE\tkissat_direct\n",0):kissat_fallback(argv);
   // A miss sends the exact unmodified CNF to Kissat without full DRNAS
   // parsing/structural scans, avoiding the largest overhead on general SAT.
   if(argc==4 && !v1532_prefix_maybe_structured(argv[1])) {
     cout<<"DRNAS_V1532_ROUTE\tprefix_kissat_direct\n"<<flush;
     return kissat_fallback(argv);
   }
   Cnf f=parse(argv[1]);
   if(f.n>4096)
     return argc==5?(cout<<"DRNAS_V153_ROUTE\tkissat_direct\n",0):kissat_fallback(argv);
   // Classification is side-effect free and has no SAT/UNSAT answer.
   if(argc==5) {
     cout<<"DRNAS_V153_ROUTE\tstructural_analysis\n";
     return 0;
   }
   // The V15.3 core remains unchanged; only work-avoidance is new.
   V1531Signals signals=v1531_signals(f);
   const auto structural_start=std::chrono::steady_clock::now();
   const auto time_exceeded=[&](){
     return std::chrono::duration_cast<std::chrono::milliseconds>(
       std::chrono::steady_clock::now()-structural_start).count()>25;
   };
   if(!signals.units && !signals.binary && !signals.xor_candidate &&
      !signals.hall_candidate && !signals.php_candidate)
     return kissat_fallback(argv);
   UpProof up;
   if(signals.units)up=unit_propagate(f);
   if(up.unsat) {
     if(!verify_unit_proof(f,up))throw runtime_error("UP proof replay failed");
     emit_unit_proof(up);return 0;
   }
   if(up.has_unit && !up.model.empty()) {
     emit_sat(f,up.model,"v153_unit_model");return 0;
   }
   if(time_exceeded())return kissat_fallback(argv);
   ImplicationProof implication;
   if(signals.binary)implication=binary_scc_conflict(f);
   if(implication.variable>0) {
     emit_binary_proof(implication);return 0;
   }
   if(!implication.candidate_model.empty() &&
      verify_model(f,implication.candidate_model)) {
     emit_sat(f,implication.candidate_model,"v153_binary_sat_verified");
     return 0;
   }
   if(time_exceeded())return kissat_fallback(argv);
   Xor10Result xr;
   if(signals.xor_candidate)xr=extract_xor10(f);
   if(!xr.exhaustive_support.empty()) {
     emit_exhaustive_proof(xr.exhaustive_support);return 0;
   }
   if(!xr.equations.empty()) {
     try {
       UnifiedResult mixed=unified_linear(f,xr.equations,implication);
       if(mixed.solved) {
         if(mixed.answer.status=="UNSAT")
           emit_unified_unsat(f,mixed);
         else json_answer(mixed.answer,f.n,mixed.equations,
                          "v153_unified_sat_verified");
         return 0;
       }
       Answer a=solve_exact(f,xr.equations);
       json_answer(a,f.n,int(xr.equations.size()),
                   a.status=="UNSAT"?"v153_affine_unsat":"v153_affine_sat_verified");
       return 0;
     } catch(const exception&) {
       // A free-variable assignment can fail the residual CNF.
       // Never turn such a failure into a SAT/UNSAT classification.
     }
   }
   if(time_exceeded())return kissat_fallback(argv);
   HallResult hall;
   if(signals.hall_candidate)hall=generalized_hall(f);
   if(hall.recognized) {
     if(hall.unsat) {emit_hall(hall);return 0;}
     if(!hall.model.empty()) {
       emit_sat(f,hall.model,"v153_hall_sat_verified");return 0;
     }
   }
   if(time_exceeded())return kissat_fallback(argv);
   PhpGeneral php;
   if(signals.php_candidate)php=pigeonhole_general(f);
   if(php.recognized) {
     if(php.unsat)json_php(php.holes,php.birds);
     else emit_sat(f,php.model,"v153_php_sat_verified");
     return 0;
   }
   // Experimental cross-structure integration is only a preprocessing route.
   // The original clauses are retained for Kissat: no unsound extrapolation.
   // The augmented temporary-CNF route repeatedly rewrites the whole
   // formula and is counterproductive on normal CNF. Disabled by default.
   // Explicit opt-in keeps it available for controlled structural research.
   const char *augment=getenv("DRNAS_V1531_AUGMENT");
   if(augment && string(augment)=="1" && !time_exceeded()) {
     vector<vector<int>> additions=implied_clauses(f,xr,implication);
     if(!additions.empty())try_augmented_kissat(argv,f,additions);
   }
 } catch(const exception& e) {
   cerr<<"DRNAS_V153_FALLBACK "<<e.what()<<"\n";
 }
 return kissat_fallback(argv);
}

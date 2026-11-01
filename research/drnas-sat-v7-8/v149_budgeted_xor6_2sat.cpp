// DRNAS V14.9: bounded preflight, exact 2-SAT SCC and complete XOR2..XOR6
// subset certificates; strict, unchanged Kissat fallback on all unproved inputs.
// Structural pattern detection is not a prediction and never implies SAT/UNSAT.
// Every emitted SAT witness is checked against the ENTIRE original CNF.
#include "v142_fastgate.cpp"
#include <optional>
#include <queue>
#include <functional>

using Support149=std::array<int,6>;
static int width149(const Support149& k) {
 int w=0;while(w<6 && k[w])++w;return w;
}
static std::pair<uint64_t,uint64_t> parity_masks149(int w) {
 uint64_t even=0,odd=0;
 for(int i=0;i<(1<<w);++i) {
  if(__builtin_popcount(unsigned(i))&1)odd|=uint64_t(1)<<i;
  else even|=uint64_t(1)<<i;
 }
 return {even,odd};
}
static bool get_mask149(const std::vector<int>& cl,Support149& key,unsigned& mask) {
 if(cl.size()<2||cl.size()>6)return false;
 auto lits=cl;
 std::sort(lits.begin(),lits.end(),[](int a,int b){return abs(a)<abs(b);});
 key.fill(0);mask=0;
 for(size_t j=0;j<lits.size();++j) {
  key[j]=abs(lits[j]);
  if(!key[j] || (j && key[j-1]==key[j]))return false;
  if(lits[j]<0)mask|=1u<<j;
 }
 return true;
}
struct Gate149 {bool xor_candidate=false,two_sat_candidate=false,php_candidate=false;};
static Gate149 preflight149(const std::string& name) {
 Gate149 g;
 struct stat st{};
 if(stat(name.c_str(),&st)!=0||st.st_size<=0||st.st_size>24*1024*1024)return g;
 std::ifstream in(name);
 if(!in)return g;
 const int cap=st.st_size>2*1024*1024?512:2048;
 const size_t max_bytes=st.st_size>2*1024*1024?64*1024:256*1024;
 std::map<Support149,uint64_t> masks;
 std::vector<int> pending;
 int clauses=0;bool all_two=true,php=true;
 size_t bytes=0;
 std::string line;
 while(clauses<cap&&bytes<max_bytes&&std::getline(in,line)) {
  bytes+=line.size()+1;
  std::istringstream ss(line);std::string token;
  if(!(ss>>token)||token=="c"||token=="p"||token=="%")continue;
  do {
   if(token=="c")break;
   char *end=nullptr;errno=0;
   long v=strtol(token.c_str(),&end,10);
   if(errno||end==token.c_str()||*end||v>100000||v< -100000)return {};
   if(v) {
    pending.push_back(int(v));
    if(pending.size()>4096)return {};
    continue;
   }
   if(pending.empty())return {};
   ++clauses;
   if(pending.size()>2)all_two=false;
   if(!((pending.size()>=3 && std::all_of(pending.begin(),pending.end(),[](int x){return x>0;})) ||
        (pending.size()==2 && pending[0]<0 && pending[1]<0)))php=false;
   Support149 key{};unsigned mask=0;
   if(get_mask149(pending,key,mask)) {
    uint64_t &seen=masks[key];seen|=(uint64_t(1)<<mask);
    auto [even,odd]=parity_masks149(width149(key));
    if(seen==even || seen==odd)g.xor_candidate=true;
   }
   pending.clear();
   if(g.xor_candidate)break;
   if(clauses>=256&&all_two)break;
  }while(ss>>token&&clauses<cap);
  if(g.xor_candidate || (clauses>=256&&all_two))break;
 }
 g.two_sat_candidate=all_two&&clauses>=2;
 // PHP exact recognition is never attempted based on a handful of clauses
 // from a 2-SAT or XOR-majority input.
 g.php_candidate=php&&clauses>=4&&!g.two_sat_candidate;
 return g;
}

// Fully populated support groups are logical consequences of the original
// clauses. Additional constraints, duplicates, and other widths are ignored.
// A GF(2) contradiction among those consequences implies full CNF UNSAT.
static bool subset_xor6_149(const Cnf& f,std::vector<Eq>& rows) {
 rows.clear();
 if(f.n<1||f.n>4096||f.clauses.size()>100000)return false;
 std::map<Support149,uint64_t> groups;
 for(const auto& cl:f.clauses) {
  Support149 key{};unsigned mask=0;
  if(!get_mask149(cl,key,mask))continue;
  groups[key]|=uint64_t(1)<<mask;
  if(groups.size()>4096)return false;
 }
 const int words=(f.n+63)/64;
 for(const auto& [key,mask]:groups) {
  const int w=width149(key);
  auto [even,odd]=parity_masks149(w);
  if(mask!=even&&mask!=odd)continue;
  Eq e;e.bits.assign(words,0);
  e.rhs=(mask==even)?1:0;
  for(int j=0;j<w;++j) {
   int b=key[j]-1;
   if(b<0||b>=f.n)return false;
   e.bits[b/64]|=uint64_t(1)<<(b%64);
  }
  rows.push_back(std::move(e));
 }
 return !rows.empty();
}
static int node149(int lit) {
 return 2*(abs(lit)-1)+int(lit<0);
}
static int lit149(int id) {
 return (id&1)?-(id/2+1):(id/2+1);
}
struct TwoSAT149 {
 Answer answer;
 std::vector<int> path_a,path_b;
 int bad_var=0;
};
static std::optional<TwoSAT149> solve_2sat149(const Cnf& f) {
 if(f.n<1||f.n>4096||f.clauses.empty()||f.clauses.size()>100000)return {};
 const int size=2*f.n;
 std::vector<std::vector<int>> adj(size),rev(size);
 auto add=[&](int a,int b) {
  int u=node149(-a),v=node149(b);
  adj[u].push_back(v);rev[v].push_back(u);
 };
 for(const auto& cl:f.clauses) {
  if(cl.size()==1)add(cl[0],cl[0]);
  else if(cl.size()==2){add(cl[0],cl[1]);add(cl[1],cl[0]);}
  else return {};
 }
 std::vector<unsigned char> seen(size,0);
 std::vector<int> order;order.reserve(size);
 // Nonrecursive Kosaraju avoids stack overflow.
 for(int root=0;root<size;++root)if(!seen[root]) {
  std::vector<std::pair<int,size_t>> stack{{root,0}};
  seen[root]=1;
  while(!stack.empty()) {
   auto &cur=stack.back();
   if(cur.second<adj[cur.first].size()) {
    int v=adj[cur.first][cur.second++];
    if(!seen[v]){seen[v]=1;stack.push_back({v,0});}
   } else {order.push_back(cur.first);stack.pop_back();}
  }
 }
 std::vector<int> comp(size,-1);int components=0;
 for(auto it=order.rbegin();it!=order.rend();++it)if(comp[*it]<0) {
  std::vector<int> stack{*it};comp[*it]=components;
  while(!stack.empty()) {
   int u=stack.back();stack.pop_back();
   for(int v:rev[u])if(comp[v]<0){comp[v]=components;stack.push_back(v);}
  }
  ++components;
 }
 TwoSAT149 result;
 for(int v=0;v<f.n;++v)if(comp[2*v]==comp[2*v+1]) {
  // Independently replayable implication cycles x -> ~x -> x,
  // with every directed edge exactly induced by an original 1/2 clause.
  auto path=[&](int start,int goal) {
   std::vector<int> parent(size,-1),q;
   parent[start]=start;q.push_back(start);
   for(size_t i=0;i<q.size()&&parent[goal]<0;++i)
    for(int to:adj[q[i]])if(parent[to]<0) {
      parent[to]=q[i];q.push_back(to);
    }
   if(parent[goal]<0)throw std::runtime_error("2SAT missing implication path");
   std::vector<int> result_path;
   for(int at=goal;at!=start;at=parent[at])result_path.push_back(lit149(at));
   result_path.push_back(lit149(start));
   std::reverse(result_path.begin(),result_path.end());
   return result_path;
  };
  result.answer.status="UNSAT";result.bad_var=v+1;
  result.path_a=path(2*v,2*v+1);
  result.path_b=path(2*v+1,2*v);
  return result;
 }
 std::vector<uint8_t> assignment(f.n,0);
 for(int v=0;v<f.n;++v)assignment[v]=comp[2*v]>comp[2*v+1];
 // Enforce complete original-CNF model validation before emitting SAT.
 for(const auto& cl:f.clauses) {
  bool ok=false;
  for(int lit:cl)if(bool(assignment[abs(lit)-1])==(lit>0)){ok=true;break;}
  if(!ok)throw std::runtime_error("2SAT model did not satisfy full CNF");
 }
 result.answer.status="SAT";
 for(int i=0;i<f.n;++i)result.answer.model.push_back(assignment[i]?i+1:-(i+1));
 return result;
}
static void print_2sat149(const TwoSAT149& r,int n) {
 if(r.answer.status=="SAT") {
  json_answer(r.answer,n,0,"two_sat_scc");return;
 }
 std::cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
          <<"\"path\":\"two_sat_scc\",\"verified\":true,"
          <<"\"variables\":"<<n<<",\"variable\":"<<r.bad_var
          <<",\"implication_paths\":[";
 auto emit=[](const std::vector<int>& p) {
  std::cout<<"[";
  for(size_t i=0;i<p.size();++i)std::cout<<(i?",":"")<<p[i];
  std::cout<<"]";
 };
 emit(r.path_a);std::cout<<",";emit(r.path_b);
 std::cout<<"]}\n";
}
int main(int argc,char**argv) {
 if(argc!=4) {
  std::cerr<<"Usage: v149_budgeted INPUT_CNF KISSAT_BINARY SEED\n";return 2;
 }
 const std::string cnf=argv[1],kissat=argv[2];
 Gate149 gate=preflight149(cnf);
 if(gate.xor_candidate||gate.two_sat_candidate||gate.php_candidate) {
  try {
   Cnf f=parse(cnf);
   if(gate.two_sat_candidate) {
    auto result=solve_2sat149(f);
    if(result) {print_2sat149(*result,f.n);return 0;}
   }
   if(gate.xor_candidate) {
    std::vector<Eq> rows;
    if(subset_xor6_149(f,rows)) {
     Answer answer=solve_exact(f,rows);
     json_answer(answer,f.n,int(rows.size()),"affine_subset_xor6");
     return 0;
    }
   }
   if(gate.php_candidate) {
    int holes=0,birds=0;
    if(complete_php_proof(f,holes,birds)) {
     json_php(holes,birds);return 0;
    }
   }
  }catch(const std::exception&) {
   // No incorrect claim escapes a failed recognizer, model or proof.
  }
 }
 std::cout<<"DRNAS_V149_ROUTE\tkissat_direct\n"<<std::flush;
 char *av[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(cnf.c_str()),nullptr};
 execv(av[0],av);
 std::cerr<<"DRNAS_V149_ERROR execv Kissat failed "<<errno<<"\n";
 return 3;
}

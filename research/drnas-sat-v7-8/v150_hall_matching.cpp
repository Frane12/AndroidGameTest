// DRNAS V15.0 EXPERIMENTAL: generalized Hall-deficiency certificate for SAT.
// This is deliberately NOT XOR, 2-SAT or phase/LBD tuning.
// From original positive ALO clauses (demands) and pairwise negative AMO
// clauses (mutually exclusive resources) prove Hall's |N(S)| < |S|.
// All proofs contain original clause indices + original-variable cliques.
// Certified SAT models are accepted only after checking the entire CNF.
// Every unrecognized/mixed case executes the identical Kissat binary.
// Known bipartite matching/Hall theory; no claim of new complexity theorem.
#define main drnas_v140_hidden_entry
#include "v140_native_hybrid.cpp"
#undef main
#include <unordered_map>
#include <unordered_set>
#include <numeric>
#include <functional>
#include <queue>

static uint64_t key150(int a,int b) {
 if(a>b)std::swap(a,b);
 return (uint64_t(unsigned(a))<<32)|unsigned(b);
}
static bool preflight150(const std::string& cnf) {
 struct stat st{};
 if(stat(cnf.c_str(),&st)!=0||st.st_size<=0||st.st_size>12*1024*1024)return false;
 std::ifstream in(cnf);
 if(!in)return false;
 int positive=0,negative=0,seen=0;
 size_t bytes=0;
 std::vector<int> pending;
 std::string line;
 while(seen<1024&&bytes<180*1024&&std::getline(in,line)) {
  bytes+=line.size()+1;
  std::istringstream ss(line);std::string token;
  if(!(ss>>token)||token=="p"||token=="c"||token=="%")continue;
  do {
   if(token=="c")break;
   char* end=nullptr;errno=0;
   long x=strtol(token.c_str(),&end,10);
   if(errno||end==token.c_str()||*end||std::abs(x)>100000)return false;
   if(x) {
    pending.push_back(int(x));
    if(pending.size()>64)return false;
   } else {
    if(pending.empty())return false;
    ++seen;
    if(pending.size()>=2&&pending.size()<=32 &&
       std::all_of(pending.begin(),pending.end(),[](int v){return v>0;}))++positive;
    if(pending.size()==2&&pending[0]<0&&pending[1]<0 &&
       pending[0]!=pending[1])++negative;
    pending.clear();
    if(positive>=3&&negative>=3)return true;
   }
  }while(ss>>token&&seen<1024);
 }
 return false;
}
struct Hall150 {
 struct Row {
  int clause_idx=-1;
  std::vector<int> variables, resources;
 };
 int resources=0;
 std::vector<Row> rows;
 std::vector<std::vector<int>> members;
 std::vector<int> matched_resource;
 std::vector<int> witness_rows;
 std::vector<std::vector<int>> witness_groups;
};
static bool extract_hall150(const Cnf& f,Hall150& out) {
 if(f.n<1||f.n>4096||f.clauses.size()>100000)return false;
 struct DSU {
  std::vector<int> p,sz;
  explicit DSU(int n):p(n+1),sz(n+1,1) {std::iota(p.begin(),p.end(),0);}
  int find(int x){while(p[x]!=x){p[x]=p[p[x]];x=p[x];}return x;}
  void join(int a,int b) {
   a=find(a);b=find(b);if(a==b)return;
   if(sz[a]<sz[b])std::swap(a,b);
   p[b]=a;sz[a]+=sz[b];
  }
 } dsu(f.n);
 std::unordered_set<uint64_t> negative;
 std::vector<Hall150::Row> candidates;
 // Only INPUT clauses are considered. Other constraints can be ignored for
 // UNSAT entailment but must be checked for any SAT model.
 for(int i=0;i<int(f.clauses.size());++i) {
  const auto& c=f.clauses[i];
  if(c.size()==2&&c[0]<0&&c[1]<0&&c[0]!=c[1]) {
   int a=-c[0],b=-c[1];
   negative.insert(key150(a,b));
   dsu.join(a,b);
  }
  if(c.size()<2||c.size()>32)continue;
  bool positive=true;
  std::vector<int> check=c;
  std::sort(check.begin(),check.end());
  if(std::adjacent_find(check.begin(),check.end())!=check.end())positive=false;
  if(positive&&std::all_of(c.begin(),c.end(),[](int lit){return lit>0;})) {
   Hall150::Row row;row.clause_idx=i;row.variables=c;
   candidates.push_back(std::move(row));
   if(candidates.size()>2048)return false;
  }
 }
 if(negative.size()<3||candidates.size()<3)return false;
 // Select disjoint original demand clauses. This is conservative and avoids
 // counting one TRUE variable as satisfying multiple demands.
 std::vector<char> used(f.n+1,0);
 out.rows.clear();
 for(auto& row:candidates) {
  bool disjoint=true;
  for(int v:row.variables)if(used[v]){disjoint=false;break;}
  if(!disjoint)continue;
  for(int v:row.variables)used[v]=1;
  out.rows.push_back(std::move(row));
  if(out.rows.size()>384)return false;
 }
 if(out.rows.size()<3)return false;
 std::unordered_map<int,int> ids;
 std::vector<int> root_of(f.n+1,-1);
 for(const auto& row:out.rows)for(int v:row.variables) {
  int root=dsu.find(v);
  if(!ids.count(root)) {
   int id=int(ids.size());ids[root]=id;
  }
  root_of[v]=ids.at(root);
 }
 out.resources=int(ids.size());
 if(out.resources<1||out.resources>4096)return false;
 out.members.assign(out.resources,{});
 // A component is used as a resource only if the participating variables
 // are pairwise forbidden by ORIGINAL negative binary clauses.
 for(const auto& row:out.rows)for(int v:row.variables) {
  out.members[root_of[v]].push_back(v);
 }
 for(auto& members:out.members) {
  std::sort(members.begin(),members.end());
  members.erase(std::unique(members.begin(),members.end()),members.end());
  if(members.size()>64)return false;
  for(size_t i=0;i<members.size();++i)
   for(size_t j=i+1;j<members.size();++j)
    if(!negative.count(key150(members[i],members[j])))return false;
 }
 // Build the bipartite graph (demand row -> disjoint AMO resource).
 std::vector<std::vector<int>> adj(out.rows.size());
 for(size_t r=0;r<out.rows.size();++r) {
  for(int v:out.rows[r].variables)adj[r].push_back(root_of[v]);
  std::sort(adj[r].begin(),adj[r].end());
  adj[r].erase(std::unique(adj[r].begin(),adj[r].end()),adj[r].end());
  if(adj[r].empty())return false;
 }
 std::vector<int> matched_col(out.resources,-1);
 out.matched_resource.assign(out.rows.size(),-1);
 std::function<bool(int,std::vector<char>&)> augment=[&](int row,std::vector<char>& visited)->bool {
  for(int col:adj[row]) {
   if(visited[col])continue;
   visited[col]=1;
   if(matched_col[col]<0||augment(matched_col[col],visited)) {
    matched_col[col]=row;
    out.matched_resource[row]=col;
    return true;
   }
  }
  return false;
 };
 int matched=0;
 for(int r=0;r<int(out.rows.size());++r) {
  std::vector<char> visited(out.resources,0);
  if(augment(r,visited))++matched;
 }
 if(matched==int(out.rows.size())) {
  out.witness_rows.clear();out.witness_groups.clear();
  return true;
 }
 // Alternating reachable rows from all unmatched demands provide an
 // independently checkable Hall-deficient S: |N(S)| < |S|.
 std::vector<char> seen_row(out.rows.size(),0),seen_col(out.resources,0);
 std::queue<int> q;
 for(int r=0;r<int(out.rows.size());++r)
  if(out.matched_resource[r]<0){seen_row[r]=1;q.push(r);}
 while(!q.empty()) {
  int r=q.front();q.pop();
  for(int col:adj[r])if(!seen_col[col]) {
   seen_col[col]=1;
   if(matched_col[col]>=0&&!seen_row[matched_col[col]]) {
    seen_row[matched_col[col]]=1;q.push(matched_col[col]);
   }
  }
 }
 out.witness_rows.clear();out.witness_groups.clear();
 for(int r=0;r<int(out.rows.size());++r)
  if(seen_row[r])out.witness_rows.push_back(r);
 for(int col=0;col<out.resources;++col)
  if(seen_col[col]) {
   std::vector<int> involved;
   for(int r:out.witness_rows)
    for(int v:out.rows[r].variables)if(root_of[v]==col)involved.push_back(v);
   std::sort(involved.begin(),involved.end());
   involved.erase(std::unique(involved.begin(),involved.end()),involved.end());
   if(involved.empty())return false;
   out.witness_groups.push_back(std::move(involved));
  }
 if(out.witness_groups.size()>=out.witness_rows.size() ||
    out.witness_rows.empty())return false;
 return true;
}
static void emit_hall150(const Hall150& h) {
 std::cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\",\"path\":\"hall_deficiency_exact\","
          <<"\"verified\":true,\"hall_rows\":[";
 for(size_t j=0;j<h.witness_rows.size();++j)
  std::cout<<(j?",":"")<<h.rows[h.witness_rows[j]].clause_idx;
 std::cout<<"],\"resource_groups\":[";
 for(size_t i=0;i<h.witness_groups.size();++i) {
  if(i)std::cout<<",";
  std::cout<<"[";
  for(size_t j=0;j<h.witness_groups[i].size();++j)
   std::cout<<(j?",":"")<<h.witness_groups[i][j];
  std::cout<<"]";
 }
 std::cout<<"],\"deficiency\":"<<(h.witness_rows.size()-h.witness_groups.size())<<"}\n";
}
static bool full_model150(const Cnf& f,const Hall150& h,std::vector<int>& model) {
 std::vector<unsigned char> assign(f.n+1,0);
 std::unordered_set<int> duplicate;
 for(size_t r=0;r<h.rows.size();++r) {
  int col=h.matched_resource[r];
  if(col<0)return false;
  int chosen=0;
  for(int v:h.rows[r].variables) {
   if(std::binary_search(h.members[col].begin(),h.members[col].end(),v)) {
    chosen=v;break;
   }
  }
  if(!chosen||!duplicate.insert(chosen).second)return false;
  assign[chosen]=1;
 }
 for(const auto& cl:f.clauses) {
  bool satisfied=false;
  for(int lit:cl)if((assign[abs(lit)]!=0)==(lit>0)){satisfied=true;break;}
  if(!satisfied)return false;
 }
 model.clear();
 for(int v=1;v<=f.n;++v)model.push_back(assign[v]?v:-v);
 return true;
}
int main(int argc,char**argv) {
 if(argc!=4){std::cerr<<"Usage: v150_hall INPUT_CNF KISSAT_BINARY SEED\n";return 2;}
 const std::string input=argv[1],kissat=argv[2];
 if(preflight150(input)) {
  try {
   Cnf f=parse(input);
   Hall150 hall;
   if(extract_hall150(f,hall)) {
    if(!hall.witness_rows.empty()) {
     emit_hall150(hall);
     return 0;
    }
    std::vector<int> model;
    if(full_model150(f,hall,model)) {
     Answer a;a.status="SAT";a.model=std::move(model);
     json_answer(a,f.n,0,"hall_matching_full_model");
     return 0;
    }
   }
  }catch(const std::exception& e) {
   std::cerr<<"DRNAS_V150_FALLBACK\t"<<e.what()<<"\n";
  }
 }
 std::cout<<"DRNAS_V150_ROUTE\tkissat_direct\n"<<std::flush;
 char *av[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(input.c_str()),nullptr};
 execv(av[0],av);
 std::cerr<<"DRNAS_V150_ERROR Kissat exec failed "<<errno<<"\n";
 return 3;
}

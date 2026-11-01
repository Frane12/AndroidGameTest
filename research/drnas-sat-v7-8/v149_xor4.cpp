// V14.9: selective structural gate + V14.8 certified solver and Kissat fallback.
#include "v142_fastgate.cpp"

// Pure structural preflight. Never returns a SAT/UNSAT classification.
// Read no more than 96 clauses and 8192 input bytes. Repeated *distinct*
// sign patterns on the same support indicate a potentially affine block.
// Missing a block is safe: the untouched Kissat solves that instance.
static bool selective_xor_gate(const string& path) {
 struct stat st{};
 if(stat(path.c_str(),&st) || st.st_size<=0 || st.st_size>16*1024*1024)
   return false;
 ifstream in(path);
 if(!in)return false;
 map<array<int,4>,uint16_t> groups;
 vector<int> clause;
 string tok;
 int clauses=0,nvars=0;
 while(clauses<96 && (in>>tok)) {
   const auto position=in.tellg();
   if(position>=0 && position>8192)return false;
   if(tok=="c" || tok=="%") {string ignored;getline(in,ignored);continue;}
   if(tok=="p") {
     string header;getline(in,header);istringstream hs(header);
     string format;int vars;
     if(hs>>format>>vars && format=="cnf")nvars=vars;
     if(nvars>4096)return false;
     continue;
   }
   char* end=nullptr;errno=0;
   long value=strtol(tok.c_str(),&end,10);
   if(errno||end==tok.c_str()||*end||value>100000||value<-100000)
     return false;
   if(value) {
     clause.push_back(int(value));
     if(clause.size()>4)return false;
     continue;
   }
   clauses++;
   if(clause.empty())return false;
   array<int,4> support{};
   sort(clause.begin(),clause.end(),[](int a,int b){return abs(a)<abs(b);});
   bool valid=true;unsigned mask=0;
   for(size_t j=0;j<clause.size();++j) {
     support[j]=abs(clause[j]);
     if(j && support[j]==support[j-1])valid=false;
     if(clause[j]<0)mask|=1u<<j;
   }
   if(valid) {
     auto& patterns=groups[support];
     patterns|=uint16_t(1u<<mask);
     const int width=int(clause.size());
     const int distinct=__builtin_popcount(unsigned(patterns));
     const int threshold=width<=2?2:width==3?3:5;
     if(distinct>=threshold)return true;
   }
   clause.clear();
 }
 return false;
}

static bool extract_partial_xor(const Cnf& f, vector<Eq>& out, vector<int>& exhausted) {
 if(f.n>4096 || f.clauses.size()>100000) return false;
 map<array<int,4>,uint16_t> patterns;
 for(const auto& cl:f.clauses) {
   if(cl.empty() || cl.size()>4)continue;
   auto literals=cl;
   sort(literals.begin(),literals.end(),[](int a,int b){return abs(a)<abs(b);});
   array<int,4> support{};unsigned mask=0;bool valid=true;
   for(size_t j=0;j<literals.size();j++) {
     support[j]=abs(literals[j]);
     if(j && support[j]==support[j-1]){valid=false;break;}
     if(literals[j]<0)mask|=1u<<j;
   }
   if(valid)patterns[support]|=uint16_t(1u<<mask);
 }
 const int words=(f.n+63)/64;
 for(const auto& entry:patterns) {
   const auto& support=entry.first;
   unsigned forbidden=entry.second;
   int width=0;while(width<4 && support[width])width++;
   if(width<1)continue;
   unsigned all=(1u<<(1u<<width))-1u;
   unsigned allowed=all & ~forbidden;
   if(!allowed) {
     // All assignments are excluded by original CNF clauses on this support.
     exhausted.assign(support.begin(),support.begin()+width);
     return true;
   }
   int parity=-1;
   for(unsigned assignment=0;assignment<(1u<<width);assignment++) {
     if(!(allowed & (1u<<assignment)))continue;
     int p=__builtin_popcount(assignment)&1;
     if(parity<0)parity=p;
     else if(parity!=p){parity=-2;break;}
   }
   if(parity<0)continue;
   Eq eq;eq.bits.assign(words,0);eq.rhs=parity;
   for(int j=0;j<width;j++) {
     int v=support[j]-1;eq.bits[v/64]|=1ULL<<(v%64);
   }
   out.push_back(move(eq));
 }
 return !out.empty();
}

int main(int argc,char**argv) {
 if(argc!=4 && !(argc==5 && string(argv[4])=="--classify-only")) {
   cerr<<"Usage: v149_xor4 INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   const string cnf=argv[1],kissat=argv[2];
   if(!selective_xor_gate(cnf)) {
     if(argc==5){cout<<"DRNAS_V149_ROUTE\tkissat_direct\n";return 0;}
     char *av[]={const_cast<char*>(argv[2]),const_cast<char*>(argv[1]),nullptr};
     execv(av[0],av);
     throw runtime_error("Kissat exec failure on direct route");
   }
   Cnf f=parse(cnf);vector<Eq> equations;vector<int> exhausted;
   if(extract_partial_xor(f,equations,exhausted)) {
     if(!exhausted.empty()) {
       cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
           <<"\"path\":\"v149_exhaustive_support\","
           <<"\"verified\":true,\"support\":[";
       for(size_t j=0;j<exhausted.size();j++)
         cout<<(j?",":"")<<exhausted[j];
       cout<<"],\"certificate\":\"all_support_assignments_excluded\"}\n";
       return 0;
     }
     Answer a=solve_exact(f,equations);
     if(a.status=="UNSAT") {
       json_answer(a,f.n,int(equations.size()),"v149_partial_xor_unsat");
       return 0;
     }
     // SAT from a subset of constraints is NOT enough; solve_exact verifies
     // the full original CNF before returning SAT. If verification fails,
     // catch below and delegate to Kissat.
     json_answer(a,f.n,int(equations.size()),"v149_partial_xor_sat_verified");
     return 0;
   }
 } catch(const exception& e) {
   cerr<<"DRNAS_V149_FALLBACK "<<e.what()<<"\n";
 }
 if(argc==5){cout<<"DRNAS_V149_ROUTE\tkissat_direct\n";return 0;}
 char *av[]={const_cast<char*>(argv[2]),const_cast<char*>(argv[1]),nullptr};
 execv(av[0],av);
 cerr<<"DRNAS_V149_ERROR Kissat exec failure\n";
 return 3;
}

// V14.8: exhaustive-local-conflict UNSAT certificate; verified SAT or fallback.
#include "v142_fastgate.cpp"

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
   cerr<<"Usage: v148_xor4 INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   const string cnf=argv[1],kissat=argv[2];
   Cnf f=parse(cnf);vector<Eq> equations,exhausted;
   if(extract_partial_xor(f,equations,exhausted)) {
     if(!exhausted.empty()) {
       cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
           <<"\"path\":\"v148_exhaustive_support\","
           <<"\"verified\":true,\"support\":[";
       for(size_t j=0;j<exhausted.size();j++)
         cout<<(j?",":"")<<exhausted[j];
       cout<<"],\"certificate\":\"all_support_assignments_excluded\"}\n";
       return 0;
     }
     Answer a=solve_exact(f,equations);
     if(a.status=="UNSAT") {
       json_answer(a,f.n,int(equations.size()),"v148_partial_xor_unsat");
       return 0;
     }
     // SAT from a subset of constraints is NOT enough; solve_exact verifies
     // the full original CNF before returning SAT. If verification fails,
     // catch below and delegate to Kissat.
     json_answer(a,f.n,int(equations.size()),"v148_partial_xor_sat_verified");
     return 0;
   }
 } catch(const exception& e) {
   cerr<<"DRNAS_V148_FALLBACK "<<e.what()<<"\n";
 }
 if(argc==5){cout<<"DRNAS_V148_ROUTE\tkissat_direct\n";return 0;}
 char *av[]={const_cast<char*>(argv[2]),const_cast<char*>(argv[1]),nullptr};
 execv(av[0],av);
 cerr<<"DRNAS_V148_ERROR Kissat exec failure\n";
 return 3;
}

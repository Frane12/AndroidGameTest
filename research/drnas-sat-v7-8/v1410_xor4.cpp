// V14.10: stratified structural gate; certified XOR solver or unchanged Kissat.
#include "v142_fastgate.cpp"

// Pure structural preflight. Never returns a SAT/UNSAT classification.
// Inspect bounded windows across the file. Repeated *distinct*
// sign patterns on the same support indicate a potentially affine block.
// Missing a block is safe: the untouched Kissat solves that instance.
static bool selective_xor_gate(const string& path) {
 struct stat st{};
 if(stat(path.c_str(),&st) || st.st_size<=0 || st.st_size>16*1024*1024)
   return false;
 ifstream in(path,ios::binary);
 if(!in)return false;
 // Sample across the file, not only its header. In some CNFs affine blocks
 // occur after a long prefix of generic clauses. The gate does not classify
 // SAT/UNSAT: false negatives and false positives both remain sound.
 map<array<int,4>,uint16_t> groups;
 int nvars=0,repeated_supports=0;
 const long long bytes=st.st_size;
 vector<long long> offsets={0,bytes/3,(2*bytes)/3,max(0LL,bytes-5500)};
 sort(offsets.begin(),offsets.end());
 offsets.erase(unique(offsets.begin(),offsets.end()),offsets.end());
 for(long long start:offsets) {
   in.clear();in.seekg(start);
   if(!in)return false;
   string line;
   if(start>0)getline(in,line); // Discard incomplete first line.
   int inspected=0;size_t read_bytes=0;
   while(inspected<96 && read_bytes<6500 && getline(in,line)) {
     read_bytes+=line.size()+1;
     istringstream ss(line);
     string token;
     if(!(ss>>token))continue;
     if(token=="c"||token=="%")continue;
     if(token=="p") {
       string kind;int vars=0;
       if((ss>>kind>>vars) && kind=="cnf")nvars=vars;
       if(nvars>4096)return false;
       continue;
     }
     vector<int> cl;
     do {
       char* end=nullptr;errno=0;
       long v=strtol(token.c_str(),&end,10);
       if(errno||end==token.c_str()||*end||v>100000||v< -100000)
         return false;
       if(v) {
         cl.push_back(int(v));
         if(cl.size()>4)break;
       } else {
         inspected++;
         if(!cl.empty() && cl.size()<=4) {
           sort(cl.begin(),cl.end(),[](int x,int y){return abs(x)<abs(y);});
           array<int,4> support{};
           unsigned mask=0;bool valid=true;
           for(size_t j=0;j<cl.size();j++) {
             support[j]=abs(cl[j]);
             if(j && support[j]==support[j-1])valid=false;
             if(cl[j]<0)mask|=1u<<j;
           }
           if(valid) {
             auto& patterns=groups[support];
             const int old_count=__builtin_popcount(unsigned(patterns));
             patterns|=uint16_t(1u<<mask);
             const int distinct=__builtin_popcount(unsigned(patterns));
             const int width=int(cl.size());
             const int threshold=width<=2?2:width==3?3:5;
             if(distinct>=threshold)return true;
             if(old_count==1 && distinct==2 && width>=3)
               repeated_supports++;
             // On large-variable inputs, multiple different sign patterns
             // on separate supports are unlikely in uniform random 3-SAT.
             if(nvars>=128 && repeated_supports>=3)return true;
           }
         }
         cl.clear();
       }
     } while(ss>>token);
   }
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
   cerr<<"Usage: v1410_xor4 INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   const string cnf=argv[1],kissat=argv[2];
   if(!selective_xor_gate(cnf)) {
     if(argc==5){cout<<"DRNAS_V1410_ROUTE\tkissat_direct\n";return 0;}
     char *av[]={const_cast<char*>(argv[2]),const_cast<char*>(argv[1]),nullptr};
     execv(av[0],av);
     throw runtime_error("Kissat exec failure on direct route");
   }
   Cnf f=parse(cnf);vector<Eq> equations;vector<int> exhausted;
   if(extract_partial_xor(f,equations,exhausted)) {
     if(!exhausted.empty()) {
       cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\"UNSAT\","
           <<"\"path\":\"v1410_exhaustive_support\","
           <<"\"verified\":true,\"support\":[";
       for(size_t j=0;j<exhausted.size();j++)
         cout<<(j?",":"")<<exhausted[j];
       cout<<"],\"certificate\":\"all_support_assignments_excluded\"}\n";
       return 0;
     }
     Answer a=solve_exact(f,equations);
     if(a.status=="UNSAT") {
       json_answer(a,f.n,int(equations.size()),"v1410_partial_xor_unsat");
       return 0;
     }
     // SAT from a subset of constraints is NOT enough; solve_exact verifies
     // the full original CNF before returning SAT. If verification fails,
     // catch below and delegate to Kissat.
     json_answer(a,f.n,int(equations.size()),"v1410_partial_xor_sat_verified");
     return 0;
   }
 } catch(const exception& e) {
   cerr<<"DRNAS_V1410_FALLBACK "<<e.what()<<"\n";
 }
 if(argc==5){cout<<"DRNAS_V1410_ROUTE\tkissat_direct\n";return 0;}
 char *av[]={const_cast<char*>(argv[2]),const_cast<char*>(argv[1]),nullptr};
 execv(av[0],av);
 cerr<<"DRNAS_V1410_ERROR Kissat exec failure\n";
 return 3;
}

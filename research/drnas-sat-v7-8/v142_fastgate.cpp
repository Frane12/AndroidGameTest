// DRNAS V14.2 FastGate - general SAT: native exact XOR/PHP only on promising
// structures, otherwise direct, unchanged Kissat. No Python or V7.6 probe.
// Full verification is performed by V14.0 original structural functions.
#define main v140_embedded_main
#include "v140_native_hybrid.cpp"
#undef main
#include <sys/stat.h>
struct Gate {bool maybe_xor=false,maybe_php=false;};
Gate inspect_fast(const string &cnf) {
 Gate g;struct stat st{};
 if(stat(cnf.c_str(),&st)!=0 || st.st_size>8*1024*1024 || st.st_size<=0)return g;
 ifstream in(cnf);if(!in)return g;
 string line;bool all3=true,php=true,found=false;
 int seen=0,first_groups=0,repeated=0;
 map<array<int,3>,int> supports;
 while(seen<128 && getline(in,line)) {
   istringstream ss(line);string token;
   if(!(ss>>token))continue;
   if(token=="c"||token=="%"||token=="p")continue;
   vector<int> clause;
   do {
     char *end=nullptr;errno=0;
     long value=strtol(token.c_str(),&end,10);
     if(errno||end==token.c_str()||*end||value>100000||value< -100000)
       return Gate{};
     if(value==0){
       if(clause.empty())return Gate{};
       found=true;++seen;
       if(clause.size()!=3)all3=false;
       const bool pos=clause.size()>=3 &&
          all_of(clause.begin(),clause.end(),[](int x){return x>0;});
       const bool neg=clause.size()==2 && clause[0]<0 && clause[1]<0;
       if(!pos&&!neg)php=false;
       if(clause.size()==3) {
         array<int,3> key={abs(clause[0]),abs(clause[1]),abs(clause[2])};
         sort(key.begin(),key.end());
         int &count=supports[key];
         if(++count>1)repeated++;
       }
       clause.clear();
     } else clause.push_back(int(value));
     if(clause.size()>4096)return Gate{};
   } while(ss>>token);
   if(!all3&&!php)return Gate{};
 }
 if(!found)return Gate{};
 // High-support repeat density indicates complete 3-XOR blocks. For short
 // files (<128 clauses), let full exact verifier check even without repeats.
 g.maybe_xor=all3&&(repeated>0||seen<128);
 g.maybe_php=php;
 return g;
}
int v142_embedded_main(int argc,char**argv) {
 if(!(argc==4||(argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v142_fastgate INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   string cnf=argv[1],kissat=argv[2];
   const Gate gate=inspect_fast(cnf);
   if(argc==5) {
     cout<<"DRNAS_V142_GATE\t"<<(gate.maybe_xor?"xor_candidate":gate.maybe_php?"php_candidate":"kissat_direct")<<"\n";
     return 0;
   }
   if(gate.maybe_xor||gate.maybe_php) {
     try {
       Cnf f=parse(cnf);
       if(gate.maybe_xor) {
         vector<Eq> equations;
         if(xor_extract(f,equations)) {
           Answer a=solve_exact(f,equations);
           json_answer(a,f.n,int(equations.size()));
           return 0;
         }
       }
       if(gate.maybe_php) {
         int holes=0,birds=0;
         if(complete_php_proof(f,holes,birds)) {
           json_php(holes,birds);
           return 0;
         }
       }
     } catch(const exception&) {
       // A failed/partial structural classification never implies SAT/UNSAT.
     }
   }
   cout<<"DRNAS_V142_ROUTE\tkissat_direct\n"<<flush;
   char *av[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(cnf.c_str()),nullptr};
   execv(av[0],av);
   throw runtime_error("Kissat exec failure");
 } catch(const exception &e) {
   cerr<<"DRNAS_V142_ERROR "<<e.what()<<"\n";return 3;
 }
}

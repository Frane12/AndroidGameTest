// DRNAS V14.7: certified subset-XOR4, tolerant of unrelated or redundant CNF clauses.
// Exactly verified parity blocks are *entailed* by the original CNF.
// An UNSAT contradiction among those blocks proves full CNF UNSAT.
// A SAT candidate is accepted ONLY after checking every original CNF clause;
// otherwise the identical pinned Kissat executable receives the original file.
// This is a conservative specialized preprocessing path, not a general SAT proof.
#include "v142_fastgate.cpp"

static bool v147_candidate(const string &name) {
 struct stat st{};
 if(stat(name.c_str(),&st)!=0 || st.st_size<=0 || st.st_size>8*1024*1024)return false;
 ifstream in(name);
 if(!in)return false;
 map<array<int,4>,int> supports;
 vector<int> pending;
 int seen=0,repeats=0,small=0;
 string line;
 while(seen<384 && getline(in,line)) {
  istringstream ss(line);
  string token;
  if(!(ss>>token) || token=="c" || token=="p" || token=="%")continue;
  do {
   if(token=="c")break;
   char *end=nullptr;errno=0;
   long v=strtol(token.c_str(),&end,10);
   if(errno || end==token.c_str() || *end || v>100000 || v< -100000)return false;
   if(!v) {
    if(pending.empty())return false;
    ++seen;
    if(pending.size()>=2 && pending.size()<=4) {
     array<int,4> key{};
     for(size_t j=0;j<pending.size();++j)key[j]=abs(pending[j]);
     sort(key.begin(),key.end());
     if(adjacent_find(key.begin(),key.end())==key.end()) {
      ++small;
      if(++supports[key]>1)++repeats;
     }
    }
    pending.clear();
   } else {
    pending.push_back(int(v));
    if(pending.size()>4096)return false;
   }
  } while(ss>>token && seen<384);
 }
 return seen>=4 && small*5>=seen*4 &&
        (seen<32 ? repeats>=1 : repeats>=4);
}

static bool v147_subset(const Cnf &f,vector<Eq>& out) {
 out.clear();
 if(f.n<1 || f.n>4096 || f.clauses.size()>100000)return false;
 // Clause-mask groups are derived exclusively from the ORIGINAL input clauses.
 // Duplicated clauses may be ignored; partial or nonparity groups may NOT be used.
 map<array<int,4>,uint16_t> groups;
 for(const auto &cl:f.clauses) {
  if(cl.size()<2 || cl.size()>4)continue;
  vector<int> lits=cl;
  sort(lits.begin(),lits.end(),[](int a,int b){return abs(a)<abs(b);});
  array<int,4> support{};
  unsigned mask=0;
  bool valid=true;
  for(size_t j=0;j<lits.size();++j) {
   support[j]=abs(lits[j]);
   if(j && support[j]==support[j-1]){valid=false;break;}
   if(lits[j]<0)mask|=1u<<j;
  }
  if(!valid)continue;
  groups[support] |= uint16_t(1u<<mask);
  if(groups.size()>4096)return false;
 }
 const int words=(f.n+63)/64;
 for(const auto &entry:groups) {
  const auto &support=entry.first;
  const unsigned patterns=entry.second;
  int width=0;
  while(width<4 && support[width])++width;
  const int rhs=int(patterns&1u);
  bool full=true;
  for(unsigned mask=0;mask<(1u<<width);++mask) {
   const bool forbidden=bool(patterns&(1u<<mask));
   if(forbidden != (bool(__builtin_popcount(mask)&1) != bool(rhs))) {
    full=false;break;
   }
  }
  if(!full)continue;
  Eq eq;eq.bits.assign(words,0);eq.rhs=rhs;
  for(int j=0;j<width;++j) {
   const int b=support[j]-1;
   if(b<0||b>=f.n)return false;
   eq.bits[b/64]|=1ULL<<(b%64);
  }
  out.push_back(move(eq));
 }
 return !out.empty();
}

int main(int argc,char**argv) {
 if(argc!=4){cerr<<"Usage: v147_subset_xor4 INPUT_CNF KISSAT_BINARY SEED\n";return 2;}
 const string cnf=argv[1],kissat=argv[2];
 if(v147_candidate(cnf)) {
  try {
   Cnf f=parse(cnf);
   vector<Eq> equations;
   if(v147_subset(f,equations)) {
    // solve_exact independently validates the entire original CNF for SAT.
    // For UNSAT its checked GF(2) combination derives 0 = 1.
    Answer a=solve_exact(f,equations);
    json_answer(a,f.n,int(equations.size()),"affine_subset_xor4");
    return 0;
   }
  } catch(const exception&) {
   // Failure to extract/validate is always UNKNOWN, never SAT/UNSAT.
  }
 }
 cout<<"DRNAS_V147_ROUTE\tkissat_direct\n"<<flush;
 char *av[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(cnf.c_str()),nullptr};
 execv(av[0],av);
 cerr<<"DRNAS_V147_ERROR execv fallback failed: "<<errno<<"\n";
 return 3;
}

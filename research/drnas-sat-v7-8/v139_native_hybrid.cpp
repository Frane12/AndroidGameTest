// DRNAS V13.9 experimental native GF(2) exact fast path with V7.6 fallback.
// Structured SAT: strict full 3-XOR encoding, not filename/label dependent.
// Outputs SAT assignment or UNSAT linear-combination proof, both verified.
// Non-XOR inputs are exec'd into ORIGINAL V7.6 adaptive_plain (no copies).
// Theorem is known polynomial GF(2) elimination, not general polynomial SAT.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>
using namespace std;

struct Cnf {
 int n=0;
 vector<vector<int>> clauses;
};
Cnf parse(const string& path) {
 ifstream in(path);
 if(!in)throw runtime_error("Cannot open DIMACS");
 Cnf f; string line; long long expected=-1; vector<int> pending;
 bool header=false;
 while(getline(in,line)) {
   istringstream iss(line);string token;
   if(!(iss>>token))continue;
   if(token=="c"||token=="%")continue;
   if(token=="p") {
     string kind,extra;
     long long n,m;
     if(header||!(iss>>kind>>n>>m)||kind!="cnf"||
        n<1||n>100000||m<1||m>100000||iss>>extra)
       throw runtime_error("Bad DIMACS header");
     f.n=int(n);expected=m;header=true;continue;
   }
   if(!header)throw runtime_error("DIMACS missing header");
   do {
     if(token=="c")break;
     char* end=nullptr;errno=0;
     long value=strtol(token.c_str(),&end,10);
     if(errno||!end||*end||value>f.n||value< -f.n)
       throw runtime_error("Invalid DIMACS literal");
     if(value==0) {
       if(pending.empty())throw runtime_error("Empty clause unsupported");
       f.clauses.push_back(move(pending));pending={};
       if(long long(f.clauses.size())>expected)throw runtime_error("Excess clauses");
     } else {
       pending.push_back(int(value));
       if(pending.size()>100000)throw runtime_error("Excessive clause");
     }
   } while(iss>>token);
 }
 if(!header||!pending.empty()||long long(f.clauses.size())!=expected)
   throw runtime_error("Incomplete DIMACS");
 return f;
}
struct Eq {
 vector<uint64_t> bits;
 int rhs=0;
};
inline int bit(const vector<uint64_t>& x,int b) {
 return (x[b/64]>>(b%64))&1ULL;
}
inline void xor_inplace(vector<uint64_t>& a,const vector<uint64_t>& b) {
 for(size_t j=0;j<a.size();j++)a[j]^=b[j];
}
bool xor_extract(const Cnf &f, vector<Eq>& out) {
 if(f.n>4096 || f.clauses.size()%4 != 0)return false;
 map<array<int,3>,uint8_t> groups;
 for(auto cl:f.clauses) {
   if(cl.size()!=3)return false;
   sort(cl.begin(),cl.end(),[](int a,int b){return abs(a)<abs(b);});
   array<int,3> vars={abs(cl[0]),abs(cl[1]),abs(cl[2])};
   if(vars[0]==vars[1]||vars[1]==vars[2])return false;
   int mask=0;
   for(int j=0;j<3;j++)if(cl[j]<0)mask|=1<<j;
   auto &entry=groups[vars];
   if(entry & (1<<mask))return false; // duplicate: no exact encoding
   entry|=1<<mask;
 }
 if(groups.size()*4!=f.clauses.size())return false;
 const int words=(f.n+63)/64;
 for(const auto &p:groups) {
   auto masks=p.second;
   int parity=-1;
   for(int m=0;m<8;m++)if(masks&(1<<m)) {
     const int q=__builtin_popcount(unsigned(m))%2;
     if(parity!=-1 && parity!=q)return false;
     parity=q;
   }
   if(__builtin_popcount(unsigned(masks))!=4||parity<0)return false;
   for(int m=0;m<8;m++)
     if(bool(masks&(1<<m))!=(__builtin_popcount(unsigned(m))%2==parity))
       return false;
   Eq e;e.bits.assign(words,0);e.rhs=1-parity;
   for(int v:p.first)e.bits[(v-1)/64]|=1ULL<<((v-1)%64);
   out.push_back(move(e));
 }
 return true;
}
int highest(const vector<uint64_t> &b) {
 for(int j=int(b.size())-1;j>=0;j--)
   if(b[j])return 64*j+63-__builtin_clzll(b[j]);
 return -1;
}
struct Answer {
 string status;
 vector<int> model, proof_rows;
};
Answer solve_exact(const Cnf& f,const vector<Eq>& equations) {
 const int n=f.n,m=int(equations.size()),proof_words=(m+63)/64;
 struct Pivot {
   vector<uint64_t> bits,combo;
   int rhs=0;
 };
 vector<Pivot> pivots(n);
 vector<char> present(n,0);
 for(int i=0;i<m;i++) {
   vector<uint64_t> bits=equations[i].bits,combo(proof_words,0);
   combo[i/64]|=1ULL<<(i%64);
   int rhs=equations[i].rhs;
   for(;;) {
     int hi=highest(bits);
     if(hi<0)break;
     if(!present[hi]) {
       present[hi]=1;pivots[hi]={move(bits),move(combo),rhs};
       goto next_equation;
     }
     xor_inplace(bits,pivots[hi].bits);
     xor_inplace(combo,pivots[hi].combo);
     rhs^=pivots[hi].rhs;
   }
   if(rhs) {
     vector<uint64_t> proof(f.n?equations[0].bits.size():0,0);
     int rhs_sum=0; Answer a;a.status="UNSAT";
     for(int j=0;j<m;j++)if(bit(combo,j)) {
       a.proof_rows.push_back(j);
       xor_inplace(proof,equations[j].bits);
       rhs_sum^=equations[j].rhs;
     }
     if(highest(proof)!=-1||rhs_sum!=1||a.proof_rows.empty())
       throw runtime_error("Unsound GF(2) UNSAT proof");
     return a;
   }
   next_equation:;
 }
 vector<uint8_t> assign(n,0);
 // Lower pivots cannot depend on higher pivots after descending-bit elimination.
 for(int col=0;col<n;col++)if(present[col]) {
   const auto &p=pivots[col];
   int parity=p.rhs;
   for(int j=0;j<col;j++)if(bit(p.bits,j))parity^=assign[j];
   assign[col]=parity;
 }
 for(const auto &eq:equations) {
   int p=0;for(int j=0;j<n;j++)if(bit(eq.bits,j))p^=assign[j];
   if(p!=eq.rhs)throw runtime_error("GF(2) assignment failed");
 }
 for(const auto &cl:f.clauses) {
   bool ok=false;
   for(int lit:cl)if(bool(assign[abs(lit)-1])==(lit>0)){ok=true;break;}
   if(!ok)throw runtime_error("SAT model failed CNF clause verification");
 }
 Answer a;a.status="SAT";
 for(int i=0;i<n;i++)a.model.push_back(assign[i]?i+1:-(i+1));
 return a;
}
void json_answer(const Answer &a,int n,int m) {
 cout<<"DRNAS_HYBRID_RESULT\t{\"status\":\""<<a.status
     <<"\",\"path\":\"affine_exact\",\"verified\":true,\"variables\":"
     <<n<<",\"equations\":"<<m;
 if(a.status=="SAT") {
   cout<<",\"model\":[";
   for(size_t i=0;i<a.model.size();i++)cout<<(i?",":"")<<a.model[i];
   cout<<"]";
 } else {
   cout<<",\"proof_rows\":[";
   for(size_t i=0;i<a.proof_rows.size();i++)
     cout<<(i?",":"")<<a.proof_rows[i];
   cout<<"]";
 }
 cout<<"}\n";
}
int main(int argc,char**argv) {
 if(argc!=4) {
   cerr<<"Usage: native_hybrid INPUT_CNF ORIGINAL_V76_BINARY SEED\n";
   return 2;
 }
 try {
   const string input=argv[1];
   struct stat st{};
   if(stat(input.c_str(),&st)!=0)throw runtime_error("Input stat failed");
   if(st.st_size<=32*1024*1024) {
     Cnf f=parse(input);
     vector<Eq> equations;
     if(xor_extract(f,equations)) {
       Answer a=solve_exact(f,equations);
       json_answer(a,f.n,int(equations.size()));
       return 0;
     }
   }
   // General SAT fallback: original C++ V7.6, bypass Python on non-XOR input.
   cout<<"DRNAS_HYBRID_ROUTE\tfallback_v76\n"<<flush;
   char *av[]={argv[2],const_cast<char*>("adaptive_plain"),argv[1],argv[3],nullptr};
   execv(argv[2],av);
   throw runtime_error("execv fallback failed (ensure absolute binary path)");
 } catch(const exception& e) {
   cerr<<"DRNAS_NATIVE_HYBRID_ERROR "<<e.what()<<"\n";return 3;
 }
}

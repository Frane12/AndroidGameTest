// DRNAS V14.4: certified hidden parity in arbitrary mixed CNFs.
// Adds sound XOR(1), XOR(2) and XOR(3) extraction; only UNSAT subset proofs.
// An XOR1 comes from a unit; XOR2 from TWO opposite-sign 2-clauses;
// XOR3 from FOUR signed ternary clauses with complete parity masks.
// Every returned certificate identifies ORIGINAL input clause indices and
// is independently checked by truth-table equivalence and GF2 replay.
// Fallback is the byte-for-byte original V14.3 native pipeline, then Kissat.
#include "v143_localxor_fastgate.cpp"
#include <set>
#include <map>
#include <array>
#include <vector>
#include <algorithm>
#include <iterator>
#include <string>
#include <sys/stat.h>
using namespace std;

struct Parity144 {
 vector<int> vars;
 int rhs=0;
 vector<int> clauses; // 0-based positions in original CNF
};
struct Basis144 { set<int> vars; set<int> witness; int rhs=0; };
template<typename T>
set<T> symmetric144(const set<T>& a,const set<T>& b) {
 set<T> r;
 set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),inserter(r,r.end()));
 return r;
}
static void append144(vector<Parity144>& eq,vector<int> vars,int rhs,vector<int> witnesses) {
 if(eq.size()>30000)return;
 eq.push_back({move(vars),rhs,move(witnesses)});
}
static vector<Parity144> extract144(const Cnf& f) {
 // Mask is defined by the signs of literals in ascending absolute variable order.
 map<array<int,2>,array<int,4>> binary;
 map<array<int,3>,array<int,8>> ternary;
 vector<Parity144> result;
 for(int i=0;i<(int)f.clauses.size();++i) {
   const auto& c=f.clauses[i];
   if(c.size()==1) {
     int lit=c[0];append144(result,{abs(lit)},lit>0?1:0,{i});
   } else if(c.size()==2) {
     auto v=c;sort(v.begin(),v.end(),[](int a,int b){return abs(a)<abs(b);});
     if(abs(v[0])==abs(v[1]))continue;
     array<int,2> key{abs(v[0]),abs(v[1])};
     int mask=(v[0]<0?1:0)|(v[1]<0?2:0);
     if(!binary.count(key))binary[key].fill(-1);
     auto& slots=binary[key];
     if(slots[mask]<0)slots[mask]=i;
   } else if(c.size()==3) {
     auto v=c;sort(v.begin(),v.end(),[](int a,int b){return abs(a)<abs(b);});
     if(abs(v[0])==abs(v[1])||abs(v[1])==abs(v[2]))continue;
     array<int,3> key{abs(v[0]),abs(v[1]),abs(v[2])};
     int mask=(v[0]<0?1:0)|(v[1]<0?2:0)|(v[2]<0?4:0);
     if(!ternary.count(key))ternary[key].fill(-1);
     auto& slots=ternary[key];
     if(slots[mask]<0)slots[mask]=i;
   }
 }
 for(const auto& p:binary) {
   const auto& m=p.second;
   if(m[0]>=0 && m[3]>=0)
     append144(result,{p.first[0],p.first[1]},1,{m[0],m[3]});
   if(m[1]>=0 && m[2]>=0)
     append144(result,{p.first[0],p.first[1]},0,{m[1],m[2]});
 }
 for(const auto& p:ternary) {
   for(int parity=0;parity<=1;parity++) {
     vector<int> witnesses;
     for(int mask=0;mask<8;mask++)
       if((__builtin_popcount((unsigned)mask)&1)==parity && p.second[mask]>=0)
         witnesses.push_back(p.second[mask]);
     if(witnesses.size()==4) {
       append144(result,{p.first[0],p.first[1],p.first[2]},1-parity,
                 move(witnesses));
     }
   }
 }
 return result;
}
static bool replay144(const vector<Parity144>& eq,const set<int>& proof) {
 set<int> all;int rhs=0;
 if(proof.empty())return false;
 for(int id:proof) {
   if(id<0||id>=(int)eq.size())return false;
   const auto& e=eq[id];rhs^=e.rhs;
   for(int v:e.vars)if(!all.erase(v))all.insert(v);
 }
 return all.empty()&&rhs==1;
}
// Independent truth-table equivalence between each source clause subset and
// its claimed XOR equation. At most 3 variables -> 8 assignments.
static bool direct_witness144(const Cnf& f,const Parity144& e) {
 if(e.vars.empty()||e.vars.size()>3||e.clauses.empty()||e.clauses.size()!=(1u<<(e.vars.size()-1)))
   return false;
 for(int index:e.clauses) {
   if(index<0||index>=(int)f.clauses.size())return false;
   for(int lit:f.clauses[index])
     if(find(e.vars.begin(),e.vars.end(),abs(lit))==e.vars.end())return false;
 }
 for(unsigned mask=0;mask<(1u<<e.vars.size());mask++) {
   bool all=true;
   for(int ci:e.clauses) {
     bool yes=false;
     for(int lit:f.clauses[ci]) {
       auto it=find(e.vars.begin(),e.vars.end(),abs(lit));
       unsigned b=(unsigned)(it-e.vars.begin());
       if(bool((mask>>b)&1u)==(lit>0)){yes=true;break;}
     }
     if(!yes){all=false;break;}
   }
   if(all!=((__builtin_popcount(mask)&1)==e.rhs))return false;
 }
 return true;
}
static bool gf2_unsat144(const vector<Parity144>& eq,set<int>& certificate,size_t& operations) {
 map<int,Basis144> basis;
 // Conservative bounds: skipped rows cannot imply SAT, only verified UNSAT.
 const size_t max_ops=240000, max_width=128, max_origin=512, max_basis=110000;
 for(int i=0;i<(int)eq.size();i++) {
   Basis144 row;
   row.vars.insert(eq[i].vars.begin(),eq[i].vars.end());
   row.witness.insert(i);
   row.rhs=eq[i].rhs;
   while(!row.vars.empty()) {
     if(operations++>=max_ops)return false;
     int pivot=*row.vars.begin();
     auto it=basis.find(pivot);
     if(it==basis.end()) {
       if(basis.size()<max_basis && row.vars.size()<=max_width &&
          row.witness.size()<=max_origin)basis.emplace(pivot,move(row));
       goto next144;
     }
     auto v=symmetric144(row.vars,it->second.vars);
     auto w=symmetric144(row.witness,it->second.witness);
     if(v.size()>max_width||w.size()>max_origin)goto next144;
     row.vars=move(v);row.witness=move(w);row.rhs^=it->second.rhs;
   }
   if(row.rhs) {
     if(!replay144(eq,row.witness))throw runtime_error("invalid GF2 replay");
     certificate=move(row.witness);return true;
   }
   next144:;
 }
 return false;
}
int main(int argc,char**argv) {
 if(!(argc==4 || (argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v144_hidden_parity INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";return 2;
 }
 try {
   struct stat st{};
   const string cnf=argv[1];
   vector<Parity144> equations;
   bool attempted=false;
   if(stat(cnf.c_str(),&st)==0 && st.st_size>0 && st.st_size<=96*1024) {
     try {
       Cnf f=parse(cnf);
       equations=extract144(f);
       // Use >=4 equations to avoid waste on tiny accidental motifs.
       attempted=equations.size()>=4;
       if(attempted && argc==4) {
         set<int> proof;size_t operations=0;
         if(gf2_unsat144(equations,proof,operations)) {
           for(int index:proof)
             if(!direct_witness144(f,equations[index]))
               throw runtime_error("invalid clause-based parity proof");
           cout<<"DRNAS_V144_RESULT\t{\"status\":\"UNSAT\","
               <<"\"verified\":true,\"path\":\"hidden_parity_gf2\","
               <<"\"eq_total\":"<<equations.size()<<",\"proof\":[";
           bool first=true;
           for(int id:proof) {
             const auto& e=equations[id];
             cout<<(first?"":",")<<"{\"variables\":[";
             first=false;
             for(size_t j=0;j<e.vars.size();j++)cout<<(j?",":"")<<e.vars[j];
             cout<<"],\"rhs\":"<<e.rhs<<",\"clause_indices\":[";
             for(size_t j=0;j<e.clauses.size();j++)cout<<(j?",":"")<<e.clauses[j];
             cout<<"]}";
           }
           cout<<"],\"xor_operations\":"<<operations<<"}\n";
           return 0;
         }
       }
     } catch(const exception& e) {
       cerr<<"DRNAS_V144_PREPASS_BYPASS "<<e.what()<<"\n";
       // Cannot accept a partial/invalid mathematical certificate.
     }
   }
   if(argc==5) {
     cout<<"DRNAS_V144_GATE\t"<<(attempted?"parity_candidate":"bypass")
         <<"\tequations="<<equations.size()<<"\n";return 0;
   }
   cout<<"DRNAS_V144_ROUTE\t"<<(attempted?"parity_then_v143":"v143_direct")<<"\n"<<flush;
   return v143_embedded_main(argc,argv);
 } catch(const exception& e) {
   cerr<<"DRNAS_V144_ERROR "<<e.what()<<"\n";return 3;
 }
}

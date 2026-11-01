// V14.3: combine V13.15 complete local-3-XOR selective gate + V14.2
// native FastGate, preserving the exact frozen V13.15 size/block thresholds.
// Only infer UNSAT from a verified GF(2) contradiction across EXACT four
// CNF clauses of one parity class; otherwise delegate unchanged V14.2.
// No filename, labels, runtime history, or oracle used in routing.
#define main v142_embedded_main
#include "v142_fastgate.cpp"
#undef main
#include <set>
#include <iterator>
#include <cstdio>
static const long LOCAL_BYTES=96*1024;
static const size_t LOCAL_MIN_BLOCKS=16;
static const size_t MAX_OPS=240000;
static const size_t MAX_SUPPORT=128;
static const size_t MAX_PROVENANCE=512;
static const size_t MAX_BASIS=110000;
struct LocalEq {
 array<int,3> support;
 int rhs;
};
struct LocalRow {
 set<int> support;
 set<int> provenance;
 int rhs;
};
template<class T> set<T> sxor(const set<T>& a,const set<T>& b) {
 set<T> result;
 set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),
                          inserter(result,result.end()));
 return result;
}
bool exact_local_equations(const Cnf& f,vector<LocalEq>& eqs) {
 map<array<int,3>,pair<unsigned,int>> counts;
 for(const vector<int>& clause:f.clauses) {
   if(clause.size()!=3)continue;
   vector<int> c=clause;
   sort(c.begin(),c.end(),[](int a,int b){return abs(a)<abs(b);});
   array<int,3> key={abs(c[0]),abs(c[1]),abs(c[2])};
   if(key[0]==key[1]||key[1]==key[2])continue;
   int mask=(c[0]<0 ? 1:0)|(c[1]<0 ? 2:0)|(c[2]<0 ? 4:0);
   auto& item=counts[key];
   item.first |= (1u<<mask);
   item.second++;
 }
 for(const auto& item:counts) {
   if(item.second.second!=4)continue;
   int bad_parity=-1;
   bool exact=true;
   for(int m=0;m<8;m++)if(item.second.first&(1u<<m)) {
     int parity=__builtin_popcount(unsigned(m))&1;
     if(bad_parity==-1)bad_parity=parity;
     else if(bad_parity!=parity)exact=false;
   }
   if(!exact||bad_parity<0||
      __builtin_popcount(item.second.first)!=4)continue;
   // Only a complete parity class implies a single XOR equation.
   eqs.push_back({item.first,1-bad_parity});
 }
 return eqs.size()>=LOCAL_MIN_BLOCKS;
}
bool replay_subset(const vector<LocalEq>& eqs,const set<int>& source) {
 set<int> support;int rhs=0;
 if(source.empty())return false;
 for(int id:source) {
   if(id<0||size_t(id)>=eqs.size())return false;
   rhs^=eqs[id].rhs;
   for(int v:eqs[id].support) {
     if(support.count(v))support.erase(v);
     else support.insert(v);
   }
 }
 return support.empty()&&rhs==1;
}
bool local_contradiction(const vector<LocalEq>& eqs,set<int>& proof,size_t& operations) {
 map<int,LocalRow> pivots;
 for(size_t i=0;i<eqs.size();i++) {
   LocalRow row;
   row.support.insert(eqs[i].support.begin(),eqs[i].support.end());
   row.provenance.insert(int(i));
   row.rhs=eqs[i].rhs;
   while(!row.support.empty()) {
     if(operations++>=MAX_OPS)return false;
     int pivot=*row.support.begin();
     auto j=pivots.find(pivot);
     if(j==pivots.end()) {
       if(pivots.size()>=MAX_BASIS||row.support.size()>MAX_SUPPORT||
          row.provenance.size()>MAX_PROVENANCE)break;
       pivots.emplace(pivot,move(row));
       goto next_row;
     }
     set<int> newrow=sxor(row.support,j->second.support);
     set<int> newproof=sxor(row.provenance,j->second.provenance);
     if(newrow.size()>MAX_SUPPORT||newproof.size()>MAX_PROVENANCE)break;
     row.support=move(newrow);
     row.provenance=move(newproof);
     row.rhs^=j->second.rhs;
   }
   if(row.support.empty()&&row.rhs) {
     if(!replay_subset(eqs,row.provenance))
       throw runtime_error("V143 local XOR proof replay mismatch");
     proof=move(row.provenance);
     return true;
   }
   next_row:;
 }
 return false;
}
int main(int argc,char**argv) {
 if(!(argc==4||(argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v143 INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";return 2;
 }
 try {
   const string path=argv[1];
   struct stat st{};
   vector<LocalEq> equations;
   bool eligible=false;
   if(stat(path.c_str(),&st)==0 && st.st_size>0 && st.st_size<=LOCAL_BYTES) {
     try {
       Cnf f=parse(path);
       eligible=exact_local_equations(f,equations);
       if(eligible && argc==4) {
         set<int> proof;
         size_t operations=0;
         if(local_contradiction(equations,proof,operations)) {
           cout<<"DRNAS_V143_RESULT\t{\"status\":\"UNSAT\","
               <<"\"path\":\"local_xor_verified\",\"verified\":true,"
               <<"\"xor_blocks\":"<<equations.size()
               <<",\"proof_equation_indices\":[";
           bool first=true;
           for(int id:proof) {
             cout<<(first?"":",")<<id;first=false;
           }
           cout<<"],\"xor_operations\":"<<operations<<"}\n";
           return 0;
         }
       }
     } catch(const exception&) {
       eligible=false; // never infer any SAT/UNSAT from parser errors
     }
   }
   if(argc==5) {
     cout<<"DRNAS_V143_GATE\t"<<(eligible?"local_xor_candidate":"bypass")
         <<"\tblocks="<<equations.size()<<"\n";
     return 0;
   }
   cout<<"DRNAS_V143_ROUTE\t"<<(eligible?"local_xor_then_v142":"v142_direct")<<"\n"<<flush;
   // Retain V14.2 native full-XOR/PHP and direct Kissat fallback, exactly.
   return v142_embedded_main(argc,argv);
 } catch(const exception& e) {
   cerr<<"DRNAS_V143_ERROR "<<e.what()<<"\n";
   return 3;
 }
}

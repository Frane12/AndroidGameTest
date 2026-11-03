// DRNAS SAT R26 — low-overhead structural XOR gate; never uses name/label.
 // This selector has no answer-producing logic. Only V15.3.1 can prove a
 // structure-specific result; everything else executes unchanged Kissat 4.0.4.
 // Replaces R25's Python startup and repeated-support false positives.
 #include <algorithm>
 #include <array>
 #include <cstdint>
 #include <cstdlib>
 #include <fstream>
 #include <iostream>
 #include <limits>
 #include <sstream>
 #include <string>
 #include <unordered_map>
 #include <vector>
 #include <unistd.h>
 using namespace std;
 struct Pattern { int k=0; uint64_t masks=0; };
 struct Decision { string route="kissat_direct"; unsigned blocks=0,covered=0,scanned=0; };
 static bool full_parity(const Pattern &p) {
   if(p.k<2 || p.k>6) return false;
   const int count=1<<p.k, half=count/2;
   uint64_t even=0,odd=0;
   for(int mask=0;mask<count;mask++)
     if(__builtin_parity(unsigned(mask)))odd|=(uint64_t(1)<<mask);
     else even|=(uint64_t(1)<<mask);
   return p.masks==even || p.masks==odd;
 }
 static Decision inspect(const char* path) {
   Decision d;
   ifstream in(path);
   if(!in) return d;
   // Only the first 512 KiB and 1536 complete clauses are inspected.
   // This is a non-answer-producing, bounded-cost filter, never proof.
   string line; size_t scanned_bytes=0;
   int declared_n=0, declared_m=0;
   unordered_map<string,Pattern> patterns;
   vector<int> clause;
   bool header=false;
   while(getline(in,line) && d.scanned<1536 && scanned_bytes<524288) {
     scanned_bytes+=line.size()+1;
     if(line.size()>30000)break;
     istringstream ss(line);string first;
     if(!(ss>>first))continue;
     if(first=="c" || first=="%")continue;
     if(first=="p") {
       string kind;
       if(!(ss>>kind>>declared_n>>declared_m) || kind!="cnf" ||
          declared_n<1 || declared_m<1)return d;
       header=true;continue;
     }
     if(!header)return d;
     // Support legal DIMACS clauses spanning multiple lines.
     string token=first;
     do {
       char *end=nullptr;
       long v=strtol(token.c_str(), &end, 10);
       if(!end || *end || v>100000000 || v< -100000000)return Decision{};
       if(v==0) {
         ++d.scanned;
         const int k=int(clause.size());
         if(k>=2 && k<=6) {
           vector<pair<int,bool>> lits; lits.reserve(k);
           bool valid=true;
           for(int x:clause) {
             if(!x || abs(x)>declared_n){valid=false;break;}
             lits.push_back({abs(x), x<0});
           }
           if(valid) {
             sort(lits.begin(),lits.end());
             for(int j=1;j<k;j++)if(lits[j].first==lits[j-1].first)valid=false;
           }
           if(valid) {
             string key=to_string(k);
             int mask=0;
             for(int j=0;j<k;j++) {
               key+=","+to_string(lits[j].first);
               if(lits[j].second)mask|=1<<j;
             }
             Pattern &p=patterns[key];p.k=k;
             p.masks|=uint64_t(1)<<mask;
           }
         }
         clause.clear();
       } else {
         if(clause.size()>20)return Decision{};
         clause.push_back(int(v));
       }
     }while(ss>>token);
   }
   for(const auto &kv:patterns)if(full_parity(kv.second)){
     d.blocks++;
     d.covered+=1u<<(kv.second.k-1);
   }
   // Require actual complete XOR blocks, not merely repeated supports.
   // This deliberately routes ambiguous/mixed formulas to Kissat.
   if(d.blocks>=4 && d.covered>=24 &&
      uint64_t(d.covered)*100>=uint64_t(d.scanned)*45)
     d.route="v1531_certified_xor";
   return d;
 }
 int main(int argc,char **argv) {
   if(argc!=5 && argc!=6) {
     cerr<<"Usage: r26_selector INPUT KISSAT V1531 SEED [--classify-only]\n";
     return 2;
   }
   const Decision d=inspect(argv[1]);
   cout<<"DRNAS_R26_ROUTE\t"<<d.route<<"\tblocks="<<d.blocks
       <<"\tcovered="<<d.covered<<"\tscanned="<<d.scanned<<"\n"<<flush;
   if(argc==6) return string(argv[5])=="--classify-only"?0:2;
   if(d.route=="v1531_certified_xor") {
     char *args[]={argv[3],argv[1],argv[2],argv[4],nullptr};
     execv(args[0],args);
   }else{
     char *args[]={argv[2],argv[1],nullptr};
     execv(args[0],args);
   }
   perror("DRNAS_R26_EXECV_FAILED");
   return 3;
 }

// DRNAS R135: bounded, read-only, non-XOR selector (Kissat/CaDiCaL portfolio).
// Frozen rule trained only from previously inspected R134 structural shadow:
// choose CaDiCaL when binary fraction < 0.20 AND Horn fraction < 0.50,
// otherwise Kissat. Never edit, learn from, or solve the input CNF here.
// Examine at most 128 KiB and 2,000 complete clauses. Include scan time
// in every full end-to-end R135 trial. Statistics from prefixes are flagged.
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
using namespace std;
struct Probe {
  int declared=0,seen=0,binaries=0,horn=0,units=0;
  bool header=false,parseok=true,truncated=false;
  long scanned=0;
  string reason="complete";
};
int main(int argc,char**argv) {
 if(argc!=2){cerr<<"usage: r135_selector original.cnf\n";return 2;}
 ifstream f(argv[1],ios::binary);
 Probe p;
 if(!f) {cout<<"c R135_SELECTOR route=KISSAT reason=unreadable parsed=0 observed=0 binary_fraction=0 horn_fraction=0 scanned_bytes=0\n";return 0;}
 string line;
 int length=0,positive=0;
 constexpr long BYTE_CAP=131072;
 constexpr int CLAUSE_CAP=2000;
 while(getline(f,line)) {
   p.scanned+=long(line.size()+1);
   if(p.scanned>BYTE_CAP){p.truncated=true;p.reason="byte_budget";break;}
   auto first=line.find_first_not_of(" \t\r");
   if(first==string::npos)continue;
   char c=line[first];
   if(c=='c'||c=='%')continue;
   if(c=='p') {
     istringstream h(line);
     string tag,fmt,extra;long vars=0,cls=0;
     if(p.header||!(h>>tag>>fmt>>vars>>cls)||tag!="p"||fmt!="cnf"||vars<1||cls<1||cls>1000000000L||(h>>extra)) {
       p.parseok=false;p.reason="header_invalid";break;
     }
     p.header=true;p.declared=int(cls);
     continue;
   }
   if(!p.header){p.parseok=false;p.reason="header_missing";break;}
   istringstream tokens(line);
   string tok;
   while(tokens>>tok) {
      errno=0;char*end=nullptr;
      const long v=strtol(tok.c_str(),&end,10);
      if(errno||end==tok.c_str()||*end||v>2000000000L||v<-2000000000L){
        p.parseok=false;p.reason="literal_invalid";break;
      }
      if(v==0) {
        ++p.seen;
        if(length==2)++p.binaries;
        if(length==1)++p.units;
        if(positive<=1)++p.horn;
        length=positive=0;
        if(p.seen>=CLAUSE_CAP){p.truncated=true;p.reason="clause_budget";break;}
      } else {
        ++length;if(v>0)++positive;
      }
   }
   if(!p.parseok||p.truncated)break;
 }
 if(!p.header){p.parseok=false;if(p.reason=="complete")p.reason="header_missing";}
 if(p.parseok&&!p.truncated&&(p.seen!=p.declared||length)){p.parseok=false;p.reason="clause_count_mismatch";}
 double binary=p.seen?double(p.binaries)/p.seen:0.0;
 double horn=p.seen?double(p.horn)/p.seen:0.0;
 bool choose=p.parseok&&p.seen>=32&&binary<0.20&&horn<0.50;
 if(p.parseok&&p.seen<32)p.reason="not_enough_clauses";
 else if(p.parseok)p.reason=choose?"low_binary_low_horn":"high_binary_or_horn";
 cout<<fixed<<setprecision(6)
     <<"c R135_SELECTOR route="<<(choose?"CADICAL":"KISSAT")
     <<" reason="<<p.reason
     <<" parsed="<<(p.parseok?1:0)
     <<" observed="<<p.seen<<" declared="<<p.declared
     <<" binary_fraction="<<binary<<" horn_fraction="<<horn
     <<" scanned_bytes="<<p.scanned<<" prefix="<<(p.truncated?1:0)
     <<"\n";
 return 0;
}

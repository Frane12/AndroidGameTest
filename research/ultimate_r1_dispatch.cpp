// DRNAS Ultimate R1: R160's frozen structural fallback with a hypothesis-driven\n// R194 dual-CDCL arm on large low-binary / low-Horn sources.\n// Original DIMACS is never changed. This selector runs only after R153 abstains.
// Entry: R153 execv() calls this binary ONLY when exact GF(2) proof does
// not settle the original CNF. This implements R135's frozen decision rule.
// The original CNF is never rewritten and the selected solver is exec'd.
// Frozen R135 rule: CaDiCaL iff >=32 observed complete clauses,
// binary_fraction < .20 && horn_fraction < .50 and prefix parsed cleanly.
// Read at most 128 KiB and 2,000 clauses; all overhead is included in PAR2.
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>
using namespace std;
struct Probe {
  int declared=0,seen=0,binaries=0,horn=0,units=0;
  bool header=false,parseok=true,truncated=false;
  long scanned=0;
  string reason="complete";
};
int main(int argc,char**argv) {
  if(argc!=2){cerr<<"usage: r160_dispatch original.cnf\n";return 2;}
  ifstream f(argv[1],ios::binary);
  Probe p;
  if(!f) {
    cout<<"c ULTIMATE_R1_SELECTOR route=KISSAT reason=unreadable parsed=0 observed=0 binary_fraction=0 horn_fraction=0 scanned_bytes=0\n"<<flush;
    return 77;
  }
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
  // PRECOMMITTED structural eligibility, no filename / label / outcome input.
  // For small or unconvincing sources retain the exact R160 default routing.
  const bool dual=choose && p.seen>=128 && p.declared>=1000 && p.scanned>=4096;
  const char* solver=dual?"ultimate_r1/r194-compat":
                     choose?"built/bin/cadical_3_0_1":"built/bin/kissat_4_0_4";
  cout<<fixed<<setprecision(6)
    <<"c R160_SELECTOR route="<<(dual?"R194_DUAL":choose?"CADICAL":"KISSAT")
    <<" reason="<<p.reason
    <<" parsed="<<(p.parseok?1:0)
    <<" observed="<<p.seen<<" declared="<<p.declared
    <<" binary_fraction="<<binary<<" horn_fraction="<<horn
    <<" scanned_bytes="<<p.scanned<<" prefix="<<(p.truncated?1:0)
    <<"\n"<<flush;
  char*args[]={const_cast<char*>(solver),argv[1],nullptr};
  execv(solver,args);
  cerr<<"R160_EXEC_FAILURE "<<solver<<" errno="<<errno<<"\n";
  return 77;
}

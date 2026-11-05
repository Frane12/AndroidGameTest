// DRNAS R147 -- bounded structural prefilter + certified R132/R118 GF(2) + guarded non-XOR portfolio.
// Never modifies the CNF. All solver answers originate from frozen external solvers or
// the proof-replaying R118 on complete, source-backed parity constraints.
// Work in the probe is charged to end-to-end paired wall time.
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
using namespace std;
using Clock = chrono::steady_clock;
struct Probe {
  bool parsed=false, complete=false, over_budget=false;
  long bytes=0, size=0;
  int clauses=0, declared=-1, binary=0, horn=0, full_xor_groups=0;
  double cost_s=0.0;
  string reason="init";
};
static bool number(const string&s,int&v){
  if(s.empty())return false;
  errno=0;char*end=nullptr;long x=strtol(s.c_str(),&end,10);
  if(errno||!end||*end||x<-2000000000L||x>2000000000L)return false;
  v=int(x);return true;
}
static uint64_t parity_mask(int width,int rhs) {
  uint64_t m=0;
  for(int s=0;s<(1<<width);++s)
    if((__builtin_popcount(unsigned(s))&1)==rhs)m|=uint64_t(1)<<s;
  return m;
}
static Probe inspect(const string&src){
  Probe p;
  const auto start=Clock::now();
  struct stat sb{};
  if(stat(src.c_str(),&sb)!=0||sb.st_size<0){p.reason="stat_failed";return p;}
  p.size=long(sb.st_size);
  ifstream f(src,ios::binary);
  if(!f){p.reason="open_failed";return p;}
  const long MAX_BYTES=65536;
  const int MAX_CLAUSES=2048;
  const double MAX_S=0.003;
  map<vector<int>,uint64_t> signatures;
  int nvars=0, positives=0, pending_length=0;
  bool header=false,valid=true;
  vector<int> literals;
  string line;
  while(getline(f,line)){
    if(p.bytes+long(line.size())+1>MAX_BYTES||p.clauses>=MAX_CLAUSES||
       chrono::duration<double>(Clock::now()-start).count()>MAX_S) {
      p.over_budget=true;break;
    }
    p.bytes+=long(line.size())+1;
    istringstream stream(line);
    string token;
    if(!(stream>>token))continue;
    if(token=="c"||token=="%")continue;
    if(token=="p"){
      string kind,extra;
      if(header||!(stream>>kind>>nvars>>p.declared)||kind!="cnf"||
         nvars<1||p.declared<0||p.declared>1000000000||(stream>>extra)){
        valid=false;break;
      }
      header=true;continue;
    }
    do {
      if(!header){valid=false;break;}
      int v=0;
      if(!number(token,v)||abs(long(v))>nvars){valid=false;break;}
      if(v){
        ++pending_length;if(v>0)++positives;
        if(literals.size()<6)literals.push_back(v);
      } else {
        ++p.clauses;
        p.binary+=(pending_length==2);
        p.horn+=(positives<=1);
        if(pending_length>=2&&pending_length<=6){
          sort(literals.begin(),literals.end(),[](int a,int b){
            return abs(a)==abs(b)?a<b:abs(a)<abs(b);
          });
          bool unique=true;
          for(size_t i=1;i<literals.size();i++)
            if(abs(literals[i])==abs(literals[i-1]))unique=false;
          if(unique){
            vector<int> key;int mask=0;
            for(size_t i=0;i<literals.size();i++){
              key.push_back(abs(literals[i]));
              if(literals[i]<0)mask|=1<<int(i);
            }
            signatures[key]|=uint64_t(1)<<mask;
          }
        }
        pending_length=0;positives=0;literals.clear();
      }
      if(p.clauses>MAX_CLAUSES){p.over_budget=true;break;}
    } while(stream>>token);
    if(!valid||p.over_budget)break;
  }
  p.cost_s=chrono::duration<double>(Clock::now()-start).count();
  p.parsed=valid&&header;
  p.complete=p.parsed&&!p.over_budget&&pending_length==0&&p.clauses==p.declared&&
             p.bytes>=p.size;
  if(p.parsed){
    for(const auto&kv:signatures){
      int k=int(kv.first.size());
      uint64_t even=parity_mask(k,0),odd=parity_mask(k,1);
      p.full_xor_groups+=((kv.second&even)==even)||((kv.second&odd)==odd);
    }
  }
  p.reason=!p.parsed?"invalid_or_incomplete_header":
           p.over_budget?"bounded_prefix":"finished_scan";
  return p;
}
static int call(const string&bin,const vector<string>&arguments){
  vector<char*> argv;
  argv.reserve(arguments.size()+2);
  argv.push_back(const_cast<char*>(bin.c_str()));
  for(const auto&str:arguments)argv.push_back(const_cast<char*>(str.c_str()));
  argv.push_back(nullptr);
  execv(bin.c_str(),argv.data());
  cerr<<"R147_EXEC_FAILURE binary="<<bin<<" errno="<<errno<<" "<<strerror(errno)<<"\n";
  return 78;
}
int main(int argc,char**argv){
  if(argc!=6 && !(argc==7&&string(argv[6])=="--probe-only")){
    cerr<<"usage: r147 CNF R132_BIN R118_BIN KISSAT_BIN CADICAL_BIN [--probe-only]\n";
    return 2;
  }
  const string src=argv[1],r132=argv[2],r118=argv[3],kissat=argv[4],cadical=argv[5];
  const Probe p=inspect(src);
  const bool strong_prefix=p.parsed&&p.full_xor_groups>=2&&
       p.size<=1024*1024&&p.cost_s<=0.0035;
  const bool eligible_cadical=p.complete&&p.cost_s<=0.002&&p.clauses>=16&&
       double(p.binary)/p.clauses<0.10&&double(p.horn)/p.clauses<0.30;
  string route=strong_prefix?"R132_GF2_GATE":eligible_cadical?"CADICAL":"KISSAT";
  cout<<"c R147_ROUTE route="<<route
      <<" reason="<<p.reason
      <<" source_bytes="<<p.size<<" scanned_bytes="<<p.bytes
      <<" scanned_clauses="<<p.clauses
      <<" prefix_xor_groups="<<p.full_xor_groups
      <<" fully_scanned="<<(p.complete?1:0)
      <<" scan_s="<<p.cost_s<<"\n"<<flush;
  if(argc==7)return 0;
  if(strong_prefix)
    return call(r132,{src,r118,kissat,"wide_exact"});
  if(eligible_cadical)return call(cadical,{src});
  return call(kissat,{src});
}

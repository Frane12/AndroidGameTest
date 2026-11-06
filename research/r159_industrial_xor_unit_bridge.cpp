// DRNAS R159: bounded source-exact XOR(2/3) detection plus certified-unit bridge.
// Research prototype. Never infers XOR from incomplete clause sign patterns.
// On mixed CNFs, append only XOR-entailed units and run pinned Kissat.
// If no new justified units, exec pinned Kissat on the ORIGINAL CNF.
// Input sizes cover frozen R158 industrial CNFs; strict no-heuristic correctness.
#include <algorithm>
#include <array>
#include <chrono>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
using namespace std;
using Clock=chrono::steady_clock;
struct Key {
  array<int,3> v{};
  uint8_t k=0;
  bool operator==(const Key& x) const { return k==x.k && v==x.v; }
};
struct KeyHash {
  size_t operator()(const Key& x) const {
    uint64_t h=1469598103934665603ULL;
    for(int i=0;i<x.k;i++){h^=uint64_t(x.v[i]);h*=1099511628211ULL;}
    return size_t(h^x.k);
  }
};
struct Eq {array<int,3> v{};uint8_t k=0;uint8_t rhs=0;};
struct Mapping {
  const char *p=nullptr,*end=nullptr;size_t bytes=0;int fd=-1;
  bool open_file(const string& path) {
    fd=open(path.c_str(),O_RDONLY);
    if(fd<0)return false;
    struct stat st{};
    if(fstat(fd,&st)!=0 || st.st_size<=0 || st.st_size>96LL*1024*1024)return false;
    bytes=size_t(st.st_size);
    void* mem=mmap(nullptr,bytes,PROT_READ,MAP_PRIVATE,fd,0);
    if(mem==MAP_FAILED)return false;
    p=static_cast<const char*>(mem);end=p+bytes;return true;
  }
  ~Mapping(){if(p)munmap(const_cast<char*>(p),bytes);if(fd>=0)close(fd);}
};
static void trace(const char* route,int clauses,int patterns,int equations,int units,
                  int derived,Clock::time_point start) {
  const auto us=chrono::duration_cast<chrono::microseconds>(Clock::now()-start).count();
  cout<<"c R159_PREP route="<<route<<" clauses="<<clauses
      <<" patterns="<<patterns<<" equations="<<equations
      <<" original_units="<<units<<" derived="<<derived
      <<" decision_us="<<us<<"\n"<<flush;
}
static int exec_original(const string& original,const string& kissat,const char* reason,
                         int clauses,int patterns,int eqs,int units,Clock::time_point t0) {
  trace(reason,clauses,patterns,eqs,units,0,t0);
  char* args[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(original.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R159_EXEC_FAILURE "<<strerror(errno)<<"\n";return 77;
}
static bool parse_source(const Mapping& map,int& n,int& m,
  unordered_map<Key,uint8_t,KeyHash>& patterns,vector<pair<int,int>>& units) {
  const char *p=map.p; bool header=false;int declared=-1,clause_count=0;
  array<int,3> cl{};int k=0;
  while(p<map.end){
    while(p<map.end && (*p==' '||*p=='\t'||*p=='\r'||*p=='\n'))++p;
    if(p>=map.end)break;
    if(*p=='c'||*p=='%'){while(p<map.end && *p!='\n')++p;continue;}
    if(*p=='p'){
      if(header)return false;
      int vars=0,cnt=0;char type[32]{};
      if(sscanf(p,"p %31s %d %d",type,&vars,&cnt)!=3||strcmp(type,"cnf")||vars<1||
         vars>250000||cnt<0||cnt>2500000)return false;
      n=vars;declared=cnt;header=true;
      while(p<map.end && *p!='\n')++p;
      continue;
    }
    if(!header)return false;
    bool neg=false;
    if(*p=='-'){neg=true;++p;}
    if(p>=map.end || *p<'0'||*p>'9')return false;
    int x=0;
    while(p<map.end && *p>='0'&&*p<='9'){
      if(x>25000000)return false;
      x=x*10+(*p++-'0');
    }
    if(x>n)return false;
    if(x==0){
      if(neg)return false;
      ++clause_count;
      if(clause_count>declared)return false;
      if(k==1)units.emplace_back(abs(cl[0]),cl[0]>0?1:0);
      else if(k==2||k==3){
        Key key;key.k=uint8_t(k);
        array<pair<int,bool>,3> items{};
        for(int j=0;j<k;j++)items[j]={abs(cl[j]),cl[j]<0};
        sort(items.begin(),items.begin()+k);
        bool unique=true;
        for(int j=1;j<k;j++)if(items[j].first==items[j-1].first)unique=false;
        if(unique){
          unsigned mask=0;
          for(int j=0;j<k;j++){key.v[j]=items[j].first;if(items[j].second)mask|=1U<<j;}
          patterns[key]|=uint8_t(1U<<mask);
          if(patterns.size()>300000)return false;
        }
      }
      k=0;continue;
    }
    if(k<3)cl[k]=neg?-x:x;
    ++k;if(k>100000)return false;
  }
  if(!header||k!=0||clause_count!=declared)return false;
  m=clause_count;return true;
}
static bool strengthen(const Mapping& source,const string& output,int n,int m,
                       const vector<int>& extra) {
  // Preserve every original clause; change only the DIMACS header and append
  // units proved by exact full XOR patterns and source unit clauses.
  FILE* f=fopen(output.c_str(),"wb");
  if(!f)return false;
  bool good=fprintf(f,"p cnf %d %zu\n",n,size_t(m)+extra.size())>0;
  const char *p=source.p,*hstart=nullptr,*hend=nullptr;
  while(p<source.end){
    const char* start=p;
    while(p<source.end && *p!='\n')++p;
    const char* lineend=p;
    if(p<source.end)++p;
    const char* x=start;
    while(x<lineend && (*x==' '||*x=='\t'||*x=='\r'))++x;
    if(x<lineend && *x=='p' && (x+1==lineend||x[1]==' '||x[1]=='\t')){
      if(hstart)return false;
      hstart=start;hend=p;break;
    }
  }
  if(!hstart){fclose(f);return false;}
  good=good && fwrite(source.p,1,size_t(hstart-source.p),f)==size_t(hstart-source.p);
  good=good && fwrite(hend,1,size_t(source.end-hend),f)==size_t(source.end-hend);
  if(source.end>source.p && source.end[-1]!='\n')good=good && fputc('\n',f)!=EOF;
  for(int v:extra)if(fprintf(f,"%d 0\n",v)<0)good=false;
  if(fclose(f)!=0)good=false;
  return good;
}
int main(int argc,char** argv) {
  if(argc!=3){cerr<<"Usage: r159_xor_bridge INPUT_CNF PINNED_KISSAT\n";return 2;}
  const string original=argv[1],kissat=argv[2];
  const auto started=Clock::now();
  Mapping source;
  if(!source.open_file(original))
    return exec_original(original,kissat,"source_over_cap",0,0,0,0,started);
  int n=0,m=0;
  unordered_map<Key,uint8_t,KeyHash> patterns;
  patterns.max_load_factor(0.8f);
  patterns.reserve(60000);
  vector<pair<int,int>> units;units.reserve(4000);
  if(!parse_source(source,n,m,patterns,units))
    return exec_original(original,kissat,"parse_or_budget_fallback",m,int(patterns.size()),0,int(units.size()),started);
  vector<Eq> eqs;eqs.reserve(min(size_t(100000),patterns.size()));
  for(const auto& kv:patterns) {
    const Key& key=kv.first;uint8_t masks=kv.second;
    const uint8_t even=key.k==2?uint8_t(0x09):uint8_t(0x69);
    const uint8_t odd=key.k==2?uint8_t(0x06):uint8_t(0x96);
    if((masks&even)==even)eqs.push_back({key.v,key.k,1});
    if((masks&odd)==odd)eqs.push_back({key.v,key.k,0});
  }
  if(eqs.empty()||units.empty())
    return exec_original(original,kissat,"no_propagating_xor",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
  vector<int8_t> val(size_t(n)+1,-1);
  vector<int> queue;queue.reserve(units.size()+4000);
  for(auto [v,rhs]:units){
    if(val[v]!=-1 && val[v]!=rhs)
      return exec_original(original,kissat,"source_unit_conflict",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
    if(val[v]==-1){val[v]=int8_t(rhs);queue.push_back(v);}
  }
  vector<int> head(size_t(n)+1,-1);
  vector<int> link;vector<int> row_id;
  link.reserve(eqs.size()*3);row_id.reserve(eqs.size()*3);
  for(size_t i=0;i<eqs.size();++i)for(int j=0;j<eqs[i].k;j++){
    const int v=eqs[i].v[j];
    row_id.push_back(int(i));link.push_back(head[v]);head[v]=int(link.size()-1);
  }
  const size_t seed_size=queue.size();
  for(size_t qi=0;qi<queue.size();qi++){
    int v=queue[qi];
    for(int at=head[v];at!=-1;at=link[size_t(at)]){
      const Eq& e=eqs[size_t(row_id[size_t(at)])];
      int missing=0,unknown=0,rhs=e.rhs;
      for(int j=0;j<e.k;j++){
        int u=e.v[j];if(val[u]<0){++unknown;missing=u;}
        else rhs^=val[u];
      }
      if(unknown==0 && rhs)
        return exec_original(original,kissat,"algebraic_conflict_recheck",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
      if(unknown==1){
        if(val[missing]<0){val[missing]=int8_t(rhs);queue.push_back(missing);}
        else if(val[missing]!=rhs)
          return exec_original(original,kissat,"unit_conflict_recheck",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
        if(queue.size()-seed_size>100000)
          return exec_original(original,kissat,"derived_budget",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
      }
    }
  }
  if(queue.size()==seed_size)
    return exec_original(original,kissat,"no_new_units",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
  vector<int> derived;derived.reserve(queue.size()-seed_size);
  for(size_t i=seed_size;i<queue.size();i++){
    const int v=queue[i];derived.push_back(val[v]?v:-v);
  }
  char path[]="/tmp/drnas-r159-XXXXXX";
  int fd=mkstemp(path);
  if(fd<0)return exec_original(original,kissat,"mkstemp_failed",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
  close(fd);
  if(!strengthen(source,path,n,m,derived)){
    unlink(path);
    return exec_original(original,kissat,"augment_io_failed",m,int(patterns.size()),int(eqs.size()),int(units.size()),started);
  }
  trace("derived_units",m,int(patterns.size()),int(eqs.size()),int(units.size()),int(derived.size()),started);
  fflush(nullptr);
  pid_t child=fork();
  if(child<0){
    unlink(path);
    cerr<<"R159_FORK_FAILED "<<strerror(errno)<<"\n";return 77;
  }
  if(child==0){
    // Parent timeout kills parent process; do not leave orphan Kissat running.
    prctl(PR_SET_PDEATHSIG,SIGKILL);
    if(getppid()==1)_exit(79);
    char* args[]={const_cast<char*>(kissat.c_str()),path,nullptr};
    execv(args[0],args);
    _exit(77);
  }
  int status=0;
  while(waitpid(child,&status,0)<0){if(errno!=EINTR){unlink(path);return 77;}}
  unlink(path);
  if(WIFEXITED(status))return WEXITSTATUS(status);
  if(WIFSIGNALED(status))return 128+WTERMSIG(status);
  return 77;
}

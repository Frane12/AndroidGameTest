// DRNAS X1: independently implemented native SAT solver, 2026-11-12.
// Standard CDCL techniques and bounded exact bucket elimination; no linked solver.
// Build: c++ -std=c++20 -O3 -DNDEBUG x1.cpp -o drnas-x1
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
using Clock=std::chrono::steady_clock;
struct Budget {
  Clock::time_point start=Clock::now(); double seconds=3.0;
  double elapsed() const {return std::chrono::duration<double>(Clock::now()-start).count();}
  bool expired() const {return elapsed()>=seconds;}
};
struct Formula { int n=0; std::vector<std::vector<int>> clauses; };
static Formula read_cnf(const std::string& path, const Budget& budget) {
  std::ifstream in(path); if(!in) throw std::runtime_error("cannot open input");
  Formula f; std::string line; bool header=false; long long expected=-1, count=0;
  std::vector<int> c;
  while(std::getline(in,line)) {
    auto p=line.find_first_not_of(" \t\r"); if(p==std::string::npos || line[p]=='c') continue;
    if(line[p]=='p') {
      if(header || !c.empty()) throw std::runtime_error("misplaced/repeated header");
      std::istringstream ss(line.substr(p)); std::string a,b,extra; long long n,m;
      if(!(ss>>a>>b>>n>>m)||b!="cnf"||n<0||n>10000000||m<0||(ss>>extra))
        throw std::runtime_error("invalid DIMACS header");
      f.n=static_cast<int>(n); expected=m; header=true; continue;
    }
    if(!header) throw std::runtime_error("missing DIMACS header");
    std::istringstream ss(line.substr(p)); std::string tok;
    while(ss>>tok) {
      size_t used=0; long long x=std::stoll(tok,&used);
      if(used!=tok.size()||x < -static_cast<long long>(f.n)||x>f.n)
        throw std::runtime_error("invalid literal");
      if(x) c.push_back(2*(static_cast<int>(std::llabs(x))-1)+(x<0));
      else {
        ++count; std::sort(c.begin(),c.end()); c.erase(std::unique(c.begin(),c.end()),c.end());
        bool taut=false;
        for(size_t i=1;i<c.size();++i) if((c[i]^1)==c[i-1]) {taut=true;break;}
        if(!taut) f.clauses.push_back(c);
        c.clear();
      }
    }
    if((count&1023)==0 && budget.expired()) throw std::runtime_error("input time limit");
  }
  if(!header||!c.empty()||count!=expected) throw std::runtime_error("DIMACS clause count/terminator mismatch");
  return f;
}
static int external(int l) {return (l&1)?-(l/2+1):(l/2+1);}
static bool model_ok(const Formula& f,const std::vector<int8_t>& m) {
  if(m.size()!=static_cast<size_t>(f.n)) return false;
  for(const auto& c:f.clauses) {
    bool sat=false; for(int l:c) if(m[l/2]>=0 && (m[l/2]!=(l&1))) {sat=true;break;}
    if(!sat) return false;
  }
  return true;
}
struct Proof {
  std::string path; std::ofstream stream; size_t bytes=0; bool full=false;
  static constexpr size_t max_bytes=8u*1024u*1024u;
  explicit Proof(std::string p):path(std::move(p)) {reset(false);}
  void reset(bool factor) {
    if(stream.is_open()) stream.close();
    bytes=0;full=false;
    if(path.empty()) return;
    stream.open(path,std::ios::trunc); if(!stream) throw std::runtime_error("cannot open proof");
    if(factor) put("c X1_FACTOR_V1\n");
  }
  void put(const std::string& s) {
    if(path.empty()||full) return;
    if(bytes+s.size()>max_bytes){full=true;return;}
    stream<<s; bytes+=s.size(); if(!stream) throw std::runtime_error("proof write failed");
  }
  void clause(const std::vector<int>& c) {
    if(path.empty()) return;
    std::string s; for(int l:c) s+=std::to_string(external(l))+" "; put(s+"0\n");
  }
};
struct Stats {
  uint64_t decisions=0,conflicts=0,propagations=0,restarts=0,learned=0,deleted=0,low_lbd=0;
  uint64_t factor_steps=0,factor_checks=0; int factor_max_width=0;
  double factor_s=0; std::string factor_stop="off",route="cdcl";
};
#include "x1_memory.hpp"
#include "x1_memory2.hpp"
class Core {
  struct Clause {std::vector<int> l; bool learned=false,dead=false; int lbd=0;};
  struct Watch {int id,block;};
  const Formula& f; Budget& budget; Proof& proof; Stats& stats;
  std::vector<Clause> db; std::vector<std::vector<Watch>> watch;
  std::vector<int8_t> val,phase; std::vector<int> level,reason,trail,limits;
  std::vector<double> activity; std::vector<int> heap,pos;
  std::vector<uint8_t> seen; double increment=1.0; size_t qhead=0; bool okay=true;
  uint64_t seed;
  X1Memory* memory=nullptr;
  X1Memory2* memory2=nullptr;
  uint64_t tie(int v) const {
    uint64_t z=static_cast<uint64_t>(v)+seed+0x9e3779b97f4a7c15ULL;
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL; z=(z^(z>>27))*0x94d049bb133111ebULL; return z^(z>>31);
  }
  bool better(int a,int b) const {return activity[a]!=activity[b]?activity[a]>activity[b]:tie(a)<tie(b);}
  void swap_heap(int a,int b){std::swap(heap[a],heap[b]);pos[heap[a]]=a;pos[heap[b]]=b;}
  void up(int i){while(i>0){int p=(i-1)/2;if(!better(heap[i],heap[p]))break;swap_heap(i,p);i=p;}}
  void down(int i){for(;;){int j=2*i+1;if(j>=static_cast<int>(heap.size()))break;
    if(j+1<static_cast<int>(heap.size())&&better(heap[j+1],heap[j]))++j;
    if(!better(heap[j],heap[i]))break;
    swap_heap(i,j);i=j;}}
  void insert(int v){if(pos[v]>=0)return;pos[v]=static_cast<int>(heap.size());heap.push_back(v);up(pos[v]);}
  int pop(){int v=heap[0];pos[v]=-1;if(heap.size()==1){heap.pop_back();return v;}
    heap[0]=heap.back();heap.pop_back();pos[heap[0]]=0;down(0);return v;}
  int dl() const{return static_cast<int>(limits.size());}
  int value(int l) const {return val[l/2]<0?-1:(val[l/2]!=(l&1));}
  bool enqueue(int l,int why) {
    int v=l/2, x=1-(l&1); if(val[v]>=0)return val[v]==x;
    val[v]=static_cast<int8_t>(x);phase[v]=static_cast<int8_t>(x);level[v]=dl();reason[v]=why;trail.push_back(l);return true;
  }
  int add(std::vector<int> c,bool learned,int lbd=0) {
    int id=static_cast<int>(db.size());db.push_back({std::move(c),learned,false,lbd});
    auto& ls=db.back().l;
    if(ls.size()>=2){watch[ls[0]].push_back({id,ls[1]});watch[ls[1]].push_back({id,ls[0]});}
    return id;
  }
  int propagate() {
    uint64_t ticks=0;
    while(qhead<trail.size()) {
      int fl=trail[qhead++]^1;++stats.propagations;auto& ws=watch[fl];size_t j=0;
      for(size_t i=0;i<ws.size();++i) {
        if((++ticks&4095)==0&&budget.expired()){
          for(;i<ws.size();++i)ws[j++]=ws[i];
          ws.resize(j);return -2;
        }
        Watch w=ws[i];auto& c=db[w.id];if(c.dead)continue;
        if(value(w.block)==1){ws[j++]=w;continue;}
        if(c.l[0]==fl)std::swap(c.l[0],c.l[1]);
        if(c.l[1]!=fl)throw std::runtime_error("watch invariant");
        int first=c.l[0];w.block=first;
        if(value(first)==1){ws[j++]=w;continue;}
        bool moved=false;
        for(size_t k=2;k<c.l.size();++k)if(value(c.l[k])!=0){
          std::swap(c.l[1],c.l[k]);watch[c.l[1]].push_back({w.id,first});moved=true;break;
        }
        if(moved)continue;
        ws[j++]=w;
        if(value(first)==0 || !enqueue(first,w.id)) {
          for(++i;i<ws.size();++i)ws[j++]=ws[i];
          ws.resize(j);return w.id;
        }
      }
      ws.resize(j);
      if((stats.propagations&1023)==0&&budget.expired())return -2;
    }
    return -1;
  }
  void bump(int v){activity[v]+=increment;if(pos[v]>=0)up(pos[v]);
    if(activity[v]>1e100){for(double& a:activity)a*=1e-100;increment*=1e-100;}}
  std::vector<int> analyze(int id,int& back,int& lbd) {
    std::vector<int> out(1,-1),touched;int pending=0,p=-1;int at=static_cast<int>(trail.size())-1;
    do {
      if(id<0)throw std::runtime_error("missing conflict reason");
      for(int l:db[id].l){int v=l/2;if((p>=0&&v==p/2)||seen[v]||level[v]==0)continue;
        seen[v]=1;touched.push_back(v);bump(v);if(level[v]==dl())++pending;else out.push_back(l);}
      while(at>=0&&!seen[trail[at]/2])--at;
      if(at<0||pending<=0)throw std::runtime_error("analysis invariant");
      p=trail[at--];seen[p/2]=0;--pending;id=reason[p/2];
    }while(pending>0);
    out[0]=p^1;back=0;
    if(out.size()>1){size_t best=1;for(size_t i=2;i<out.size();++i)if(level[out[i]/2]>level[out[best]/2])best=i;
      std::swap(out[1],out[best]);back=level[out[1]/2];}
    std::vector<int> levels;for(int l:out)levels.push_back(level[l/2]);
    std::sort(levels.begin(),levels.end());lbd=static_cast<int>(std::unique(levels.begin(),levels.end())-levels.begin());
    for(int v:touched)seen[v]=0;
    return out;
  }
  void cancel(int target){if(dl()<=target)return;size_t keep=static_cast<size_t>(limits[target]);
    for(size_t i=trail.size();i>keep;--i){int v=trail[i-1]/2;val[v]=-1;reason[v]=-1;level[v]=0;insert(v);}
    trail.resize(keep);qhead=std::min(qhead,keep);limits.resize(target);}
  void reduce(){
    std::vector<uint8_t> locked(db.size(),0);for(int v=0;v<f.n;++v)if(val[v]>=0&&reason[v]>=0)locked[reason[v]]=1;
    std::vector<int> ids;
    for(size_t i=0;i<db.size();++i)if(db[i].learned&&!db[i].dead&&db[i].l.size()>2&&db[i].lbd>2&&!locked[i])ids.push_back(static_cast<int>(i));
    std::sort(ids.begin(),ids.end(),[&](int a,int b){return std::make_tuple(db[a].lbd,db[a].l.size())>std::make_tuple(db[b].lbd,db[b].l.size());});
    for(size_t i=0;i<ids.size()/2;++i){auto& c=db[ids[i]];c.dead=true;std::vector<int>().swap(c.l);++stats.deleted;}
    // Deletion records are unnecessary: retaining implied clauses is sound for DRUP checking.
  }
public:
  Core(const Formula& formula,Budget& b,Proof& p,Stats& s,uint64_t se,X1Memory* mem=nullptr,X1Memory2* mem2=nullptr):f(formula),budget(b),proof(p),stats(s),
      watch(static_cast<size_t>(2)*f.n),val(f.n,-1),phase(f.n,0),level(f.n,0),reason(f.n,-1),
      activity(f.n,0),pos(f.n,-1),seen(f.n,0),seed(se),memory(mem),memory2(mem2){
    std::vector<uint8_t> used(f.n,0);
    for(const auto& c:f.clauses){int id=add(c,false);if(c.empty())okay=false;
      if(c.size()==1&&!enqueue(c[0],id))okay=false;
      for(int l:c){used[l/2]=1;activity[l/2]+=1.0/static_cast<double>(c.size());}}
    for(int v=0;v<f.n;++v)if(used[v])insert(v);
  }
  size_t assigned()const{return trail.size();}
  int depth()const{return dl();}
  int solve(std::vector<int8_t>& model){
    if(!okay){proof.clause({});return proof.full?0:20;}
    uint64_t since=0,limit=96,next_reduce=2000;
    while(!budget.expired()&&!proof.full){
      int conflict=propagate();if(conflict==-2)return 0;
      if(conflict>=0){
        ++stats.conflicts;++since;
        if(dl()==0){proof.clause({});return proof.full?0:20;}
        int back,lbd;auto learned=analyze(conflict,back,lbd);cancel(back);proof.clause(learned);
        int id=add(std::move(learned),true,lbd);++stats.learned;if(lbd<=2)++stats.low_lbd;
        if(!enqueue(db[id].l[0],id))throw std::runtime_error("asserting clause invariant");
        increment/=0.95;
        if(stats.conflicts>=next_reduce){reduce();next_reduce=stats.conflicts+2000;}
        if(since>=limit){cancel(0);since=0;limit=std::min<uint64_t>(8192,limit+limit/2);++stats.restarts;}
        if(db.size()>f.clauses.size()+1000000u)return 0;
      }else{
        int v=-1;while(!heap.empty()){int t=pop();if(val[t]<0){v=t;break;}}
        if(v<0){model=val;for(auto& x:model)if(x<0)x=0;return 10;}
        const int action=memory2?memory2->select(stats,trail.size(),dl(),budget,v):
          (memory?memory->select(stats,trail.size(),dl(),budget.elapsed()):0);
        const int chosen=phase[v]^(action==1);
        limits.push_back(static_cast<int>(trail.size()));++stats.decisions;
        if(!enqueue(2*v+(chosen?0:1),-1))throw std::runtime_error("decision invariant");
      }
    }
    return 0;
  }
};
struct Factor {
  std::vector<int> vars; std::vector<uint64_t> bits; bool active=true;
  bool has(unsigned a) const{return (bits[a/64]>>(a%64))&1u;}
  void set(unsigned a){bits[a/64]|=uint64_t(1)<<(a%64);}
};
struct Witness {int var;std::vector<int> vars;std::vector<uint8_t> choice;};
class Eliminator {
  const Formula& f; Budget& budget; Proof& proof; Stats& stats;
  int width;double end;uint64_t max_work;
  std::vector<Factor> factors;std::vector<std::vector<int>> occ;
  std::vector<uint8_t> alive;std::vector<unsigned> version,mark;unsigned stamp=0;
  std::vector<Witness> history;
  using Item=std::tuple<int,int,int,unsigned>;
  std::priority_queue<Item,std::vector<Item>,std::greater<Item>> queue;
  bool expired() const{return budget.elapsed()>=end||budget.expired()||stats.factor_checks>=max_work||proof.full;}
  std::vector<int> scope(int v,std::vector<int>* bucket=nullptr){
    ++stamp;std::vector<int> u;
    for(int id:occ[v])if(factors[id].active){if(bucket)bucket->push_back(id);
      for(int x:factors[id].vars)if(mark[x]!=stamp){mark[x]=stamp;u.push_back(x);
        if(!bucket&&static_cast<int>(u.size())>width)return u;}}
    std::sort(u.begin(),u.end());return u;
  }
  void schedule(int v){if(!alive[v])return;++version[v];auto u=scope(v);
    if(static_cast<int>(u.size())<=width)queue.emplace(static_cast<int>(u.size()),static_cast<int>(occ[v].size()),v,version[v]);}
  void add(Factor g){int id=static_cast<int>(factors.size());for(int v:g.vars)occ[v].push_back(id);factors.push_back(std::move(g));}
public:
  Eliminator(const Formula& ff,Budget& b,Proof& p,Stats& s,int w,double slice,uint64_t work):f(ff),budget(b),proof(p),stats(s),
      width(w),end(std::min(b.seconds,b.elapsed()+slice)),max_work(work),occ(f.n),alive(f.n,0),version(f.n,0),mark(f.n,0){}
  int solve(std::vector<int8_t>& model){
    stats.factor_stop="size_gate";
    if(f.n>2048||f.clauses.size()>20000)return 0;
    for(const auto& c:f.clauses)if(static_cast<int>(c.size())>width)return 0;
    proof.reset(true);
    for(const auto& c:f.clauses){
      if(expired()){stats.factor_stop="budget";return 0;}
      if(c.empty()){proof.put("u\n");stats.factor_stop="unsat";return 20;}
      Factor g;for(int l:c)g.vars.push_back(l/2);
      unsigned size=1u<<g.vars.size();g.bits.assign((size+63)/64,0);
      for(unsigned a=0;a<size;++a){bool sat=false;
        for(size_t j=0;j<c.size();++j)if(((a>>j)&1u)!=static_cast<unsigned>(c[j]&1)){sat=true;break;}
        if(sat)g.set(a);}
      for(int v:g.vars)alive[v]=1;
      add(std::move(g));
    }
    for(int v=0;v<f.n;++v)if(alive[v]){schedule(v);if((v&63)==0&&expired()){stats.factor_stop="budget";return 0;}}
    int remaining=std::accumulate(alive.begin(),alive.end(),0);
    while(remaining){
      if(expired()){stats.factor_stop="budget";return 0;}
      while(!queue.empty()&&(!alive[std::get<2>(queue.top())]||version[std::get<2>(queue.top())]!=std::get<3>(queue.top())))queue.pop();
      if(queue.empty()){stats.factor_stop="width";return 0;}
      int v=std::get<2>(queue.top());queue.pop();std::vector<int> bucket;auto u=scope(v,&bucket);
      if(static_cast<int>(u.size())>width){schedule(v);continue;}
      if(bucket.empty()){alive[v]=0;--remaining;continue;}
      stats.factor_max_width=std::max(stats.factor_max_width,static_cast<int>(u.size()));
      auto at=std::lower_bound(u.begin(),u.end(),v)-u.begin();
      Factor out;out.vars=u;out.vars.erase(out.vars.begin()+at);unsigned count=1u<<out.vars.size();out.bits.assign((count+63)/64,0);
      Witness rec{v,out.vars,std::vector<uint8_t>(count,0)};
      std::vector<std::vector<int>> projections;
      for(int id:bucket){std::vector<int> m;for(int x:factors[id].vars)m.push_back(static_cast<int>(std::lower_bound(u.begin(),u.end(),x)-u.begin()));projections.push_back(std::move(m));}
      unsigned allowed=0;
      for(unsigned a=0;a<(1u<<u.size());++a){
        if((a&255u)==0&&expired()){stats.factor_stop="budget";return 0;}
        bool good=true;
        for(size_t j=0;j<bucket.size();++j){unsigned p=0;const auto& map=projections[j];
          for(size_t k=0;k<map.size();++k)p|=((a>>map[k])&1u)<<k;
          ++stats.factor_checks;if(!factors[bucket[j]].has(p)){good=false;break;}}
        if(good){unsigned lowmask=(1u<<at)-1u;unsigned b=(a&lowmask)|((a>>(at+1))<<at);
          if(!out.has(b)){out.set(b);++allowed;}rec.choice[b]|=1u<<((a>>at)&1u);}
      }
      proof.put("e "+std::to_string(v+1)+"\n");++stats.factor_steps;
      if(allowed==0){proof.put("u\n");stats.factor_stop="unsat";return proof.full?0:20;}
      history.push_back(std::move(rec));
      for(int id:bucket){factors[id].active=false;std::vector<uint64_t>().swap(factors[id].bits);}
      alive[v]=0;--remaining;
      if(allowed<count)add(std::move(out));
      for(int x:u)if(x!=v)schedule(x);
    }
    model.assign(f.n,0);
    for(auto i=history.rbegin();i!=history.rend();++i){unsigned a=0;for(size_t j=0;j<i->vars.size();++j)a|=static_cast<unsigned>(model[i->vars[j]])<<j;
      uint8_t choices=i->choice[a];if(!choices)throw std::runtime_error("factor reconstruction invariant");model[i->var]=(choices&1u)?0:1;}
    stats.factor_stop="sat";return 10;
  }
};
int main(int argc,char** argv){
  Budget budget;std::string path,mode="auto",proof_path,mem_load,mem_save,mem_log,mem2_load,mem2_save,mem2_log;uint64_t seed=17;int width=12,mem_interval=64,mem2_interval=8;bool mem_on=false,mem_frozen=false,mem2_on=false,mem2_frozen=false,mem2_shadow=false;
  try{
    for(int i=1;i<argc;++i){std::string arg=argv[i];auto next=[&](){if(++i>=argc)throw std::runtime_error("missing option value");return std::string(argv[i]);};
      if(arg=="--seconds")budget.seconds=std::stod(next());else if(arg=="--mode")mode=next();
      else if(arg=="--proof")proof_path=next();else if(arg=="--seed")seed=std::stoull(next());else if(arg=="--width")width=std::stoi(next());
      else if(arg=="--memory")mem_on=true;
      else if(arg=="--memory-load"){mem_load=next();mem_on=true;}
      else if(arg=="--memory-save"){mem_save=next();mem_on=true;}
      else if(arg=="--memory-log"){mem_log=next();mem_on=true;}
      else if(arg=="--memory-frozen"){mem_frozen=true;mem_on=true;}
      else if(arg=="--memory-interval"){mem_interval=std::stoi(next());mem_on=true;}
      else if(arg=="--memory2"){mem2_on=true;}
      else if(arg=="--memory2-load"){mem2_load=next();mem2_on=true;}
      else if(arg=="--memory2-save"){mem2_save=next();mem2_on=true;}
      else if(arg=="--memory2-log"){mem2_log=next();mem2_on=true;}
      else if(arg=="--memory2-frozen"){mem2_frozen=true;mem2_on=true;}
      else if(arg=="--memory2-shadow"){mem2_shadow=true;mem2_on=true;}
      else if(arg=="--memory2-interval"){mem2_interval=std::stoi(next());mem2_on=true;}
      else if(arg=="--help"){std::cout<<"drnas-x1 [--mode core|factor|auto] [--seconds N] [--width 4..16] [--proof FILE] [--seed N] [--memory] [--memory-load FILE] [--memory-save FILE] [--memory-log FILE] [--memory-frozen] [--memory-interval 8..4096] [--memory2] [--memory2-load FILE] [--memory2-save FILE] [--memory2-log FILE] [--memory2-frozen] [--memory2-shadow] [--memory2-interval 4..1024] input.cnf\n";return 0;}
      else if(!arg.empty()&&arg[0]=='-')throw std::runtime_error("unknown option");else if(path.empty())path=arg;else throw std::runtime_error("multiple input files");}
    if(path.empty()||(mode!="core"&&mode!="factor"&&mode!="auto")||!std::isfinite(budget.seconds)||budget.seconds<=0||width<4||width>16)
      throw std::runtime_error("invalid arguments");
    if(mem_on&&mem2_on)throw std::runtime_error("MEMORY1 and MEMORY2 cannot both control a single run");
    auto f=read_cnf(path,budget);Proof proof(proof_path);Stats stats;std::vector<int8_t> model;int result=0;X1Memory memory(f,seed,mem_on,mem_frozen,mem_interval,mem_load,mem_save,mem_log);X1Memory2 memory2(f,mem2_on,mem2_frozen,mem2_shadow,mem2_interval,mem2_load,mem2_save,mem2_log);size_t last_trail=0;int last_depth=0;
    if(mode!="core"&&!budget.expired()){
      double t=budget.elapsed();double slice=mode=="factor"?budget.seconds:std::min(0.05,budget.seconds*0.03);
      if(f.n<=2048 && f.clauses.size()<=20000){
        Eliminator elim(f,budget,proof,stats,width,slice,mode=="factor"?200000000ULL:2000000ULL);
        result=elim.solve(model);
      }else stats.factor_stop="size_gate";stats.factor_s=budget.elapsed()-t;if(result)stats.route="factor";
    }
    if(result==0&&mode!="factor"&&!budget.expired()){
      proof.reset(false);Core core(f,budget,proof,stats,seed,mem_on?&memory:nullptr,mem2_on?&memory2:nullptr);result=core.solve(model);last_trail=core.assigned();last_depth=core.depth();stats.route="cdcl";
    }
    if(result==10&&!model_ok(f,model))throw std::runtime_error("invalid internal SAT witness");
    if(proof.stream.is_open()){proof.stream.flush();if(!proof.stream)throw std::runtime_error("proof flush failed");}
    if(budget.expired()||proof.full)result=0;
    memory.finish(stats,last_trail,last_depth,budget.elapsed(),result);
    memory2.finish(stats,last_trail,last_depth,budget.elapsed(),result);
    std::cout<<"c X1_STATS {\"mode\":\""<<mode<<"\",\"route\":\""<<stats.route<<"\",\"decisions\":"<<stats.decisions
      <<",\"conflicts\":"<<stats.conflicts<<",\"propagations\":"<<stats.propagations<<",\"restarts\":"<<stats.restarts
      <<",\"learned\":"<<stats.learned<<",\"deleted\":"<<stats.deleted<<",\"factor_steps\":"<<stats.factor_steps
      <<",\"factor_checks\":"<<stats.factor_checks<<",\"factor_max_width\":"<<stats.factor_max_width<<",\"factor_s\":"<<stats.factor_s
      <<",\"factor_stop\":\""<<stats.factor_stop<<"\",\"elapsed_s\":"<<budget.elapsed()<<",\"proof_bytes\":"<<proof.bytes<<",\"external_solver_calls\":0,\"memory_on\":"<<(memory.enabled?"true":"false")<<",\"memory_frozen\":"<<(memory.frozen?"true":"false")<<",\"memory_events\":"<<memory.events<<",\"memory_flip_blocks\":"<<memory.flips<<",\"low_lbd\":"<<stats.low_lbd
      <<",\"memory2_on\":"<<(memory2.enabled?"true":"false")<<",\"memory2_frozen\":"<<(memory2.frozen?"true":"false")
      <<",\"memory2_shadow\":"<<(memory2.shadow?"true":"false")<<",\"memory2_episodes\":"<<memory2.episodes
      <<",\"memory2_horizon_observations\":"<<memory2.horizon_observations<<",\"memory2_flip_blocks\":"<<memory2.flip_blocks
      <<",\"memory2_exploration_blocks\":"<<memory2.exploration_blocks<<"}\n";
    if(result==10){std::cout<<"s SATISFIABLE\nv";for(int v=0;v<f.n;++v){if(v&&v%32==0)std::cout<<"\nv";std::cout<<' '<<(model[v]?v+1:-v-1);}std::cout<<" 0\n";}
    else if(result==20)std::cout<<"s UNSATISFIABLE\n";else std::cout<<"s UNKNOWN\n";
    return result;
  }catch(const std::exception& e){if(std::string(e.what())=="input time limit"){std::cout<<"s UNKNOWN\n";return 0;}std::cerr<<"c X1_ERROR "<<e.what()<<'\n';std::cout<<"s UNKNOWN\n";return 1;}
}

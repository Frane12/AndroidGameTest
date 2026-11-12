// DRNAS X1 MEMORY1: bounded before/action/after episodes, optional persistent policy.
// The controller ONLY selects CDCL decision polarity. It never asserts a clause,
// changes the proof, accepts a witness, or claims a SAT/UNSAT result.
#pragma once
#include <array>
#include <cstdio>
#include <cmath>
#include <iomanip>
#include <stdexcept>

struct X1Memory {
  static constexpr int CONTEXTS = 16;
  static constexpr int ARMS = 2; // 0: phase saving, 1: inverted saved phase
  struct State {
    uint64_t decisions=0,conflicts=0,propagations=0,learned=0,low_lbd=0;
    size_t trail=0; int depth=0; double elapsed=0;
  };
  struct Cell {uint64_t samples=0; double reward_sum=0;};
  std::array<std::array<Cell,ARMS>,CONTEXTS> cells{};
  bool enabled=false, frozen=false, active=false;
  int interval=64, base_context=0, current_context=0, current_arm=0;
  uint64_t signature=0, events=0, flips=0, seed=17;
  State before{};
  std::string load_path,save_path,log_path;
  std::ofstream log;

  static uint64_t mix(uint64_t h,uint64_t x) {
    x+=0x9e3779b97f4a7c15ULL;
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return (h^(x^(x>>31)))*1099511628211ULL;
  }
  static uint64_t fingerprint(const Formula& f) {
    // A variable-rename-invariant coarse structural signature, not a graph isomorphism test.
    uint64_t h=mix(1469598103934665603ULL,static_cast<uint64_t>(f.n));
    h=mix(h,f.clauses.size());
    std::array<uint64_t,9> lengths{};
    std::vector<int> positive(f.n,0),negative(f.n,0);
    for(const auto& c:f.clauses){
      ++lengths[std::min<size_t>(8,c.size())];
      for(int l:c)(l&1?negative[l/2]:positive[l/2])++;
    }
    for(uint64_t n:lengths)h=mix(h,n);
    std::vector<uint64_t> degrees;degrees.reserve(f.n);
    for(int v=0;v<f.n;++v){
      unsigned p=static_cast<unsigned>(positive[v]),n=static_cast<unsigned>(negative[v]);
      degrees.push_back((static_cast<uint64_t>(std::min(1023u,p+n))<<12)
        |(static_cast<uint64_t>(std::min(1023u,std::min(p,n)))<<2)
        |static_cast<uint64_t>((p==0)||(n==0)));
    }
    std::sort(degrees.begin(),degrees.end());
    for(uint64_t d:degrees)h=mix(h,d);
    return h;
  }
  explicit X1Memory(const Formula& f,uint64_t ss,bool on,bool freeze,int period,
                    std::string read_file,std::string write_file,std::string trace_file):
    enabled(on),frozen(freeze),interval(period),seed(ss),
    load_path(std::move(read_file)),save_path(std::move(write_file)),log_path(std::move(trace_file)) {
    if(!enabled)return;
    if(interval<8||interval>4096)throw std::runtime_error("memory interval outside 8..4096");
    if(frozen&&!save_path.empty())throw std::runtime_error("frozen memory cannot save");
    signature=fingerprint(f);
    size_t binary=0;
    for(const auto& c:f.clauses)binary+=(c.size()<=2);
    base_context=(binary*2>=f.clauses.size()?1:0)|(f.clauses.size()>3u*static_cast<size_t>(f.n)?2:0);
    if(!load_path.empty())load();
    if(!log_path.empty()){log.open(log_path,std::ios::trunc);if(!log)throw std::runtime_error("cannot create memory trace");}
  }
  void load(){
    std::ifstream in(load_path);
    if(!in)throw std::runtime_error("cannot load memory state");
    std::string version;int contexts=0,arms=0;
    if(!(in>>version>>contexts>>arms)||version!="X1MEMORY1"||contexts!=CONTEXTS||arms!=ARMS)
      throw std::runtime_error("incompatible memory state");
    for(int c=0;c<CONTEXTS;++c)for(int a=0;a<ARMS;++a) {
      int context=-1,arm=-1;uint64_t n=0;double value=0;
      if(!(in>>context>>arm>>n>>value)||context!=c||arm!=a||
         n>1000000000ULL||!std::isfinite(value)||std::abs(value)>1000000000.0)
        throw std::runtime_error("corrupt memory state");
      cells[c][a]={n,value};
    }
    std::string trailing;
    if(in>>trailing)throw std::runtime_error("trailing memory data");
  }
  void save(){
    if(!enabled||frozen||save_path.empty())return;
    const auto tmp=save_path+".tmp";
    {
      std::ofstream out(tmp,std::ios::trunc);
      if(!out)throw std::runtime_error("cannot create memory state");
      out<<"X1MEMORY1 "<<CONTEXTS<<" "<<ARMS<<"\n"<<std::setprecision(17);
      for(int c=0;c<CONTEXTS;++c)for(int a=0;a<ARMS;++a)
        out<<c<<" "<<a<<" "<<cells[c][a].samples<<" "<<cells[c][a].reward_sum<<"\n";
      out.flush();
      if(!out)throw std::runtime_error("cannot write memory state");
    }
    if(std::rename(tmp.c_str(),save_path.c_str())!=0)
      throw std::runtime_error("cannot atomically promote memory state");
  }
  static State snapshot(const Stats& s,size_t trail,int depth,double t){
    return {s.decisions,s.conflicts,s.propagations,s.learned,s.low_lbd,trail,depth,t};
  }
  int context(const State& s)const{
    int c=base_context;
    if(s.decisions>=8&&s.conflicts*4>s.decisions)c|=4;
    if(s.depth>=8)c|=8;
    return c;
  }
  int choose(int c)const {
    const auto& a=cells[c];
    const uint64_t total=a[0].samples+a[1].samples;
    if(frozen){
      if(!a[0].samples&&!a[1].samples)return 0;
      const double s0=a[0].samples?a[0].reward_sum/a[0].samples:0;
      const double s1=a[1].samples?a[1].reward_sum/a[1].samples:0;
      return s1>s0+1e-12?1:0;
    }
    // Bounded deterministic bandit exploration; no random or unsafe logical deductions.
    if(a[0].samples==0)return 0;
    if(a[1].samples==0)return 1;
    const auto estimate=[&](int arm){
      const auto& x=a[arm];
      return x.reward_sum/x.samples+0.05*std::sqrt(std::log(double(total)+1)/x.samples);
    };
    return estimate(1)>estimate(0)?1:0;
  }
  void emit_state(const State& s){
    log<<"{\"decisions\":"<<s.decisions<<",\"conflicts\":"<<s.conflicts
       <<",\"propagations\":"<<s.propagations<<",\"learned\":"<<s.learned
       <<",\"low_lbd\":"<<s.low_lbd<<",\"trail\":"<<s.trail
       <<",\"depth\":"<<s.depth<<",\"elapsed_s\":"<<std::setprecision(9)<<s.elapsed<<"}";
  }
  void complete(const State& after,int result) {
    if(!active)return;
    const uint64_t d=after.decisions-before.decisions;
    if(d==0&&!result){active=false;return;}
    const double ms=std::max(0.0,1000*(after.elapsed-before.elapsed));
    const double useful=2.0*(after.low_lbd-before.low_lbd)
      +0.20*(after.learned-before.learned)
      +0.002*(after.propagations-before.propagations)
      +(result==10||result==20?2.0:0.0);
    // Proxy reward, not a proof of causal contribution or distance to SAT.
    const double score=std::min(8.0,useful/(1.0+ms+0.03*d));
    if(!frozen){auto& cell=cells[current_context][current_arm];++cell.samples;cell.reward_sum+=score;}
    if(log.is_open()&&events<2048){
      log<<"{\"event\":\"transition\",\"id\":"<<events
         <<",\"signature\":\""<<std::hex<<signature<<std::dec<<"\",\"context\":"
         <<current_context<<",\"action\":\""<<(current_arm?"invert_phase":"saved_phase")<<"\",\"before\":";
      emit_state(before);log<<",\"after\":";emit_state(after);
      log<<",\"duration_ms\":"<<ms<<",\"proxy_score\":"<<score
         <<",\"terminal\":"<<(result==10?"\"SAT\"":result==20?"\"UNSAT\"":result==0?"\"UNKNOWN\"":"null")<<"}\n";
    }
    ++events;active=false;
  }
  int select(const Stats& s,size_t trail,int depth,double t){
    if(!enabled)return 0;
    const State now=snapshot(s,trail,depth,t);
    if(active&&now.decisions-before.decisions>=static_cast<uint64_t>(interval))complete(now,-1);
    if(!active){
      before=now;current_context=context(now);current_arm=choose(current_context);
      if(current_arm)++flips;
      active=true;
    }
    return current_arm;
  }
  void finish(const Stats& s,size_t trail,int depth,double t,int result){
    if(!enabled)return;
    const State after=snapshot(s,trail,depth,t);
    complete(after,result);
    if(log.is_open()){
      log<<"{\"event\":\"outcome\",\"signature\":\""<<std::hex<<signature<<std::dec
         <<"\",\"status\":\""<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
         <<"\",\"sat_witness_checked_in_core\":"<<(result==10?"true":"false")
         <<",\"unsat_independently_verified\":false,\"events\":"<<events
         <<",\"flipped_blocks\":"<<flips<<",\"elapsed_s\":"<<t<<"}\n";
      log.flush();if(!log)throw std::runtime_error("memory trace write failed");
    }
    // Caller must independently validate UNSAT before retaining this state for training.
    save();
  }
};

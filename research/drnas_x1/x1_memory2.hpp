// DRNAS X1 MEMORY2: delayed multi-horizon structural feedback, 2026-11-13.
// Opt-in heuristic only: no change to CDCL deductions, DRUP proof or SAT witness.
// A prediction is a statistical proxy, NOT proof or the probability SAT exists.
#pragma once
#include <array>
#include <cstdio>
#include <deque>
#include <iomanip>
#include <limits>

struct X1Memory2 {
  static constexpr int CONTEXTS=64, ARMS=2, NH=3;
  static constexpr std::array<int,NH> horizons={16,64,256};
  static constexpr std::array<double,NH> weights={0.50,0.30,0.20};
  static constexpr size_t TRACE_LIMIT=4096;
  struct Snapshot {
    uint64_t decisions=0,conflicts=0,propagations=0,learned=0,low_lbd=0;
    size_t trail=0;
    int depth=0;
    double seconds=0;
  };
  struct Cell {
    uint64_t n=0;
    double sum=0,sumsq=0;
  };
  struct Episode {
    uint64_t id=0,prev_id=0;
    int context=0,action=0,var=0;
    std::array<int,4> previous_actions={-1,-1,-1,-1};
    double predicted0=0,predicted1=0;
    Snapshot before,after;
    double immediate=0;
    uint8_t observed_mask=0;
  };
  bool enabled=false,frozen=false,shadow=false,active=false;
  int interval=8, base=0;
  uint64_t signature=0,episodes=0,horizon_observations=0,flip_blocks=0,exploration_blocks=0;
  size_t trace_rows=0;
  int last_action=-1,previous_effect_positive=0;
  double last_immediate=0;
  std::array<int,4> recent_actions={-1,-1,-1,-1};
  std::array<std::array<std::array<Cell,NH>,ARMS>,CONTEXTS> cells{};
  std::array<std::array<Cell,NH>,ARMS> pooled{};
  std::vector<uint32_t> degree,binary_degree,positive_degree,negative_degree;
  double mean_degree=1.0;
  Episode current{};
  std::deque<Episode> pending;
  std::string load_path,save_path,log_path;
  std::ofstream log;

  static Snapshot snapshot(const Stats& s,size_t trail,int depth,double elapsed) {
    return {s.decisions,s.conflicts,s.propagations,s.learned,s.low_lbd,trail,depth,elapsed};
  }
  static double clamp(double v,double a,double b){
    return std::min(b,std::max(a,v));
  }
  static uint64_t mix(uint64_t h,uint64_t v){
    v+=0x9e3779b97f4a7c15ULL;
    v=(v^(v>>30))*0xbf58476d1ce4e5b9ULL;
    v=(v^(v>>27))*0x94d049bb133111ebULL;
    return (h^(v^(v>>31)))*1099511628211ULL;
  }
  explicit X1Memory2(const Formula& f,bool on,bool freeze,bool diagnostic,int decision_interval,
      std::string in,std::string out,std::string trace):
      enabled(on),frozen(freeze),shadow(diagnostic),interval(decision_interval),
      load_path(std::move(in)),save_path(std::move(out)),log_path(std::move(trace)) {
    if(!enabled)return;
    if(interval<4||interval>1024)throw std::runtime_error("MEMORY2 interval outside 4..1024");
    if(frozen&&!save_path.empty())throw std::runtime_error("MEMORY2 frozen state cannot save");
    if(f.n<0)throw std::runtime_error("MEMORY2 invalid variable count");
    degree.assign(f.n,0);binary_degree.assign(f.n,0);
    positive_degree.assign(f.n,0);negative_degree.assign(f.n,0);
    uint64_t literals=0,bin_clauses=0;
    std::array<uint64_t,9> sizes{};
    for(const auto& clause:f.clauses){
      ++sizes[std::min<size_t>(8,clause.size())];
      if(clause.size()==2)++bin_clauses;
      for(const int lit:clause){
        const int v=lit/2;
        ++degree[v];++literals;
        if(clause.size()==2)++binary_degree[v];
        if(lit&1)++negative_degree[v];else ++positive_degree[v];
      }
    }
    mean_degree=double(literals)/std::max(1,f.n);
    base=(2*bin_clauses>=f.clauses.size()?1:0) |
      (f.clauses.size()>4u*static_cast<size_t>(std::max(1,f.n))?2:0);
    signature=mix(1469598103934665603ULL,static_cast<uint64_t>(f.n));
    signature=mix(signature,f.clauses.size());
    for(auto value:sizes)signature=mix(signature,value);
    std::vector<uint64_t> structure;
    structure.reserve(f.n);
    for(int v=0;v<f.n;++v){
      uint64_t d=std::min<uint32_t>(4095,degree[v]);
      uint64_t b=std::min<uint32_t>(4095,binary_degree[v]);
      uint64_t p=std::min<uint32_t>(4095,positive_degree[v]);
      uint64_t n=std::min<uint32_t>(4095,negative_degree[v]);
      structure.push_back((d<<36)|(b<<24)|(std::min(p,n)<<12)|std::max(p,n));
    }
    std::sort(structure.begin(),structure.end());
    for(auto v:structure)signature=mix(signature,v);
    if(!load_path.empty())load();
    if(!log_path.empty()){
      log.open(log_path,std::ios::trunc);
      if(!log)throw std::runtime_error("MEMORY2 cannot create trace");
    }
  }
  void load(){
    std::ifstream in(load_path);
    if(!in)throw std::runtime_error("MEMORY2 cannot load state");
    std::string version;int contexts=-1,arms=-1,nh=-1;
    if(!(in>>version>>contexts>>arms>>nh)||version!="X1MEMORY2"||
      contexts!=CONTEXTS||arms!=ARMS||nh!=NH)
      throw std::runtime_error("MEMORY2 incompatible model");
    for(int c=0;c<CONTEXTS;++c)for(int a=0;a<ARMS;++a)for(int h=0;h<NH;++h){
      int x=-1,y=-1,z=-1;Cell item;
      if(!(in>>x>>y>>z>>item.n>>item.sum>>item.sumsq)||
          x!=c||y!=a||z!=h||item.n>1000000000ULL||
          !std::isfinite(item.sum)||!std::isfinite(item.sumsq)||
          std::abs(item.sum)>1e11||item.sumsq<0||item.sumsq>1e12)
        throw std::runtime_error("MEMORY2 corrupted model");
      cells[c][a][h]=item;
      auto& pool=pooled[a][h];pool.n+=item.n;pool.sum+=item.sum;pool.sumsq+=item.sumsq;
    }
    std::string extra;if(in>>extra)throw std::runtime_error("MEMORY2 trailing model data");
  }
  void save(){
    if(!enabled||frozen||save_path.empty())return;
    const std::string tmp=save_path+".tmp";
    {
      std::ofstream out(tmp,std::ios::trunc);
      if(!out)throw std::runtime_error("MEMORY2 cannot write model");
      out<<"X1MEMORY2 "<<CONTEXTS<<" "<<ARMS<<" "<<NH<<"\n"<<std::setprecision(17);
      for(int c=0;c<CONTEXTS;++c)for(int a=0;a<ARMS;++a)for(int h=0;h<NH;++h){
        const auto& v=cells[c][a][h];
        out<<c<<" "<<a<<" "<<h<<" "<<v.n<<" "<<v.sum<<" "<<v.sumsq<<"\n";
      }
      out.flush();if(!out)throw std::runtime_error("MEMORY2 model flush failed");
    }
    if(std::rename(tmp.c_str(),save_path.c_str())!=0)
      throw std::runtime_error("MEMORY2 failed atomic save");
  }
  int context(const Snapshot& s,int var)const{
    int result=base;
    if(degree[var]>=1.5*mean_degree)result|=4;
    if(2*binary_degree[var]>=degree[var]&&degree[var]>0)result|=8;
    if(s.decisions>=8&&s.conflicts*4>s.decisions)result|=16;
    if(previous_effect_positive)result|=32;
    return result;
  }
  static void add(Cell& cell,double reward){
    ++cell.n;cell.sum+=reward;cell.sumsq+=reward*reward;
  }
  double estimate_h(int c,int action,int h)const{
    const Cell& local=cells[c][action][h];
    const Cell& global=pooled[action][h];
    const double mean=global.n?global.sum/double(global.n):0.0;
    // Strong shrinkage prevents untested one-off substructures from dominating.
    return (local.sum+8.0*mean)/(double(local.n)+8.0);
  }
  double estimate(int c,int action)const{
    double val=0;for(int h=0;h<NH;++h)val+=weights[h]*estimate_h(c,action,h);
    return val;
  }
  int choose(int c,bool& exploratory)const{
    exploratory=false;
    if(shadow)return 0;
    const auto a=cells[c][0][0].n,b=cells[c][1][0].n;
    // Training may explore. Inference never explores.
    if(!frozen&&a<2){exploratory=true;return 0;}
    if(!frozen&&b<2){exploratory=true;return 1;}
    // Require evidence for BOTH arms; absent evidence means safe baseline.
    const bool sufficient=(a>=4&&b>=4) ||
      (a>=1&&b>=1&&pooled[0][0].n>=24&&pooled[1][0].n>=24);
    if(!sufficient)return 0;
    const double margin=frozen?0.12:0.08;
    return estimate(c,1)>estimate(c,0)+margin?1:0;
  }
  void state_json(const Snapshot& s){
    log<<"{\"decisions\":"<<s.decisions<<",\"conflicts\":"<<s.conflicts
       <<",\"propagations\":"<<s.propagations<<",\"learned\":"<<s.learned
       <<",\"low_lbd\":"<<s.low_lbd<<",\"trail\":"<<s.trail
       <<",\"depth\":"<<s.depth<<",\"elapsed_s\":"<<std::setprecision(9)<<s.seconds<<"}";
  }
  void trace_open(const Episode& ep,bool exploratory){
    if(!log.is_open()||trace_rows>=TRACE_LIMIT)return;
    log<<"{\"event\":\"before_action\",\"id\":"<<ep.id<<",\"prev_id\":"<<ep.prev_id
       <<",\"signature\":\""<<std::hex<<signature<<std::dec
       <<"\",\"context\":"<<ep.context<<",\"action\":\""
       <<(ep.action?"inverted_phase":"saved_phase")<<"\",\"exploration\":"
       <<(exploratory?"true":"false")<<",\"feature\":{"
       <<"\"degree\":"<<degree[ep.var]<<",\"binary_degree\":"<<binary_degree[ep.var]
       <<",\"positive_degree\":"<<positive_degree[ep.var]
       <<",\"negative_degree\":"<<negative_degree[ep.var]
       <<",\"recent_actions\":[";
    for(int i=0;i<4;++i){if(i)log<<",";log<<ep.previous_actions[i];}
    log<<"]},\"expected_utility\":["<<ep.predicted0<<","<<ep.predicted1<<"],\"state\":";
    state_json(ep.before);log<<"}\n";++trace_rows;
  }
  void close(const Snapshot& after){
    if(!active)return;
    Episode closed=current;closed.after=after;active=false;
    const double ms=std::max(0.0,1000.0*(after.seconds-closed.before.seconds));
    const double high=double(after.low_lbd-closed.before.low_lbd);
    const double prop=double(after.propagations-closed.before.propagations);
    closed.immediate=clamp((1.5*high+0.005*prop)/(1+ms),0,5);
    previous_effect_positive=closed.immediate>=0.15?1:0;
    last_immediate=closed.immediate;last_action=closed.action;
    recent_actions[closed.id%4]=closed.action;
    if(log.is_open()&&trace_rows<TRACE_LIMIT){
      log<<"{\"event\":\"after_action\",\"id\":"<<closed.id
         <<",\"context\":"<<closed.context<<",\"action\":"<<closed.action
         <<",\"immediate_proxy\":"<<closed.immediate
         <<",\"elapsed_ms\":"<<ms<<",\"state\":";
      state_json(after);log<<"}\n";++trace_rows;
    }
    pending.push_back(std::move(closed));
  }
  static double delayed_proxy(const Episode& ep,const Snapshot& now,int horizon){
    const double millis=std::max(0.0,1000.0*(now.seconds-ep.after.seconds));
    const double d=double(now.decisions-ep.after.decisions);
    const double l=double(now.low_lbd-ep.after.low_lbd);
    const double p=double(now.propagations-ep.after.propagations);
    // This measures future search signals / cost, NOT truth or causal progress.
    const double useful=1.8*l+0.003*p+0.2*std::min<double>(
      24.0,double(now.learned-ep.after.learned));
    const double future=useful/(1.0+0.2*millis+0.03*d);
    const double combined=0.15*ep.immediate+0.85*future;
    (void)horizon;
    return clamp(combined,0.0,8.0);
  }
  void observe(const Snapshot& now,bool final){
    for(auto& ep:pending){
      const uint64_t distance=now.decisions-ep.after.decisions;
      for(int h=0;h<NH;++h){
        if(ep.observed_mask&(1u<<h))continue;
        if(distance<static_cast<uint64_t>(horizons[h])){
          if(!final)continue;
          // Explicit right-censoring: DO NOT train from an unobserved horizon.
          ep.observed_mask|=static_cast<uint8_t>(1u<<h);
          if(log.is_open()&&trace_rows<TRACE_LIMIT){
            log<<"{\"event\":\"horizon\",\"id\":"<<ep.id<<",\"horizon\":"
               <<horizons[h]<<",\"observed\":false,\"censored\":true,\"decisions\":"
               <<distance<<"}\n";++trace_rows;
          }
          continue;
        }
        const double reward=delayed_proxy(ep,now,horizons[h]);
        if(!frozen){
          add(cells[ep.context][ep.action][h],reward);
          add(pooled[ep.action][h],reward);
        }
        ep.observed_mask|=static_cast<uint8_t>(1u<<h);++horizon_observations;
        if(log.is_open()&&trace_rows<TRACE_LIMIT){
          log<<"{\"event\":\"horizon\",\"id\":"<<ep.id<<",\"horizon\":"
             <<horizons[h]<<",\"observed\":true,\"censored\":false,"
             <<"\"decisions\":"<<distance<<",\"duration_ms\":"
             <<1000.0*std::max(0.0,now.seconds-ep.after.seconds)
             <<",\"reward_proxy\":"<<reward
             <<",\"predicted_utility\":"<<(ep.action?ep.predicted1:ep.predicted0)
             <<",\"context\":"<<ep.context<<",\"action\":"<<ep.action<<"}\n";
          ++trace_rows;
        }
      }
    }
    while(!pending.empty()&&pending.front().observed_mask==((1u<<NH)-1u))
      pending.pop_front();
    if(pending.size()>128)throw std::runtime_error("MEMORY2 pending horizon bound violated");
  }
  int select(const Stats& s,size_t trail,int depth,double elapsed,int variable){
    if(!enabled)return 0;
    const Snapshot now=snapshot(s,trail,depth,elapsed);
    if(active&&now.decisions-current.before.decisions>=static_cast<uint64_t>(interval))
      close(now);
    observe(now,false);
    if(!active){
      const int c=context(now,variable);
      bool exploratory=false;const int a=choose(c,exploratory);
      current={};
      current.id=episodes++;
      current.prev_id=current.id?current.id-1:0;
      current.context=c;current.action=a;current.var=variable;
      current.before=now;current.previous_actions=recent_actions;
      current.predicted0=estimate(c,0);current.predicted1=estimate(c,1);
      if(a)++flip_blocks;
      if(exploratory)++exploration_blocks;
      active=true;
      trace_open(current,exploratory);
    }
    return current.action;
  }
  void finish(const Stats& s,size_t trail,int depth,double elapsed,int outcome){
    if(!enabled)return;
    const auto now=snapshot(s,trail,depth,elapsed);
    close(now);
    observe(now,true);
    if(log.is_open()){
      log<<"{\"event\":\"outcome\",\"signature\":\""<<std::hex<<signature<<std::dec
         <<"\",\"status\":\""<<(outcome==10?"SAT":outcome==20?"UNSAT":"UNKNOWN")
         <<"\",\"episodes\":"<<episodes<<",\"horizon_observations\":"
         <<horizon_observations<<",\"flip_blocks\":"<<flip_blocks
         <<",\"exploration_blocks\":"<<exploration_blocks
         <<",\"future_data_censored\":true,"
         <<"\"unsat_independently_verified\":false,\"elapsed_s\":"<<elapsed<<"}\n";
      log.flush();if(!log)throw std::runtime_error("MEMORY2 trace flush failed");
    }
    // This is a STAGED policy. The driver that checks original CNF+proof must
    // validate the whole run before promoting the file as trusted training.
    save();
  }
};

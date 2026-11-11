// DRNAS ATLAS-MAP1: proof-safe structural shortcuts with parity substitution map.
// EXPERIMENTAL: source-paired binary equivalences; no third-party SAT backend.
// Existing ATLAS-X and DRNAS R3C core are included unchanged except library guard.
#define DRNAS_ATLASX_AS_LIBRARY
#include "drnas_atlasx.cpp"
#undef DRNAS_ATLASX_AS_LIBRARY
#include <cstdio>
#include <sstream>
#include <tuple>

namespace atlasmap {
using drnas::CNF;
using drnas::Clock;
static double seconds_since(Clock::time_point t) {
  return std::chrono::duration<double>(Clock::now()-t).count();
}
struct ParityDSU {
  std::vector<int> parent, rank, parity;
  explicit ParityDSU(int n=0) { reset(n); }
  void reset(int n) {
    parent.resize(n+1);rank.assign(n+1,0);parity.assign(n+1,0);
    for(int i=0;i<=n;++i)parent[i]=i;
  }
  // parity returned is value(x) XOR value(root).
  std::pair<int,int> find(int x) {
    if(parent[x]==x)return {x,0};
    const auto p=find(parent[x]);
    parity[x]^=p.second;parent[x]=p.first;
    return {parent[x],parity[x]};
  }
  // Certify value(x) XOR value(y) == relation.
  bool unite(int x,int y,int relation) {
    auto a=find(x),b=find(y);
    if(a.first==b.first)return (a.second^b.second)==relation;
    if(rank[a.first]<rank[b.first])std::swap(a,b);
    parent[b.first]=a.first;
    parity[b.first]=a.second^b.second^relation;
    if(rank[a.first]==rank[b.first])++rank[a.first];
    return true;
  }
};
struct Metrics {
  ParityDSU map;
  size_t binary_seen=0, certified_pairs=0, alias_edges=0, rewritten=0;
  size_t removed_clauses=0, skipped_tautologies=0, duplicate_clauses=0;
  int64_t saved_literals=0;
  double map_s=0, preprocess_s=0;
  bool committed=false, atlas_checked=false, history_skip=false;
  std::string decision="baseline", reason="none", kind="none", signature="none";
  atlasx::Metrics xm;
};
static std::string signature(const CNF& f) {
  // Coarse structure, no variable IDs or formula hashes in persistent memory.
  int binaries=0,small=0,repeated=0;
  std::map<std::vector<int>,unsigned> supports;
  const size_t limit=std::min<size_t>(f.clauses.size(),800);
  for(size_t i=0;i<limit;++i) {
    const auto& c=f.clauses[i];
    if(c.size()==2)++binaries;
    if(c.empty()||c.size()>4)continue;
    ++small;
    std::vector<int> s;for(int lit:c)s.push_back(std::abs(lit));
    std::sort(s.begin(),s.end());s.erase(std::unique(s.begin(),s.end()),s.end());
    if(++supports[s]==2)++repeated;
  }
  auto bucket=[](size_t v)->int {
    if(v<32)return 0;if(v<128)return 1;if(v<512)return 2;
    if(v<2048)return 3;return 4;
  };
  const int binary_pct=limit?100*binaries/int(limit):0;
  std::ostringstream out;
  out<<"v"<<bucket(size_t(f.vars))<<"c"<<bucket(f.clauses.size())
     <<"b"<<(binary_pct/20)<<"r"<<(repeated?repeated<4?1:2:0)
     <<"s"<<(small?1:0);
  return out.str();
}
struct History { uint64_t seen=0, probed=0, hits=0; };
using HistoryTable=std::map<std::string,History>;
static HistoryTable load_history(const std::string& path) {
  HistoryTable table;
  if(path.empty())return table;
  std::ifstream in(path);
  std::string key;uint64_t seen=0,probed=0,hits=0;
  while(in>>key>>seen>>probed>>hits) {
    if(key.size()>80||table.size()>=1024)break;
    if(hits>probed||probed>seen)continue;
    table[key]={seen,probed,hits};
  }
  return table;
}
static void store_history(const std::string& path,const HistoryTable& table) {
  if(path.empty())return;
  const std::string tmp=path+".tmp";
  std::ofstream out(tmp,std::ios::trunc);
  drnas::require(bool(out),"ATLASMAP1 cannot open temporary memory file");
  for(const auto& item:table)
    out<<item.first<<"\t"<<item.second.seen<<"\t"
       <<item.second.probed<<"\t"<<item.second.hits<<"\n";
  out.close();
  drnas::require(bool(out),"ATLASMAP1 cannot flush memory");
  drnas::require(std::rename(tmp.c_str(),path.c_str())==0,
                 "ATLASMAP1 cannot commit memory");
}
static bool relation_pair(const std::pair<int,int>& clause,
                          const std::set<std::pair<int,int>>& all) {
  return all.count({-clause.first,-clause.second})!=0;
}
static CNF shortcut(const CNF& f, Metrics& met, double cap) {
  const auto start=Clock::now();
  met.map.reset(f.vars);
  auto fallback=[&](const std::string& why)->CNF {
    met.reason=why;met.map_s=seconds_since(start);
    return f;
  };
  // Bounded scan (no unsound guesses when incomplete).
  if(f.clauses.size()>20000 || f.vars>200000)return fallback("source_size_gate");
  const double budget=std::min(0.012,std::max(0.0007,cap*0.001));
  std::set<std::pair<int,int>> binary;
  for(const auto& clause:f.clauses) {
    if(seconds_since(start)>budget)return fallback("map_index_budget");
    if(clause.size()!=2)continue;
    int a=clause[0],b=clause[1];
    if(std::abs(a)==std::abs(b))continue;
    if(std::abs(a)>std::abs(b))std::swap(a,b);
    binary.insert({a,b});
  }
  met.binary_seen=binary.size();
  if(binary.empty())return fallback("no_binary_source");
  for(const auto& clause:binary) {
    if(seconds_since(start)>budget)return fallback("map_relation_budget");
    if(!relation_pair(clause,binary))continue;
    const auto other=std::make_pair(-clause.first,-clause.second);
    if(!(clause<other))continue; // count pair once
    ++met.certified_pairs;
    const int x=std::abs(clause.first),y=std::abs(clause.second);
    // Both (a OR b) AND (!a OR !b) occur in ORIGINAL CNF.
    // Therefore value(x) XOR value(y) = 1 XOR sign(a) XOR sign(b).
    const int relation=1^(clause.first<0)^(clause.second<0);
    const int before=met.map.find(x).first==met.map.find(y).first;
    if(!met.map.unite(x,y,relation))
      return fallback("contradictory_parity_cycle_fallback");
    if(!before)++met.alias_edges;
    if(met.alias_edges>=2048)break;
  }
  if(met.alias_edges==0)return fallback("no_certified_alias");
  CNF out;out.vars=f.vars;
  std::set<std::vector<int>> unique;
  int64_t old_lits=0,new_lits=0;
  for(const auto& clause:f.clauses) {
    if(seconds_since(start)>budget)return fallback("map_rewrite_budget");
    old_lits+=int64_t(clause.size());
    std::vector<int> c;c.reserve(clause.size());
    for(int lit:clause) {
      const auto rep=met.map.find(std::abs(lit));
      const bool positive=(lit>0) ^ bool(rep.second);
      c.push_back(positive?rep.first:-rep.first);
    }
    std::sort(c.begin(),c.end(),[](int a,int b) {
      return std::abs(a)!=std::abs(b)?std::abs(a)<std::abs(b):a<b;
    });
    c.erase(std::unique(c.begin(),c.end()),c.end());
    bool taut=false;
    for(size_t j=1;j<c.size();++j)
      if(c[j]==-c[j-1]){taut=true;break;}
    if(taut){++met.skipped_tautologies;continue;}
    if(!unique.insert(c).second){++met.duplicate_clauses;continue;}
    new_lits+=int64_t(c.size());
    out.clauses.push_back(std::move(c));
  }
  met.map_s=seconds_since(start);
  const int64_t saved=old_lits-new_lits;
  if(saved<=0 || out.clauses.size()>f.clauses.size())
    return fallback("map_no_profitable_rewrite");
  met.committed=true;
  met.rewritten=f.clauses.size();
  met.saved_literals=saved;
  met.removed_clauses=f.clauses.size()-out.clauses.size();
  met.decision="commit";met.reason="source_binary_parity_verified";
  met.kind="PARITY_DSU_SHORTCUT";
  met.preprocess_s=met.map_s;
  return out;
}
static std::vector<int8_t> reconstruct(
    const drnas::NativeCDCL& solver,Metrics& met,const CNF& original) {
  auto values=solver.assignments();
  if(met.committed) {
    for(int i=1;i<=original.vars;++i) {
      const auto p=met.map.find(i);
      drnas::require(values[p.first]!=0,"unassigned representative");
      const bool truth=(values[p.first]>0)^bool(p.second);
      values[i]=truth?1:-1;
    }
  }
  return values;
}
static bool verify_original(const CNF& original,const std::vector<int8_t>& values) {
  if(values.size()!=size_t(original.vars)+1)return false;
  for(const auto& clause:original.clauses) {
    bool sat=false;
    for(int lit:clause)
      if(values[std::abs(lit)]!=0 &&
         (values[std::abs(lit)]>0)==(lit>0)){sat=true;break;}
    if(!sat)return false;
  }
  return true;
}
static CNF prepare(const CNF& f,Metrics& m,const std::string& mode,
                   double cap,const HistoryTable& history) {
  if(mode=="A"){m.reason="clean_baseline";return f;}
  if(mode=="ATLASX") {
    m.atlas_checked=true;
    auto out=atlasx::preprocess(f,m.xm,cap);
    m.kind=m.xm.kind;m.decision=m.xm.decision;m.reason=m.xm.reason;
    m.preprocess_s=m.xm.preprocess_s;m.saved_literals=m.xm.saved_literals;
    return out;
  }
  m.signature=signature(f);
  CNF out=shortcut(f,m,cap);
  if(m.committed)return out;  // Structural shortcut avoids expensive joins.
  if(mode=="MAP_LEARN") {
    const auto it=history.find(m.signature);
    if(it!=history.end() && it->second.probed>=4 &&
       it->second.hits==0 && (it->second.seen%8)!=7) {
      m.history_skip=true;m.decision="sleep";
      m.reason="learned_no_atlasx_gain_explore_1_in_8";
      m.kind="LEARNED_GATE";m.preprocess_s=m.map_s;
      return f;
    }
  }
  // No proven DSU gain: retain existing exact ATLAS-X as safe fallback.
  m.atlas_checked=true;
  out=atlasx::preprocess(f,m.xm,cap);
  m.kind=m.xm.kind;m.decision=m.xm.decision;m.reason=m.xm.reason;
  m.saved_literals=m.xm.saved_literals;
  m.preprocess_s=m.map_s+m.xm.preprocess_s;
  return out;
}
static bool holds_assignment(const CNF& f,unsigned bits) {
  for(const auto& c:f.clauses) {
    bool ok=false;
    for(int lit:c)if(bool((bits>>(std::abs(lit)-1))&1u)==(lit>0)){
      ok=true;break;
    }
    if(!ok)return false;
  }
  return true;
}
static int selftest() {
  std::mt19937 rng(20261111u);
  int passed=0,commits=0;
  for(int repeat=0;repeat<350;++repeat) {
    CNF f;f.vars=6;
    const int x=1+int(rng()%6);
    int y=1+int(rng()%6);if(x==y)y=(y%6)+1;
    const bool eq=(rng()&1u)!=0;
    // Complete original-clause support for x XOR y == 0 or == 1.
    if(eq) {f.clauses.push_back({-x,y});f.clauses.push_back({x,-y});}
    else {f.clauses.push_back({x,y});f.clauses.push_back({-x,-y});}
    for(int j=0;j<20;++j) {
      std::vector<int> c;
      const int width=1+int(rng()%4);
      for(int k=0;k<width;++k) {
        int v=1+int(rng()%6);
        c.push_back((rng()&1u)?v:-v);
      }
      f.clauses.push_back(std::move(c));
    }
    Metrics m;
    CNF g=shortcut(f,m,20);
    drnas::require(drnas::brute_sat(f)==drnas::brute_sat(g),
                   "ATLASMAP1 brute satisfiability changed");
    // Stronger than equisatisfiability: every reduced-model lift must
    // satisfy all original clauses, for all 64 truth assignments.
    if(m.committed) {
      ++commits;
      for(unsigned bits=0;bits<64;++bits) {
        if(!holds_assignment(g,bits))continue;
        unsigned reconstructed=0;
        for(int v=1;v<=6;++v) {
          const auto rep=m.map.find(v);
          const unsigned value=((bits>>(rep.first-1))&1u)^unsigned(rep.second);
          reconstructed|=value<<(v-1);
        }
        drnas::require(holds_assignment(f,reconstructed),
                       "ATLASMAP1 lifted model failed original formula");
      }
    }
    ++passed;
  }
  CNF positive;positive.vars=6;
  positive.clauses={{-1,2},{1,-2},{2},{-2,3},{4,5,6},{-4,-5,6}};
  Metrics p;CNF reduced=shortcut(positive,p,20);
  drnas::require(p.committed && p.alias_edges==1 &&
                 drnas::brute_sat(positive)==drnas::brute_sat(reduced),
                 "ATLASMAP1 certified equality positive control failed");
  CNF cycle;cycle.vars=3;cycle.clauses={
    {-1,2},{1,-2},{-2,3},{2,-3},{1,3},{-1,-3}};
  Metrics c;auto fallback=shortcut(cycle,c,20);
  drnas::require(!c.committed &&
                 c.reason=="contradictory_parity_cycle_fallback" &&
                 fallback.clauses==cycle.clauses &&
                 !drnas::brute_sat(cycle),
                 "ATLASMAP1 contradictory parity cycle safety gate failed");
  CNF partial;partial.vars=3;partial.clauses={{1,2},{-2,3}};
  Metrics m;auto rejected=shortcut(partial,m,20);
  drnas::require(!m.committed && rejected.clauses==partial.clauses,
                 "ATLASMAP1 inferred alias from incomplete pair");
  std::cout<<"ATLASMAP1_SELFTEST_PASS random_bruteforce="<<passed
           <<" random_commits="<<commits
           <<" certified_pair=1 contradictory_cycle=1 incomplete_pair=1\n";
  return 0;
}
} // namespace atlasmap

#ifndef DRNAS_ATLASMAP1_AS_LIBRARY
int main(int argc,char** argv) {
  try {
    if(argc==2 && std::string(argv[1])=="--atlasmap-selftest")
      return atlasmap::selftest();
    if((argc!=6 && argc!=8) || std::string(argv[2])!="--mode" ||
       std::string(argv[4])!="--time" ||
       (argc==8 && std::string(argv[6])!="--memory")) {
      std::cerr<<"usage: atlasmap1 FILE --mode A|ATLASX|MAP1|MAP_LEARN --time SECONDS [--memory path]\n";
      return 2;
    }
    const std::string mode=argv[3], memory=argc==8?argv[7]:"";
    drnas::require(mode=="A"||mode=="ATLASX"||mode=="MAP1"||mode=="MAP_LEARN",
                   "invalid ATLASMAP1 arm");
    const double cap=std::stod(argv[5]);
    drnas::require(std::isfinite(cap)&&cap>0&&cap<=3600,"invalid cap");
    const auto start=drnas::Clock::now();
    const drnas::CNF original=drnas::read_dimacs(argv[1]);
    const auto history=(mode=="MAP_LEARN")?atlasmap::load_history(memory):
                                               atlasmap::HistoryTable{};
    atlasmap::Metrics m;
    const drnas::CNF work=atlasmap::prepare(original,m,mode,cap,history);
    drnas::NativeCDCL solver(work.vars);solver.add_cnf(work);
    const double before=atlasmap::seconds_since(start);
    const int status=(before<cap)?solver.solve(cap-before):0;
    std::vector<int8_t> model;
    if(status==10) {
      model=atlasmap::reconstruct(solver,m,original);
      drnas::require(atlasmap::verify_original(original,model),
                     "reconstructed SAT witness failed original CNF");
    }
    if(mode=="MAP_LEARN" && !memory.empty()) {
      auto next=history;
      auto& h=next[m.signature];
      ++h.seen;
      if(m.atlas_checked) {
        ++h.probed;
        if(m.xm.decision=="commit")++h.hits;
      }
      atlasmap::store_history(memory,next);
    }
    const double e2e=atlasmap::seconds_since(start);
    const auto& s=solver.statistics();
    std::cout<<std::fixed<<std::setprecision(8)
       <<"ATLASMAP1_TRIAL arm="<<mode
       <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
       <<" e2e_s="<<e2e<<" preprocess_s="<<m.preprocess_s
       <<" map_s="<<m.map_s<<" original_clauses="<<original.clauses.size()
       <<" final_clauses="<<work.clauses.size()
       <<" binary_seen="<<m.binary_seen<<" source_pairs="<<m.certified_pairs
       <<" alias_edges="<<m.alias_edges<<" saved_literals="<<m.saved_literals
       <<" removed_clauses="<<m.removed_clauses
       <<" duplicate_clauses="<<m.duplicate_clauses
       <<" atlas_checked="<<int(m.atlas_checked)
       <<" l2_pairs="<<m.xm.l2_pairs
       <<" l2_expansions="<<m.xm.l2_expansions
       <<" memory_skip="<<int(m.history_skip)
       <<" signature="<<m.signature<<" kind="<<m.kind
       <<" decision="<<m.decision<<" reason="<<m.reason
       <<" conflicts="<<s.conflicts<<" decisions="<<s.decisions
       <<" propagations="<<s.propagations<<" learned="<<s.learned_clauses
       <<" SAT_original_verified="<<int(status==10)
       <<" UNSAT_independent_LRAT=0 oneCPU=1\n";
    if(status==10) {
      std::cout<<"s SATISFIABLE\nv ";
      for(int v=1;v<=original.vars;++v)
        std::cout<<(model[size_t(v)]<0?-v:v)<<" ";
      std::cout<<"0\n";
    } else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
    return status==10?10:status==20?20:0;
  } catch(const std::exception& e) {
    std::cerr<<"ATLASMAP1_ERROR "<<e.what()<<"\n";return 2;
  }
}

#endif // DRNAS_ATLASMAP1_AS_LIBRARY

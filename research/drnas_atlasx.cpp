// DRNAS ATLAS-X: compressed local relations and demand-only 5/6-variable joins.
// Experimental frontend for the independent DRNAS R3C CDCL core; no stable changes.
#define main drnas_atlas1_embedded_main
#include "drnas_atlas1.cpp"
#undef main
#include <numeric>

namespace atlasx {
using drnas::CNF;
using drnas::Clock;
struct Module {
  std::vector<int> vars, ids;
  uint16_t mask=0;                  // 2^(2^k) compact truth signature, k<=4
  int literals=0;
};
struct Candidate {
  std::vector<int> ids, vars;
  std::vector<std::vector<int>> replacement;
  int saved=0, npn=-1;
  std::string kind="none";
};
struct Metrics {
  size_t l0_modules=0, mask_bytes=0, l1_checks=0, l2_pairs=0;
  size_t l2_implications=0, l2_expansions=0, l2_skipped=0;
  int saved_literals=0, removed=0, added=0, npn=-1;
  double preprocess_s=0;
  std::string decision="sleep",reason="no_benefit",kind="none";
};
static uint64_t full(int k) {
  return k==6 ? ~uint64_t(0) : (uint64_t(1)<<(1u<<k))-1;
}
static int lit_count(const std::vector<std::vector<int>>& cs) {
  int n=0; for(const auto& c:cs)n+=int(c.size()); return n;
}
static uint16_t local_mask(const CNF& f,const Module& m) {
  uint32_t allowed=0;
  for(int bits=0;bits<(1<<m.vars.size());++bits) {
    bool sat=true;
    for(int id:m.ids)if(!arl1::clause_holds(f.clauses[id],m.vars,bits)){sat=false;break;}
    if(sat)allowed|=(1u<<bits);
  }
  return uint16_t(allowed);
}
static uint64_t lift(const Module& m,const std::vector<int>& common) {
  uint64_t result=0;
  for(int bits=0;bits<(1<<common.size());++bits) {
    unsigned sub=0;
    for(size_t j=0;j<m.vars.size();++j) {
      auto p=std::lower_bound(common.begin(),common.end(),m.vars[j]);
      drnas::require(p!=common.end() && *p==m.vars[j],"ATLASX projection mismatch");
      sub|=((bits>>int(p-common.begin()))&1u)<<j;
    }
    if((m.mask>>sub)&1u)result|=uint64_t(1)<<bits;
  }
  return result;
}
// Only called after a strict opportunity/budget gate. No CNF is stored for
// larger relations. Materialize exact implicates only when the attempt can pay.
static std::vector<std::vector<int>> expand_exact(
    const std::vector<int>& vars, uint64_t truth) {
  const int k=int(vars.size()),states=1<<k;
  drnas::require(k==5||k==6,"ATLASX extended support outside bound");
  uint64_t uncovered=full(k)&~truth;
  if(!uncovered)return {};
  if(!truth)return {{}};
  struct Imp {int code,width;uint64_t cover;};
  std::vector<Imp> implicates;
  int codes=1;for(int i=0;i<k;++i)codes*=3;
  for(int code=1;code<codes;++code) {
    int t=code,width=0;
    std::array<int,6> digits{};
    for(int i=0;i<k;++i){digits[i]=t%3;t/=3;if(digits[i])++width;}
    uint64_t falsifies=0;
    for(int bits=0;bits<states;++bits) {
      bool clause_sat=false;
      for(int i=0;i<k;++i)if(digits[i] &&
          ((bits>>i)&1)==(digits[i]==1)){clause_sat=true;break;}
      if(!clause_sat)falsifies|=uint64_t(1)<<bits;
    }
    if(falsifies && !(falsifies&truth))
      implicates.push_back({code,width,falsifies});
  }
  std::vector<std::vector<int>> result;
  while(uncovered) {
    const Imp* best=nullptr;int gain_best=0;
    for(const auto& imp:implicates){
      int gain=__builtin_popcountll(imp.cover&uncovered);
      if(gain>gain_best || (gain==gain_best && gain>0 &&
          (!best || imp.width<best->width ||
           (imp.width==best->width && imp.code<best->code)))) {
        best=&imp;gain_best=gain;
      }
    }
    drnas::require(best!=nullptr,"ATLASX covering failed");
    std::vector<int> c;
    int code=best->code;
    for(int i=0;i<k;++i) {
      int digit=code%3;code/=3;
      if(digit)c.push_back(digit==1?vars[i]:-vars[i]);
    }
    result.push_back(std::move(c));
    uncovered&=~best->cover;
  }
  return result;
}
static bool verify(const CNF& f,const Candidate& c) {
  if(c.ids.empty()||c.vars.size()>6)return false;
  for(int bits=0;bits<(1<<c.vars.size());++bits) {
    bool old=true,now=true;
    for(int id:c.ids)if(!arl1::clause_holds(f.clauses[id],c.vars,bits)){
      old=false;break;
    }
    for(const auto& clause:c.replacement)
      if(!arl1::clause_holds(clause,c.vars,bits)){now=false;break;}
    if(old!=now)return false;
  }
  return true;
}
static void consider(const CNF& f,Candidate& best,Candidate&& c,
                     int old_literals) {
  if(c.ids.empty()||c.replacement.size()>c.ids.size())return;
  const int saved=old_literals-lit_count(c.replacement);
  if(saved<=0)return;
  c.saved=saved;
  if(c.saved<best.saved)return;
  if(c.saved==best.saved && c.ids.size()<=best.ids.size())return;
  drnas::require(verify(f,c),"ATLASX local equivalence failed");
  best=std::move(c);
}
static CNF preprocess(const CNF& original,Metrics& met,double cap) {
  const auto start=Clock::now();
  auto seconds=[&] {return std::chrono::duration<double>(Clock::now()-start).count();};
  const double budget=std::min(0.005,cap*0.0005);
  CNF out=original;
  std::map<std::vector<int>,std::vector<int>> by_support;
  const size_t limit=std::min<size_t>(original.clauses.size(),900);
  for(size_t id=0;id<limit;++id) {
    const auto& clause=original.clauses[id];
    if(clause.empty()||clause.size()>4)continue;
    std::vector<int> support;
    for(int l:clause)support.push_back(std::abs(l));
    std::sort(support.begin(),support.end());
    support.erase(std::unique(support.begin(),support.end()),support.end());
    if(support.size()==clause.size() && support.size()<=4)
      by_support[support].push_back(int(id));
  }
  std::vector<Module> modules;modules.reserve(std::min<size_t>(by_support.size(),200));
  for(const auto& item:by_support) {
    if(seconds()>budget || modules.size()>=160)break;
    Module m;m.vars=item.first;m.ids=item.second;
    for(int id:m.ids)m.literals+=int(original.clauses[id].size());
    m.mask=local_mask(original,m);
    modules.push_back(std::move(m));
  }
  met.l0_modules=modules.size();
  met.mask_bytes=2*modules.size();
  Candidate best;
  // L1: instant lookup of the precomputed exact NPN-CNF recipe, no expansion.
  for(const auto& m:modules) {
    if(seconds()>budget)break;
    const int k=int(m.vars.size());
    if(k<2||m.ids.size()<2)continue;
    ++met.l1_checks;
    const auto recipe=arl1::atlas_recipe(k,m.mask,m.vars);
    Candidate c;c.ids=m.ids;c.vars=m.vars;c.replacement=recipe.clauses;
    c.npn=recipe.cls;c.kind="L1_NPN";
    consider(original,best,std::move(c),m.literals);
  }
  // L2: lazy join of overlapping *distinct* modules. No >=5-var CNF
  // materialization when implication can be checked directly from masks.
  // The join is attempted only under explicit caps and with real savings.
  bool limit_hit=false;
  for(size_t i=0;i<modules.size() && !limit_hit;++i) {
    for(size_t j=i+1;j<modules.size();++j) {
      if(seconds()>budget || met.l2_pairs>=400){limit_hit=true;break;}
      const auto& a=modules[i];const auto& b=modules[j];
      std::vector<int> common;
      std::set_union(a.vars.begin(),a.vars.end(),b.vars.begin(),b.vars.end(),
                     std::back_inserter(common));
      const int k=int(common.size());
      if(k<5||k>6||a.vars.size()+b.vars.size()==common.size())continue;
      ++met.l2_pairs;
      const uint64_t am=lift(a,common), bm=lift(b,common);
      // Removing an implied module is exact and needs no decompression.
      if(!(am&~bm)) {
        ++met.l2_implications;
        Candidate c;c.ids=a.ids;c.ids.insert(c.ids.end(),b.ids.begin(),b.ids.end());
        c.vars=common;c.kind="L2_MASK_SUBSUMPTION";
        for(int id:a.ids)c.replacement.push_back(original.clauses[id]);
        consider(original,best,std::move(c),a.literals+b.literals);
      }
      if(!(bm&~am)) {
        ++met.l2_implications;
        Candidate c;c.ids=a.ids;c.ids.insert(c.ids.end(),b.ids.begin(),b.ids.end());
        c.vars=common;c.kind="L2_MASK_SUBSUMPTION";
        for(int id:b.ids)c.replacement.push_back(original.clauses[id]);
        consider(original,best,std::move(c),a.literals+b.literals);
      }
      if(!(am&~bm)||!(bm&~am))continue;
      // L2 extended recipe, only when the cheap mask join shows an
      // opportunity and original clause materialization is expensive.
      const int old_lits=a.literals+b.literals;
      if(k!=5||a.ids.size()+b.ids.size()<4||
         old_lits<14||met.l2_expansions>=6) {
        ++met.l2_skipped;continue;
      }
      if(seconds()>budget){limit_hit=true;break;}
      ++met.l2_expansions;
      Candidate c;c.ids=a.ids;c.ids.insert(c.ids.end(),b.ids.begin(),b.ids.end());
      c.vars=common;c.kind="L2_LAZY_EXPAND";
      c.replacement=expand_exact(common,am&bm);
      consider(original,best,std::move(c),old_lits);
    }
  }
  if(!best.ids.empty()) {
    // Source-level exhaustiveness: only selected original clauses are
    // replaced. All others, including clauses sharing any variables, survive.
    drnas::require(verify(original,best),"ATLASX precommit verification failed");
    std::vector<uint8_t> drop(original.clauses.size(),0);
    for(int id:best.ids)drop[size_t(id)]=1;
    out.clauses.clear();
    out.clauses.reserve(original.clauses.size()-best.ids.size()+best.replacement.size());
    for(size_t i=0;i<original.clauses.size();++i)
      if(!drop[i])out.clauses.push_back(original.clauses[i]);
    for(const auto& clause:best.replacement)out.clauses.push_back(clause);
    met.saved_literals=best.saved;
    met.removed=int(best.ids.size());met.added=int(best.replacement.size());
    met.npn=best.npn;met.kind=best.kind;
    met.decision="commit";met.reason="exact_truth_table_equivalence";
  } else {
    met.decision="sleep";
    met.reason=limit_hit?"budget_exhausted_no_gain":"no_profitable_relation";
  }
  met.preprocess_s=seconds();
  return out;
}
static int selftest() {
  std::mt19937 rng(20261111u);
  int commits=0;
  for(int run=0;run<300;++run) {
    CNF f;f.vars=16;
    for(int c=0;c<12;++c) {
      std::vector<int> pool={1,2,3,4,5,6};
      std::shuffle(pool.begin(),pool.end(),rng);
      const int width=1+int(rng()%4);
      std::vector<int> clause;
      for(int j=0;j<width;++j)
        clause.push_back((rng()%2)?pool[j]:-pool[j]);
      f.clauses.push_back(std::move(clause));
    }
    Metrics m;
    const CNF updated=preprocess(f,m,10);
    if(m.decision=="commit")++commits;
    for(int bits=0;bits<64;++bits) {
      auto eval=[&](const CNF& x) {
        for(const auto& clause:x.clauses) {
          bool sat=false;
          for(int l:clause)if(bool(bits&(1<<(std::abs(l)-1)))==(l>0)){
            sat=true;break;
          }
          if(!sat)return false;
        }
        return true;
      };
      drnas::require(eval(f)==eval(updated),"ATLASX randomized truth mismatch");
    }
  }
  // Deterministic L2 redundancy positive control, 5-variable union.
  CNF f;f.vars=16;
  f.clauses={{1,2,3},{1,2,-3},{1,2,4,5},{1,2,-4,5}};
  Metrics m;CNF g=preprocess(f,m,10);
  drnas::require(m.decision=="commit" && m.kind=="L2_MASK_SUBSUMPTION",
                 "ATLASX L2 redundancy control failed");
  drnas::require(g.clauses.size()==2,"ATLASX L2 deletion count");
  std::cout<<"ATLASX_SELFTEST_PASS random=300 L2_redundancy=1 random_commits="
           <<commits<<"\n";
  return 0;
}
}
int main(int argc,char** argv) {
  try {
    if(argc==2 && std::string(argv[1])=="--atlasx-selftest")
      return atlasx::selftest();
    if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
      std::cerr<<"usage: atlasx FILE --mode A|ATLAS1|ATLASX --time SECONDS\n";return 2;
    }
    const std::string arm=argv[3];
    drnas::require(arm=="A"||arm=="ATLAS1"||arm=="ATLASX","invalid mode");
    const double cap=std::stod(argv[5]);
    drnas::require(cap>0 && cap<=3600,"invalid time cap");
    const auto start=drnas::Clock::now();
    const CNF original=drnas::read_dimacs(argv[1]);
    atlasx::Metrics xm;
    arl1::Result am;
    CNF working=original;
    if(arm=="ATLAS1"){
      working=arl1::first_look(original,am,cap,start);
      xm.decision=am.decision;xm.reason=am.reason;
      xm.saved_literals=am.saved_literals;xm.kind="ATLAS1";
      xm.removed=am.pivots;xm.added=am.accepted;xm.npn=am.npn_class;
      xm.preprocess_s=am.scan_s+am.probe_s;
    } else if(arm=="ATLASX")working=atlasx::preprocess(original,xm,cap);
    else {xm.decision="baseline";xm.reason="no_preprocessing";}
    drnas::NativeCDCL solver(working.vars);
    solver.add_cnf(working);
    const double elapsed=std::chrono::duration<double>(drnas::Clock::now()-start).count();
    const int status=elapsed<cap?solver.solve(cap-elapsed):0;
    if(status==10)drnas::require(solver.verify_original(original),"original SAT witness invalid");
    const double e2e=std::chrono::duration<double>(drnas::Clock::now()-start).count();
    const auto& s=solver.statistics();
    std::cout<<std::fixed<<std::setprecision(8)
      <<"ATLASX_TRIAL arm="<<arm
      <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
      <<" e2e_s="<<e2e<<" preprocess_s="<<xm.preprocess_s
      <<" original_clauses="<<original.clauses.size()
      <<" final_clauses="<<working.clauses.size()
      <<" l0_modules="<<xm.l0_modules<<" compressed_bytes="<<xm.mask_bytes
      <<" l1_checks="<<xm.l1_checks<<" l2_pairs="<<xm.l2_pairs
      <<" l2_implications="<<xm.l2_implications
      <<" l2_expansions="<<xm.l2_expansions
      <<" l2_skipped="<<xm.l2_skipped
      <<" saved_literals="<<xm.saved_literals
      <<" removed="<<xm.removed<<" added="<<xm.added
      <<" npn_class="<<xm.npn<<" kind="<<xm.kind
      <<" decision="<<xm.decision<<" reason="<<xm.reason
      <<" conflicts="<<s.conflicts<<" decisions="<<s.decisions
      <<" propagations="<<s.propagations<<" learned="<<s.learned_clauses
      <<" SAT_original_verified="<<int(status==10)
      <<" UNSAT_independent_LRAT=0 oneCPU=1\n";
    if(status==10){
      std::cout<<"s SATISFIABLE\nv ";
      for(int v=1;v<=original.vars;++v)
        std::cout<<(solver.assignments()[v]<0?-v:v)<<" ";
      std::cout<<"0\n";
    } else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
    return status==10?10:status==20?20:0;
  } catch(const std::exception& e) {
    std::cerr<<"ATLASX_ERROR "<<e.what()<<"\n";return 2;
  }
}

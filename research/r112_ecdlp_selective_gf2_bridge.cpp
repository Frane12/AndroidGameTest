// R112: ECDLP-focused bounded, proof-carrying GF(2) -> CDCL experiment.
//
// Extract exact source XOR2..6 from immutable DIMACS. Derive short GF(2)
// relations by XOR of two independently rechecked source equations. When CDCL
// assigns all or all but one row variable, the IPASIR-UP ExternalPropagator
// communicates an entailed CNF clause back to CaDiCaL during search.
// CaDiCaL's assignments/backtracks are fed into the GF(2) row evaluator.
// This does NOT advertise full Gaussian re-elimination under assumptions.
// Abort on malformed inputs; cap rows, watched variables and emitted lemmas.

#define main r107c_embedded_main
#include "r107c_native_xor_finder.cpp"
#undef main
#include "cadical.hpp"
#include <atomic>
#include <map>
#include <chrono>
#include <memory>
#include <numeric>
#include <unordered_map>

using CaDiCaL::Solver;
struct XorEquation {
  V vars;int rhs=0;std::pair<int,int> source{-1,-1};
};

[[maybe_unused]] [[maybe_unused]] static int intersection_count(const V& a,const V& b){
  int c=0;size_t i=0,j=0;
  while(i<a.size()&&j<b.size()){
    if(a[i]==b[j]){++c;++i;++j;}
    else if(a[i]<b[j])++i;
    else ++j;
  }
  return c;
}
static std::vector<XorEquation> certified_relations(
  const fs::path& source, const Group& groups,
  int& source_count,int& accepted, std::string& gate) {
  std::vector<XorEquation> originals;
  for(const auto& [vars,mask]:groups){
    for(int rhs=0;rhs<=1;++rhs){
      auto signature=parity_mask(int(vars.size()),rhs);
      if((mask&signature)==signature)
        originals.push_back({vars,rhs,{-1,-1}});
    }
  }
  source_count=int(originals.size());
  accepted=0;
  if(originals.size()<2){gate="too_few_original_rows";return {};}
  // R112 controlled test: do not discard all dense ECDLP input XORs.
  // Explore only proof-certified pairs with two shared variables. Source count
  // is capped to bound memory/time, while every chosen row is independently
  // rechecked against the immutable CNF (same proof checks as R111).
  if(originals.size()>30000){gate="source_budget_skip";return {};}
  std::vector<XorEquation> selected;
  std::set<std::pair<V,int>> existing;
  for(const auto& row:originals)existing.insert({row.vars,row.rhs});
  std::map<std::pair<int,int>,std::vector<int>> by_pair;
  for(size_t i=0;i<originals.size();++i){
    const V& v=originals[i].vars;
    for(size_t x=0;x<v.size();++x){
      for(size_t y=x+1;y<v.size();++y){
        auto& bucket=by_pair[{v[x],v[y]}];
        if(bucket.size()<16)bucket.push_back(int(i));
      }
    }
  }
  std::set<std::pair<int,int>> visited;
  for(const auto& kv:by_pair){
    const auto& ids=kv.second;
    for(size_t x=0;x<ids.size()&&selected.size()<128;++x){
      for(size_t y=x+1;y<ids.size()&&selected.size()<128;++y){
        const int ai=ids[x],bi=ids[y];
        if(!visited.insert({ai,bi}).second)continue;
        const auto& row_a=originals[size_t(ai)];
        const auto& row_b=originals[size_t(bi)];
        V vars=xor_vectors(row_a.vars,row_b.vars);
        int rhs=row_a.rhs^row_b.rhs;
        if(vars.size()<2||vars.size()>8)continue;
        if(!existing.insert({vars,rhs}).second)continue;
        selected.push_back({std::move(vars),rhs,{ai,bi}});
      }
    }
    if(selected.size()>=128)break;
  }
  if(selected.empty()){gate="no_short_GF2_pair";return {};}
  // Hard cap observed variables: freezing too many variables changes CDCL
  // behavior and would make comparison against clean CaDiCaL unfair.
  std::set<int> observed;
  std::vector<XorEquation> bounded;
  for(const auto& row:selected){
    std::set<int> next=observed;
    next.insert(row.vars.begin(),row.vars.end());
    if(next.size()>96)continue;
    bounded.push_back(row);
    observed=std::move(next);
    if(bounded.size()>=96)break;
  }
  if(bounded.empty()){gate="observed_variable_budget_skip";return {};}
  // Independently replay all source 2..6 parity signatures that justify
  // each selected GF(2) row; never trust the extraction's initial bitsets.
  std::set<V> needed;
  for(const auto& row:bounded){
    needed.insert(originals[row.source.first].vars);
    needed.insert(originals[row.source.second].vars);
    const auto& a=originals[row.source.first],&b=originals[row.source.second];
    require(xor_vectors(a.vars,b.vars)==row.vars && (a.rhs^b.rhs)==row.rhs,
            "R111 GF2 ancestry invalid");
  }
  Group independent;
  parse(source,[&](const V& clause){add_group(independent,clause,&needed);});
  for(const auto& row:bounded){
    for(int index:{row.source.first,row.source.second}){
      const auto& original=originals[index];
      const auto itr=independent.find(original.vars);
      require(itr!=independent.end(),"R111 missing source XOR signature");
      const auto mask=parity_mask(int(original.vars.size()),original.rhs);
      require((itr->second&mask)==mask,"R111 invalid source GF2 witness");
    }
  }
  accepted=int(bounded.size());
  gate="R112_selective_certified_GF2_bridge";
  return bounded;
}

class GF2Bridge final: public CaDiCaL::ExternalPropagator{
public:
  std::vector<XorEquation> rows;
  std::vector<int8_t> vals;
  std::vector<std::pair<int,int>> trail;
  std::set<V> emitted;
  V pending;
  size_t pending_pos=0;
  int level=0;
  int notifications=0,backtracks=0,scans=0,lemmas=0,conflicts=0,units=0;
  bool dirty=true;

  GF2Bridge(std::vector<XorEquation> rules,int n):
    rows(std::move(rules)),vals(n+1,-1) {
    is_lazy=false;
    are_reasons_forgettable=false;
  }
  void notify_assignment(const std::vector<int>& lits) override {
    for(int lit:lits){
      int v=std::abs(lit);
      require(v>0&&size_t(v)<vals.size(),"R111 observed variable outside CNF");
      int8_t sign=lit>0?1:0;
      if(vals[v]==sign)continue;
      require(vals[v]<0,"R111 contradictory assignment notification");
      vals[v]=sign;
      trail.emplace_back(v,level);
      ++notifications;
    }
    dirty=true;
  }
  void notify_new_decision_level() override {++level;}
  void notify_backtrack(size_t to) override {
    require(to<=size_t(level),"R111 invalid backtrack level");
    while(!trail.empty()&&size_t(trail.back().second)>to){
      vals[trail.back().first]=-1;
      trail.pop_back();
    }
    level=int(to);
    ++backtracks;
    dirty=true;
  }
  bool cb_check_found_model(const std::vector<int>& model) override {
    std::vector<int8_t> assignment(vals.size(),-1);
    for(int lit:model){
      if(lit==0)continue;
      int v=std::abs(lit);
      if(size_t(v)<assignment.size())assignment[v]=lit>0?1:0;
    }
    for(const auto& row:rows){
      int parity=0;
      bool full=true;
      V clause;
      for(int v:row.vars){
        if(assignment[v]<0){full=false;break;}
        parity^=assignment[v];
        clause.push_back(assignment[v]?-v:v);
      }
      if(full&&parity!=row.rhs){
        pending=std::move(clause);
        pending_pos=0;
        dirty=true;
        return false;
      }
    }
    return true;
  }
  int cb_propagate() override {return 0;} // Clauses below drive CDCL propagation.
  bool cb_has_external_clause(bool& forgettable) override {
    forgettable=false;
    if(!pending.empty())return true;
    if(!dirty||lemmas>=256)return false;
    dirty=false;
    ++scans;
    for(const auto& row:rows){
      int parity=0,unknown=0,unassigned=0;
      V clause;clause.reserve(row.vars.size());
      for(int var:row.vars){
        if(vals[var]<0){++unknown;unassigned=var;}
        else{
          parity^=vals[var];
          clause.push_back(vals[var]?-var:var);
        }
        if(unknown>1)break;
      }
      if(unknown>1)continue;
      const bool conflicting=(unknown==0&&parity!=row.rhs);
      if(unknown==0&&!conflicting)continue;
      if(unknown==1){
        const int value=parity^row.rhs;
        clause.push_back(value?unassigned:-unassigned);
      }
      if(!emitted.insert(clause).second)continue;
      pending=std::move(clause);
      pending_pos=0;
      ++lemmas;
      if(conflicting)++conflicts;
      else ++units;
      return true;
    }
    return false;
  }
  int cb_add_external_clause_lit() override {
    if(pending_pos<pending.size())return pending[pending_pos++];
    pending.clear();pending_pos=0;dirty=true;
    return 0;
  }
};

struct Dimacs{
  Parsed head;
  std::vector<V> clauses;
  Group groups;
};
static Dimacs load_input(const fs::path& source){
  Dimacs d;
  d.head=parse(source,[&](const V& c){
    d.clauses.push_back(c);
    add_group(d.groups,c);
  });
  return d;
}
static void check_model(Solver& solver,const Dimacs& data){
  for(const V& clause:data.clauses){
    bool satisfies=false;
    for(int lit:clause){
      int value=solver.val(std::abs(lit));
      require(value!=0,"R111 model missing assigned variable");
      if((value>0)==(lit>0)){satisfies=true;break;}
    }
    require(satisfies,"R111 SAT output fails original source clause");
  }
}

int main(int argc,char**argv){
  try{
    require(argc==3,"usage: r111_solver clean|bridge DIMACS.cnf");
    std::string mode=argv[1];
    require(mode=="clean"||mode=="bridge","R111 invalid mode");
    fs::path source=argv[2];
    auto start=std::chrono::steady_clock::now();
    Dimacs d=load_input(source);
    require(d.head.vars<=500000,"R111 excessive variable count");
    int source_rows=0,derived_rows=0;
    std::string gate=(mode=="clean"?"clean_CaDiCaL":"not_selected");
    std::vector<XorEquation> bridge_rows;
    if(mode=="bridge")
      bridge_rows=certified_relations(source,d.groups,source_rows,derived_rows,gate);
    Solver solver;
    solver.set("quiet",1);
    for(const auto& clause:d.clauses){
      for(int lit:clause)solver.add(lit);
      solver.add(0);
    }
    std::unique_ptr<GF2Bridge> bridge;
    if(!bridge_rows.empty()){
      bridge.reset(new GF2Bridge(std::move(bridge_rows),d.head.vars));
      solver.connect_external_propagator(bridge.get());
      std::set<int> watch;
      for(const auto& row:bridge->rows)
        watch.insert(row.vars.begin(),row.vars.end());
      for(int v:watch)solver.add_observed_var(v);
    }
    int code=solver.solve();
    if(code==10)check_model(solver,d);
    if(code==10){
      std::cout<<"s SATISFIABLE\n";
      for(int v=1;v<=d.head.vars;v+=16){
        std::cout<<"v ";
        for(int w=v;w<std::min(v+16,d.head.vars+1);++w){
          int sign=solver.val(w);
          std::cout<<(sign>0?w:-w)<<" ";
        }
        std::cout<<"0\n";
      }
    }else if(code==20)std::cout<<"s UNSATISFIABLE\n";
    else std::cout<<"s UNKNOWN\n";
    double t=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    std::cerr<<"R111_AUDIT mode="<<mode<<" gate="<<gate
             <<" source_xor="<<source_rows
             <<" derived_GF2_rows="<<derived_rows
             <<" external_lemmas="<<(bridge?bridge->lemmas:0)
             <<" external_implications="<<(bridge?bridge->units:0)
             <<" external_conflicts="<<(bridge?bridge->conflicts:0)
             <<" external_assignments="<<(bridge?bridge->notifications:0)
             <<" external_backtracks="<<(bridge?bridge->backtracks:0)
             <<" external_scans="<<(bridge?bridge->scans:0)
             <<" elapsed_s="<<t<<"\n";
    // Detach before destruction of propagator, to avoid stale callback pointer.
    if(bridge)solver.disconnect_external_propagator();
    return code;
  }catch(const std::exception& e){
    std::cerr<<"R111_FAIL_CLOSED "<<e.what()<<"\n";
    return 2;
  }
}

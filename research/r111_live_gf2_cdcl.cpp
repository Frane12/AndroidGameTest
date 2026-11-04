// R111 - In-process certified GF(2) <-> CaDiCaL IPASIR-UP experiment.
//
// CDCL decision/assignment/backtrack notifications update the GF(2) side.
// The GF(2) side substitutes these values, eliminates unknown variables and
// returns reason-carrying unit propagations or conflict clauses.
// Each explanation is a parity consequence of independently verified,
// complete original CNF 2..6-XOR signatures. Budgets fail open to plain CDCL.
//
// This is an experimental, bounded implementation, not a general-purpose
// GPU solver, XOR mining system or official SAT Competition entry.
#define main r107c_standalone_unused_main
#include "r107c_native_xor_finder.cpp"
#undef main
#include "cadical.hpp"
#include <array>
#include <deque>
#include <iomanip>
#include <memory>

struct ActiveRow {
  V unknown;
  V why;
  int rhs = 0;
};
struct Signal {
  int lit = 0;
  V clause;
};
struct GF2Report {
  std::vector<Signal> units;
  V conflict;
  bool contradictory = false;
  long operations = 0;
  long pivots = 0;
};
static V symdiff(const V& a,const V& b) {
  V out;
  out.reserve(a.size()+b.size());
  std::set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),
                               std::back_inserter(out));
  return out;
}
static void insert_unique(V& v,int x) {
  auto p=std::lower_bound(v.begin(),v.end(),x);
  if(p==v.end()||*p!=x)v.insert(p,x);
}
static GF2Report derive(const std::vector<Row>& source,
                        const std::vector<signed char>& assigned,
                        long budget) {
  GF2Report result;
  std::map<int,ActiveRow> pivots;
  std::set<int> emitted_vars;
  for(const Row& source_row:source) {
    ActiveRow row;
    row.rhs=source_row.rhs;
    for(int var:source_row.vars) {
      if(var<=0 || size_t(var)>=assigned.size())
        throw std::runtime_error("R111_GF2_BAD_VARIABLE");
      if(assigned[var]==0) row.unknown.push_back(var);
      else {
        row.why.push_back(var);
        if(assigned[var]>0)row.rhs^=1;
      }
    }
    while(!row.unknown.empty()) {
      const int pivot=row.unknown.front();
      auto it=pivots.find(pivot);
      if(it==pivots.end()) {
        pivots.emplace(pivot,std::move(row));
        break;
      }
      auto& previous=it->second;
      result.operations+=long(row.unknown.size()+previous.unknown.size()+
                              row.why.size()+previous.why.size());
      if(result.operations>budget)
        throw std::runtime_error("R111_GF2_OPERATION_BUDGET");
      row.unknown=symdiff(row.unknown,previous.unknown);
      row.why=symdiff(row.why,previous.why);
      row.rhs^=previous.rhs;
    }
    // If the pivot was stored, the moved-from row is empty but not a
    // contradiction. Check only rows that were actually reduced to zero.
    if(row.unknown.empty() && !row.why.empty() && row.rhs) {
      bool moved=false;
      // A stored pivot is in pivots even after move; however std::move
      // empties the input vector. Track insertion explicitly instead.
      (void)moved;
    }
  }
  result.pivots=pivots.size();
  // A pivot system in row-echelon form may encode a unit even when it has
  // not reduced another row to zero.
  for(const auto& [lead,row]:pivots) {
    (void)lead;
    if(row.unknown.size()!=1)continue;
    const int var=row.unknown[0];
    if(emitted_vars.count(var))continue;
    emitted_vars.insert(var);
    Signal s;
    s.lit=row.rhs ? var:-var;
    for(int why:row.why)
      s.clause.push_back(assigned[why]>0 ? -why : why);
    s.clause.push_back(s.lit);
    std::sort(s.clause.begin(),s.clause.end(),
       [](int a,int b){return std::abs(a)<std::abs(b);});
    result.units.push_back(std::move(s));
  }
  return result;
}
// The above basic pivot-only scan is replaced below with a certified
// reduction that records both zero rows and one-unknown rows.
static GF2Report fully_reduce(const std::vector<Row>& source,
                              const std::vector<signed char>& assigned,
                              long budget) {
  GF2Report result;
  std::map<int,ActiveRow> pivots;
  for(const Row& origin:source) {
    ActiveRow r;
    r.rhs=origin.rhs;
    for(int v:origin.vars) {
      if(v<=0 || size_t(v)>=assigned.size())
        throw std::runtime_error("R111_GF2_BAD_VARIABLE");
      if(assigned[v]==0)r.unknown.push_back(v);
      else {
        r.why.push_back(v);
        if(assigned[v]>0)r.rhs^=1;
      }
    }
    bool stored=false;
    while(!r.unknown.empty()) {
      const int pivot=r.unknown.front();
      auto itr=pivots.find(pivot);
      if(itr==pivots.end()) {
        pivots.emplace(pivot,std::move(r));
        stored=true;
        break;
      }
      const auto& p=itr->second;
      result.operations+=long(r.unknown.size()+p.unknown.size()+
                              r.why.size()+p.why.size());
      if(result.operations>budget)
        throw std::runtime_error("R111_GF2_OPERATION_BUDGET");
      r.unknown=symdiff(r.unknown,p.unknown);
      r.why=symdiff(r.why,p.why);
      r.rhs^=p.rhs;
    }
    if(!stored && r.unknown.empty() && r.rhs) {
      result.contradictory=true;
      for(int v:r.why)result.conflict.push_back(assigned[v]>0?-v:v);
      result.pivots=pivots.size();
      return result;
    }
  }
  result.pivots=pivots.size();
  std::set<int> scheduled;
  // Echelon pivots can yield units after XORing with other pivots.
  // Perform a bounded backwards elimination over pivot variables.
  for(auto it=pivots.rbegin();it!=pivots.rend();++it) {
    const int lead=it->first;
    const ActiveRow current=it->second;
    for(auto jt=pivots.begin();jt!=pivots.end()&&jt->first<lead;++jt) {
      ActiveRow& parent=jt->second;
      if(!std::binary_search(parent.unknown.begin(),parent.unknown.end(),lead))
        continue;
      result.operations+=long(parent.unknown.size()+current.unknown.size()+
                              parent.why.size()+current.why.size());
      if(result.operations>budget)
        throw std::runtime_error("R111_GF2_OPERATION_BUDGET");
      parent.unknown=symdiff(parent.unknown,current.unknown);
      parent.why=symdiff(parent.why,current.why);
      parent.rhs^=current.rhs;
    }
  }
  for(const auto& [key,row]:pivots) {
    (void)key;
    if(row.unknown.empty()) {
      if(row.rhs) {
        result.contradictory=true;
        for(int v:row.why)result.conflict.push_back(assigned[v]>0?-v:v);
        return result;
      }
      continue;
    }
    if(row.unknown.size()!=1)continue;
    int var=row.unknown.front();
    if(!scheduled.insert(var).second)continue;
    Signal result_signal;
    result_signal.lit=row.rhs?var:-var;
    for(int assigned_var:row.why)
      result_signal.clause.push_back(assigned[assigned_var]>0?-assigned_var:assigned_var);
    result_signal.clause.push_back(result_signal.lit);
    std::sort(result_signal.clause.begin(),result_signal.clause.end(),
       [](int a,int b){return std::abs(a)<std::abs(b);});
    result.units.push_back(std::move(result_signal));
  }
  return result;
}

class R111Bridge final: public CaDiCaL::ExternalPropagator {
 public:
  std::vector<Row> rows;
  std::vector<signed char> values;
  std::vector<int> trail;
  std::vector<size_t> levels;
  std::deque<Signal> pending;
  std::map<int,V> reasons;
  std::map<int,size_t> reason_cursor;
  std::vector<int> external_clause;
  size_t external_index=0;
  bool dirty=true, disabled=false, budget_off=false;
  long notifications=0,backtracks=0,callbacks=0;
  long scans=0,solved_units=0,reason_calls=0,conflict_events=0;
  long operations=0,peak_rank=0,clauses_exported=0;
  long process_budget=0;
  const long MAX_SCANS=1800;
  const long MAX_CALLBACKS=200000;
  const long MATRIX_BUDGET=120000;
  const long MAX_UNITS=10000;
  explicit R111Bridge(std::vector<Row> certified,int n):
    rows(std::move(certified)),values(size_t(n)+1,0) {
    are_reasons_forgettable=false;
    is_lazy=false;
  }
  void notify_assignment(const std::vector<int>& literals) override {
    for(int lit:literals) {
      int v=std::abs(lit);
      if(v<1||size_t(v)>=values.size()){disabled=true;continue;}
      signed char val=lit>0?1:-1;
      if(values[v]==val)continue;
      if(values[v]!=0){disabled=true;continue;}
      values[v]=val;
      trail.push_back(lit);
      ++notifications;
      dirty=true;
    }
  }
  void notify_new_decision_level() override {levels.push_back(trail.size());}
  void notify_backtrack(size_t level) override {
    ++backtracks;
    if(level>levels.size()){disabled=true;return;}
    while(levels.size()>level) {
      size_t end=levels.back();levels.pop_back();
      while(trail.size()>end) {
        int var=std::abs(trail.back());trail.pop_back();
        values[var]=0;
      }
    }
    pending.clear();
    external_clause.clear();
    external_index=0;
    dirty=true;
  }
  bool cb_check_found_model(const std::vector<int>& model) override {
    if(disabled||rows.empty())return true;
    std::vector<signed char> complete(values.size(),0);
    for(int lit:model) {
      int v=std::abs(lit);
      if(v>0 && size_t(v)<complete.size())complete[v]=lit>0?1:-1;
    }
    for(const Row& row:rows) {
      int rhs=0;
      V no_good;
      for(int v:row.vars) {
        if(complete[v]==0) return true; // original CNF remains authoritative
        rhs^=(complete[v]>0);
        no_good.push_back(complete[v]>0?-v:v);
      }
      if(rhs!=row.rhs) {
        external_clause=std::move(no_good);
        external_index=0;
        return false;
      }
    }
    return true;
  }
  void recompute() {
    if(!dirty || disabled||budget_off)return;
    dirty=false;
    pending.clear();
    if(scans>=MAX_SCANS){budget_off=true;return;}
    try {
      auto r=fully_reduce(rows,values,MATRIX_BUDGET);
      ++scans;operations+=r.operations;
      peak_rank=std::max(peak_rank,r.pivots);
      if(r.contradictory) {
        external_clause=std::move(r.conflict);
        external_index=0;
        ++conflict_events;
        return;
      }
      for(auto &unit:r.units) {
        int v=std::abs(unit.lit);
        if(values[v]!=0)continue;
        if(!reasons.count(unit.lit))
          reasons.emplace(unit.lit,unit.clause);
        pending.push_back(std::move(unit));
      }
    }catch(const std::exception&) {
      budget_off=true;
      pending.clear();
    }
  }
  int cb_propagate() override {
    ++callbacks;
    if(callbacks>MAX_CALLBACKS){budget_off=true;return 0;}
    if(disabled||budget_off||rows.empty()||!external_clause.empty())return 0;
    recompute();
    if(!external_clause.empty())return 0;
    while(!pending.empty() && solved_units<MAX_UNITS) {
      Signal s=std::move(pending.front());pending.pop_front();
      const int var=std::abs(s.lit);
      if(values[var]!=0)continue;
      // Reasons are immutable mathematical consequences of the XOR source,
      // even if future assignments cause a different explanation.
      reasons[s.lit]=s.clause;
      reason_cursor.erase(s.lit);
      ++solved_units;
      return s.lit;
    }
    if(solved_units>=MAX_UNITS)budget_off=true;
    return 0;
  }
  int cb_add_reason_clause_lit(int lit) override {
    ++reason_calls;
    auto it=reasons.find(lit);
    if(it==reasons.end())throw std::runtime_error("R111_MISSING_REASON");
    size_t &at=reason_cursor[lit];
    if(at<it->second.size())return it->second[at++];
    reason_cursor.erase(lit);
    return 0;
  }
  bool cb_has_external_clause(bool& forgettable) override {
    ++callbacks;
    forgettable=false;
    if(callbacks>MAX_CALLBACKS){budget_off=true;return false;}
    if(disabled||budget_off)return false;
    if(external_clause.empty())recompute();
    if(external_clause.empty())return false;
    ++clauses_exported;
    return true;
  }
  int cb_add_external_clause_lit() override {
    if(external_index<external_clause.size())
      return external_clause[external_index++];
    external_clause.clear();external_index=0;
    return 0;
  }
};

static std::vector<Row> certified_rows(const fs::path& source,
                                      int max_rows,int max_vars,
                                      int& all_rows,int& observed_vars) {
  Group primary;
  Parsed parsed=parse(source,[&](const V& c){add_group(primary,c);});
  (void)parsed;
  std::vector<Row> exact;
  for(const auto& [vars,mask]:primary) {
    for(int rhs=0;rhs<2;++rhs) {
      uint64_t want=parity_mask(int(vars.size()),rhs);
      if((mask&want)==want)exact.push_back({vars,rhs,{}});
    }
  }
  all_rows=int(exact.size());
  // Certify against a completely independent parsing pass before any
  // row is presented to CaDiCaL through the external propagator.
  std::set<V> requested;
  for(const auto& row:exact)requested.insert(row.vars);
  Group check;
  parse(source,[&](const V& c){add_group(check,c,&requested);});
  for(const auto& r:exact) {
    auto it=check.find(r.vars);
    if(it==check.end() || (it->second&parity_mask(int(r.vars.size()),r.rhs)) !=
                          parity_mask(int(r.vars.size()),r.rhs))
      throw std::runtime_error("R111_INDEPENDENT_XOR_CERT_FAILED");
  }
  std::stable_sort(exact.begin(),exact.end(),
       [](const Row& a,const Row& b){
         if(a.vars.size()!=b.vars.size())return a.vars.size()<b.vars.size();
         return a.vars<b.vars;
       });
  std::set<int> observed;
  std::vector<Row> accepted;
  for(const auto& row:exact) {
    if(int(accepted.size())>=max_rows)break;
    size_t additional=0;
    for(int v:row.vars)additional+=!observed.count(v);
    if(int(observed.size()+additional)>max_vars)continue;
    accepted.push_back(row);
    for(int v:row.vars)observed.insert(v);
  }
  observed_vars=int(observed.size());
  return accepted;
}
static void selftest() {
  std::vector<Row> matrix={
    {{1,2,3},0,{}},
    {{1,2,4},0,{}}
  };
  std::vector<signed char> values(5,0);
  values[3]=1;
  auto r=fully_reduce(matrix,values,20000);
  require(!r.contradictory,"R111 GF2 false conflict");
  bool found=false;
  for(const auto &s:r.units) {
    if(s.lit==4) {
      if(s.clause!=V({-3,4}))throw std::runtime_error("R111_GF2_WRONG_REASON");
      found=true;
    }
  }
  require(found,"R111 GF2 failed derived two-row unit");
  values[4]=-1;
  auto bad=fully_reduce(matrix,values,20000);
  require(bad.contradictory,"R111 failed GF2 conflict");
  std::sort(bad.conflict.begin(),bad.conflict.end());
  require(bad.conflict==V({-3,4}),"R111 GF2 wrong conflict reason");
  values[3]=0;values[4]=0;
  auto neutral=fully_reduce(matrix,values,20000);
  require(!neutral.contradictory && neutral.units.empty(),
          "R111 GF2 unjustified unit");
  R111Bridge bridge(matrix,4);
  bridge.notify_new_decision_level();
  bridge.notify_assignment({3});
  require(bridge.cb_propagate()==4,"R111 IPASIR-UP missing two-way unit");
  V reason;
  int lit;
  while((lit=bridge.cb_add_reason_clause_lit(4))!=0)reason.push_back(lit);
  require(reason==V({-3,4}),"R111 IPASIR-UP bad streamed reason");
  bridge.notify_backtrack(0);
  require(bridge.values[3]==0,"R111 IPASIR-UP failed backtrack");
  std::cout<<"R111_GF2_BIDIRECTIONAL_SELFTEST_PASS\n";
}

int main(int argc,char**argv){
  try{
    if(argc==2&&std::string(argv[1])=="selftest"){
      selftest();
      return 0;
    }
    require(argc==4,"usage: r111_live selftest | clean|live original.cnf solver_input.cnf");
    const std::string mode=argv[1];
    require(mode=="clean"||mode=="live","invalid live mode");
    fs::path source=argv[2],input=argv[3];
    auto started=std::chrono::steady_clock::now();
    int total_xor=0,observed=0;
    std::vector<Row> certified;
    if(mode=="live")
      certified=certified_rows(source,192,1024,total_xor,observed);
    CaDiCaL::Solver solver;
    Parsed parsed=parse(input,[&](const V& c){
      for(int lit:c)solver.add(lit);
      solver.add(0);
    });
    std::unique_ptr<R111Bridge> external;
    if(mode=="live" && !certified.empty()) {
      external=std::make_unique<R111Bridge>(std::move(certified),parsed.vars);
      solver.connect_external_propagator(external.get());
      std::set<int> seen;
      for(const auto &row:external->rows)
        for(int v:row.vars)if(seen.insert(v).second)solver.add_observed_var(v);
    }
    auto solve_start=std::chrono::steady_clock::now();
    int status=solver.solve();
    const double solve_s=std::chrono::duration<double>(
         std::chrono::steady_clock::now()-solve_start).count();
    if(status==10){
      parse(source,[&](const V& c){
        bool satisfied=false;
        for(int lit:c) {
          int val=solver.val(std::abs(lit));
          if(val && ((val>0)==(lit>0)))satisfied=true;
        }
        if(!satisfied)throw std::runtime_error("R111_SAT_MODEL_NOT_VERIFIED");
      });
    }
    require(status==10||status==20,"R111 solver returned unknown");
    const double full_s=std::chrono::duration<double>(
       std::chrono::steady_clock::now()-started).count();
    std::cout<<std::fixed<<std::setprecision(7)
       <<"R111_RESULT status="<<(status==10?"SAT":"UNSAT")
       <<" solve_s="<<solve_s<<" wall_s="<<full_s
       <<" source_xors="<<total_xor
       <<" activated_rows="<<(external?external->rows.size():0)
       <<" observed_vars="<<observed
       <<" assignments="<<(external?external->notifications:0)
       <<" backtracks="<<(external?external->backtracks:0)
       <<" live_scans="<<(external?external->scans:0)
       <<" live_units="<<(external?external->solved_units:0)
       <<" live_conflicts="<<(external?external->conflict_events:0)
       <<" live_clause_exports="<<(external?external->clauses_exported:0)
       <<" live_reason_calls="<<(external?external->reason_calls:0)
       <<" live_operations="<<(external?external->operations:0)
       <<" budget_off="<<(external?external->budget_off:0)
       <<" disabled="<<(external?external->disabled:0)
       <<" model_checked="<<(status==10)
       <<"\n";
    return status;
  }catch(const std::exception& e){
    std::cerr<<"R111_FAIL_CLOSED "<<e.what()<<"\n";
    return 2;
  }
}

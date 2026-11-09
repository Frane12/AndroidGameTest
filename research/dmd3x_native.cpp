// DRNAS DMD3X - one-process native structural ANF search and full-source BCP gate.
// Source-only heuristic. ALL injected clauses retain local exhaustive proofs
// from original CNF. Original clauses are never removed. No LRAT UNSAT claim.
#define main dmd1_legacy_entry
#include "dmd1_anf.cpp"
#undef main
#include <deque>
#include <limits>
using namespace std;

struct BCPResult {
  vector<signed char> values;
  int assignments=0;
  bool conflict=false,expired=false;
};
static BCPResult full_bcp(const CNF& f,const vector<Lemma>& extra,
                          Clock::time_point until) {
  BCPResult b; b.values.assign((size_t)f.n+1,0);
  if(f.clauses.size()>80000 || f.n>150000){b.expired=true;return b;}
  vector<const Clause*> all; all.reserve(f.clauses.size()+extra.size());
  for(const auto& c:f.clauses)all.push_back(&c);
  for(const auto& c:extra)all.push_back(&c.c);
  vector<vector<int>> occ((size_t)f.n+1);
  for(int i=0;i<(int)all.size();++i) {
    if((i&2047)==0&&Clock::now()>until){b.expired=true;return b;}
    for(int l:*all[i])occ[abs(l)].push_back(i);
  }
  deque<int> queue;
  auto assign=[&](int lit)->bool {
    int var=abs(lit);signed char val=lit>0?1:-1;
    if(b.values[var]==-val){b.conflict=true;return false;}
    if(!b.values[var]){b.values[var]=val;queue.push_back(var);++b.assignments;}
    return true;
  };
  for(const Clause* c:all) {
    if(c->empty()){b.conflict=true;return b;}
    if(c->size()==1&&!assign((*c)[0]))return b;
  }
  long steps=0;
  while(!queue.empty()) {
    int v=queue.front();queue.pop_front();
    if((++steps&1023)==0&&Clock::now()>until){b.expired=true;return b;}
    for(int id:occ[v]){
      const auto& c=*all[id];
      int free=0,unassigned=0;bool satisfied=false;
      for(int lit:c) {
        signed char val=b.values[abs(lit)];
        if(!val){++unassigned;free=lit;}
        else if((lit>0?val:-val)>0){satisfied=true;break;}
      }
      if(satisfied)continue;
      if(unassigned==0){b.conflict=true;return b;}
      if(unassigned==1&&!assign(free))return b;
    }
  }
  return b;
}
struct Ranked {int index=0,score=0,region=0;};
static vector<int> choose_seeds(const CNF& f,int max_seeds,int& gates,
                                int& binary,int& units) {
  vector<int> bin_ref((size_t)f.n+1,0),unit_ref((size_t)f.n+1,0);
  gates=0;binary=0;units=0;
  for(const auto& c:f.clauses) {
    if(c.size()==1){++units;++unit_ref[abs(c[0])];}
    if(c.size()==2){++binary;for(int l:c)++bin_ref[abs(l)];}
  }
  vector<vector<Ranked>> region(8);
  for(int i=0;i<(int)f.clauses.size();++i){
    const auto& c=f.clauses[i];
    if(c.empty()||c.size()>3)continue;
    int s=(c.size()==1?10000:c.size()==2?500:120);
    for(int lit:c){
      int v=abs(lit);
      if(unit_ref[v])s+=800;
      if(c.size()==3&&bin_ref[v]>=2)s+=70;
    }
    if(c.size()==3) {
      int strong=0;for(int lit:c)if(bin_ref[abs(lit)]>=2)++strong;
      if(strong>=2){s+=125;gates++;}
    }
    // All selection is based on original CNF geometry, never SAT outcomes.
    int rg=(int)((8LL*i)/max(1LL,(long long)f.clauses.size()));
    rg=min(7,rg);
    region[rg].push_back({i,s,rg});
  }
  for(auto& v:region)sort(v.begin(),v.end(),[](auto&a,auto&b){
    if(a.score!=b.score)return a.score>b.score;
    return a.index<b.index;
  });
  vector<int> out;out.reserve(max_seeds);
  size_t at[8]={};
  bool progress=true;
  while((int)out.size()<max_seeds&&progress){
    progress=false;
    for(int k=0;k<8&&out.size()<(size_t)max_seeds;k++) {
      if(at[k]<region[k].size()){
        out.push_back(region[k][at[k]++].index);
        progress=true;
      }
    }
  }
  return out;
}
static vector<int> local_bag(const CNF& f,int seed,
                             const vector<vector<int>>& occ) {
  vector<int> ids={seed};set<int> vs;
  for(int l:f.clauses[seed])vs.insert(abs(l));
  if(vs.size()>8)return {};
  set<int> seen={seed};
  // Greedily add the nearest short clauses in the implication neighborhood.
  for(int turn=0;turn<11;turn++) {
    int best=-1,best_score=numeric_limits<int>::min();
    vector<int> vars(vs.begin(),vs.end());
    for(int var:vars) {
      int count=0;
      for(int id:occ[var]) {
        if(++count>120)break;
        if(seen.count(id))continue;
        const auto& c=f.clauses[id];
        if(c.empty()||c.size()>4)continue;
        int extra=0,share=0;
        for(int l:c) {
          if(vs.count(abs(l)))++share;
          else ++extra;
        }
        if(vs.size()+(size_t)extra>8)continue;
        // Favor tight overlaps and small proof supports.
        int score=30*share-20*extra-4*(int)c.size();
        if(score>best_score||(score==best_score&&id<best)) {
          best=id;best_score=score;
        }
      }
    }
    if(best<0)break;
    ids.push_back(best);seen.insert(best);
    for(int l:f.clauses[best])vs.insert(abs(l));
  }
  sort(ids.begin(),ids.end());
  return ids;
}
static string json_escape(const string& s){
  string v="\"";for(char x:s){if(x=='"'||x=='\\')v+='\\';v+=x;}v+='\"';return v;
}
int main(int argc,char** argv) {
 try {
  if(argc!=7)throw runtime_error(
    "usage: dmd3x_native original.cnf augmented.cnf proof.json budget_ms max_groups gate|all");
  string input=argv[1],output=argv[2],proof=argv[3],mode=argv[6];
  int budget=stoi(argv[4]),max_groups=stoi(argv[5]);
  if((mode!="gate"&&mode!="all")||budget<1||budget>1000||
      max_groups<1||max_groups>128)throw runtime_error("invalid DMD3X configuration");
  auto total_start=Clock::now();
  CNF f=parse(input);
  auto parse_ms=chrono::duration<double,milli>(Clock::now()-total_start).count();
  int gate_like=0,binary=0,unit=0;
  vector<int> seeds=choose_seeds(f,512,gate_like,binary,unit);
  vector<vector<int>> occ((size_t)f.n+1);
  for(int i=0;i<(int)f.clauses.size();i++)
    if(f.clauses[i].size()<=4)
      for(int lit:f.clauses[i])occ[abs(lit)].push_back(i);
  auto mining_start=Clock::now();
  vector<Lemma> candidates;
  set<string> known;for(const auto& c:f.clauses)known.insert(clause_key(c));
  set<string> seen_groups;
  int groups=0,nonlinear=0,tested=0,proposals=0;
  int seed_probes=0,skipped_bags=0;
  bool mining_timeout=false;
  for(int seed:seeds){
    if(groups>=max_groups||(int)candidates.size()>=24)break;
    if(!in_time(mining_start,budget)){mining_timeout=true;break;}
    ++seed_probes;
    auto ids=local_bag(f,seed,occ);
    if(ids.size()<2){++skipped_bags;continue;}
    set<int> vs;for(int id:ids)for(int l:f.clauses[id])vs.insert(abs(l));
    if(vs.size()<2||vs.size()>8){++skipped_bags;continue;}
    ostringstream sig;for(int id:ids)sig<<id<<',';
    if(!seen_groups.insert(sig.str()).second){++skipped_bags;continue;}
    ++groups;
    vector<int> vars(vs.begin(),vs.end());
    unordered_map<int,int> pos;for(int i=0;i<(int)vars.size();i++)pos[vars[i]]=i;
    int n=(int)vars.size();
    vector<uint32_t> good;
    for(uint32_t mask=0;mask<(1u<<n);mask++)
      if(any_sat(ids,f,pos,mask))good.push_back(mask);
    tested+=1<<n;
    auto add=[&](Clause c){
      if(candidates.size()>=24)return;
      string k=clause_key(c);
      if(known.count(k))return;
      ++proposals;
      if(!verify_local(c,ids,f,pos,n))
        throw runtime_error("unsound local algebraic derivation");
      candidates.push_back({move(c),ids});known.insert(k);
    };
    if(good.empty()){add({});break;}
    // First try units and binary equations: strongest possible BCP impact.
    for(int j=0;j<n;j++) {
      bool all0=true,all1=true;
      for(uint32_t m:good) {
        if(m&(1u<<j))all0=false;else all1=false;
      }
      if(all0)add({-vars[j]});
      if(all1)add({vars[j]});
    }
    for(int a=0;a<n;a++)for(int b=a+1;b<n;b++){
      bool eq=true,neq=true;
      for(uint32_t m:good){
        bool x=(m>>a)&1u,y=(m>>b)&1u;
        if(x!=y)eq=false;else neq=false;
      }
      if(eq){add({-vars[a],vars[b]});add({vars[a],-vars[b]});}
      if(neq){add({vars[a],vars[b]});add({-vars[a],-vars[b]});}
    }
    vector<uint32_t> mons={0};
    for(int j=0;j<n;j++)mons.push_back(1u<<j);
    for(int a=0;a<n;a++)for(int b=a+1;b<n;b++)mons.push_back((1u<<a)|(1u<<b));
    vector<uint64_t> rows;
    for(auto m:good)rows.push_back(monomial_row(m,mons));
    auto basis=nullspace(rows,(int)mons.size());
    for(uint64_t b:basis){
      int deg=0;uint32_t support=0;
      for(int k=0;k<(int)mons.size();k++)if(b&(1ull<<k)){
        deg=max(deg,__builtin_popcount(mons[k]));support|=mons[k];
      }
      if(deg==2&&__builtin_popcountll(b)<=5)++nonlinear;
      if(deg!=2||__builtin_popcountll(b)>4||
         __builtin_popcount(support)<2||__builtin_popcount(support)>3)continue;
      if(candidates.size()>=24)break;
      vector<int> active;
      for(int j=0;j<n;j++)if(support&(1u<<j))active.push_back(j);
      int count=0;
      for(int sub=0;sub<(1<<(int)active.size());sub++){
        uint32_t m=0;
        for(int j=0;j<(int)active.size();j++)
          if(sub&(1<<j))m|=1u<<active[j];
        if(__builtin_parityll(monomial_row(m,mons)&b))++count;
      }
      if(count>4)continue;
      for(int sub=0;sub<(1<<(int)active.size());sub++){
        uint32_t m=0;
        for(int j=0;j<(int)active.size();j++)
          if(sub&(1<<j))m|=1u<<active[j];
        if(!__builtin_parityll(monomial_row(m,mons)&b))continue;
        Clause blocked;
        for(int j:active)blocked.push_back((m&(1u<<j))?-vars[j]:vars[j]);
        add(move(blocked));
      }
    }
  }
  auto mining_ms=chrono::duration<double,milli>(Clock::now()-mining_start).count();
  // FULL-CNF root UP is independently evaluated on identical ORIGINAL clauses.
  // It is a novelty heuristic, not a global proof of CDCL usefulness.
  BCPResult base,aug;
  bool gate_probed=false;
  int new_units=0;
  bool new_root_conflict=false;
  string selection_reason="no_lemmas";
  vector<Lemma> selected;
  if(!candidates.empty()){
    if(mode=="all"){
      selected=candidates;selection_reason="all_proved_lemmas";
    }else{
      auto gate_stop=Clock::now()+chrono::milliseconds(200);
      base=full_bcp(f,{},gate_stop);
      if(!base.expired)aug=full_bcp(f,candidates,gate_stop);
      if(base.expired||aug.expired){
        selection_reason="full_bcp_budget_exhausted";
      }else{
        gate_probed=true;
        for(int i=1;i<=f.n;i++)
          if(base.values[i]==0&&aug.values[i]!=0)++new_units;
        new_root_conflict=aug.conflict&&!base.conflict;
        if(new_units>0||new_root_conflict){
          selected=candidates;selection_reason="full_bcp_new_propagation";
        }else selection_reason="no_global_root_bcp_novelty";
      }
    }
  }
  if(!selected.empty())save_dimacs(output,f,selected);
  auto elapsed=chrono::duration<double,milli>(Clock::now()-total_start).count();
  string result=proof_json(selected,groups,nonlinear,proposals,tested,
                           mining_timeout,false,elapsed);
  size_t where=result.find("\"lemmas\":");
  if(where==string::npos)throw runtime_error("proof serialization error");
  ostringstream meta;
  meta<<"\"dmd3x_protocol\":\"DMD3X-NATIVE-STRUCTURE-ROOT-BCP-v1\","
      <<"\"gate_mode\":"<<json_escape(mode)<<","
      <<"\"candidate_lemmas\":"<<candidates.size()<<","
      <<"\"selected_lemmas\":"<<selected.size()<<","
      <<"\"selection_reason\":"<<json_escape(selection_reason)<<","
      <<"\"structural_gate_like_clause_seeds\":"<<gate_like<<","
      <<"\"original_binary_clauses\":"<<binary<<","
      <<"\"original_unit_clauses\":"<<unit<<","
      <<"\"full_formula_clauses\":"<<f.clauses.size()<<","
      <<"\"seed_probes\":"<<seed_probes<<","
      <<"\"skipped_bags\":"<<skipped_bags<<","
      <<"\"native_parse_ms\":"<<parse_ms<<","
      <<"\"native_mining_ms\":"<<mining_ms<<","
      <<"\"full_BCP_probed\":"<<(gate_probed?"true":"false")<<","
      <<"\"root_BCP_base_units\":"<<(gate_probed?base.assignments:-1)<<","
      <<"\"root_BCP_after_units\":"<<(gate_probed?aug.assignments:-1)<<","
      <<"\"root_BCP_new_units\":"<<new_units<<","
      <<"\"root_BCP_new_conflict\":"<<(new_root_conflict?"true":"false")<<",";
  result.insert(where,meta.str());
  ofstream out(proof);if(!out)throw runtime_error("cannot write proof JSON");
  out<<result<<"\n";
  cout<<"DMD3X_DISCOVERY "<<result<<"\n";
  return 0;
 }catch(const exception& e){cerr<<"DMD3X_ERROR "<<e.what()<<"\n";return 1;}
}

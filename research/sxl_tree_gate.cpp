// DRNAS SXL: bounded binary lookahead to rank already source-proved lemmas.
// Every branch probes the ORIGINAL full CNF. No branch assumption is injected.
#define main sxl_embedded_dmd1_main
#include "dmd1_anf.cpp"
#undef main
#include <deque>
#include <functional>
#include <iomanip>
#include <map>
#include <random>

struct StopSXL {};
struct LimitSXL {
  Clock::time_point start=Clock::now(),end;
  explicit LimitSXL(int ms):end(start+chrono::milliseconds(ms)){}
  void check()const{if(Clock::now()>=end)throw StopSXL{};}
  double elapsed()const{return chrono::duration<double>(Clock::now()-start).count();}
};
struct UPStateSXL {vector<signed char> val;bool conflict=false;long long work=0;};
struct OriginalUP {
  const CNF& f;
  vector<vector<int>> falsified;
  vector<int> units;
  vector<int> degree;
  bool empty=false;
  static size_t key(int lit){return 2ULL*abs(lit)+(lit<0);}
  OriginalUP(const CNF& src,const LimitSXL& lim):f(src),falsified(2ULL*src.n+2),degree(src.n+1,0){
    for(int i=0;i<(int)f.clauses.size();++i){
      if((i&255)==0)lim.check();
      Clause c=f.clauses[i];sort(c.begin(),c.end());
      c.erase(unique(c.begin(),c.end()),c.end());
      bool taut=false;for(int l:c)if(binary_search(c.begin(),c.end(),-l)){taut=true;break;}
      if(taut)continue;
      if(c.empty())empty=true;
      if(c.size()==1)units.push_back(c[0]);
      for(int l:c){falsified[key(l)].push_back(i);++degree[abs(l)];}
    }
  }
  UPStateSXL run(const Clause& assumptions,const Clause* extra,const LimitSXL& lim)const{
    lim.check();UPStateSXL s;s.val.assign(f.n+1,0);s.conflict=empty;
    Clause normalized_extra;
    if(extra){normalized_extra=*extra;sort(normalized_extra.begin(),normalized_extra.end());
      normalized_extra.erase(unique(normalized_extra.begin(),normalized_extra.end()),normalized_extra.end());extra=&normalized_extra;}
    deque<int> pending;
    auto assign=[&](int l){
      int v=abs(l);signed char x=l>0?1:-1;
      if(s.val[v]==-x)s.conflict=true;
      else if(!s.val[v]){s.val[v]=x;pending.push_back(l);}
    };
    for(int l:units)assign(l);
    for(int l:assumptions)assign(l);
    auto scan=[&](const Clause& c){
      int free=0,last=0;bool sat=false;
      // Count literal inspections including the optional short-cut clause.
      for(int l:c){
        ++s.work;
        if(!s.val[abs(l)]){++free;last=l;}
        else if((l>0?s.val[abs(l)]:-s.val[abs(l)])>0){sat=true;break;}
      }
      if(!sat){if(free==0)s.conflict=true;else if(free==1)assign(last);}
    };
    if(extra)scan(*extra);
    long long visits=0;
    while(!pending.empty()&&!s.conflict){
      int l=pending.front();pending.pop_front();
      if(extra)scan(*extra);
      for(int id:falsified[key(-l)]){
        if((++visits&127)==0)lim.check();
        // Normalize duplicate literals for semantically exact UP.
        const Clause& raw=f.clauses[id];
        if(raw.size()<=1){scan(raw);continue;}
        Clause c=raw;sort(c.begin(),c.end());c.erase(unique(c.begin(),c.end()),c.end());
        scan(c);if(s.conflict)break;
      }
    }
    lim.check();return s;
  }
};
struct RatingSXL {
  int index=0,nodes=0,novel=0,conflicts=0;
  long long base_work=0,aug_work=0,score=0;
};
static RatingSXL rate_sxl(const OriginalUP& up,const Clause& lemma,int index,int depth,const LimitSXL& lim){
  RatingSXL r;r.index=index;
  vector<int> vars;for(int l:lemma)vars.push_back(abs(l));
  sort(vars.begin(),vars.end());vars.erase(unique(vars.begin(),vars.end()),vars.end());
  sort(vars.begin(),vars.end(),[&](int a,int b){return up.degree[a]!=up.degree[b]?up.degree[a]>up.degree[b]:a<b;});
  // Add a small original-CNF neighborhood so depth 3 can reveal contexts that
  // one-level probing of the lemma variables misses. Rank without literal signs.
  set<int> support(vars.begin(),vars.end());map<int,int> nearby;
  for(int l:lemma)for(int sign:{-1,1}){
    int seen=0;
    for(int id:up.falsified[OriginalUP::key(sign*abs(l))]){
      if(++seen>64)break;
      for(int x:up.f.clauses[id])if(!support.count(abs(x)))++nearby[abs(x)];
    }
  }
  vector<pair<int,int>> ns;for(auto [v,c]:nearby)ns.push_back({-c,v});
  sort(ns.begin(),ns.end());
  // Interleave one neighbor ahead of the final support variable.
  if(!ns.empty()&&vars.size()>1)vars.insert(vars.begin()+1,ns.front().second);
  function<void(Clause&,int)> visit=[&](Clause& assumptions,int level){
    lim.check();auto base=up.run(assumptions,nullptr,lim);
    if(base.conflict)return;
    auto aug=up.run(assumptions,&lemma,lim);++r.nodes;
    r.base_work+=base.work;r.aug_work+=aug.work;
    if(aug.conflict)++r.conflicts;
    else for(int v=1;v<=up.f.n;++v)if(!base.val[v]&&aug.val[v])++r.novel;
    if(level==depth)return;
    int split=0;for(int v:vars)if(!base.val[v]){split=v;break;}
    if(!split)return;
    assumptions.push_back(-split);visit(assumptions,level+1);
    assumptions.back()=split;visit(assumptions,level+1);assumptions.pop_back();
  };
  Clause assumptions;visit(assumptions,0);
  long long saved=r.base_work-r.aug_work;
  // Work savings are a heuristic about this probe, never a CDCL speedup claim.
  bool useful_work=saved>=64&&saved*50>=max(1LL,r.base_work);
  r.score=1000000LL*r.conflicts+10000LL*r.novel+(useful_work?min(9999LL,saved):0);
  return r;
}
static string indices_sxl(const vector<int>& a){return array_json(a);}
static UPStateSXL slow_up_sxl(const CNF& f,const Clause& assumptions,const Clause* extra){
  UPStateSXL s;s.val.assign(f.n+1,0);
  auto put=[&](int l){signed char v=l>0?1:-1;if(s.val[abs(l)]==-v)s.conflict=true;else s.val[abs(l)]=v;};
  for(int l:assumptions)put(l);
  bool changed=true;
  while(changed&&!s.conflict){
    changed=false;
    for(size_t i=0;i<f.clauses.size()+(extra?1:0);++i){
      Clause c=i<f.clauses.size()?f.clauses[i]:*extra;sort(c.begin(),c.end());c.erase(unique(c.begin(),c.end()),c.end());
      bool taut=false;for(int l:c)if(binary_search(c.begin(),c.end(),-l))taut=true;if(taut)continue;
      bool sat=false;int free=0,last=0;
      for(int l:c){if(!s.val[abs(l)]){++free;last=l;}else if((l>0?s.val[abs(l)]:-s.val[abs(l)])>0)sat=true;}
      if(sat)continue;
      if(free==0){s.conflict=true;break;}
      if(free==1){put(last);changed=true;}
    }
  }
  return s;
}
static void selftest_sxl(){
  mt19937 rng(921137);int checked=0;
  LimitSXL lim(2000);
  for(int t=0;t<180;++t){
    CNF f;f.n=1+rng()%6;
    for(int j=0,nc=rng()%14;j<nc;++j){Clause c;for(int k=0,nl=rng()%5;k<nl;++k)c.push_back((rng()%2?1:-1)*(1+int(rng()%f.n)));f.clauses.push_back(c);}
    OriginalUP up(f,lim);
    for(int j=0;j<6;++j){
      Clause assumptions,extra;for(int k=0,n=rng()%4;k<n;++k)assumptions.push_back((rng()%2?1:-1)*(1+int(rng()%f.n)));
      for(int k=0,n=rng()%4;k<n;++k)extra.push_back((rng()%2?1:-1)*(1+int(rng()%f.n)));
      for(bool use:{false,true}){
        auto a=up.run(assumptions,use?&extra:nullptr,lim),b=slow_up_sxl(f,assumptions,use?&extra:nullptr);
        if(a.conflict!=b.conflict||(!a.conflict&&a.val!=b.val))throw runtime_error("SXL independent UP closure mismatch");
        ++checked;
      }
    }
  }
  CNF f;f.n=3;f.clauses={{1,2,3},{1,2,-3}};OriginalUP up(f,lim);Clause lemma={1,2};
  auto root=rate_sxl(up,lemma,0,0,lim),tree=rate_sxl(up,lemma,0,1,lim);
  if(root.novel||tree.novel<=0||tree.nodes>3)throw runtime_error("SXL branch-only novelty not detected");
  cout<<"SXL_NATIVE_SELFTEST_PASS {\"independent_UP_closures\":"<<checked<<",\"root_novel_units\":0,\"branch_novel_units\":"<<tree.novel<<"}\n";
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="selftest"){selftest_sxl();return 0;}
  if(argc!=8)throw runtime_error("usage: sxl_tree_gate original augmented selected metrics depth budget_ms max_selected");
  int depth=stoi(argv[5]),budget=stoi(argv[6]),keep=stoi(argv[7]);
  if(depth<0||depth>3||budget<1||budget>2000||keep<1||keep>2)throw runtime_error("invalid SXL limits");
  LimitSXL lim(budget);CNF f=parse(argv[1]),full=parse(argv[2]);
  if(f.n!=full.n||full.clauses.size()<f.clauses.size()||full.clauses.size()-f.clauses.size()>24||
     !equal(f.clauses.begin(),f.clauses.end(),full.clauses.begin()))throw runtime_error("original prefix mismatch");
  vector<Clause> candidates(full.clauses.begin()+f.clauses.size(),full.clauses.end());
  vector<RatingSXL> rated;vector<int> selected;int scanned=0,total_nodes=0;bool expired=false;
  try{
    lim.check();
    if(!candidates.empty()){
      OriginalUP up(f,lim);vector<int> pool(candidates.size());iota(pool.begin(),pool.end(),0);
      sort(pool.begin(),pool.end(),[&](int a,int b){
        if(candidates[a].size()!=candidates[b].size())return candidates[a].size()<candidates[b].size();
        return a<b;
      });
      if(pool.size()>8)pool.resize(8);
      for(int i:pool){auto v=rate_sxl(up,candidates[i],i,depth,lim);++scanned;total_nodes+=v.nodes;rated.push_back(v);}
      sort(rated.begin(),rated.end(),[](const auto&a,const auto&b){return a.score!=b.score?a.score>b.score:a.index<b.index;});
      for(const auto& r:rated)if(r.score>0&&(int)selected.size()<keep)selected.push_back(r.index);
    }
  }catch(const StopSXL&){expired=true;selected.clear();}
  vector<Lemma> out;for(int i:selected)out.push_back({candidates[i],{}});
  if(!out.empty())save_dimacs(argv[3],f,out);
  ostringstream js;js<<fixed<<setprecision(6)<<"{\"protocol\":\"DRNAS-SXL-BINARY-LOOKAHEAD-v1\",\"depth\":"<<depth
    <<",\"budget_ms\":"<<budget<<",\"candidates\":"<<candidates.size()<<",\"scanned\":"<<scanned
    <<",\"nodes\":"<<total_nodes<<",\"budget_exhausted\":"<<(expired?"true":"false")
    <<",\"selected\":"<<selected.size()<<",\"selected_indices\":"<<indices_sxl(selected)
    <<",\"wall_s\":"<<lim.elapsed()<<",\"ratings\":[";
  for(size_t i=0;i<rated.size();++i){if(i)js<<",";const auto& r=rated[i];
    js<<"{\"index\":"<<r.index<<",\"nodes\":"<<r.nodes<<",\"novel_units\":"<<r.novel
      <<",\"earlier_conflicts\":"<<r.conflicts<<",\"base_literal_work\":"<<r.base_work
      <<",\"aug_literal_work\":"<<r.aug_work<<",\"score\":"<<r.score<<"}";}
  js<<"]}";ofstream meta(argv[4]);if(!meta)throw runtime_error("cannot write SXL metadata");
  meta<<js.str()<<"\n";cout<<"SXL_GATE "<<js.str()<<"\n";
  return 0;
 }catch(const exception& e){cerr<<"SXL_ERROR "<<e.what()<<"\n";return 1;}
}

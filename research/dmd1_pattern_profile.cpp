// DRNAS DMD1: bounded ANF relation discovery with locally exhaustive certificates.
// Experiment, not a general SAT solver. No external libraries required.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
static map<string,int> pat2,pat1;
static map<string,string> patterns_example;
static long long n2_terms_linear=0,n2_terms_quad=0,n2_terms_constant=0;
static long long unit0_all=0,unit1_all=0,equiv_all=0,anti_equiv_all=0;
static void print_counter(const map<string,int>& m){cout<<'{';bool first=true;for(auto& e:m){if(!first)cout<<',';first=false;cout<<'"'<<e.first<<"\":"<<e.second;}cout<<'}';}
static void print_examples(const map<string,string>& m){cout<<'{';bool first=true;for(auto& e:m){if(!first)cout<<',';first=false;cout<<'"'<<e.first<<"\":\""<<e.second<<'"';}cout<<'}';}
using Clause=vector<int>;
struct CNF {int n=0; vector<Clause> clauses;};
struct Lemma {Clause c; vector<int> sources;};
static bool in_time(Clock::time_point start,int ms){return chrono::duration_cast<chrono::milliseconds>(Clock::now()-start).count()<ms;}
static bool lit_sat(int lit,uint32_t mask,const unordered_map<int,int>& pos) {
  auto it=pos.find(abs(lit)); if(it==pos.end())throw runtime_error("unmapped literal");
  bool bit=(mask>>it->second)&1u;return lit>0?bit:!bit;
}
static bool clause_sat(const Clause& c,uint32_t mask,const unordered_map<int,int>& pos){for(int l:c)if(lit_sat(l,mask,pos))return true;return false;}
static CNF parse(const string &file){
  ifstream in(file);if(!in)throw runtime_error("cannot open CNF");
  CNF f; string word; bool header=false;Clause cur;long expected=-1;
  while(in>>word){
    if(word=="c"){string rest;getline(in,rest);continue;}
    if(word=="p") {string fmt;in>>fmt>>f.n>>expected;if(fmt!="cnf"||f.n<=0||expected<0)throw runtime_error("DIMACS header");header=true;continue;}
    if(!header)throw runtime_error("missing header");
    int x=0;try{size_t used; x=stoi(word,&used);if(used!=word.size())throw invalid_argument("token");}catch(...){throw runtime_error("bad DIMACS literal");}
    if(x==0){f.clauses.push_back(move(cur));cur.clear();}
    else {if(abs((long long)x)>f.n)throw runtime_error("literal exceeds vars");cur.push_back(x);}
  }
  if(!header||!cur.empty()||(long)f.clauses.size()!=expected)throw runtime_error("DIMACS clauses mismatch");
  return f;
}
static void save_dimacs(const string& file,const CNF& f,const vector<Lemma>& lemmas) {
  ofstream out(file);if(!out)throw runtime_error("cannot write augmented CNF");
  out<<"p cnf "<<f.n<<" "<<(f.clauses.size()+lemmas.size())<<"\n";
  for(auto& c:f.clauses){for(int l:c)out<<l<<" ";out<<"0\n";}
  for(auto& v:lemmas){for(int l:v.c)out<<l<<" ";out<<"0\n";}
}
static string clause_key(Clause c){sort(c.begin(),c.end());ostringstream s;for(int l:c)s<<l<<',';return s.str();}
static string array_json(const vector<int>& a) {ostringstream s;s<<'[';for(size_t i=0;i<a.size();i++){if(i)s<<',';s<<a[i];}s<<']';return s.str();}
static bool any_sat(const vector<int>& ids,const CNF& f,const unordered_map<int,int>& pos,uint32_t mask){for(int id:ids)if(!clause_sat(f.clauses[id],mask,pos))return false;return true;}
static uint64_t monomial_row(uint32_t mask,const vector<uint32_t>& monomials){uint64_t row=0;for(size_t i=0;i<monomials.size();i++)if((mask&monomials[i])==monomials[i])row|=1ull<<i;return row;}
static vector<uint64_t> nullspace(const vector<uint64_t>& rows,int dim){
  uint64_t pivots[64]={};int rank=0;
  for(uint64_t r:rows){
    while(r){int k=63-__builtin_clzll(r);if(!pivots[k]){pivots[k]=r;rank++;break;}r^=pivots[k];}
  }
  vector<uint64_t> basis;
  for(int free=0;free<dim;free++)if(!pivots[free]){
    uint64_t sol=1ull<<free;
    for(int k=0;k<dim;k++)if(pivots[k]){
      uint64_t other=pivots[k]&~(1ull<<k);
      if(__builtin_parityll(other&sol))sol|=1ull<<k;
    }
    basis.push_back(sol);
  }
  return basis;
}
static bool verify_local(const Clause& c,const vector<int>& ids,const CNF& f,const unordered_map<int,int>& pos,int n){
  for(uint32_t mask=0;mask<(1u<<n);mask++)if(any_sat(ids,f,pos,mask)&&!clause_sat(c,mask,pos))return false;
  return true;
}
static string proof_json(const vector<Lemma>& lemmas,int groups,int nonlinear,int candidates,int tested,int timed_out,bool abstain,double elapsed){
  ostringstream s;s<<"{\"protocol\":\"DMD1-ANF-LOCAL-EXHAUSTIVE-v1\",\"groups\":"<<groups<<",\"nonlinear_relations\":"<<nonlinear<<",\"candidates\":"<<candidates<<",\"tested_assignments\":"<<tested<<",\"timed_out\":"<<(timed_out?"true":"false")<<",\"abstain\":"<<(abstain?"true":"false")<<",\"prep_ms\":"<<elapsed<<",\"lemmas\":[";
  for(size_t i=0;i<lemmas.size();i++){if(i)s<<',';s<<"{\"clause\":"<<array_json(lemmas[i].c)<<",\"source_ids\":"<<array_json(lemmas[i].sources)<<"}";}
  s<<"]}";return s.str();
}
int main(int argc,char** argv){
 try {
  if(argc<4||argc>6){cerr<<"usage: dmd1_anf original.cnf augmented.cnf proof.json [budget_ms=20] [max_groups=64]\n";return 2;}
  string input=argv[1],output=argv[2],proof=argv[3];
  int budget=argc>=5?stoi(argv[4]):20, max_groups=argc>=6?stoi(argv[5]):64;
  if(budget<1||budget>5000||max_groups<1||max_groups>1000)throw runtime_error("invalid budget");
  auto start=Clock::now();vector<Lemma> lemmas;int groups=0,nonlinear=0,candidates=0,tested=0;
  bool abstain=false,timed_out=false;
  CNF f;
  // Avoid paying a large parsing tax on enormous source formulas.
  if(filesystem::file_size(input)>4*1024*1024){abstain=true;}
  else {
   f=parse(input);
   set<string> known;for(auto& c:f.clauses)known.insert(clause_key(c));
   vector<int> seeds;for(int i=0;i<(int)f.clauses.size()&&i<1200;i++)if(f.clauses[i].size()>=1&&f.clauses[i].size()<=3)seeds.push_back(i);
   stable_sort(seeds.begin(),seeds.end(),[&](int a,int b){return f.clauses[a].size()<f.clauses[b].size();});
   set<string> seen_groups;
   for(int seed:seeds){
    if(groups>=max_groups||(int)lemmas.size()>=24)break;
    if(!in_time(start,budget)){timed_out=true;break;}
    vector<int> ids;set<int> vs;
    auto incorporate=[&](int id){set<int> nv=vs;for(int lit:f.clauses[id])nv.insert(abs(lit));if(nv.size()>8)return false;vs=move(nv);ids.push_back(id);return true;};
    if(!incorporate(seed))continue;
    // Grow a small *connected* bag; never incorporate unrelated variables.
    for(int i=0;i<(int)f.clauses.size()&&i<1200&&(int)ids.size()<12;i++){
      if(i==seed||f.clauses[i].empty()||f.clauses[i].size()>4)continue;
      bool shares=false;for(int l:f.clauses[i])if(vs.count(abs(l))){shares=true;break;}
      if(shares)incorporate(i);
    }
    if(vs.size()<2)continue;
    sort(ids.begin(),ids.end());
    ostringstream sig;for(int id:ids)sig<<id<<',';
    if(!seen_groups.insert(sig.str()).second)continue;
    groups++;
    vector<int> vars(vs.begin(),vs.end());unordered_map<int,int> pos;for(int i=0;i<(int)vars.size();i++)pos[vars[i]]=i;
    int n=vars.size(); vector<uint32_t> good;good.reserve(1<<n);
    for(uint32_t mask=0;mask<(1u<<n);mask++)if(any_sat(ids,f,pos,mask))good.push_back(mask);
    tested+=1<<n;
    auto add=[&](Clause c){
      if((int)lemmas.size()>=24)return;
      string key=clause_key(c);
      if(known.count(key))return;
      candidates++;
      if(!verify_local(c,ids,f,pos,n))throw runtime_error("independent local consequence failed");
      known.insert(key);lemmas.push_back({move(c),ids});
    };
    if(good.empty()){add({});break;}
    // Abstract algebraic discovery: degree<=2 monomials and GF(2) nullspace.
    vector<uint32_t> mons={0};for(int i=0;i<n;i++)mons.push_back(1u<<i);
    for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)mons.push_back((1u<<i)|(1u<<j));
    vector<uint64_t> rows;for(auto mask:good)rows.push_back(monomial_row(mask,mons));
    auto basis=nullspace(rows,mons.size());
    for(uint64_t b:basis){
      int deg=0;uint32_t support=0;
      for(int i=0;i<(int)mons.size();i++)if(b&(1ull<<i)){
        deg=max(deg,__builtin_popcount(mons[i]));support|=mons[i];
      }
      if((deg==2||deg==1)&&__builtin_popcountll(b)<=5){
        int q=0,l=0,cc=0;vector<string> terms;
        for(int ix=0;ix<(int)mons.size();ix++)if(b&(1ull<<ix)){
          uint32_t m=mons[ix];int d=__builtin_popcount(m);
          if(d==0){cc++;terms.push_back("1");}
          else if(d==1){
            l++;int j=__builtin_ctz(m);terms.push_back("x"+to_string(j+1));
          }else if(d==2){
            q++;int a=__builtin_ctz(m);int z=__builtin_ctz(m&(m-1));
            terms.push_back("x"+to_string(a+1)+"x"+to_string(z+1));
          }
        }
        const string key="q"+to_string(q)+"_l"+to_string(l)+"_c"+to_string(cc)+"_v"+to_string(__builtin_popcount(support));
        if(deg==2){pat2[key]++;n2_terms_linear+=l;n2_terms_quad+=q;n2_terms_constant+=cc;}
        else pat1[key]++;
        if(!patterns_example.count(key)){
          string repr;for(size_t i=0;i<terms.size();i++){if(i)repr+=" XOR ";repr+=terms[i];}
          patterns_example[key]=repr+" = 0";
        }
      }
      if(deg==2&&__builtin_popcountll(b)<=5)nonlinear++;
      // Compact degree-2 polynomial -> short CNF constraints by its truth table.
      if(deg!=2||__builtin_popcountll(b)>4||__builtin_popcount(support)>3||__builtin_popcount(support)<2)continue;
      if((int)lemmas.size()>=12)break;
      vector<int> active;for(int j=0;j<n;j++)if(support&(1u<<j))active.push_back(j);
      int count=0;for(int sub=0;sub<(1<<(int)active.size());sub++){
        uint32_t m=0;for(int j=0;j<(int)active.size();j++)if(sub&(1<<j))m|=1u<<active[j];
        if(__builtin_parityll(monomial_row(m,mons)&b))count++;
      }
      if(count>4)continue;
      for(int sub=0;sub<(1<<(int)active.size());sub++){
        uint32_t m=0;for(int j=0;j<(int)active.size();j++)if(sub&(1<<j))m|=1u<<active[j];
        if(!__builtin_parityll(monomial_row(m,mons)&b))continue;
        Clause block;for(int j:active)block.push_back(m&(1u<<j)?-vars[j]:vars[j]);
        add(move(block));
      }
    }
    // Linear corollaries may be hidden by the nullspace basis orientation.
    for(int j=0;j<n;j++){
      bool all0=true,all1=true;
      for(auto m:good){if(m&(1u<<j))all0=false;else all1=false;}
      if(all0){unit0_all++;add({-vars[j]});}
      if(all1){unit1_all++;add({vars[j]});}
    }
    for(int a=0;a<n;a++)for(int b=a+1;b<n;b++){
      bool eq=true,neq=true;
      for(auto m:good){bool x=(m>>a)&1u,y=(m>>b)&1u;if(x!=y)eq=false;else neq=false;}
      if(eq){equiv_all++;add({-vars[a],vars[b]});add({vars[a],-vars[b]});}
      if(neq){anti_equiv_all++;add({vars[a],vars[b]});add({-vars[a],-vars[b]});}
    }
   }
  }
  auto elapsed=chrono::duration<double,milli>(Clock::now()-start).count();
  if(!abstain&&!lemmas.empty())save_dimacs(output,f,lemmas);
  ofstream p(proof);if(!p)throw runtime_error("cannot write proof json");p<<proof_json(lemmas,groups,nonlinear,candidates,tested,timed_out,abstain,elapsed)<<"\n";
  cout<<"DMD1_DISCOVERY "<<proof_json(lemmas,groups,nonlinear,candidates,tested,timed_out,abstain,elapsed)<<"\n";
  map<string,int> lengths;
  for(auto& v:lemmas)lengths["length_"+to_string(v.c.size())]++;
  cout<<"DMD1_PATTERN {\"groups\":"<<groups<<",\"nonlinear_relations\":"<<nonlinear<<",\"degree2_shapes\":";
  print_counter(pat2);cout<<",\"degree1_shapes\":";print_counter(pat1);
  cout<<",\"examples\":";print_examples(patterns_example);
  cout<<",\"lemma_length\":";print_counter(lengths);
  cout<<",\"n2_linear_terms\":"<<n2_terms_linear<<",\"n2_quadratic_terms\":"<<n2_terms_quad<<",\"n2_constant_terms\":"<<n2_terms_constant;
  cout<<",\"implied_units_false\":"<<unit0_all<<",\"implied_units_true\":"<<unit1_all;
  cout<<",\"implied_equalities\":"<<equiv_all<<",\"implied_inequalities\":"<<anti_equiv_all;
  cout<<",\"soft_budget_ms\":"<<budget<<",\"max_groups\":"<<max_groups<<"}"<<'\n';

  return 0;
 }catch(const exception& e){cerr<<"DMD1_ERROR "<<e.what()<<"\n";return 1;}
}
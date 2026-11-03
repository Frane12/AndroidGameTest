// DRNAS SAT R29 research: reversible bounded auxiliary resolution + certified
// partial GF(2) reasoning. The original R28 primitives are unchanged.
// No structure-only guess is allowed to become a solver answer.
#define main r28_original_main
#include "r28_exact_gf2.cpp"
#undef main
#include <cstdio>
#include <cstring>
#include <set>
#include <unordered_set>
#include <sys/stat.h>
using namespace std;

struct R29Elim {
  int variable=0, pos_id=-1, neg_id=-1;
  vector<int> pos,neg,resolvent;
};
struct R29Recovered {
  vector<vector<int>> clauses;
  vector<R29Elim> eliminated;
};
static bool r29_true(int literal,const vector<int>& truth) {
  return (literal>0)==bool(truth[abs(literal)]);
}
static bool r29_others_true(const vector<int>& clause,int variable,
                           const vector<int>& truth) {
  for(int literal:clause)
    if(abs(literal)!=variable && r29_true(literal,truth))return true;
  return false;
}
static bool r29_reconstruct(const vector<R29Elim>& eliminated,
                           vector<int>& truth) {
  // Pairs are disjoint and refer to original input clauses, hence no other
  // eliminated variable occurs in their two parent clauses.
  for(auto it=eliminated.rbegin();it!=eliminated.rend();++it) {
    const bool need_true=!r29_others_true(it->pos,it->variable,truth);
    const bool need_false=!r29_others_true(it->neg,it->variable,truth);
    if(need_true && need_false)return false;
    truth[it->variable]=need_true?1:0;
  }
  return true;
}
static R29Recovered r29_resolve(const vector<vector<int>>& original,int n) {
  struct Occ {int pos=-1,neg=-1;};
  vector<Occ> occurrence(size_t(n)+1);
  for(size_t c=0;c<original.size();c++)
    for(int lit:original[c]) {
      int v=abs(lit);
      int &where=lit>0?occurrence[v].pos:occurrence[v].neg;
      if(where==-1)where=int(c);
      else where=-2;
    }
  vector<bool> used(original.size(),false);
  R29Recovered out;
  for(int v=1;v<=n;v++) {
    int p=occurrence[v].pos,m=occurrence[v].neg;
    if(p<0 || m<0 || p==m || used[p] || used[m])continue;
    const auto &a=original[p],&b=original[m];
    const bool split=(a.size()==2 && b.size()>=2 && b.size()<=6) ||
                     (b.size()==2 && a.size()>=2 && a.size()<=6);
    if(!split)continue;
    set<int> lits;
    for(int x:a)if(abs(x)!=v)lits.insert(x);
    for(int x:b)if(abs(x)!=v)lits.insert(x);
    if(lits.size()<2 || lits.size()>6)continue;
    bool bad=false;
    for(int x:lits)if(lits.count(-x)){bad=true;break;}
    if(bad)continue;
    vector<int> resolvent(lits.begin(),lits.end());
    used[p]=used[m]=true;
    out.eliminated.push_back({v,p,m,a,b,resolvent});
  }
  out.clauses.reserve(original.size());
  for(size_t i=0;i<original.size();i++)
    if(!used[i])out.clauses.push_back(original[i]);
  for(const auto &e:out.eliminated)out.clauses.push_back(e.resolvent);
  return out;
}
static void r29_resolve_proof(const vector<R29Elim>& entries){
  for(const auto& e:entries) {
    cout<<"c R29_RESOLVE var="<<e.variable<<" pos="<<e.pos_id
        <<" neg="<<e.neg_id<<" literals=";
    for(size_t i=0;i<e.resolvent.size();i++){
      if(i)cout<<",";
      cout<<e.resolvent[i];
    }
    cout<<"\n";
  }
}
static string r29_ids(const vector<uint64_t>& proof,size_t count) {
  string s;
  for(size_t k=0;k<count;k++)
    if(bit(proof,int(k))) {
      if(!s.empty())s+=",";
      s+=to_string(k);
    }
  return s;
}
static bool r29_print_sat(const vector<vector<int>>& original,
                         const vector<R29Elim>& eliminated,
                         const vector<Row>& basis,int n,int rank,
                         size_t eq_count,int covered) {
  vector<int> truth(size_t(n)+1,0);
  for(int p=n;p>=1;p--)if(basis[p].valid){
    int value=basis[p].rhs;
    for(int q=p+1;q<=n;q++)
      if(bit(basis[p].bits,q))value^=truth[q];
    truth[p]=value;
  }
  if(!r29_reconstruct(eliminated,truth) ||
     !valid_model(original,truth))return false;
  cout<<"c R29_ROUTE certified_recovered_pure_xor_sat rank="<<rank
      <<" equations="<<eq_count<<" covered="<<covered
      <<" resolved="<<eliminated.size()<<"\n";
  cout<<"s SATISFIABLE\n";
  for(int v=1;v<=n;v++){
    if((v-1)%20==0)cout<<"v ";
    cout<<(truth[v]?v:-v)<<" ";
    if(v%20==0)cout<<"0\n";
  }
  if(n%20)cout<<"0\n";
  cout<<flush;
  return true;
}
static int r29_fallback(const string& filename,const string& kissat,
                        string reason,int total,int covered,
                        size_t equations,size_t resolved,bool classify){
  cout<<"c R29_ROUTE fallback reason="<<reason
      <<" clauses="<<total<<" covered="<<covered<<" equations="
      <<equations<<" resolved="<<resolved<<"\n"<<flush;
  if(classify)return 0;
  char* args[]={const_cast<char*>(kissat.c_str()),
                const_cast<char*>(filename.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R29_EXEC_FAILURE "<<strerror(errno)<<"\n";
  return 77;
}
static int r29_inject_units(const string& filename,const string& kissat,
                           const vector<vector<int>>& original,int n,
                           const vector<pair<int,vector<uint64_t>>>& forced,
                           const vector<Equation>& eqs,
                           const vector<R29Elim>& eliminated,
                           bool classify) {
  cout<<"c R29_ROUTE certified_derived_units added="<<forced.size()
      <<" equations="<<eqs.size()<<" resolved="<<eliminated.size()
      <<"\n";
  r29_resolve_proof(eliminated);
  print_equations(eqs);
  for(const auto &item:forced) {
    cout<<"c R29_UNIT value="<<item.first
        <<" ids="<<r29_ids(item.second,eqs.size())<<"\n";
  }
  cout<<flush;
  if(classify)return 0;
  char path[]="/tmp/drnas_r29_cnf_XXXXXX";
  int fd=mkstemp(path);
  if(fd<0)return r29_fallback(filename,kissat,"temp_failed",
                              int(original.size()),0,eqs.size(),eliminated.size(),false);
  FILE* f=fdopen(fd,"w");
  if(!f) {close(fd);return 77;}
  if(fprintf(f,"p cnf %d %zu\n",n,original.size()+forced.size())<0) {
    fclose(f);return 77;
  }
  for(const auto &cl:original){
    for(int v:cl)fprintf(f,"%d ",v);
    fprintf(f,"0\n");
  }
  for(const auto &unit:forced)fprintf(f,"%d 0\n",unit.first);
  if(fclose(f)!=0)return 77;
  char* args[]={const_cast<char*>(kissat.c_str()),path,nullptr};
  execv(args[0],args);
  cerr<<"R29_EXEC_FAILURE "<<strerror(errno)<<"\n";
  return 77;
}

int main(int argc,char** argv){
  if(argc!=3 && !(argc==4 && string(argv[3])=="--classify-only")) {
    cerr<<"Usage: r29 INPUT KISSAT [--classify-only]\n";return 2;
  }
  const string filename=argv[1],kissat=argv[2];
  const bool classify=argc==4;
  const bool shadow=[](){
    const char* mode=getenv("R29_MODE");
    return mode && !strcmp(mode,"shadow");
  }();
  int n=0;vector<vector<int>> original;
  if(!read_cnf(filename,n,original))
    return r29_fallback(filename,kissat,"input_guard",0,0,0,0,classify);
  R29Recovered rec=r29_resolve(original,n);
  const auto& clauses=rec.clauses;
  map<string,Pattern> groups;
  vector<pair<string,int>> lookup(clauses.size());
  int covered=0;
  for(size_t id=0;id<clauses.size();id++) {
    const auto& cl=clauses[id];
    int k=int(cl.size());
    if(k==1)continue;
    if(k<2 || k>6)continue;
    vector<pair<int,bool>> literals;
    for(int v:cl)literals.push_back({abs(v),v<0});
    sort(literals.begin(),literals.end());
    bool unique=true;
    for(int j=1;j<k;j++)if(literals[j-1].first==literals[j].first)unique=false;
    if(!unique)continue;
    vector<int> vars;
    int mask=0;
    for(int j=0;j<k;j++) {
      vars.push_back(literals[j].first);
      if(literals[j].second)mask|=1<<j;
    }
    string key=var_key(vars);
    Pattern &p=groups[key];p.vars=vars;p.k=k;
    p.masks|=uint64_t(1)<<mask;
    lookup[id]={key,mask};
  }
  vector<Equation> eqs;
  for(auto &kv:groups) {
    Pattern &p=kv.second;
    int k=p.k;
    uint64_t even=parity_mask(k,0),odd=parity_mask(k,1);
    if((p.masks&even)==even){
      eqs.push_back({p.vars,1});
      p.recognized|=even;
    }
    if((p.masks&odd)==odd){
      eqs.push_back({p.vars,0});
      p.recognized|=odd;
    }
  }
  for(size_t i=0;i<clauses.size();i++){
    if(clauses[i].size()==1){
      eqs.push_back({{abs(clauses[i][0])},int(clauses[i][0]>0)});
      covered++;
    } else if(!lookup[i].first.empty()){
      const auto it=groups.find(lookup[i].first);
      if(it!=groups.end() &&
         (it->second.recognized & (uint64_t(1)<<lookup[i].second)))
        covered++;
    }
  }
  if(eqs.empty())
    return r29_fallback(filename,kissat,"no_certified_parity",
                        int(clauses.size()),covered,0,rec.eliminated.size(),classify);
  if(eqs.size()>3000)
    return r29_fallback(filename,kissat,"eq_cap",int(clauses.size()),
                        covered,eqs.size(),rec.eliminated.size(),classify);
  const size_t words=size_t(n/64+1),proof_words=(eqs.size()+63)/64;
  vector<Row> basis(size_t(n)+1);
  int rank=0;
  for(size_t id=0;id<eqs.size();id++){
    Row row;
    row.bits.assign(words,0);
    row.proof.assign(proof_words,0);
    row.rhs=eqs[id].rhs;
    for(int x:eqs[id].vars)flip(row.bits,x);
    row.proof[id>>6] |= uint64_t(1)<<(id&63);
    for(;;){
      int p=lowest(row.bits);
      if(p==0){
        if(row.rhs){
          cout<<"c R29_ROUTE certified_xor_contradiction equations="
              <<eqs.size()<<" rank="<<rank<<" covered="<<covered
              <<" clauses="<<clauses.size()<<" resolved="
              <<rec.eliminated.size()<<"\n";
          r29_resolve_proof(rec.eliminated);
          print_equations(eqs);
          cout<<"c R28_UNSAT_CERT ids="<<r29_ids(row.proof,eqs.size())
              <<"\ns UNSATISFIABLE\n"<<flush;
          return classify?0:20;
        }
        break;
      }
      if(basis[p].valid)add(row,basis[p]);
      else{row.valid=true;basis[p]=move(row);rank++;break;}
    }
  }
  if(covered==int(clauses.size())) {
    if(r29_print_sat(original,rec.eliminated,basis,n,rank,eqs.size(),covered))
      return classify?0:10;
    return r29_fallback(filename,kissat,"pure_sat_witness_guard",
                        int(clauses.size()),covered,eqs.size(),
                        rec.eliminated.size(),classify);
  }
  // Derive unit consequences using GF(2) row reduction, not guessing from
  // incomplete CNF clause patterns. Every unit has an XOR-row certificate.
  for(int p=n;p>=1;p--)if(basis[p].valid){
    for(int q=p-1;q>=1;q--)if(basis[q].valid&&bit(basis[q].bits,p))
      add(basis[q],basis[p]);
  }
  set<int> original_units;
  for(const auto &cl:original)if(cl.size()==1)original_units.insert(cl[0]);
  vector<pair<int,vector<uint64_t>>> forced;
  for(int p=1;p<=n;p++)if(basis[p].valid) {
    unsigned pop=0;
    for(auto w:basis[p].bits)pop+=__builtin_popcountll(w);
    if(pop!=1)continue;
    int unit=basis[p].rhs?p:-p;
    if(!original_units.count(unit))forced.push_back({unit,basis[p].proof});
  }
  // Frozen risk gate: no external restarts, no phase changes. Only use
  // mathematically implied new unit clauses with substantial XOR support.
  const bool valuable=forced.size()>=4 && covered>=32 &&
         clauses.size()>=200 && int(clauses.size())<=150000;
  if(valuable && !shadow)
    return r29_inject_units(filename,kissat,original,n,forced,eqs,
                            rec.eliminated,classify);
  return r29_fallback(filename,kissat,
                      valuable?"shadow_certified_units":"no_validated_action",
                      int(clauses.size()),covered,eqs.size(),
                      rec.eliminated.size(),classify);
}

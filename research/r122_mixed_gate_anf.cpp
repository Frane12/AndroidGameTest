// DRNAS R122: conservative AND/OR/XOR gate-miter decoder, Boolean ANF GF(2).
// Never infer from partial gates: EXACT source clause partition is mandatory.
// Proof: identical canonical ANFs imply universally identical outputs.
// SAT: produce and check full original-source counterexample assignment.
// Unknown forms -> unmodified pinned Kissat; V15.3.1 never touched.
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_set>
#include <vector>
#include <unistd.h>
using namespace std;
using Clause=vector<int>;
using Poly=vector<uint64_t>;
struct Gate{int z,a,b;char op;};
static int fallback(const string&file,const string&solver,const string&why){
  cout<<"c R122_ROUTE fallback reason="<<why<<"\n"<<flush;
  char*args[]={const_cast<char*>(solver.c_str()),const_cast<char*>(file.c_str()),nullptr};
  execv(args[0],args);cerr<<"R122_EXEC_ERROR "<<strerror(errno)<<"\n";return 78;
}
static Clause ordered(Clause x){sort(x.begin(),x.end());return x;}
static bool read_dimacs(const string&path,int&n,vector<Clause>&clauses){
  ifstream f(path,ios::binary);if(!f)return false;
  f.seekg(0,ios::end);auto bytes=f.tellg();
  if(bytes<0||bytes>8*1024*1024)return false;
  f.seekg(0);string tok;int declared=-1;bool header=false;Clause current;
  while(f>>tok){
    if(tok=="c"||tok=="%"){string rest;getline(f,rest);continue;}
    if(tok=="p"){
      string fmt;
      if(header||!(f>>fmt>>n>>declared)||fmt!="cnf"||n<2||n>20000||declared<2||declared>500000)return false;
      header=true;continue;
    }
    if(!header)return false;
    char*end=nullptr;errno=0;long lit=strtol(tok.c_str(),&end,10);
    if(errno||!end||*end||lit<-n||lit>n)return false;
    if(!lit){
      if(current.empty())return false;
      clauses.push_back(ordered(current));current.clear();
      if(int(clauses.size())>declared)return false;
    }else{
      current.push_back(int(lit));
      if(current.size()>6)return false;
    }
  }
  return header&&current.empty()&&int(clauses.size())==declared;
}
static vector<Clause> gate_clauses(Gate g){
  int a=g.a,b=g.b,z=g.z;
  if(g.op=='X')return {ordered({a,b,-z}),ordered({a,-b,z}),ordered({-a,b,z}),ordered({-a,-b,-z})};
  if(g.op=='A')return {ordered({-a,-b,z}),ordered({a,-z}),ordered({b,-z})};
  if(g.op=='O')return {ordered({-a,z}),ordered({-b,z}),ordered({a,b,-z})};
  return {};
}
static bool reconstruct(const vector<Clause>&clauses,int n,vector<Gate>&gates,int&outa,int&outb,int&nin){
  set<Clause>source(clauses.begin(),clauses.end());
  if(source.size()!=clauses.size())return false;
  set<tuple<int,int,int>>candidates;
  for(const Clause&c:clauses)if(c.size()==3){
    vector<int>v={abs(c[0]),abs(c[1]),abs(c[2])};
    sort(v.begin(),v.end());
    if(v[0]==v[1]||v[1]==v[2])continue;
    candidates.insert(make_tuple(v[2],v[0],v[1]));
  }
  map<int,Gate>detected;
  for(const auto&candidate:candidates){
    int z,a,b;tie(z,a,b)=candidate;
    for(char op:{'X','A','O'}){
      Gate g{z,a,b,op};auto req=gate_clauses(g);
      bool valid=all_of(req.begin(),req.end(),[&](const Clause&x){return source.count(x)>0;});
      if(valid){
        if(detected.count(z))return false;
        detected[z]=g;
      }
    }
  }
  if(detected.size()<2)return false;
  set<Clause>covered;
  for(const auto&entry:detected){
    gates.push_back(entry.second);
    for(const auto&c:gate_clauses(entry.second))
      if(!covered.insert(c).second)return false;
  }
  int miters=0;
  for(const Clause&c:clauses)if(c.size()==2&&c[0]>0&&c[1]>0&&c[0]!=c[1]){
    if(detected.count(c[0])&&detected.count(c[1])&&source.count(ordered({-c[0],-c[1]}))){
      ++miters;outa=c[0];outb=c[1];
    }
  }
  if(miters!=1)return false;
  covered.insert(ordered({outa,outb}));covered.insert(ordered({-outa,-outb}));
  if(covered!=source)return false;
  nin=n-int(gates.size());
  return nin>=1&&nin<=20;
}
static Poly xor_poly(const Poly&a,const Poly&b){
  Poly result;result.reserve(a.size()+b.size());
  set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),back_inserter(result));
  return result;
}
static bool and_poly(const Poly&a,const Poly&b,Poly&out,unsigned long long&ops){
  if(a.empty()||b.empty()){out.clear();return true;}
  if(a.size()>20000/b.size()||ops+a.size()*b.size()>100000)return false;
  ops+=a.size()*b.size();
  unordered_set<uint64_t>terms;
  for(uint64_t x:a)for(uint64_t y:b){
    uint64_t mask=x|y;auto it=terms.find(mask);
    if(it==terms.end())terms.insert(mask);else terms.erase(it);
  }
  out.assign(terms.begin(),terms.end());sort(out.begin(),out.end());
  return true;
}
static bool check_original(const vector<Clause>&clauses,const vector<bool>&v){
  for(const Clause&c:clauses){
    bool satisfied=false;
    for(int lit:c)if(v[abs(lit)]==(lit>0)){satisfied=true;break;}
    if(!satisfied)return false;
  }
  return true;
}
int main(int argc,char**argv){
  if(argc!=3){cerr<<"usage: r122 SOURCE.cnf KISSAT\n";return 2;}
  string filename=argv[1],kissat=argv[2];int n=0;vector<Clause>clauses;
  if(!read_dimacs(filename,n,clauses))return fallback(filename,kissat,"parse_or_limits");
  vector<Gate>gates;int outa=0,outb=0,nin=0;
  if(!reconstruct(clauses,n,gates,outa,outb,nin))
    return fallback(filename,kissat,"unrecognized_source_gate_miter");
  vector<bool>isgate(n+1,false),known(n+1,false);
  for(const Gate&g:gates)isgate[g.z]=true;
  vector<int>input_index(n+1,-1);int count=0;
  vector<Poly>expression(n+1);
  for(int i=1;i<=n;i++)if(!isgate[i]){
    input_index[i]=count;expression[i]={uint64_t(1)<<count};
    ++count;known[i]=true;
  }
  if(count!=nin)return fallback(filename,kissat,"input_invariant");
  unsigned long long ops=0;
  for(const Gate&g:gates){
    if(!known[g.a]||!known[g.b])return fallback(filename,kissat,"non_topological_gate");
    if(g.op=='X')expression[g.z]=xor_poly(expression[g.a],expression[g.b]);
    else{
      Poly product;
      if(!and_poly(expression[g.a],expression[g.b],product,ops))
        return fallback(filename,kissat,"bounded_anf_budget");
      expression[g.z]=(g.op=='A'?product:xor_poly(xor_poly(expression[g.a],expression[g.b]),product));
    }
    if(expression[g.z].size()>8192)return fallback(filename,kissat,"anf_term_cap");
    known[g.z]=true;
  }
  if(!known[outa]||!known[outb])return fallback(filename,kissat,"incomplete_outputs");
  Poly mismatch=xor_poly(expression[outa],expression[outb]);
  if(mismatch.empty()){
    cout<<"c R122_ROUTE certified_gate_anf_equivalent inputs="<<nin
        <<" gates="<<gates.size()<<" monomials=0\n";
    cout<<"s UNSATISFIABLE\n"<<flush;
    return 20;
  }
  // A minimum-degree monomial gives a guaranteed nonzero Boolean ANF witness.
  uint64_t witness=mismatch[0];
  for(uint64_t term:mismatch)
    if(__builtin_popcountll(term)<__builtin_popcountll(witness))witness=term;
  vector<bool>truth(n+1,false);
  for(int i=1;i<=n;i++)if(!isgate[i])
    truth[i]=!!(witness&(uint64_t(1)<<input_index[i]));
  for(const Gate&g:gates){
    bool a=truth[g.a],b=truth[g.b];
    truth[g.z]=(g.op=='X'?a!=b:g.op=='A'?a&&b:a||b);
  }
  if(!check_original(clauses,truth))
    return fallback(filename,kissat,"full_source_model_rejected");
  cout<<"c R122_ROUTE certified_gate_anf_counterexample inputs="<<nin
      <<" gates="<<gates.size()<<" monomials="<<mismatch.size()<<"\n";
  cout<<"s SATISFIABLE\n";
  for(int i=1;i<=n;i++){
    if((i-1)%20==0)cout<<"v ";
    cout<<(truth[i]?i:-i)<<" ";
    if(i%20==0)cout<<"0\n";
  }
  if(n%20!=0)cout<<"0\n";
  cout<<flush;
  return 10;
}

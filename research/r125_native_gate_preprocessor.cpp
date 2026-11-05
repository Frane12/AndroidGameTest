// DRNAS R125: conservative partial Tseitin gate detection and sound binary
// equivalences (common subexpression) from COMPLETE source gate clause blocks.
// No Kissat source modifications. Only exact local 2- and 3-CNF gate patterns
// can imply new equivalence clauses. Every equivalence is externally audited.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <cmath>
using namespace std;
using Clock=chrono::steady_clock;
struct Key{
 int a,b,c;
 bool operator==(const Key&x)const{return a==x.a&&b==x.b&&c==x.c;}
};
struct Hasher{
 size_t operator()(const Key&x)const{
  uint64_t z=uint32_t(x.a)*0x9e3779b185ebca87ULL;
  z^=uint32_t(x.b)*0xc2b2ae3d27d4eb4fULL;
  z^=uint32_t(x.c)*0x165667b19e3779f9ULL;
  return size_t(z^(z>>32));
 }
};
static Key make_key(vector<int> a){
 sort(a.begin(),a.end());
 if(a.size()==2)return {a[0],a[1],0};
 if(a.size()==3)return {a[0],a[1],a[2]};
 return {0,0,0};
}
static vector<Key> gate_clauses(char op,int a,int b,int z){
 if(op=='X')return {make_key({a,b,-z}),make_key({a,-b,z}),
                       make_key({-a,b,z}),make_key({-a,-b,-z})};
 if(op=='A')return {make_key({-a,-b,z}),make_key({a,-z}),make_key({b,-z})};
 return {make_key({a,b,-z}),make_key({-a,z}),make_key({-b,z})};
}
struct Gate{char op;int a,b,z;int norm;string signature;};
static Gate normalized(char op,int a,int b,int z){
 Gate g{op,a,b,z,z,""};
 if(op=='X'){
  const int x=min(abs(a),abs(b)),y=max(abs(a),abs(b));
  const bool negative=(a<0)^(b<0)^(z<0);
  g.norm=(negative?-1:1)*abs(z);
  g.signature="X:"+to_string(x)+":"+to_string(y);
 }else{
  if(op=='O'){a=-a;b=-b;g.norm=-z;}
  if(a>b)swap(a,b);
  g.signature="A:"+to_string(a)+":"+to_string(b);
 }
 return g;
}
static bool full_gate_semantics(const Gate&g,const vector<Key>&expected){
 if(abs(g.a)==abs(g.b)||abs(g.a)==abs(g.z)||abs(g.b)==abs(g.z))return false;
 int v[3]={abs(g.a),abs(g.b),abs(g.z)};
 sort(v,v+3);
 for(int mask=0;mask<8;mask++){
  auto literal=[&](int lit)->bool{
   int idx=int(lower_bound(v,v+3,abs(lit))-v);
   return ((mask>>idx)&1)!=(lit<0);
  };
  bool lhs=literal(g.a),rhs=literal(g.b),out=literal(g.z);
  bool wanted=(g.op=='X'?lhs!=rhs:g.op=='A'?lhs&&rhs:lhs||rhs);
  bool satisfies=true;
  for(const Key&c:expected){
   if(!(literal(c.a)||literal(c.b)||(c.c!=0&&literal(c.c))))satisfies=false;
  }
  if(satisfies!=(out==wanted))return false;
 }
 return true;
}
struct Problem{
 int vars=0,declared=0;
 vector<vector<int>> clauses;
 unordered_set<Key,Hasher> present;
 vector<array<int,3>> triples;
 string error;
};
static bool load(const string&path,Problem&problem){
 ifstream f(path,ios::binary);
 if(!f){problem.error="unreadable";return false;}
 f.seekg(0,ios::end);
 auto size=f.tellg();
 if(size<0||size>8*1024*1024){problem.error="bytes_gt_8MiB";return false;}
 f.seekg(0);
 string line;vector<int>current;bool header=false;
 while(getline(f,line)){
  if(line.empty())continue;
  istringstream ss(line);string token;ss>>token;
  if(token=="c"||token=="%")continue;
  if(token=="p"){
   string cnf;int vars=0,m=0;
   if(header||!(ss>>cnf>>vars>>m)||cnf!="cnf"||vars<=0||m<0||m>500000){
    problem.error="invalid_header";return false;
   }
   problem.vars=vars;problem.declared=m;header=true;continue;
  }
  if(!header){problem.error="no_header";return false;}
  // Restore the token (first literal) and process the rest of its line.
  ss.clear();ss.str(line);
  int lit=0;
  while(ss>>lit){
   if(lit!=0){
    if(abs((long long)lit)>problem.vars){problem.error="bad_literal";return false;}
    current.push_back(lit);
    if(current.size()>100000){problem.error="clause_width_guard";return false;}
   }else{
    problem.clauses.push_back(current);
    if(problem.clauses.size()>size_t(problem.declared)){
     problem.error="too_many_clauses";return false;
    }
    if(current.size()==2||current.size()==3){
     set<int>vars;for(int x:current)vars.insert(abs(x));
     if(vars.size()==current.size()){
      Key key=make_key(current);problem.present.insert(key);
      if(current.size()==3)problem.triples.push_back({*vars.begin(),
        *next(vars.begin()),*next(vars.begin(),2)});
     }
    }
    current.clear();
   }
  }
  if(!ss.eof()){problem.error="invalid_token";return false;}
 }
 if(!header||!current.empty()||problem.clauses.size()!=size_t(problem.declared)){
  problem.error="incomplete_dimacs";return false;
 }
 sort(problem.triples.begin(),problem.triples.end());
 problem.triples.erase(unique(problem.triples.begin(),problem.triples.end()),problem.triples.end());
 return true;
}
static bool source_contains(const Problem&p,const vector<Key>&clauses){
 for(const Key&k:clauses)if(!p.present.count(k))return false;
 return true;
}
static double elapsed_ms(Clock::time_point start){
 return chrono::duration<double,milli>(Clock::now()-start).count();
}
static void print_result(const string&status,const Problem&p,size_t inspected,
     size_t detected,size_t pairs,bool limited,double ms){
 cout<<"R125_SUMMARY {\"status\":\""<<status<<"\",\"variables\":"<<p.vars
     <<",\"clauses\":"<<p.declared<<",\"candidate_triplets\":"<<p.triples.size()
     <<",\"inspected_triplets\":"<<inspected<<",\"verified_gate_candidates\":"<<detected
     <<",\"equivalence_pairs\":"<<pairs<<",\"new_binary_clauses\":"<<(2*pairs)
     <<",\"budget_limited\":"<<(limited?"true":"false")
     <<",\"native_ms\":"<<ms<<"}\n"<<flush;
}
int main(int argc,char**argv){
 if(argc!=4){cerr<<"usage: r125_native INPUT.cnf OUT.cnf|- PROOF.tsv|-\n";return 2;}
 auto start=Clock::now();
 string input=argv[1],out=argv[2],proof=argv[3];
 Problem p;
 if(!load(input,p)){
  cerr<<"R125_GUARD "<<p.error<<"\n";
  print_result("guard",p,0,0,0,false,elapsed_ms(start));
  return 0;
 }
 vector<Gate>all;
 const size_t max_triples=12000,max_gates=30000,max_pairs=128;
 const double budget_ms=400.0;
 bool limited=false;size_t inspected=0;
 for(const auto&v:p.triples){
  if(inspected>=max_triples||all.size()>=max_gates||elapsed_ms(start)>budget_ms){
   limited=true;break;
  }
  inspected++;
  for(int iz=0;iz<3;iz++){
   int zvar=v[iz];vector<int>inputs;
   for(int i=0;i<3;i++)if(i!=iz)inputs.push_back(v[i]);
   for(int mask=0;mask<8;mask++){
    int a=inputs[0]*((mask&1)?-1:1);
    int b=inputs[1]*((mask&2)?-1:1);
    int z=zvar*((mask&4)?-1:1);
    for(char op:{'X','A','O'}){
     vector<Key>clauses=gate_clauses(op,a,b,z);
     if(!source_contains(p,clauses))continue;
     Gate g=normalized(op,a,b,z);
     if(!full_gate_semantics(g,clauses)){
      cerr<<"R125_INTERNAL_GATE_PROOF_FAILURE\n";return 75;
     }
     all.push_back(g);
    }
   }
  }
 }
 map<string,vector<Gate>> groups;
 for(const Gate&g:all)groups[g.signature].push_back(g);
 struct Pair{Gate a,b;int u,v;};
 vector<Pair>edges;set<pair<int,int>>dedup;
 for(const auto&entry:groups){
  const auto&group=entry.second;
  if(group.size()<2)continue;
  for(size_t i=1;i<group.size();i++){
   const Gate&g=group[0],&h=group[i];
   if(abs(g.norm)==abs(h.norm))continue;
   pair<int,int>key=minmax(g.norm,h.norm);
   if(!dedup.insert(key).second)continue;
   edges.push_back({g,h,g.norm,h.norm});
   if(edges.size()>=max_pairs){limited=true;break;}
  }
  if(edges.size()>=max_pairs)break;
 }
 if(out!="-"){
  if(proof=="-"){cerr<<"proof path required for source augmentation\n";return 2;}
  ofstream audit(proof);
  if(!audit){cerr<<"cannot open proof output\n";return 2;}
  audit<<"op1\ta1\tb1\tz1\top2\ta2\tb2\tz2\tq1\tq2\n";
  for(const auto&e:edges)
   audit<<e.a.op<<"\t"<<e.a.a<<"\t"<<e.a.b<<"\t"<<e.a.z<<"\t"
      <<e.b.op<<"\t"<<e.b.a<<"\t"<<e.b.b<<"\t"<<e.b.z<<"\t"
      <<e.u<<"\t"<<e.v<<"\n";
  audit.close();
  if(!edges.empty()){
   ofstream file(out);
   if(!file){cerr<<"cannot create augmented CNF\n";return 2;}
   file<<"c DRNAS R125: original clauses preserved, derived output equivalences only\n";
   file<<"p cnf "<<p.vars<<" "<<(p.clauses.size()+2*edges.size())<<"\n";
   for(const auto&cl:p.clauses){
    for(int literal:cl)file<<literal<<" ";
    file<<"0\n";
   }
   for(const auto&e:edges){
    file<<-e.u<<" "<<e.v<<" 0\n";
    file<<e.u<<" "<<-e.v<<" 0\n";
   }
   if(!file.good()){cerr<<"failed writing augmented CNF\n";return 2;}
  }
 }
 print_result("ok",p,inspected,all.size(),edges.size(),limited,elapsed_ms(start));
 return 0;
}

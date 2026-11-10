// COMBO6 native, deterministic and bounded source-CNF UP novelty probe.
// This tests preprocessing implications under short assumptions, NOT the live CMS trail.
// Never asserts SAT/UNSAT; no relation is allowed unless upstream original-CNF GF2 proof replay passed.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using namespace std;
using Clause=vector<int>;
static constexpr long long MAX_VISITS=1200000;
static constexpr size_t MAX_CLAUSES=40000, MAX_LITERALS=220000;
static constexpr int MAX_PROBES=12;
struct Result {bool conflict=false, budget=false;vector<int8_t> values;};
Result propagate(const vector<Clause>& clauses, int n, const vector<int>& assumptions,long long& visits){
  Result out;out.values.assign(n+1,-1);
  for(int lit:assumptions){int v=abs(lit);if(v<1||v>n){out.budget=true;return out;}
    int b=lit>0?1:0;
    if(out.values[v]!=-1 && out.values[v]!=b){out.conflict=true;return out;}
    out.values[v]=b;
  }
  bool changed=true;
  while(changed){changed=false;
    for(const auto& cl:clauses){
      if((visits+=cl.size()+1)>MAX_VISITS){out.budget=true;return out;}
      bool satisfied=false;int unknown=0,last=0;
      for(int lit:cl){int8_t b=out.values[abs(lit)];
        if(b<0){unknown++;last=lit;}else if((lit>0)==(b==1)){satisfied=true;break;}
      }
      if(satisfied)continue;
      if(!unknown){out.conflict=true;return out;}
      if(unknown==1){int v=abs(last),b=last>0?1:0;
        if(out.values[v]==-1){out.values[v]=b;changed=true;}
        else if(out.values[v]!=b){out.conflict=true;return out;}
      }
    }
  }
  return out;
}
int main(int argc,char**argv){
  if(argc!=3){cerr<<"usage: combo6-probe original.cnf relations.txt\n";return 2;}
  ifstream in(argv[1]);if(!in){cerr<<"missing cnf\n";return 2;}
  int n=0, declared=0;vector<Clause> base;size_t lits=0;string line;
  while(getline(in,line)){
    if(line.empty()||line[0]=='c')continue;
    if(line[0]=='p'){istringstream z(line);string p,cnf;
      if(!(z>>p>>cnf>>n>>declared)||cnf!="cnf"||n<1||n>2000000||declared<1){cerr<<"bad header\n";return 2;}
      continue;
    }
    if(n<1){cerr<<"missing header\n";return 2;}
    istringstream z(line);int lit;Clause clause;
    while(z>>lit){if(!lit){if(!clause.empty()){lits+=clause.size();base.push_back(clause);clause.clear();}continue;}
      if(abs(lit)>n){cerr<<"bad literal\n";return 2;}
      clause.push_back(lit);
    }
    if(!clause.empty()){cerr<<"multiline clauses unsupported, abstain\n";return 2;}
    if(base.size()>MAX_CLAUSES || lits>MAX_LITERALS){
      cout<<"COMBO6_PROBE {\"reason\":\"cnf_too_large\",\"probes\":0,\"new_units\":0,\"new_conflicts\":0,\"useful_probes\":0,\"budget_exceeded\":true}\n";
      return 0;
    }
  }
  if((int)base.size()!=declared){cerr<<"clause count mismatch\n";return 2;}
  ifstream relfile(argv[2]);if(!relfile){cerr<<"missing candidate file\n";return 2;}
  vector<pair<vector<int>,int>> relations;
  while(getline(relfile,line)){
    if(line.empty())continue;
    istringstream z(line);int rhs,lit; if(!(z>>rhs)||(rhs!=0&&rhs!=1)){cerr<<"bad rhs\n";return 2;}
    vector<int> vs;bool zero=false;
    while(z>>lit){if(lit==0){zero=true;break;}if(lit<1||lit>n){cerr<<"bad relation var\n";return 2;}vs.push_back(lit);}
    if(!zero || vs.size()<2 || vs.size()>3 || adjacent_find(vs.begin(),vs.end())!=vs.end()){cerr<<"bad relation\n";return 2;}
    relations.emplace_back(vs,rhs);
    if(relations.size()>8){cerr<<"too many relations\n";return 2;}
  }
  long long visits=0;int probes=0,useful=0,new_units=0,new_conflicts=0;bool budget=false;
  for(const auto& [vs,rhs]:relations){
    // Evaluate each candidate independently: avoid crediting other derived relations.
    vector<Clause> test=base;
    int k=vs.size(), combinations=1<<k;
    for(int mask=0;mask<combinations;mask++){
      if((__builtin_popcount((unsigned)mask)&1)==rhs)continue;
      Clause cl;for(int i=0;i<k;i++)cl.push_back((mask&(1<<i))?-vs[i]:vs[i]);
      test.push_back(cl);
    }
    for(int mask=0;mask<(1<<(k-1));mask++){
      if(probes>=MAX_PROBES)break;
      vector<int> assumptions;
      for(int i=0;i<k-1;i++)assumptions.push_back((mask&(1<<i))?vs[i]:-vs[i]);
      auto a=propagate(base,n,assumptions,visits);
      if(a.budget){budget=true;break;}
      auto b=propagate(test,n,assumptions,visits);
      if(b.budget){budget=true;break;}
      probes++;
      if(a.conflict)continue;
      if(b.conflict){new_conflicts++;useful++;continue;}
      int changed=0;
      for(int v=1;v<=n;v++)if(a.values[v]<0 && b.values[v]>=0)changed++;
      if(changed){new_units+=changed;useful++;}
    }
    if(budget || probes>=MAX_PROBES)break;
  }
  cout<<"COMBO6_PROBE {\"reason\":\""<<(budget?"operation_bound":"ok")<<"\",\"probes\":"<<probes
      <<",\"new_units\":"<<new_units<<",\"new_conflicts\":"<<new_conflicts
      <<",\"useful_probes\":"<<useful<<",\"budget_exceeded\":"<<(budget?"true":"false")
      <<",\"clause_visits\":"<<visits<<"}\n";
  return 0;
}

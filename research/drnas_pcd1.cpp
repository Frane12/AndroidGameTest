// DRNAS PCD1: bounded parallel conflict discovery; diagnostics only.
// No CNF mutation, no UNSAT certification, no learned-clause injection.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <future>
#include <iostream>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using namespace std;
struct CNF { int vars=0; vector<vector<int>> clauses; };
static CNF parse(const string& path){
  ifstream f(path); if(!f) throw runtime_error("cannot open CNF");
  CNF c; string line; vector<int> clause; bool header=false;
  while(getline(f,line)){
    if(line.empty()||line[0]=='c'||line[0]=='%')continue;
    if(line[0]=='p'){
      istringstream s(line); string p,kind;int count;
      if(!(s>>p>>kind>>c.vars>>count)||kind!="cnf"||c.vars<0||count<0)
        throw runtime_error("bad DIMACS header");
      header=true;continue;
    }
    istringstream s(line);int lit;
    while(s>>lit){
      if(lit==0){c.clauses.push_back(clause);clause.clear();}
      else {if(!header||abs(lit)>c.vars)throw runtime_error("bad literal");clause.push_back(lit);}
    }
  }
  if(!header||!clause.empty())throw runtime_error("incomplete CNF");
  return c;
}
struct Probe {
  bool conflict=false;
  vector<int8_t> value;
  vector<int> reason;
  vector<int> trail;
  uint64_t scans=0;
};
static Probe propagate(const CNF& cnf,int assumed,int scan_budget){
  Probe p; p.value.assign(cnf.vars+1,0);p.reason.assign(cnf.vars+1,-1);
  if(assumed){
    p.value[abs(assumed)]=assumed>0?1:-1;
    p.trail.push_back(assumed);
  }
  bool progress=true;
  while(progress&&!p.conflict){
    progress=false;
    for(size_t i=0;i<cnf.clauses.size();++i){
      if(p.scans++>=uint64_t(scan_budget))return p; // inconclusive, never claim conflict
      const auto& cl=cnf.clauses[i];bool sat=false;int open=0,last=0;
      for(int lit:cl){
        int v=p.value[abs(lit)];
        if(v==0){++open;last=lit;}
        else if((lit>0&&v==1)||(lit<0&&v==-1)){sat=true;break;}
      }
      if(sat)continue;
      if(open==0){p.conflict=true;return p;}
      if(open==1){
        int v=abs(last), val=last>0?1:-1;
        if(p.value[v]!=0&&p.value[v]!=val){p.conflict=true;return p;}
        if(p.value[v]==0){
          p.value[v]=val;p.reason[v]=int(i);p.trail.push_back(last);progress=true;
        }
      }
    }
  }
  return p;
}
// Traverse implication ancestors by independent layers. This is NOT a
// replacement for 1-UIP resolution, which stays in the trusted CDCL core.
static vector<int> ancestors(const CNF& c,const Probe& p,vector<int> seeds,bool parallel){
  vector<uint8_t> seen(c.vars+1,0);
  vector<int> frontier;
  for(int v:seeds)if(v>0&&v<=c.vars&&!seen[v]){seen[v]=1;frontier.push_back(v);}
  while(!frontier.empty()){
    auto parents=[&](size_t from,size_t to){
      vector<int> out;
      for(size_t i=from;i<to;++i){
        int v=frontier[i],r=p.reason[v];
        if(r<0)continue;
        for(int lit:c.clauses[size_t(r)]){
          int w=abs(lit);
          if(w!=v&&p.value[w]!=0)out.push_back(w);
        }
      }
      return out;
    };
    vector<int> next;
    if(parallel&&frontier.size()>=2){
      size_t mid=frontier.size()/2;
      auto fut=async(launch::async,parents,0,mid);
      next=parents(mid,frontier.size());
      auto left=fut.get();next.insert(next.end(),left.begin(),left.end());
    } else next=parents(0,frontier.size());
    sort(next.begin(),next.end());next.erase(unique(next.begin(),next.end()),next.end());
    frontier.clear();
    for(int v:next)if(!seen[v]){seen[v]=1;frontier.push_back(v);}
  }
  vector<int> out;for(int v=1;v<=c.vars;++v)if(seen[v])out.push_back(v);
  return out;
}
struct Report {int probes=0,failed=0,forced=0,unknown=0,graph_checks=0;uint64_t scans=0;vector<int> units;};
static Report run(const CNF& c,int workers,int maxvars,int budget,bool test=false){
  Report result; vector<int> forced;
  // Fixed batch, read-only CNF, no shared assignments or solver trail.
  for(int start=1;start<=min(c.vars,maxvars);start+=workers){
    vector<future<pair<Probe,Probe>>> futures;
    for(int v=start;v<min(start+workers,min(c.vars,maxvars)+1);++v){
      futures.push_back(async(launch::async,[&,v]{
        return make_pair(propagate(c,v,budget),propagate(c,-v,budget));
      }));
    }
    for(size_t i=0;i<futures.size();++i){
      int v=start+int(i);auto both=futures[i].get();
      Probe& positive=both.first;Probe& negative=both.second;
      result.probes+=2;result.scans+=positive.scans+negative.scans;
      if(positive.conflict)++result.failed;
      if(negative.conflict)++result.failed;
      if(positive.conflict&&!negative.conflict){forced.push_back(-v);++result.forced;}
      if(negative.conflict&&!positive.conflict){forced.push_back(v);++result.forced;}
      if(!positive.conflict&&!negative.conflict)++result.unknown;
      // Parallel and serial implication graph traversals must agree exactly.
      // This graph is a diagnostic snapshot; never assert it is a 1-UIP proof.
      for(const Probe* p:{&positive,&negative}){
        if(p->trail.size()<2)continue;
        vector<int> seeds;
        for(size_t j=1;j<p->trail.size();++j)seeds.push_back(abs(p->trail[j]));
        auto a=ancestors(c,*p,seeds,false),b=ancestors(c,*p,seeds,true);
        if(a!=b)throw runtime_error("parallel reason graph mismatch");
        ++result.graph_checks;
      }
    }
  }
  // Derivation check: every reported unit is supported by a conflict
  // under the opposite assumption; never produce units from mere timeout.
  for(int lit:forced){
    Probe check=propagate(c,-lit,budget);
    if(!check.conflict)throw runtime_error("failed literal not reproducible");
  }
  result.units=forced;
  if(test&&result.forced==0)throw runtime_error("expected forced literal absent");
  return result;
}
int main(int argc,char** argv){
 try{
  if(argc==2&&string(argv[1])=="--selftest"){
    CNF c{4,{{1,2},{1,-2},{-1,3},{-3,4}}};
    auto r=run(c,2,4,10000,true);
    if(r.graph_checks==0)throw runtime_error("graph path not exercised");
    cout<<"PCD1_SELFTEST_PASS probes="<<r.probes<<" forced="<<r.forced
        <<" reason_graph_checks="<<r.graph_checks<<"\n";
    return 0;
  }
  if(argc<2||argc>6)throw runtime_error("usage: pcd1 CNF [workers=2] [vars=16] [scan_budget=200000] [units_file]");
  CNF c=parse(argv[1]);
  int workers=argc>2?stoi(argv[2]):2,vars=argc>3?stoi(argv[3]):16;
  int budget=argc>4?stoi(argv[4]):200000;
  if(workers<1||workers>8||vars<0||budget<1)throw runtime_error("invalid limits");
  auto a=chrono::steady_clock::now();
  auto r=run(c,workers,vars,budget);
  double ms=chrono::duration<double,milli>(chrono::steady_clock::now()-a).count();
  if(argc==6){ofstream out(argv[5]);if(!out)throw runtime_error("cannot write units");
    for(int lit:r.units)out<<lit<<" 0\n";}
  cout<<"PCD1_DIAGNOSTIC vars="<<c.vars<<" clauses="<<c.clauses.size()
      <<" threads="<<workers<<" probes="<<r.probes<<" failed_assumptions="<<r.failed
      <<" forced_candidates="<<r.forced<<" no_conflict_pairs="<<r.unknown
      <<" graph_parity_checks="<<r.graph_checks<<" scans="<<r.scans
      <<" wall_ms="<<ms<<" solver_status=UNKNOWN certified_UNSAT=0"
      <<" original_CNF_unchanged=1 mode=shadow\n";
  return 0;
 }catch(const exception& e){cerr<<"PCD1_ERROR "<<e.what()<<"\n";return 2;}
}

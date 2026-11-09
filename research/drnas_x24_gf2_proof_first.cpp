// DRNAS X24: candidate GF(2) derivations ONLY. Never edits CNF.
// Source clause IDs and XOR-combination IDs are independently replayed in Python.
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using namespace std;
struct Eq {
  vector<int> vars;
  int rhs=0;
  vector<int> proof;
};
static vector<int> sxor(const vector<int>& a,const vector<int>& b) {
  vector<int> o;
  set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),back_inserter(o));
  return o;
}
static void add(Eq& a,const Eq& b) {
  a.vars=sxor(a.vars,b.vars);
  a.proof=sxor(a.proof,b.proof);
  a.rhs^=b.rhs;
}
static int parity(int m) {
  int x=0;while(m){x^=1;m&=m-1;}return x;
}
static void write(const char* kind,const Eq& e,ostream& out){
  out<<kind<<" "<<e.rhs<<" "<<e.vars.size();
  for(int v:e.vars)out<<" "<<v;
  out<<" |";
  for(int p:e.proof)out<<" "<<p;
  out<<"\n";
}
int main(int argc,char** argv) {
  if(argc!=3){cerr<<"usage: drnas_x24_gf2 SOURCE.cnf OUTPUT.cert\n";return 2;}
  ifstream in(argv[1]);if(!in){cerr<<"source unreadable\n";return 2;}
  ofstream out(argv[2],ios::trunc);if(!out){cerr<<"certificate unwritable\n";return 2;}
  out<<"GF2V1\n";
  // A complete parity half-cube of k=2,3,4 clauses certifies an XOR equation.
  // Each clause index points into the ORIGINAL DIMACS; missing patterns do not count.
  map<vector<int>,map<int,int>> blocks;
  string line;vector<int> pending;int index=0,limit=120000,nvars=0;
  bool header=false;
  while(index<limit && getline(in,line)){
    if(line.empty() || line[0]=='c' || line[0]=='%')continue;
    if(line[0]=='p'){
      istringstream h(line);string p,fmt;int declared=0;
      if(!(h>>p>>fmt>>nvars>>declared) || fmt!="cnf" || nvars<0)
        return 3;
      header=true;continue;
    }
    if(!header)return 3;
    istringstream ss(line);string field;
    while(ss>>field && index<limit) {
      int lit=0;
      try{size_t pos=0;lit=stoi(field,&pos);if(pos!=field.size())return 3;}
      catch(...){return 3;}
      if(lit!=0){
        if(lit==-2147483647-1 || abs(lit)>nvars)return 3;
        pending.push_back(lit);
        if(pending.size()>2048)return 3;
        continue;
      }
      if(pending.size()>=2 && pending.size()<=4) {
        vector<int> key;for(int v:pending)key.push_back(abs(v));
        sort(key.begin(),key.end());
        if(adjacent_find(key.begin(),key.end())==key.end()){
          int mask=0;
          for(int v:pending){
            auto p=lower_bound(key.begin(),key.end(),abs(v))-key.begin();
            if(v<0)mask|=(1<<p);
          }
          if(blocks.size()<55000 || blocks.count(key))blocks[key].emplace(mask,index);
        }
      }
      pending.clear();++index;
    }
  }
  vector<Eq> equations;
  for(const auto& group:blocks) {
    int k=(int)group.first.size(),half=1<<(k-1);
    for(int forbidden=0;forbidden<2;forbidden++){
      vector<int> source;
      for(int mask=0;mask<(1<<k);mask++)if(parity(mask)==forbidden) {
        auto it=group.second.find(mask);
        if(it!=group.second.end())source.push_back(it->second);
      }
      if((int)source.size()!=half)continue;
      Eq e;e.vars=group.first;e.rhs=1-forbidden;
      sort(source.begin(),source.end());e.proof=source;
      equations.push_back(e);
      if(equations.size()>=256)break;
    }
    if(equations.size()>=256)break;
  }
  for(const Eq& e:equations)write("E",e,out);
  map<int,Eq> basis;
  for(size_t i=0;i<equations.size();i++) {
    Eq row=equations[i];row.proof={int(i)};
    for(;;){
      if(row.vars.empty())break;
      int pivot=row.vars.front();auto it=basis.find(pivot);
      if(it==basis.end()){
        if(row.vars.size()<=256 && row.proof.size()<=256)
          basis.emplace(pivot,move(row));
        break;
      }
      add(row,it->second);
      if(row.vars.size()>256 || row.proof.size()>256)break;
    }
    // A zero row with RHS=1 is an independently replayable contradiction.
    if(row.vars.empty() && row.rhs && row.proof.size()<=256)
      basis[0]=row;
  }
  // Reduced echelon form may reveal units or two-variable equalities.
  for(auto rit=basis.rbegin();rit!=basis.rend();++rit){
    int pivot=rit->first;if(pivot<=0)continue;
    for(auto it=basis.begin();it!=basis.end() && it->first<pivot;it++){
      if(it->first==0)continue;
      if(binary_search(it->second.vars.begin(),it->second.vars.end(),pivot)){
        Eq tmp=it->second;add(tmp,rit->second);
        if(tmp.vars.size()<=256 && tmp.proof.size()<=256)
          it->second=move(tmp);
      }
    }
  }
  set<string> observed;int derived=0;
  for(const auto& kv:basis){
    const Eq& row=kv.second;
    if(row.vars.size()>2 || (row.vars.empty() && !row.rhs))continue;
    if(row.proof.empty())continue;
    ostringstream signature;signature<<row.rhs<<":";
    for(int x:row.vars)signature<<x<<",";
    if(!observed.insert(signature.str()).second)continue;
    write("D",row,out);derived++;
    if(derived>=32)break;
  }
  out<<"END\n";
  cerr<<"X24_SCAN clauses_seen="<<index<<" complete_blocks="<<equations.size()
      <<" derived_short_rows="<<derived<<" capped="<<(index==limit)<<"\n";
  return 0;
}

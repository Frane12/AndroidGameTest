// DRNAS V14.4 — proof-checked mixed-CNF local XOR preprocessing.
// All added unit/equivalence clauses are derived from COMPLETE four-clause
// XOR encodings and independently replayed as GF(2) combinations.
// No SAT/UNSAT is inferred from a partial subsystem. If no safe implication
// is found, invoke unchanged V14.3 FastGate. Comparisons always use pinned
// original Kissat 4.0.4, and include preprocessing/wall-time overhead.
// This is standard polynomial-time algebraic preprocessing, not P=NP.
#include "v144_v143_embedded.inc"
#include <sys/types.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <numeric>

static constexpr long V144_SIZE_CAP=4L*1024*1024;
static constexpr size_t V144_MAX_EQUATIONS=18000;
static constexpr size_t V144_MAX_COMPONENT_EQ=96;
static constexpr size_t V144_MAX_COMPONENT_VARS=96;
static constexpr size_t V144_TOTAL_ELIMINATIONS=35000;
static constexpr size_t V144_MAX_NEW_CLAUSES=96;
static constexpr size_t V144_MAX_ROW_SUPPORT=96;
static constexpr size_t V144_MAX_PROOF_SIZE=96;
struct Derived144 {
  set<int> support;
  int rhs;
  set<int> provenance;
};
struct Output144 {
  vector<Derived144> derived;
  set<int> unsat_proof;
  int certified_units=0,certified_binary=0;
  size_t recognized=0,examined=0,skipped=0,ops=0;
};
static bool replay144(const vector<LocalEq>& eqs,const set<int>& proof,
                      const set<int>& expected,int rhs) {
  if(proof.empty())return false;
  set<int> vars;int parity=0;
  for(int id:proof) {
    if(id<0||size_t(id)>=eqs.size())return false;
    parity^=eqs[id].rhs;
    for(int v:eqs[id].support) {
      auto it=vars.find(v);
      if(it!=vars.end())vars.erase(it);
      else vars.insert(v);
    }
  }
  return vars==expected&&parity==rhs;
}
static bool reduce_component144(const vector<LocalEq>& eqs,
       const vector<int>& ids,Output144& out) {
  // Full per-component elimination is bounded and atomic. If a limit is
  // exceeded, discard every tentative result from this component.
  map<int,LocalRow> pivots;
  size_t local_ops=0;
  for(int id:ids) {
    LocalRow row;
    row.support.insert(eqs[id].support.begin(),eqs[id].support.end());
    row.provenance.insert(id);row.rhs=eqs[id].rhs;
    while(!row.support.empty()) {
      if(out.ops+local_ops++>=V144_TOTAL_ELIMINATIONS)return false;
      const int high=*row.support.rbegin();
      auto it=pivots.find(high);
      if(it==pivots.end()) {
        pivots.emplace(high,move(row));
        goto next_eq;
      }
      row.support=sxor(row.support,it->second.support);
      row.provenance=sxor(row.provenance,it->second.provenance);
      row.rhs^=it->second.rhs;
      if(row.support.size()>V144_MAX_ROW_SUPPORT||
         row.provenance.size()>V144_MAX_PROOF_SIZE)return false;
    }
    if(row.rhs) {
      if(!replay144(eqs,row.provenance,{},1))
        throw runtime_error("Unverified V14.4 GF2 contradiction");
      out.unsat_proof=row.provenance;
      out.ops+=local_ops;
      return true;
    }
    next_eq:;
  }
  // Reduced row echelon: pivot HIGH; remove lower pivot bits from high rows
  // by sweeping LOW to HIGH. Every row remains an exact combination.
  for(auto low=pivots.begin();low!=pivots.end();++low) {
    const int bit=low->first;
    for(auto high=next(low);high!=pivots.end();++high) {
      if(high->second.support.find(bit)==high->second.support.end())continue;
      if(out.ops+local_ops++>=V144_TOTAL_ELIMINATIONS)return false;
      auto ns=sxor(high->second.support,low->second.support);
      auto np=sxor(high->second.provenance,low->second.provenance);
      if(ns.size()>V144_MAX_ROW_SUPPORT||np.size()>V144_MAX_PROOF_SIZE)return false;
      high->second.support=move(ns);
      high->second.provenance=move(np);
      high->second.rhs^=low->second.rhs;
    }
  }
  vector<Derived144> additions;
  for(const auto& entry:pivots) {
    const auto& row=entry.second;
    if(row.support.empty()||row.support.size()>2)continue;
    if(!replay144(eqs,row.provenance,row.support,row.rhs))
      throw runtime_error("V14.4 implied XOR proof replay mismatch");
    additions.push_back({row.support,row.rhs,row.provenance});
  }
  out.ops+=local_ops;
  for(auto& x:additions)out.derived.push_back(move(x));
  return true;
}
static Output144 analyze144(const Cnf& f) {
  Output144 out;
  vector<LocalEq> eqs;
  exact_local_equations(f,eqs);
  out.recognized=eqs.size();
  if(eqs.size()<2||eqs.size()>V144_MAX_EQUATIONS)return out;
  UnionFind uf(f.n);
  for(const auto& e:eqs) {
    uf.join(e.support[0],e.support[1]);
    uf.join(e.support[0],e.support[2]);
  }
  map<int,vector<int>> groups;
  for(size_t i=0;i<eqs.size();++i)
    groups[uf.find(eqs[i].support[0])].push_back(int(i));
  set<pair<set<int>,int>> unique;
  for(const auto& group:groups) {
    const auto& ids=group.second;
    if(ids.size()>V144_MAX_COMPONENT_EQ){out.skipped++;continue;}
    set<int> vars;
    for(int id:ids)vars.insert(eqs[id].support.begin(),eqs[id].support.end());
    if(vars.size()>V144_MAX_COMPONENT_VARS||out.ops>=V144_TOTAL_ELIMINATIONS) {
      out.skipped++;continue;
    }
    size_t first=out.derived.size();
    if(!reduce_component144(eqs,ids,out)) {
      out.derived.resize(first);
      out.skipped++;
      continue;
    }
    out.examined++;
    if(!out.unsat_proof.empty())return out;
    for(size_t i=first;i<out.derived.size();i++) {
      const auto& row=out.derived[i];
      if(unique.insert({row.support,row.rhs}).second) {
        if(row.support.size()==1)out.certified_units++;
        else out.certified_binary++;
      }
    }
    if(size_t(out.certified_units+2*out.certified_binary)>=V144_MAX_NEW_CLAUSES)
      break;
  }
  // Atomic deduplication. Never add a clause without verified provenance.
  vector<Derived144> filtered;
  for(const auto& d:out.derived) {
    if(!unique.count({d.support,d.rhs}))continue;
    unique.erase({d.support,d.rhs});
    if(filtered.size()*2>=V144_MAX_NEW_CLAUSES)break;
    filtered.push_back(d);
  }
  out.derived=move(filtered);
  out.certified_units=out.certified_binary=0;
  for(const auto& d:out.derived)
    if(d.support.size()==1)out.certified_units++;
    else if(d.support.size()==2)out.certified_binary++;
  return out;
}
static void append_cnf144(const Cnf& f,const Output144& p,const string& filename) {
  size_t extra=0;
  for(const auto& row:p.derived)extra+=row.support.size();
  ofstream file(filename,ios::trunc);
  if(!file)throw runtime_error("Cannot create temporary verified CNF");
  file<<"c DRNAS V14.4 independently verified redundant XOR consequences\n";
  file<<"p cnf "<<f.n<<" "<<f.clauses.size()+extra<<"\n";
  for(const auto& clause:f.clauses) {
    for(int lit:clause)file<<lit<<' ';
    file<<"0\n";
  }
  for(const auto& row:p.derived) {
    if(row.support.size()==1) {
      int x=*row.support.begin();
      file<<(row.rhs?x:-x)<<" 0\n";
    } else if(row.support.size()==2) {
      auto iter=row.support.begin();int a=*iter++,b=*iter;
      if(row.rhs==0) {
        file<<-a<<' '<<b<<" 0\n"<<a<<' '<<-b<<" 0\n";
      } else {
        file<<a<<' '<<b<<" 0\n"<<-a<<' '<<-b<<" 0\n";
      }
    } else throw runtime_error("Invalid derived width");
  }
  file.flush();
  if(!file)throw runtime_error("Temporary CNF write failed");
}
static int kissat_augmented144(const Cnf& f,const Output144& out,const string& kissat) {
  char name[]="/tmp/drnas_v144_cnf_XXXXXX";
  int fd=mkstemp(name);
  if(fd<0)throw runtime_error("mkstemp failed");
  close(fd);
  try {append_cnf144(f,out,name);}
  catch(...) {unlink(name);throw;}
  pid_t child=fork();
  if(child<0){unlink(name);throw runtime_error("fork failed");}
  if(child==0) {
    char* args[]={const_cast<char*>(kissat.c_str()),name,nullptr};
    execv(args[0],args);
    _exit(127);
  }
  int result=0;
  while(waitpid(child,&result,0)<0) {
    if(errno!=EINTR){unlink(name);throw runtime_error("waitpid failed");}
  }
  unlink(name);
  if(WIFEXITED(result))return WEXITSTATUS(result);
  if(WIFSIGNALED(result))return 128+WTERMSIG(result);
  return 3;
}
int main(int argc,char**argv) {
  if(!(argc==4||(argc==5&&string(argv[4])=="--classify-only"))) {
    cerr<<"Usage: v144 INPUT_CNF KISSAT_BINARY SEED [--classify-only]\n";
    return 2;
  }
  try {
    struct stat st{};
    const string input=argv[1],kissat=argv[2];
    if(stat(input.c_str(),&st)!=0 || st.st_size<=0 || st.st_size>V144_SIZE_CAP)
      return v143_embedded_main(argc,argv);
    Cnf cnf;
    try {cnf=parse(input);}
    catch(const exception&){return v143_embedded_main(argc,argv);}
    Output144 result=analyze144(cnf);
    if(argc==5) {
      cout<<"DRNAS_V144_GATE\t"<<
         (!result.unsat_proof.empty()?"certified_unsat":
          result.derived.empty()?"unchanged_fallback":"mixed_xor_augmented")
         <<"\tblocks="<<result.recognized
         <<"\tunits="<<result.certified_units
         <<"\tbinaries="<<result.certified_binary
         <<"\texamined="<<result.examined
         <<"\tskipped="<<result.skipped<<"\n";
      return 0;
    }
    if(!result.unsat_proof.empty()) {
      vector<LocalEq> eqs;exact_local_equations(cnf,eqs);
      if(!replay144(eqs,result.unsat_proof,{},1))
        throw runtime_error("Local contradiction replay rejected");
      cout<<"DRNAS_V143_RESULT\t{\"status\":\"UNSAT\","
          <<"\"path\":\"local_xor_verified\",\"verified\":true,"
          <<"\"xor_blocks\":"<<eqs.size()<<",\"proof_equation_indices\":[";
      bool first=true;
      for(int id:result.unsat_proof) {
        cout<<(first?"":",")<<id;
        first=false;
      }
      cout<<"]}\n";
      return 0;
    }
    if(result.derived.empty())return v143_embedded_main(argc,argv);
    cout<<"DRNAS_V144_ROUTE\tmixed_xor_augmented\tunits="
        <<result.certified_units<<"\tbinaries="<<result.certified_binary
        <<"\tblocks="<<result.recognized<<"\n"<<flush;
    return kissat_augmented144(cnf,result,kissat);
  } catch(const exception& e) {
    cerr<<"DRNAS_V144_ERROR "<<e.what()<<"\n";
    // Error is NOT a SAT/UNSAT answer.
    return 3;
  }
}

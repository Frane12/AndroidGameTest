// DRNAS V14.5: sound parity reasoning with propagated unit implications.
// New evidence path: initial CNF unit clauses -> bounded unit propagation
// -> certified GF(2) contradiction with original XOR1/2/3 equations.
// All derived units carry explicit original-CNF reason clauses; every step
// must be independently checked by replay in frozen Python audit.
// No SAT claim from a parity subset. All other cases -> unchanged V14.4.
// No file names, expected labels, benchmark outcomes used in routing.
#include "v144_hidden_parity.cpp"
#include <numeric>

struct UpStep145 {int lit; int reason;};
struct Propagated145 {
 vector<UpStep145> steps;
 bool complete=true;
 bool conflict=false;
 int derived=0;
};
static Propagated145 propagate145(const Cnf& f,const vector<Parity144>& eq) {
 Propagated145 p;
 // Leave already certified multi-variable XOR clauses for GF(2), not CNF UP.
 // Unit implications can use all remaining clauses, with original reasons.
 vector<char> parity_used(f.clauses.size(),0);
 for(const auto& e:eq)if(e.vars.size()>1)
   for(int clause:e.clauses)if(clause>=0 && clause<(int)f.clauses.size())
     parity_used[clause]=1;
 const int max_steps=4096;
 const int max_scans=160000;
 vector<int8_t> values(f.n+1,0);
 int scans=0;
 bool changed=true;
 while(changed) {
   changed=false;
   for(int i=0;i<(int)f.clauses.size();i++) {
     if(parity_used[i])continue;
     if(++scans>max_scans) {p.complete=false;return p;}
     const auto& clause=f.clauses[i];
     bool sat=false,unknown=false;
     int last=0,unknown_count=0;
     for(int lit:clause) {
       const int v=abs(lit);
       const int8_t value=values[v];
       if(value==0){last=lit;unknown_count++;continue;}
       if((value>0)==(lit>0)){sat=true;break;}
     }
     if(sat)continue;
     if(unknown_count==0) {p.conflict=true;return p;}
     if(unknown_count!=1)continue;
     const int var=abs(last);
     const int8_t val=last>0?1:-1;
     if(values[var]==0) {
       if(p.steps.size()>=max_steps){p.complete=false;return p;}
       values[var]=val;
       p.steps.push_back({last,i});
       if(clause.size()>1)p.derived++;
       changed=true;
     } else if(values[var]!=val){p.conflict=true;return p;}
   }
 }
 return p;
}
static bool replay_unit145(const Cnf& f,const vector<UpStep145>& steps) {
 vector<int8_t> value(f.n+1,0);
 for(const auto& s:steps) {
   if(s.reason<0||s.reason>=(int)f.clauses.size()||
      !s.lit||abs(s.lit)>f.n||value[abs(s.lit)]!=0)return false;
   bool satisfied=false;
   int undetermined=0;
   for(int lit:f.clauses[s.reason]) {
     if(value[abs(lit)]==0) {
       undetermined++;
       if(lit!=s.lit)return false;
     } else if((value[abs(lit)]>0)==(lit>0))satisfied=true;
   }
   if(satisfied||undetermined!=1)return false;
   value[abs(s.lit)]=s.lit>0?1:-1;
 }
 return true;
}
int main(int argc,char**argv) {
 if(!(argc==4 || (argc==5 && string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v145_propagated_parity CNF KISSAT SEED [--classify-only]\n";
   return 2;
 }
 try {
   const string filename=argv[1];
   bool candidate=false;
   int equation_count=0,unit_count=0;
   struct stat st{};
   if(stat(filename.c_str(),&st)==0 && st.st_size>0 && st.st_size<=96*1024) {
     try {
       const Cnf f=parse(filename);
       vector<Parity144> eq=extract144(f);
       equation_count=(int)eq.size();
       const bool nontrivial=any_of(eq.begin(),eq.end(),[](const Parity144& e){
         return e.vars.size()>1;
       });
       if(nontrivial) {
         const Propagated145 propagation=propagate145(f,eq);
         unit_count=(int)propagation.steps.size();
         candidate=propagation.complete && !propagation.conflict &&
                   propagation.derived>0;
         if(candidate && argc==4) {
           if(!replay_unit145(f,propagation.steps))
             throw runtime_error("Unit propagation replay invalid");
           const int original_count=(int)eq.size();
           // Each fresh forced literal is a valid implied XOR1; proof source
           // is its propagation step, not an unproved fact about the CNF.
           for(size_t i=0;i<propagation.steps.size();i++) {
             const auto& up=propagation.steps[i];
             eq.push_back({{abs(up.lit)},up.lit>0?1:0,{-(int(i)+1)}});
           }
           set<int> proof;size_t ops=0;
           if(gf2_unsat144(eq,proof,ops)) {
             bool allgood=true;
             for(int index:proof) {
               if(index<original_count) {
                 if(!direct_witness144(f,eq[index])){allgood=false;break;}
               } else {
                 const int k=index-original_count;
                 if(k<0||k>=(int)propagation.steps.size()||
                    eq[index].clauses.size()!=1||
                    eq[index].clauses[0]!=-(k+1)) {allgood=false;break;}
               }
             }
             if(!allgood||!replay144(eq,proof))
               throw runtime_error("Original-clause GF2 proof mismatch");
             cout<<"DRNAS_V145_RESULT\t{\"status\":\"UNSAT\",\"verified\":true,"
                 <<"\"path\":\"propagated_hidden_parity\",\"proof\":[";
             bool first=true;
             for(int index:proof) {
               const auto& e=eq[index];
               cout<<(first?"":",")<<"{\"variables\":[";
               first=false;
               for(size_t j=0;j<e.vars.size();j++)
                 cout<<(j?",":"")<<e.vars[j];
               cout<<"],\"rhs\":"<<e.rhs<<",\"clause_indices\":[";
               if(index<original_count) {
                 for(size_t j=0;j<e.clauses.size();j++)
                   cout<<(j?",":"")<<e.clauses[j];
               }
               cout<<"]";
               if(index>=original_count)cout<<",\"unit_step\":"<<(index-original_count);
               cout<<"}";
             }
             cout<<"],\"unit_steps\":[";
             for(size_t i=0;i<propagation.steps.size();i++)
               cout<<(i?",":"")<<"{\"lit\":"<<propagation.steps[i].lit
                   <<",\"reason_clause\":"<<propagation.steps[i].reason<<"}";
             cout<<"],\"original_equations\":"<<original_count
                 <<",\"propagated_units\":"<<propagation.derived
                 <<",\"xor_operations\":"<<ops<<"}\n";
             return 0;
           }
         }
       }
     } catch(const exception& error) {
       cerr<<"DRNAS_V145_PREPASS_BYPASS "<<error.what()<<"\n";
     }
   }
   if(argc==5) {
     cout<<"DRNAS_V145_GATE\t"<<(candidate?"propagated_candidate":"bypass")
         <<"\tequations="<<equation_count<<"\tunits="<<unit_count<<"\n";
     return 0;
   }
   cout<<"DRNAS_V145_ROUTE\t"<<(candidate?"unit_parity_then_v144":"v144_direct")
       <<"\n"<<flush;
   return v144_embedded_main(argc,argv);
 } catch(const exception& error) {
   cerr<<"DRNAS_V145_ERROR "<<error.what()<<"\n";
   return 3;
 }
}

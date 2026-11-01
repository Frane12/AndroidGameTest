// DRNAS V15.4: Kissat C API bridge. Compiled and linked against the
// exact pinned libkissat.a; no secondary process or intermediate CNF file.
// Assumes Cnf and its parser have already been defined by v140.
#ifndef DRNAS_KISSAT_API_BRIDGE_INCLUDED
#define DRNAS_KISSAT_API_BRIDGE_INCLUDED
extern "C" {
#include "kissat.h"
}
#include <stdexcept>
#include <iostream>
#include <vector>

// A correct SAT witness is always checked against ALL original clauses.
// UNSAT delivered by Kissat API is Kissat's answer, not a DRNAS certificate;
// never mark it as independently proof-verified or fabricate a proof.
static inline bool drnas_kissat_model_valid(const Cnf& f,
                                           const std::vector<int>& model) {
 if(int(model.size())!=f.n)return false;
 std::vector<char> assignment(f.n+1,0);
 for(int lit:model) {
   if(lit==0||abs(lit)>f.n)return false;
   assignment[abs(lit)]=lit>0;
 }
 for(const auto& clause:f.clauses){
   bool satisfied=false;
   for(int lit:clause)
     if(assignment[abs(lit)]==(lit>0)){satisfied=true;break;}
   if(!satisfied)return false;
 }
 return true;
}
static inline int drnas_kissat_inprocess(const Cnf& f,
                                         const char* route,
                                         const std::vector<std::vector<int>>* additions=nullptr) {
 kissat* solver=kissat_init();
 if(!solver)throw std::runtime_error("kissat_init failed");
 int status=0;
 std::vector<int> model;
 try {
   kissat_reserve(solver,f.n);
   for(const auto& clause:f.clauses) {
     for(int lit:clause)kissat_add(solver,lit);
     kissat_add(solver,0);
   }
   if(additions)for(const auto& clause:*additions) {
     for(int lit:clause)kissat_add(solver,lit);
     kissat_add(solver,0);
   }
   status=kissat_solve(solver);
   if(status==10) {
     model.reserve(f.n);
     for(int v=1;v<=f.n;v++) {
       const int value=kissat_value(solver,v);
       model.push_back(value>0?v:-v);
     }
     if(!drnas_kissat_model_valid(f,model))
       throw std::runtime_error("Kissat API SAT witness invalid on original CNF");
   }
 } catch (...) {
   kissat_release(solver);
   throw;
 }
 kissat_release(solver);
 std::cout<<"DRNAS_V154_ROUTE\t"<<route<<"\n";
 if(status==10){
   std::cout<<"s SATISFIABLE\n";
   for(size_t i=0;i<model.size();i+=32){
     std::cout<<"v";
     for(size_t j=i;j<model.size()&&j<i+32;j++)
       std::cout<<" "<<model[j];
     std::cout<<(i+32>=model.size()?" 0":"")<<"\n";
   }
 } else if(status==20){
   std::cout<<"s UNSATISFIABLE\n";
 } else {
   std::cout<<"s UNKNOWN\n";
 }
 return status==10||status==20?0:3;
}
#endif

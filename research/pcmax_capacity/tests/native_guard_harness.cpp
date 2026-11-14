#include "pcmax_capacity.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>

int main(int argc,char** argv) {
 if(argc!=3&&argc!=4) return 2;
 std::ifstream file(argv[1]);
 std::vector<std::vector<int>> clauses;
 std::vector<int> pending;
 std::string line;
 int variables=-1,declared=-1;
 while(std::getline(file,line)) {
  std::istringstream in(line);std::string first;
  if(!(in>>first)||first=="c")continue;
  if(first=="p"){std::string format;in>>format>>variables>>declared;continue;}
  in.clear();in.str(line);int lit;
  while(in>>lit){if(lit)pending.push_back(lit);else{clauses.push_back(pending);pending.clear();}}
 }
 if(variables<0||!pending.empty()||int(clauses.size())!=declared)return 3;
 pcmax::Options options;options.seconds=argc==4?std::stod(argv[3]):1.0;
 const auto result=pcmax::analyze(clauses,variables,argv[2],options);
 std::cout<<std::setprecision(17)<<"{\"verified\":"<<(result.verified?"true":"false")
  <<",\"reason\":\""<<result.reason<<"\",\"elapsed\":"<<result.elapsed
  <<",\"certificate\":"<<(result.certificate_json.empty()?"null":result.certificate_json)
  <<",\"oracle\":";
 try {
  pcmax::detail::Budget budget(5.0);
  const auto g=pcmax::detail::extract(clauses,variables,budget);
  std::vector<int> covered(g.nv+1,0),eligible(g.groups.size(),1);
  for(const auto& machine:g.machines)for(int x:machine.order)covered[x]=1;
  bool incomplete=false;
  for(size_t j=0;j<g.groups.size();++j)for(int x:g.groups[j])if(!covered[x]){eligible[j]=0;incomplete=true;}
  bool uncovered_rejected=false;
  if(incomplete){
   std::vector<int64_t> all_positive(g.groups.size(),1);
   const auto unsafe=pcmax::detail::bounds(g,all_positive,budget);
   try {pcmax::detail::verify(g,all_positive,unsafe.capacities,budget);}
   catch(const pcmax::detail::Stop&){uncovered_rejected=true;}
   if(!uncovered_rejected)return 5;
  }
  std::cout<<"{\"groups\":[";
  for(size_t j=0;j<g.groups.size();++j){if(j)std::cout<<',';pcmax::detail::array(std::cout,g.groups[j]);}
  std::cout<<"],\"eligible\":";pcmax::detail::array(std::cout,eligible);
  std::cout<<",\"positive_uncovered_rejected\":"<<(uncovered_rejected?"true":"false")<<",\"samples\":[";
  std::mt19937 random(81337);
  for(int sample=0;sample<13;++sample){
   if(sample)std::cout<<',';
   std::vector<int64_t> w(g.groups.size());
   for(size_t j=0;j<w.size();++j){
    if(sample==0)w[j]=0;
    else if(sample==1)w[j]=1;
    else if(sample==2)w[j]=j%2;
    else if(sample==3)w[j]=1000000;
    else if(sample==4)w[j]=(j+1==w.size())?1000000:0;
    else w[j]=random()%19;
    if(!eligible[j])w[j]=0;
   }
   const auto maxima=pcmax::detail::bounds(g,w,budget,true);
   const bool valid=pcmax::detail::verify(g,w,maxima.capacities,budget);
   auto bad=maxima.capacities;bad.front()+=1;bool rejected=false;
   try {pcmax::detail::verify(g,w,bad,budget);}catch(const pcmax::detail::Stop&){rejected=true;}
   if(!rejected)return 4;
   std::cout<<"{\"weights\":";pcmax::detail::array(std::cout,w);
   std::cout<<",\"exact_verifier_accepts\":"<<(valid?"true":"false")
    <<",\"forged_capacity_rejected\":"<<(rejected?"true":"false");
   std::cout<<",\"maxima\":";pcmax::detail::array(std::cout,maxima.capacities);
   std::cout<<",\"patterns\":[";
   for(size_t m=0;m<maxima.patterns.size();++m){if(m)std::cout<<',';pcmax::detail::array(std::cout,maxima.patterns[m]);}
   std::cout<<"]}";
  }
  std::cout<<"]}";
 }catch(const pcmax::detail::Stop& e){std::cout<<"{\"unsupported\":\""<<e.what()<<"\"}";}
 std::cout<<"}\n";
 return 0;
}

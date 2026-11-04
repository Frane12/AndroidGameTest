// R107C: fast native complete XOR2..6 finder + GF(2) certificate, CNF output.
// No heuristic/partial XOR witnesses; independently re-read source before
// emitting a derived empty clause. Exit nonzero on parse/proof failures.
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <cstdint>
namespace fs = std::filesystem;
using V=std::vector<int>;
using Group=std::map<V,uint64_t>;
struct Row{V vars; int rhs=0; V ancestry;};
struct Parsed {int vars=0;int clauses=0;};
static void require(bool valid,const std::string &why){if(!valid)throw std::runtime_error("R107C_FAIL_CLOSED "+why);}
template<class Fn> Parsed parse(const fs::path& path, Fn callback){
  require(fs::exists(path) && fs::is_regular_file(path),"missing CNF");
  require(fs::file_size(path) <= 24*1024*1024,"bounded CNF size");
  std::ifstream in(path);require(bool(in),"cannot open CNF");
  std::string line; V current;
  int vars=-1,expected=-1,count=0;
  while(std::getline(in,line)){
    const char* cur=line.c_str();
    while(*cur==' '||*cur=='\r'||*cur=='\t')++cur;
    if(!*cur || *cur=='c')continue;
    if(*cur=='%')break;
    if(*cur=='p'){
      require(vars<0,"duplicate header");
      std::istringstream hdr(cur);
      std::string p,cnf,extra;hdr>>p>>cnf>>vars>>expected;
      require(p=="p"&&cnf=="cnf"&&!(hdr>>extra),"invalid DIMACS header");
      require(vars>0&&vars<=2000000&&expected>=0&&expected<=1500000,"header exceeds limits");
      continue;
    }
    require(vars>=0,"missing header");
    while(*cur){
      while(*cur==' '||*cur=='\r'||*cur=='\t')++cur;
      if(!*cur)break;
      char *end=nullptr;
      long lit=std::strtol(cur,&end,10);
      require(end!=cur,"invalid literal token");
      require(lit<=vars&&lit>=-vars,"literal outside declared vars");
      require(*end==' '||*end=='\r'||*end=='\t'||*end=='\0',"junk after literal");
      if(lit==0){
        callback(current);
        current.clear();
        ++count;
        require(count<=expected,"excess clauses");
      }else{
        current.push_back(int(lit));
        require(current.size()<=500000,"excess clause length");
      }
      cur=end;
    }
  }
  require(vars>0 && current.empty() && count==expected,"truncated DIMACS");
  return {vars,count};
}
static uint64_t parity_mask(int k,int rhs){
  uint64_t bits=0;
  for(int assignment=0; assignment<(1<<k); ++assignment)
    if((__builtin_popcount((unsigned)assignment)&1)!=rhs)bits|=(uint64_t(1)<<assignment);
  return bits;
}
static void add_group(Group& groups,const V& clause,const std::set<V>* restrict_to=nullptr){
  int k=int(clause.size());
  if(k<2 || k>6)return;
  V sorted=clause;
  std::sort(sorted.begin(),sorted.end(),[](int a,int b){return std::abs(a)<std::abs(b);});
  V vars;vars.reserve(k);int bits=0;
  for(int i=0;i<k;++i){
    int v=std::abs(sorted[i]);
    if(!vars.empty()&&v==vars.back())return;
    vars.push_back(v);
    if(sorted[i]<0)bits|=1<<i;
  }
  if(restrict_to && !restrict_to->count(vars))return;
  if(groups.find(vars)==groups.end())require(groups.size()<500000,"too many XOR groups");
  groups[std::move(vars)]|=uint64_t(1)<<bits;
}
static V xor_vectors(const V& a,const V& b){
  V c;c.reserve(a.size()+b.size());
  std::set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),std::back_inserter(c));
  return c;
}
static bool eliminate(const std::vector<Row>& rows,V& ancestry,size_t& rank){
  std::map<int,Row> pivots; size_t operations=0;
  for(int i=0;i<int(rows.size());++i){
    Row r=rows[i];r.ancestry={i};
    while(!r.vars.empty()){
      const int lead=r.vars.front();
      auto itr=pivots.find(lead);
      if(itr==pivots.end()){pivots.emplace(lead,std::move(r));break;}
      auto &p=itr->second;
      operations+=r.vars.size()+p.vars.size()+r.ancestry.size()+p.ancestry.size();
      require(operations<=100000000,"GF2 elimination budget exceeded");
      r.vars=xor_vectors(r.vars,p.vars);
      r.rhs^=p.rhs;
      r.ancestry=xor_vectors(r.ancestry,p.ancestry);
    }
    if(r.vars.empty()&&r.rhs==1){
      ancestry=std::move(r.ancestry);rank=pivots.size();return true;
    }
  }
  rank=pivots.size();return false;
}
static void replay_proof(const fs::path& source,const std::vector<Row>& rows,const V& proof){
  require(!proof.empty(),"missing GF2 ancestors");
  std::set<V> wanted; V cumulative;int rhs=0;
  for(int index:proof){
    require(index>=0&&index<int(rows.size()),"out-of-bounds ancestry");
    const Row &r=rows[index];
    wanted.insert(r.vars);
    cumulative=xor_vectors(cumulative,r.vars);
    rhs^=r.rhs;
  }
  require(cumulative.empty()&&rhs==1,"algebraic contradiction invalid");
  Group independent;
  Parsed parsed=parse(source,[&](const V& clause){add_group(independent,clause,&wanted);});
  (void)parsed;
  for(int index:proof){
    const Row &r=rows[index];
    auto it=independent.find(r.vars);
    require(it!=independent.end(),"independently missing XOR source");
    const auto needed=parity_mask(int(r.vars.size()),r.rhs);
    require((it->second & needed)==needed,"incomplete original clause pattern");
  }
}
static void output_cnf(const fs::path& source,const fs::path& dest,int clause_count,bool unsat){
  require(fs::absolute(source)!=fs::absolute(dest),"cannot overwrite source");
  if(!unsat){fs::copy_file(source,dest,fs::copy_options::overwrite_existing);return;}
  std::ifstream in(source);std::ofstream out(dest);
  require(bool(in)&&bool(out),"cannot stream augmented CNF");
  std::string line;bool changed=false;
  while(std::getline(in,line)){
    std::istringstream is(line);
    std::string first,format;is>>first;
    if(first=="p"){
      require(!changed,"duplicate source CNF header");
      int vars=0,declared=0;is>>format>>vars>>declared;
      require(format=="cnf"&&declared==clause_count,"bad CNF header on output");
      out<<"p cnf "<<vars<<" "<<(clause_count+1)<<"\n";changed=true;
    }else out<<line<<"\n";
  }
  require(changed,"missing source CNF header on output");
  out<<"0\n";require(bool(out),"write error");
}
static int build(const fs::path& source,const fs::path& dest,const fs::path& evidence){
  auto begin=std::chrono::steady_clock::now();
  require(!fs::equivalent(source,dest),"overlapping source and output");
  Group groups;
  Parsed parsed=parse(source,[&](const V& clause){add_group(groups,clause);});
  std::vector<Row> rows; int width_count[7]={};
  for(const auto& [vars,mask]:groups){
    for(int rhs=0;rhs<=1;++rhs)
      if((mask&parity_mask(int(vars.size()),rhs))==parity_mask(int(vars.size()),rhs)){
        rows.push_back({vars,rhs,{}});++width_count[vars.size()];
      }
  }
  require(rows.size()<=100000,"too many XOR rows");
  V proof;size_t rank=0;
  bool unsat=eliminate(rows,proof,rank);
  if(unsat)replay_proof(source,rows,proof);
  fs::create_directories(dest.parent_path());
  output_cnf(source,dest,parsed.clauses,unsat);
  auto secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  fs::create_directories(evidence.parent_path());
  std::ofstream out(evidence);require(bool(out),"cannot write evidence");
  out<<"{\"protocol\":\"R107C-FAST-XOR2-6-CERTIFIED\",\"source_clauses\":"<<parsed.clauses
     <<",\"source_xors\":"<<rows.size()<<",\"gf2_rank\":"<<rank
     <<",\"gf2_unsat\":"<<(unsat?"true":"false")
     <<",\"proof_length\":"<<proof.size()<<",\"prep_s\":"<<secs
     <<",\"widths\":{";
  for(int k=2;k<=6;++k){if(k>2)out<<",";out<<"\""<<k<<"\":"<<width_count[k];}
  out<<"},\"proof_row_ids\":[";
  for(size_t i=0;i<proof.size();++i){if(i)out<<",";out<<proof[i];}
  out<<"]}\n";require(bool(out),"evidence write failed");
  std::cout<<"R107C_PREPASS source_xors="<<rows.size()<<" gf2_unsat="<<unsat
           <<" proof_length="<<proof.size()<<" prep_s="<<secs<<"\n";
  return 0;
}
int main(int argc,char**argv){
  try{
    require(argc==4,"usage: r107c_fast_xor SOURCE_CNF OUTPUT_CNF EVIDENCE_JSON");
    return build(argv[1],argv[2],argv[3]);
  }catch(const std::exception&ex){std::cerr<<ex.what()<<"\n";return 2;}
}

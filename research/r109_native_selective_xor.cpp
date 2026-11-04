// R109: selective "twin-clause" resolution, an O(k*N log N) hidden-XOR
// experiment. Reuses frozen R107C parser, GF(2) kernel, original-CNF writer.
// Explicitly verify every selected proof node back to the original CNF.
#define main r107c_standalone_main
#include "r107c_native_xor_finder.cpp"
#undef main
#include <unordered_set>

struct HiddenNode {V clause;int parent_a=-1,parent_b=-1,pivot=0;};
struct HiddenRow {Row r;bool original=false;std::vector<int> witnesses;};
static constexpr int R109_MAX_INPUT_NODES=90000;
static constexpr int R109_MAX_NEW_NODES=9000;
static constexpr int R109_MAX_CANDIDATES=4500;

static bool by_abs(int a,int b){return std::abs(a)<std::abs(b);}
static bool canon(V& c){
  std::sort(c.begin(),c.end(),by_abs);
  for(size_t i=1;i<c.size();++i)
    if(std::abs(c[i])==std::abs(c[i-1]))return false;
  return true;
}
static V vars_of(const V& c){
  V a; a.reserve(c.size());
  for(int x:c)a.push_back(std::abs(x));
  return a;
}
static bool valid_step(const V& a,const V& b,int pivot,const V& child){
  V expected_a, expected_b;
  bool plus=false,minus=false;
  for(int v:a){
    if(v==pivot)plus=true;
    else expected_a.push_back(v);
  }
  for(int v:b){
    if(v==-pivot)minus=true;
    else expected_b.push_back(v);
  }
  return plus&&minus&&expected_a==child&&expected_b==child;
}
static bool false_on_assignment(const V& clause,const V& variables,int bits){
  for(int lit:clause){
    auto p=std::lower_bound(variables.begin(),variables.end(),std::abs(lit));
    if(p==variables.end()||*p!=std::abs(lit))return false;
    int bit=int(p-variables.begin());
    if(((bits>>bit)&1)==int(lit>0))return false;
  }
  return true;
}
static std::vector<int> find_support(const V& Vset,int rhs,
                                    const std::map<V,std::vector<int>>& by_variables,
                                    const std::vector<HiddenNode>& nodes){
  const int k=int(Vset.size());
  std::vector<int> witness(1<<k,-1);
  // 2^k subset queries, never enumerate pairs of clauses.
  for(int s=1;s<(1<<k);++s){
    V subset;
    for(int j=0;j<k;++j)if(s&(1<<j))subset.push_back(Vset[j]);
    auto itr=by_variables.find(subset);
    if(itr==by_variables.end())continue;
    for(int id:itr->second){
      const auto &clause=nodes[id].clause;
      for(int bits=0;bits<(1<<k);++bits){
        if(witness[bits]>=0)continue;
        if((__builtin_popcount((unsigned)bits)&1)==rhs)continue;
        if(false_on_assignment(clause,Vset,bits))witness[bits]=id;
      }
    }
  }
  for(int bits=0;bits<(1<<k);++bits)
    if((__builtin_popcount((unsigned)bits)&1)!=rhs&&witness[bits]<0)
      return {};
  return witness;
}
static void replay_hidden(const fs::path& source,
                          const std::vector<HiddenNode>& nodes,
                          int originals,
                          const std::vector<HiddenRow>& cert_rows,
                          const V& proof){
  require(!proof.empty(),"R109 empty GF2 ancestry");
  V reduced;int parity=0;
  std::set<V> baseline_needed;
  std::set<int> leaves;
  std::vector<char> checked(nodes.size(),0);
  std::function<void(int)> walk=[&](int id){
    require(id>=0&&size_t(id)<nodes.size(),"R109 bad proof node id");
    if(checked[id])return;
    checked[id]=1;
    if(nodes[id].parent_a<0){
      require(id<originals,"R109 forged original node");
      leaves.insert(id);
      return;
    }
    const auto &nd=nodes[id];
    require(nd.parent_a<id&&nd.parent_b<id,"R109 resolution ancestry cycle");
    walk(nd.parent_a);walk(nd.parent_b);
    require(valid_step(nodes[nd.parent_a].clause,nodes[nd.parent_b].clause,
                       nd.pivot,nd.clause),"R109 invalid resolved clause");
  };
  for(int idx:proof){
    require(idx>=0&&size_t(idx)<cert_rows.size(),"R109 bad GF2 row index");
    const auto &row=cert_rows[idx];
    reduced=xor_vectors(reduced,row.r.vars);
    parity^=row.r.rhs;
    if(row.original){baseline_needed.insert(row.r.vars);continue;}
    require(!row.witnesses.empty(),"R109 missing XOR certificate");
    const int k=int(row.r.vars.size());
    for(int mask=0;mask<(1<<k);++mask){
      if((__builtin_popcount((unsigned)mask)&1)==row.r.rhs)continue;
      const int id=row.witnesses[mask];
      walk(id);
      require(false_on_assignment(nodes[id].clause,row.r.vars,mask),
              "R109 witness does not falsify parity counterexample");
    }
  }
  require(reduced.empty()&&parity==1,"R109 algebra failed proof replay");
  // Source-CNF access is independent of the detector's original clause memory.
  int current_index=0; std::set<int> missing=leaves;
  Group verified;
  parse(source,[&](const V& clause){
    if(missing.erase(current_index)){
      V reconstructed=clause;
      require(canon(reconstructed)&&reconstructed==nodes[current_index].clause,
              "R109 original clause differs from replayed proof");
    }
    ++current_index;
    if(!baseline_needed.empty())add_group(verified,clause,&baseline_needed);
  });
  require(missing.empty(),"R109 source proof leaf missing");
  for(int idx:proof){
    const auto &row=cert_rows[idx];
    if(!row.original)continue;
    auto itr=verified.find(row.r.vars);
    require(itr!=verified.end(),"R109 baseline XOR missing in original");
    const auto want=parity_mask(int(row.r.vars.size()),row.r.rhs);
    require((itr->second&want)==want,"R109 missing complete original XOR");
  }
}
static int r109_build(const fs::path& source,const fs::path& output,
                      const fs::path& evidence){
  const auto start=std::chrono::steady_clock::now();
  require(fs::absolute(source).lexically_normal()!=fs::absolute(output).lexically_normal(),
          "R109 source overwrite");
  Group initial_groups;
  std::vector<HiddenNode> nodes;nodes.reserve(20000);
  bool selector_truncated=false;
  // One pass: build all frozen R107C patterns, plus a bounded original graph.
  Parsed original=parse(source,[&](const V& raw){
    add_group(initial_groups,raw);
    V clause=raw;
    if(!canon(clause))clause.clear();
    nodes.push_back({std::move(clause),-1,-1,0});
  });
  const int original_nodes=int(nodes.size());
  std::vector<HiddenRow> cert_rows;
  std::set<std::pair<V,int>> have;
  int base_counts[7]={};
  for(const auto& [v,mask]:initial_groups){
    for(int rhs=0;rhs<=1;++rhs){
      const uint64_t want=parity_mask(int(v.size()),rhs);
      if((mask&want)!=want)continue;
      cert_rows.push_back({{v,rhs,{}},true,{}});
      have.emplace(v,rhs);
      base_counts[v.size()]++;
    }
  }
  require(cert_rows.size()<=100000,"R109 excessive baseline XOR rows");
  V before_proof;size_t before_rank=0;
  bool baseline_unsat=false;
  {
    std::vector<Row> first;first.reserve(cert_rows.size());
    for(const auto &r:cert_rows)first.push_back(r.r);
    baseline_unsat=eliminate(first,before_proof,before_rank);
  }
  int original_xors=int(cert_rows.size());
  const size_t input_keep=std::min(size_t(original_nodes),size_t(R109_MAX_INPUT_NODES));
  if(original_nodes>R109_MAX_INPUT_NODES)selector_truncated=true;
  int generated=0, scanned_keys=0, new_rows=0, rounds_done=0;
  const auto gate_start=std::chrono::steady_clock::now();
  std::string gate=baseline_unsat?"baseline_already_unsat":"selective_bounded_twins";
  auto exceeded=[&](){
    return std::chrono::duration<double,std::milli>(
      std::chrono::steady_clock::now()-gate_start).count()>16.0;
  };
  if(!baseline_unsat){
    // Indexed pair cancellation: (C v x),(C v ~x) -> C.
    // Unlike unrestricted resolution, the identical core is hashed once.
    std::map<V,int> seen;
    for(size_t i=0;i<input_keep;++i){
      if(nodes[i].clause.size()>=1&&nodes[i].clause.size()<=8)
        seen.emplace(nodes[i].clause,int(i));
    }
    size_t from=0,to=input_keep;
    for(int depth=0;depth<2;++depth){
      if(exceeded()){selector_truncated=true;break;}
      std::map<std::pair<int,V>,std::pair<int,int>> twins;
      std::vector<HiddenNode> derived;
      for(size_t i=from;i<to;++i){
        const V& c=nodes[i].clause;
        if(c.size()<2||c.size()>8)continue;
        for(size_t j=0;j<c.size();++j){
          if(exceeded()){selector_truncated=true;break;}
          V core=c;const int lit=core[j];core.erase(core.begin()+j);
          auto& pair=twins[{std::abs(lit),core}];
          int& side=lit>0?pair.first:pair.second;
          if(side==0)side=int(i)+1;
          if(pair.first&&pair.second &&
             core.size()>=1&&core.size()<=6 &&
             !seen.count(core)){
            // Only one resolvent per canonical clause; parents remain valid.
            int ap=pair.first-1,bp=pair.second-1;
            require(valid_step(nodes[ap].clause,nodes[bp].clause,
                               std::abs(lit),core),"R109 invalid twin antecedents");
            const int next=int(nodes.size()+derived.size());
            seen.emplace(core,next);
            derived.push_back({std::move(core),ap,bp,std::abs(lit)});
            generated++;
            if(generated>=R109_MAX_NEW_NODES){selector_truncated=true;break;}
          }
        }
        if(selector_truncated)break;
      }
      if(!derived.empty()){
        from=nodes.size();
        nodes.insert(nodes.end(),std::make_move_iterator(derived.begin()),
                     std::make_move_iterator(derived.end()));
        to=nodes.size();
        rounds_done++;
      }else break;
      if(selector_truncated)break;
    }
    // Candidate full supports are a superset of baseline rows; derived clauses
    // are always checked under every falsifying assignment.
    std::map<V,std::vector<int>> by_variables;
    std::vector<V> candidates;
    std::set<V> candidate_set;
    for(size_t i=0;i<nodes.size();++i){
      const auto& cl=nodes[i].clause;
      if(cl.empty()||cl.size()>6)continue;
      V vs=vars_of(cl);
      by_variables[vs].push_back(int(i));
      if(vs.size()<2||candidate_set.count(vs))continue;
      // Prioritize actual derived clauses before source-only shortened forms.
      if(i>=size_t(original_nodes)){
        candidate_set.insert(vs);
        candidates.push_back(vs);
      }
    }
    for(const auto& [vars,mask]:initial_groups){
      (void)mask;
      if(vars.size()<2||candidate_set.count(vars))continue;
      candidate_set.insert(vars);candidates.push_back(vars);
    }
    if(candidates.size()>R109_MAX_CANDIDATES){candidates.resize(R109_MAX_CANDIDATES);selector_truncated=true;}
    for(const auto& vars:candidates){
      if(exceeded()||scanned_keys>=R109_MAX_CANDIDATES){selector_truncated=true;break;}
      ++scanned_keys;
      for(int rhs=0;rhs<=1;++rhs){
        if(have.count({vars,rhs}))continue;
        std::vector<int> w=find_support(vars,rhs,by_variables,nodes);
        if(w.empty())continue;
        // New rows from shortened original clauses are also allowed.
        cert_rows.push_back({{vars,rhs,{}},false,std::move(w)});
        have.emplace(vars,rhs);
        ++new_rows;
        if(int(cert_rows.size())>=100000){selector_truncated=true;break;}
      }
      if(selector_truncated)break;
    }
  }
  V proof;size_t rank=0;
  bool unsat=false;
  if(baseline_unsat){proof=before_proof;rank=before_rank;unsat=true;}
  else{
    std::vector<Row> all;all.reserve(cert_rows.size());
    for(auto& r:cert_rows)all.push_back(r.r);
    unsat=eliminate(all,proof,rank);
  }
  if(unsat)replay_hidden(source,nodes,original_nodes,cert_rows,proof);
  if(fs::absolute(output).has_parent_path())
    fs::create_directories(output.parent_path());
  output_cnf(source,output,original.clauses,unsat);
  auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  if(evidence.has_parent_path())fs::create_directories(evidence.parent_path());
  std::ofstream report(evidence);require(bool(report),"R109 evidence open failed");
  report<<"{\"protocol\":\"R109-SELECTIVE-TWIN-XOR-CERTIFIED\""
        <<",\"source_clauses\":"<<original.clauses
        <<",\"baseline_xors\":"<<original_xors
        <<",\"source_xors\":"<<cert_rows.size()
        <<",\"new_xors\":"<<new_rows
        <<",\"derived_clauses\":"<<generated
        <<",\"rounds\":"<<rounds_done
        <<",\"candidate_groups\":"<<scanned_keys
        <<",\"selector_truncated\":"<<(selector_truncated?"true":"false")
        <<",\"gf2_rank\":"<<rank
        <<",\"gf2_unsat\":"<<(unsat?"true":"false")
        <<",\"proof_length\":"<<proof.size()
        <<",\"prep_s\":"<<elapsed
        <<",\"gate\":\""<<gate<<"\""
        <<",\"proof_row_ids\":[";
  for(size_t i=0;i<proof.size();++i){if(i)report<<",";report<<proof[i];}
  report<<"]}\n";require(bool(report),"R109 evidence write failed");
  std::cout<<"R109_PREPASS baseline_xors="<<original_xors
           <<" source_xors="<<cert_rows.size()
           <<" new_xors="<<new_rows
           <<" gf2_unsat="<<unsat
           <<" prep_s="<<elapsed
           <<" selector_truncated="<<selector_truncated<<"\n";
  return 0;
}
int main(int argc,char** argv){
  try{
    require(argc==4,"usage: r109_native SOURCE_CNF OUTPUT_CNF EVIDENCE_JSON");
    return r109_build(argv[1],argv[2],argv[3]);
  }catch(const std::exception& e){std::cerr<<"R109_FAIL_CLOSED "<<e.what()<<"\n";return 2;}
}

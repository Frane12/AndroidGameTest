// IPG-BDD1: native source-derived BDD graph EXPORT ONLY (no UNSAT claim).
// Reuses the existing exact PCMAX source clause extractor without changing it.
// Every asserted premise is rechecked by an independent Python verifier.
#include "../src/pcmax_capacity.hpp"
#include <openssl/evp.h>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>
#include <charconv>

static std::string hash256(const std::string& data) {
    unsigned char h[EVP_MAX_MD_SIZE];unsigned int n=0;
    if(EVP_Digest(data.data(),data.size(),h,&n,EVP_sha256(),nullptr)!=1||n!=32)
        throw std::runtime_error("sha256_failed");
    constexpr char hex[]="0123456789abcdef";
    std::string v;
    for(unsigned int i=0;i<n;++i){v+=hex[h[i]>>4];v+=hex[h[i]&15];}
    return v;
}
static bool parse(const std::string& data,int& nv,std::vector<std::vector<int>>& clauses) {
    std::istringstream file(data);
    std::string line;
    int expected=-1;
    std::vector<int> cur;
    nv=-1;
    while(std::getline(file,line)) {
        auto i=line.find_first_not_of(" \t\r");
        if(i==std::string::npos)continue;
        if(line[i]=='c')continue;
        std::istringstream row(line.substr(i));
        if(line[i]=='p') {
            std::string p,fmt,extra;
            if(nv>=0||!(row>>p>>fmt>>nv>>expected)||p!="p"||fmt!="cnf"||
               nv<0||nv>200000||expected<0||expected>1000000||row>>extra)return false;
            clauses.reserve(static_cast<size_t>(expected));
            continue;
        }
        if(nv<0)return false;
        std::string tok;
        while(row>>tok){
            int v=0;
            auto result=std::from_chars(tok.data(),tok.data()+tok.size(),v);
            if(result.ec!=std::errc{}||result.ptr!=tok.data()+tok.size()||
               v>nv||v< -nv)return false;
            if(v==0){
                clauses.push_back(std::move(cur));
                cur.clear();
                if(clauses.size()>static_cast<size_t>(expected))return false;
            }else cur.push_back(v);
        }
    }
    return nv>=0&&expected==static_cast<int>(clauses.size())&&cur.empty();
}
static std::string export_json(const pcmax::detail::Graph& g,
                               const std::string& digest, int source_clauses) {
    using namespace pcmax::detail;
    std::ostringstream out;
    out<<"{\"format\":\"IPG-BDD1-SOURCE-GRAPH-V1\","
       <<"\"source_sha256\":\""<<digest<<"\","
       <<"\"source_variables\":"<<g.nv<<","
       <<"\"source_clauses\":"<<source_clauses<<","
       <<"\"eligible_groups\":[";
    int eligible=0;
    for(size_t j=0;j<g.groups.size();++j) {
        if(!g.eligible[j])continue;
        if(eligible++)out<<',';
        array(out,g.groups[j]);
    }
    out<<"],\"eligible_group_order\":[";
    int emitted=0;
    // This topological order is a heuristic for partial-demand subsets;
    // it is NOT an axiom used by the independent checker.
    std::vector<int> eligible_index(g.groups.size(),-1);
    int next=0;
    for(size_t j=0;j<g.groups.size();++j)
        if(g.eligible[j])eligible_index[j]=next++;
    for(int j:g.group_order) {
        if(eligible_index[static_cast<size_t>(j)]<0)continue;
        if(emitted++)out<<',';
        out<<eligible_index[static_cast<size_t>(j)];
    }
    out<<"],\"machine_graphs\":[";
    for(size_t k=0;k<g.machines.size();++k) {
        if(k)out<<',';
        const auto& m=g.machines[k];
        out<<"{\"root\":"<<m.root<<",\"true_terminal\":"<<m.yes
           <<",\"false_terminal\":"<<m.no<<",\"variable_order\":";
        array(out,m.order);
        out<<",\"transitions\":[";
        for(size_t i=0;i<m.nodes.size();++i) {
            if(i)out<<',';
            const auto& x=g.nodes[m.nodes[i]];
            out<<'['<<m.nodes[i]<<','<<x.x<<','<<x.left<<','<<x.right<<']';
        }
        out<<"]}";
    }
    out<<"]}\n";
    return out.str();
}
int main(int argc,char** argv) {
    if(argc!=4||std::string(argv[2])!="--output"){
        std::cerr<<"usage: ipg-bdd-extract SOURCE.cnf --output GRAPH.json\n";
        return 1;
    }
    try{
        std::ifstream fd(argv[1],std::ios::binary);
        if(!fd)throw std::runtime_error("cannot_read_source");
        std::string data((std::istreambuf_iterator<char>(fd)),
                         std::istreambuf_iterator<char>());
        if(data.size()>32000000)throw std::runtime_error("source_bytes_gate");
        int nv=0;std::vector<std::vector<int>> clauses;
        if(!parse(data,nv,clauses))throw std::runtime_error("invalid_dimacs");
        pcmax::detail::Budget b(3.0);
        auto graph=pcmax::detail::extract(clauses,nv,b);
        int eligible=0;
        for(auto flag:graph.eligible)if(flag)++eligible;
        if(eligible<3||eligible>56||graph.machines.size()>48)
            throw std::runtime_error("profile_size_gate");
        const auto cert=export_json(graph,hash256(data),int(clauses.size()));
        std::ofstream result(argv[3],std::ios::binary);
        if(!result)throw std::runtime_error("cannot_write_graph");
        result<<cert;
        if(!result)throw std::runtime_error("graph_write_failed");
        std::cout<<"IPG_BDD_SOURCE_GRAPH {\"status\":\"EXTRACTED\","
                 <<"\"groups\":"<<graph.groups.size()
                 <<",\"eligible\":"<<eligible
                 <<",\"machines\":"<<graph.machines.size()
                 <<",\"nodes\":"<<graph.nv<<"}\n";
        return 0;
    }catch(const std::exception& e) {
        std::cout<<"IPG_BDD_SOURCE_GRAPH {\"status\":\"UNKNOWN\","
                 <<"\"reason\":\""<<e.what()<<"\"}\n";
        return 0; // no file / no claim
    }
}

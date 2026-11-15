// DRNAS source-clique/PHP structural UNSAT proof, standalone native C++20.
// No Python subprocess, no CDCL, no labels or frozen-layout assumptions.
// The standard VeriPB 3.0 proof must be independently checked downstream.
#include <openssl/sha.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
struct Unknown : std::runtime_error { using std::runtime_error::runtime_error; };
static void require(bool good, const char* reason) { if (!good) throw Unknown(reason); }
struct Budget {
    Clock::time_point start = Clock::now();
    double max_seconds;
    explicit Budget(double s) : max_seconds(s) {}
    void check() const {
        if (std::chrono::duration<double>(Clock::now()-start).count()>max_seconds)
            throw Unknown("budget_exhausted");
    }
    double elapsed() const { return std::chrono::duration<double>(Clock::now()-start).count(); }
};
static std::string digest(const std::string &data) {
    unsigned char out[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char*>(data.data()),data.size(),out);
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (unsigned char c:out) oss << std::setw(2) << int(c);
    return oss.str();
}
static uint64_t key(int a,int b) {
    if (a>b) std::swap(a,b);
    return (uint64_t(uint32_t(a))<<32)|uint32_t(b);
}
struct Source {
    int vars=0,clauses=0;
    std::string sha256;
    std::vector<std::vector<int>> groups;
    std::vector<int> group_clause_ids;
    std::unordered_map<uint64_t,int> mutex_ids;
};
static Source parse(const fs::path &cnf,Budget &budget) {
    require(fs::is_regular_file(cnf),"not_regular_input");
    auto bytes=fs::file_size(cnf);
    require(bytes<=30'000'000,"input_size_gate");
    std::ifstream f(cnf,std::ios::binary);
    if (!f) throw std::runtime_error("cannot_open_source");
    std::string raw((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
    if (!f.eof() && f.fail()) throw std::runtime_error("input_read_failure");
    budget.check();
    Source src;
    src.sha256=digest(raw);
    std::map<std::vector<int>,int> group_map;
    std::istringstream input(raw);
    std::string line;
    std::vector<int> pending;
    bool has_header=false;
    int64_t line_no=0;
    int seen=0;
    while(std::getline(input,line)) {
        if ((++line_no&2047)==0) budget.check();
        auto first=line.find_first_not_of(" \t\r\n");
        if (first==std::string::npos) continue;
        if (line[first]=='c') continue;
        if (line[first]=='p') {
            std::istringstream parts(line.substr(first));
            std::string p,kind,extra;
            int n,m;
            require(!has_header && bool(parts>>p>>kind>>n>>m) && !(parts>>extra)
                    && p=="p" && kind=="cnf", "invalid_header");
            require(n>=1 && n<=200000 && m>=0 && m<=1'000'000,"size_gate");
            src.vars=n;src.clauses=m;has_header=true;
            continue;
        }
        require(has_header,"missing_header");
        std::istringstream litstream(line.substr(first));
        std::string token;
        while (litstream>>token) {
            char *end=nullptr;
            errno=0;
            long v=std::strtol(token.c_str(),&end,10);
            require(errno==0 && end && *end=='\0' && v>=-src.vars && v<=src.vars,"invalid_literal");
            if (v) {
                require(pending.size()<100000,"clause_width_gate");
                pending.push_back(int(v));
                continue;
            }
            ++seen;
            require(seen<=src.clauses,"clause_count_exceeded");
            if(pending.size()==2 && pending[0]<0 && pending[1]<0) {
                int a=-pending[0],b=-pending[1];
                if(a!=b) src.mutex_ids.emplace(key(a,b),seen);
            }
            if(pending.size()>=2 && pending.size()<=128 &&
               std::all_of(pending.begin(),pending.end(),[](int v){return v>0;})) {
                auto grp=pending;
                std::sort(grp.begin(),grp.end());
                bool distinct=std::adjacent_find(grp.begin(),grp.end())==grp.end();
                if(distinct) {
                    group_map.emplace(std::move(grp),seen);
                    require(group_map.size()<=256,"positive_group_gate");
                }
            }
            pending.clear();
        }
    }
    require(has_header && pending.empty() && seen==src.clauses,"bad_dimacs_count");
    for (const auto &[grp,id]:group_map) {
        src.groups.push_back(grp);
        src.group_clause_ids.push_back(id);
    }
    require(src.groups.size()>=3,"insufficient_positive_groups");
    budget.check();
    return src;
}
struct Structure {
    std::vector<std::vector<int>> resources;
    int selected=0;
};
struct DSU {
    std::vector<int> parent;
    explicit DSU(int n):parent(n+1) {std::iota(parent.begin(),parent.end(),0);}
    int find(int x) {while (parent[x]!=x) {parent[x]=parent[parent[x]];x=parent[x];}return x;}
    void join(int a,int b) {a=find(a);b=find(b);if (a!=b) parent[b]=a;}
};
static Structure reconstruct(const Source &src,Budget &budget) {
    std::vector<int> owner(src.vars+1,-1);
    int selected=0;
    for(size_t g=0;g<src.groups.size();++g) {
        for(int v:src.groups[g]) {
            require(owner[v]==-1,"overlapping_alo_groups");
            owner[v]=int(g);++selected;
        }
    }
    // This conservative fast path requires no unbounded auxiliary variables.
    require(selected==src.vars,"incomplete_alo_cover");
    std::vector<std::vector<int>> cross(src.vars+1);
    for(const auto &[pair,id]:src.mutex_ids) {
        (void)id;
        int a=int(pair>>32),b=int(pair&0xffffffffu);
        if(owner[a]>=0 && owner[b]>=0 && owner[a]!=owner[b]) {
            cross[a].push_back(b);
            cross[b].push_back(a);
        }
    }
    DSU dsu(src.vars);
    for(const auto &grp:src.groups) {
        std::map<std::vector<int>,int> signatures;
        for(int v:grp) {
            auto &c=cross[v];
            std::sort(c.begin(),c.end());
            c.erase(std::unique(c.begin(),c.end()),c.end());
            auto [it,inserted]=signatures.emplace(c,v);
            if(!inserted) dsu.join(v,it->second);
        }
        budget.check();
    }
    for(const auto &[pair,id]:src.mutex_ids) {
        (void)id;
        int a=int(pair>>32),b=int(pair&0xffffffffu);
        if(owner[a]>=0 && owner[b]>=0 && owner[a]!=owner[b]) dsu.join(a,b);
    }
    std::map<int,std::vector<int>> components;
    for(int v=1;v<=src.vars;++v) components[dsu.find(v)].push_back(v);
    Structure out;
    out.selected=selected;
    for(auto &[root,clique]:components) {
        (void)root;
        require(clique.size()>=2,"singleton_resource");
        for(size_t i=0;i<clique.size();++i) {
            if((i&15)==0) budget.check();
            for(size_t j=i+1;j<clique.size();++j)
                require(src.mutex_ids.contains(key(clique[i],clique[j])),"resource_not_clique");
        }
        out.resources.push_back(std::move(clique));
    }
    std::sort(out.resources.begin(),out.resources.end(),
              [](const auto &a,const auto &b){return a.front()<b.front();});
    require(out.resources.size()<src.groups.size(),"no_capacity_deficit");
    return out;
}
class AtomicProof {
    fs::path output_;
    std::string temp_;
    FILE *fd_=nullptr;
    int raw_fd_=-1;
    bool finished_=false;
public:
    explicit AtomicProof(fs::path out):output_(std::move(out)) {
        if(fs::exists(output_) || fs::is_symlink(output_)) throw std::runtime_error("proof_path_exists");
        if(!fs::is_directory(output_.parent_path().empty()?fs::path("."):output_.parent_path()))
            throw std::runtime_error("proof_parent_missing");
        std::string pattern=output_.string()+".tmp.XXXXXX";
        std::vector<char> chars(pattern.begin(),pattern.end());chars.push_back('\0');
        raw_fd_=mkstemp(chars.data());
        if(raw_fd_<0) throw std::runtime_error("cannot_create_proof_temp");
        temp_=chars.data();
        fd_=fdopen(raw_fd_,"w");
        if(!fd_) {close(raw_fd_);raw_fd_=-1;unlink(temp_.c_str());throw std::runtime_error("cannot_fdopen_proof");}
    }
    AtomicProof(const AtomicProof&)=delete;
    AtomicProof& operator=(const AtomicProof&)=delete;
    ~AtomicProof() {
        if(fd_) fclose(fd_);
        if(!temp_.empty()) unlink(temp_.c_str());
    }
    void write(const std::string &s) {
        if(!fd_ || std::fwrite(s.data(),1,s.size(),fd_)!=s.size())
            throw std::runtime_error("proof_write_failure");
    }
    void finish() {
        if(!fd_ || std::fflush(fd_)!=0 || fsync(raw_fd_)!=0)
            throw std::runtime_error("proof_flush_failure");
        if(std::fclose(fd_)!=0) {fd_=nullptr;throw std::runtime_error("proof_close_failure");}
        fd_=nullptr;
        // Atomic, no-overwrite publish. Never replace source files or older proofs.
        if(link(temp_.c_str(),output_.c_str())!=0)
            throw std::runtime_error("proof_atomic_publish_failure");
        unlink(temp_.c_str());temp_.clear();finished_=true;
    }
};
struct Produced {int steps=0;uintmax_t bytes=0;};
static Produced emit(const Source &source,const Structure &structure,const fs::path &path,Budget &budget) {
    AtomicProof output(path);
    int last=source.clauses;
    int steps=0;
    const auto pol=[&](const std::vector<int> &terms,int divisor,int scale_last)->int {
        require(!terms.empty() && divisor>=1 && scale_last>=1,"bad_pol_args");
        require(++steps<=100000,"proof_steps_gate");
        std::ostringstream buf;
        buf<<"pol "<<terms.front();
        for(size_t i=1;i<terms.size();++i) {
            buf<<' '<<terms[i];
            if(i==terms.size()-1 && scale_last>1) buf<<' '<<scale_last<<" *";
            buf<<" +";
        }
        if(divisor>1)buf<<' '<<divisor<<" d";
        buf<<" ;\n";
        output.write(buf.str());
        return ++last;
    };
    output.write("pseudo-Boolean proof version 3.0\n");
    output.write("f "+std::to_string(source.clauses)+" ;\n");
    std::vector<int> capacity_ids;
    for(const auto &clique:structure.resources) {
        int prev=source.mutex_ids.at(key(clique[0],clique[1]));
        for(size_t j=2;j<clique.size();++j) {
            budget.check();
            std::vector<int> ids;
            ids.reserve(j+1);
            for(size_t k=0;k<j;++k) ids.push_back(source.mutex_ids.at(key(clique[k],clique[j])));
            ids.push_back(prev);
            prev=pol(ids,int(j),int(j)-1);
        }
        capacity_ids.push_back(prev);
    }
    std::vector<int> all=source.group_clause_ids;
    all.insert(all.end(),capacity_ids.begin(),capacity_ids.end());
    pol(all,1,1);
    output.write("output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n");
    budget.check();
    output.finish();
    Produced r;r.steps=steps;r.bytes=fs::file_size(path);
    return r;
}
int main(int argc,char **argv) {
    if(argc<4) {
        std::cerr<<"Usage: drnas-php-native ORIGINAL.cnf --proof NEW_CERTIFICATE.pbp [--time seconds]\n";
        return 1;
    }
    fs::path cnf=argv[1],proof;
    double seconds=30.0;
    for(int i=2;i<argc;++i) {
        std::string arg=argv[i];
        if(arg=="--proof" && i+1<argc) proof=argv[++i];
        else if(arg=="--time" && i+1<argc) {
            try {seconds=std::stod(argv[++i]);}
            catch(...) {std::cerr<<"Invalid --time\n";return 1;}
        } else {std::cerr<<"Unknown option "<<arg<<"\n";return 1;}
    }
    if(proof.empty() || !(seconds>0.0 && seconds<=86400.0)) {
        std::cerr<<"Missing proof or invalid time budget\n";return 1;
    }
    Budget budget(seconds);
    try {
        Source src=parse(cnf,budget);
        Structure structure=reconstruct(src,budget);
        Produced result=emit(src,structure,proof,budget);
        std::cout<<"c DRNAS_PHP_NATIVE {\"status\":\"UNSAT_PBP_EMITTED_UNCHECKED\","
                 <<"\"source_sha256\":\""<<src.sha256<<"\","
                 <<"\"variables\":"<<src.vars<<",\"clauses\":"<<src.clauses<<","
                 <<"\"demand\":"<<src.groups.size()<<",\"resources\":"<<structure.resources.size()<<","
                 <<"\"proof_steps\":"<<result.steps<<",\"proof_bytes\":"<<result.bytes<<","
                 <<"\"native_s\":"<<std::fixed<<std::setprecision(6)<<budget.elapsed()<<"}\n";
        std::cout<<"s UNSATISFIABLE\n";
        return 20;
    } catch(const Unknown &e) {
        std::cout<<"c DRNAS_PHP_NATIVE {\"status\":\"UNKNOWN\",\"reason\":\""<<e.what()<<"\"}\n";
        std::cout<<"s UNKNOWN\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"DRNAS_PHP_NATIVE_ERROR "<<e.what()<<"\n";
        return 1;
    }
}

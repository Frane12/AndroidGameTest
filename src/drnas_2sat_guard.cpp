// DRNAS 2SAT-GUARD1: source-backed binary-subformula contradiction detector
// for arbitrary DIMACS CNF. Safe on mixed-width formulas: ignores wide
// clauses, UNSAT only from original unit/binary clause implication SCC.
// Produces RUP-compatible DRAT proof, no CDCL/Python subprocess.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
struct Unknown:std::runtime_error{using std::runtime_error::runtime_error;};
struct Deadline {
    Clock::time_point start=Clock::now();
    double limit;
    explicit Deadline(double seconds):limit(seconds){}
    void check() const {
        if(std::chrono::duration<double>(Clock::now()-start).count()>=limit)
            throw Unknown("time_budget_exhausted");
    }
    double elapsed() const {
        return std::chrono::duration<double>(Clock::now()-start).count();
    }
};
void expect(bool p,const char* msg){if(!p)throw Unknown(msg);}
int vertex(int literal){return (std::abs(literal)-1)*2+(literal<0);}
void edge(std::vector<std::vector<int>>&g,std::vector<std::vector<int>>&reverse,
          int from,int to){g[from].push_back(to);reverse[to].push_back(from);}
struct CNF{
    int vars=0,clauses=0;
    bool empty_clause=false;
    int wide_clauses=0, binary_clauses=0;
    std::vector<std::vector<int>> forward,reverse;
};
CNF read_cnf(const fs::path&path,Deadline&budget){
    expect(fs::is_regular_file(path),"not_regular_source");
    expect(fs::file_size(path)<=35'000'000,"source_byte_gate");
    std::ifstream in(path,std::ios::binary);
    if(!in)throw std::runtime_error("cannot_open_source");
    CNF src;
    bool has_header=false;
    int seen=0;
    std::vector<int> pending;
    std::string line;
    size_t line_count=0;
    while(std::getline(in,line)){
        if((++line_count&1023)==0)budget.check();
        auto begin=line.find_first_not_of(" \t\r\n");
        if(begin==std::string::npos)continue;
        if(line[begin]=='c')continue;
        if(line[begin]=='p'){
            std::istringstream h(line.substr(begin));
            std::string p,kind,extra;
            long long n,m;
            expect(!has_header&&bool(h>>p>>kind>>n>>m)&&!(h>>extra)&&
                   p=="p"&&kind=="cnf","bad_header");
            expect(n>0&&n<=200000&&m>=0&&m<=1000000,"header_size_gate");
            src.vars=int(n);src.clauses=int(m);
            src.forward.resize(src.vars*2);
            src.reverse.resize(src.vars*2);
            has_header=true;
            continue;
        }
        expect(has_header,"missing_header");
        std::istringstream tokens(line.substr(begin));
        std::string token;
        while(tokens>>token){
            char *end=nullptr;
            errno=0;
            long long v=std::strtoll(token.c_str(),&end,10);
            expect(errno==0 && end && *end=='\0'&&v>=-src.vars&&v<=src.vars,
                   "invalid_literal");
            if(v){
                if(pending.size()<3)pending.push_back(int(v));
                // Track only first 3 literals: non-binary clauses are skipped.
                continue;
            }
            ++seen;
            expect(seen<=src.clauses,"too_many_clauses");
            if(pending.empty())src.empty_clause=true;
            else if(pending.size()>2)++src.wide_clauses;
            else if(pending.size()==1){
                ++src.binary_clauses;
                int a=vertex(pending[0]);
                edge(src.forward,src.reverse,a^1,a);
            }else{
                ++src.binary_clauses;
                int a=vertex(pending[0]),b=vertex(pending[1]);
                edge(src.forward,src.reverse,a^1,b);
                edge(src.forward,src.reverse,b^1,a);
            }
            pending.clear();
        }
    }
    if(!in.eof()&&in.fail())throw std::runtime_error("source_read_failed");
    expect(has_header&&pending.empty()&&seen==src.clauses,"clause_count_mismatch");
    budget.check();
    return src;
}
int unsat_variable(const CNF&src,Deadline&budget){
    if(src.empty_clause)return 0;
    int n=src.vars*2;
    std::vector<unsigned char>seen(n,0);
    std::vector<int>finish;finish.reserve(n);
    std::vector<std::pair<int,size_t>>todo;
    for(int root=0;root<n;++root){
        if(seen[root])continue;
        seen[root]=1;
        todo.emplace_back(root,0);
        while(!todo.empty()){
            if((finish.size()&4095)==0)budget.check();
            auto &[v,i]=todo.back();
            if(i<src.forward[v].size()){
                int next=src.forward[v][i++];
                if(!seen[next]){
                    seen[next]=1;todo.emplace_back(next,0);
                }
            }else{
                finish.push_back(v);todo.pop_back();
            }
        }
    }
    std::vector<int>component(n,-1),stack;
    int id=0;
    for(auto it=finish.rbegin();it!=finish.rend();++it){
        int root=*it;
        if(component[root]!=-1)continue;
        component[root]=id;
        stack.push_back(root);
        while(!stack.empty()){
            int v=stack.back();stack.pop_back();
            for(int next:src.reverse[v]){
                if(component[next]==-1){
                    component[next]=id;stack.push_back(next);
                }
            }
        }
        ++id;
        budget.check();
    }
    for(int v=1;v<=src.vars;++v)
        if(component[(v-1)*2]==component[(v-1)*2+1])
            return v;
    return -1;
}
class AtomicDRAT{
    fs::path output;
    std::string tmp;
    FILE*file=nullptr;
    int fd=-1;
public:
    explicit AtomicDRAT(const fs::path&out):output(out){
        if(fs::exists(output)||fs::is_symlink(output))
            throw std::runtime_error("proof_path_exists");
        fs::path parent=out.parent_path().empty()?fs::path("."):out.parent_path();
        if(!fs::is_directory(parent))throw std::runtime_error("missing_proof_parent");
        std::string pattern=out.string()+".tmp.XXXXXX";
        std::vector<char>name(pattern.begin(),pattern.end());
        name.push_back('\0');
        fd=mkstemp(name.data());
        if(fd<0)throw std::runtime_error("mkstemp_failed");
        tmp=name.data();
        file=fdopen(fd,"w");
        if(!file){close(fd);fd=-1;unlink(tmp.c_str());throw std::runtime_error("fdopen_failed");}
    }
    ~AtomicDRAT(){
        if(file)fclose(file);
        if(!tmp.empty())unlink(tmp.c_str());
    }
    void finish(int contradiction){
        std::string text;
        if(contradiction==0)text="0\n";
        else text=std::to_string(contradiction)+" 0\n"+
                  std::to_string(-contradiction)+" 0\n0\n";
        if(fwrite(text.data(),1,text.size(),file)!=text.size()||
           fflush(file)!=0||fsync(fd)!=0)throw std::runtime_error("write_failed");
        if(fclose(file)!=0){file=nullptr;throw std::runtime_error("close_failed");}
        file=nullptr;
        // Publish atomically without replacing any old or original file.
        if(link(tmp.c_str(),output.c_str())!=0)
            throw std::runtime_error("proof_no_replace_publish_failed");
        unlink(tmp.c_str());
        tmp.clear();
    }
};
int main(int argc,char**argv){
    if(argc<4){std::cerr<<"Usage: drnas-2sat-guard CNF --proof NEW.drat [--time 10]\n";return 1;}
    fs::path source=argv[1],proof;
    double seconds=10.0;
    for(int i=2;i<argc;++i){
        std::string arg=argv[i];
        if(arg=="--proof"&&i+1<argc)proof=argv[++i];
        else if(arg=="--time"&&i+1<argc){
            try{seconds=std::stod(argv[++i]);}catch(...){return 1;}
        }else return 1;
    }
    if(proof.empty()||!std::isfinite(seconds)||seconds<=0||seconds>86400)return 1;
    Deadline budget(seconds);
    try{
        auto cnf=read_cnf(source,budget);
        int contradiction=unsat_variable(cnf,budget);
        if(contradiction<0)throw Unknown("binary_subformula_not_proven_unsat");
        budget.check();
        AtomicDRAT out(proof);
        out.finish(contradiction);
        std::cout<<"c DRNAS_2SAT_GUARD {\"status\":\"DRAT_EMITTED_UNCHECKED\","
                 <<"\"vars\":"<<cnf.vars<<",\"clauses\":"<<cnf.clauses<<","
                 <<"\"pivot\":"<<contradiction<<",\"wide_skipped\":"<<cnf.wide_clauses<<",\"binary_clauses\":"<<cnf.binary_clauses<<",\"elapsed_s\":"<<budget.elapsed()<<"}\n";
        std::cout<<"s UNSATISFIABLE\n";
        return 20;
    }catch(const Unknown&e){
        std::cout<<"c DRNAS_QUEEN2 {\"status\":\"UNKNOWN\",\"reason\":\""<<e.what()<<"\"}\n";
        std::cout<<"s UNKNOWN\n";
        return 0;
    }catch(const std::exception&e){
        std::cerr<<"DRNAS_QUEEN2_ERROR "<<e.what()<<"\n";
        return 1;
    }
}

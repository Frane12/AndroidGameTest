// DRNAS 2SAT-EXACT1: source-backed unit-propagation simplification
// of general CNF, followed by exact 2-SAT implication SCC on the residual
// binary clauses. All shortened clauses are RUP-added before an UNSAT proof.
// Pure 2-CNF: exact SAT witness or RUP UNSAT proof. Mixed CNF: certified UNSAT or verified SAT witness only.
#include <algorithm>
#include <cstdint>
#include <cerrno>
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
    bool empty_clause=false,unit_conflict=false;
    int wide_clauses=0,binary_clauses=0,up_assignments=0,wide_reduced=0;
    std::vector<int8_t> forced;
    std::vector<std::vector<int>> forward,reverse;
    std::vector<std::vector<int>> original, additions;
};
CNF read_cnf(const fs::path&path,Deadline&budget){
    expect(fs::is_regular_file(path),"not_regular_source");
    expect(fs::file_size(path)<=35'000'000,"source_byte_gate");
    std::ifstream in(path,std::ios::binary);
    if(!in)throw std::runtime_error("cannot_open_source");
    CNF src;
    bool has_header=false;
    int seen=0;
    size_t total_literals=0;
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
            src.original.reserve(src.clauses);
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
            expect(errno==0 && end && *end=='\0' && v>=-src.vars && v<=src.vars,
                   "invalid_literal");
            if(v){
                expect(++total_literals<=3'000'000,"literal_gate");
                pending.push_back(int(v));
                continue;
            }
            expect(++seen<=src.clauses,"too_many_clauses");
            std::sort(pending.begin(),pending.end(),[](int a,int b){
                return std::abs(a)==std::abs(b)?a<b:std::abs(a)<std::abs(b);
            });
            pending.erase(std::unique(pending.begin(),pending.end()),pending.end());
            bool tautology=false;
            for(size_t j=1;j<pending.size();++j)
                if(pending[j]==-pending[j-1]){tautology=true;break;}
            if(!tautology){
                if(pending.empty())src.empty_clause=true;
                else if(pending.size()>2)++src.wide_clauses;
                else ++src.binary_clauses;
                src.original.push_back(std::move(pending));
            }
            pending.clear();
        }
    }
    if(!in.eof()&&in.fail())throw std::runtime_error("source_read_failed");
    expect(has_header&&pending.empty()&&seen==src.clauses,"clause_count_mismatch");
    budget.check();
    return src;
}
void close_units_and_extract(CNF& src,Deadline&budget){
    if(src.empty_clause){src.unit_conflict=true;return;}
    const int count=int(src.original.size());
    std::vector<std::vector<int>> occurrences(2*src.vars);
    std::vector<int> remaining(count,0);
    std::vector<uint8_t> satisfied(count,0);
    std::vector<int8_t> assignment(src.vars,0);
    std::vector<int> queue;
    size_t visits=0;
    auto enqueue=[&](int l)->bool{
        int8_t sign=l>0?1:-1;
        int8_t& current=assignment[std::abs(l)-1];
        if(current==0){current=sign;queue.push_back(l);return true;}
        return current==sign;
    };
    for(int i=0;i<count;++i){
        const auto& c=src.original[i];
        if(c.empty()){src.unit_conflict=true;return;}
        remaining[i]=int(c.size());
        for(int l:c) occurrences[vertex(l)].push_back(i);
        if(c.size()==1&&!enqueue(c[0])){src.unit_conflict=true;return;}
        if((++visits&8191)==0)budget.check();
    }
    for(size_t head=0;head<queue.size();++head){
        int l=queue[head];
        for(int ci:occurrences[vertex(l)]) satisfied[ci]=1;
        for(int ci:occurrences[vertex(-l)]){
            if(satisfied[ci])continue;
            // Other initial/queued assignments may already satisfy this clause.
            // They must not be misclassified as a propagation conflict.
            bool already_true=false;
            for(int x:src.original[ci]){
                int8_t v=assignment[std::abs(x)-1];
                if(v!=0&&v==(x>0?1:-1)){already_true=true;break;}
            }
            if(already_true){satisfied[ci]=1;continue;}
            --remaining[ci];
            if(remaining[ci]==0){src.unit_conflict=true;return;}
            if(remaining[ci]==1){
                int pending=0;
                for(int x:src.original[ci]){
                    if(assignment[std::abs(x)-1]==0){pending=x;break;}
                }
                if(pending==0 || !enqueue(pending)){
                    src.unit_conflict=true;return;
                }
            }
            if((++visits&8191)==0)budget.check();
        }
        if((head&4095)==0)budget.check();
    }
    src.up_assignments=int(queue.size());
    src.forced=assignment;
    for(int ci=0;ci<count;++ci){
        if(satisfied[ci])continue;
        const auto& c=src.original[ci];
        std::vector<int> residual;
        for(int l:c){
            if(assignment[std::abs(l)-1]==0)residual.push_back(l);
        }
        if(residual.empty()){src.unit_conflict=true;return;}
        if(residual.size()<=2){
            if(residual.size()<c.size()){
                expect(src.additions.size()<100000,"proof_additions_gate");
                src.additions.push_back(residual);
                if(c.size()>2)++src.wide_reduced;
            }
            int a=vertex(residual[0]);
            if(residual.size()==1)edge(src.forward,src.reverse,a^1,a);
            else{
                int b=vertex(residual[1]);
                edge(src.forward,src.reverse,a^1,b);
                edge(src.forward,src.reverse,b^1,a);
            }
        }
        if((ci&4095)==0)budget.check();
    }
}
int unsat_variable(const CNF&src,Deadline&budget,std::vector<int8_t>& model){
    if(src.empty_clause||src.unit_conflict)return 0;
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
    model.assign(src.vars,0);
    for(int v=0;v<src.vars;++v)
        model[v]=(component[2*v]>component[2*v+1])?1:-1;
    for(int v=0;v<(int)src.forced.size();++v)
        if(src.forced[v])model[v]=src.forced[v];
    return -1;
}
bool verifies_source(const CNF&cnf,const std::vector<int8_t>&model){
    if((int)model.size()!=cnf.vars)return false;
    for(const auto&clause:cnf.original){
        bool ok=false;
        for(int l:clause){
            if(model[std::abs(l)-1]==(l>0?1:-1)){ok=true;break;}
        }
        if(!ok)return false;
    }
    return true;
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
    void finish(int contradiction,const CNF& cnf){
        std::ostringstream proof;
        if(contradiction!=0){
            for(const auto& c:cnf.additions){
                for(int l:c)proof<<l<<' ';
                proof<<"0\n";
            }
            proof<<contradiction<<" 0\n"<<-contradiction<<" 0\n0\n";
        }else proof<<"0\n";
        std::string text=proof.str();
        if(fwrite(text.data(),1,text.size(),file)!=text.size()||
           fflush(file)!=0||fsync(fd)!=0)throw std::runtime_error("write_failed");
        if(fclose(file)!=0){file=nullptr;throw std::runtime_error("close_failed");}
        file=nullptr;
        if(link(tmp.c_str(),output.c_str())!=0)
            throw std::runtime_error("proof_no_replace_publish_failed");
        unlink(tmp.c_str());
        tmp.clear();
    }
};
int main(int argc,char**argv){
    if(argc<4){std::cerr<<"Usage: drnas-2sat-exact CNF --proof NEW.drat [--time 10]\n";return 1;}
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
        close_units_and_extract(cnf,budget);
        std::vector<int8_t> model;
        int contradiction=unsat_variable(cnf,budget,model);
        budget.check();
        if(contradiction<0){
            if(!verifies_source(cnf,model))
                throw Unknown("binary_subformula_satisfiable_but_whole_CNF_unresolved");
            std::cout<<"c DRNAS_2SAT_EXACT {\\\"status\\\":\\\"SAT_MODEL_VERIFIED\\\","
                     <<"\\\"pure_2cnf\\\":"<<(cnf.wide_clauses==0?"true":"false")
                     <<",\\\"vars\\\":"<<cnf.vars<<",\\\"clauses\\\":"<<cnf.clauses<<"}\\n";
            std::cout<<"s SATISFIABLE\\n";
            for(int i=0;i<cnf.vars;++i){
                if(i%30==0)std::cout<<"v ";
                std::cout<<(model[i]>0?i+1:-(i+1))<<' ';
                if(i%30==29||i+1==cnf.vars)std::cout<<"0\\n";
            }
            return 10;
        }
        AtomicDRAT out(proof);
        out.finish(contradiction,cnf);
        std::cout<<"c DRNAS_2SAT_EXACT {\"status\":\"DRAT_EMITTED_UNCHECKED\","
                 <<"\"vars\":"<<cnf.vars<<",\"clauses\":"<<cnf.clauses<<","
                 <<"\"pivot\":"<<contradiction<<",\"wide_skipped\":"<<cnf.wide_clauses<<",\"binary_clauses\":"<<cnf.binary_clauses<<",\"elapsed_s\":"<<budget.elapsed()<<"}\n";
        std::cout<<"s UNSATISFIABLE\n";
        return 20;
    }catch(const Unknown&e){
        std::cout<<"c DRNAS_2SAT_EXACT {\"status\":\"UNKNOWN\",\"reason\":\""<<e.what()<<"\"}\n";
        std::cout<<"s UNKNOWN\n";
        return 0;
    }catch(const std::exception&e){
        std::cerr<<"DRNAS_QUEEN2_ERROR "<<e.what()<<"\n";
        return 1;
    }
}

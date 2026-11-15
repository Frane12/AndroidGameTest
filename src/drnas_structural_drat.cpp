// DRNAS native C++ structural-certificate -> standard DRAT bridge.
// Source-backed Hall/PHP (extended resolution) and XOR/Tseitin (RUP elimination).
// Never claim UNSAT from a structural cert: require an independent DRAT checker.
// C++20, Boost.PropertyTree JSON headers, OpenSSL libcrypto.
#define BOOST_BIND_GLOBAL_PLACEHOLDERS
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <openssl/evp.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>
#include <sys/types.h>
#include <sys/wait.h>
#include <sched.h>
#include <unistd.h>
#include <fcntl.h>

namespace pt=boost::property_tree;
using Clause=std::vector<int>;
using Clock=std::chrono::steady_clock;
using namespace std::chrono;

[[noreturn]] static void fail(const std::string& why){throw std::runtime_error(why);}
static Clause canonical(Clause c){std::sort(c.begin(),c.end());c.erase(std::unique(c.begin(),c.end()),c.end());return c;}
static bool subset(const Clause& a,const Clause& b){return std::includes(b.begin(),b.end(),a.begin(),a.end());}
static bool contains(const Clause& a,int lit){return std::binary_search(a.begin(),a.end(),lit);}
static bool tautology(const Clause& a){for(int l:a)if(contains(a,-l))return true;return false;}
static double elapsed_s(Clock::time_point start){return duration<double>(Clock::now()-start).count();}
static std::string hexsha(const std::string& path){
    auto *ctx=EVP_MD_CTX_new();if(!ctx)fail("EVP_MD_CTX_new failed");
    std::ifstream f(path,std::ios::binary);if(!f){EVP_MD_CTX_free(ctx);fail("cannot read CNF for SHA");}
    if(EVP_DigestInit_ex(ctx,EVP_sha256(),nullptr)!=1){EVP_MD_CTX_free(ctx);fail("SHA256 init");}
    std::array<char,65536> buf{};
    while(f){f.read(buf.data(),buf.size());auto n=f.gcount();if(n>0&&EVP_DigestUpdate(ctx,buf.data(),size_t(n))!=1){EVP_MD_CTX_free(ctx);fail("SHA256 update");}}
    unsigned char digest[EVP_MAX_MD_SIZE]{};unsigned int len=0;
    if(EVP_DigestFinal_ex(ctx,digest,&len)!=1){EVP_MD_CTX_free(ctx);fail("SHA256 final");}
    EVP_MD_CTX_free(ctx);
    std::ostringstream s;s<<std::hex<<std::setfill('0');for(unsigned i=0;i<len;++i)s<<std::setw(2)<<int(digest[i]);return s.str();
}
struct CNF{int variables=0;int64_t declared=0;std::set<Clause> source;};
static CNF read_cnf(const std::string& path){
    std::ifstream f(path);if(!f)fail("cannot open original CNF");
    CNF cnf;bool header=false;Clause current;int64_t seen=0;
    std::string line;
    while(std::getline(f,line)){
        auto pos=line.find_first_not_of(" \t\r");if(pos==std::string::npos)continue;
        char start=line[pos];if(start=='c'||start=='%')continue;
        if(start=='p'){
            if(header)fail("duplicate DIMACS header");
            std::istringstream h(line.substr(pos));std::string p,cnftext,garbage;
            if(!(h>>p>>cnftext>>cnf.variables>>cnf.declared) || (h>>garbage) || cnftext!="cnf"
               || cnf.variables<=0||cnf.variables>2000000||cnf.declared<1||cnf.declared>3000000)fail("bad DIMACS header");
            header=true;continue;
        }
        if(!header)fail("missing DIMACS header");
        std::istringstream row(line.substr(pos));int v=0;
        while(row>>v){
            if(v==0){cnf.source.insert(canonical(current));current.clear();++seen;if(seen>cnf.declared)fail("too many clauses");}
            else{if(v==std::numeric_limits<int>::min()||std::abs(v)>cnf.variables)fail("literal out of range");
                 current.push_back(v);if(current.size()>2500000)fail("large clause limit");}
        }
        if(!row.eof())fail("malformed DIMACS row");
    }
    if(!header||!current.empty()||seen!=cnf.declared)fail("incomplete CNF");
    return cnf;
}
static std::vector<int> ints(const pt::ptree& a){
    std::vector<int> r;for(const auto &item:a){if(!item.first.empty())fail("expected JSON array");
        r.push_back(item.second.get_value<int>());}return r;
}
static std::vector<std::vector<int>> arrays(const pt::ptree& a){
    std::vector<std::vector<int>> r;for(const auto& e:a){if(!e.first.empty())fail("expected JSON array");r.push_back(ints(e.second));}return r;
}
struct Emit{
    std::ofstream out;size_t steps=0,rat=0,rup=0,max_steps=1000000;
    Clock::time_point start;double cap;
    Emit(const std::string& p,Clock::time_point s,double timeout):out(p,std::ios::binary|std::ios::trunc),start(s),cap(timeout){if(!out)fail("cannot write proof");}
    void add(const Clause& c,bool israt){
        if(++steps>max_steps||elapsed_s(start)>cap)fail("proof step/time limit");
        for(int x:c)out<<x<<' ';
        out<<"0\n";
        if(!out)fail("proof I/O error");
        if(israt)++rat;else ++rup;
    }
    void close(){out.flush();if(!out)fail("proof flush failed");out.close();}
};
static void validate_source_sha(const std::string& cnf,const pt::ptree& cert){
    const auto claimed=cert.get<std::string>("source_sha256");
    if(claimed.size()!=64||claimed!=hexsha(cnf))fail("source SHA256 mismatch");
}
static std::string hall_proof(const CNF& cnf,const pt::ptree& cert,Emit& proof){
    auto groups=arrays(cert.get_child("alo_groups"));auto columns=arrays(cert.get_child("resource_cliques"));
    const int g=cert.get<int>("required_groups"),h=cert.get<int>("resource_bound");
    if(g!=int(groups.size())||h!=int(columns.size())||h<1||g<=h||h>256)fail("invalid Hall dimensions/limit");
    groups.resize(size_t(h+1));const int p=h+1;
    std::vector<std::vector<int>> matrix(p,std::vector<int>(h,0));std::set<int> all;
    for(int i=0;i<p;++i){
        const auto& row=groups[i];
        if(int(row.size())!=h)fail("invalid source ALO width");
        std::set<int> uniq(row.begin(),row.end());if(int(uniq.size())!=h)fail("duplicate ALO literal");
        for(int x:row)if(x<=0||x>cnf.variables)fail("invalid ALO variable");
        if(!cnf.source.count(canonical(row)))fail("ALO clause absent from original source");
        for(int j=0;j<h;++j){
            int matches=0,matched=0;
            for(int x:row)for(int y:columns[j])if(x==y){matched=x;++matches;}
            if(matches!=1)fail("Hall row-column intersection not unique");
            matrix[i][j]=matched;if(!all.insert(matched).second)fail("repeated Hall variable");
        }
    }
    for(int j=0;j<h;++j)for(int i=0;i<p;++i)for(int k=i+1;k<p;++k)
        if(!cnf.source.count(canonical({-matrix[i][j],-matrix[k][j]})))fail("source AMO clause missing");
    int nextvar=cnf.variables;
    while(matrix[0].size()>1){
        const int old_h=int(matrix[0].size()),old_p=int(matrix.size());
        if(old_p!=old_h+1)fail("PHP induction invariant");
        const auto last=matrix.back();
        std::vector<std::vector<int>> reduced(old_p-1,std::vector<int>(old_h-1));
        for(int i=0;i<old_p-1;++i){
            for(int j=0;j<old_h-1;++j){
                if(nextvar==std::numeric_limits<int>::max())fail("auxiliary variable overflow");
                int y=++nextvar,a=matrix[i][j],b=matrix[i][old_h-1],c=last[j];
                proof.add({y,-a},true);
                proof.add({y,-b,-c},true);
                proof.add({-y,a,b},true);
                proof.add({-y,a,c},true);
                reduced[i][j]=y;
            }
        }
        for(const auto& row:reduced)proof.add(row,false);
        for(int j=0;j<old_h-1;++j){
            for(int i=0;i<old_p-1;++i)for(int k=i+1;k<old_p-1;++k){
                const int y1=reduced[i][j],y2=reduced[k][j];
                proof.add({-y1,-matrix[k][j]},false);
                proof.add({-y1,-matrix[k][old_h-1],-last[j]},false);
                proof.add({-y1,-y2},false);
            }
        }
        matrix=std::move(reduced);
    }
    proof.add({},false);return "HALL_ER";
}
static std::string xor_proof(const CNF& cnf,const pt::ptree& cert,Emit& proof){
    std::set<Clause> active;
    const auto& rows=cert.get_child("xor_rows");
    if(rows.empty()||rows.size()>5000)fail("empty or oversized XOR certificate");
    for(const auto& row:rows){
        if(!row.first.empty())fail("nonarray XOR rows");
        const auto vs=ints(row.second.get_child("vars"));const int forbidden=row.second.get<int>("forbidden_parity");
        if(vs.empty()||vs.size()>5|| (forbidden!=0&&forbidden!=1))fail("unsupported XOR encoding");
        std::set<int> unique(vs.begin(),vs.end());
        if(unique.size()!=vs.size())fail("duplicate XOR variable");
        for(int v:vs)if(v<=0||v>cnf.variables)fail("out of range XOR var");
        for(unsigned mask=0;mask<(1u<<vs.size());++mask){
            if(int(__builtin_popcount(mask)&1u)!=forbidden)continue;
            Clause c;for(size_t b=0;b<vs.size();++b)c.push_back((mask&(1u<<b))?-vs[b]:vs[b]);
            c=canonical(std::move(c));
            if(!cnf.source.count(c))fail("source XOR clause missing");
            active.insert(std::move(c));
        }
    }
    constexpr size_t max_active=200000;
    while(!active.count(Clause{})){
        if(elapsed_s(proof.start)>proof.cap||active.size()>max_active)fail("XOR elimination resource limit");
        std::map<int,std::array<std::vector<Clause>,2>> occ;
        for(const auto& c:active)for(int lit:c)occ[std::abs(lit)][lit<0].push_back(c);
        if(occ.empty())fail("no contradiction derived");
        int pivot=0;uint64_t best_prod=UINT64_MAX,best_total=UINT64_MAX;
        for(const auto& [x,buckets]:occ){
            uint64_t prod=uint64_t(buckets[0].size())*buckets[1].size(),total=0;
            for(const auto& bucket:buckets)for(const auto& c:bucket)total+=c.size();
            if(prod<best_prod||(prod==best_prod&&(total<best_total||(total==best_total&&x<pivot)))){
                pivot=x;best_prod=prod;best_total=total;
            }
        }
        const auto &positive=occ[pivot][0],&negative=occ[pivot][1];
        std::set<Clause> base,added;
        for(const auto& c:active)if(!contains(c,pivot)&&!contains(c,-pivot))base.insert(c);
        bool contradiction=false;
        for(const auto &left:positive){
            for(const auto &right:negative){
                Clause r;
                for(int l:left)if(l!=pivot)r.push_back(l);
                for(int l:right)if(l!=-pivot)r.push_back(l);
                r=canonical(std::move(r));
                if(tautology(r)||base.count(r)||added.count(r))continue;
                bool subsumed=false;for(const auto& b:base){if(b.size()<=r.size() && subset(b,r)){subsumed=true;break;}}
                if(subsumed)continue;
                for(auto it=added.begin();it!=added.end();){
                    if(subset(r,*it))it=added.erase(it);else ++it;
                }
                added.insert(r);proof.add(r,false);
                if(r.empty()){contradiction=true;break;}
            }
            if(contradiction)break;
        }
        active=std::move(base);active.insert(added.begin(),added.end());
        if(active.empty())fail("XOR elimination exhausted without contradiction");
    }
    return "XOR_DP_RUP";
}
static void pin_one_core(){
    cpu_set_t available;CPU_ZERO(&available);
    if(sched_getaffinity(0,sizeof(available),&available)!=0)fail("cannot read CPU affinity");
    int cpu=-1;for(int k=0;k<CPU_SETSIZE;++k)if(CPU_ISSET(k,&available)){cpu=k;break;}
    if(cpu<0)fail("no available core");
    CPU_ZERO(&available);CPU_SET(cpu,&available);
    if(sched_setaffinity(0,sizeof(available),&available)!=0)fail("cannot pin CPU");
}
static std::string run_checker(const std::string& checker,const std::string& cnf,const std::string& drat,const std::string& logfile,Clock::time_point start,double cap){
    if(elapsed_s(start)>=cap)fail("no time left for external checker");
    pid_t pid=fork();if(pid<0)fail("cannot fork independent checker");
    if(pid==0){
        const int fd=open(logfile.c_str(),O_CREAT|O_WRONLY|O_TRUNC,0600);
        if(fd<0)_exit(126);
        dup2(fd,STDOUT_FILENO);dup2(fd,STDERR_FILENO);close(fd);
        execl(checker.c_str(),checker.c_str(),cnf.c_str(),drat.c_str(),(char*)nullptr);
        _exit(127);
    }
    int status=0;bool finished=false;
    while(elapsed_s(start)<cap){
        pid_t w=waitpid(pid,&status,WNOHANG);
        if(w==pid){finished=true;break;}if(w<0)break;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    if(!finished){kill(pid,SIGKILL);waitpid(pid,&status,0);fail("independent checker timeout/failure");}
    std::ifstream file(logfile);std::ostringstream content;content<<file.rdbuf();const std::string log=content.str();
    if(!WIFEXITED(status)||WEXITSTATUS(status)!=0||log.find("s VERIFIED")==std::string::npos)
        fail("independent drat-trim did NOT verify original CNF + proof");
    return log;
}
int main(int argc,char**argv){
    std::string proof;
    try{
        if(argc!=7||std::string(argv[4])!="--checker"){
            std::cerr<<"USAGE: drnas-structural-drat <original.cnf> <structural_cert.json> <output.drat> --checker <drat-trim> <max_s>\n";
            return 2;
        }
        const std::string cnf=argv[1],certpath=argv[2],checker=argv[5];proof=argv[3];
        const double max_s=std::stod(argv[6]);if(max_s<=0||max_s>600)fail("invalid time cap");
        const auto start=Clock::now();pin_one_core();
        pt::ptree cert;pt::read_json(certpath,cert);validate_source_sha(cnf,cert);
        CNF source=read_cnf(cnf);
        Emit emit(proof,start,max_s*0.9);
        const auto fmt=cert.get<std::string>("format");std::string method;
        if(fmt=="pcmax-clause-hall-v1")method=hall_proof(source,cert,emit);
        else if(fmt=="drnas-math5-eo-xor-unit-v1")method=xor_proof(source,cert,emit);
        else fail("unsupported certificate format");
        emit.close();
        run_checker(checker,cnf,proof,proof+".checker.log",start,max_s);
        std::cout<<"NATIVE_BRIDGE_VERIFIED {\"method\":\""<<method<<"\",\"steps\":"<<emit.steps
                 <<",\"rat\":"<<emit.rat<<",\"rup\":"<<emit.rup
                 <<",\"strict_e2e_s\":"<<std::fixed<<std::setprecision(6)<<elapsed_s(start)<<"}\n";
        return 0;
    }catch(const std::exception& ex){
        if(!proof.empty())std::remove(proof.c_str());
        std::cerr<<"NATIVE_BRIDGE_UNKNOWN "<<ex.what()<<"\n";
        return 1;
    }
}

// Versioned, bounded priors. SQLite is accessed outside the native search loop.
#pragma once
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <string>
namespace drnas_context {
constexpr const char* schema="DRNAS_R28_CONTEXT_V1";
struct State {
    bool enabled=false, first=true;
    int key=0,phase=0;
    std::array<std::array<uint64_t,4>,2> prior_n{},new_n{};
    std::array<std::array<double,4>,2> prior_mean{},new_sum{};
    uint64_t loaded=0;
    void init(int context,bool eligible){
        const char* file=std::getenv("DRNAS_CONTEXT_SNAPSHOT");
        enabled=eligible && file && *file;
        if(!enabled)return;
        key=context;
        const auto start=std::chrono::steady_clock::now();
        std::ifstream in(file,std::ios::binary);std::string magic;
        bool ok=bool(in);in.seekg(0,std::ios::end);
        const auto size=in.tellg();ok=ok&&size>=0&&size<=65536;in.seekg(0);
        in>>magic;ok=ok&&magic==schema;
        std::array<std::array<uint64_t,4>,2> n{};
        std::array<std::array<double,4>,2> m{};
        std::array<bool,576> seen{};
        int k=0,p=0,a=0;uint64_t count=0;double mean=0;unsigned rows=0;
        while(ok){
            in>>std::ws;if(in.eof())break;
            if(!(in>>k>>p>>a>>count>>mean)){ok=false;break;}
            if(++rows>576||k<0||k>=72||p<0||p>=2||a<0||a>=4||count>8||!std::isfinite(mean)||mean<0||mean>1){ok=false;break;}
            const size_t idx=size_t(k*8+p*4+a);
            if(seen[idx]){ok=false;break;}seen[idx]=true;
            if(k==key){n[p][a]=count;m[p][a]=mean;}
        }
        if(ok){prior_n=n;prior_mean=m;for(const auto& row:n)for(auto v:row)loaded+=v;}
        const double us=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
        std::cout<<"c R28_CONTEXT_LOAD key="<<key<<" accepted="<<ok<<" prior_weight="<<loaded<<" read_us="<<us<<"\n"<<std::flush;
    }
    void enter(int next,std::array<uint64_t,4>& count,std::array<double,4>& mean){
        phase=next;count=prior_n[phase];mean=prior_mean[phase];first=true;
    }
    int initial_arm(){
        if(!enabled||!first)return -1;
        first=false;int best=-1;
        for(int i=0;i<4;++i)if(prior_n[phase][i] && (best<0||prior_mean[phase][i]>prior_mean[phase][best]))best=i;
        return best;
    }
    void observe(int arm,double reward){if(enabled){++new_n[phase][arm];new_sum[phase][arm]+=reward;}}
    void emit()const{
        if(!enabled)return;
        for(int p=0;p<2;++p)for(int a=0;a<4;++a)if(new_n[p][a])
            std::cout<<std::setprecision(17)<<"c R28_CONTEXT_DELTA key="<<key<<" phase="<<p<<" arm="<<a
                     <<" n="<<new_n[p][a]<<" sum="<<new_sum[p][a]<<"\n";
        std::cout<<std::flush;
    }
};
}

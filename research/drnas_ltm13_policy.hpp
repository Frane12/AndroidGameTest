// DRNAS LTM8: bounded online parameter learning. No logical deductions here.
#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <string>
#include <cstdlib>
#include <cstdio>
#include <iostream>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
namespace ltm8 {
struct Policy {
    bool direct=false, fallback=false;
    unsigned bad_windows=0;
    double best_reward=0;
    uint64_t initial_work=0;
    int last_lbd=0;
    int fixed=-1;
    bool enabled=false,chaos=false;
    int arm=0,quota=75,restart_min=80,restart_max=1500,random_permil=0,flip_permil=0;
    double decay=.95,restart_factor=1.15;
    uint64_t rng=1,windows=0,loaded=0,random_decisions=0;
    std::array<uint64_t,4> count{};
    std::array<double,4> mean{};
    unsigned samples=0;
    double quality=0;
    uint64_t last_work=0;
    std::string path;
    int lock_fd=-1;
    ~Policy(){if(lock_fd>=0){flock(lock_fd,LOCK_UN);close(lock_fd);}}
    uint64_t next(){rng^=rng>>12;rng^=rng<<25;rng^=rng>>27;return rng*2685821657736338717ULL;}
    void choose(){
        arm=0;
        if(direct){
            if(fallback)arm=0;
            else if(fixed>=0)arm=fixed;
            else {
                bool unseen=false;
                for(int i=0;i<4;++i)if(count[i]==0){arm=i;unseen=true;break;}
                if(!unseen){
                    double best=-1e100;uint64_t total=0;for(auto n:count)total+=n;
                    for(int i=0;i<4;++i){
                        const double u=mean[i]+0.12*std::sqrt(std::log(double(total)+1)/count[i]);
                        if(u>best){best=u;arm=i;}
                    }
                }
            }
        }else{
            for(int i=1;i<4;++i)if(mean[i]>mean[arm])arm=i;
            if(next()%1000 < unsigned(chaos?650:60))arm=int(next()%4);
        }
        static const double decays[]={.95,.97,.99,.93};
        static const int maxima[]={1500,750,4000,500};
        decay=decays[arm];restart_max=maxima[arm];restart_min=80;
        restart_factor=arm==2?1.30:1.15;quota=arm==2?50:75;
        random_permil=arm==3?25:0;flip_permil=0;
        if(chaos){
            // Learn the four profile distributions, with reproducible random jitter.
            decay=std::clamp(decay+(double(next()%101)-50)*.001,.85,.995);
            restart_min=32+int(next()%97);
            restart_max=std::max(restart_min+1,restart_max/2+int(next()%unsigned(restart_max)));
            random_permil=50+int(next()%451);flip_permil=int(next()%351);
            quota=(next()%2)?50:75;restart_factor=1.02+double(next()%40)*.01;
        }
    }
    void init(bool wild,uint64_t seed,int bucket){
        enabled=true;chaos=wild;rng=seed?seed:1;
        direct=std::getenv("DRNAS_LTM13_DIRECT")!=nullptr;
        if(direct){
            chaos=false;
            const char* forced=std::getenv("DRNAS_LTM13_FIXED");
            if(forced){fixed=std::atoi(forced);if(fixed<0||fixed>3)fixed=-1;}
        }
        const char* p=std::getenv("DRNAS_LTM8_MEMORY");
        if(!p)p="ltm8_memory";
        if(direct)p=""; // isolate this experimental controller from legacy memory
        if(p && *p){
            path=std::string(p)+(chaos?".chaos.":".fast.")+std::to_string(bucket);
            lock_fd=open((path+".lock").c_str(),O_CREAT|O_RDWR,0600);
            if(lock_fd<0 || flock(lock_fd,LOCK_EX|LOCK_NB)!=0){
                if(lock_fd>=0)close(lock_fd);lock_fd=-1;path.clear();
                std::cerr<<"c LTM8 memory busy/unavailable: session-only learning\n";
            }else{
                std::ifstream in(path);std::string magic;in>>magic;
                std::array<uint64_t,4> c{};std::array<double,4> m{};
                bool ok=magic=="DRNAS_LTM8_V1";
                for(int i=0;i<4;++i){in>>c[i]>>m[i];ok=ok&&bool(in)&&c[i]<=1000000000ULL&&std::isfinite(m[i])&&m[i]>=0&&m[i]<=1;}
                if(ok){count=c;mean=m;for(auto n:count)loaded+=n;}
            }
        }
        choose();
    }
    bool observe(int lbd,uint64_t work){
        quality+=1.0/std::max(1,lbd);++samples;
        if(samples<unsigned(direct?64:chaos?256:512))return false;
        const double effort=double(work-last_work)/samples;
        // A surrogate reward, not a measured claim of SAT solving speed.
        const double reward=.8*quality/samples+.2/(1.+effort/100.);
        if(direct && fixed<0 && windows>=4){
            if(reward<best_reward*.70)++bad_windows;else bad_windows=0;
            if(bad_windows>=3)fallback=true;
        }
        best_reward=std::max(best_reward,reward);
        auto& n=count[arm];auto& m=mean[arm];
        m+= (reward-m)/double(std::min<uint64_t>(++n,32));
        ++windows;
        const int previous=arm;
        samples=0;quality=0;last_work=work;choose();
        if(direct && (windows<=32 || windows%64==0))
            std::cout<<"c LTM13_WINDOW window="<<windows<<" previous="<<previous
                     <<" next="<<arm<<" reward="<<reward<<" effort="<<effort
                     <<" lbd_last="<<lbd<<" count0="<<count[0]<<" count1="<<count[1]
                     <<" count2="<<count[2]<<" count3="<<count[3]
                     <<" reason="<<(fallback?"fallback-low-reward":fixed>=0?"fixed-control":"explore-or-UCB")<<"\n";
        return true;
    }
    void save(){
        if(path.empty() || !windows)return;
        const std::string temp=path+".tmp."+std::to_string(getpid());
        std::ofstream out(temp);out.precision(17);out<<"DRNAS_LTM8_V1\n";
        for(int i=0;i<4;++i)out<<count[i]<<' '<<mean[i]<<'\n';
        out.flush();const bool ok=bool(out);out.close();
        if(!ok || std::rename(temp.c_str(),path.c_str())!=0){
            std::remove(temp.c_str());std::cerr<<"c LTM8 memory save failed\n";
        }
    }
};
}


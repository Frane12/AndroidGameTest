// R28/R153 exact algebra followed by DRNAS native learning, in one executable.
// No external solver is invoked. All stages share one wall-clock deadline.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <sys/time.h>
#include <unistd.h>
int drnas_math_entry(const char*, double);
int drnas_native_entry(int, char**);
static void deadline(int) {
    const char msg[]="c R28_NATIVE deadline\ns UNKNOWN\n";
    (void)!write(STDOUT_FILENO,msg,sizeof(msg)-1);
    _exit(0);
}
int main(int argc,char** argv) {
    using Clock=std::chrono::steady_clock;
    const auto start=Clock::now();
    try {
        if(argc<2){std::cerr<<"usage: drnas_r28_native FILE [--time SEC] [--seed N] [--profile fast|direct|fixed0] [--gf2-ms MS] [--keep75] [--no-selective]\n";return 2;}
        double cap=10,math_ms=50;std::string seed="17",profile="fast";
        bool keep50=true,selective=true;
        for(int i=2;i<argc;++i){
            std::string key=argv[i];
            if(key=="--keep75"){keep50=false;continue;}
            if(key=="--no-selective"){selective=false;continue;}
            if(i+1>=argc)throw std::runtime_error("missing argument");
            std::string value=argv[++i];
            if(key=="--time")cap=std::stod(value);
            else if(key=="--seed"){std::stoull(value);seed=value;}
            else if(key=="--profile")profile=value;
            else if(key=="--gf2-ms")math_ms=std::stod(value);
            else throw std::runtime_error("unknown option");
        }
        if(!std::isfinite(cap)||cap<=0||cap>300||!std::isfinite(math_ms)||math_ms<0||math_ms>1000||
           (profile!="fast"&&profile!="direct"&&profile!="fixed0"))throw std::runtime_error("invalid setting");
        std::signal(SIGALRM,deadline);
        itimerval timer{};timer.it_value.tv_sec=long(cap);
        timer.it_value.tv_usec=long((cap-long(cap))*1000000);
        if(!timer.it_value.tv_sec&&!timer.it_value.tv_usec)timer.it_value.tv_usec=1;
        if(setitimer(ITIMER_REAL,&timer,nullptr))throw std::runtime_error("timer setup failed");
        // Prevent inherited profile flags from changing the declared experiment.
        unsetenv("DRNAS_LTM13_DIRECT");unsetenv("DRNAS_LTM13_FIXED");
        if(profile!="fast")setenv("DRNAS_LTM13_DIRECT","1",1);
        if(profile=="fixed0")setenv("DRNAS_LTM13_FIXED","0",1);
        setenv("DRNAS_R28_KEEP50",keep50?"1":"0",1);
        setenv("DRNAS_R28_SELECTIVE",selective?"1":"0",1);
        const double allowance=std::min(math_ms/1000.,cap*.10);
        int result=allowance>0?drnas_math_entry(argv[1],allowance):0;
        if(result==10||result==20){
            timer={};setitimer(ITIMER_REAL,&timer,nullptr);
            std::cout<<"c R28_NATIVE route=exact_gf2 profile="<<profile<<"\n";return result;
        }
        if(result!=0)throw std::runtime_error("exact stage failed");
        const double elapsed=std::chrono::duration<double>(Clock::now()-start).count();
        if(elapsed>=cap){std::cout<<"s UNKNOWN\n";return 0;}
        std::cout<<"c R28_NATIVE route=native_learning profile="<<profile
                 <<" exact_s="<<elapsed<<" keep50="<<keep50<<" selective="<<selective<<"\n"<<std::flush;
        std::vector<std::string> args={"drnas_native",argv[1],"--mode","LTM8_FAST","--time",std::to_string(cap-elapsed),"--seed",seed,"--policy","1.0,0.85"};
        std::vector<char*> ptr;for(auto& s:args)ptr.push_back(s.data());ptr.push_back(nullptr);
        result=drnas_native_entry(int(args.size()),ptr.data());
        timer={};setitimer(ITIMER_REAL,&timer,nullptr);return result;
    }catch(const std::exception& e){std::cerr<<"R28_NATIVE_ERROR "<<e.what()<<"\n";return 2;}
}

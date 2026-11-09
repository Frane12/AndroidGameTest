/* DRNAS C16P-D: delayed-start POSIX C11 multi-process SAT portfolio controller.
   Each child solves the EXACT SAME original CNF. No shared CDCL state.
   SAT: checked against every original clause BEFORE becoming winner.
   UNSAT: cannot be independently certified without a checked proof;
     explicit --reference-unsat-agreement option accepts a solver's UNSAT
     only if it matches a frozen published reference, and labels it clearly.
   Timeout: UNKNOWN. Race winner is first acceptable completed result.
   Include creation, checking, child cancellation and wait4 CPU accounting
   in full E2E wall. No portfolio speedup claim without CPU/cap controls.
*/
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>
#include <time.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <fcntl.h>
#include <signal.h>

#define MAX_WORKERS 3
typedef struct {const char *name,*path;int novivify;pid_t pid;int fd;
                int done,exit_code,signal_code,was_killed,solver_status;
                double cpu_s,done_s,delay_s,actual_launch_s;int started;long maxrss_kb;} Worker;
typedef struct {int n,m;} Header;
static void fatal(const char *m){fprintf(stderr,"C16PD_FATAL %s\n",m);exit(3);}
static double now_s(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))fatal("clock");return (double)t.tv_sec+t.tv_nsec*1e-9;}
static void tick_ms(int ms){struct timespec ts={ms/1000,(ms%1000)*1000000L};while(nanosleep(&ts,&ts)<0&&errno==EINTR){}}
static double tv_s(struct timeval v){return (double)v.tv_sec+1e-6*v.tv_usec;}
static Header header(const char *filename){
 FILE *f=fopen(filename,"r");if(!f)fatal("cnf_open");
 char *line=NULL;size_t len=0;ssize_t got;Header h={0,0};int found=0;
 while((got=getline(&line,&len,f))>=0){(void)got;
   char *p=line;while(isspace((unsigned char)*p))p++;
   if(*p=='p'){char extra;
     if(found||sscanf(p,"p cnf %d %d %c",&h.n,&h.m,&extra)!=2 ||
        h.n<1||h.n>1000000||h.m<0||h.m>30000000)fatal("cnf_bad_header");
     found=1;break;
   }
 }
 free(line);fclose(f);if(!found)fatal("cnf_no_header");return h;
}
static int parse_solver_output(int fd,int n,int8_t *values){
 int copy=dup(fd);if(copy<0)fatal("dup_log");if(lseek(copy,0,SEEK_SET)<0)fatal("seek_log");
 FILE *f=fdopen(copy,"r");if(!f)fatal("fdopen");
 char *line=NULL;size_t cap=0;int sat=0,unsat=0,bad=0;
 while(getline(&line,&cap,f)>=0){
   char *p=line;while(isspace((unsigned char)*p))p++;
   if(*p=='s'&&isspace((unsigned char)p[1])){
     p++;while(isspace((unsigned char)*p))p++;
     if(!strncmp(p,"UNSATISFIABLE",13))unsat=1;
     else if(!strncmp(p,"SATISFIABLE",11))sat=1;
   }
   if(*p!='v'||!isspace((unsigned char)p[1]))continue;
   p++;
   while(*p){
     while(isspace((unsigned char)*p))p++;
     if(!*p||*p=='c')break;
     errno=0;char *end=NULL;long v=strtol(p,&end,10);
     if(end==p||errno||v < -(long)n||v > n){bad=1;break;}
     p=end;
     if(!v)continue;
     int k=(int)labs(v);int8_t z=v>0?1:-1;
     if(values[k]!=0&&values[k]!=z)bad=1;
     values[k]=z;
   }
 }
 free(line);fclose(f);
 if(bad||sat==unsat)return 0;
 return sat?10:20;
}
static int original_cnf_witness(const char *path,const int8_t *v,Header h){
 FILE *f=fopen(path,"r");if(!f)fatal("original_cnf_open");
 char *line=NULL;size_t cap=0;int seen_header=0,clauses=0,clausesat=0,have_literal=0,okay=1;
 while(getline(&line,&cap,f)>=0){
   char *p=line;while(isspace((unsigned char)*p))p++;
   if(!*p||*p=='c'||*p=='%')continue;
   if(*p=='p'){seen_header=1;continue;}
   if(!seen_header){okay=0;break;}
   while(*p){
     while(isspace((unsigned char)*p))p++;
     if(!*p||*p=='c')break;
     errno=0;char *end=NULL;long l=strtol(p,&end,10);
     if(end==p||errno||l<-(long)h.n||l>h.n){okay=0;break;}
     p=end;
     if(l==0){
       if(!clausesat){okay=0;break;}
       clauses++;clausesat=0;have_literal=0;
     }else{
       int8_t z=v[labs(l)];
       if(z!=0&&((l>0&&z==1)||(l<0&&z==-1)))clausesat=1;
       have_literal=1;
     }
   }
   if(!okay)break;
 }
 if(have_literal||!seen_header||clauses!=h.m)okay=0;
 free(line);fclose(f);return okay;
}
static void start_worker(Worker *w,const char *cnf,double start){
 char tmp[]="/tmp/drnas-c16p-XXXXXX";
 int fd=mkstemp(tmp);if(fd<0)fatal("mkstemp");unlink(tmp);
 pid_t pid=fork();if(pid<0)fatal("fork");
 if(pid==0){
   (void)setpgid(0,0);
   if(dup2(fd,STDOUT_FILENO)<0||dup2(fd,STDERR_FILENO)<0)_exit(126);
   close(fd);
   struct rlimit core={0,0};(void)setrlimit(RLIMIT_CORE,&core);
   if(w->novivify)execl(w->path,w->path,"--no-vivify",cnf,(char *)NULL);
   else execl(w->path,w->path,cnf,(char *)NULL);
   _exit(127);
 }
 (void)setpgid(pid,pid);w->pid=pid;w->fd=fd;w->done=0;w->started=1;w->actual_launch_s=now_s()-start;w->solver_status=0;
}
static void reap(Worker *w,int blocking,double start){
 if(!w->started||w->done)return;
 int status=0;struct rusage usage={0};
 pid_t got=wait4(w->pid,&status,blocking?0:WNOHANG,&usage);
 if(got==0)return;
 if(got<0){if(errno==EINTR)return;fatal("wait4");}
 w->done=1;w->done_s=now_s()-start;
 w->exit_code=WIFEXITED(status)?WEXITSTATUS(status):-1;
 w->signal_code=WIFSIGNALED(status)?WTERMSIG(status):0;
 w->cpu_s=tv_s(usage.ru_utime)+tv_s(usage.ru_stime);
 w->maxrss_kb=usage.ru_maxrss;
}
static void terminate(Worker *w){if(w->started&&w->pid>0&&!w->done){
    if(kill(-w->pid,SIGTERM)<0&&errno==ESRCH)(void)kill(w->pid,SIGTERM);
    w->was_killed=1;
 }}
static const char *status_str(int code){return code==10?"SAT":code==20?"UNSAT":"UNKNOWN";}
int main(int argc,char **argv){
 if(argc!=7&&argc!=8){
   fprintf(stderr,"usage: c16p MODE CNF KISSAT CADICAL CAP_SECONDS REFERENCE_STATUS [--reference-unsat-agreement]\n");
   fprintf(stderr,"MODE: kissat cadical novivify p2 p3 d1 d4 d3way\n");return 2;
 }
 const char *mode=argv[1],*cnf=argv[2],*kissat=argv[3],*cadical=argv[4],*expected=argv[6];
 int allow=argc==8&&!strcmp(argv[7],"--reference-unsat-agreement");
 if(argc==8&&!allow)fatal("unknown_option");
 int exp=!strcmp(expected,"SAT")?10:!strcmp(expected,"UNSAT")?20:0;
 if(!exp)fatal("reference_must_be_SAT_or_UNSAT");
 char *end=NULL;errno=0;double cap=strtod(argv[5],&end);
 if(errno||end==argv[5]||*end||!(cap>=0.05&&cap<=300))fatal("invalid_cap");
 if(access(cnf,R_OK)||access(kissat,X_OK)||access(cadical,X_OK))fatal("input_or_binary_unreadable");
 Header h=header(cnf);
 Worker w[MAX_WORKERS]={0};int count=0;
 int delayed_1=!strcmp(mode,"d1"),delayed_4=!strcmp(mode,"d4"),delayed_3=!strcmp(mode,"d3way");
 if(!strcmp(mode,"kissat")||!strcmp(mode,"p2")||!strcmp(mode,"p3")||delayed_1||delayed_4||delayed_3)
     w[count++]=(Worker){.name="kissat",.path=kissat,.delay_s=0};
 if(!strcmp(mode,"cadical")||!strcmp(mode,"p3")||delayed_3)
     w[count++]=(Worker){.name="cadical",.path=cadical,.delay_s=delayed_3?8.0:0};
 if(!strcmp(mode,"novivify")||!strcmp(mode,"p2")||!strcmp(mode,"p3")||delayed_1||delayed_4||delayed_3)
     w[count++]=(Worker){.name="novivify",.path=cadical,.novivify=1,
          .delay_s=delayed_1?1.0:delayed_4?4.0:delayed_3?2.0:0};
 if(!count||count>MAX_WORKERS)fatal("unknown_mode");
 int winner=-1,result=0,unverified_unsat=0,invalid=0,checked_sat=0;
 double start=now_s();const double deadline=start+cap;
 for(int i=0;i<count;i++)if(w[i].delay_s<=0)start_worker(&w[i],cnf,start);
 while(now_s()<deadline&&winner<0){
   int all_done=1;
   double at=now_s()-start;
   for(int i=0;i<count;i++)
     if(!w[i].started&&at>=w[i].delay_s&&at+0.05<cap)
       start_worker(&w[i],cnf,start);
   for(int i=0;i<count;i++){
     if(!w[i].started){all_done=0;continue;}
     reap(&w[i],0,start);
     if(!w[i].done){all_done=0;continue;}
     if(w[i].solver_status)continue;
     w[i].solver_status=-1;
     if(w[i].exit_code!=10&&w[i].exit_code!=20)continue;
     int8_t *assignment=calloc((size_t)h.n+1,sizeof(int8_t));
     if(!assignment)fatal("assignment_alloc");
     int code=parse_solver_output(w[i].fd,h.n,assignment);
     if(code!=w[i].exit_code){invalid=1;free(assignment);break;}
     if(code==10){
       int valid=original_cnf_witness(cnf,assignment,h);free(assignment);
       if(!valid||exp!=10){invalid=1;break;}
       checked_sat++;winner=i;result=10;break;
     }
     free(assignment);
     if(exp!=20){invalid=1;break;}
     if(!allow){unverified_unsat++;continue;}
     unverified_unsat++;winner=i;result=20;break;
   }
   if(invalid||all_done)break;
   if(winner<0)tick_ms(2);
 }
 for(int i=0;i<count;i++)if(w[i].started&&!w[i].done)terminate(&w[i]);
 tick_ms(8);
 for(int i=0;i<count;i++)if(w[i].started&&!w[i].done){
   if(kill(-w[i].pid,SIGKILL)<0&&errno==ESRCH)(void)kill(w[i].pid,SIGKILL);
 }
 for(int i=0;i<count;i++)if(w[i].started){
   while(!w[i].done){reap(&w[i],1,start);}
   close(w[i].fd);
 }
 double wall=now_s()-start,cpu=0;long rss=0;int launched=0;
 for(int i=0;i<count;i++)if(w[i].started){
     cpu+=w[i].cpu_s;rss+=w[i].maxrss_kb;launched++;
 }
 if(wall>cap||winner<0||invalid)result=0;
 printf("C16PD_RESULT {\"mode\":\"%s\",\"status\":\"%s\",\"winner\":\"%s\",",mode,
        status_str(result),result==0?"none":w[winner].name);
 printf("\"wall_s\":%.6f,\"cpu_sum_s\":%.6f,\"rss_sum_upper_kb\":%ld,",wall,cpu,rss);
 printf("\"cap_s\":%.3f,\"processes\":%d,\"launched_processes\":%d,\"online_cpus\":%ld,",cap,count,launched,sysconf(_SC_NPROCESSORS_ONLN));
 printf("\"sat_original_verified\":%s,\"unsat_reference_agreement_only\":%s,\"unsat_independent_proof\":false,",result==10?"true":"false",result==20?"true":"false");
 printf("\"unsat_unverified_reports\":%d,\"invalid_result_detected\":%s,\"workers\":[",unverified_unsat,invalid?"true":"false");
 for(int i=0;i<count;i++){
   if(i)putchar(',');
   printf("{\"name\":\"%s\",\"started\":%s,\"planned_delay_s\":%.3f,\"actual_launch_s\":%.6f,\"exit\":%d,\"signal\":%d,\"killed\":%s,\"cpu_s\":%.6f,\"rss_kb\":%ld}",
     w[i].name,w[i].started?"true":"false",w[i].delay_s,
     w[i].actual_launch_s,w[i].exit_code,w[i].signal_code,
     w[i].was_killed?"true":"false",w[i].cpu_s,w[i].maxrss_kb);
 }
 puts("]}");fflush(stdout);
 if(invalid)return 3;
 return result==10?10:result==20?20:0;
}

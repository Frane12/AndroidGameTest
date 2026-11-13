#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>
#include <stdio.h>
int main(int argc,char**argv){
 if(argc<3)return 125;
 pid_t pid=fork();if(pid<0)return 125;
 if(!pid){execvp(argv[2],argv+2);_exit(127);}
 int status;struct rusage ru;
 if(wait4(pid,&status,0,&ru)<0)return 125;
 FILE*f=fopen(argv[1],"w");if(!f)return 125;
 fprintf(f,"%ld\n",ru.ru_maxrss);fclose(f);
 return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
}

#ifndef SIM_SYS_RESOURCE_H
#define SIM_SYS_RESOURCE_H
typedef unsigned long rlim_t;
struct rlimit { rlim_t rlim_cur; rlim_t rlim_max; };
#define RLIMIT_CPU 0
#define setrlimit __libc_setrlimit
int setrlimit(int iResource, const struct rlimit *psRlimit);
#endif

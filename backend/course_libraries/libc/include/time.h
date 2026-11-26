#ifndef SIM_TIME_H
#define SIM_TIME_H
typedef long clock_t;
#define CLOCKS_PER_SEC 1000000L
#define clock __libc_clock
clock_t clock(void);
#endif

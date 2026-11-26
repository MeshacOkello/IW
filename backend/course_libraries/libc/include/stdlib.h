#ifndef SIM_STDLIB_H
#define SIM_STDLIB_H
#include <stddef.h>
#define EXIT_SUCCESS 0
#define EXIT_FAILURE 1
#define RAND_MAX 2147483647
#define rand __libc_rand
void *malloc(size_t size);
void *calloc(size_t count, size_t size);
void free(void *p);
void exit(int status);
int rand(void);
#endif

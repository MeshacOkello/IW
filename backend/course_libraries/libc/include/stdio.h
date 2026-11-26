/* The part of <stdio.h> the bundled course code uses. Formatting is done by
   libc.c inside the bundle; only finished text reaches the simulator. */
#ifndef SIM_STDIO_H
#define SIM_STDIO_H
#include <stddef.h>
#include <stdarg.h>

typedef struct SimFile FILE;
#define stdout ((FILE *)1)
#define stderr ((FILE *)2)
#define EOF (-1)

#define printf  __libc_printf
#define fprintf __libc_fprintf
#define putchar __libc_putchar
#define fflush  __libc_fflush
#define sscanf  __libc_sscanf

int printf(const char *pcFormat, ...);
int fprintf(FILE *psFile, const char *pcFormat, ...);
int putchar(int c);
int fflush(FILE *psFile);
int sscanf(const char *pcStr, const char *pcFormat, ...);
#endif

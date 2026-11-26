#ifndef SIM_CTYPE_H
#define SIM_CTYPE_H
static inline int isxdigit(int c)
{
   return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}
#endif

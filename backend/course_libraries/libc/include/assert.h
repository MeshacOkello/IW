#ifndef SIM_ASSERT_H
#define SIM_ASSERT_H
void __libc_assert_fail(const char *pcExpr, const char *pcFile, int iLine,
                        const char *pcFunction);
#ifdef NDEBUG
#define assert(e) ((void)0)
#else
#define assert(e) ((e) ? (void)0 : __libc_assert_fail(#e, __FILE__, __LINE__, __func__))
#endif
#endif

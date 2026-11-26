/*--------------------------------------------------------------------*/
/* libc.c                                                             */
/*                                                                    */
/* The C library functions bundled course code needs that the         */
/* simulator does not provide itself. They are compiled into each     */
/* bundle with that bundle's sources, so they run as ordinary ARM64   */
/* code. Output leaves through the simulator's own printf, called     */
/* with "%s", so the simulator only ever receives finished text.      */
/*--------------------------------------------------------------------*/

#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/resource.h>
#include <assert.h>

/* The simulator's printf, under a C name that does not collide with the
   printf macro from <stdio.h>. */
#ifdef __APPLE__
/* Lets the bundle be built and checked as a native program too. */
int __simulator_printf(const char *pcFormat, ...) __asm__("_printf");
#else
int __simulator_printf(const char *pcFormat, ...) __asm__("printf");
#endif

/* argv[0], set by the loader, for assertion messages. */
const char *__libc_program_name = "a.out";

/*--------------------------------------------------------------------*/

enum {BUFFER_SIZE = 512};

struct Output
{
   char acBuffer[BUFFER_SIZE + 1];
   int iLength;
   int iCount;
};

static void flushOutput(struct Output *psOutput)
{
   if (psOutput->iLength == 0)
      return;
   psOutput->acBuffer[psOutput->iLength] = '\0';
   __simulator_printf("%s", psOutput->acBuffer);
   psOutput->iLength = 0;
}

static void emit(struct Output *psOutput, char c)
{
   /* The simulator's printf stops at a null byte, so one is passed on
      by itself through a "%c" conversion. */
   if (c == '\0')
   {
      flushOutput(psOutput);
      __simulator_printf("%c", 0);
      psOutput->iCount++;
      return;
   }
   if (psOutput->iLength == BUFFER_SIZE)
      flushOutput(psOutput);
   psOutput->acBuffer[psOutput->iLength++] = c;
   psOutput->iCount++;
}

static void emitPadded(struct Output *psOutput, const char *pcText, int iLength,
                       int iWidth, int iLeft, char cPad)
{
   int i;
   if (! iLeft)
   {
      /* Zero padding goes after a sign, as in -0005. */
      if (cPad == '0' && iLength > 0 && pcText[0] == '-')
      {
         emit(psOutput, '-');
         pcText++;
         iLength--;
         iWidth--;
      }
      for (i = iLength; i < iWidth; i++)
         emit(psOutput, cPad);
   }
   for (i = 0; i < iLength; i++)
      emit(psOutput, pcText[i]);
   if (iLeft)
      for (i = iLength; i < iWidth; i++)
         emit(psOutput, ' ');
}

/* Write ulValue in iBase into the end of pcEnd's buffer, returning the
   first character. */
static char *formatUnsigned(char *pcEnd, unsigned long ulValue, unsigned long ulBase,
                            int iUpper)
{
   const char *pcDigits = iUpper ? "0123456789ABCDEF" : "0123456789abcdef";
   *--pcEnd = '\0';
   do
   {
      *--pcEnd = pcDigits[ulValue % ulBase];
      ulValue /= ulBase;
   } while (ulValue != 0);
   return pcEnd;
}

static int length(const char *pc)
{
   int i = 0;
   while (pc[i] != '\0')
      i++;
   return i;
}

static int format(const char *pcFormat, va_list ap)
{
   struct Output sOutput;
   char acNumber[48];
   sOutput.iLength = 0;
   sOutput.iCount = 0;

   for ( ; *pcFormat != '\0'; pcFormat++)
   {
      int iLeft = 0;
      char cPad = ' ';
      int iWidth = 0;
      int iPrecision = -1;
      int iLong = 0;
      char *pcText;

      if (*pcFormat != '%')
      {
         emit(&sOutput, *pcFormat);
         continue;
      }
      pcFormat++;
      for (;; pcFormat++)
      {
         if (*pcFormat == '-')
            iLeft = 1;
         else if (*pcFormat == '0')
            cPad = '0';
         else if (*pcFormat != '+' && *pcFormat != ' ' && *pcFormat != '#')
            break;
      }
      while (*pcFormat >= '0' && *pcFormat <= '9')
         iWidth = iWidth * 10 + (*pcFormat++ - '0');
      if (*pcFormat == '.')
      {
         iPrecision = 0;
         pcFormat++;
         while (*pcFormat >= '0' && *pcFormat <= '9')
            iPrecision = iPrecision * 10 + (*pcFormat++ - '0');
      }
      while (*pcFormat == 'l')
      {
         iLong = 1;
         pcFormat++;
      }

      switch (*pcFormat)
      {
         case 'd':
         case 'i':
         {
            long lValue = iLong ? va_arg(ap, long) : (long)va_arg(ap, int);
            unsigned long ulMagnitude = lValue < 0 ? 0UL - (unsigned long)lValue
                                                   : (unsigned long)lValue;
            pcText = formatUnsigned(acNumber + sizeof(acNumber), ulMagnitude, 10, 0);
            if (lValue < 0)
               *--pcText = '-';
            emitPadded(&sOutput, pcText, length(pcText), iWidth, iLeft, cPad);
            break;
         }
         case 'u':
         case 'x':
         case 'X':
         {
            unsigned long ulValue = iLong ? va_arg(ap, unsigned long)
                                          : (unsigned long)va_arg(ap, unsigned int);
            pcText = formatUnsigned(acNumber + sizeof(acNumber), ulValue,
                                    *pcFormat == 'u' ? 10 : 16, *pcFormat == 'X');
            emitPadded(&sOutput, pcText, length(pcText), iWidth, iLeft, cPad);
            break;
         }
         case 'p':
         {
            unsigned long ulValue = (unsigned long)va_arg(ap, void *);
            pcText = formatUnsigned(acNumber + sizeof(acNumber), ulValue, 16, 0);
            *--pcText = 'x';
            *--pcText = '0';
            emitPadded(&sOutput, pcText, length(pcText), iWidth, iLeft, ' ');
            break;
         }
         case 'f':
         {
            double dValue = va_arg(ap, double);
            unsigned long ulWhole;
            unsigned long ulFraction;
            unsigned long ulScale = 1;
            int iDigits = iPrecision < 0 ? 6 : iPrecision;
            int i;
            char *pcEnd = acNumber + sizeof(acNumber);
            int iNegative = dValue < 0;
            if (iNegative)
               dValue = -dValue;
            for (i = 0; i < iDigits; i++)
               ulScale *= 10;
            ulWhole = (unsigned long)dValue;
            ulFraction = (unsigned long)((dValue - (double)ulWhole) * (double)ulScale + 0.5);
            if (ulFraction >= ulScale)
            {
               ulWhole++;
               ulFraction -= ulScale;
            }
            *--pcEnd = '\0';
            for (i = 0; i < iDigits; i++)
            {
               *--pcEnd = (char)('0' + ulFraction % 10);
               ulFraction /= 10;
            }
            if (iDigits > 0)
               *--pcEnd = '.';
            do
            {
               *--pcEnd = (char)('0' + ulWhole % 10);
               ulWhole /= 10;
            } while (ulWhole != 0);
            pcText = pcEnd;
            if (iNegative)
               *--pcText = '-';
            emitPadded(&sOutput, pcText, length(pcText), iWidth, iLeft, cPad);
            break;
         }
         case 'c':
         {
            char c = (char)va_arg(ap, int);
            emitPadded(&sOutput, &c, 1, iWidth, iLeft, ' ');
            break;
         }
         case 's':
         {
            const char *pcValue = va_arg(ap, const char *);
            int iLength = length(pcValue);
            if (iPrecision >= 0 && iPrecision < iLength)
               iLength = iPrecision;
            emitPadded(&sOutput, pcValue, iLength, iWidth, iLeft, ' ');
            break;
         }
         case '%':
            emit(&sOutput, '%');
            break;
         default:
            emit(&sOutput, '%');
            if (*pcFormat == '\0')
               pcFormat--;
            else
               emit(&sOutput, *pcFormat);
            break;
      }
   }
   flushOutput(&sOutput);
   return sOutput.iCount;
}

int printf(const char *pcFormat, ...)
{
   int iCount;
   va_list ap;
   va_start(ap, pcFormat);
   iCount = format(pcFormat, ap);
   va_end(ap);
   return iCount;
}

/* stdout and stderr share the simulator's one output stream, as they
   share a terminal. */
int fprintf(FILE *psFile, const char *pcFormat, ...)
{
   int iCount;
   va_list ap;
   (void)psFile;
   va_start(ap, pcFormat);
   iCount = format(pcFormat, ap);
   va_end(ap);
   return iCount;
}

int putchar(int c)
{
   __simulator_printf("%c", c);
   return c & 0xff;
}

int fflush(FILE *psFile)
{
   (void)psFile;
   return 0;
}

/* Only the "%d" conversion, which is all the course code asks for. */
int sscanf(const char *pcStr, const char *pcFormat, ...)
{
   va_list ap;
   int *piValue;
   long lValue = 0;
   int iSign = 1;
   int iDigits = 0;

   if (! (pcFormat[0] == '%' && pcFormat[1] == 'd' && pcFormat[2] == '\0'))
      return 0;
   while (*pcStr == ' ' || (*pcStr >= '\t' && *pcStr <= '\r'))
      pcStr++;
   if (*pcStr == '-' || *pcStr == '+')
   {
      if (*pcStr == '-')
         iSign = -1;
      pcStr++;
   }
   while (*pcStr >= '0' && *pcStr <= '9')
   {
      lValue = lValue * 10 + (*pcStr++ - '0');
      iDigits++;
   }
   if (iDigits == 0)
      return *pcStr == '\0' ? EOF : 0;
   va_start(ap, pcFormat);
   piValue = va_arg(ap, int *);
   *piValue = (int)(iSign * lValue);
   va_end(ap);
   return 1;
}

/*--------------------------------------------------------------------*/

/* glibc's rand(): the additive feedback generator random_r uses for its
   default TYPE_3 state, seeded with 1. It yields the same sequence as
   armlab, so randomized tests print the same numbers there and here. */

enum {RAND_DEGREE = 31, RAND_SEPARATION = 3};

static int aiRandState[RAND_DEGREE];
static int iRandFront;
static int iRandRear;
static int iRandSeeded = 0;

static int nextRandom(void)
{
   unsigned int uValue;
   aiRandState[iRandFront] = (int)((unsigned int)aiRandState[iRandFront]
                                   + (unsigned int)aiRandState[iRandRear]);
   uValue = (unsigned int)aiRandState[iRandFront];
   iRandFront = (iRandFront + 1) % RAND_DEGREE;
   iRandRear = (iRandRear + 1) % RAND_DEGREE;
   return (int)(uValue >> 1);
}

static void seedRandom(unsigned int uSeed)
{
   long lWord;
   int i;
   if (uSeed == 0)
      uSeed = 1;
   aiRandState[0] = (int)uSeed;
   lWord = (long)(int)uSeed;
   for (i = 1; i < RAND_DEGREE; i++)
   {
      long lHigh = lWord / 127773;
      long lLow = lWord % 127773;
      lWord = 16807 * lLow - 2836 * lHigh;
      if (lWord < 0)
         lWord += 2147483647;
      aiRandState[i] = (int)lWord;
   }
   iRandFront = RAND_SEPARATION;
   iRandRear = 0;
   for (i = 0; i < 10 * RAND_DEGREE; i++)
      (void)nextRandom();
}

int rand(void)
{
   if (! iRandSeeded)
   {
      seedRandom(1);
      iRandSeeded = 1;
   }
   return nextRandom();
}

/*--------------------------------------------------------------------*/

/* The simulator has no clock: CPU time reads as zero. */
clock_t clock(void)
{
   return 0;
}

/* The simulator limits a run by its instruction count instead. */
int setrlimit(int iResource, const struct rlimit *psRlimit)
{
   (void)iResource;
   (void)psRlimit;
   return 0;
}

/* glibc's message, followed by abort's exit status. */
void __libc_assert_fail(const char *pcExpr, const char *pcFile, int iLine,
                        const char *pcFunction)
{
   fprintf(stderr, "%s: %s:%d: %s: Assertion `%s' failed.\n",
           __libc_program_name, pcFile, iLine, pcFunction, pcExpr);
   fprintf(stderr, "Aborted (core dumped)\n");
   exit(134);
}

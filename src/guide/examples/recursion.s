// Compute 4! recursively. Each call reserves a stack frame.
        .section .text

        // long fact(long n)
        .equ    FACT_STACK_BYTECOUNT, 16
        .equ    LN, 8           // where fact keeps n in its frame
fact:
        sub     sp, sp, FACT_STACK_BYTECOUNT
        str     x30, [sp]       // save the return address
        str     x0, [sp, LN]    // save n

        cmp     x0, 1
        bgt     factRecurse     // n > 1: recurse
        mov     x0, 1           // base case: fact(n) = 1
        b       factReturn
factRecurse:
        sub     x0, x0, 1
        bl      fact            // x0 = fact(n - 1)
        ldr     x1, [sp, LN]    // reload this call's n
        mul     x0, x0, x1      // x0 = n * fact(n - 1)
factReturn:
        ldr     x30, [sp]
        add     sp, sp, FACT_STACK_BYTECOUNT
        ret

        // int main(void)
        .equ    MAIN_STACK_BYTECOUNT, 16
        .global main
main:
        sub     sp, sp, MAIN_STACK_BYTECOUNT
        str     x30, [sp]

        mov     x0, 4
        bl      fact            // x0 = fact(4) = 24

        ldr     x30, [sp]
        add     sp, sp, MAIN_STACK_BYTECOUNT
        ret                     // return 24

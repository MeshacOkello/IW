//----------------------------------------------------------------------
// euclid.s
// Author: Bob Dondero
//----------------------------------------------------------------------

        .section .rodata

promptStr:
        .string "Enter an integer: "
scanfFormatStr:
        .string "%ld"
printfFormatStr:
        .string "The gcd is %ld\n"

//----------------------------------------------------------------------
        .section .data

//----------------------------------------------------------------------
        .section .bss

//----------------------------------------------------------------------
        .section .text

        //--------------------------------------------------------------
        // Return the greatest common divisor of lFirst and lSecond.
        // long gcd(long lFirst, long lSecond)
        //--------------------------------------------------------------

        // Must be a multiple of 16
        .equ    GCD_STACK_BYTECOUNT, 48

        // Local variable stack offsets:
        .equ    LABSSECOND, 8
        .equ    LABSFIRST, 16
        .equ    LTEMP,     24

        // Parameter stack offsets:
        .equ    LSECOND,   32
        .equ    LFIRST,    40

gcd:
        // Prolog
        sub     sp, sp, GCD_STACK_BYTECOUNT
        str     x30, [sp]
        str     x0, [sp, LFIRST]
        str     x1, [sp, LSECOND]

        // long lTemp
        // long lAbsFirst
        // long lAbsSecond

        // lAbsFirst = labs(lFirst)
        ldr     x0, [sp, LFIRST]
        bl      labs
        str     x0, [sp, LABSFIRST]

        // lAbsSecond = labs(lSecond)
        ldr     x0, [sp, LSECOND]
        bl      labs
        str     x0, [sp, LABSSECOND]

gcdLoop:
        // if (lAbsSecond == 0) goto gcdLoopEnd
        ldr     x0, [sp, LABSSECOND]
        cmp     x0, 0
        beq     gcdLoopEnd

        // lTemp = lAbsFirst % lAbsSecond
        // remainder = (dividend - (quotient * divisor))
        ldr     x0, [sp, LABSFIRST]
        ldr     x1, [sp, LABSSECOND]
        sdiv    x2, x0, x1
        mul     x3, x2, x1
        sub     x4, x0, x3
        str     x4, [sp, LTEMP]

        // lAbsFirst = lAbsSecond
        ldr     x0, [sp, LABSSECOND]
        str     x0, [sp, LABSFIRST]

        // lAbsSecond = lTemp
        ldr     x0, [sp, LTEMP]
        str     x0, [sp, LABSSECOND]

        // goto gcdLoop
        b       gcdLoop

gcdLoopEnd:
        // Epilog and return lAbsFirst
        ldr     x0, [sp, LABSFIRST]
        ldr     x30, [sp]
        add     sp, sp, GCD_STACK_BYTECOUNT
        ret

        .size   gcd, (. - gcd)

        //--------------------------------------------------------------
        // Read two integers from stdin. Compute their greatest common
        // divisor, and write it to stdout. Return 0.
        // int main(void)
        //--------------------------------------------------------------

        // Must be a multiple of 16
        .equ    MAIN_STACK_BYTECOUNT, 32

        // Local variables stack offsets:
        .equ    LGCD,  8
        .equ    L2,    16
        .equ    L1,    24

        .global main

main:
        // Prolog
        sub     sp, sp, MAIN_STACK_BYTECOUNT
        str     x30, [sp]

        // long l1
        // long l2
        // long lGcd

        // printf("Enter an integer: ")
        adr     x0, promptStr
        bl      printf

        // scanf("%ld", &l1)
        adr     x0, scanfFormatStr
        add     x1, sp, L1
        bl      scanf

        // printf("Enter an integer: ")
        adr     x0, promptStr
        bl      printf

        // scanf("%ld", &l2)
        adr     x0, scanfFormatStr
        add     x1, sp, L2
        bl      scanf

        // lGcd = gcd(l1, l2)
        ldr     x0, [sp, L1]
        ldr     x1, [sp, L2]
        bl      gcd
        str     x0, [sp, LGCD]

        // printf("The gcd is %ld\n", lGcd)
        adr     x0, printfFormatStr
        ldr     x1, [sp, LGCD]
        bl      printf

        // Epilog and return 0
        mov     w0, 0
        ldr     x30, [sp]
        add     sp, sp, MAIN_STACK_BYTECOUNT
        ret

        .size   main, (. - main)
